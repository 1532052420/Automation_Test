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
