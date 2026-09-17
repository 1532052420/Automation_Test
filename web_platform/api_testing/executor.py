# -*- coding: utf-8 -*-
"""接口测试 · 执行引擎（移植自 testhub_platform/apps/api_testing/utils.py + views.py 执行动作）

保留 testhub 的全部执行语义：
- 变量替换顺序：先 {{env_var}} 环境变量，再 ${function(args)} 动态函数；
- 请求体类型：none / json / raw / form-data / x-www-form-urlencoded；
- 断言类型：status_code / response_time / contains / json_path / header / equals；
- 历史与执行记录字段与 testhub 模型同名（区别：持久化走 YAML 存储层）。
"""
import json
import threading
import time
from urllib.parse import urlparse

import requests
from jsonpath_ng import parse as jsonpath_parse

from web_platform.api_testing import yaml_store as store
from web_platform.api_testing.variable_resolver import VariableResolver

REQUEST_TIMEOUT = 30


def _session_for(url):
    """回环地址（本平台内置 mock）不走系统代理——环境里的 HTTP_PROXY 会把
    127.0.0.1 的请求转发出去，导致 mock 收不到/404。"""
    host = (urlparse(url).hostname or '').lower()
    if host in ('127.0.0.1', 'localhost', '::1'):
        s = requests.Session()
        s.trust_env = False
        return s
    return requests.Session()


# ---------------- 断言（照抄 testhub utils.execute_assertions） ----------------
def execute_assertions(resp, assertions):
    """对 requests.Response 执行断言列表，返回逐条结果（与 testhub 同结构）"""
    results = []
    for assertion in assertions or []:
        result = {
            'name': assertion.get('name', '未命名断言'),
            'type': assertion.get('type'),
            'passed': False,
            'expected': assertion.get('expected'),
            'actual': None,
            'error': None,
        }
        try:
            a_type = assertion.get('type')
            expected = assertion.get('expected')
            actual, passed = None, False

            if a_type == 'status_code':
                actual = resp.status_code
                passed = actual == expected
            elif a_type == 'response_time':
                actual = assertion.get('actual_time')
                passed = actual <= expected if actual is not None else False
            elif a_type == 'contains':
                text = resp.text or ''
                actual = text[:200] + '...' if len(text) > 200 else text
                passed = str(expected) in str(text)
            elif a_type == 'json_path':
                json_path = assertion.get('json_path', '')
                try:
                    if 'application/json' not in (resp.headers.get('content-type') or '').lower():
                        raise ValueError('响应不是JSON格式，Content-Type: %s'
                                         % resp.headers.get('content-type'))
                    resp_json = json.loads(resp.text)
                    if not json_path:
                        raise ValueError('JSON路径表达式不能为空')
                    matches = jsonpath_parse(json_path).find(resp_json)
                    actual = matches[0].value if matches else None
                    passed = str(actual) == str(expected)
                    result['actual'] = actual
                except json.JSONDecodeError as e:
                    result['error'] = 'JSON解析失败: %s' % e
                except ImportError:
                    result['error'] = '缺少依赖库 jsonpath-ng'
                except Exception as e:
                    result['error'] = '执行错误: %s' % e
            elif a_type == 'header':
                actual = resp.headers.get(assertion.get('header_name', ''))
                passed = actual == assertion.get('expected_value')
            elif a_type == 'equals':
                actual = resp.text.strip()
                passed = actual == str(expected).strip()

            if result['actual'] is None:
                result['actual'] = actual
            result['passed'] = bool(passed)
        except Exception as e:
            result['error'] = str(e)
            result['passed'] = False
        results.append(result)
    return results


# ---------------- 变量替换（照抄 testhub views 的 _replace_variables*） ----------------
def replace_vars(text, variables):
    if not isinstance(text, str):
        return text
    for k, v in (variables or {}).items():
        text = text.replace('{{%s}}' % k, str(v))
    return text


def replace_vars_in_dict(data, variables):
    if isinstance(data, dict):
        return {k: replace_vars_in_dict(v, variables) for k, v in data.items()}
    if isinstance(data, list):
        return [replace_vars_in_dict(v, variables) for v in data]
    return replace_vars(data, variables)


def resolve_vars_in_dict(data, resolver):
    if isinstance(data, dict):
        return {k: resolve_vars_in_dict(v, resolver) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_vars_in_dict(v, resolver) for v in data]
    if isinstance(data, str):
        return resolver.resolve(data)
    return data


def _env_variables(environment):
    """环境 → 变量表（YAML 里 variables 就是 dict，与 testhub JSONField 一致）"""
    if not environment:
        return {}
    return dict(environment.get('variables') or {})


# ---------------- 单请求执行（testhub RequestViewSet.execute 的核心路径） ----------------
def send_request(req, environment=None, overrides=None):
    """按请求定义发一次真实 HTTP 请求。

    req: 请求 dict（url/method/headers/params/body/assertions）
    overrides: 前端调试时覆盖的字段（与 testhub「用前端数据优先」一致）
    返回 history dict（写入 histories 的同构数据 + assertions_results）。
    """
    ov = overrides or {}
    resolver = VariableResolver()
    variables = _env_variables(environment)

    method = (ov.get('method') or req.get('method') or 'GET').upper()
    url = replace_vars(str(ov.get('url') or req.get('url') or ''), variables)
    url = resolver.resolve(url)

    # 请求头：新数组格式 [{key,value,enabled}]，兼容旧对象格式
    headers = {}
    raw_headers = ov.get('headers') if ov.get('headers') is not None else req.get('headers')
    if isinstance(raw_headers, list):
        for h in raw_headers:
            if h.get('enabled', True) and h.get('key'):
                val = resolver.resolve(replace_vars(str(h.get('value', '')), variables))
                headers[h['key']] = val
    elif isinstance(raw_headers, dict):
        for k, v in raw_headers.items():
            headers[k] = resolver.resolve(replace_vars(str(v), variables))

    params = {}
    raw_params = ov.get('params') if ov.get('params') is not None else req.get('params')
    if isinstance(raw_params, dict):
        for k, v in raw_params.items():
            params[k] = resolver.resolve(replace_vars(str(v), variables))

    # 请求体
    body_data, body_type = None, 'none'
    raw_body = ov.get('body') if ov.get('body') is not None else req.get('body')
    if raw_body and method in ('POST', 'PUT', 'PATCH'):
        body_type = raw_body.get('type', 'none')
        content = raw_body.get('data')
        if body_type == 'json':
            body_data = resolve_vars_in_dict(replace_vars_in_dict(content, variables), resolver) \
                if isinstance(content, (dict, list)) else content
        elif body_type == 'raw':
            body_data = resolver.resolve(replace_vars(content, variables)) if isinstance(content, str) else content
        elif body_type in ('form-data', 'x-www-form-urlencoded'):
            body_data = resolve_vars_in_dict(replace_vars_in_dict(content, variables), resolver) \
                if isinstance(content, (dict, list)) else content
        else:
            body_data = content

    started = time.time()
    error_msg = ''
    try:
        kwargs = dict(method=method, url=url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if body_type == 'raw':
            kwargs['data'] = body_data
        else:
            kwargs['json'] = body_data
        resp = _session_for(url).request(**kwargs)
        elapsed_ms = (time.time() - started) * 1000
    except Exception as e:
        error_msg = str(e)[:500]

    history = {
        'request_id': req.get('id'),
        'environment_id': (environment or {}).get('id'),
        'request_data': {'url': url, 'method': method, 'headers': headers,
                         'params': params, 'body': body_data},
        'response_data': {}, 'status_code': None, 'response_time': None,
        'error_message': error_msg, 'assertions_results': [],
        'executed_by': ov.get('executed_by') or 'platform',
        'executed_at': int(time.time()),
    }

    if error_msg:
        # 失败也落历史（与 testhub 一致：错误历史可回看）
        return store.histories.create(history)

    is_json = 'application/json' in (resp.headers.get('content-type') or '').lower()
    history.update({
        'response_data': {
            'headers': dict(resp.headers),
            'body': resp.text[:20000],
            'json': resp.text[:20000] if is_json else None,
        },
        'status_code': resp.status_code,
        'response_time': round(elapsed_ms, 1),
    })
    # 断言（response_time 断言先注入实际耗时，同 testhub）
    assertions = ov.get('assertions')
    if assertions is None:
        assertions = req.get('assertions')
    assertions = [dict(a) for a in (assertions or [])]
    for a in assertions:
        if a.get('type') == 'response_time':
            a['actual_time'] = round(elapsed_ms, 1)
    history['assertions_results'] = execute_assertions(resp, assertions)
    return store.histories.create(history)


# ---------------- 测试套件执行（testhub utils.execute_test_suite） ----------------
def execute_suite(suite, environment=None, executed_by='platform', execution=None):
    """顺序执行套件内启用的请求，落 TestExecution 记录并返回结果 dict。
    execution：外部已建好的执行记录（routes 先建 RUNNING 记录以便前端立刻可见），
    传入则复用更新，不再新建。"""
    env = environment or (store.environments.get(suite.get('environment_id'))
                          if suite.get('environment_id') else None)
    items = sorted([r for r in (suite.get('suite_requests') or []) if r.get('enabled', True)],
                   key=lambda r: r.get('order', 0))
    if execution is None:
        execution = store.executions.create({
            'suite_id': suite.get('id'),
            'status': 'RUNNING', 'start_time': int(time.time()), 'end_time': None,
            'total_requests': len(items), 'passed_requests': 0, 'failed_requests': 0,
            'results': [], 'executed_by': executed_by,
        })
    results, passed, failed = [], 0, 0
    for sr in items:
        req = store.requests.get(sr.get('request_id'))
        if not req:
            results.append({'name': '已删除请求 #%s' % sr.get('request_id'),
                            'passed': False, 'error': '请求不存在'})
            failed += 1
            continue
        # 套件内可覆盖断言（testhub TestSuiteRequest.assertions）
        overrides = {'assertions': sr.get('assertions') or req.get('assertions'),
                     'executed_by': executed_by}
        history = send_request(req, env, overrides)
        ok = all(a.get('passed') for a in history.get('assertions_results') or []) \
            and not history.get('error_message') and history.get('status_code')
        results.append({
            'request_id': req.get('id'), 'name': req.get('name'),
            'method': (history.get('request_data') or {}).get('method'),
            'url': (history.get('request_data') or {}).get('url'),
            'status_code': history.get('status_code'),
            'response_time': history.get('response_time'),
            'history_id': history.get('id'),
            'assertions_results': history.get('assertions_results'),
            'passed': bool(ok),
        })
        if ok:
            passed += 1
        else:
            failed += 1

    patch = {
        'status': 'COMPLETED' if failed == 0 else 'FAILED',
        'end_time': int(time.time()),
        'total_requests': len(items),
        'passed_requests': passed, 'failed_requests': failed, 'results': results,
    }
    execution.update(patch)
    # 关键：落库。只改内存 dict 不写存储层的话，读回的永远是 RUNNING
    return store.executions.update(execution['id'], patch)


def execute_single_request(request_id, environment_id=None, executed_by='platform'):
    """定时任务的 API_REQUEST 类型：执行单请求（testhub utils.execute_api_request）"""
    req = store.requests.get(request_id)
    env = store.environments.get(environment_id) if environment_id else None
    return send_request(req or {}, env, {'executed_by': executed_by})


def run_in_thread(fn):
    """后台线程执行（testhub _execute_task_async 的 threading.Thread(daemon=True) 等价）"""
    t = threading.Thread(target=fn)
    t.daemon = True
    t.start()
    return t
