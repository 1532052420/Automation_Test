# -*- coding: utf-8 -*-
"""Web 执行平台 · 统一配置加载与只读探测

渐进式方案：复用现有 .conf 读取链与 pojo 组装逻辑，不推倒重来。
本模块只提供"读"能力（conf 列表 / devices_info 解析 / 用例树 / adb 设备 / Appium 探测），
执行生命周期由 runner.ExecutionManager 负责。
"""
import ast
import configparser as ConfigParser
import os
import re
import subprocess
import ujson

from pojo.app_ui_devices_info import APP_UI_Devices_Info

# 项目根（本文件位于 <项目根>/platform/ 下）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CASES_APP_UI_DIR = os.path.join(BASE_DIR, 'cases', 'app_ui')
DEMO_CONFIG_DIR = os.path.join(BASE_DIR, 'config', 'demoProject')
PYTEST_CONF = os.path.join(BASE_DIR, 'config', 'pytest.conf')


# 项目名 / 环境名白名单：只允许字母数字下划线，从根上杜绝路径穿越
_NAME_RE = re.compile(r'^[A-Za-z0-9_]{1,32}$')

# 服务地址：只允许 http(s)，且不含空白（防把注释/换行写进 conf）
_URL_RE = re.compile(r'^https?://\S+$')


def _split_values(value):
    """按 || 拆分多设备值（与 base/read_app_ui_devices_info 一致），空串返回 []"""
    return list(filter(None, value.split('||'))) if value else []


class WebPlatformConfig(object):
    """读 config/web_platform.conf：平台端口、报告起始端口（env 可覆盖）"""

    def __init__(self):
        self.port = 8080
        self.report_start_port = 4000
        path = os.path.join(BASE_DIR, 'config', 'web_platform.conf')
        config = ConfigParser.ConfigParser()
        try:
            config.read(path, encoding='utf-8')
            self.port = int(config.get('platform', 'port', fallback='8080'))
            self.report_start_port = int(config.get('platform', 'report_start_port', fallback='4000'))
        except Exception:
            pass
        # 环境变量优先
        self.port = int(os.environ.get('WEB_PLATFORM_PORT', self.port))


def list_devices_conf_files():
    """扫描 config/demoProject/ 下所有 devices_info conf，返回相对项目根的完整路径列表"""
    if not os.path.isdir(DEMO_CONFIG_DIR):
        return []
    files = [f for f in os.listdir(DEMO_CONFIG_DIR)
             if re.match(r'^app_ui_android_devices_info_.+\.conf$', f)]
    # 返回相对项目根的完整路径（parse_devices_info 按该路径拼接，直接给前端展示也明确）
    return sorted(os.path.join('config', 'demoProject', f) for f in files)


def parse_devices_info(conf_file):
    """解析一个 devices_info conf，返回 devices_info 列表（结构同 pojo.get_devices_info）。

    注意：框架的 Read_APP_UI_Devices_Info 是单例（首次读取的 conf 固定，再次传其他 conf
    仍返回第一次结果），平台要支持切换多个 conf，这里直接实例化非单例的 pojo 组装器，
    保证每次按传入 conf 重新解析。
    """
    path = os.path.join(BASE_DIR, conf_file)
    if not os.path.isfile(path):
        return []
    config = ConfigParser.ConfigParser()
    config.read(path, encoding='utf-8')

    devices = APP_UI_Devices_Info()
    devices.devices_desc = _split_values(config.get('devices_info', 'devices_desc', fallback=''))
    devices.app_ui_configs = _split_values(config.get('devices_info', 'app_ui_configs', fallback=''))
    devices.api_configs = _split_values(config.get('devices_info', 'api_configs', fallback=''))
    devices.server_ports = _split_values(config.get('devices_info', 'server_ports', fallback=''))
    devices.server_ips = _split_values(config.get('devices_info', 'server_ips', fallback=''))
    devices.system_auth_alert_labels = _split_values(
        config.get('devices_info', 'system_auth_alert_labels', fallback=''))
    devices.is_enable_system_auth_check = _split_values(
        config.get('devices_info', 'is_enable_system_auth_check', fallback=''))
    devices.udids = _split_values(config.get('devices_info', 'udids', fallback=''))
    devices.platformNames = _split_values(config.get('devices_info', 'platformNames', fallback=''))
    devices.automationNames = _split_values(config.get('devices_info', 'automationNames', fallback=''))
    devices.platformVersions = _split_values(config.get('devices_info', 'platformVersions', fallback=''))
    devices.deviceNames = _split_values(config.get('devices_info', 'deviceNames', fallback=''))
    devices.chromeDriverPorts = _split_values(config.get('devices_info', 'chromeDriverPorts', fallback=''))
    devices.chromeDriverPaths = _split_values(config.get('devices_info', 'chromeDriverPaths', fallback=''))
    devices.recreateChromeDriverSessions = _split_values(
        config.get('devices_info', 'recreateChromeDriverSessions', fallback=''))
    devices.nativeWebScreenshots = _split_values(config.get('devices_info', 'nativeWebScreenshots', fallback=''))
    devices.systemports = _split_values(config.get('devices_info', 'systemports', fallback=''))
    devices.wdaLocalPorts = _split_values(config.get('devices_info', 'wdaLocalPorts', fallback=''))
    devices.appPackages = _split_values(config.get('devices_info', 'appPackages', fallback=''))
    devices.appActivitys = _split_values(config.get('devices_info', 'appActivitys', fallback=''))
    devices.bundleIds = _split_values(config.get('devices_info', 'bundleIds', fallback=''))
    devices.apps_dirs = _split_values(config.get('devices_info', 'apps_dirs', fallback=''))
    devices.apps_urls = _split_values(config.get('devices_info', 'apps_urls', fallback=''))
    devices.noSigns = _split_values(config.get('devices_info', 'noSigns', fallback=''))
    devices.fullResets = _split_values(config.get('devices_info', 'fullResets', fallback=''))
    devices.noResets = _split_values(config.get('devices_info', 'noResets', fallback=''))
    devices.waitForIdleTimeouts = _split_values(config.get('devices_info', 'waitForIdleTimeouts', fallback=''))
    return devices.get_devices_info()


def scan_case_tree(root_dir=None):
    """扫描 root_dir（默认 cases/app_ui）下所有 test_*.py，返回用例树：
    [{'file': 相对项目根路径, 'class_name': 类名, 'methods': [test_方法名, ...],
      'cn_name': 文件头「# 用例中文名：xxx」映射（无则 ''，元素管理同款中文名方案）,
      'mtime': 文件更新时间戳, 'method_descs': {方法: docstring 首行（场景描述）}}]
"""
    root = root_dir or CASES_APP_UI_DIR
    tree = []
    if not os.path.isdir(root):
        return tree
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != '__pycache__' and not d.startswith('.')]
        for fn in sorted(filenames):
            if not (fn.startswith('test_') and fn.endswith('.py')):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, BASE_DIR).replace(os.sep, '/')
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    src = f.read()
            except Exception:
                continue
            try:
                mod = ast.parse(src)
            except SyntaxError:
                continue
            m_cn = re.search(r'^#\s*用例中文名[：:]\s*(.+?)\s*$', src, re.MULTILINE)
            cn_name = m_cn.group(1).strip() if m_cn else ''
            try:
                mtime = int(os.path.getmtime(path))
            except OSError:
                mtime = 0
            for node in mod.body:
                if isinstance(node, ast.ClassDef):
                    methods, descs = [], {}
                    for n in node.body:
                        if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'):
                            methods.append(n.name)
                            try:
                                doc = ast.get_docstring(n)
                            except Exception:
                                doc = None
                            if doc and doc.strip():
                                descs[n.name] = doc.strip().splitlines()[0][:120]
                    if methods:
                        tree.append({'file': rel, 'class_name': node.name, 'methods': methods,
                                     'method_descs': descs, 'cn_name': cn_name, 'mtime': mtime})
    return tree


def list_markers():
    """解析 config/pytest.conf 的 markers= 段，返回 [{'name','desc'}]。
    选项自动生成，使用者不必手写 pytest 标记名。"""
    markers = []
    if not os.path.isfile(PYTEST_CONF):
        return markers
    try:
        with open(PYTEST_CONF, 'r', encoding='utf-8') as f:
            in_markers = False
            for raw in f:
                line = raw.rstrip('\n')
                if re.match(r'^\s*markers\s*=', line):
                    in_markers = True
                    continue
                if not in_markers:
                    continue
                if not line.strip():
                    continue
                if not line.startswith((' ', '\t')):   # 缩进结束即离开 markers 段
                    break
                name, _, desc = line.strip().partition(':')
                name = name.strip()
                if name:
                    markers.append({'name': name, 'desc': desc.strip()})
    except Exception:
        return []
    return markers


def adb_devices():
    """adb devices -l 解析：返回 {'ok': bool, 'msg': str, 'devices': [{udid, state, model}]}"""
    try:
        out = subprocess.check_output(
            ['adb', 'devices', '-l'], stderr=subprocess.STDOUT, timeout=10
        ).decode('utf-8', 'ignore')
    except Exception as e:
        return {'ok': False, 'msg': str(e), 'devices': []}
    devices = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith('List of devices'):
            continue
        parts = line.split()
        if len(parts) >= 2:
            udid, state = parts[0], parts[1]
            model = ''
            for p in parts[2:]:
                if p.startswith('model:'):
                    model = p.split(':', 1)[1].replace('_', ' ')
            devices.append({'udid': udid, 'state': state, 'model': model})
    return {'ok': True, 'msg': '', 'devices': devices}


def check_appium(server_ip, server_port):
    """校验 Appium server 可用性：GET /wd/hub/status。
    兼容两种格式：Appium 1.x JSON Wire 顶层 status==0；Appium 2+/3+ 纯 W3C value.ready==true。
    返回 (ok, err_msg)"""
    import urllib.request
    url = 'http://%s:%s/wd/hub/status' % (server_ip, server_port)
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = ujson.loads(resp.read().decode('utf-8', 'ignore'))
            if body.get('status') == 0:
                return True, ''
            value = body.get('value') or {}
            if value.get('ready') is True:
                return True, ''
            return False, 'Appium /status 未就绪: %s' % body
    except Exception as e:
        return False, str(e)


def find_free_port(start_port):
    """从 start_port 起找一个未被占用的端口（socket 探测）"""
    import socket
    port = start_port
    while port < start_port + 200:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                port += 1
    return start_port