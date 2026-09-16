# -*- coding: utf-8 -*-
"""AppUI 自动化测试平台 · 功能接口自动化测试

自包含：fixture 自动以 8099 端口拉起平台进程，结束后关闭。
运行：cd <项目根> && .venv/bin/python -m pytest web_platform/tests/ -v
用例与功能点映射见 web_platform/平台功能测试用例.md
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

PORT = int(os.environ.get('PLATFORM_TEST_PORT', '8099'))
BASE = 'http://127.0.0.1:%d' % PORT
VALID_CONF = 'config/demoProject/app_ui_android_devices_info_demoProject.conf'
VALID_CASE = 'cases/app_ui/android/demoProject/test_login.py::TestDemoToolLogin::test_phone_login_flow'
FAKE_RUN = '20991231_901'
RUNS_DIR = os.path.join(ROOT, 'output', 'runs')


def _make_opener(no_redirect=False):
    handlers = [urllib.request.ProxyHandler({})]  # 本机服务绕过系统代理（防 502 干扰）
    if no_redirect:
        handlers.append(_NoRedirect)
    return urllib.request.build_opener(*handlers)


def http(method, path, body=None, timeout=30, no_redirect=False, raw_body=None, headers=None):
    """返回 (status_code, body_str, headers)"""
    data = raw_body if raw_body is not None else (json.dumps(body).encode('utf-8') if body is not None else None)
    hdrs = dict(headers or {})
    if raw_body is None and body is not None:
        hdrs.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(BASE + path, method=method, data=data, headers=hdrs)
    opener = _make_opener(no_redirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode('utf-8', 'replace'), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), dict(e.headers)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@pytest.fixture(scope='session')
def platform(tmp_path_factory):
    rec_path = tmp_path_factory.mktemp('dbg_records') / 'records.json'
    meta_path = tmp_path_factory.mktemp('admin_meta') / 'admin_meta.json'
    env = dict(os.environ, WEB_PLATFORM_PORT=str(PORT), PYTHONIOENCODING='utf-8',
               DEBUG_RECORDS_PATH=str(rec_path), ADMIN_META_PATH=str(meta_path))
    # 启动前清理端口占用者：上一个会话若 teardown 失败留下孤儿进程，
    # 新平台会绑定失败/请求打到旧代码上，导致瞬态 500
    try:
        holder = subprocess.run(['lsof', '-ti', 'tcp:%d' % PORT],
                                capture_output=True, text=True, timeout=10)
        for pid in holder.stdout.split():
            try:
                os.kill(int(pid), 9)
            except (ValueError, ProcessLookupError):
                pass
        if holder.stdout.strip():
            time.sleep(1)
    except Exception:
        pass
    proc = subprocess.Popen([sys.executable, os.path.join('web_platform', 'app.py')],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=open('/tmp/fixture_platform_stderr.log', 'w'),
                            start_new_session=True)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            code, _, _ = http('GET', '/api/status', timeout=3)
            if code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError('测试平台启动超时')
    yield BASE
    # 进程组整体终止：平台可能派生子进程（报告服务/定位器等），逐个杀会漏
    try:
        os.killpg(os.getpgid(proc.pid), 15)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except Exception:
            proc.kill()


@pytest.fixture()
def fake_run():
    """预置一条磁盘历史任务（模拟平台重启后的持久化恢复场景）"""
    run_dir = os.path.join(RUNS_DIR, FAKE_RUN)
    os.makedirs(os.path.join(run_dir, 'logs'), exist_ok=True)
    result = {'run_id': FAKE_RUN, 'status': 'RUNNING', 'start_time': '2099-12-31 00:00:00',
              'end_time': None, 'conf_file': VALID_CONF, 'device_desc': 'ghost', 'device_model': '',
              'app_package': 'com.example.app', 'udid': 'ghost-udid', 'overrides': {},
              'case_nodes': [VALID_CASE], 'total': 1, 'passed': 0, 'failed': 0, 'error': 0,
              'skipped': 0, 'exit_code': None, 'error_msg': '', 'allure_dir': '', 
              'log_path': 'output/runs/%s/logs/test.log' % FAKE_RUN, 'report_dir': '',
              'stop_requested': False}
    with open(os.path.join(run_dir, 'result.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False))
    yield FAKE_RUN
    shutil.rmtree(run_dir, ignore_errors=True)


# ---------------------------------------------------------------- 页面与导航
def test_pages_ok(platform):
    for page in ('/', '/run', '/report', '/debug'):
        code, body, _ = http('GET', page)
        assert code == 200, '%s -> %s' % (page, code)
        assert 'sidebar' in body


def test_locator_mounted(platform):
    """定位器并入平台：/locator 补斜杠跳转，/locator/ 直接返回定位器页面（TC-076）"""
    code, _, headers = http('GET', '/locator', no_redirect=True)
    assert code in (301, 308)
    assert headers.get('Location', '').endswith('/locator/')
    code, body, _ = http('GET', '/locator/')
    assert code == 200
    assert '定位' in body or '元素' in body


# ---------------------------------------------------------------- 只读探测
def test_status_structure(platform):
    code, body, _ = http('GET', '/api/status')
    assert code == 200
    d = json.loads(body)
    for key in ('ok', 'service', 'confs', 'device_online', 'devices', 'appium', 'running', 'port'):
        assert key in d, '缺字段 %s' % key
    assert d['service'] == 'app-ui-platform'
    assert isinstance(d['confs'], list) and d['confs']


def test_devices_structure(platform):
    code, body, _ = http('GET', '/api/devices')
    assert code == 200
    d = json.loads(body)
    assert d['ok'] is True and isinstance(d['devices'], list)


def test_cases_tree(platform):
    code, body, _ = http('GET', '/api/cases')
    assert code == 200
    tree = json.loads(body)['tree']
    assert tree, '用例树为空'
    node = tree[0]
    assert node['file'].startswith('cases/app_ui') and node['file'].endswith('.py')
    assert node['class_name'] and all(m.startswith('test_') for m in node['methods'])


def test_confs(platform):
    code, body, _ = http('GET', '/api/confs')
    assert code == 200
    confs = json.loads(body)['confs']
    assert confs and confs[0]['file'].endswith('.conf')
    assert 'devices' in confs[0]


def test_exec_defaults(platform):
    code, body, _ = http('GET', '/api/exec_defaults')
    assert code == 200
    d = json.loads(body)
    assert d['ok'] and d['defaults']['conf_file']
    for key in ('udid', 'app_package', 'app_activity', 'server', 'occupied',
                'device_online', 'udid_from_conf'):
        assert key in d['defaults']
    # 状态真实性：device_online 是布尔实测值；无设备时 udid 可为 conf 预填但必须有标记
    assert isinstance(d['defaults']['device_online'], bool)
    if not d['defaults']['device_online']:
        assert d['defaults']['udid_from_conf'] or not d['defaults']['udid']
    # ?conf= 切换来源
    other = [c for c in d['confs'] if c != d['defaults']['conf_file']]
    if other:
        code2, body2, _ = http('GET', '/api/exec_defaults?conf=' + urllib.parse.quote(other[0]))
        assert code2 == 200 and json.loads(body2)['defaults']['conf_file'] == other[0]


# ---------------------------------------------------------------- 启动校验链
def test_start_run_empty_cases(platform):
    code, body, _ = http('POST', '/api/run', {})
    assert code == 400 and '请至少选择一个用例' in json.loads(body).get('msg', '')


def test_start_run_missing_conf(platform):
    code, body, _ = http('POST', '/api/run', {'case_nodes': [VALID_CASE]})
    assert code == 400 and '请选择设备配置文件' in json.loads(body).get('msg', '')


def test_start_run_bad_conf(platform):
    code, body, _ = http('POST', '/api/run', {'case_nodes': [VALID_CASE],
                                              'conf_file': 'config/demoProject/not_exist.conf'})
    assert code == 400 and '解析不到设备信息' in json.loads(body).get('msg', '')


def test_start_run_appium_down(platform):
    # 安全护栏：设备 + Appium 都在线时，此用例会真实创建执行任务驱动真机 —— 必须跳过
    st = json.loads(http('GET', '/api/status')[1])
    if st['appium']['ok'] and st['device_online'] > 0:
        import pytest
        pytest.skip('Appium 与设备均在线，跳过启动校验测试（避免驱动真实设备）')
    code, body, _ = http('POST', '/api/run', {'case_nodes': [VALID_CASE], 'conf_file': VALID_CONF})
    msg = json.loads(body).get('msg', '')
    # 无设备环境：Appium 未启动时应在 Appium 校验处拦截；若本机 Appium 恰好在跑，则应拦在设备在线校验
    assert code == 400 and ('Appium 不可用' in msg or '不在线' in msg), msg


def test_start_run_node_injection(platform):
    """用例节点白名单：pytest 参数注入必须被拒绝（TC-024）"""
    for bad in ('--version', '-k', 'x y', '../etc/passwd'):
        code, body, _ = http('POST', '/api/run',
                             {'case_nodes': [bad], 'conf_file': VALID_CONF})
        assert code == 400 and '用例节点不合法' in json.loads(body).get('msg', ''), '%s -> %s' % (bad, body)


# ---------------------------------------------------------------- 历史与恢复
def test_disk_task_visible(platform, fake_run):
    code, body, _ = http('GET', '/api/runs')
    assert code == 200
    ids = [r['run_id'] for r in json.loads(body)['runs']]
    assert fake_run in ids, '磁盘历史未恢复'
    code, body, _ = http('GET', '/api/run/%s' % fake_run)
    assert code == 200 and json.loads(body)['task']['run_id'] == fake_run


def test_ghost_running_normalized(platform, fake_run):
    """平台重启残留的 RUNNING 任务应归一为 ERROR（TC-041）"""
    code, body, _ = http('GET', '/api/run/%s' % fake_run)
    task = json.loads(body)['task']
    assert task['status'] == 'ERROR', '幽灵 RUNNING 未归一: %s' % task['status']
    assert '平台重启' in (task['error_msg'] or '')


def test_delete_run(platform, fake_run):
    code, body, _ = http('DELETE', '/api/runs/%s' % fake_run)
    assert code == 200 and json.loads(body)['ok']
    assert not os.path.isdir(os.path.join(RUNS_DIR, fake_run)), 'run 目录未删除'
    code, body, _ = http('GET', '/api/runs')
    assert fake_run not in [r['run_id'] for r in json.loads(body)['runs']]


def test_delete_invalid_id(platform):
    code, body, _ = http('DELETE', '/api/runs/abc')
    assert code == 400 and 'run_id 不合法' in json.loads(body).get('msg', '')


def test_clear_runs(platform, fake_run):
    code, body, _ = http('POST', '/api/runs/clear', {})
    assert code == 200 and json.loads(body)['ok']
    assert not os.path.isdir(os.path.join(RUNS_DIR, fake_run))


def test_not_found_paths(platform):
    code, body, _ = http('GET', '/api/run/99999999_999')
    assert code == 404 and '任务不存在' in json.loads(body).get('msg', '')
    code, body, _ = http('GET', '/api/run/99999999_999/log')
    assert code == 200 and json.loads(body)['ok'] is False
    code, body, _ = http('POST', '/api/run/99999999_999/stop', {})
    assert code == 400
    code, body, _ = http('POST', '/api/run/99999999_999/report', {})
    assert code == 400
    code, body, _ = http('POST', '/api/run/99999999_999/report/open', {})
    assert code == 404


def test_cases_of_missing_run(platform):
    code, body, _ = http('GET', '/api/run/99999999_999/cases')
    assert code == 200 and json.loads(body)['cases'] == []


def test_attachment_traversal_blocked(platform, fake_run):
    """附件接口路径穿越防护（TC-051）"""
    for evil in ('..%2F..%2Fconfig%2Fpytest.ini', '%2E%2E%2F%2E%2E%2Fetc%2Fpasswd',
                 '.hidden', 'sub%2Fx.png', 'nope.png'):
        code, _, _ = http('GET', '/api/runs/%s/res/%s' % (fake_run, evil))
        assert code == 404, '%s -> %s（应拒绝）' % (evil, code)


# ---------------------------------------------------------------- 代码审查回归
def test_debug_items(platform):
    code, body, _ = http('GET', '/api/debug/items')
    assert code == 200
    d = json.loads(body)
    assert d['ok'] and len(d['items']) >= 40 and not d['load_errors']


def test_debug_run_single(platform):
    code, body, _ = http('POST', '/api/debug/run', {'id': 'common.hamcrest'}, timeout=120)
    assert code == 200 and json.loads(body)['result']['status'] == 'PASS'
    code, body, _ = http('POST', '/api/debug/run', {'id': 'nope.nope'}, timeout=30)
    assert code == 200 and json.loads(body)['result']['status'] == 'FAIL'


# ---------------------------------------------------------------- 临时文件清理（单元级）
def test_tmp_device_files_cleanup():
    """任务终态后 config/app_ui_tmp/<pid>* 两个设备临时文件应被清理（TC-035）"""
    from web_platform import runner as R
    tmp_dir = R.APP_UI_TMP_DIR
    os.makedirs(tmp_dir, exist_ok=True)
    f1 = os.path.join(tmp_dir, str(os.getpid()))
    f2 = os.path.join(tmp_dir, '%s_current_desired_capabilities' % os.getpid())
    for f in (f1, f2):
        with open(f, 'w') as fh:
            fh.write('{}')
    task = {'status': 'PASSED', 'tmp_files': [f1, f2]}
    R.ExecutionManager()._cleanup_device_tmp_files(task)
    assert not os.path.exists(f1) and not os.path.exists(f2)


# ---------------------------------------------------------------- 周边脚本
def test_run_sh_no_dead_branch():
    """run.sh 不再引用不存在的 run_web_ui_test.py（TC-070）"""
    content = open(os.path.join(ROOT, 'run.sh'), encoding='utf-8').read()
    assert 'run_web_ui_test' not in content
    subprocess.run(['bash', '-n', os.path.join(ROOT, 'run.sh')], check=True)


# ---------------------------------------------------------------- 审查记录
def _make_results(passed=38, failed=2, skipped=2):
    results = []
    n = 0
    for status, count in (('PASS', passed), ('FAIL', failed), ('SKIP', skipped)):
        for _ in range(count):
            results.append({'id': 'case.%03d' % n, 'file': 'x.py', 'title': 't',
                            'status': status, 'detail': '', 'error': None, 'duration_ms': 1})
            n += 1
    return results


def test_debug_records_save_and_list(platform):
    for i in range(3):
        code, body, _ = http('POST', '/api/debug/records',
                             {'results': _make_results(passed=30 + i), 'duration_ms': 1000 + i})
        assert code == 200 and json.loads(body)['ok']
    code, body, _ = http('GET', '/api/debug/records')
    d = json.loads(body)
    assert d['ok'] and d['total'] == 3 and d['pages'] == 1
    newest = d['records'][0]
    assert newest['summary']['passed'] == 32, '应按时间倒序（最新在前）'
    assert 'results' not in newest, '列表载荷不应携带明细'


def test_debug_records_pagination(platform):
    for i in range(12):
        http('POST', '/api/debug/records', {'results': _make_results(), 'duration_ms': i})
    code, body, _ = http('GET', '/api/debug/records')
    d = json.loads(body)
    assert d['total'] == 15 and d['pages'] == 2 and len(d['records']) == 10
    code, body, _ = http('GET', '/api/debug/records?page=2')
    d2 = json.loads(body)
    assert len(d2['records']) == 5 and d2['page'] == 2


def test_debug_records_detail_and_delete(platform):
    code, body, _ = http('POST', '/api/debug/records', {'results': _make_results()})
    rid = json.loads(body)['record_id']
    code, body, _ = http('GET', '/api/debug/records/%s' % rid)
    rec = json.loads(body)['record']
    assert len(rec['results']) == 42 and rec['summary']['failed'] == 2
    code, body, _ = http('DELETE', '/api/debug/records/%s' % rid)
    assert code == 200 and json.loads(body)['ok']
    code, body, _ = http('GET', '/api/debug/records/%s' % rid)
    assert code == 404


def test_debug_records_validation(platform):
    code, body, _ = http('POST', '/api/debug/records', {'results': []})
    assert code == 400
    code, body, _ = http('GET', '/api/debug/records/bad..id')
    assert code == 400
    code, body, _ = http('GET', '/api/debug/records/no_such_id')
    assert code == 404

# ---------------------------------------------------------------- 交互调试工具
def _run_tool(tool, params):
    code, body, _ = http('POST', '/api/debug/tool', {'tool': tool, 'params': params}, timeout=120)
    return code, json.loads(body)


def test_debug_functions_catalog(platform):
    """方法目录自动识别：覆盖框架文件，新增/删除文件后清单自动增减"""
    code, body, _ = http('GET', '/api/debug/functions', timeout=60)
    assert code == 200
    d = json.loads(body)
    assert d['ok'] and d['total_files'] >= 30 and d['total_methods'] >= 100
    files = {f['file']: f for f in d['files']}
    assert 'common/dateTimeTool.py' in files, '框架文件未自动识别'
    entries = files['common/dateTimeTool.py']['entries']
    targets = [e['target'] for e in entries]
    assert 'common.dateTimeTool::DateTimeTool.strToTimeStamp' in targets
    # 参数签名来自源码反射
    st = next(e for e in entries if e['target'] == 'common.dateTimeTool::DateTimeTool.strToTimeStamp')
    names = [p['name'] for p in st['params']]
    assert names == ['str', 'str_format', 'is_with_millisecond']
    # 用例目录也在扫描范围
    assert any(f.startswith('cases/') for f in files)


def test_entry_scripts_clean():
    """统一入口检查（TC-077）：仅保留 自动化执行入口.command + run.sh（定位器已并入平台）"""
    main = os.path.join(ROOT, '自动化执行入口.command')
    assert os.path.isfile(main)
    mcontent = open(main, encoding='utf-8').read()
    assert 'web_platform/app.py' not in mcontent  # 启动一律走 run.sh
    assert '8001' not in mcontent                 # 独立定位器端口已取消
    runsh = os.path.join(ROOT, 'run.sh')
    rcontent = open(runsh, encoding='utf-8').read()
    assert 'element_locator/server.py' not in rcontent
    subprocess.run(['bash', '-n', main], check=True)
    subprocess.run(['bash', '-n', runsh], check=True)

# ---------------------------------------------------------------- 管理后台
def test_admin_upload_list_delete(platform):
    """上传→列表→覆盖保护→删除 全链路（本机模式无口令）"""
    import io
    leftover = os.path.join(ROOT, 'cases/demoProject/api/test_admin_upload.py')
    if os.path.isfile(leftover):
        os.remove(leftover)
    boundary = '----dbg'
    payload = ('# 管理后台上传用例\n'
               'from common.hamcrest.hamcrest import assert_that\n\n\n'
               'class TestAdminUpload:\n'
               '    def test_admin_upload_case(self):\n'
               '        assert_that(1).is_equal_to(1)\n').encode()
    body = (('--%s\r\nContent-Disposition: form-data; name="kind"\r\n\r\ncases\r\n'
             '--%s\r\nContent-Disposition: form-data; name="subdir"\r\n\r\ndemoProject/api\r\n'
             '--%s\r\nContent-Disposition: form-data; name="file"; filename="test_admin_upload.py"\r\n'
             'Content-Type: text/x-python\r\n\r\n') % (boundary, boundary, boundary)).encode() \
        + payload + ('\r\n--%s--\r\n' % boundary).encode()
    code, body_resp, _ = http('POST', '/api/admin/upload', raw_body=body,
                              headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    d = json.loads(body_resp)
    assert d['ok'], d
    assert d['path'] == 'cases/demoProject/api/test_admin_upload.py'
    assert os.path.isfile(os.path.join(ROOT, d['path']))
    # 语法非法文件被拒
    bad = b'class Broken:\n  def x(:\n'
    body2 = (('--%s\r\nContent-Disposition: form-data; name="kind"\r\n\r\ncases\r\n'
              '--%s\r\nContent-Disposition: form-data; name="file"; filename="test_bad.py"\r\n\r\n') % (boundary, boundary)).encode() \
        + bad + ('\r\n--%s--\r\n' % boundary).encode()
    code, body_resp, _ = http('POST', '/api/admin/upload', raw_body=body2,
                              headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    assert json.loads(body_resp)['ok'] is False and '语法' in json.loads(body_resp)['msg']
    # 列表可见
    code, body_resp, _ = http('GET', '/api/admin/files?kind=cases')
    paths = [f['path'] for f in json.loads(body_resp)['files']]
    assert 'cases/demoProject/api/test_admin_upload.py' in paths
    # 删除（v2 接口：path 为相对项目根的完整路径）
    code, body_resp, _ = http('DELETE', '/api/admin/file?path=cases%2FdemoProject%2Fapi%2Ftest_admin_upload.py')
    assert json.loads(body_resp)['ok']
    assert not os.path.isfile(os.path.join(ROOT, 'cases/demoProject/api/test_admin_upload.py'))
    # 列表可见性（统一列表）
    code, body_resp, _ = http('GET', '/api/admin/files?kind=cases')
    paths = [f['path'] for f in json.loads(body_resp)['files']]
    assert 'cases/demoProject/api/test_admin_upload.py' not in paths


def test_admin_upload_rejects(platform):
    """文件名规范/路径穿越/超大文件 拒绝"""
    import io
    def multipart(fields, filename='test_x.py', content=b'pass\n'):
        boundary = '----dbg'
        parts = ''.join('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                        % (boundary, k, v) for k, v in fields.items())
        parts += ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
                  'Content-Type: text/x-python\r\n\r\n' % (boundary, filename))
        return (parts.encode() + content + ('\r\n--%s--\r\n' % boundary).encode()), boundary

    body, b = multipart({'kind': 'cases', 'subdir': ''}, filename='not_test.py')
    code, body_resp, _ = http('POST', '/api/admin/upload', raw_body=body,
                              headers={'Content-Type': 'multipart/form-data; boundary=' + b})
    # 非 test_ 前缀 py = 框架公共文件 → 仅管理员可上传（4.4）
    assert json.loads(body_resp)['ok'] is False and '仅管理员' in json.loads(body_resp)['msg']
    body, b = multipart({'kind': 'cases', 'subdir': '../../etc'})
    code, body_resp, _ = http('POST', '/api/admin/upload', raw_body=body,
                              headers={'Content-Type': 'multipart/form-data; boundary=' + b})
    assert json.loads(body_resp)['ok'] is False and '不合法' in json.loads(body_resp)['msg']


def test_admin_token_protected(platform):
    """设置 ADMIN_TOKEN 后无口令访问被拒（子进程验证）"""
    import subprocess as sp
    env = dict(os.environ, ADMIN_TOKEN='secret123', WEB_PLATFORM_PORT='8098')
    proc = sp.Popen([sys.executable, 'web_platform/app.py'], cwd=ROOT, env=env,
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    try:
        base2 = 'http://127.0.0.1:8098'
        import time as _t
        no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = _t.time() + 15
        while _t.time() < deadline:
            try:
                no_proxy.open(base2 + '/api/status', timeout=2)
                break
            except Exception:
                _t.sleep(0.3)
        req = urllib.request.Request(base2 + '/api/admin/files?kind=cases')
        try:
            resp = no_proxy.open(req, timeout=5)
            code = resp.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 401, '无口令应被拒: %s' % code
        req2 = urllib.request.Request(base2 + '/api/admin/files?kind=cases',
                                      headers={'X-Admin-Token': 'secret123'})
        resp2 = no_proxy.open(req2, timeout=5)
        assert resp2.getcode() == 200
    finally:
        proc.terminate()

# ---------------------------------------------------------------- 方案A：文件管理增强
def _upload(platform, filename, content, kind='cases', subdir='demoProject/api', force=False, uploader='测试员A', force_admin=False):
    boundary = '----dbg'
    body = (('--%s\r\nContent-Disposition: form-data; name="kind"\r\n\r\n%s\r\n'
             '--%s\r\nContent-Disposition: form-data; name="subdir"\r\n\r\n%s\r\n'
             '--%s\r\nContent-Disposition: form-data; name="uploader"\r\n\r\n%s\r\n'
             '--%s\r\nContent-Disposition: form-data; name="force"\r\n\r\n%s\r\n'
             '--%s\r\nContent-Disposition: form-data; name="force_admin"\r\n\r\n%s\r\n'
             '--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
             'Content-Type: text/x-python\r\n\r\n') % (
        boundary, kind, boundary, subdir, boundary, uploader, boundary,
        'true' if force else 'false', boundary, 'true' if force_admin else 'false',
        boundary, filename)).encode() + content \
        + ('\r\n--%s--\r\n' % boundary).encode()
    code, resp, _ = http('POST', '/api/admin/upload', raw_body=body,
                         headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    return code, json.loads(resp)


def test_admin_files_unified_list_and_types(platform):
    """统一列表：类型/上传人/受保护标记（TC-078 增强）"""
    leftover = os.path.join(ROOT, 'cases/demoProject/api/test_admin_v2.py')
    if os.path.isfile(leftover):
        os.remove(leftover)
    code, d = _upload(platform, 'test_admin_v2.py', b'pass\n')
    assert d['ok'] and d['path'] == 'cases/demoProject/api/test_admin_v2.py'
    code, body, _ = http('GET', '/api/admin/files')
    d = json.loads(body)
    f = next(x for x in d['files'] if x['path'] == 'cases/demoProject/api/test_admin_v2.py')
    assert f['file_type'] == 'case' and f['type_label'] == '测试用例' and f['uploader'] == '测试员A'
    # 框架公共文件：conftest 受保护
    cf = next(x for x in d['files'] if x['path'].endswith('conftest.py'))
    assert cf['file_type'] == 'framework' and cf['is_protected'] and cf['uploader'] == '框架'
    # 类型筛选
    code, body, _ = http('GET', '/api/admin/files?type=framework')
    assert all(f['file_type'] == 'framework' for f in json.loads(body)['files'])
    # 清理：与其他 admin 用例一致，避免残留文件污染用例树
    os.remove(leftover)


def test_admin_overwrite_backup(platform):
    """覆盖上传：409 带原上传人 → force 后自动生成时间戳备份（3.3/4.3）"""
    import glob as _glob
    for f in _glob.glob(os.path.join(ROOT, 'cases/demoProject/api/test_admin_backup*')):
        os.remove(f)
    code, d = _upload(platform, 'test_admin_backup.py', b'value = 1\n')
    assert d['ok']
    code, d = _upload(platform, 'test_admin_backup.py', b'value = 2\n')
    assert code == 409 and d['exists']
    assert d['meta']['uploader'] == '测试员A' and d['meta']['modify_time'] > 0
    code, d = _upload(platform, 'test_admin_backup.py', b'value = 3\n', force=True, uploader='测试员B')
    assert d['ok'] and d['backed_up']
    target_dir = os.path.join(ROOT, 'cases/demoProject/api')
    backups = [f for f in os.listdir(target_dir) if f.startswith('test_admin_backup_') and f.endswith('_backup.py')]
    assert len(backups) == 1, '应生成一个时间戳备份'
    code, body, _ = http('GET', '/api/admin/files')
    f = next(x for x in json.loads(body)['files'] if x['path'] == 'cases/demoProject/api/test_admin_backup.py')
    assert f['uploader'] == '测试员B' and len(f['backups']) == 1
    # 清理
    os.remove(os.path.join(target_dir, 'test_admin_backup.py'))
    os.remove(os.path.join(target_dir, backups[0]))


def test_admin_protected_delete_denied(platform):
    """受保护文件：删除/重命名默认 403；force_admin 显式放行（4.4）"""
    # 上传一个非 test_ 前缀用例文件 → 自动归类为受保护框架文件
    if os.path.isfile(os.path.join(ROOT, 'cases/app_ui/conftest_custom.py')):
        os.remove(os.path.join(ROOT, 'cases/app_ui/conftest_custom.py'))
    code, d = _upload(platform, 'conftest_custom.py', b'# custom\n', subdir='app_ui')
    assert d['ok'] is False and '仅管理员' in d['msg'], d  # 框架文件默认禁止上传
    code, d = _upload(platform, 'conftest_custom.py', b'# custom\n', subdir='app_ui', force_admin=True)
    assert d['ok'], d
    assert d['path'] == 'cases/app_ui/conftest_custom.py'
    rel = d['path']
    code, body, _ = http('DELETE', '/api/admin/file?path=' + urllib.parse.quote(rel, safe=''))
    d = json.loads(body)
    assert code == 403 and '仅管理员' in d['msg'], d
    code, body, _ = http('POST', '/api/admin/rename',
                         body={'path': rel, 'new_name': 'conftest_custom2.py'})
    assert code == 403 and '仅管理员' in json.loads(body)['msg']
    # 批量删除同样默认跳过受保护文件
    code, body, _ = http('POST', '/api/admin/batch_delete', body={'paths': [rel]})
    d = json.loads(body)
    assert rel in d['denied'] and not d['deleted']
    # force_admin 显式放行后可删除
    code, body, _ = http('POST', '/api/admin/batch_delete',
                         body={'paths': [rel], 'force_admin': True})
    d = json.loads(body)
    assert d['ok'] and rel in d['deleted']
    assert not os.path.isfile(os.path.join(ROOT, rel))


def test_admin_rename_and_folder(platform):
    """重命名 + 新建文件夹"""
    code, d = _upload(platform, 'test_admin_rename.py', b'pass\n')
    assert d['ok']
    code, body, _ = http('POST', '/api/admin/rename',
                         body={'path': 'cases/demoProject/api/test_admin_rename.py',
                               'new_name': 'test_admin_renamed.py'})
    assert json.loads(body)['ok']
    assert os.path.isfile(os.path.join(ROOT, 'cases/demoProject/api/test_admin_renamed.py'))
    code, body, _ = http('POST', '/api/admin/folder', body={'kind': 'cases', 'subdir': 'demoProject/tmp_dir'})
    assert json.loads(body)['ok']
    assert os.path.isdir(os.path.join(ROOT, 'cases/demoProject/tmp_dir'))
    code, body, _ = http('POST', '/api/admin/folder', body={'kind': 'cases', 'subdir': 'demoProject/tmp_dir'})
    assert code == 409
    os.rmdir(os.path.join(ROOT, 'cases/demoProject/tmp_dir'))
    os.remove(os.path.join(ROOT, 'cases/demoProject/api/test_admin_renamed.py'))


def test_admin_batch_download_and_delete(platform):
    """批量下载 zip 与批量删除（受保护自动跳过）"""
    import io as _io
    if os.path.isfile(os.path.join(ROOT, 'cases/demoProject/api/test_admin_batch1.py')):
        os.remove(os.path.join(ROOT, 'cases/demoProject/api/test_admin_batch1.py'))
    code, d = _upload(platform, 'test_admin_batch1.py', b'pass\n')
    assert d['ok']
    # 批量下载（包含一个受保护文件验证不报错）
    import urllib.request as _ur
    import urllib.parse as _up
    opener = _ur.build_opener(_ur.ProxyHandler({}))
    url = BASE + '/api/admin/download_batch?paths=' + _up.quote(
        'cases/demoProject/api/test_admin_batch1.py,cases/app_ui/conftest.py', safe='')
    with opener.open(url, timeout=30) as resp:
        assert resp.getcode() == 200
        import zipfile as _zf
        zf = _zf.ZipFile(_io.BytesIO(resp.read()))
        assert 'demoProject/api/test_admin_batch1.py' in zf.namelist()
    # 批量删除：受保护文件默认跳过
    code, body, _ = http('POST', '/api/admin/batch_delete',
                         body={'paths': ['cases/demoProject/api/test_admin_batch1.py',
                                         'cases/app_ui/conftest.py']})
    d = json.loads(body)
    assert d['ok'] and 'cases/demoProject/api/test_admin_batch1.py' in d['deleted']
    assert 'cases/app_ui/conftest.py' in d['denied']
    assert os.path.isfile(os.path.join(ROOT, 'cases/app_ui/conftest.py'))
    assert not os.path.isfile(os.path.join(ROOT, 'cases/demoProject/api/test_admin_batch1.py'))
