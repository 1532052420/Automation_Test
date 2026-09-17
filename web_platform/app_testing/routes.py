# -*- coding: utf-8 -*-
"""AppUI 用例编排 · 测试用例 / 测试套件（移植自 testhub_platform apps/app_automation）

与 testhub 的对应关系（结构优化点见各路由注释）：
- AppTestCase（用例 = ui_flow 有序步骤 JSON）→ 用例 = 有序步骤列表，每步引用本仓库
  cases/app_ui 的 pytest 用例节点（scan_case_tree 扫描所得），执行直接复用 runner 链路；
- AppTestSuite + AppTestSuiteCase(through, order) → 套件内嵌有序 case_ids（YAML 无需 through 表）；
- AppTestExecution + Celery 回写 → 复用 runner.ExecutionManager，套件统计在读时惰性同步。

持久化走 api_testing.yaml_store.YamlStore（data_dir 参数化到 config/app_testing/）。
"""
import os
import time

from flask import Blueprint, jsonify, request

from web_platform import runner
from web_platform.api_testing.yaml_store import YamlStore
from web_platform.routes import _valid_nodes
from web_platform.runtime_config import BASE_DIR, list_devices_conf_files

bp = Blueprint('app_testing', __name__, url_prefix='/app-testing')

DATA_DIR = os.path.join(BASE_DIR, 'config', 'app_testing')
cases_store = YamlStore('cases', data_dir=DATA_DIR)
suites_store = YamlStore('suites', data_dir=DATA_DIR)

CASE_STATUS = ('NOT_RUN', 'RUNNING', 'COMPLETED', 'ERROR')
SUITE_RESULTS = ('PASSED', 'FAILED', 'SKIPPED')


def _ok(**payload):
    return jsonify(dict({'ok': True}, **payload))


def _bad(msg, code=400):
    return jsonify({'ok': False, 'msg': msg}), code


def _now():
    return int(time.time())


def _clean_cases_steps(steps):
    """校验并规整步骤列表：[{node, name}]；node 必须是合法 pytest nodeid（防注入）。
    返回 (steps, err_msg)。"""
    if steps is None:
        return [], ''
    if not isinstance(steps, list):
        return None, 'steps 必须是列表'
    out = []
    for s in steps:
        if not isinstance(s, dict):
            return None, '步骤必须是对象'
        node = str(s.get('node') or '').strip()
        if not node:
            return None, '步骤缺少用例节点(node)'
        if _valid_nodes([node]):
            return None, '用例节点不合法: %s' % node
        out.append({'node': node, 'name': str(s.get('name') or node)})
    return out, ''


def _clean_suite_case_ids(case_ids):
    """校验套件用例引用：必须是已存在用例 id 且去重，返回 (ids, err)。"""
    if case_ids is None:
        return [], ''
    if not isinstance(case_ids, list) or not all(isinstance(i, int) for i in case_ids):
        return None, 'case_ids 必须是整数列表'
    seen, out = set(), []
    for cid in case_ids:
        if not cases_store.get(cid):
            return None, '用例不存在: #%s' % cid
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out, ''


def _suite_public(suite):
    """套件公开结构：case_ids → cases 明细（含实时步骤数），并惰性同步执行统计。"""
    suite = _sync_suite_runs(suite)
    detail = []
    for cid in suite.get('case_ids') or []:
        c = cases_store.get(cid)
        if c:
            detail.append({'id': c['id'], 'name': c['name'], 'step_count': len(c.get('steps') or [])})
    suite['cases'] = detail
    return suite


# ---------------- 用例编排 / 测试用例 ----------------
@bp.route('/api/case-tree')
def api_case_tree():
    """可编排的原始用例树（与「选择用例」面板同一数据源）"""
    from web_platform.runtime_config import scan_case_tree
    return _ok(tree=scan_case_tree())


@bp.route('/api/cases', methods=['GET', 'POST'])
def api_cases():
    if request.method == 'GET':
        items = sorted(cases_store.list(), key=lambda c: -c['id'])
        return _ok(results=items)
    d = request.get_json(force=True, silent=True) or {}
    name = (d.get('name') or '').strip()
    if not name:
        return _bad('用例名称不能为空')
    steps, err = _clean_cases_steps(d.get('steps'))
    if err:
        return _bad(err)
    return _ok(case=cases_store.create({
        'name': name[:100], 'description': (d.get('description') or '').strip()[:500],
        'steps': steps, 'created_by': (d.get('created_by') or '').strip()[:40],
    }))


@bp.route('/api/cases/<int:cid>', methods=['GET', 'PUT', 'DELETE'])
def api_case_detail(cid):
    case = cases_store.get(cid)
    if not case:
        return _bad('用例不存在', 404)
    if request.method == 'GET':
        return _ok(case=case)
    if request.method == 'DELETE':
        cases_store.delete(cid)
        for s in suites_store.list():
            if cid in (s.get('case_ids') or []):
                suites_store.update(s['id'], {'case_ids': [i for i in s['case_ids'] if i != cid]})
        return _ok()
    d = request.get_json(force=True, silent=True) or {}
    patch = {}
    if 'name' in d:
        name = (d.get('name') or '').strip()
        if not name:
            return _bad('用例名称不能为空')
        patch['name'] = name[:100]
    if 'description' in d:
        patch['description'] = (d.get('description') or '').strip()[:500]
    if 'steps' in d:
        steps, err = _clean_cases_steps(d.get('steps'))
        if err:
            return _bad(err)
        patch['steps'] = steps
    return _ok(case=cases_store.update(cid, patch))


@bp.route('/api/cases/<int:cid>/run', methods=['POST'])
def api_case_run(cid):
    """单用例执行：按编排顺序展开步骤节点，走 AppUI 执行链路"""
    case = cases_store.get(cid)
    if not case:
        return _bad('用例不存在', 404)
    return _run_nodes([s['node'] for s in (case.get('steps') or [])],
                      (request.get_json(force=True, silent=True) or {}), case=case)


# ---------------- 测试套件 ----------------
@bp.route('/api/suites', methods=['GET', 'POST'])
def api_suites():
    if request.method == 'GET':
        items = sorted(suites_store.list(), key=lambda s: -s['id'])
        return _ok(results=[_suite_public(s) for s in items])
    d = request.get_json(force=True, silent=True) or {}
    name = (d.get('name') or '').strip()
    if not name:
        return _bad('套件名称不能为空')
    ids, err = _clean_suite_case_ids(d.get('case_ids'))
    if err:
        return _bad(err)
    return _ok(suite=_suite_public(suites_store.create({
        'name': name[:100], 'description': (d.get('description') or '').strip()[:500],
        'case_ids': ids,
        'execution_status': 'NOT_RUN', 'execution_result': None,
        'passed_count': 0, 'failed_count': 0, 'last_run_at': None, 'last_run_id': None,
        'runs': [],
    })))


@bp.route('/api/suites/<int:sid>', methods=['GET', 'PUT', 'DELETE'])
def api_suite_detail(sid):
    suite = suites_store.get(sid)
    if not suite:
        return _bad('套件不存在', 404)
    if request.method == 'GET':
        return _ok(suite=_suite_public(suite))
    if request.method == 'DELETE':
        suites_store.delete(sid)
        return _ok()
    d = request.get_json(force=True, silent=True) or {}
    patch = {}
    if 'name' in d:
        name = (d.get('name') or '').strip()
        if not name:
            return _bad('套件名称不能为空')
        patch['name'] = name[:100]
    if 'description' in d:
        patch['description'] = (d.get('description') or '').strip()[:500]
    if 'case_ids' in d:
        ids, err = _clean_suite_case_ids(d.get('case_ids'))
        if err:
            return _bad(err)
        patch['case_ids'] = ids
    return _ok(suite=_suite_public(suites_store.update(sid, patch)))


@bp.route('/api/suites/<int:sid>/run', methods=['POST'])
def api_suite_run(sid):
    """套件执行：按套件内用例顺序展开全部步骤节点（testhub AppTestSuiteViewSet.run）"""
    suite = suites_store.get(sid)
    if not suite:
        return _bad('套件不存在', 404)
    if not (suite.get('case_ids') or []):
        return _bad('该套件未包含任何测试用例')
    nodes = []
    for cid in suite['case_ids']:
        c = cases_store.get(cid) or {}
        nodes += [s['node'] for s in (c.get('steps') or [])]
    if not nodes:
        return _bad('套件内用例均无执行步骤')
    return _run_nodes(nodes, (request.get_json(force=True, silent=True) or {}), suite=suite)


def _run_nodes(nodes, body, suite=None, case=None):
    """公共执行入口：冲突校验 → runner.manager.start_run → 回写套件/用例执行状态"""
    running = runner.manager.running_task()
    if running:
        return _bad('已有任务在运行（Run %s），请等待完成或先停止' % running['run_id'], 409)
    if not nodes:
        return _bad('没有可执行的用例节点')
    conf_file = (body.get('conf_file') or '').strip() or \
        (list_devices_conf_files() or [''])[0]
    ok, result = runner.manager.start_run(
        conf_file, nodes, body.get('overrides') or {},
        owner=(body.get('owner') or '').strip()[:40])
    if not ok:
        return _bad(result, 409 if '正在运行' in result else 400)
    run_id = result
    if suite:
        suites_store.update(suite['id'], {
            'execution_status': 'RUNNING', 'execution_result': None,
            'last_run_at': _now(), 'last_run_id': run_id,
            'runs': ([{'run_id': run_id, 'start_time': _now()}] +
                     (suite.get('runs') or []))[:20],
        })
    if case:
        pass  # 用例级状态随 run 结果在列表读时展示，无需单独字段
    return _ok(run_id=run_id)


def _sync_suite_runs(suite):
    """读时惰性同步：把 runs 里已结束的 run 结果回写到套件统计（替代 testhub 的 Celery 回写）"""
    runs, changed = suite.get('runs') or [], False
    for r in runs:
        if r.get('status'):
            continue
        t = runner.manager.get_task(r['run_id'])
        if not t:
            r['status'] = 'UNKNOWN'
            changed = True
            continue
        if t['status'] in ('PENDING', 'RUNNING'):
            continue
        r.update({'status': t['status'], 'total': t.get('total', 0),
                  'passed': t.get('passed', 0), 'failed': t.get('failed', 0),
                  'error': t.get('error', 0)})
        changed = True
    if changed or (suite.get('execution_status') == 'RUNNING' and
                   (not runs or runs[0].get('status'))):
        last = next((r for r in runs if r.get('status') in ('PASSED', 'FAILED', 'ERROR')), None)
        patch = {'runs': runs, 'execution_status': 'COMPLETED' if runs else 'NOT_RUN'}
        if last:
            patch.update({'execution_result': last['status'],
                          'passed_count': last.get('passed', 0),
                          'failed_count': last.get('failed', 0) + last.get('error', 0)})
        elif runs:
            patch['execution_status'] = 'ERROR'
        suite.update(patch)
        suites_store.update(suite['id'], patch)
    return suite
