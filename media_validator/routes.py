# -*- coding: utf-8 -*-
"""媒体产物检测 · 路由（独立模块，不依赖框架任何代码）

页面 + API 一张蓝图：
    GET    /media-validator/                    检测页
    GET    /media-validator/api/overview        工具可用性 + 统计
    GET    /media-validator/api/rules           三类默认规则（前端渲染表单用）
    POST   /media-validator/api/upload          上传：multipart files[]（拖拽/本地选择）
                                                    或 form.sources（链接 http/https / 本地路径
                                                    ~·绝对·相对项目根，JSON 数组）→ 建任务；
                                                    可带规则并立即检测
    POST   /media-validator/api/detect          批量开始检测 {ids: [...]}
    GET    /media-validator/api/tasks           任务列表（含报告）
    GET    /media-validator/api/task/<id>       单任务（轮询）
    POST   /media-validator/api/task/<id>/detect  重新检测（可带规则）
    DELETE /media-validator/api/task/<id>       删除任务与文件

检测在后台线程执行（ffmpeg 全量解码耗时不可控），前端轮询任务状态。
状态机：PENDING → RUNNING → PASSED / FAILED / ERROR（ERROR 仅指基础设施故障）。
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

from flask import Blueprint, abort, jsonify, render_template, request

from media_validator import engine
from media_validator import rules as rules_mod
from media_validator import store

bp = Blueprint(
    'media_validator', __name__,
    template_folder='templates', static_folder='static', static_url_path='static',
    url_prefix='/media-validator',
)

_detecting = set()          # 正在检测的任务 id（防重复提交）
_detect_lock = threading.Lock()


def sweep_interrupted():
    """把遗留的 RUNNING 任务置为 ERROR。

    检测跑在后台线程，平台重启/进程退出会杀死线程而任务状态停在 RUNNING——
    没有本扫描的话该任务永远显示「检测中」、前端永远轮询。蓝图加载时执行一次。
    """
    swept = []
    for t in store.load_tasks():
        if t.get('status') == 'RUNNING':
            t['status'] = 'ERROR'
            t['error'] = '检测中断（平台重启或进程退出），请重新检测'
            t['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            store.upsert_task(t)
            swept.append(t['id'])
    return swept


sweep_interrupted()


# ---------------------------------------------------------------- 页面
@bp.route('/')
def page():
    return render_template('mv.html')


# ---------------------------------------------------------------- 查询
@bp.route('/api/overview')
def api_overview():
    tasks = store.load_tasks()
    stats = {'total': len(tasks), 'pending': 0, 'running': 0, 'passed': 0, 'failed': 0, 'error': 0}
    for t in tasks:
        key = {'PENDING': 'pending', 'RUNNING': 'running',
               'PASSED': 'passed', 'FAILED': 'failed'}.get(t.get('status'))
        if key:
            stats[key] += 1
        else:
            stats['error'] += 1
    tools = engine.tools_available()
    return jsonify({'ok': True, 'tools': tools, 'stats': stats})


@bp.route('/api/rules')
def api_rules():
    return jsonify({'ok': True, 'rules': rules_mod.DEFAULT_RULES,
                    'ext_types': rules_mod.EXT_TYPES,
                    'type_labels': rules_mod.TYPE_LABELS})


@bp.route('/api/tasks')
def api_tasks():
    return jsonify({'ok': True, 'tasks': store.load_tasks()})


@bp.route('/api/task/<task_id>')
def api_task(task_id):
    t = store.get_task(task_id)
    if t is None:
        return jsonify({'ok': False, 'msg': '任务不存在'}), 404
    return jsonify({'ok': True, 'task': t})


# ---------------------------------------------------------------- 上传
# Content-Type → 扩展名（URL 无扩展名时的次选识别，嗅探优先于它）
_CTYPE_EXT = {
    'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp',
    'audio/mpeg': 'mp3', 'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/mp4': 'm4a',
    'video/mp4': 'mp4', 'video/quicktime': 'mov', 'video/x-matroska': 'mkv',
}

URL_TIMEOUT = 60          # 链接下载超时（秒）
_REJECT_FORMAT = '不支持的格式（仅图片 PNG/JPG/WEBP、音频 MP3/WAV/M4A、视频 MP4/MOV/MKV）'


@bp.route('/api/upload', methods=['POST'])
def api_upload():
    """统一上传入口：multipart files[]（拖拽/本地选择）或 form.sources（链接/路径，JSON 数组）。"""
    files = request.files.getlist('files')
    sources = _parse_sources_arg()
    if not files and not sources:
        return jsonify({'ok': False, 'msg': '未收到任何文件或链接'}), 400
    # 超大 multipart 请求在读入前拒绝（仅对文件通道；Werkzeug 会把大文件落盘暂存，不会占内存）
    if files and request.content_length and \
            request.content_length > (store.MAX_UPLOAD_BYTES + 64 * 1024) * len(files):
        abort(413)

    rules_raw = _parse_rules_arg()
    start = str(request.form.get('start', '')).lower() in ('1', 'true', 'yes')
    created, rejected = [], []

    for f in files:
        name = f.filename or ''
        mtype = rules_mod.media_type_of(name)
        if mtype is None:
            rejected.append({'filename': name, 'reason': _REJECT_FORMAT})
            continue
        task_id = store.new_task_id()
        try:
            stored_path, size = store.save_upload(f, name, task_id)
        except ValueError as e:
            rejected.append({'filename': name, 'reason': str(e)})
            continue
        _register_task(created, task_id, name, stored_path, size, mtype, _ext_of(name),
                       {'kind': 'file'}, rules_raw, start)

    for src in sources:
        _create_from_source(src, rules_raw, start, created, rejected)

    return jsonify({'ok': True, 'created': created, 'rejected': rejected})


def _register_task(created, task_id, filename, stored_path, size, mtype, ext, origin, rules_raw, start):
    """统一任务注册：规则快照 → 落盘 → 可选立即检测"""
    task = {
        'id': task_id,
        'filename': filename,
        'ext': ext,
        'stored_path': stored_path,
        'media_type': mtype,
        'size_bytes': size,
        'status': 'PENDING',
        'rules': rules_mod.sanitize(mtype, rules_raw.get(mtype)),
        'report': None,
        'error': None,
        'origin': origin,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'finished_at': None,
    }
    store.upsert_task(task)
    created.append(task)
    if start:
        _spawn_detect(task_id)


def _parse_sources_arg():
    """form.sources：JSON 数组（链接 / 本地路径混合）；坏输入按空处理（由上层 400 兜底）"""
    raw = request.form.get('sources')
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, str)]


def _create_from_source(src, rules_raw, start, created, rejected):
    """链接（http/https）与本地路径（~ / 绝对 / 相对项目根）的统一入口"""
    src = str(src or '').strip().strip('\'"').strip()
    if not src:
        return
    if '://' in src:
        _create_from_url(src, rules_raw, start, created, rejected)
    else:
        _create_from_path(src, rules_raw, start, created, rejected)


def _create_from_path(src, rules_raw, start, created, rejected):
    absp = os.path.abspath(os.path.expanduser(src))   # 相对路径基于平台进程 CWD = 项目根
    if not os.path.isfile(absp):
        rejected.append({'filename': src, 'reason': '路径不存在或不是文件: %s' % src})
        return
    if os.path.getsize(absp) > store.MAX_UPLOAD_BYTES:
        rejected.append({'filename': src, 'reason': '文件超过单文件上限 %dMB'
                         % (store.MAX_UPLOAD_BYTES // (1024 * 1024))})
        return
    name = os.path.basename(absp)
    mtype = rules_mod.media_type_of(name)
    if mtype is None:
        # 扩展名缺失或白名单外 → 按源文件魔数识别（识别不出再拒，不盲目拷贝）
        sniffed = engine.sniff_ext(absp)
        if sniffed is None:
            rejected.append({'filename': src, 'reason': '无法识别媒体类型（扩展名与文件头均未识别）'})
            return
        mtype = rules_mod.EXT_TYPES[sniffed]
        stem = os.path.splitext(name)[0] or 'media'
        name = '%s.%s' % (stem, sniffed)
    task_id = store.new_task_id()
    try:
        with open(absp, 'rb') as fh:                  # 拷贝副本入 uploads：删除任务不动用户原文件
            stored_path, size = store.save_stream(fh, name, task_id)
    except (OSError, ValueError) as e:
        rejected.append({'filename': src, 'reason': '读取文件失败: %s' % str(e)[:120]})
        return
    _register_task(created, task_id, name, stored_path, size, mtype, _ext_of(name),
                   {'kind': 'path', 'src': src}, rules_raw, start)


def _create_from_url(src, rules_raw, start, created, rejected):
    parsed = urllib.parse.urlparse(src)
    if parsed.scheme not in ('http', 'https'):
        rejected.append({'filename': src, 'reason': '不支持的链接协议（仅 http/https）'})
        return
    base = os.path.basename(urllib.parse.unquote(parsed.path))
    stem, dot_ext = os.path.splitext(base)
    url_ext = dot_ext[1:].lower() if dot_ext else ''
    task_id = store.new_task_id()
    os.makedirs(store.UPLOADS_DIR, exist_ok=True)
    tmp_path = os.path.join(store.UPLOADS_DIR, '%s__%s' % (task_id, store.safe_filename(base) or 'download'))
    size, ctype = 0, ''
    try:
        req = urllib.request.Request(src, headers={'User-Agent': 'media-validator/1.0'})
        with urllib.request.urlopen(req, timeout=URL_TIMEOUT) as resp, open(tmp_path, 'wb') as f:
            ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > store.MAX_UPLOAD_BYTES:
                    raise ValueError('链接文件超过单文件上限 %dMB'
                                     % (store.MAX_UPLOAD_BYTES // (1024 * 1024)))
                f.write(chunk)
    except ValueError as e:
        _silent_remove(tmp_path)
        rejected.append({'filename': src, 'reason': str(e)})
        return
    except Exception as e:
        _silent_remove(tmp_path)
        rejected.append({'filename': src, 'reason': '下载失败: %s' % str(e)[:120]})
        return
    if size == 0:
        _silent_remove(tmp_path)
        rejected.append({'filename': src, 'reason': '下载内容为空'})
        return

    # 类型定案：URL 扩展名（可信时直接用）→ 魔数嗅探 → Content-Type；都认不出才拒
    final_ext = url_ext if url_ext and rules_mod.media_type_of('x.' + url_ext) else None
    display_name = store.safe_filename(base)
    if final_ext is None:
        final_ext = engine.sniff_ext(tmp_path) or _CTYPE_EXT.get(ctype)
        if final_ext is None:
            _silent_remove(tmp_path)
            rejected.append({'filename': src, 'reason': '无法识别媒体类型（URL 无扩展名且内容嗅探失败）'})
            return
        display_name = '%s.%s' % (stem or 'download', final_ext)
        fixed_path = os.path.join(store.UPLOADS_DIR, '%s__%s' % (task_id, store.safe_filename(display_name)))
        os.rename(tmp_path, fixed_path)
        tmp_path = fixed_path
    mtype = rules_mod.EXT_TYPES[final_ext]
    _register_task(created, task_id, display_name, tmp_path, size, mtype, final_ext,
                   {'kind': 'url', 'src': src}, rules_raw, start)


def _silent_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _parse_rules_arg():
    """表单里的 rules 字段：JSON {media_type: {...}}；坏输入静默回退默认值"""
    raw = request.form.get('rules')
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------- 检测
@bp.route('/api/detect', methods=['POST'])
def api_detect():
    body = request.get_json(silent=True) or {}
    ids = body.get('ids') or []
    if not isinstance(ids, list):
        return jsonify({'ok': False, 'msg': 'ids 应为数组'}), 400
    rules_raw = body.get('rules') if isinstance(body.get('rules'), dict) else {}
    started, unknown = [], []
    for tid in ids:
        t = store.get_task(tid)
        if t is None:
            unknown.append(tid)
            continue
        if rules_raw.get(t['media_type']):
            t['rules'] = rules_mod.sanitize(t['media_type'], rules_raw[t['media_type']])
            store.upsert_task(t)
        _spawn_detect(tid)
        started.append(tid)
    return jsonify({'ok': True, 'started': started, 'unknown': unknown})


@bp.route('/api/task/<task_id>/detect', methods=['POST'])
def api_detect_one(task_id):
    t = store.get_task(task_id)
    if t is None:
        return jsonify({'ok': False, 'msg': '任务不存在'}), 404
    body = request.get_json(silent=True) or {}
    raw = body.get('rules')
    if isinstance(raw, dict) and raw:
        # 兼容两种形态：{媒体类型: {规则}}（与批量接口一致）或该任务类型的扁平 {规则}
        inner = raw.get(t['media_type'])
        t['rules'] = rules_mod.sanitize(t['media_type'], inner if isinstance(inner, dict) else raw)
        store.upsert_task(t)
    if not _spawn_detect(task_id):
        return jsonify({'ok': False, 'msg': '该任务正在检测中'}), 409
    return jsonify({'ok': True})


def _spawn_detect(task_id):
    """起后台检测线程；同任务并发提交返回 False。

    任务快照与 tasks.json 路径在请求上下文内一次性取定传给线程——
    线程生命期长于请求，落盘一律走显式路径（store.upsert_task_into），
    不依赖可能被并发改动的模块级全局，杜绝任务写错存储。
    """
    with _detect_lock:
        if task_id in _detecting:
            return False
        _detecting.add(task_id)
    task = store.get_task(task_id)
    if task is None:
        with _detect_lock:
            _detecting.discard(task_id)
        return False
    th = threading.Thread(target=_run_detect, args=(task, store.TASKS_FILE), daemon=True)
    th.start()
    return True


def _run_detect(task, tasks_file):
    """线程体：RUNNING → PASSED/FAILED/ERROR，任何异常兜底成 ERROR 而非拖垮线程"""
    task['status'], task['error'], task['report'] = 'RUNNING', None, None
    task['started_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    store.upsert_task_into(tasks_file, task)
    try:
        report = engine.detect(task['stored_path'], task['media_type'], task['rules'],
                               size_bytes=task.get('size_bytes'), ext=task.get('ext') or '')
        task['report'] = report
        task['status'] = 'PASSED' if report['passed'] else 'FAILED'
    except engine.EngineError as e:
        task['status'], task['error'] = 'ERROR', str(e)
    except Exception as e:                      # 引擎意外异常也归为 ERROR，不让线程无声死亡
        task['status'], task['error'] = 'ERROR', '检测执行异常: %s' % e
    finally:
        task['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        store.upsert_task_into(tasks_file, task)
        with _detect_lock:
            _detecting.discard(task['id'])


def _ext_of(filename):
    parts = (filename or '').rsplit('.', 1)
    return parts[1].lower() if len(parts) == 2 else ''


# ---------------------------------------------------------------- 删除
@bp.route('/api/task/<task_id>', methods=['DELETE'])
def api_delete(task_id):
    victim = store.delete_task(task_id)
    if victim is None:
        return jsonify({'ok': False, 'msg': '任务不存在'}), 404
    return jsonify({'ok': True})
