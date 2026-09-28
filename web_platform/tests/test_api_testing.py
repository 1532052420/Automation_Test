# -*- coding: utf-8 -*-
"""接口测试模块（testhub 移植版）· 存储层/执行器/路由/调度 测试

覆盖 AAA 与全路径：正向 → 边界 → 异常。存储层指向临时目录，不碰真实 YAML 数据。
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest web_platform/tests/ -q
"""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from web_platform.api_testing import yaml_store as store          # noqa: E402
from web_platform.api_testing import executor, scheduler          # noqa: E402
from web_platform.api_testing.routes import bp                    # noqa: E402

API = '/api-testing/api'      # 蓝图前缀 + api 子路径
PFX = '/api-testing'          # mock 服务前缀


@pytest.fixture()
def tmp_stores(tmp_path, monkeypatch):
    """全部仓库重定向到临时目录（隔离真实数据）"""
    d = str(tmp_path / 'api_testing')
    os.makedirs(d, exist_ok=True)
    for name in ('projects', 'collections', 'requests', 'environments', 'histories',
                 'suites', 'executions', 'tasks', 'task_logs', 'settings'):
        inst = getattr(store, name)
        monkeypatch.setattr(inst, 'path', os.path.join(d, '%s.yaml' % name))
        if not os.path.exists(inst.path):
            inst._write({'meta': {'next_id': 1}, 'items': []})
    yield store


@pytest.fixture()
def client(tmp_stores):
    """Flask 测试客户端（只挂 api_testing 蓝图）"""
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.config['TESTING'] = True
    return app.test_client()


def _mk_request(client, name='回显测试', url=None, assertions=None):
    p = client.post(API + '/projects', json={'name': '演示项目'}).get_json()['data']
    r = client.post(API + '/requests', json={
        'name': name, 'method': 'POST',
        'url': url or 'http://127.0.0.1:8080/api-testing/mock/echo',
        'headers': [{'key': 'X-Trace', 'value': 'hdr-{{token}}', 'enabled': True}],
        'params': {'from': 'suite'},
        'body': {'type': 'json', 'data': {'username': 'admin', 'password': '123456'}},
        'assertions': assertions or [{'name': '状态码', 'type': 'status_code', 'expected': 200}],
        'project_id': p['id'],
    }).get_json()
    assert r['ok'], r
    return p, r['data']


# ---------------- 存储层 ----------------
class TestYamlStore:
    def test_create_get_update_delete(self, tmp_stores):
        item = tmp_stores.projects.create({'name': 'P1'})
        assert item['id'] == 1
        assert tmp_stores.projects.get(1)['name'] == 'P1'
        tmp_stores.projects.update(1, {'name': 'P1改'})
        assert tmp_stores.projects.get(1)['name'] == 'P1改'
        assert tmp_stores.projects.delete(1) is True
        assert tmp_stores.projects.get(1) is None

    def test_id_auto_increment_persisted(self, tmp_stores):
        a = tmp_stores.projects.create({'name': 'A'})
        b = tmp_stores.projects.create({'name': 'B'})
        assert b['id'] == a['id'] + 1

    def test_list_condition_filter(self, tmp_stores):
        tmp_stores.tasks.create({'name': 'T1', 'status': 'ACTIVE'})
        tmp_stores.tasks.create({'name': 'T2', 'status': 'PAUSED'})
        assert [t['name'] for t in tmp_stores.tasks.list(status='ACTIVE')] == ['T1']

    def test_delete_missing_returns_false(self, tmp_stores):
        assert tmp_stores.projects.delete(999) is False


# ---------------- 执行器 ----------------
class _FakeResp:
    def __init__(self, status=200, text='{"code": 0}', headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {'content-type': 'application/json'}


class TestAssertions:
    def test_status_code_pass(self):
        r = executor.execute_assertions(_FakeResp(200), [{'type': 'status_code', 'expected': 200}])
        assert r[0]['passed'] is True and r[0]['actual'] == 200

    def test_status_code_fail(self):
        r = executor.execute_assertions(_FakeResp(500), [{'type': 'status_code', 'expected': 200}])
        assert r[0]['passed'] is False

    def test_json_path(self):
        r = executor.execute_assertions(_FakeResp(text='{"code": 0, "data": {"name": "管理员"}}'),
                                        [{'type': 'json_path', 'json_path': '$.data.name', 'expected': '管理员'}])
        assert r[0]['passed'] is True and r[0]['actual'] == '管理员'

    def test_json_path_not_json(self):
        resp = _FakeResp(text='html page', headers={'content-type': 'text/html'})
        r = executor.execute_assertions(resp, [{'type': 'json_path', 'json_path': '$.a', 'expected': '1'}])
        assert r[0]['passed'] is False and '不是JSON' in (r[0]['error'] or '')

    def test_contains_and_header_and_time(self):
        resp = _FakeResp(text='hello world', headers={'content-type': 'text/plain', 'X-Flag': 'on'})
        rs = executor.execute_assertions(resp, [
            {'type': 'contains', 'expected': 'world'},
            {'type': 'header', 'header_name': 'X-Flag', 'expected_value': 'on'},
            {'type': 'response_time', 'actual_time': 12.5, 'expected': 100},
        ])
        assert all(x['passed'] for x in rs)

    def test_exception_becomes_error(self):
        r = executor.execute_assertions(_FakeResp(), [{'type': 'no_such_type', 'expected': 1}])
        assert r[0]['passed'] is False


class TestSendRequest:
    def test_send_against_live_mock(self, client):
        """真实 HTTP：打平台内置 mock/echo（Flask test client 不走网络？——send_request 用 requests，
        需要活服务；此用例在完整平台起服务后由 test_api_testing_live.py 覆盖，这里验证参数组装路径"""
        # 仅验证 overrides/body 组装不抛异常（mock 服务不可达时错误落入历史）
        p, r = _mk_request(client, url='http://127.0.0.1:9/api-testing/mock/echo')
        hist = executor.send_request(r, None, {'executed_by': 'test'})
        assert hist['error_message'] or hist['status_code']
        assert hist['executed_by'] == 'test'

    def test_params_list_format_enabled_flag(self, monkeypatch):
        """params 新数组格式 [{key,value,description,enabled}]：只发启用项，description 不入参；
        旧对象格式仍兼容"""
        captured = {}

        class _FakeResp:
            status_code = 200
            headers = {'content-type': 'application/json'}
            elapsed = None
            text = '{}'
            def json(self): return {}

        class _FakeSession:
            def request(self, **kw):
                captured.update(kw)
                return _FakeResp()

        monkeypatch.setattr(executor, '_session_for', lambda url: _FakeSession())
        req = {'method': 'GET', 'url': 'http://127.0.0.1:9/x', 'headers': [], 'body': None,
               'assertions': [],
               'params': [
                   {'key': 'a', 'value': '1', 'description': '页码', 'enabled': True},
                   {'key': 'b', 'value': '2', 'description': '停用项', 'enabled': False},
               ]}
        executor.send_request(req, None, {})
        assert captured['params'] == {'a': '1'}          # 停用项不发，描述不进 query
        # 旧 dict 格式
        req2 = dict(req, params={'k': 'v'})
        captured.clear()
        executor.send_request(req2, None, {})
        assert captured['params'] == {'k': 'v'}


# ---------------- 路由（CRUD + mock + 调度闭环） ----------------
class TestRoutes:
    def test_project_crud(self, client):
        p = client.post(API + '/projects', json={'name': 'P'}).get_json()['data']
        assert client.put(API + '/projects/%d' % p['id'], json={'name': 'P2'}).get_json()['data']['name'] == 'P2'
        assert client.delete(API + '/projects/%d' % p['id']).get_json()['ok'] is True

    def test_project_name_required(self, client):
        r = client.post(API + '/projects', json={'name': ' '})
        assert r.status_code == 400

    def test_request_url_validation(self, client):
        client.post(API + '/projects', json={'name': 'P'})
        r = client.post(API + '/requests', json={'name': 'X', 'url': 'ftp://x', 'method': 'GET'})
        assert r.status_code == 400 and 'http' in r.get_json()['msg']

    def test_mock_echo_and_login(self, client):
        r = client.post(PFX + '/mock/echo?q=1', json={'a': 1})
        d = r.get_json()
        assert d['ok'] and d['args']['q'] == '1' and d['body'] == {'a': 1}
        ok = client.post(PFX + '/mock/login', json={'username': 'admin', 'password': '123456'}).get_json()
        bad = client.post(PFX + '/mock/login', json={'username': 'x', 'password': 'y'}).get_json()
        assert ok['code'] == 0 and bad['code'] == 1001

    def test_environment_activate_semantics(self, client):
        a = client.post(API + '/environments', json={'name': 'A', 'is_active': True}).get_json()['data']
        b = client.post(API + '/environments', json={'name': 'B', 'is_active': True}).get_json()['data']
        envs = client.get(API + '/environments').get_json()['data']
        active = [e for e in envs if e['is_active']]
        assert len(active) == 1 and active[0]['name'] == 'B'     # 全局唯一激活

    def test_suite_add_requests_unique(self, client):
        p, r = _mk_request(client)
        s = client.post(API + '/suites', json={'name': 'S', 'project_id': p['id']}).get_json()['data']
        client.post(API + '/suites/%d/add-requests' % s['id'], json={'request_ids': [r['id']]})
        client.post(API + '/suites/%d/add-requests' % s['id'], json={'request_ids': [r['id']]})
        suite = client.get(API + '/suites').get_json()['data'][0]
        assert len(suite['suite_requests']) == 1                  # unique_together 语义

    def test_task_validation(self, client):
        assert client.post(API + '/tasks', json={'name': 'T', 'task_type': 'TEST_SUITE',
                                               'trigger_type': 'INTERVAL', 'interval_seconds': 0}).status_code == 400
        assert client.post(API + '/tasks', json={'name': 'T', 'task_type': 'API_REQUEST',
                                               'trigger_type': 'BAD', 'request_id': 1}).status_code == 400
        assert client.post(API + '/tasks', json={'name': 'T', 'task_type': 'API_REQUEST',
                                               'trigger_type': 'CRON', 'cron_expression': 'not a cron',
                                               'request_id': 1}).status_code == 400

    def test_settings_roundtrip(self, client):
        client.put(API + '/settings', json={'webhook_url': 'http://x/hook', 'notify_on_failure': True})
        s = client.get(API + '/settings').get_json()['data']
        assert s['webhook_url'] == 'http://x/hook' and 'smtp_password' not in s


# ---------------- 调度器 ----------------
class TestScheduler:
    def test_calculate_next_run_cron(self):
        t = {'trigger_type': 'CRON', 'cron_expression': '0 3 * * *'}
        nxt = scheduler.calculate_next_run(t, now=datetime_local(2026, 9, 17, 10, 0))
        assert nxt and nxt > int(datetime_local(2026, 9, 17, 10, 0).timestamp())

    def test_calculate_next_run_interval_and_once(self):
        base = datetime_local(2026, 9, 17, 10, 0)
        assert scheduler.calculate_next_run({'trigger_type': 'INTERVAL', 'interval_seconds': 60}, now=base) \
            == int(base.timestamp()) + 60
        past = int(base.timestamp()) - 100
        assert scheduler.calculate_next_run({'trigger_type': 'ONCE', 'execute_at': past}, now=base) is None

    def test_task_stats_update(self, tmp_stores):
        t = tmp_stores.tasks.create({'name': 'T', 'task_type': 'API_REQUEST',
                                     'trigger_type': 'INTERVAL', 'interval_seconds': 60,
                                     'status': 'ACTIVE'})
        scheduler._update_task_stats(t['id'], True, {})
        fresh = tmp_stores.tasks.get(t['id'])
        assert fresh['total_runs'] == 1 and fresh['successful_runs'] == 1 and fresh['next_run_time']

    def test_run_now_creates_log(self, tmp_stores, client):
        p, r = _mk_request(client, url='http://127.0.0.1:9/never')   # 不可达 → 失败历史
        t = client.post(API + '/tasks', json={
            'name': '演示任务', 'task_type': 'API_REQUEST', 'trigger_type': 'INTERVAL',
            'interval_seconds': 3600, 'request_id': r['id']}).get_json()['data']
        log, err = scheduler.run_task_now(t['id'])
        assert err == '' and log['status'] in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')
        deadline = time.time() + 15
        while time.time() < deadline:
            lg = tmp_stores.task_logs.get(log['id'])
            if lg['status'] in ('COMPLETED', 'FAILED'):
                break
            time.sleep(0.3)
        assert tmp_stores.task_logs.get(log['id'])['status'] == 'FAILED'   # 不可达地址必失败
        fresh = tmp_stores.tasks.get(t['id'])
        assert fresh['total_runs'] == 1 and fresh['failed_runs'] == 1


def datetime_local(*args):
    from datetime import datetime
    return datetime(*args)
