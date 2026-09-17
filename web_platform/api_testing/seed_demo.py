# -*- coding: utf-8 -*-
"""接口测试模块 · 演示数据播种（幂等：按名称判重，可重复执行）

用法：cd <项目根> && .venv/bin/python -m web_platform.api_testing.seed_demo
造出的数据全部指向平台内置 mock 服务（/api-testing/mock/*，离线可用）：
  项目「电商平台示例」 → 集合「用户服务」「通用工具」 → 6 个接口（含断言）
  环境「本地测试」（激活）→ 套件「用户登录链路」→ 定时任务「链路巡检」（每 30 分钟）
"""
import sys
import time


def _ensure(store, unique_key, unique_val, payload):
    """按唯一键判重的创建（幂等核心）"""
    exist = [x for x in store.list() if x.get(unique_key) == unique_val]
    if exist:
        print('已存在，跳过: %s' % unique_val)
        return exist[0]
    item = store.create(payload)
    print('已创建: %s (id=%s)' % (unique_val, item['id']))
    return item


def seed():
    from web_platform.api_testing import yaml_store as store
    from web_platform.api_testing.variable_resolver import VariableResolver

    base = 'http://127.0.0.1:8080/api-testing'
    resolver = VariableResolver()

    project = _ensure(store.projects, 'name', '电商平台示例', {
        'name': '电商平台示例', 'description': 'testhub_platform 移植验收演示项目（指向内置 mock 服务）',
        'project_type': 'HTTP', 'status': 'IN_PROGRESS', 'owner': 'seed',
    })

    coll_user = _ensure(store.collections, 'name', '用户服务', {
        'name': '用户服务', 'description': '登录 / 注册 / 个人信息', 'project_id': project['id'], 'order': 1})
    coll_tool = _ensure(store.collections, 'name', '通用工具', {
        'name': '通用工具', 'description': '回显 / 延迟演示', 'project_id': project['id'], 'order': 2})

    env = _ensure(store.environments, 'name', '本地测试', {
        'name': '本地测试', 'scope': 'LOCAL', 'is_active': True,
        'variables': {'base_url': base, 'token': 'demo-token-001', 'env': 'test'},
        'project_id': project['id'],
    })

    def mk_request(name, coll, method, url, headers, params, body, assertions):
        exist = [x for x in store.requests.list() if x.get('name') == name]
        if exist:
            print('已存在，跳过: %s' % name)
            return exist[0]
        return store.requests.create({
            'name': name, 'description': '', 'project_id': project['id'],
            'collection_id': coll['id'], 'request_type': 'HTTP',
            'method': method, 'url': url, 'headers': headers, 'params': params,
            'body': body, 'assertions': assertions,
        })

    auth_headers = [{'key': 'Authorization', 'value': 'Bearer {{token}}', 'enabled': True}]
    r_login = mk_request(
        '用户登录', coll_user, 'POST', '{{base_url}}/mock/login', [], {},
        {'type': 'json', 'data': {'username': 'admin', 'password': '123456'}},
        [{'name': '状态码', 'type': 'status_code', 'expected': 200},
         {'name': '业务码', 'type': 'json_path', 'json_path': '$.code', 'expected': '0'},
         {'name': '角色', 'type': 'json_path', 'json_path': '$.data.user.role', 'expected': 'admin'}])
    r_login_bad = mk_request(
        '错误口令登录（反向断言）', coll_user, 'POST', '{{base_url}}/mock/login', [], {},
        {'type': 'json', 'data': {'username': 'admin', 'password': '${random_digits(4)}'}},
        [{'name': '业务码=错误', 'type': 'json_path', 'json_path': '$.code', 'expected': '1001'}])
    r_echo = mk_request(
        '动态变量回显', coll_tool, 'POST', '{{base_url}}/mock/echo', auth_headers, {'from': 'seed'},
        {'type': 'json', 'data': {'phone': '${random_phone}', 'name': '${generate_chinese_name}'}},
        [{'name': '状态码', 'type': 'status_code', 'expected': 200},
         {'name': '含请求头', 'type': 'json_path', 'json_path': '$.headers.Authorization',
          'expected': 'Bearer demo-token-001'}])
    r_slow = mk_request(
        '响应时间断言（≤800ms）', coll_tool, 'GET', '{{base_url}}/mock/slow?ms=300', [], {}, {'type': 'none', 'data': None},
        [{'name': '耗时上限', 'type': 'response_time', 'expected': 800},
         {'name': '状态码', 'type': 'status_code', 'expected': 200}])
    mk_request('GET 回显', coll_tool, 'GET', '{{base_url}}/mock/echo?env={{env}}', [], {}, {'type': 'none', 'data': None},
               [{'name': '状态码', 'type': 'status_code', 'expected': 200}])
    mk_request('HEAD 连通性', coll_tool, 'HEAD', '{{base_url}}/mock/echo', [], {}, {'type': 'none', 'data': None}, [])

    # 变量解析冒烟（证明 {{}} 与 ${} 全链路可用）
    print('变量解析演示:', resolver.resolve('令牌={{token}} 手机=${random_phone}')[:60])

    suite = _ensure(store.suites, 'name', '用户登录链路', {
        'name': '用户登录链路', 'description': '正反向登录 + 回显变量 + 耗时断言',
        'project_id': project['id'], 'environment_id': env['id'],
        'suite_requests': [
            {'request_id': r_login['id'], 'order': 1, 'assertions': [], 'enabled': True},
            {'request_id': r_login_bad['id'], 'order': 2, 'assertions': [], 'enabled': True},
            {'request_id': r_echo['id'], 'order': 3, 'assertions': [], 'enabled': True},
            {'request_id': r_slow['id'], 'order': 4, 'assertions': [], 'enabled': True},
        ]})

    _ensure(store.tasks, 'name', '链路巡检（每30分钟）', {
        'name': '链路巡检（每30分钟）', 'description': '定时执行「用户登录链路」套件',
        'task_type': 'TEST_SUITE', 'trigger_type': 'INTERVAL', 'interval_seconds': 1800,
        'execute_at': None, 'cron_expression': '',
        'suite_id': suite['id'], 'request_id': None, 'environment_id': env['id'],
        'status': 'ACTIVE', 'next_run_time': int(time.time()) + 1800,
        'last_run_time': None, 'total_runs': 0, 'successful_runs': 0,
        'failed_runs': 0, 'last_result': {}, 'error_message': '',
    })
    store.get_settings()
    print('\n演示数据就绪。打开平台「接口测试」页即可查看。')


if __name__ == '__main__':
    sys.path.insert(0, '.')
    seed()
