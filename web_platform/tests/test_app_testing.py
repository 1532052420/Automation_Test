# -*- coding: utf-8 -*-
"""AppUI 用例编排 / 测试用例 / 测试套件（testhub 移植版）· 路由层测试

产品模型：用例 = 元素 + 页面操作的有序组合（步骤 [{type, element, param, desc}]），
保存时由 codegen 编译为框架三件套并回写 node。存储重定向临时目录，codegen 与 runner 全部打桩。
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest web_platform/tests/test_app_testing.py -q

用例清单（TC_ID 见各测试 docstring）：
- 编排/用例：创建正向 / 空名异常 / 元素文件缺失异常 / 元素不在库异常 / 缺参数异常 /
  类型非法异常 / 更新重排 / 404 / 删除级联清套件引用并清理生成文件
- 套件：创建正向 / case_ids 去重 / 引用不存在用例异常 / 排序更新 / 404
- 执行：套件按用例顺序展开 node / 用例执行 / 冲突 409 / 空套件 400 / 缺 node 拦截 / 惰性统计同步
- 项目：创建正向（含状态/负责人/成员数/起止日期）/ 空名 / 同名 / 更新 / 计数 / 404 /
  字段校验（状态词表 / 成员数数字 / 日期格式 / 部分更新）/
  删除级联（项目下用例连生成文件删除、项目套件删除、跨项目套件引用移除）/
  用例挂项目（正向 / 项目不存在拒绝）/ 套件挂项目（创建与更新）
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from web_platform.app_testing import routes as AT                 # noqa: E402
from web_platform.app_testing.routes import bp                    # noqa: E402

API = '/app-testing/api'
_EL_FILE = 'kuaigeLoginElements.py'
_STEPS = [{'type': 'click', 'element': 'btn_agree_privacy'},
          {'type': 'input', 'element': 'et_phone', 'param': '13800138000'}]


def _node(cid):
    return 'cases/app_ui/android/demoProject/test_orch%d.py::TestOrch%d::test_orch_%d' % (cid, cid, cid)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask 测试客户端：存储指向临时目录；元素库 / codegen / runner 全部打桩"""
    d = str(tmp_path / 'app_testing')
    os.makedirs(d, exist_ok=True)
    for inst in (AT.projects_store, AT.cases_store, AT.suites_store):
        monkeypatch.setattr(inst, 'path', os.path.join(d, '%s.yaml' % inst.name))
        if not os.path.exists(inst.path):
            inst._write({'meta': {'next_id': 1}, 'items': []})
    monkeypatch.setattr(AT, 'list_devices_conf_files', lambda: ['config/devices.conf'])
    monkeypatch.setattr(AT, '_element_files', lambda: [_EL_FILE])
    monkeypatch.setattr(AT, '_element_names', lambda f: {'btn_agree_privacy', 'et_phone', 'et_code'})
    monkeypatch.setattr(AT.codegen, 'compile_case',
                        lambda case: _node(case['id']))
    removed = []
    monkeypatch.setattr(AT.codegen, 'remove_generated', lambda cid: removed.append(cid))
    monkeypatch.setattr(AT.runner.manager, 'running_task', lambda: None)
    monkeypatch.setattr(AT.runner.manager, 'start_run',
                        lambda conf, nodes, overrides=None, owner='': (True, 'run-fake-1'))
    monkeypatch.setattr(AT.runner.manager, 'get_task', lambda rid: None)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.config['TESTING'] = True
    c = app.test_client()
    c.ext_removed = removed
    return c


def _mk_case(client, name='登录冒烟', steps=None, elements_file=_EL_FILE):
    r = client.post(API + '/cases', json={
        'name': name, 'description': '冒烟', 'created_by': 'tester',
        'elements_file': elements_file,
        'steps': steps if steps is not None else _STEPS,
    }).get_json()
    assert r['ok'], r
    return r['case']


def _mk_suite(client, case_ids, name='回归套件'):
    r = client.post(API + '/suites', json={'name': name, 'case_ids': case_ids}).get_json()
    assert r['ok'], r
    return r['suite']


def _mk_proj(client, name='快歌', description='快歌 App 回归', **extra):
    body = {'name': name, 'description': description, 'owner': 'tester'}
    body.update(extra)
    r = client.post(API + '/projects', json=body).get_json()
    assert r['ok'], r
    return r['project']


# ---------------- 用例编排 / 测试用例 ----------------
def test_case_create_ok(client):
    """TC_APP_ORCH_001 正向：创建用例，步骤规整落库且回写编译 node"""
    c = _mk_case(client)
    assert c['id'] and c['name'] == '登录冒烟'
    assert c['steps'] == [{'type': 'click', 'element': 'btn_agree_privacy', 'param': '', 'desc': ''},
                          {'type': 'input', 'element': 'et_phone', 'param': '13800138000', 'desc': ''}]
    assert c['elements_file'] == _EL_FILE
    assert c['node'] == _node(c['id'])


def test_case_create_empty_name(client):
    """TC_APP_ORCH_002 异常：空名称拒绝"""
    r = client.post(API + '/cases', json={'name': '  ', 'steps': []}).get_json()
    assert not r['ok'] and '名称' in r['msg']


def test_case_create_missing_elements_file(client):
    """TC_APP_ORCH_003 异常：未选 / 元素文件不存在拒绝"""
    r1 = client.post(API + '/cases', json={'name': 'x', 'steps': _STEPS}).get_json()
    assert not r1['ok'] and '元素文件' in r1['msg']
    r2 = client.post(API + '/cases', json={
        'name': 'x', 'elements_file': 'nope.py', 'steps': _STEPS}).get_json()
    assert not r2['ok'] and '不存在' in r2['msg']


def test_case_create_element_not_in_file(client):
    """TC_APP_ORCH_004 异常：元素不在所选元素文件里拒绝"""
    r = client.post(API + '/cases', json={
        'name': 'x', 'elements_file': _EL_FILE,
        'steps': [{'type': 'click', 'element': 'tab_home'}]}).get_json()
    assert not r['ok'] and '不在元素文件' in r['msg']


def test_case_create_step_validation(client):
    """TC_APP_ORCH_005 异常：非法类型 / 需参数未填 / 坐标格式错误拒绝"""
    r1 = client.post(API + '/cases', json={
        'name': 'x', 'elements_file': _EL_FILE,
        'steps': [{'type': 'hack', 'element': 'et_phone'}]}).get_json()
    assert not r1['ok'] and '不合法' in r1['msg']
    r2 = client.post(API + '/cases', json={
        'name': 'x', 'elements_file': _EL_FILE,
        'steps': [{'type': 'input', 'element': 'et_phone'}]}).get_json()
    assert not r2['ok'] and '参数' in r2['msg']
    r3 = client.post(API + '/cases', json={
        'name': 'x', 'elements_file': _EL_FILE,
        'steps': [{'type': 'tap', 'param': 'abc'}]}).get_json()
    assert not r3['ok'] and '坐标' in r3['msg']


def test_case_update_reorder(client):
    """TC_APP_ORCH_006 正向（边界）：更新步骤实现重排，顺序持久化并重新编译"""
    c = _mk_case(client)
    r = client.put(API + '/cases/%d' % c['id'], json={
        'name': c['name'], 'elements_file': _EL_FILE,
        'steps': [{'type': 'sleep', 'param': '1'}, {'type': 'click', 'element': 'et_phone'}]}).get_json()
    assert r['ok']
    assert [s['type'] for s in r['case']['steps']] == ['sleep', 'click']


def test_case_404(client):
    """TC_APP_ORCH_007 异常：不存在的用例返回 404"""
    assert client.get(API + '/cases/999').status_code == 404


def test_case_delete_cascades_suite(client):
    """TC_APP_ORCH_008 正向（级联）：删除用例后清理生成文件、套件引用同步移除"""
    c1 = _mk_case(client, name='A')
    c2 = _mk_case(client, name='B')
    s = _mk_suite(client, [c1['id'], c2['id']])
    assert client.delete(API + '/cases/%d' % c1['id']).get_json()['ok']
    assert client.ext_removed == [c1['id']]          # 生成文件按标记清理
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['case_ids'] == [c2['id']]


def test_case_attach_project(client):
    """TC_APP_ORCH_009 正向：用例创建时挂项目；project_id 不存在拒绝"""
    p = _mk_proj(client)
    c = _mk_case(client, name='快歌登录')
    r = client.put(API + '/cases/%d' % c['id'], json={
        'name': '快歌登录', 'project_id': p['id'], 'elements_file': _EL_FILE,
        'steps': _STEPS}).get_json()
    assert r['ok'] and r['case']['project_id'] == p['id']
    r2 = client.post(API + '/cases', json={
        'name': 'x', 'project_id': 42, 'elements_file': _EL_FILE, 'steps': _STEPS}).get_json()
    assert not r2['ok'] and '所属项目不存在' in r2['msg']


# ---------------- 测试套件 ----------------
def test_suite_create_ok(client):
    """TC_APP_SUITE_001 正向：创建套件，cases 明细带实时步骤数"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    assert s['case_ids'] == [c['id']]
    assert s['cases'][0] == {'id': c['id'], 'name': '登录冒烟', 'step_count': 2}
    assert s['execution_status'] == 'NOT_RUN'


def test_suite_create_dedup(client):
    """TC_APP_SUITE_002 边界：重复引用同一用例自动去重"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id'], c['id']])
    assert s['case_ids'] == [c['id']]


def test_suite_create_missing_case(client):
    """TC_APP_SUITE_003 异常：引用不存在的用例拒绝"""
    r = client.post(API + '/suites', json={'name': 'x', 'case_ids': [42]}).get_json()
    assert not r['ok'] and '不存在' in r['msg']


def test_suite_update_reorder(client):
    """TC_APP_SUITE_004 正向：更新 case_ids 顺序即编排排序"""
    c1 = _mk_case(client, name='A')
    c2 = _mk_case(client, name='B')
    s = _mk_suite(client, [c1['id'], c2['id']])
    r = client.put(API + '/suites/%d' % s['id'], json={'case_ids': [c2['id'], c1['id']]}).get_json()
    assert r['ok'] and r['suite']['case_ids'] == [c2['id'], c1['id']]


def test_suite_404(client):
    """TC_APP_SUITE_005 异常：不存在的套件返回 404"""
    assert client.get(API + '/suites/999').status_code == 404


# ---------------- 执行 ----------------
def test_suite_run_expands_case_nodes_in_order(client, monkeypatch):
    """TC_APP_RUN_001 正向：套件执行按用例顺序展开各自编译 node 传给 runner"""
    c1 = _mk_case(client, name='A')
    c2 = _mk_case(client, name='B')
    s = _mk_suite(client, [c1['id'], c2['id']])
    seen = {}
    monkeypatch.setattr(AT.runner.manager, 'start_run',
                        lambda conf, nodes, overrides=None, owner='': seen.update(
                            conf=conf, nodes=nodes) or (True, 'run-9'))
    monkeypatch.setattr(AT.runner.manager, 'get_task', lambda rid: {
        'run_id': rid, 'status': 'RUNNING', 'total': 0, 'passed': 0, 'failed': 0, 'error': 0})
    r = client.post(API + '/suites/%d/run' % s['id'], json={'conf_file': 'config/d.conf'}).get_json()
    assert r['ok'] and r['run_id'] == 'run-9'
    assert seen['nodes'] == [_node(c1['id']), _node(c2['id'])]
    assert seen['conf'] == 'config/d.conf'
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['execution_status'] == 'RUNNING' and suite['last_run_id'] == 'run-9'
    assert suite['runs'][0]['run_id'] == 'run-9'


def test_case_run_uses_compiled_node(client, monkeypatch):
    """TC_APP_RUN_002 正向：单用例执行其编译产物节点"""
    c = _mk_case(client)
    seen = {}
    monkeypatch.setattr(AT.runner.manager, 'start_run',
                        lambda conf, nodes, overrides=None, owner='': seen.update(nodes=nodes) or (True, 'r'))
    r = client.post(API + '/cases/%d/run' % c['id'], json={}).get_json()
    assert r['ok'] and seen['nodes'] == [_node(c['id'])]


def test_suite_run_missing_node(client, monkeypatch):
    """TC_APP_RUN_003 异常：套件内有用例缺编译产物（旧数据）时拦截并列出"""
    c = _mk_case(client)
    AT.cases_store.update(c['id'], {'node': None})
    r = client.post(API + '/suites/%d/run' % _mk_suite(client, [c['id']])['id'], json={})
    assert r.status_code == 400 and '重新保存' in r.get_json()['msg']


def test_suite_run_conflict(client, monkeypatch):
    """TC_APP_RUN_004 异常：已有任务运行时返回 409"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    monkeypatch.setattr(AT.runner.manager, 'running_task',
                        lambda: {'run_id': 'run-busy'})
    r = client.post(API + '/suites/%d/run' % s['id'], json={})
    assert r.status_code == 409


def test_suite_run_empty(client):
    """TC_APP_RUN_005 异常：空套件（未选用例）拒绝执行"""
    s = _mk_suite(client, [])
    r = client.post(API + '/suites/%d/run' % s['id'], json={})
    assert r.status_code == 400


def test_suite_stats_synced_on_read(client, monkeypatch):
    """TC_APP_RUN_006 正向（惰性同步）：run 结束后，读套件时统计回写（替代 Celery 回写）"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    client.post(API + '/suites/%d/run' % s['id'], json={})
    monkeypatch.setattr(AT.runner.manager, 'get_task', lambda rid: {
        'run_id': rid, 'status': 'PASSED', 'total': 3, 'passed': 2, 'failed': 1, 'error': 0})
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['execution_status'] == 'COMPLETED'
    assert suite['execution_result'] == 'PASSED'
    assert suite['passed_count'] == 2 and suite['failed_count'] == 1


# ---------------- 项目管理（统一管理测试项目） ----------------
def test_project_create_ok_and_list_counts(client):
    """TC_APP_PROJ_001 正向：创建项目（全字段），列表带用例数 / 套件数统计"""
    p = _mk_proj(client, status='未开始', owner='qa1', member_count=3,
                 start_date='2026-09-01', end_date='2026-09-30')
    assert p['id'] and p['name'] == '快歌' and p['owner'] == 'qa1'
    assert p['status'] == '未开始' and p['member_count'] == 3
    assert p['start_date'] == '2026-09-01' and p['end_date'] == '2026-09-30'
    _mk_case(client, name='快歌登录')
    r = client.put(API + '/cases/1', json={          # 把用例挂到项目下
        'name': '快歌登录', 'project_id': p['id'], 'elements_file': _EL_FILE,
        'steps': _STEPS}).get_json()
    assert r['ok']
    s = _mk_suite(client, [], name='快歌回归')
    client.put(API + '/suites/%d' % s['id'], json={'project_id': p['id']}).get_json()
    items = client.get(API + '/projects').get_json()['results']
    mine = next(x for x in items if x['id'] == p['id'])
    assert mine['case_count'] == 1 and mine['suite_count'] == 1


def test_project_create_validations(client):
    """TC_APP_PROJ_002 异常/边界：空名拒绝；同名拒绝"""
    r1 = client.post(API + '/projects', json={'name': '  '}).get_json()
    assert not r1['ok'] and '名称' in r1['msg']
    _mk_proj(client, name='快歌')
    r2 = client.post(API + '/projects', json={'name': '快歌'}).get_json()
    assert not r2['ok'] and '已存在' in r2['msg']


def test_project_update_and_404(client):
    """TC_APP_PROJ_003 正向/异常：更新名称与描述；改名撞同名拒绝；不存在 404"""
    p1 = _mk_proj(client, name='快歌')
    p2 = _mk_proj(client, name='慢歌')
    r = client.put(API + '/projects/%d' % p1['id'], json={
        'name': '快歌App', 'description': '改名'}).get_json()
    assert r['ok'] and r['project']['name'] == '快歌App'
    r2 = client.put(API + '/projects/%d' % p1['id'], json={'name': '慢歌'}).get_json()
    assert not r2['ok'] and '已存在' in r2['msg']
    assert client.get(API + '/projects/999').status_code == 404
    assert client.put(API + '/projects/999', json={'name': 'x'}).status_code == 404


def test_project_delete_cascades(client):
    """TC_APP_PROJ_004 正向（级联）：删项目 → 项目下用例连生成文件删除、
    项目下套件删除、跨项目套件对该项目用例的引用移除、未关联数据不受影响"""
    p = _mk_proj(client)
    p2 = _mk_proj(client, name='其他项目')
    c_in = _mk_case(client, name='快歌登录')           # 项目内用例
    c_out = _mk_case(client, name='独立用例')          # 项目外用例
    for c in (c_in, c_out):
        client.put(API + '/cases/%d' % c['id'], json={
            'name': c['name'], 'project_id': p['id'] if c is c_in else p2['id'],
            'elements_file': _EL_FILE, 'steps': _STEPS}).get_json()
    s_proj = _mk_suite(client, [c_in['id']], name='项目套件')
    client.put(API + '/suites/%d' % s_proj['id'], json={'project_id': p['id']}).get_json()
    s_cross = _mk_suite(client, [c_in['id'], c_out['id']], name='跨项目套件')   # 挂 p2，引用 c_in
    client.put(API + '/suites/%d' % s_cross['id'], json={'project_id': p2['id']}).get_json()

    r = client.delete(API + '/projects/%d' % p['id']).get_json()
    assert r['ok'] and r['removed_cases'] == 1 and r['removed_suites'] == 1
    assert client.ext_removed == [c_in['id']]        # 项目内用例生成文件被清理
    assert client.get(API + '/cases/%d' % c_in['id']).status_code == 404
    assert client.get(API + '/cases/%d' % c_out['id']).status_code == 200
    assert client.get(API + '/suites/%d' % s_proj['id']).status_code == 404   # 项目套件随之删除
    cross = client.get(API + '/suites/%d' % s_cross['id']).get_json()['suite']
    assert cross['case_ids'] == [c_out['id']]        # 跨项目套件保留并移除失效引用
    assert client.get(API + '/projects/%d' % p['id']).status_code == 404


def test_suite_attach_project(client):
    """TC_APP_PROJ_005 正向/异常：套件创建与更新挂项目；项目不存在拒绝"""
    p = _mk_proj(client)
    s = _mk_suite(client, [], name='回归套件')
    r = client.put(API + '/suites/%d' % s['id'], json={'project_id': p['id']}).get_json()
    assert r['ok'] and r['suite']['project_id'] == p['id']
    r2 = client.post(API + '/suites', json={'name': 'x', 'project_id': 42, 'case_ids': []}).get_json()
    assert not r2['ok'] and '所属项目不存在' in r2['msg']


def test_project_field_validation(client):
    """TC_APP_PROJ_006 异常/边界（对齐 testhub 字段）：状态/成员数/日期校验；部分更新只改传入字段"""
    p = _mk_proj(client)
    r1 = client.put(API + '/projects/%d' % p['id'], json={'status': '已上线'}).get_json()
    assert not r1['ok'] and '状态不合法' in r1['msg']
    r2 = client.put(API + '/projects/%d' % p['id'], json={'member_count': 'abc'}).get_json()
    assert not r2['ok'] and '成员数' in r2['msg']
    r3 = client.put(API + '/projects/%d' % p['id'], json={'start_date': '09-01'}).get_json()
    assert not r3['ok'] and 'YYYY-MM-DD' in r3['msg']
    r4 = client.put(API + '/projects/%d' % p['id'], json={'status': '已完成'}).get_json()
    assert r4['ok'] and r4['project']['status'] == '已完成'
    assert r4['project']['name'] == p['name']          # 部分更新不影响其他字段
    assert r4['project']['owner'] == 'tester'


def test_suite_stats_sync_run_lost(client, monkeypatch):
    """TC_APP_RUN_007 异常（边界）：执行记录丢失时套件标记 ERROR，不卡 RUNNING"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    client.post(API + '/suites/%d/run' % s['id'], json={})
    # get_task 已打桩返回 None（记录丢失）
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['execution_status'] == 'ERROR'
    assert suite['runs'][0]['status'] == 'UNKNOWN'
