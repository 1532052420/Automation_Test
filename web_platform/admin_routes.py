# -*- coding: utf-8 -*-
"""Web 执行平台 · 管理后台（用例 / 页面对象 / 元素 上传与文件管理 · 方案A）

功能：统一文件列表（类型/上传人/受保护标记）、上传（py_compile/yaml/json 校验、
覆盖确认与历史备份）、下载（单个/批量zip）、重命名、新建文件夹、删除（受保护拦截）、
批量删除。文件元数据（上传人/备份记录）存储于 output/admin_meta.json，
二期账号体系落地后可平移到 file_manage 数据表。

安全约定：
- 上传仅限 .py/.yaml/.json，上传前 py_compile 或 yaml/json 解析校验（错误带行号）
- 目标路径严格限制在 cases/ 与 page_objects 指定目录内，杜绝路径穿越
- 受保护文件（框架公共文件，如 conftest.py）删除/重命名需管理员权限
  （本机模式即管理员；启用 ADMIN_TOKEN 后需请求头 X-Admin-Token 匹配）
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile

from flask import Blueprint, jsonify, render_template, request, send_file

from web_platform.runtime_config import BASE_DIR

bp = Blueprint('admin', __name__)

ROOT = BASE_DIR  # 项目根（可读性别名）
MAX_UPLOAD_BYTES = 200 * 1024
META_PATH = os.environ.get('ADMIN_META_PATH') or os.path.join(
    BASE_DIR, 'output', 'admin_meta.json')

_UPLOAD_TARGETS = {
    'cases': os.path.join(BASE_DIR, 'cases'),
    'elements': os.path.join(BASE_DIR, 'page_objects', 'app_ui', 'android', 'demoProject', 'elements'),
    'pages': os.path.join(BASE_DIR, 'page_objects', 'app_ui', 'android', 'demoProject', 'pages'),
}
# 统一列表的类型定义：code -> (显示名, 目录, 文件名规范)
TYPE_DEFS = {
    'case': {'label': '测试用例', 'base': _UPLOAD_TARGETS['cases'], 'base_kind': 'cases',
             'name_re': re.compile(r'^test_[A-Za-z0-9_]+\.py$')},
    'framework': {'label': '框架公共文件', 'base': _UPLOAD_TARGETS['cases'], 'base_kind': 'cases',
                  'name_re': re.compile(r'^(?!test_)[A-Za-z_][A-Za-z0-9_]*\.py$')},
    'page': {'label': '页面对象', 'base': _UPLOAD_TARGETS['pages'], 'base_kind': 'pages',
             'name_re': re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\.py$')},
    'element': {'label': '元素定位', 'base': _UPLOAD_TARGETS['elements'], 'base_kind': 'elements',
                'name_re': re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\.(py|yaml|json)$')},
}
PROTECTED_TYPES = {'framework'}  # 受保护：删除/重命名仅管理员
TYPE_LABELS = {k: v['label'] for k, v in TYPE_DEFS.items()}
_NAME_RULES = {
    'cases': r'^test_[A-Za-z0-9_]+\.py$',
    'pages': r'^[A-Za-z_][A-Za-z0-9_]*\.py$',
    'elements': r'^[A-Za-z_][A-Za-z0-9_]*\.(py|yaml|json)$',
}


class AdminError(Exception):
    pass


# ---------------- 元数据（上传人/备份记录），二期平移 file_manage 表 ----------------
def _load_meta():
    if not os.path.isfile(META_PATH):
        return {}
    try:
        with open(META_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_meta(meta):
    os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
    with open(META_PATH, 'w', encoding='utf-8') as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=1))


def _meta_of(meta, full_rel):
    return meta.get(full_rel, {})


def _protected_allowed(force_admin=False):
    """受保护文件（框架公共文件）操作权限：默认拒绝，防止误删框架。
    放行条件：口令模式下管理员令牌匹配；或本机模式下显式 force_admin=true
    （操作者明确知道自己在动框架文件）。"""
    token = os.environ.get('ADMIN_TOKEN', '').strip()
    if token:
        return request.headers.get('X-Admin-Token', '') == token
    return bool(force_admin)


def _check_token():
    """返回鉴权状态字符串：'off'（本机模式）/ 'on'（口令校验通过）"""
    token = os.environ.get('ADMIN_TOKEN', '').strip()
    if not token:
        return 'off'
    if request.headers.get('X-Admin-Token', '') != token:
        raise AdminError('访问口令不正确（管理后台已启用口令保护）')
    return 'on'


def _classify(rel_to_base, base_kind):
    """按目录归属与文件名判定类型；cases 下非 test_ 前缀的 py 为受保护框架文件"""
    filename = os.path.basename(rel_to_base)
    if base_kind == 'cases':
        code = 'case' if filename.startswith('test_') else 'framework'
        return code, code in PROTECTED_TYPES
    if base_kind == 'pages':
        return 'page', False
    return 'element', False


def _resolve_managed_path(full_rel):
    """把相对项目根的路径解析到受管目录之一，返回 (abs_path, base_kind, rel_to_base)"""
    rel = (full_rel or '').strip().replace('\\', '/')
    if not rel or '..' in rel or rel.startswith('/'):
        raise AdminError('路径不合法: %r' % full_rel)
    for kind, base in _UPLOAD_TARGETS.items():
        norm_base = os.path.normpath(base)
        abs_path = os.path.normpath(os.path.join(ROOT, rel))
        if abs_path == norm_base or abs_path.startswith(norm_base + os.sep):
            return abs_path, kind, os.path.relpath(abs_path, norm_base).replace(os.sep, '/')
    raise AdminError('路径不在受管目录内: %s' % rel)


def _validate_name(kind, filename):
    if kind not in _NAME_RULES:
        raise AdminError('未知的上传类型: %s' % kind)
    if not re.match(_NAME_RULES[kind], filename):
        raise AdminError('文件名不符合规范: %s（要求 %s）' % (filename, _NAME_RULES[kind]))


def _syntax_check(abs_path, ext=None):
    """按后缀校验（临时文件需显式传原始后缀）；py 错误提取行号，yaml/json 错误提取位置"""
    ext = (ext or os.path.splitext(abs_path)[1]).lower()
    if ext == '.py':
        r = subprocess.run([sys.executable, '-m', 'py_compile', abs_path],
                           capture_output=True, timeout=30, cwd=ROOT)
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', 'ignore')
            m = re.search(r'line (\d+)', err)
            line = ('第 %s 行' % m.group(1)) if m else ''
            detail = err.strip().splitlines()[-1][:200] if err.strip() else ''
            raise AdminError('py 语法错误%s: %s' % (line, detail))
    elif ext == '.yaml':
        import yaml
        try:
            with open(abs_path, encoding='utf-8') as f:
                yaml.safe_load(f)
        except yaml.YAMLError as e:
            mark = getattr(getattr(e, 'problem_mark', None), 'line', None)
            where = ('第 %d 行' % (mark + 1)) if mark is not None else ''
            raise AdminError('yaml 格式错误%s: %s' % (where, str(e).splitlines()[0][:200]))
    elif ext == '.json':
        try:
            with open(abs_path, encoding='utf-8') as f:
                json.load(f)
        except json.JSONDecodeError as e:
            raise AdminError('json 格式错误第 %d 行: %s' % (e.lineno, e.msg))
    else:
        raise AdminError('不支持的文件后缀: %s' % ext)


# ---------------- 受管文件写入（单文件上传与用例包入库共用同一套校验/备份/登记） ----------------
def _rm_quiet(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _target_dir(kind, subdir):
    """受管子目录内的目标目录；越界返回 (None, 错误信息)"""
    sub = (subdir or '').strip().strip('/')
    if sub and (not re.match(r'^[A-Za-z0-9_/-]+$', sub) or '..' in sub):
        return None, '子目录不合法: %r' % subdir
    target_dir = os.path.normpath(os.path.join(_UPLOAD_TARGETS[kind], sub))
    norm_base = os.path.normpath(_UPLOAD_TARGETS[kind])
    if target_dir != norm_base and not target_dir.startswith(norm_base + os.sep):
        return None, '目标路径越界'
    return target_dir, None


def _stage_file(target, content, ext):
    """写 .uploading 临时文件并做语法校验；失败抛 AdminError（临时文件已清理）。
    只动临时文件、不碰原文件 —— 便于多文件先整体校验、再统一落盘。"""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + '.uploading'
    with open(tmp, 'wb') as fh:
        fh.write(content)
    try:
        _syntax_check(tmp, ext)
    except AdminError:
        _rm_quiet(tmp)
        raise
    return tmp


def _commit_file(target, tmp, meta, full_rel, uploader):
    """暂存文件落盘：覆盖前备份历史版本，登记上传人与时间。返回是否发生了备份"""
    m = meta.setdefault(full_rel, {})
    backed = os.path.isfile(target)
    if backed:
        stem, ext = os.path.splitext(target)
        backup_name = '%s_%s_backup%s' % (stem, time.strftime('%Y%m%d_%H%M%S'), ext)
        os.replace(target, backup_name)
        m.setdefault('backups', []).append(os.path.basename(backup_name))
        m['backups'] = m['backups'][-20:]
    m['uploader'] = uploader
    m['uploaded_at'] = int(time.time())
    os.replace(tmp, target)
    return backed


def write_managed_file(kind, filename, content, subdir='', force=False,
                       uploader='admin', force_admin=False, meta=None):
    """单文件入库：校验名与目录 → 暂存+语法校验 → 落盘（覆盖前备份、登记元数据）。
    返回 (payload, status)；status=409 表示同名文件已存在且未允许覆盖（供前端弹确认框）。"""
    meta = {} if meta is None else meta
    try:
        _validate_name(kind, filename)
    except AdminError as e:
        # cases 下非 test_ 前缀的 py = 框架公共文件，仅管理员可上传（4.4）
        if kind == 'cases' and re.match(r'^(?!test_)[A-Za-z_][A-Za-z0-9_]*\.py$', filename):
            if not _protected_allowed(force_admin):
                return {'ok': False,
                        'msg': '框架公共文件（非 test_ 前缀 py）仅管理员可上传，'
                               '请携带管理员凭据（force_admin=true 或管理员令牌）'}, 403
        else:
            return {'ok': False, 'msg': str(e)}, 400
    target_dir, err = _target_dir(kind, subdir)
    if err:
        return {'ok': False, 'msg': err}, 400
    content = content.encode('utf-8') if isinstance(content, str) else content
    if len(content) > MAX_UPLOAD_BYTES:
        return {'ok': False, 'msg': '文件过大（限 200KB）'}, 400
    target = os.path.join(target_dir, filename)
    full_rel = os.path.relpath(target, ROOT).replace(os.sep, '/')
    exists = os.path.isfile(target)
    if exists and not force:
        m = _meta_of(meta, full_rel)
        st = os.stat(target)
        # 未勾选覆盖：返回已存在文件的元信息，供前端弹确认框（覆盖交互 3.3）
        return {'ok': False, 'exists': True,
                'meta': {'uploader': m.get('uploader', '框架'),
                         'uploaded_at': m.get('uploaded_at', int(st.st_mtime)),
                         'modify_time': int(st.st_mtime)}}, 409
    try:
        tmp = _stage_file(target, content, os.path.splitext(filename)[1])
    except AdminError as e:
        return {'ok': False, 'msg': str(e)}, 400
    backed = _commit_file(target, tmp, meta, full_rel, uploader)
    return {'ok': True, 'path': full_rel, 'filename': filename, 'backed_up': backed,
            'msg': ('已覆盖上传 %s（旧文件已自动备份）' if backed else '已上传 %s') % filename
                   + '，平台已自动识别'}, 200


# ---------------- 用例包（元素定位器三件套）整体入库 ----------------
MAX_PACKAGE_BYTES = MAX_UPLOAD_BYTES * 3


def import_case_package(package='', files=None, uploader='admin'):
    """用例包整体入库：files = [{'dir': 相对项目根的目录, 'name': ..., 'content': ...}]
    例如 dir='cases/app_ui/android/demoProject'、'page_objects/app_ui/android/demoProject/pages'。
    目录必须落在受管目录内（_resolve_managed_path 校验，杜绝路径穿越）。

    两阶段执行：先把全部文件写成 .uploading 并逐个语法校验，全部通过后才统一落盘 ——
    三件套必须整体成功，避免留下「用例已入库但页面文件语法错」的半成品。
    同名文件自动备份历史版本（与单文件上传同一套逻辑）。"""
    items = [f for f in (files or []) if isinstance(f, dict)]
    if not items:
        return {'ok': False, 'msg': '用例包为空'}, 400
    meta, staged, errors = _load_meta(), [], []
    for f in items:
        subdir = (f.get('dir') or '').strip().strip('/')
        name = os.path.basename((f.get('name') or '').strip())
        content = f.get('content')
        where = '%s/%s' % (subdir or '?', name or '?')
        if not subdir or not name or not isinstance(content, str):
            errors.append('%s: 结构不合法（dir 为相对项目根的目录，'
                          '如 cases/app_ui/android/demoProject）' % where)
            continue
        try:
            target, kind, _ = _resolve_managed_path('%s/%s' % (subdir, name))
        except AdminError as e:
            errors.append('%s: %s' % (where, e))
            continue
        try:
            _validate_name(kind, name)
        except AdminError as e:
            errors.append('%s: %s' % (where, e))
            continue
        raw = content.encode('utf-8')
        if len(raw) > MAX_UPLOAD_BYTES:
            errors.append('%s: 文件过大（限 200KB）' % where)
            continue
        try:
            staged.append((kind, name, target,
                           _stage_file(target, raw, os.path.splitext(name)[1])))
        except AdminError as e:
            errors.append('%s: %s' % (where, e))
    if errors:
        for _, _, _, tmp in staged:
            _rm_quiet(tmp)
        return {'ok': False, 'errors': errors,
                'msg': '用例包校验未通过，未写入任何文件：' + '；'.join(errors)}, 400
    done = []
    for kind, name, target, tmp in staged:
        full_rel = os.path.relpath(target, ROOT).replace(os.sep, '/')
        backed = _commit_file(target, tmp, meta, full_rel, uploader)
        done.append({'dir': os.path.dirname(full_rel), 'name': name,
                     'path': full_rel, 'backed_up': backed})
    _save_meta(meta)
    return {'ok': True, 'package': package, 'files': done, 'total': len(done),
            'backed_up': sum(1 for d in done if d['backed_up']),
            'msg': '用例包「%s」已入库 %d 个文件（%s），平台已自动识别'
                   % (package or '未命名', len(done),
                      '、'.join(d['path'] for d in done))}, 200


def _read_package_zip(zf):
    """读用例包 zip → files 列表；结构非法返回错误字符串。
    只收录落在受管目录（cases/ 及 page_objects 的 pages/elements）内的文件，
    其余（__MACOSX、说明书等）一律忽略；目录层级不限，与「下载用例包」产出对齐。"""
    files, total = [], 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = info.filename.replace('\\', '/').lstrip('/')
        try:
            _resolve_managed_path(rel)
        except AdminError:
            continue
        total += info.file_size
        if total > MAX_PACKAGE_BYTES:
            return '用例包过大（限 %dKB）' % (MAX_PACKAGE_BYTES // 1024)
        files.append({'dir': os.path.dirname(rel), 'name': os.path.basename(rel),
                      'content': zf.read(info).decode('utf-8', 'replace')})
    return files or 'zip 内未找到受管目录（cases/ 或 page_objects 的 pages/elements）内的文件'


@bp.route('/admin')
def page_admin():
    return render_template('admin.html')


@bp.route('/api/admin/files')
def api_admin_files():
    """统一文件列表：跨 cases/pages/elements 三个受管目录，含类型/上传人/受保护标记"""
    try:
        auth = _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    type_filter = request.args.get('type', '')
    meta = _load_meta()
    now = int(time.time())
    files, seen = [], set()
    for type_code, conf in TYPE_DEFS.items():
        base = conf['base']
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != '__pycache__' and not d.startswith('.')]
            for fn in sorted(filenames):
                if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*\.(py|yaml|json)$', fn):
                    continue
                full = os.path.join(dirpath, fn)
                rel_to_base = os.path.relpath(full, base).replace(os.sep, '/')
                full_rel = os.path.relpath(full, ROOT).replace(os.sep, '/')
                if full_rel in seen:
                    continue
                seen.add(full_rel)
                code, protected = _classify(rel_to_base, conf['base_kind'])
                st = os.stat(full)
                m = _meta_of(meta, full_rel)
                files.append({
                    'path': full_rel,
                    'file_type': code,
                    'type_label': TYPE_LABELS[code],
                    'is_protected': protected,
                    'size': st.st_size,
                    'mtime': int(st.st_mtime),
                    'uploader': m.get('uploader', '框架'),
                    'uploaded_at': m.get('uploaded_at', now),
                    'backups': m.get('backups', []),
                })
    if type_filter:
        files = [f for f in files if f['file_type'] == type_filter]
    files.sort(key=lambda x: x['path'])
    return jsonify({'ok': True, 'auth': auth, 'files': files})


@bp.route('/api/admin/upload', methods=['POST'])
def api_admin_upload():
    try:
        auth = _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({'ok': False, 'msg': '未选择文件'}), 400
    meta = _load_meta()
    payload, status = write_managed_file(
        request.form.get('kind', ''), os.path.basename(f.filename), f.read(),
        subdir=request.form.get('subdir', ''),
        force=request.form.get('force') == 'true',
        uploader=(request.form.get('uploader') or 'admin').strip()[:32],
        force_admin=request.form.get('force_admin') == 'true',
        meta=meta)
    if status == 200:
        _save_meta(meta)
        payload['auth'] = auth
    return jsonify(payload), status


@bp.route('/api/admin/upload_zip_content', methods=['POST'])
def api_admin_upload_zip_content():
    """用例包入库（JSON 形式）：{package, uploader, files:[{dir,name,content}]}。
    元素定位器「💾 保存到框架」与平台同进程，直接调用 import_case_package，
    不再依赖任何外部端口。"""
    try:
        auth = _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    data = request.get_json(silent=True) or {}
    payload, status = import_case_package(
        (data.get('package') or '').strip(), data.get('files'),
        (data.get('uploader') or 'locator').strip()[:32])
    payload['auth'] = auth
    return jsonify(payload), status


@bp.route('/api/admin/upload_package', methods=['POST'])
def api_admin_upload_package():
    """用例包入库（multipart 上传 .zip）：管理后台「📦 上传用例包」入口。
    zip 内一级目录须为 cases/ pages/ elements/（与定位器「⬇ 下载用例包」产出一致）。"""
    try:
        auth = _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({'ok': False, 'msg': '未选择文件'}), 400
    try:
        zf = zipfile.ZipFile(io.BytesIO(f.read()))
    except zipfile.BadZipFile:
        return jsonify({'ok': False, 'msg': '不是合法的 zip 文件'}), 400
    files = _read_package_zip(zf)
    if isinstance(files, str):
        return jsonify({'ok': False, 'msg': files}), 400
    payload, status = import_case_package(
        os.path.splitext(os.path.basename(f.filename))[0], files,
        (request.form.get('uploader') or 'admin').strip()[:32])
    payload['auth'] = auth
    return jsonify(payload), status


@bp.route('/api/admin/download')
def api_admin_download():
    try:
        _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    try:
        abs_path, _, _ = _resolve_managed_path(request.args.get('path', ''))
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 400
    if not os.path.isfile(abs_path):
        return jsonify({'ok': False, 'msg': '文件不存在'}), 404
    return send_file(abs_path, as_attachment=True)


@bp.route('/api/admin/download_batch')
def api_admin_download_batch():
    try:
        _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    paths = (request.args.get('paths') or '').split(',')
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel in paths:
            try:
                abs_path, _, rel_to_base = _resolve_managed_path(rel)
            except AdminError:
                continue
            if os.path.isfile(abs_path):
                zf.write(abs_path, rel_to_base)
                count += 1
    if not count:
        return jsonify({'ok': False, 'msg': '没有可下载的文件'}), 404
    buf.seek(0)
    # Flask 1.x 用 attachment_filename（download_name 是 2.0+ 参数）
    return send_file(buf, as_attachment=True, mimetype='application/zip',
                     attachment_filename='files_%s.zip' % time.strftime('%Y%m%d_%H%M%S'))


@bp.route('/api/admin/rename', methods=['POST'])
def api_admin_rename():
    try:
        _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    body = request.get_json(force=True, silent=True) or {}
    try:
        abs_path, kind, rel_to_base = _resolve_managed_path(body.get('path', ''))
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 400
    _, protected = _classify(rel_to_base, kind)
    if protected and not _protected_allowed(bool(body.get('force_admin'))):
        return jsonify({'ok': False, 'msg': '框架公共文件，仅管理员可操作'}), 403
    new_name = os.path.basename(body.get('new_name') or '')
    try:
        _validate_name(kind, new_name)
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 400
    new_path = os.path.join(os.path.dirname(abs_path), new_name)
    if os.path.isfile(new_path):
        return jsonify({'ok': False, 'msg': '目标文件名已存在: %s' % new_name}), 409
    old_rel = os.path.relpath(abs_path, ROOT).replace(os.sep, '/')
    os.rename(abs_path, new_path)
    meta = _load_meta()
    if old_rel in meta:
        meta[os.path.relpath(new_path, ROOT).replace(os.sep, '/')] = meta.pop(old_rel)
        _save_meta(meta)
    return jsonify({'ok': True, 'msg': '已重命名为 %s' % new_name})


@bp.route('/api/admin/folder', methods=['POST'])
def api_admin_folder():
    try:
        _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    body = request.get_json(force=True, silent=True) or {}
    kind = body.get('kind', '')
    subdir = (body.get('subdir') or '').strip().strip('/')
    if kind not in _NAME_RULES:
        return jsonify({'ok': False, 'msg': '未知类型'}), 400
    if not subdir or not re.match(r'^[A-Za-z0-9_/-]+$', subdir) or '..' in subdir:
        return jsonify({'ok': False, 'msg': '目录名不合法（字母/数字/_/-，可含子层级）'}), 400
    target_dir = os.path.normpath(os.path.join(_UPLOAD_TARGETS[kind], subdir))
    norm_base = os.path.normpath(_UPLOAD_TARGETS[kind])
    if target_dir != norm_base and not target_dir.startswith(norm_base + os.sep):
        return jsonify({'ok': False, 'msg': '目标路径越界'}), 400
    if os.path.isdir(target_dir):
        return jsonify({'ok': False, 'msg': '目录已存在: %s' % subdir}), 409
    os.makedirs(target_dir, exist_ok=True)
    return jsonify({'ok': True, 'msg': '已创建目录 %s' % subdir})


@bp.route('/api/admin/batch_delete', methods=['POST'])
def api_admin_batch_delete():
    try:
        _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    body = request.get_json(force=True, silent=True) or {}
    paths = body.get('paths') or []
    force_admin = bool(body.get('force_admin'))
    if not paths:
        return jsonify({'ok': False, 'msg': '未选择文件'}), 400
    meta = _load_meta()
    deleted, denied, missing = [], [], []
    for rel in paths:
        try:
            abs_path, kind, rel_to_base = _resolve_managed_path(rel)
        except AdminError:
            missing.append(rel)
            continue
        _, protected = _classify(rel_to_base, kind)
        if protected and not _protected_allowed(force_admin):
            denied.append(rel)
            continue
        if not os.path.isfile(abs_path):
            missing.append(rel)
            continue
        os.remove(abs_path)
        meta.pop(os.path.relpath(abs_path, ROOT).replace(os.sep, '/'), None)
        deleted.append(rel)
    _save_meta(meta)
    msg_parts = ['已删除 %d 个' % len(deleted)]
    if denied:
        msg_parts.append('受保护跳过 %d 个（框架公共文件仅管理员可操作）' % len(denied))
    if missing:
        msg_parts.append('不存在 %d 个' % len(missing))
    return jsonify({'ok': True, 'deleted': deleted, 'denied': denied, 'missing': missing,
                    'msg': '；'.join(msg_parts)})


@bp.route('/api/admin/file', methods=['DELETE'])
def api_admin_delete():
    """单文件删除；受保护文件（框架公共文件）仅管理员可操作"""
    try:
        _check_token()
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 401
    try:
        abs_path, kind, rel_to_base = _resolve_managed_path(request.args.get('path', ''))
    except AdminError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 400
    _, protected = _classify(rel_to_base, kind)
    if protected and not _protected_allowed(request.args.get('force_admin') == 'true'):
        return jsonify({'ok': False, 'msg': '框架公共文件，仅管理员可操作'}), 403
    if not os.path.isfile(abs_path):
        return jsonify({'ok': False, 'msg': '文件不存在'}), 404
    os.remove(abs_path)
    meta = _load_meta()
    meta.pop(os.path.relpath(abs_path, ROOT).replace(os.sep, '/'), None)
    _save_meta(meta)
    return jsonify({'ok': True, 'msg': '已删除 %s' % rel_to_base})
