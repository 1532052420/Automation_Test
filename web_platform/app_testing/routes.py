# -*- coding: utf-8 -*-
"""AppUI 用例编排 · 测试用例 / 测试套件（移植自 testhub_platform apps/app_automation）

与 testhub 的对应关系（结构优化点见各路由注释）：
- AppTestCase（用例 = ui_flow 有序步骤 JSON，步骤引用元素执行）→ 同构落地：用例 = 有序步骤
  [{type, element, param, desc}]，元素即定位器/元素管理维护的同一份元素库；保存时由
  codegen 把编排编译成框架三件套（页面文件 + 用例文件，元素文件只引用不生成），
  生成文件自动进入「选择用例」树与现有 Appium/pytest 执行与报告链路；
- AppTestSuite + AppTestSuiteCase(through, order) → 套件内嵌有序 case_ids（YAML 无需 through 表），
  执行按各用例编译产物的 pytest nodeid 顺序展开；
- AppTestExecution + Celery 回写 → 复用 runner.ExecutionManager，套件统计在读时惰性同步。

持久化走 api_testing.yaml_store.YamlStore（data_dir 参数化到 config/app_testing/）。
"""
import os
import re
import time

from flask import Blueprint, jsonify, request

from web_platform import runner
from web_platform.app_testing import codegen
from web_platform.api_testing.yaml_store import YamlStore
from web_platform.runtime_config import BASE_DIR, list_devices_conf_files

bp = Blueprint('app_testing', __name__, url_prefix='/app-testing')

DATA_DIR = os.path.join(BASE_DIR, 'config', 'app_testing')
projects_store = YamlStore('projects', data_dir=DATA_DIR)
cases_store = YamlStore('cases', data_dir=DATA_DIR)
suites_store = YamlStore('suites', data_dir=DATA_DIR)


def _ok(**payload):
    return jsonify(dict({'ok': True}, **payload))


def _bad(msg, code=400):
    return jsonify({'ok': False, 'msg': msg}), code


def _now():
    return int(time.time())


def _element_names(elements_file):
    """指定元素库文件里的元素名集合（数据与定位器同一份，来自 element_manager）"""
    from web_platform import element_manager
    return {e['name'] for e in element_manager.list_elements()
            if e.get('file') == elements_file}


def _element_files():
    from web_platform import element_manager
    return element_manager.list_element_files()


def _clean_steps(steps, elements_file):
    """校验并规整步骤列表（[{type, element, param, desc}]）：类型词表/元素存在性/参数完备性"""
    if steps is None:
        return [], ''
    if not isinstance(steps, list):
        return None, 'steps 必须是列表'
    err = codegen.validate_steps(steps)
    if err:
        return None, err
    names = _element_names(elements_file)
    out = []
    for s in steps:
        t = s.get('type')
        el = str(s.get('element') or '').strip()
        if el and names and el not in names:
            return None, '元素「%s」不在元素文件 %s 里（请先在元素定位器/元素管理中采集）' % (el, elements_file)
        out.append({'type': t,
                    'element': el,
                    'param': str(s.get('param') or '').strip(),
                    'desc': str(s.get('desc') or '').strip()[:100]})
    return out, ''


def _clean_project_id(val):
    """项目归属校验：空 = 未分组（兼容旧数据）；非空必须是已存在项目 id。返回 (project_id, err)"""
    if val in (None, ''):
        return None, ''
    try:
        pid = int(val)
    except (TypeError, ValueError):
        return None, '所属项目不合法: %r' % (val,)
    if not projects_store.get(pid):
        return None, '所属项目不存在: #%s' % pid
    return pid, ''


def _clean_case_body(d, cid=None):
    """校验创建/更新请求体，返回 (payload, err)。cid 仅删除旧产物时用（由调用方处理）"""
    name = (d.get('name') or '').strip()
    if not name:
        return None, '用例名称不能为空'
    project_id, err = _clean_project_id(d.get('project_id'))
    if err:
        return None, err
    elements_file = (d.get('elements_file') or '').strip()
    if not elements_file:
        return None, '请选择元素文件（元素来自元素定位器采集的元素库）'
    if elements_file not in _element_files():
        return None, '元素文件不存在: %s' % elements_file
    steps, err = _clean_steps(d.get('steps'), elements_file)
    if err:
        return None, err
    return {'name': name[:100],
            'description': (d.get('description') or '').strip()[:500],
            'created_by': (d.get('created_by') or '').strip()[:40],
            'project_id': project_id,
            'elements_file': elements_file,
            'app_package': (d.get('app_package') or '').strip()[:120] or None,
            'app_activity': (d.get('app_activity') or '').strip()[:160] or None,
            'steps': steps}, ''


def _compile_and_store(case):
    """编译编排用例并把 nodeid 写回存储；失败时返回 (None, err)"""
    try:
        node = codegen.compile_case(case)
    except Exception as e:   # 编译失败要把原因带给用户（模板/元素/语法问题）
        return None, '用例代码生成失败: %s' % e
    cases_store.update(case['id'], {'node': node})
    return node, ''


def _suite_public(suite):
    """套件公开结构：case_ids → cases 明细（含实时步骤数），并惰性同步执行统计"""
    suite = _sync_suite_runs(suite)
    detail = []
    for cid in suite.get('case_ids') or []:
        c = cases_store.get(cid)
        if c:
            detail.append({'id': c['id'], 'name': c['name'], 'step_count': len(c.get('steps') or [])})
    suite['cases'] = detail
    return suite


# ---------------- 项目管理（对齐 testhub APP项目管理：状态/负责人/成员数/起止日期） ----------------
PROJECT_STATUS = ('未开始', '进行中', '已完成')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _clean_project_body(d, pid=None):
    """校验项目创建/更新体，返回 (payload, err)。pid=None 为创建（全部字段给默认值），
    更新时只收请求里出现的字段（部分更新）。"""
    d = d or {}
    payload = {}
    if 'name' in d or pid is None:
        name = (d.get('name') or '').strip()
        if not name:
            return None, '项目名称不能为空'
        if any(x['name'] == name and x['id'] != pid for x in projects_store.list()):
            return None, '项目名称已存在: %s' % name
        payload['name'] = name[:100]
    if 'description' in d or pid is None:
        payload['description'] = (d.get('description') or '').strip()[:500]
    if 'status' in d or pid is None:
        status = (d.get('status') or '进行中').strip()
        if status not in PROJECT_STATUS:
            return None, '项目状态不合法: %s（可选：%s）' % (status, '、'.join(PROJECT_STATUS))
        payload['status'] = status
    if 'owner' in d or pid is None:
        payload['owner'] = (d.get('owner') or '').strip()[:40]
    if 'member_count' in d or pid is None:
        try:
            members = int(d.get('member_count') or 1)
        except (TypeError, ValueError):
            return None, '成员数必须是数字'
        if members < 0:
            return None, '成员数不能为负数'
        payload['member_count'] = members
    for f, label in (('start_date', '开始日期'), ('end_date', '结束日期')):
        if f in d or pid is None:
            v = (d.get(f) or '').strip()
            if v and not _DATE_RE.match(v):
                return None, '%s 格式应为 YYYY-MM-DD' % label
            payload[f] = v or None
    return payload, ''


def _project_public(p):
    """项目公开结构：附用例数 / 套件数（列表页直接展示，不用前端再数一遍）"""
    p = dict(p)
    p['case_count'] = len(cases_store.list(project_id=p['id']))
    p['suite_count'] = len(suites_store.list(project_id=p['id']))
    return p


@bp.route('/api/projects', methods=['GET', 'POST'])
def api_projects():
    if request.method == 'GET':
        items = sorted(projects_store.list(), key=lambda p: -p['id'])
        return _ok(results=[_project_public(p) for p in items])
    d = request.get_json(force=True, silent=True) or {}
    payload, err = _clean_project_body(d)
    if err:
        return _bad(err)
    return _ok(project=projects_store.create(payload))


@bp.route('/api/projects/<int:pid>', methods=['GET', 'PUT', 'DELETE'])
def api_project_detail(pid):
    p = projects_store.get(pid)
    if not p:
        return _bad('项目不存在', 404)
    if request.method == 'GET':
        return _ok(project=_project_public(p))
    if request.method == 'DELETE':
        # 级联清理（testhub 是 DB 级联，这里手工保证）：项目下用例连生成文件一起删，
        # 其他套件里对这些用例的引用同步移除；挂在项目下的套件一并删除。
        case_ids = [c['id'] for c in cases_store.list(project_id=pid)]
        for cid in case_ids:
            codegen.remove_generated(cid)
            cases_store.delete(cid)
        removed_suites = 0
        for s in list(suites_store.list()):
            if s.get('project_id') == pid:
                suites_store.delete(s['id'])
                removed_suites += 1
            elif any(i in case_ids for i in (s.get('case_ids') or [])):
                suites_store.update(s['id'],
                                    {'case_ids': [i for i in s['case_ids'] if i not in case_ids]})
        projects_store.delete(pid)
        return _ok(msg='项目已删除（含 %d 个用例、%d 个套件）' % (len(case_ids), removed_suites),
                   removed_cases=len(case_ids), removed_suites=removed_suites)
    d = request.get_json(force=True, silent=True) or {}
    payload, err = _clean_project_body(d, pid=pid)
    if err:
        return _bad(err)
    return _ok(project=_project_public(projects_store.update(pid, payload)))


# ---------------- 用例编排 / 测试用例 ----------------
@bp.route('/api/cases', methods=['GET', 'POST'])
def api_cases():
    if request.method == 'GET':
        items = sorted(cases_store.list(), key=lambda c: -c['id'])
        return _ok(results=items)
    d = request.get_json(force=True, silent=True) or {}
    payload, err = _clean_case_body(d)
    if err:
        return _bad(err)
    case = cases_store.create(payload)
    node, err = _compile_and_store(case)
    if err:
        cases_store.delete(case['id'])          # 编译失败不落半成品
        return _bad(err)
    return _ok(case=cases_store.get(case['id']))


@bp.route('/api/cases/<int:cid>', methods=['GET', 'PUT', 'DELETE'])
def api_case_detail(cid):
    case = cases_store.get(cid)
    if not case:
        return _bad('用例不存在', 404)
    if request.method == 'GET':
        return _ok(case=case)
    if request.method == 'DELETE':
        codegen.remove_generated(cid)           # 只清理本模块生成的页面/用例文件
        cases_store.delete(cid)
        for s in suites_store.list():
            if cid in (s.get('case_ids') or []):
                suites_store.update(s['id'], {'case_ids': [i for i in s['case_ids'] if i != cid]})
        return _ok()
    d = request.get_json(force=True, silent=True) or {}
    payload, err = _clean_case_body(d)
    if err:
        return _bad(err)
    updated = cases_store.update(cid, payload)
    node, err = _compile_and_store(updated)
    if err:
        return _bad(err)
    return _ok(case=cases_store.get(cid))


@bp.route('/api/cases/<int:cid>/run', methods=['POST'])
def api_case_run(cid):
    """单用例执行：执行其编译产物的 pytest 节点，走 AppUI 执行链路"""
    case = cases_store.get(cid)
    if not case:
        return _bad('用例不存在', 404)
    node = case.get('node')
    if not node:
        return _bad('该用例还没有编译产物（旧版数据请重新保存一次）')
    return _run_nodes([node], (request.get_json(force=True, silent=True) or {}), case=case)


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
    project_id, err = _clean_project_id(d.get('project_id'))
    if err:
        return _bad(err)
    ids, err = _clean_suite_case_ids(d.get('case_ids'))
    if err:
        return _bad(err)
    return _ok(suite=_suite_public(suites_store.create({
        'name': name[:100], 'description': (d.get('description') or '').strip()[:500],
        'project_id': project_id,
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
    if 'project_id' in d:
        project_id, err = _clean_project_id(d.get('project_id'))
        if err:
            return _bad(err)
        patch['project_id'] = project_id
    if 'case_ids' in d:
        ids, err = _clean_suite_case_ids(d.get('case_ids'))
        if err:
            return _bad(err)
        patch['case_ids'] = ids
    return _ok(suite=_suite_public(suites_store.update(sid, patch)))


@bp.route('/api/suites/<int:sid>/run', methods=['POST'])
def api_suite_run(sid):
    """套件执行：按套件内用例顺序展开各自编译产物的节点（testhub AppTestSuiteViewSet.run）"""
    suite = suites_store.get(sid)
    if not suite:
        return _bad('套件不存在', 404)
    if not (suite.get('case_ids') or []):
        return _bad('该套件未包含任何测试用例')
    nodes, missing = [], []
    for cid in suite['case_ids']:
        c = cases_store.get(cid) or {}
        if c.get('node'):
            nodes.append(c['node'])
        else:
            missing.append('#%s %s' % (cid, c.get('name') or ''))
    if missing:
        return _bad('以下用例缺少编译产物（请重新保存）：%s' % '、'.join(missing))
    if not nodes:
        return _bad('套件内用例均无可执行节点')
    return _run_nodes(nodes, (request.get_json(force=True, silent=True) or {}), suite=suite)


def _clean_suite_case_ids(case_ids):
    """校验套件用例引用：必须是已存在用例 id 且去重，返回 (ids, err)"""
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


def _run_nodes(nodes, body, suite=None, case=None):
    """公共执行入口：冲突校验 → runner.manager.start_run → 回写套件执行状态"""
    running = runner.manager.running_task()
    if running:
        return _bad('已有任务在运行（Run %s），请等待完成或先停止' % running['run_id'], 409)
    if not nodes:
        return _bad('没有可执行的用例节点')
    conf_file = (body.get('conf_file') or '').strip() or \
        (list_devices_conf_files() or [''])[0]
    overrides = body.get('overrides') or {}
    ok, result = runner.manager.start_run(
        conf_file, nodes, overrides,
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
