# -*- coding: utf-8 -*-
"""媒体产物检测 · 路由（独立模块，不依赖框架任何代码）

页面 + API 一张蓝图：
    GET    /media-validator/                    检测页
    GET    /media-validator/api/overview        工具可用性 + 统计
    GET    /media-validator/api/rules           三类默认规则（前端渲染表单用）
    POST   /media-validator/api/upload          上传（多文件）→ 建任务；可带规则并立即检测
    POST   /media-validator/api/detect          批量开始检测 {ids: [...]}
    GET    /media-validator/api/tasks           任务列表（含报告）
    GET    /media-validator/api/task/<id>       单任务（轮询）
    POST   /media-validator/api/task/<id>/detect  重新检测（可带规则）
    DELETE /media-validator/api/task/<id>       删除任务与文件

检测在后台线程执行（ffmpeg 全量解码耗时不可控），前端轮询任务状态。
状态机：PENDING → RUNNING → PASSED / FAILED / ERROR（ERROR 仅指基础设施故障）。
"""
import json
import threading
import time

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
@bp.route('/api/upload', methods=['POST'])
def api_upload():
    files = request.files.getlist('files')
    if not files:
        return jsonify({'ok': False, 'msg': '未收到任何文件'}), 400
    # 超大请求在读入前拒绝（Content-Length 预检；Werkzeug 本身会把大文件落盘暂存，不会占内存）
    if request.content_length and request.content_length > (store.MAX_UPLOAD_BYTES + 64 * 1024) * len(files):
        abort(413)

    rules_raw = _parse_rules_arg()
    start = str(request.form.get('start', '')).lower() in ('1', 'true', 'yes')

    created, rejected = [], []
    for f in files:
        name = f.filename or ''
        mtype = rules_mod.media_type_of(name)
        if mtype is None:
            rejected.append({'filename': name, 'reason': '不支持的格式（仅图片 PNG/JPG/WEBP、音频 MP3/WAV/M4A、视频 MP4/MOV/MKV）'})
            continue
        task_id = store.new_task_id()
        try:
            stored_path, size = store.save_upload(f, name, task_id)
        except ValueError as e:
            rejected.append({'filename': name, 'reason': str(e)})
            continue
        task = {
            'id': task_id,
            'filename': name,
            'ext': _ext_of(name),
            'stored_path': stored_path,
            'media_type': mtype,
            'size_bytes': size,
            'status': 'PENDING',
            'rules': rules_mod.sanitize(mtype, rules_raw.get(mtype)),
            'report': None,
            'error': None,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'finished_at': None,
        }
        store.upsert_task(task)
        created.append(task)
        if start:
            _spawn_detect(task_id)

    return jsonify({'ok': True, 'created': created, 'rejected': rejected})


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
    if isinstance(body.get('rules'), dict) and body['rules']:
        t['rules'] = rules_mod.sanitize(t['media_type'], body['rules'])
        store.upsert_task(t)
    if not _spawn_detect(task_id):
        return jsonify({'ok': False, 'msg': '该任务正在检测中'}), 409
    return jsonify({'ok': True})


def _spawn_detect(task_id):
    """起后台检测线程；同任务并发提交返回 False"""
    with _detect_lock:
        if task_id in _detecting:
            return False
        _detecting.add(task_id)
    th = threading.Thread(target=_run_detect, args=(task_id,), daemon=True)
    th.start()
    return True


def _run_detect(task_id):
    """线程体：RUNNING → PASSED/FAILED/ERROR，任何异常兜底成 ERROR 而非拖垮线程"""
    t = store.get_task(task_id)
    if t is None:
        return
    t['status'], t['error'], t['report'] = 'RUNNING', None, None
    t['started_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    store.upsert_task(t)
    try:
        report = engine.detect(t['stored_path'], t['media_type'], t['rules'],
                               size_bytes=t.get('size_bytes'), ext=t.get('ext') or '')
        t['report'] = report
        t['status'] = 'PASSED' if report['passed'] else 'FAILED'
    except engine.EngineError as e:
        t['status'], t['error'] = 'ERROR', str(e)
    except Exception as e:                      # 引擎意外异常也归为 ERROR，不让线程无声死亡
        t['status'], t['error'] = 'ERROR', '检测执行异常: %s' % e
    finally:
        t['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        store.upsert_task(t)
        with _detect_lock:
            _detecting.discard(task_id)


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
