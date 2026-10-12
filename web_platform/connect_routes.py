# -*- coding: utf-8 -*-
"""设备连接（SoloPi 无线化）· 连接配置 / 扫码二维码 / adb 无线管理

能力（对应调研 docs/远程扫码连接设备方案调研.md 的「底座 + 扫码层」路线）：
- 连接配置持久化（config/connect_settings.json）：二维码模式 adbwifi / url / custom、
  主机 IP（留空自动探测局域网地址）、端口、配对服务名/密码、自定义文本（{host} {port} 占位）
- 扫码二维码：GET /api/connect/qrcode → PNG（qrcode + Pillow 本地生成，页面无外链）
  · adbwifi：Android 11+ 官方无线调试配对串 WIFI:T:ADB;S:..;P:..;;（手机「无线调试→配对设备」扫码）
  · url：平台地址（手机浏览器/应用扫码打开）
  · custom：自定义文本模板
- adb 无线管理：设备列表（区分 USB/无线）、adb connect / disconnect、usb→tcpip 5555、
  SoloPi APK 一键安装（APK 放 tools/solopi/*.apk）

首页入口与「扫码连接」弹窗见 templates/index.html + static/app.js 的 initIndex/openQrConnectModal。
"""
import glob
import io
import json
import os
import re
import socket
import subprocess
import threading

from flask import Blueprint, jsonify, request, send_file

from web_platform.runtime_config import BASE_DIR, adb_devices

bp = Blueprint('connect', __name__)

_CFG_PATH = os.path.join(BASE_DIR, 'config', 'connect_settings.json')
_SOLOPI_APK_DIR = os.path.join(BASE_DIR, 'tools', 'solopi')
_QR_TIMEOUT = 12          # adb 命令超时（秒）
_INSTALL_TIMEOUT = 300    # APK 安装超时（秒，包体大时较慢）

_CFG_LOCK = threading.Lock()

DEFAULTS = {
    'mode': 'adbwifi',             # adbwifi | url | custom
    'host': '',                    # 空 = 自动探测本机局域网 IP
    'port': 8080,                  # 平台端口（url 模式）
    'adb_port': 5555,              # adb tcpip 端口（tcpip 动作用）
    'service': 'AutomationTest',   # adbwifi 配对服务名
    'password': 'autotest123',     # adbwifi 配对密码
    'custom': 'http://{host}:{port}/connect',   # 自定义二维码文本（支持占位符）
}

_ADDR_RE = re.compile(r'^(\d{1,3}\.){3}\d{1,3}(:\d{2,5})?$')
_UDID_RE = re.compile(r'^[A-Za-z0-9_\.\-:]+$')


def _detect_host():
    """取本机局域网源 IP（UDP connect 不发包，只查路由）；失败回退 127.0.0.1"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('223.5.5.5', 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith('127.'):
            return ip
    except Exception:
        pass
    return '127.0.0.1'


def _load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(_CFG_PATH, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        for k in DEFAULTS:
            if k in saved and saved[k] not in (None, ''):
                cfg[k] = saved[k]
    except Exception:
        pass   # 首次/损坏时用默认值
    return cfg


def _save_cfg(cfg):
    os.makedirs(os.path.dirname(_CFG_PATH), exist_ok=True)
    with open(_CFG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _payload(cfg):
    """按配置生成二维码文本，返回 (payload, host)"""
    host = (str(cfg.get('host') or '').strip()) or _detect_host()
    mode = cfg.get('mode')
    if mode == 'url':
        return 'http://%s:%s/connect' % (host, cfg.get('port', 8080)), host
    if mode == 'custom':
        text = str(cfg.get('custom') or '')
        return text.replace('{host}', host).replace('{port}', str(cfg.get('port', 8080))), host
    # 默认 adbwifi：Android 官方无线调试配对串（与 Android Studio「二维码配对」同协议）
    return 'WIFI:T:ADB;S:%s;P:%s;;' % (cfg.get('service', ''), cfg.get('password', '')), host


def _clean_cfg(cfg):
    """对外输出前裁剪：仅白名单键 + 端口转 int"""
    out = {}
    for k in DEFAULTS:
        v = cfg.get(k, DEFAULTS[k])
        if k in ('port', 'adb_port'):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = DEFAULTS[k]
        out[k] = v
    return out


def _qr_png(text):
    import qrcode
    img = qrcode.make(text, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return buf


def _run_adb(args, timeout=_QR_TIMEOUT):
    """执行 adb 命令：返回 (ok, 输出末尾文本)"""
    try:
        r = subprocess.run(['adb'] + args, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or '') + (r.stderr or '')
        return r.returncode == 0, out.strip()[-400:]
    except FileNotFoundError:
        return False, 'adb 不可用：请确认已安装 Android platform-tools'
    except subprocess.TimeoutExpired:
        return False, 'adb 命令超时（%ss）' % timeout
    except Exception as e:
        return False, str(e)[:200]


# ---------------------------------------------------------------- 页面
@bp.route('/connect')
def page_connect():
    from flask import render_template
    return render_template('connect.html')


# ---------------------------------------------------------------- 连接配置 + 二维码
@bp.route('/api/connect/info')
def api_connect_info():
    cfg = _clean_cfg(_load_cfg())
    payload, host = _payload(cfg)
    apks = sorted(glob.glob(os.path.join(_SOLOPI_APK_DIR, '*.apk')))
    return jsonify({
        'ok': True,
        'config': cfg,
        'payload': payload,
        'detected_host': _detect_host(),
        'solopi': {'apk_dir': os.path.relpath(_SOLOPI_APK_DIR, BASE_DIR),
                   'apks': [os.path.basename(a) for a in apks]},
    })


@bp.route('/api/connect/config', methods=['POST'])
def api_connect_config():
    body = request.get_json(silent=True) or {}
    with _CFG_LOCK:
        cfg = _load_cfg()
        for k in DEFAULTS:
            if k in body:
                v = body[k]
                if k in ('port', 'adb_port'):
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        return jsonify({'ok': False, 'msg': '%s 必须是数字' % k})
                if not isinstance(v, str):
                    v = str(v)
                if len(v) > 500:
                    return jsonify({'ok': False, 'msg': '%s 过长（上限 500 字符）' % k})
                cfg[k] = v.strip() if isinstance(v, str) else v
        if cfg['mode'] not in ('adbwifi', 'url', 'custom'):
            return jsonify({'ok': False, 'msg': '未知二维码模式: %s' % cfg['mode']})
        if cfg['mode'] == 'adbwifi':
            if not re.match(r'^[A-Za-z0-9_\-]{1,32}$', cfg['service']):
                return jsonify({'ok': False, 'msg': '配对服务名限 1-32 位字母/数字/中划线/下划线'})
            if len(cfg['password']) < 8:
                return jsonify({'ok': False, 'msg': '配对密码至少 8 位（Android 无线调试要求）'})
        _save_cfg(cfg)
    cfg = _clean_cfg(cfg)
    payload, host = _payload(cfg)
    return jsonify({'ok': True, 'msg': '已保存', 'config': cfg, 'payload': payload})


@bp.route('/api/connect/qrcode')
def api_connect_qrcode():
    """二维码 PNG：默认用当前配置生成；?text= 临时预览其他文本（上限 800 字符）"""
    text = (request.args.get('text') or '').strip()
    if not text:
        cfg = _clean_cfg(_load_cfg())
        text, _host = _payload(cfg)
    if len(text) > 800:
        return jsonify({'ok': False, 'msg': '二维码内容过长（上限 800 字符）'})
    try:
        return send_file(_qr_png(text), mimetype='image/png')
    except Exception as e:
        return jsonify({'ok': False, 'msg': '二维码生成失败: %s' % str(e)[:120]}), 500


# ---------------------------------------------------------------- adb 无线管理
@bp.route('/api/connect/devices')
def api_connect_devices():
    d = adb_devices()
    for dev in d.get('devices', []):
        dev['wireless'] = ':' in dev.get('udid', '')
    return jsonify(d)


@bp.route('/api/connect/adb', methods=['POST'])
def api_connect_adb():
    """无线连接动作：connect(地址) / disconnect(地址) / tcpip(udid 转无线)"""
    body = request.get_json(silent=True) or {}
    action = body.get('action')
    addr = str(body.get('addr') or '').strip()
    udid = str(body.get('udid') or '').strip()
    if action == 'connect':
        if not _ADDR_RE.match(addr):
            return jsonify({'ok': False, 'msg': '地址格式应为 IP:端口，如 192.168.1.20:5555'})
        ok, out = _run_adb(['connect', addr])
        return jsonify({'ok': ok, 'msg': ('已连接 %s' % addr) if ok else out, 'output': out})
    if action == 'disconnect':
        if not _ADDR_RE.match(addr):
            return jsonify({'ok': False, 'msg': '地址格式应为 IP:端口'})
        ok, out = _run_adb(['disconnect', addr])
        return jsonify({'ok': ok, 'msg': ('已断开 %s' % addr) if ok else out, 'output': out})
    if action == 'tcpip':
        if not _UDID_RE.match(udid):
            return jsonify({'ok': False, 'msg': '设备序列号不合法'})
        port = str(body.get('port') or 5555)
        ok, out = _run_adb(['-s', udid, 'tcpip', port])
        if ok:
            ok2, out2 = _run_adb(['-s', udid, 'shell', 'ip', '-f', 'inet', 'addr', 'show', 'wlan0'])
            tip = ''
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', out2)
            if m:
                tip = '；设备 Wi-Fi IP: %s:%s' % (m.group(1), port)
        return jsonify({'ok': ok, 'msg': ('已切换 %s 为无线模式（端口 %s）%s' % (udid, port, tip)) if ok else out,
                        'output': out})
    return jsonify({'ok': False, 'msg': '未知动作: %s' % action})


# ---------------------------------------------------------------- SoloPi APK 部署
@bp.route('/api/connect/solopi/install', methods=['POST'])
def api_solopi_install():
    """一键安装 SoloPi APK（tools/solopi/ 下第一个 apk；可传 apk 指定文件名）到指定设备"""
    body = request.get_json(silent=True) or {}
    udid = str(body.get('udid') or '').strip()
    if not _UDID_RE.match(udid):
        return jsonify({'ok': False, 'msg': '设备序列号不合法'})
    apk = str(body.get('apk') or '').strip()
    if apk:
        if '/' in apk or '..' in apk or not apk.endswith('.apk'):
            return jsonify({'ok': False, 'msg': 'APK 文件名不合法'})
        path = os.path.join(_SOLOPI_APK_DIR, apk)
    else:
        found = sorted(glob.glob(os.path.join(_SOLOPI_APK_DIR, '*.apk')))
        if not found:
            return jsonify({'ok': False, 'msg':
                            '未检测到 SoloPi APK：请从 GitHub alipay/SoloPi Releases 下载安装包，'
                            '放入项目 %s/ 目录后重试'
                            % os.path.relpath(_SOLOPI_APK_DIR, BASE_DIR)})
        path = found[0]
    if not os.path.exists(path):
        return jsonify({'ok': False, 'msg': 'APK 不存在: %s' % apk})
    ok, out = _run_adb(['-s', udid, 'install', '-r', path], timeout=_INSTALL_TIMEOUT)
    return jsonify({'ok': ok, 'msg': ('SoloPi 已安装到 %s' % udid) if ok else out, 'output': out})


# ---------------------------------------------------------------- SoloPi 用例导入
# 2026-10-12 新增：把手机 SoloPi 录制回放导出的 JSON 转换为平台三件套（元素/页面/用例）
# 并经 admin_routes.import_case_package 整体入库（两阶段语法校验 + 备份 + 受管路径校验）。
# schema 要点（实测样本 tools/solopi/samples/）：operationLog 是 JSON 字符串需二次解析；
# resourceId 分隔符为 `:id/`；operationParam dict/字符串混存；输入 text 默认加密不可还原。
_SOLOPI_IMPORT_DIR = os.path.join(BASE_DIR, 'tools', 'solopi', 'import')
_CASES_DIR = 'cases/app_ui/android/demoProject'
_PAGES_DIR = 'page_objects/app_ui/android/demoProject/pages'
_ELEMENTS_DIR = 'page_objects/app_ui/android/demoProject/elements'


def _pascal_case(case_id):
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', case_id) if p]
    return ''.join(p[:1].upper() + p[1:] for p in parts) or 'SolopiCase'


def _solopi_parse(content):
    """解析 SoloPi 导出 JSON → 预览结构。返回 (info, err)"""
    try:
        d = json.loads(content)
    except Exception as e:
        return None, 'JSON 解析失败: %s' % str(e)[:80]
    try:
        log = d.get('operationLog')
        steps_raw = json.loads(log)['steps'] if isinstance(log, str) else (log or {}).get('steps', [])
    except Exception as e:
        return None, 'operationLog 解析失败: %s' % str(e)[:80]
    if not isinstance(steps_raw, list) or not steps_raw:
        return None, '用例没有步骤（operationLog.steps 为空）'
    steps, warnings = [], []
    for i, s in enumerate(steps_raw):
        m = s.get('operationMethod') or {}
        action = str(m.get('actionEnum') or '').strip("'")
        n = s.get('operationNode') or {}
        rid, xp, desc = n.get('resourceId', ''), n.get('xpath', ''), n.get('description', '')
        text = n.get('text', '')
        p = m.get('operationParam', {})
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = {}
        name = rid.split(':id/')[-1] if ':id/' in rid else 'node%d' % i
        if ':id/' in rid:
            control, mapped = '%s (ID)' % rid, True
        elif xp:
            control, mapped = 'XPATH 兜底', True
        else:
            control, mapped = '无控件信息', False
        input_text, encrypted = '', False
        if action == 'CLICK_AND_INPUT':
            raw = p.get('text', '')
            encrypted = bool(raw) and all(c in '0123456789ABCDEFabcdef' for c in raw)
            input_text = '' if encrypted else raw
            if encrypted:
                warnings.append('步骤%d 的输入内容被 SoloPi 加密，生成后请在用例中填写真实文字' % (i + 1))
        steps.append({'idx': i, 'action': action, 'control': control,
                      'elementName': name if mapped else '',
                      'mapped': mapped and (action in ('CLICK', 'CLICK_AND_INPUT')),
                      'inputText': input_text, 'inputEncrypted': encrypted,
                      'note': desc or text})
    return {'caseName': str(d.get('caseName') or '未命名'), 'caseDesc': str(d.get('caseDesc') or ''),
            'targetAppPackage': str(d.get('targetAppPackage') or ''),
            'steps': steps, 'warnings': warnings}, None


@bp.route('/api/solopi/import/pull', methods=['POST'])
def api_solopi_import_pull():
    """从在线设备拉取 SoloPi 导出目录的用例文件清单（不下载内容，仅列表）"""
    body = request.get_json(silent=True) or {}
    udid = str(body.get('udid') or '').strip()
    if not _UDID_RE.match(udid):
        return jsonify({'ok': False, 'msg': '设备序列号不合法'})
    ok, out = _run_adb(['-s', udid, 'shell', 'ls', '/storage/emulated/0/solopi/export/'])
    if not ok:
        return jsonify({'ok': False, 'msg': '读取导出目录失败：%s' % out})
    files = [l.strip() for l in out.splitlines() if l.strip().endswith('.json')]
    return jsonify({'ok': True, 'files': files})


@bp.route('/api/solopi/import/pull_file', methods=['POST'])
def api_solopi_import_pull_file():
    """adb pull 指定导出文件到 tools/solopi/import/ 并返回解析预览"""
    body = request.get_json(silent=True) or {}
    udid = str(body.get('udid') or '').strip()
    name = os.path.basename(str(body.get('name') or ''))
    if not _UDID_RE.match(udid) or not name.endswith('.json'):
        return jsonify({'ok': False, 'msg': '参数不合法'})
    os.makedirs(_SOLOPI_IMPORT_DIR, exist_ok=True)
    local = os.path.join(_SOLOPI_IMPORT_DIR, name)
    ok, out = _run_adb(['-s', udid, 'pull', '/storage/emulated/0/solopi/export/%s' % name, local],
                       timeout=60)
    if not ok or not os.path.exists(local):
        return jsonify({'ok': False, 'msg': '拉取失败：%s' % out})
    info, err = _solopi_parse(open(local, encoding='utf-8', errors='replace').read())
    if err:
        return jsonify({'ok': False, 'msg': err})
    info['localFile'] = os.path.relpath(local, BASE_DIR)
    return jsonify({'ok': True, **info})


@bp.route('/api/solopi/import/parse', methods=['POST'])
def api_solopi_import_parse():
    """解析上传的 JSON 文本 → 预览（供「上传 JSON」入口）"""
    body = request.get_json(silent=True) or {}
    content = str(body.get('content') or '')
    if len(content) > 2 * 1024 * 1024:
        return jsonify({'ok': False, 'msg': '文件过大（上限 2MB）'})
    info, err = _solopi_parse(content)
    if err:
        return jsonify({'ok': False, 'msg': err})
    return jsonify({'ok': True, **info})


@bp.route('/api/solopi/import/generate', methods=['POST'])
def api_solopi_import_generate():
    """按预览结果生成三件套并整体入库。body: {content 或 localFile, caseId, inputs:{idx:text}}"""
    from web_platform.admin_routes import import_case_package
    body = request.get_json(silent=True) or {}
    content = str(body.get('content') or '')
    if not content:
        local = str(body.get('localFile') or '')
        if local.endswith('.json') and '..' not in local:
            abs_local = os.path.join(BASE_DIR, local)
            if os.path.exists(abs_local):
                content = open(abs_local, encoding='utf-8', errors='replace').read()
    if not content:
        return jsonify({'ok': False, 'msg': '缺少用例 JSON（content 或 localFile）'})
    info, err = _solopi_parse(content)
    if err:
        return jsonify({'ok': False, 'msg': err})
    case_id = re.sub(r'[^A-Za-z0-9_]+', '_', str(body.get('caseId') or '')).strip('_').lower()
    if not case_id or not re.match(r'^[a-z]', case_id):
        case_id = 'solopi_%d' % int(time.time())
    cls = _pascal_case(case_id)
    inputs = body.get('inputs') or {}
    pkg = info['targetAppPackage'] or 'com.recordlife.kuaige'

    # 元素抽取（ID 优先，无 id 退回 SoloPi 自带 xpath）
    elements = {}
    for st in info['steps']:
        if not st['mapped'] or st['elementName'] in elements:
            continue
        n = json.loads(content)   # 重新取原始节点（预览里没有 xpath 全文）
        raw = json.loads(n.get('operationLog'))['steps'][st['idx']].get('operationNode') or {}
        rid, xp = raw.get('resourceId', ''), raw.get('xpath', '')
        if ':id/' in rid:
            loc = "Locator_Type.ID, '%s'" % rid
        elif xp:
            loc = "Locator_Type.XPATH, '%s'" % xp.replace("'", '')
        else:
            continue
        cn = (raw.get('description') or raw.get('text') or st['elementName']).replace("'", '')[:20]
        elements[st['elementName']] = (loc, cn)

    # 页面方法 + 用例调用
    methods, calls, unmapped = [], [], []
    for st in info['steps']:
        i, action, el = st['idx'], st['action'], st['elementName']
        if action == 'BACK':
            methods.append(("press_back", None, "按返回键", "self.appOperator.press_keycode(4)"))
            calls.append("        page.press_back()")
        elif action == 'HANDLE_ALERT':
            methods.append(("handle_alert_%d" % i, None, "处理系统弹窗（SoloPi 自动关闭动作）",
                            "self.appOperator.press_keycode(4)  # 也可改配平台弹窗自动关闭规则"))
            calls.append("        page.handle_alert_%d()" % i)
        elif action == 'CLICK' and el in elements:
            methods.append(("click_%s" % el, None, "点击「%s」" % (elements[el][1] or el),
                            "self.appOperator.click(self._elements.%s)" % el))
            calls.append("        page.click_%s()" % el)
        elif action == 'CLICK_AND_INPUT' and el in elements:
            txt = str((inputs or {}).get(str(i)) or (inputs or {}).get(i) or '<请填写输入内容>').replace("'", '')
            methods.append(("input_%s" % el, 'text', "输入内容",
                            "self.appOperator.sendText(self._elements.%s, text)" % el))
            calls.append("        page.input_%s('%s')" % (el, txt))
        else:
            unmapped.append('步骤%d(%s)' % (i + 1, action))
            calls.append("        # TODO 步骤%d action=%s：无法自动映射，请人工改写" % (i + 1, action))
    if not methods:
        return jsonify({'ok': False, 'msg': '没有可自动转换的步骤，请检查 JSON 内容'})

    elem_lines = ["        self.%s = CreateElement.create(%s, wait_type=Wait_By.VISIBILITY_OF, "
                  "wait_seconds=6, desc='%s')  # %s" % (name, loc, cn, cn)
                  for name, (loc, cn) in elements.items()]
    m_lines = []
    for name, sig, desc, mbody in methods:
        args = '' if sig is None else ', ' + sig
        m_lines.append("    def %s(self%s):\n        \"\"\"%s\"\"\"\n        %s" % (name, args, desc, mbody))

    files = [
        {'dir': _ELEMENTS_DIR, 'name': '%sElements.py' % case_id,
         'content': "# -*- coding: utf-8 -*-\n"
                    "# 本文件由「SoloPi 用例导入」自动生成（来源用例：%s · 目标 %s）\n"
                    "from page_objects.createElement import CreateElement\n"
                    "from page_objects.app_ui.locator_type import Locator_Type\n"
                    "from page_objects.app_ui.wait_type import Wait_Type as Wait_By\n\n\n"
                    "class %sElements:\n    def __init__(self):\n%s\n"
                    % (info['caseName'], pkg, cls, '\n'.join(elem_lines))},
        {'dir': _PAGES_DIR, 'name': '%sPage.py' % case_id,
         'content': "# -*- coding: utf-8 -*-\n# 页面对象（SoloPi 导入自动生成）\n"
                    "from page_objects.app_ui.android.demoProject.elements.%sElements import %sElements\n\n\n"
                    "class %sPage:\n\n    def __init__(self, appOperator):\n"
                    "        self.appOperator = appOperator\n"
                    "        self._elements = %sElements()\n\n%s\n"
                    % (case_id, cls, cls, cls, '\n\n'.join(m_lines))},
        {'dir': _CASES_DIR, 'name': 'test_%s.py' % case_id,
         'content': (
             "# -*- coding: utf-8 -*-\n"
             f"# 用例中文名：{info['caseName']}（SoloPi 录制导入 · {info['caseDesc']}）\n"
             f"# 目标 App：{pkg} · 原始步骤数：{len(info['steps'])}"
             + (f"；未自动映射：{'、'.join(unmapped)}" if unmapped else '') + "\n"
             "import time\nimport allure\n"
             "from base.app_ui.android.demoProject.app_ui_android_demoProject_client "
             "import APP_UI_Android_demoProject_Client\n"
             f"from page_objects.app_ui.android.demoProject.pages.{case_id}Page import {cls}Page\n\n\n"
             "@allure.parent_suite('快歌APP自动化')\n@allure.suite('solopi_import')\n"
             f"class Test{cls}:\n\n"
             "    def setup_class(self):\n"
             "        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)\n"
             "        self.appOperator = self.demoProjectClient.appOperator\n"
             f"        self.appOperator.start_activity('{pkg}', '{pkg}.feature.main.MainActivity')\n"
             "        time.sleep(3)\n"
             f"        self.page = {cls}Page(self.appOperator)\n\n"
             f"    @allure.title('{info['caseName']}：SoloPi 录制回放')\n"
             f"    def test_{case_id}(self):\n"
             f"        \"\"\"SoloPi 导入用例：{info['caseDesc']}\"\"\"\n"
             "        page = self.page\n\n" + '\n'.join(calls) + "\n")},
    ]
    result, code = import_case_package(package=case_id, files=files, uploader='solopi-import')
    if not result.get('ok'):
        return jsonify({'ok': False, 'msg': result.get('msg') or '入库失败'}), code
    msg = '已生成并入库 %d 个文件（%s）' % (len(files), '、'.join(f['name'] for f in files))
    if unmapped:
        msg += '；%d 步未自动映射已在用例中标注 TODO' % len(unmapped)
    return jsonify({'ok': True, 'msg': msg, 'files': [f['name'] for f in files]})
