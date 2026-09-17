# -*- coding: utf-8 -*-
"""接口测试 · REST 路由（移植 testhub apps/api_testing 的 ViewSet 端点）

端点与 testhub 一一对应（DRF router → Flask blueprint）：
  projects / collections / requests / environments / histories /
  test-suites / test-executions / scheduled-tasks / task-execution-logs /
  dashboard / 通知设置（原 TaskNotificationSetting 简化为全局设置）
另内置 /api-testing/mock/* 回显服务，作为自测/demo 的被测目标（离线可用）。
字段名与 testhub 模型保持同名，持久化走 YAML 存储层。
"""
import time

from flask import Blueprint, jsonify, request

from web_platform.api_testing import yaml_store as store
from web_platform.api_testing import executor, scheduler

bp = Blueprint('api_testing', __name__, url_prefix='/api-testing')

HTTP_METHODS = ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS')
ASSERTION_TYPES = ('status_code', 'response_time', 'contains', 'json_path', 'header', 'equals')


def _body():
    return request.get_json(force=True, silent=True) or {}


def _ok(data=None, msg=''):
    return jsonify({'ok': True, 'data': data, 'msg': msg})


def _bad(msg, code=400):
    return jsonify({'ok': False, 'msg': msg}), code


def _clean(s, limit=200):
    return (str(s or '').strip())[:limit]


def _page(items, args):
    """与 DRF 页码分页语义对齐：?page=&page_size=，默认 1/20"""
    try:
        page = max(1, int(args.get('page', 1)))
        size = min(200, max(1, int(args.get('page_size', 20))))
    except (TypeError, ValueError):
        page, size = 1, 20
    total = len(items)
    start = (page - 1) * size
    return {'count': total, 'page': page, 'page_size': size,
            'results': items[start:start + size]}


# ---------------- 仪表盘 ----------------
@bp.route('/api/dashboard')
def dashboard():
    """统计概览（对应 testhub ApiDashboardViewSet 的核心统计）"""
    reqs = store.requests.list()
    hist = store.histories.list()
    ok_hist = [h for h in hist if h.get('status_code') and not h.get('error_message')]
    execs = store.executions.list()
    return _ok({
        'projects': len(store.projects.list()),
        'requests': len(reqs),
        'suites': len(store.suites.list()),
        'environments': len(store.environments.list()),
        'tasks_active': len(store.tasks.list(status='ACTIVE')),
        'executions': len(execs),
        'request_total': len(hist),
        'success_rate': (round(len(ok_hist) * 100.0 / len(hist), 1) if hist else None),
        'recent_executions': sorted(execs, key=lambda x: -x['id'])[:8],
        'recent_histories': sorted(hist, key=lambda x: -x['id'])[:8],
    })


# ---------------- 项目 ----------------
@bp.route('/api/projects', methods=['GET', 'POST'])
def projects():
    if request.method == 'GET':
        return _ok(store.projects.list())
    d = _body()
    name = _clean(d.get('name'))
    if not name:
        return _bad('项目名称不能为空')
    item = store.projects.create({
        'name': name, 'description': _clean(d.get('description'), 500),
        'project_type': _clean(d.get('project_type') or 'HTTP'),
        'status': _clean(d.get('status') or 'NOT_STARTED'),
        'owner': _clean(d.get('owner') or 'platform', 40),
    })
    return _ok(item)


@bp.route('/api/projects/<int:pid>', methods=['PUT', 'DELETE'])
def project_detail(pid):
    if request.method == 'DELETE':
        # 级联清理：集合/请求/环境/套件/执行（testhub 是 DB 级联，这里手工保证）
        cols = [c['id'] for c in store.collections.list(project_id=pid)]
        for r in store.requests.list(project_id=pid):
            store.histories.replace_all([h for h in store.histories.list()
                                         if h.get('request_id') != r['id']])
            store.requests.delete(r['id'])
        for c in cols:
            store.collections.delete(c)
        for e in store.environments.list(project_id=pid):
            store.environments.delete(e['id'])
        for s in store.suites.list(project_id=pid):
            store.executions.replace_all([x for x in store.executions.list()
                                          if x.get('suite_id') != s['id']])
            store.suites.delete(s['id'])
        for t in store.tasks.list():
            if t.get('suite_id') and store.suites.get(t['suite_id']) is None:
                store.tasks.delete(t['id'])
        store.projects.delete(pid)
        return _ok(msg='项目及关联数据已删除')
    item = store.projects.update(pid, _body())
    return _ok(item) if item else _bad('项目不存在', 404)


# ---------------- 集合 ----------------
@bp.route('/api/collections', methods=['GET', 'POST'])
def collections():
    if request.method == 'GET':
        pid = request.args.get('project')
        items = store.collections.list(project_id=int(pid)) if pid else store.collections.list()
        return _ok(items)
    d = _body()
    name = _clean(d.get('name'))
    if not name:
        return _bad('集合名称不能为空')
    if not store.projects.get(d.get('project_id')):
        return _bad('所属项目不存在')
    item = store.collections.create({
        'name': name, 'description': _clean(d.get('description'), 500),
        'project_id': int(d['project_id']),
        'parent_id': int(d['parent_id']) if d.get('parent_id') else None,
        'order': int(d.get('order') or 0),
    })
    return _ok(item)


@bp.route('/api/collections/<int:cid>', methods=['PUT', 'DELETE'])
def collection_detail(cid):
    if request.method == 'DELETE':
        for r in store.requests.list(collection_id=cid):
            r2 = dict(r, collection_id=None)      # 请求不级联删，挪出集合
            store.requests.update(r['id'], r2)
        for c in store.collections.list(parent_id=cid):
            store.collections.update(c['id'], {'parent_id': None})
        store.collections.delete(cid)
        return _ok(msg='集合已删除')
    return _ok(store.collections.update(cid, _body()))


# ---------------- 请求 ----------------
def _validate_request_payload(d):
    """请求字段的公共校验（新建/编辑共用）"""
    if not _clean(d.get('name')):
        return '请求名称不能为空'
    if _clean(d.get('method') or 'GET') not in HTTP_METHODS:
        return '请求方式不合法: %s' % d.get('method')
    url = _clean(d.get('url'))
    if not url:
        return '请求地址不能为空'
    if not (url.startswith('http://') or url.startswith('https://') or '{{' in url or '${' in url):
        return '请求地址必须以 http(s):// 开头（或含变量）'
    return ''


@bp.route('/api/requests', methods=['GET', 'POST'])
def requests_api():
    if request.method == 'GET':
        pid = request.args.get('project')
        items = store.requests.list(project_id=int(pid)) if pid else store.requests.list()
        return _ok(items)
    d = _body()
    err = _validate_request_payload(d)
    if err:
        return _bad(err)
    item = store.requests.create({
        'name': _clean(d['name']),
        'description': _clean(d.get('description'), 500),
        'project_id': int(d['project_id']) if d.get('project_id') else None,
        'collection_id': int(d['collection_id']) if d.get('collection_id') else None,
        'request_type': _clean(d.get('request_type') or 'HTTP'),
        'method': _clean(d.get('method') or 'GET'),
        'url': _clean(d['url'], 1000),
        'headers': d.get('headers') or [],
        'params': d.get('params') or {},
        'body': d.get('body') or {'type': 'none', 'data': None},
        'assertions': d.get('assertions') or [],
    })
    return _ok(item)


@bp.route('/api/requests/<int:rid>', methods=['GET', 'PUT', 'DELETE'])
def request_detail(rid):
    req = store.requests.get(rid)
    if not req:
        return _bad('请求不存在', 404)
    if request.method == 'GET':
        return _ok(req)
    if request.method == 'DELETE':
        store.requests.delete(rid)
        for h in store.histories.list(request_id=rid):
            store.histories.delete(h['id'])
        for s in store.suites.list():
            srs = [x for x in (s.get('suite_requests') or []) if x.get('request_id') != rid]
            store.suites.update(s['id'], {'suite_requests': srs})
        return _ok(msg='请求已删除')
    d = _body()
    err = _validate_request_payload({**req, **d})
    if err:
        return _bad(err)
    patch = {k: d[k] for k in ('name', 'description', 'collection_id', 'method', 'url',
                               'headers', 'params', 'body', 'assertions') if k in d}
    return _ok(store.requests.update(rid, patch))


@bp.route('/api/requests/<int:rid>/execute', methods=['POST'])
def request_execute(rid):
    """执行请求（testhub RequestViewSet.execute）：env_id + 前端覆盖参数"""
    req = store.requests.get(rid)
    if not req:
        return _bad('请求不存在', 404)
    d = _body()
    env = store.environments.get(d['environment_id']) if d.get('environment_id') else \
        next((e for e in store.environments.list() if e.get('is_active')), None)   # 兜底：激活环境
    overrides = {k: d[k] for k in ('method', 'url', 'headers', 'params', 'body',
                                   'assertions', 'executed_by') if k in d}
    history = executor.send_request(req, env, overrides)
    return _ok(history)


@bp.route('/api/requests/<int:rid>/histories')
def request_histories(rid):
    items = sorted(store.histories.list(request_id=rid), key=lambda x: -x['id'])
    return _ok(_page(items, request.args))


# ---------------- 请求历史 ----------------
@bp.route('/api/histories')
def histories():
    rid = request.args.get('request')
    items = store.histories.list(request_id=int(rid)) if rid else store.histories.list()
    items = sorted(items, key=lambda x: -x['id'])
    return _ok(_page(items, request.args))


@bp.route('/api/histories/batch-delete', methods=['POST'])
def histories_batch_delete():
    ids = [int(i) for i in (_body().get('ids') or [])]
    for i in ids:
        store.histories.delete(i)
    return _ok(msg='已删除 %d 条历史' % len(ids))


# ---------------- 环境 ----------------
@bp.route('/api/environments', methods=['GET', 'POST'])
def environments():
    if request.method == 'GET':
        return _ok(store.environments.list())
    d = _body()
    name = _clean(d.get('name'))
    if not name:
        return _bad('环境名称不能为空')
    if not isinstance(d.get('variables') or {}, dict):
        return _bad('环境变量必须是 key-value 对象')
    scope = _clean(d.get('scope') or 'LOCAL')
    if scope not in ('GLOBAL', 'LOCAL'):
        return _bad('作用域不合法')
    item = store.environments.create({
        'name': name, 'scope': scope,
        'variables': d.get('variables') or {},
        'is_active': bool(d.get('is_active')),
        'project_id': int(d['project_id']) if d.get('project_id') else None,
    })
    if item.get('is_active'):
        _activate_env(item['id'])
    return _ok(item)


def _activate_env(eid):
    """testhub 的 activate 语义：全局只保留一个激活环境"""
    for e in store.environments.list():
        store.environments.update(e['id'], {'is_active': e['id'] == int(eid)})


@bp.route('/api/environments/<int:eid>', methods=['PUT', 'DELETE'])
def environment_detail(eid):
    if request.method == 'DELETE':
        store.environments.delete(eid)
        return _ok(msg='环境已删除')
    d = _body()
    patch = {k: d[k] for k in ('name', 'scope', 'variables', 'is_active', 'project_id') if k in d}
    item = store.environments.update(eid, patch)
    if item and patch.get('is_active'):
        _activate_env(eid)
    return _ok(item)


@bp.route('/api/environments/<int:eid>/activate', methods=['POST'])
def environment_activate(eid):
    if not store.environments.get(eid):
        return _bad('环境不存在', 404)
    _activate_env(eid)
    return _ok(msg='已激活')


# ---------------- 测试套件 ----------------
@bp.route('/api/suites', methods=['GET', 'POST'])
def suites():
    if request.method == 'GET':
        return _ok(store.suites.list())
    d = _body()
    name = _clean(d.get('name'))
    if not name:
        return _bad('套件名称不能为空')
    if not store.projects.get(d.get('project_id')):
        return _bad('所属项目不存在')
    item = store.suites.create({
        'name': name, 'description': _clean(d.get('description'), 500),
        'project_id': int(d['project_id']),
        'environment_id': int(d['environment_id']) if d.get('environment_id') else None,
        'suite_requests': [],
    })
    return _ok(item)


@bp.route('/api/suites/<int:sid>', methods=['PUT', 'DELETE'])
def suite_detail(sid):
    if request.method == 'DELETE':
        store.suites.delete(sid)
        for t in store.tasks.list(suite_id=sid):
            store.tasks.delete(t['id'])
        return _ok(msg='套件及其定时任务已删除')
    d = _body()
    patch = {k: d[k] for k in ('name', 'description', 'environment_id', 'suite_requests') if k in d}
    return _ok(store.suites.update(sid, patch))


@bp.route('/api/suites/<int:sid>/add-requests', methods=['POST'])
def suite_add_requests(sid):
    """套件加请求（testhub add-requests）：body {request_ids:[...]}，按顺序追加"""
    suite = store.suites.get(sid)
    if not suite:
        return _bad('套件不存在', 404)
    ids = [int(i) for i in (_body().get('request_ids') or [])]
    srs = list(suite.get('suite_requests') or [])
    order = max([x.get('order', 0) for x in srs] or [0])
    for rid in ids:
        if any(x.get('request_id') == rid for x in srs):
            continue                      # 同一请求在套件内唯一（unique_together 语义）
        order += 1
        srs.append({'request_id': rid, 'order': order, 'assertions': [], 'enabled': True})
    return _ok(store.suites.update(sid, {'suite_requests': srs}))


@bp.route('/api/suites/<int:sid>/execute', methods=['POST'])
def suite_execute(sid):
    """执行套件：后台线程跑，立即返回执行记录（前端轮询）"""
    suite = store.suites.get(sid)
    if not suite:
        return _bad('套件不存在', 404)
    d = _body()
    env = store.environments.get(d['environment_id']) if d.get('environment_id') else \
        (store.environments.get(suite.get('environment_id')) if suite.get('environment_id') else None)
    executed_by = _clean(d.get('executed_by') or 'platform', 40)
    execution = store.executions.create({
        'suite_id': sid, 'status': 'RUNNING', 'start_time': int(time.time()),
        'end_time': None, 'total_requests': 0, 'passed_requests': 0,
        'failed_requests': 0, 'results': [], 'executed_by': executed_by,
    })

    def run():
        fresh = store.suites.get(sid) or suite
        # 传入已建的外层执行记录，execute_suite 只负责更新（避免双记录/id 覆盖）
        executor.execute_suite(fresh, env, executed_by, execution=store.executions.get(execution['id']))

    executor.run_in_thread(run)
    return _ok(store.executions.get(execution['id']))


@bp.route('/api/executions')
def executions():
    sid = request.args.get('suite')
    items = store.executions.list(suite_id=int(sid)) if sid else store.executions.list()
    return _ok(_page(sorted(items, key=lambda x: -x['id']), request.args))


@bp.route('/api/executions/<int:eid>')
def execution_detail(eid):
    item = store.executions.get(eid)
    return _ok(item) if item else _bad('执行记录不存在', 404)


# ---------------- 定时任务 ----------------
TRIGGER_TYPES = ('CRON', 'INTERVAL', 'ONCE')
TASK_TYPES = ('TEST_SUITE', 'API_REQUEST')


def _validate_task(d):
    if not _clean(d.get('name')):
        return '任务名称不能为空'
    if d.get('task_type') not in TASK_TYPES:
        return '任务类型不合法'
    if d.get('trigger_type') not in TRIGGER_TYPES:
        return '触发器类型不合法'
    if d['trigger_type'] == 'CRON' and not _clean(d.get('cron_expression')):
        return 'Cron 表达式不能为空'
    if d['trigger_type'] == 'INTERVAL' and int(d.get('interval_seconds') or 0) <= 0:
        return '间隔秒数必须为正整数'
    if d['trigger_type'] == 'ONCE' and not d.get('execute_at'):
        return '单次执行必须指定执行时间'
    if d.get('task_type') == 'TEST_SUITE' and not d.get('suite_id'):
        return '套件任务必须选择测试套件'
    if d.get('task_type') == 'API_REQUEST' and not d.get('request_id'):
        return '请求任务必须选择 API 请求'
    return ''


@bp.route('/api/tasks', methods=['GET', 'POST'])
def tasks():
    if request.method == 'GET':
        return _ok(store.tasks.list())
    d = _body()
    err = _validate_task(d)
    if err:
        return _bad(err)
    try:
        probe = {**d, 'trigger_type': d['trigger_type']}
        if d['trigger_type'] == 'ONCE':
            probe['execute_at'] = d['execute_at']
        nxt = scheduler.calculate_next_run(probe)
        if d['trigger_type'] == 'CRON' and nxt is None:
            return _bad('Cron 表达式无法解析')
    except Exception as e:
        return _bad('触发器配置无法解析: %s' % e)
    item = store.tasks.create({
        'name': _clean(d['name']),
        'description': _clean(d.get('description'), 500),
        'task_type': d['task_type'],
        'trigger_type': d['trigger_type'],
        'cron_expression': _clean(d.get('cron_expression'), 100),
        'interval_seconds': int(d['interval_seconds']) if d.get('interval_seconds') else None,
        'execute_at': int(d['execute_at']) if d.get('execute_at') else None,
        'suite_id': int(d['suite_id']) if d.get('suite_id') else None,
        'request_id': int(d['request_id']) if d.get('request_id') else None,
        'environment_id': int(d['environment_id']) if d.get('environment_id') else None,
        'status': 'ACTIVE' if d.get('status', 'ACTIVE') == 'ACTIVE' else 'PAUSED',
        'next_run_time': scheduler.calculate_next_run(
            {**d, 'execute_at': int(d['execute_at']) if d.get('execute_at') else None})
        if d.get('status', 'ACTIVE') == 'ACTIVE' else None,
        'last_run_time': None, 'total_runs': 0, 'successful_runs': 0, 'failed_runs': 0,
        'last_result': {}, 'error_message': '',
    })
    return _ok(item)


@bp.route('/api/tasks/<int:tid>', methods=['PUT', 'DELETE'])
def task_detail(tid):
    if request.method == 'DELETE':
        store.tasks.delete(tid)
        for lg in store.task_logs.list(task_id=tid):
            store.task_logs.delete(lg['id'])
        return _ok(msg='任务及其执行日志已删除')
    d = _body()
    task = store.tasks.get(tid)
    err = _validate_task({**task, **d}) if task else '任务不存在'
    if err:
        return _bad(err)
    patch = {k: d[k] for k in ('name', 'description', 'task_type', 'trigger_type',
                               'cron_expression', 'interval_seconds', 'execute_at',
                               'suite_id', 'request_id', 'environment_id', 'status') if k in d}
    item = store.tasks.update(tid, patch)
    if item and item.get('status') == 'ACTIVE':
        store.tasks.update(tid, {'next_run_time': scheduler.calculate_next_run(item)})
    return _ok(store.tasks.get(tid))


@bp.route('/api/tasks/<int:tid>/run-now', methods=['POST'])
def task_run_now(tid):
    log, err = scheduler.run_task_now(tid, trigger='manual')
    return _bad(err) if err else _ok(log, msg='已触发执行')


@bp.route('/api/tasks/<int:tid>/activate', methods=['POST'])
def task_activate(tid):
    task = store.tasks.get(tid)
    if not task:
        return _bad('任务不存在', 404)
    patch = {'status': 'ACTIVE', 'next_run_time': scheduler.calculate_next_run(task)}
    return _ok(store.tasks.update(tid, patch), msg='已激活')


@bp.route('/api/tasks/<int:tid>/pause', methods=['POST'])
def task_pause(tid):
    return _ok(store.tasks.update(tid, {'status': 'PAUSED', 'next_run_time': None}), msg='已暂停')


@bp.route('/api/tasks/<int:tid>/logs')
def task_logs(tid):
    items = sorted(store.task_logs.list(task_id=tid), key=lambda x: -x['id'])
    return _ok(_page(items, request.args))


@bp.route('/api/task-logs')
def all_task_logs():
    return _ok(_page(sorted(store.task_logs.list(), key=lambda x: -x['id']), request.args))


# ---------------- 通知设置（原 TaskNotificationSetting 全局化） ----------------
@bp.route('/api/settings', methods=['GET', 'PUT'])
def notification_settings():
    store.get_settings()               # 确保单例记录存在（空库时 PUT 也能落盘）
    if request.method == 'GET':
        s = dict(store.get_settings())
        s.pop('smtp_password', None)       # 不回传明文密码
        return _ok(s)
    d = _body()
    patch = {k: d[k] for k in ('notify_on_success', 'notify_on_failure', 'notify_emails',
                               'webhook_url', 'smtp_host', 'smtp_port', 'smtp_user',
                               'smtp_password', 'smtp_from', 'smtp_use_ssl') if k in d}
    return _ok(store.settings.update(1, patch))


# ---------------- 内置 mock 被测服务（demo/自测用，离线可用） ----------------
@bp.route('/mock/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def mock_echo():
    """原样回显请求信息：url/args/headers/body，供请求调试与断言演示"""
    d = _body()
    return jsonify({
        'ok': True,
        'method': request.method,
        'path': request.path,
        'args': request.args.to_dict(),
        'headers': {k: v for k, v in request.headers.items() if k.lower() not in
                    ('host', 'content-length', 'user-agent', 'accept-encoding', 'connection')},
        'body': d,
        'echo_time': int(time.time()),
    })


@bp.route('/mock/login', methods=['POST'])
def mock_login():
    """固定响应的登录接口：供断言（json_path/status_code）演示与套件联测"""
    d = _body()
    if d.get('username') == 'admin' and d.get('password') == '123456':
        return jsonify({'code': 0, 'message': 'success',
                        'data': {'token': 'mock-token-%d' % int(time.time()),
                                 'user': {'name': '管理员', 'role': 'admin'}}})
    return jsonify({'code': 1001, 'message': '用户名或密码错误'}), 200


@bp.route('/mock/slow', methods=['GET'])
def mock_slow():
    """延迟响应：供响应时间断言演示（?ms=800）"""
    ms = min(5000, max(0, int(request.args.get('ms', 500))))
    time.sleep(ms / 1000.0)
    return jsonify({'ok': True, 'slept_ms': ms})
