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


ADMIN_META_FILE = {}   # platform fixture 填充：测试平台进程使用的元数据文件路径（供用例断言）


@pytest.fixture(scope='session')
def platform(tmp_path_factory):
    meta_path = tmp_path_factory.mktemp('admin_meta') / 'admin_meta.json'
    ADMIN_META_FILE['path'] = str(meta_path)
    env = dict(os.environ, WEB_PLATFORM_PORT=str(PORT), PYTHONIOENCODING='utf-8',
               ADMIN_META_PATH=str(meta_path))
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
    for page in ('/', '/run', '/report'):
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

# ---------------------------------------------------------------- 用例管理（上传）
def test_admin_upload_list_delete(platform):
    """上传落盘 + 语法校验拒绝（本机模式无口令）"""
    import io
    leftover = os.path.join(ROOT, 'cases/demoProject/api/test_admin_upload.py')
    if os.path.isfile(leftover):
        os.remove(leftover)
    boundary = '----dbg'
    payload = ('# 用例管理上传用例\n'
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
    # 清理（文件列表已按需求下线，直接按落盘路径清理）
    os.remove(os.path.join(ROOT, 'cases/demoProject/api/test_admin_upload.py'))


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
        req = urllib.request.Request(base2 + '/api/admin/upload_zip_content',
                                     data=b'{}', method='POST',
                                     headers={'Content-Type': 'application/json'})
        try:
            resp = no_proxy.open(req, timeout=5)
            code = resp.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 401, '无口令应被拒: %s' % code
        req2 = urllib.request.Request(base2 + '/api/admin/upload_zip_content',
                                      data=b'{}', method='POST',
                                      headers={'X-Admin-Token': 'secret123',
                                               'Content-Type': 'application/json'})
        try:
            resp2 = no_proxy.open(req2, timeout=5)
            code2 = resp2.getcode()
        except urllib.error.HTTPError as e:
            code2 = e.code
        # 带正确口令：通过鉴权（400 = 空用例包被参数校验拒绝，而非 401）
        assert code2 == 400, '带口令应通过鉴权(400), 实际 %s' % code2
    finally:
        proc.terminate()

# ---------------------------------------------------------------- 方案A：上传增强
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
    # 元数据登记：上传人与备份历史（文件列表已下线，读 admin_meta.json 验证）
    meta = json.load(open(ADMIN_META_FILE['path'], encoding='utf-8'))
    m = meta.get('cases/demoProject/api/test_admin_backup.py', {})
    assert m.get('uploader') == '测试员B' and len(m.get('backups', [])) == 1
    # 清理
    os.remove(os.path.join(target_dir, 'test_admin_backup.py'))
    os.remove(os.path.join(target_dir, backups[0]))


# ---------------------------------------------------------------- 录屏配置
def test_recording_config_roundtrip(platform):
    """录屏配置：GET 读生效值 → POST 落盘 conf → 回读一致；非法值 400 且不落盘"""
    import json as _json
    import shutil as _shutil
    from web_platform.recording_config import CONF_PATH

    code, body, _ = http('GET', '/api/recording/config')
    assert code == 200 and _json.loads(body)['ok']
    cfg = _json.loads(body)['config']
    for k in ('enabled', 'required', 'keep_on_success', 'before_seconds',
              'after_seconds', 'max_segment_seconds', 'bit_rate'):
        assert k in cfg, '缺字段 %s' % k

    # 备份既有 conf（可能不存在），测试后还原
    backup = _shutil.copyfile(CONF_PATH, CONF_PATH + '.bak') if os.path.isfile(CONF_PATH) else None
    try:
        # 合法保存：改全部 7 项
        payload = dict(cfg, before_seconds=8, after_seconds=3, max_segment_seconds=120,
                       bit_rate=6000000, enabled=False, keep_on_success=True, required=False)
        code, body, _ = http('POST', '/api/recording/config', payload)
        assert code == 200 and _json.loads(body)['ok']
        assert os.path.isfile(CONF_PATH), 'conf 未落盘'
        code, body, _ = http('GET', '/api/recording/config')
        cfg2 = _json.loads(body)['config']
        assert (cfg2['before_seconds'], cfg2['after_seconds']) == (8, 3)
        assert (cfg2['max_segment_seconds'], cfg2['bit_rate']) == (120, 6000000)
        assert cfg2['enabled'] is False and cfg2['keep_on_success'] is True and cfg2['required'] is False
        # pytest 侧加载器读同一份 conf（录屏配置单一数据源）
        import importlib
        import common.video_evidence.config as ve_cfg
        importlib.reload(ve_cfg)
        rc = ve_cfg.RecordingConfig(adb_serial='X')
        assert (rc.before_seconds, rc.after_seconds, rc.enabled, rc.keep_on_success) == (8, 3, False, True)
        assert (rc.max_segment_seconds, rc.bit_rate) == (120, 6000000)
        # 越界被钳制/拒绝：max_segment 超上限由保存接口 400 拒绝
        code, body, _ = http('POST', '/api/recording/config',
                             dict(payload, max_segment_seconds=999))
        assert code == 400 and '范围' in _json.loads(body)['msg']
        # 非法整数 400
        code, body, _ = http('POST', '/api/recording/config', dict(payload, before_seconds='abc'))
        assert code == 400 and '不是合法' in _json.loads(body)['msg']
        # 400 后 conf 仍是上一次合法内容（部分写入防护）
        code, body, _ = http('GET', '/api/recording/config')
        assert _json.loads(body)['config']['before_seconds'] == 8
    finally:
        if backup is not None:
            _shutil.move(CONF_PATH + '.bak', CONF_PATH)
        elif os.path.isfile(CONF_PATH):
            os.remove(CONF_PATH)
    # 还原后回读为默认值
    code, body, _ = http('GET', '/api/recording/config')
    assert _json.loads(body)['config']['before_seconds'] == 5
