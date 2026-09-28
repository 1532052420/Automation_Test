# -*- coding: utf-8 -*-
"""接口测试 · REST 路由（移植 testhub apps/api_testing 的 ViewSet 端点）

端点与 testhub 一一对应（DRF router → Flask blueprint）：
  projects / collections / requests / environments / histories /
  test-suites / test-executions / scheduled-tasks / task-execution-logs /
  dashboard / 通知设置（原 TaskNotificationSetting 简化为全局设置）
另内置 /api-testing/mock/* 回显服务，作为自测/demo 的被测目标（离线可用）。
字段名与 testhub 模型保持同名，持久化走 YAML 存储层。
"""
import os
import time

from flask import Blueprint, jsonify, request, send_file

from web_platform.api_testing import yaml_store as store
from web_platform.api_testing import executor, scheduler
from web_platform.api_testing import media_assertions

bp = Blueprint('api_testing', __name__, url_prefix='/api-testing')

HTTP_METHODS = ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS')
# 断言类型清单不在本层维护：普通类型见 executor.execute_assertions，
# 音视频类型见 executor.MEDIA_ASSERT_TYPES（实现见 media_assertions.py）。


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




def _oplog(operation_type, resource_type, resource_id, resource_name, description=''):
    """操作日志（testhub OperationLog；Dashboard 最近活动数据源）"""
    store.operation_logs.create({
        'operation_type': operation_type, 'resource_type': resource_type,
        'resource_id': resource_id, 'resource_name': _clean(resource_name, 120),
        'description': _clean(description, 300), 'user': 'platform',
    })
    store.trim_logs()

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
    _oplog('create', 'project', item['id'], item['name'], '创建项目')
    return _ok(item)


@bp.route('/api/projects/<int:pid>', methods=['GET', 'PUT', 'DELETE'])
def project_detail(pid):
    if request.method == 'GET':
        item = store.projects.get(pid)
        return _ok(item) if item else _bad('项目不存在', 404)
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
        _oplog('delete', 'project', pid, '', '删除项目及关联数据')
        return _ok(msg='项目及关联数据已删除')
    item = store.projects.update(pid, _body())
    if item:
        _oplog('edit', 'project', pid, item.get('name', ''), '更新项目')
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
    _oplog('create', 'request', item['id'], item['name'], '%s %s' % (item['method'], item['url'][:80]))
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
        for s2 in store.suites.list():
            srs = [x for x in (s2.get('suite_requests') or []) if x.get('request_id') != rid]
            store.suites.update(s2['id'], {'suite_requests': srs})
        _oplog('delete', 'request', rid, req.get('name', ''), '删除接口')
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
    _oplog('execute', 'request', rid, req.get('name', ''),
           '状态码 %s' % (history.get('status_code') or 'ERR'))
    return _ok(history)


@bp.route('/api/requests/<int:rid>/histories')
def request_histories(rid):
    items = sorted(store.histories.list(request_id=rid), key=lambda x: -x['id'])
    return _ok(_page(items, request.args))


# ---------------- 请求历史 ----------------
def _enrich_history(h):
    """历史记录联表富化：嵌套 request/environment 概要（对齐 testhub 序列化结构）"""
    r = store.requests.get(h.get('request_id')) or {}
    e = store.environments.get(h.get('environment_id')) if h.get('environment_id') else None
    return dict(h, request={'id': r.get('id'), 'name': r.get('name'),
                            'method': r.get('method'), 'request_type': r.get('request_type')},
                environment={'id': (e or {}).get('id'), 'name': (e or {}).get('name')} if e else None)


@bp.route('/api/histories')
def histories():
    rid = request.args.get('request')
    if rid:
        items = store.histories.list(request_id=int(rid))
    else:
        rtype = request.args.get('request__request_type')
        items = store.histories.list()
        if rtype:
            rids = {r['id'] for r in store.requests.list(request_type=rtype)}
            items = [h for h in items if h.get('request_id') in rids]
    items = [_enrich_history(h) for h in sorted(items, key=lambda x: -x['id'])]
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
    _oplog('edit', 'environment', eid, (store.environments.get(eid) or {}).get('name', ''), '激活环境')
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
    _oplog('create', 'suite', item['id'], item['name'], '创建测试套件')
    return _ok(item)


@bp.route('/api/suites/<int:sid>', methods=['GET', 'PUT', 'DELETE'])
def suite_detail(sid):
    if request.method == 'GET':
        item = store.suites.get(sid)
        return _ok(item) if item else _bad('套件不存在', 404)
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
    _oplog('execute', 'suite', sid, suite.get('name', ''), '执行测试套件 #%s' % execution['id'])
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
        'notify_on_success': bool(d.get('notify_on_success')),
        'notify_on_failure': bool(d.get('notify_on_failure', True)),
        'notification_type': _clean(d.get('notification_type') or 'both', 20),
        'notify_emails': d.get('notify_emails') or [],
    })
    _oplog('create', 'task', item['id'], item['name'], '创建定时任务')
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
                               'suite_id', 'request_id', 'environment_id', 'status',
                               'notify_on_success', 'notify_on_failure',
                               'notification_type', 'notify_emails') if k in d}
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




# ================= ===== 以下为 v6.15 完整对齐 testhub 的新增端点 ================= =====

# ---------------- 变量助手目录（对应 testhub GET /data-factory/variable_functions/） ----------------
VARIABLE_FUNCTIONS = {
 "加密哈希": [
  {
   "name": "aes_decrypt",
   "args": "(encrypted_text: str, password: str, mode: str = 'CBC') -> Dict[str, Any]",
   "desc": "AES解密"
  },
  {
   "name": "aes_encrypt",
   "args": "(text: str, password: str, mode: str = 'CBC') -> Dict[str, Any]",
   "desc": "AES加密"
  },
  {
   "name": "hash_comparison",
   "args": "(text: str, hash_value: str, algorithm: str = 'md5') -> Dict[str, Any]",
   "desc": "哈希值比对"
  },
  {
   "name": "md5",
   "args": "",
   "desc": ""
  },
  {
   "name": "md5_hash",
   "args": "(text: str) -> Dict[str, Any]",
   "desc": "MD5加密"
  },
  {
   "name": "sha1",
   "args": "",
   "desc": ""
  },
  {
   "name": "sha1_hash",
   "args": "(text: str) -> Dict[str, Any]",
   "desc": "SHA1加密"
  },
  {
   "name": "sha256",
   "args": "",
   "desc": ""
  },
  {
   "name": "sha256_hash",
   "args": "(text: str) -> Dict[str, Any]",
   "desc": "SHA256加密"
  },
  {
   "name": "sha512_hash",
   "args": "(text: str) -> Dict[str, Any]",
   "desc": "SHA512加密"
  }
 ],
 "编码转换": [
  {
   "name": "ascii_convert",
   "args": "(text: str, convert_type: str = 'to_ascii') -> Dict[str, Any]",
   "desc": "ASCII码转换"
  },
  {
   "name": "base64",
   "args": "",
   "desc": ""
  },
  {
   "name": "base64_decode",
   "args": "(text: str, encoding: str = 'utf-8') -> Dict[str, Any]",
   "desc": "Base64解码"
  },
  {
   "name": "base64_encode",
   "args": "(text: str, encoding: str = 'utf-8') -> Dict[str, Any]",
   "desc": "Base64编码"
  },
  {
   "name": "base64_to_image",
   "args": "(base64_str: str) -> Dict[str, Any]",
   "desc": "Base64转图片"
  },
  {
   "name": "base_convert",
   "args": "(number: Any, from_base: int = 10, to_base: int = 16) -> Dict[str, Any]",
   "desc": "进制转换"
  },
  {
   "name": "color_convert",
   "args": "(color: str, from_type: str = 'hex', to_type: str = 'rgb') -> Dict[str, Any]",
   "desc": "颜色值转换"
  },
  {
   "name": "image_to_base64",
   "args": "(image_data: Union[bytes, str], image_format: str, include_prefix: bool = True) -> Dict[str, Any]",
   "desc": "图片转Base64"
  },
  {
   "name": "unicode_convert",
   "args": "(text: str, convert_type: str = 'to_unicode') -> Dict[str, Any]",
   "desc": "中文转Unicode"
  },
  {
   "name": "url_decode",
   "args": "(data: str, encoding: str = 'utf-8', plus: bool = False) -> Dict[str, Any]",
   "desc": "URL解码"
  },
  {
   "name": "url_encode",
   "args": "(data: str, encoding: str = 'utf-8', safe: str = '', plus: bool = False) -> Dict[str, Any]",
   "desc": "URL编码"
  }
 ],
 "字符串处理": [
  {
   "name": "case_convert",
   "args": "(text: str, convert_type: str) -> Dict[str, Any]",
   "desc": "大小写转换"
  },
  {
   "name": "regex_test",
   "args": "(pattern: str, text: str, flags: str = '') -> Dict[str, Any]",
   "desc": "正则表达式测试"
  },
  {
   "name": "remove_whitespace",
   "args": "(text: str) -> Dict[str, Any]",
   "desc": "去除空格和换行"
  },
  {
   "name": "replace_string",
   "args": "(text: str, old_str: str, new_str: str, is_regex: bool = False) -> Dict[str, Any]",
   "desc": "字符串替换"
  },
  {
   "name": "word_count",
   "args": "(text: str) -> Dict[str, Any]",
   "desc": "字数统计"
  }
 ],
 "时间日期": [
  {
   "name": "date",
   "args": "()",
   "desc": "Return date object with same year, month and day."
  },
  {
   "name": "date_offset",
   "args": "(days=0, hours=0, minutes=0, format_str='%Y-%m-%d %H:%M:%S')",
   "desc": "生成偏移后的日期时间"
  },
  {
   "name": "datetime",
   "args": "(format_str='%Y-%m-%d %H:%M:%S')",
   "desc": "生成当前日期时间"
  },
  {
   "name": "time",
   "args": "()",
   "desc": "Return time object with same time but with tzinfo=None."
  },
  {
   "name": "timestamp",
   "args": "()",
   "desc": "Return POSIX timestamp as float."
  },
  {
   "name": "timestamp_convert",
   "args": "(timestamp: Any, convert_type: str = 'to_datetime', timestamp_unit: str = 'auto') -> Dict[str, Any]",
   "desc": "时间戳转换"
  },
  {
   "name": "timestamp_sec",
   "args": "()",
   "desc": "生成当前时间戳（秒）"
  }
 ],
 "其他": [
  {
   "name": "decode_qrcode",
   "args": "(image_data: str, image_format: str = 'png') -> Dict[str, Any]",
   "desc": "解析二维码图片"
  }
 ],
 "证件与卡号": [
  {
   "name": "generate_bank_card",
   "args": "(count: int = 1) -> Dict[str, Any]",
   "desc": "生成银行卡号"
  },
  {
   "name": "generate_barcode",
   "args": "(data: str, barcode_type: str = 'code128', save_to_static: bool = True) -> Dict[str, Any]",
   "desc": "生成条形码"
  },
  {
   "name": "generate_business_license",
   "args": "(count: int = 1) -> Dict[str, Any]",
   "desc": "生成营业执照号"
  },
  {
   "name": "generate_company_name",
   "args": "(company_type: str = 'all', count: int = 1) -> Dict[str, Any]",
   "desc": "生成公司名称"
  },
  {
   "name": "generate_coordinates",
   "args": "(count: int = 1) -> Dict[str, Any]",
   "desc": "生成经纬度"
  },
  {
   "name": "generate_expression",
   "args": "(minute: str, hour: str, day: str, month: str, weekday: str) -> Dict[str, Any]",
   "desc": "生成Crontab表达式"
  },
  {
   "name": "generate_hk_id_card",
   "args": "(count: int = 1) -> Dict[str, Any]",
   "desc": "生成香港身份证号"
  },
  {
   "name": "generate_id_card",
   "args": "(count: int = 1) -> Dict[str, Any]",
   "desc": "生成身份证号"
  },
  {
   "name": "generate_qrcode",
   "args": "(data: str, image_size: int = 300, border: int = 4, save_to_static: bool = True) -> Dict[str, Any]",
   "desc": "生成二维码"
  },
  {
   "name": "generate_user_profile",
   "args": "(count: int = 1) -> Dict[str, Any]",
   "desc": "生成完整的用户档案"
  }
 ],
 "中文数据": [
  {
   "name": "generate_chinese_address",
   "args": "(full_address: bool = True, count: int = 1) -> Dict[str, Any]",
   "desc": "生成中国地址"
  },
  {
   "name": "generate_chinese_email",
   "args": "(domain: str = 'random', count: int = 1) -> Dict[str, Any]",
   "desc": "生成中国邮箱"
  },
  {
   "name": "generate_chinese_name",
   "args": "(gender: str = 'random', count: int = 1) -> Dict[str, Any]",
   "desc": "生成中文姓名"
  },
  {
   "name": "generate_chinese_phone",
   "args": "(region: str = 'all', count: int = 1) -> Dict[str, Any]",
   "desc": "生成中国手机号"
  }
 ],
 "Cron工具": [
  {
   "name": "get_next_runs",
   "args": "(expression: str, count: int = 10) -> Dict[str, Any]",
   "desc": "获取Crontab表达式的下次执行时间"
  },
  {
   "name": "parse_expression",
   "args": "(expression: str) -> Dict[str, Any]",
   "desc": "解析Crontab表达式"
  },
  {
   "name": "validate_expression",
   "args": "(expression: str) -> Dict[str, Any]",
   "desc": "验证Crontab表达式"
  }
 ],
 "随机数据": [
  {
   "name": "random_address",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_boolean",
   "args": "(count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机布尔值"
  },
  {
   "name": "random_chinese",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_color",
   "args": "(format: str = 'hex', count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机颜色"
  },
  {
   "name": "random_company",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_date",
   "args": "(start_date: str, end_date: str, count: int = 1, date_format: str = '%Y-%m-%d') -> Dict[str, Any]",
   "desc": "生成随机日期"
  },
  {
   "name": "random_digits",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_email",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_float",
   "args": "(min_val: float, max_val: float, precision: int = 2, count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机浮点数"
  },
  {
   "name": "random_guid",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_id_card",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_int",
   "args": "(min_val: int, max_val: int, count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机整数"
  },
  {
   "name": "random_ip",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_ip_address",
   "args": "(ip_version: int = 4, count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机IP地址"
  },
  {
   "name": "random_letters",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_mac",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_mac_address",
   "args": "(separator: str = ':', count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机MAC地址"
  },
  {
   "name": "random_name",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_password",
   "args": "(length: int = 12, include_uppercase: bool = True, include_lowercase: bool = True, include_digits: bool = True, include_special: bool = True, count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机密码"
  },
  {
   "name": "random_phone",
   "args": "",
   "desc": ""
  },
  {
   "name": "random_sequence",
   "args": "(sequence: List, count: int = 1, unique: bool = False) -> Dict[str, Any]",
   "desc": "从序列中随机选择"
  },
  {
   "name": "random_string",
   "args": "(length: int = 10, char_type: str = 'all', count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机字符串"
  },
  {
   "name": "random_uuid",
   "args": "(version: int = 4, count: int = 1) -> Dict[str, Any]",
   "desc": "生成随机UUID"
  }
 ]
}



@bp.route('/api/data-factory/functions')
def data_factory_functions():
    """变量助手/数据工厂函数目录（分组：随机数据/编码转换/加密哈希/时间日期/…）"""
    return _ok({cat: fns for cat, fns in VARIABLE_FUNCTIONS.items()})


# ---------------- 集合搜索（testhub GET /collections/search，前端防抖搜索） ----------------
@bp.route('/api/collections/search')
def collections_search():
    keyword = (request.args.get('keyword') or '').strip().lower()
    pid = request.args.get('project')
    items = store.collections.list(project_id=int(pid)) if pid else store.collections.list()
    out = []
    if keyword:
        for c in items:
            if keyword in (c.get('name') or '').lower():
                out.append({'id': c['id'], 'name': c.get('name'), 'type': 'collection',
                            'match_type': '名称'})
        for r in store.requests.list(project_id=int(pid)) if pid else store.requests.list():
            hit = None
            if keyword in (r.get('name') or '').lower():
                hit = '名称'
            elif keyword in (r.get('url') or '').lower():
                hit = 'URL'
            elif keyword in (r.get('method') or '').lower():
                hit = '方法'
            if hit:
                out.append({'id': r['id'], 'name': r.get('name'), 'method': r.get('method'),
                            'url': r.get('url'), 'collection_id': r.get('collection_id'),
                            'type': 'request', 'match_type': hit})
    return _ok(out)


# ---------------- 用户（成员选择；testhub GET /users/，本机平台走本地注册表） ----------------
@bp.route('/api/users', methods=['GET', 'POST'])
def users():
    if request.method == 'GET':
        kw = (request.args.get('search') or '').strip().lower()
        items = store.users.list()
        if kw:
            items = [u for u in items if kw in (u.get('username') or '').lower()
                     or kw in (u.get('email') or '').lower()]
        return _ok(items)
    d = _body()
    name = _clean(d.get('username'))
    if not name:
        return _bad('用户名不能为空')
    if any(u.get('username') == name for u in store.users.list()):
        return _bad('用户名已存在')
    return _ok(store.users.create({'username': name, 'email': _clean(d.get('email'), 100)}))


# ---------------- 一键示例项目（testhub POST /projects/create-sample/） ----------------
@bp.route('/api/projects/create-sample', methods=['POST'])
def projects_create_sample():
    if any(p.get('name') == '宠物店API示例项目' for p in store.projects.list()):
        return _bad('示例项目已存在，无需重复创建')
    proj = store.projects.create({
        'name': '宠物店API示例项目', 'description': 'testhub 经典示例：宠物店接口（内置 mock 服务联调）',
        'project_type': 'HTTP', 'status': 'IN_PROGRESS', 'owner': 'platform',
    })
    col_cat = store.collections.create({'name': '宠物集合', 'description': '宠物增删改查',
                                        'project_id': proj['id'], 'parent_id': None, 'order': 1})
    col_user = store.collections.create({'name': '用户集合', 'description': '登录与用户信息',
                                         'project_id': proj['id'], 'parent_id': None, 'order': 2})
    base = request.host_url.rstrip('/') + '/api-testing'
    samples = [
        ('查询宠物列表', 'GET', base + '/mock/echo?type=pet list', col_cat['id'],
         [{'name': '状态码200', 'type': 'status_code', 'expected': 200}]),
        ('添加宠物', 'POST', base + '/mock/echo', col_cat['id'],
         [{'name': '状态码200', 'type': 'status_code', 'expected': 200},
          {'name': '包含ok', 'type': 'contains', 'expected': 'ok'}]),
        ('登录成功', 'POST', base + '/mock/login', col_user['id'],
         [{'name': 'code=0', 'type': 'json_path', 'json_path': '$.code', 'expected': 0}]),
        ('慢接口演示', 'GET', base + '/mock/slow?ms=200', col_user['id'],
         [{'name': '响应时间<1s', 'type': 'response_time', 'expected': 1000}]),
    ]
    for name, method, url, cid, asserts in samples:
        store.requests.create({
            'name': name, 'description': '', 'project_id': proj['id'], 'collection_id': cid,
            'request_type': 'HTTP', 'method': method, 'url': url,
            'headers': [], 'params': {}, 'body': {'type': 'none', 'data': None},
            'assertions': asserts,
        })
    return _ok(proj, msg='示例项目已创建（含 2 集合 4 接口，内置 mock 服务联调）')


# ---------------- 操作日志（Dashboard 最近活动 + 全量查询） ----------------
@bp.route('/api/operation-logs')
def operation_logs():
    otype = request.args.get('operation_type')
    rtype = request.args.get('resource_type')
    items = store.operation_logs.list()
    if otype:
        items = [x for x in items if x.get('operation_type') == otype]
    if rtype:
        items = [x for x in items if x.get('resource_type') == rtype]
    return _ok(_page(sorted(items, key=lambda x: -x['id']), request.args))


# ---------------- 请求复制（testhub 树节点「复制接口」） ----------------
@bp.route('/api/requests/<int:rid>/copy', methods=['POST'])
def request_copy(rid):
    req = store.requests.get(rid)
    if not req:
        return _bad('请求不存在', 404)
    dup = {k: v for k, v in req.items() if k not in ('id', 'created_at', 'updated_at')}
    dup['name'] = '%s - Copy' % req.get('name')
    return _ok(store.requests.create(dup), msg='已复制为「%s」' % dup['name'])


# ---------------- 请求历史：单删 / 清空 ----------------
@bp.route('/api/histories/<int:hid>', methods=['DELETE'])
def history_delete(hid):
    return _ok(msg='已删除') if store.histories.delete(hid) else _bad('记录不存在', 404)


@bp.route('/api/histories/clear', methods=['POST'])
def histories_clear():
    rtype = request.args.get('request_type')          # HTTP / WEBSOCKET / 空=全部
    if rtype:
        rids = {r['id'] for r in store.requests.list(request_type=rtype)}
        for h in store.histories.list():
            if h.get('request_id') in rids:
                store.histories.delete(h['id'])
    else:
        for h in store.histories.list():
            store.histories.delete(h['id'])
    store.trim_logs()
    return _ok(msg='历史已清空')


# ---------------- 套件-请求粒度操作（testhub /test-suite-requests/ CRUD） ----------------
@bp.route('/api/suites/<int:sid>/requests/<int:rid>', methods=['PUT', 'DELETE'])
def suite_request_detail(sid, rid):
    suite = store.suites.get(sid)
    if not suite:
        return _bad('套件不存在', 404)
    srs = list(suite.get('suite_requests') or [])
    hit = next((x for x in srs if x.get('request_id') == rid), None)
    if not hit:
        return _bad('该请求不在套件内', 404)
    if request.method == 'DELETE':
        srs = [x for x in srs if x.get('request_id') != rid]
        return _ok(store.suites.update(sid, {'suite_requests': srs}), msg='已移除')
    d = _body()
    patch = {k: d[k] for k in ('enabled', 'order', 'assertions') if k in d}
    hit.update(patch)
    srs.sort(key=lambda x: x.get('order', 0))
    return _ok(store.suites.update(sid, {'suite_requests': srs}))


# ---------------- AI 服务配置（testhub /ai-service-configs/ 全套） ----------------
from web_platform.api_testing import ai as _ai          # noqa: E402


@bp.route('/api/ai-configs', methods=['GET', 'POST'])
def ai_configs():
    if request.method == 'GET':
        items = store.ai_configs.list()
        out = [dict(c, service_type_display=_ai.SERVICE_NAMES.get(c.get('service_type'), c.get('service_type')),
                    role_display=_ai.ROLE_NAMES.get(c.get('role'), c.get('role'))) for c in items]
        for c in out:
            c.pop('api_key', None)            # 密钥不回传前端
        return _ok(out)
    d = _body()
    name = _clean(d.get('name'))
    if not name:
        return _bad('配置名称不能为空')
    if d.get('service_type') not in _ai.SERVICE_TYPES:
        return _bad('服务类型不合法')
    if d.get('role') not in _ai.ROLES:
        return _bad('角色不合法')
    if not _clean(d.get('api_key')) or not _clean(d.get('base_url')) or not _clean(d.get('model_name')):
        return _bad('api_key / base_url / model_name 均不能为空')
    return _ok(store.ai_configs.create({
        'name': name, 'service_type': d['service_type'], 'role': d['role'],
        'api_key': _clean(d.get('api_key'), 500), 'base_url': _clean(d.get('base_url'), 500).rstrip('/'),
        'model_name': _clean(d.get('model_name'), 100),
        'max_tokens': int(d.get('max_tokens') or 4096),
        'temperature': float(d.get('temperature') or 0.7),
        'is_active': bool(d.get('is_active')),
    }))


@bp.route('/api/ai-configs/<int:aid>', methods=['PUT', 'DELETE'])
def ai_config_detail(aid):
    if request.method == 'DELETE':
        return _ok(msg='已删除') if store.ai_configs.delete(aid) else _bad('配置不存在', 404)
    d = _body()
    patch = {k: d[k] for k in ('name', 'service_type', 'role', 'api_key', 'base_url',
                               'model_name', 'max_tokens', 'temperature', 'is_active') if k in d}
    if 'base_url' in patch:
        patch['base_url'] = str(patch['base_url']).rstrip('/')
    return _ok(store.ai_configs.update(aid, patch))


@bp.route('/api/ai-configs/test-connection', methods=['POST'])
def ai_test_connection():
    cid = _body().get('config_id')
    cfg = store.ai_configs.get(cid) if cid else None
    if not cfg:
        return _bad('配置不存在', 404)
    ok, msg = _ai.test_connection(cfg)
    return _ok({'status': 'success'} if ok else None, msg=msg) if ok else _bad(msg)


@bp.route('/api/ai-configs/complete-descriptions', methods=['POST'])
def ai_complete_descriptions():
    data, err = _ai.complete_parameter_descriptions(_body().get('request_id'))
    return _ok(data) if not err else _bad(err)


@bp.route('/api/ai-configs/generate-mock-data', methods=['POST'])
def ai_generate_mock_data():
    d = _body()
    data, err = _ai.generate_mock_data(d.get('schema') or {}, d.get('count') or 1)
    return _ok(data) if not err else _bad(err)


@bp.route('/api/ai-configs/normalize-names', methods=['POST'])
def ai_normalize_names():
    data, err = _ai.normalize_parameter_names(_body().get('parameters') or [])
    return _ok(data) if not err else _bad(err)


@bp.route('/api/ai-configs/extract-docs', methods=['POST'])
def ai_extract_docs():
    data, err = _ai.extract_documentation(_body().get('request_id'))
    return _ok(data) if not err else _bad(err)


# ---------------- 通知日志（testhub /notification-logs/ 只读 + 详情） ----------------
@bp.route('/api/notification-logs')
def notification_logs():
    status = request.args.get('status')
    ntype = request.args.get('notification_type')
    items = store.notification_logs.list()
    if status:
        items = [x for x in items if x.get('status') == status]
    if ntype:
        items = [x for x in items if x.get('notification_type') == ntype]
    return _ok(_page(sorted(items, key=lambda x: -x['id']), request.args))


@bp.route('/api/notification-logs/<int:nid>')
def notification_log_detail(nid):
    item = store.notification_logs.get(nid)
    if not item:
        return _bad('通知记录不存在', 404)
    recipients = '、'.join(
        ('%s（%s）' % (r.get('name'), r.get('email'))) if r.get('name') and r.get('email')
        else (r.get('email') or r.get('name') or '未知')
        for r in (item.get('recipient_info') or [])) or '未知收件人'
    return _ok(dict(item, recipients_display=recipients,
                    retry_status='未重试' if not item.get('is_retried') else '已重试 %s 次' % item.get('retry_count')))


# ---------------- Allure 报告（testhub POST /test-executions/{id}/generate-allure-report/） ----------------
from web_platform.api_testing import allure_report                     # noqa: E402
from flask import send_from_directory                                  # noqa: E402


@bp.route('/api/executions/<int:eid>/allure-report', methods=['POST'])
def execution_allure_report(eid):
    execution = store.executions.get(eid)
    if not execution:
        return _bad('执行记录不存在', 404)
    suite = store.suites.get(execution.get('suite_id'))
    execution = dict(execution,
                     suite_name=(suite or {}).get('name'),
                     project_name=(store.projects.get((suite or {}).get('project_id')) or {}).get('name'))
    url, err = allure_report.generate(execution)
    return _ok({'report_url': url}, msg='Allure报告生成成功') if not err else _bad(err, 500)


@bp.route('/report/execution_<eid>/<path:filename>')
def report_file(eid, filename):
    """报告静态文件服务（等价 testhub /media/api-testing/allure-reports/…）"""
    full = allure_report.report_dir(eid)
    if not os.path.isdir(full):
        return _bad('报告不存在，请先生成', 404)
    return send_from_directory(full, filename)


# ---------------- 通知设置扩展（webhook 多机器人，对齐 testhub UnifiedNotificationConfig） ----------------
@bp.route('/api/settings/webhook-bots', methods=['GET', 'PUT'])
def settings_webhook_bots():
    store.get_settings()
    if request.method == 'GET':
        return _ok(store.get_settings().get('webhook_bots') or [])
    bots = _body().get('bots')
    if not isinstance(bots, list):
        return _bad('bots 必须是数组')
    clean = []
    for b in bots:
        clean.append({'name': _clean(b.get('name'), 60), 'type': _clean(b.get('type') or 'generic', 20),
                      'webhook_url': _clean(b.get('webhook_url'), 500),
                      'secret': _clean(b.get('secret'), 200),
                      'enabled': bool(b.get('enabled'))})
    store.settings.update(1, {'webhook_bots': clean})
    return _ok(clean)

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


# 1 秒 440Hz 正弦波 WAV（标准库生成，进程内缓存字节）—— 音视频断言演示用
_media_wav_cache = None

def _mock_media_wav():
    """生成带有效声音的 WAV（非静音）：8kHz 采样、1 秒、440Hz 正弦、振幅 0.4"""
    global _media_wav_cache
    if _media_wav_cache is None:
        import io
        import math
        import struct
        import wave
        rate, seconds, amp = 8000, 1.0, 0.4
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            frames = b''.join(struct.pack('<h', int(amp * 32767 *
                                          math.sin(2 * math.pi * 440 * i / rate)))
                              for i in range(int(rate * seconds)))
            w.writeframes(frames)
        _media_wav_cache = buf.getvalue()
    return _media_wav_cache


@bp.route('/mock/media.wav', methods=['GET'])
def mock_media_wav():
    """返回 1 秒 440Hz 正弦 WAV：供「音频声音检测」断言演示与联测"""
    import io
    return send_file(io.BytesIO(_mock_media_wav()), mimetype='audio/wav')


# 1 秒 320x240 带音轨 MP4（ffmpeg 现场合成，进程内缓存）—— 视频属性断言演示用
_video_mp4_cache = None


def _mock_media_video():
    """生成 320x240 / 1 秒 / 带 AC 音轨的 MP4（H.264），分辨率与时长固定便于断言"""
    global _video_mp4_cache
    if _video_mp4_cache is None:
        import subprocess
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.mp4', prefix='mockvideo_')
        os.close(fd)
        cmd = [
            media_assertions.FFMPEG, '-y', '-v', 'error',
            '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=10:duration=1',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-shortest', path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
            with open(path, 'rb') as f:
                _video_mp4_cache = f.read()
        except Exception:
            _video_mp4_cache = None
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    return _video_mp4_cache


@bp.route('/mock/media.mp4', methods=['GET'])
def mock_media_video():
    """返回 320x240 / 1 秒 / 带音轨的 MP4：供「音视频检测」分辨率、时长、码率断言演示"""
    import io
    data = _mock_media_video()
    if not data:
        return jsonify({'ok': False, 'msg': '生成演示视频失败（需要可用的 ffmpeg）'}), 500
    return send_file(io.BytesIO(data), mimetype='video/mp4')
