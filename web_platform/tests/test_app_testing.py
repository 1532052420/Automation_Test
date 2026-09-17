# -*- coding: utf-8 -*-
"""AppUI 用例编排 / 测试用例 / 测试套件（testhub 移植版）· 路由层测试

覆盖 AAA 与全路径：正向 → 边界 → 异常。存储重定向临时目录，runner 全部打桩（不起真实执行）。
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest web_platform/tests/test_app_testing.py -q

用例清单（TC_ID 见各测试 docstring）：
- 编排/用例：创建正向 / 空名异常 / 非法节点异常 / 更新排序 / 404 / 删除级联清套件引用
- 套件：创建正向 / case_ids 去重 / 引用不存在用例异常 / 排序更新 / 404
- 执行：套件按序展开节点 / 用例执行 / 冲突 409 / 空套件 400 / 惰性统计同步（完成/丢失）
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from web_platform.app_testing import routes as AT                 # noqa: E402
from web_platform.app_testing.routes import bp                    # noqa: E402

API = '/app-testing/api'

_N1 = 'cases/app_ui/android/demoProject/test_login.py::TestLogin::test_login_ok'
_N2 = 'cases/app_ui/android/demoProject/test_login.py::TestLogin::test_login_bad'
_N3 = 'cases/app_ui/android/demoProject/test_home.py::TestHome::test_home_load'


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask 测试客户端：存储指向临时目录，runner 与 conf 扫描打桩"""
    d = str(tmp_path / 'app_testing')
    os.makedirs(d, exist_ok=True)
    for inst in (AT.cases_store, AT.suites_store):
        monkeypatch.setattr(inst, 'path', os.path.join(d, '%s.yaml' % inst.name))
        if not os.path.exists(inst.path):
            inst._write({'meta': {'next_id': 1}, 'items': []})
    monkeypatch.setattr(AT, 'list_devices_conf_files', lambda: ['config/devices.conf'])
    monkeypatch.setattr(AT.runner.manager, 'running_task', lambda: None)
    monkeypatch.setattr(AT.runner.manager, 'start_run',
                        lambda conf, nodes, overrides=None, owner='': (True, 'run-fake-1'))
    monkeypatch.setattr(AT.runner.manager, 'get_task', lambda rid: None)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.config['TESTING'] = True
    return app.test_client()


def _mk_case(client, name='登录冒烟', steps=None):
    r = client.post(API + '/cases', json={
        'name': name, 'description': '冒烟', 'created_by': 'tester',
        'steps': steps if steps is not None else [{'node': _N1, 'name': '登录成功'}],
    }).get_json()
    assert r['ok'], r
    return r['case']


def _mk_suite(client, case_ids, name='回归套件'):
    r = client.post(API + '/suites', json={'name': name, 'case_ids': case_ids}).get_json()
    assert r['ok'], r
    return r['suite']


# ---------------- 用例编排 / 测试用例 ----------------
def test_case_create_ok(client):
    """TC_APP_ORCH_001 正向：创建用例，字段完整落库"""
    c = _mk_case(client)
    assert c['id'] and c['name'] == '登录冒烟'
    assert c['steps'][0]['node'] == _N1
    assert c['created_by'] == 'tester'


def test_case_create_empty_name(client):
    """TC_APP_ORCH_002 异常：空名称拒绝"""
    r = client.post(API + '/cases', json={'name': '  ', 'steps': []}).get_json()
    assert not r['ok'] and '名称' in r['msg']


def test_case_create_bad_node(client):
    """TC_APP_ORCH_003 异常：非法 pytest 节点（防注入）拒绝"""
    r = client.post(API + '/cases', json={
        'name': 'x', 'steps': [{'node': '-p no:cacheprovider', 'name': '注入'}]}).get_json()
    assert not r['ok'] and '不合法' in r['msg']


def test_case_update_reorder(client):
    """TC_APP_ORCH_004 正向（边界）：更新步骤实现重排，顺序持久化"""
    c = _mk_case(client, steps=[{'node': _N1, 'name': 'a'}, {'node': _N2, 'name': 'b'}])
    r = client.put(API + '/cases/%d' % c['id'], json={
        'steps': [{'node': _N2, 'name': 'b'}, {'node': _N1, 'name': 'a'}]}).get_json()
    assert r['ok']
    assert [s['node'] for s in r['case']['steps']] == [_N2, _N1]


def test_case_404(client):
    """TC_APP_ORCH_005 异常：不存在的用例返回 404"""
    assert client.get(API + '/cases/999').status_code == 404


def test_case_delete_cascades_suite(client):
    """TC_APP_ORCH_006 正向（级联）：删除用例后，套件引用同步移除"""
    c1 = _mk_case(client, name='A')
    c2 = _mk_case(client, name='B', steps=[{'node': _N2, 'name': 'b'}])
    s = _mk_suite(client, [c1['id'], c2['id']])
    assert client.delete(API + '/cases/%d' % c1['id']).get_json()['ok']
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['case_ids'] == [c2['id']]


# ---------------- 测试套件 ----------------
def test_suite_create_ok(client):
    """TC_APP_SUITE_001 正向：创建套件，cases 明细带出"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    assert s['case_ids'] == [c['id']]
    assert s['cases'][0]['name'] == '登录冒烟'
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
def test_suite_run_flattens_nodes_in_order(client, monkeypatch):
    """TC_APP_RUN_001 正向：套件执行按「用例顺序 × 步骤顺序」展开节点传给 runner"""
    c1 = _mk_case(client, name='A', steps=[{'node': _N1, 'name': 'a1'}, {'node': _N2, 'name': 'a2'}])
    c2 = _mk_case(client, name='B', steps=[{'node': _N3, 'name': 'b1'}])
    s = _mk_suite(client, [c1['id'], c2['id']])
    seen = {}
    monkeypatch.setattr(AT.runner.manager, 'start_run',
                        lambda conf, nodes, overrides=None, owner='': seen.update(
                            conf=conf, nodes=nodes) or (True, 'run-9'))
    monkeypatch.setattr(AT.runner.manager, 'get_task', lambda rid: {
        'run_id': rid, 'status': 'RUNNING', 'total': 0, 'passed': 0, 'failed': 0, 'error': 0})
    r = client.post(API + '/suites/%d/run' % s['id'], json={'conf_file': 'config/d.conf'}).get_json()
    assert r['ok'] and r['run_id'] == 'run-9'
    assert seen['nodes'] == [_N1, _N2, _N3]
    assert seen['conf'] == 'config/d.conf'
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['execution_status'] == 'RUNNING' and suite['last_run_id'] == 'run-9'
    assert suite['runs'][0]['run_id'] == 'run-9'


def test_case_run_uses_case_steps(client, monkeypatch):
    """TC_APP_RUN_002 正向：单用例执行只展开该用例的步骤节点"""
    c = _mk_case(client, steps=[{'node': _N1, 'name': 'a'}, {'node': _N3, 'name': 'b'}])
    seen = {}
    monkeypatch.setattr(AT.runner.manager, 'start_run',
                        lambda conf, nodes, overrides=None, owner='': seen.update(nodes=nodes) or (True, 'r'))
    r = client.post(API + '/cases/%d/run' % c['id'], json={}).get_json()
    assert r['ok'] and seen['nodes'] == [_N1, _N3]


def test_suite_run_conflict(client, monkeypatch):
    """TC_APP_RUN_003 异常：已有任务运行时返回 409"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    monkeypatch.setattr(AT.runner.manager, 'running_task',
                        lambda: {'run_id': 'run-busy'})
    r = client.post(API + '/suites/%d/run' % s['id'], json={})
    assert r.status_code == 409


def test_suite_run_empty(client):
    """TC_APP_RUN_004 异常：空套件（未选用例）拒绝执行"""
    s = _mk_suite(client, [])
    r = client.post(API + '/suites/%d/run' % s['id'], json={})
    assert r.status_code == 400


def test_suite_stats_synced_on_read(client, monkeypatch):
    """TC_APP_RUN_005 正向（惰性同步）：run 结束后，读套件时统计回写（替代 Celery 回写）"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    client.post(API + '/suites/%d/run' % s['id'], json={})
    monkeypatch.setattr(AT.runner.manager, 'get_task', lambda rid: {
        'run_id': rid, 'status': 'PASSED', 'total': 3, 'passed': 2, 'failed': 1, 'error': 0})
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['execution_status'] == 'COMPLETED'
    assert suite['execution_result'] == 'PASSED'
    assert suite['passed_count'] == 2 and suite['failed_count'] == 1


def test_suite_stats_sync_run_lost(client, monkeypatch):
    """TC_APP_RUN_006 异常（边界）：执行记录丢失时套件标记 ERROR，不卡 RUNNING"""
    c = _mk_case(client)
    s = _mk_suite(client, [c['id']])
    client.post(API + '/suites/%d/run' % s['id'], json={})
    # get_task 已打桩返回 None（记录丢失）
    suite = client.get(API + '/suites/%d' % s['id']).get_json()['suite']
    assert suite['execution_status'] == 'ERROR'
    assert suite['runs'][0]['status'] == 'UNKNOWN'
