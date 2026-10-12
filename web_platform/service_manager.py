# -*- coding: utf-8 -*-
"""平台托管服务管理 · 手动开关 / 页面心跳 / 5 小时未用自动关闭

需求（2026-10-12 用户）：
- 所有服务默认关闭：平台启动不自动拉起 Appium/Maestro 等（runner 执行用例前按需自启，见 runner.py）；
- 开关：首页卡片右上角开关图标，点击启停对应服务；
- 自动关闭：所有平台网页都关掉（心跳停止）满 5 小时 → 自动关闭仍在运行的托管服务。

托管服务与命令（appium 3.7.0 / maestro 2.10.0 实探）：
- appui   Appium      /Users/ouyang/homebrew/bin/appium --port 4726 --base-path /wd/hub --address 127.0.0.1
- aicase  Maestro MCP /Users/ouyang/.maestro/bin/maestro mcp
- connect adb server  adb start-server / adb kill-server（kill 后任何 adb 命令会自动拉起）
- escrcpy 投屏应用    escrcpy.launcher.launch / 按 svc 类别 kill
状态判定复用 routes._project_services / check_appium，本模块不重复实现。
"""
import json
import os
import subprocess
import threading
import time

from web_platform.runtime_config import BASE_DIR

_STATE_PATH = os.path.join(BASE_DIR, 'config', 'service_usage.json')
_LOG_PATH = os.path.join(BASE_DIR, 'logs', 'service_autoclose.log')

APPIUM_BIN = '/Users/ouyang/homebrew/bin/appium'
MAESTRO_BIN = '/Users/ouyang/.maestro/bin/maestro'

AUTO_CLOSE_SECONDS = 5 * 3600    # 心跳停止满 5 小时自动关闭
_CHECK_INTERVAL = 300            # 自动关闭巡检间隔（秒）
_LOCK = threading.Lock()

_state = {'last_beat': 0.0, 'auto_closed_at': 0.0}
_loaded = False


def _load_state():
    global _state, _loaded
    if _loaded:
        return _state
    try:
        with open(_STATE_PATH, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            _state.update({k: float(saved.get(k, 0) or 0) for k in ('last_beat', 'auto_closed_at')})
    except Exception:
        pass
    _loaded = True
    return _state


def _save_state():
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_state, f)
    except Exception:
        pass


def touch_beat():
    """页面心跳：任一平台页面在轮询即视为「平台生态在使用」。"""
    with _LOCK:
        _load_state()
        _state['last_beat'] = time.time()
        _save_state()


def last_beat_age():
    """返回心跳距今秒数；从未心跳返回 None"""
    _load_state()
    if not _state.get('last_beat'):
        return None
    return max(0.0, time.time() - _state['last_beat'])


def _log(msg):
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass


def _kill_by_kinds(kinds):
    """按 svc 类别杀进程（复用 routes._project_services 的识别），返回被杀 pid 数"""
    from web_platform.routes import _project_services
    killed = 0
    for s in _project_services():
        if s['kind'] in kinds and not s.get('current'):
            try:
                os.kill(s['pid'], 15)
                killed += 1
            except Exception:
                pass
    return killed


def _wait_appui_ready(seconds=30):
    """轮询 Appium /status 就绪"""
    from web_platform.runtime_config import check_appium
    for _ in range(max(1, int(seconds / 2.5))):
        time.sleep(2.5)
        ok, _m = check_appium('127.0.0.1', '4726')
        if ok:
            return True
    return False


def _wait_kind(kind, seconds=10):
    """轮询 ps 直到看到指定类别进程（用户环境 ps 可用；沙箱受限时以超时为准）"""
    from web_platform.routes import _project_services
    for _ in range(max(1, int(seconds / 1.5))):
        time.sleep(1.5)
        if any(s['kind'] == kind for s in _project_services()):
            return True
    return False


def start_service(svc):
    """启动托管服务并【轮询等待就绪】再返回——保证调用方拿到结果时状态可探测。
    返回 (ok, msg)。沙箱/命令缺失时如实报错。"""
    if svc == 'appui':
        cmd = [APPIUM_BIN, '--port', '4726', '--base-path', '/wd/hub', '--address', '127.0.0.1']
        log = open(os.path.join(BASE_DIR, 'logs', 'appium.log'), 'ab')
    elif svc == 'aicase':
        cmd = [MAESTRO_BIN, 'mcp']
        log = open(os.path.join(BASE_DIR, 'logs', 'maestro.log'), 'ab')
    elif svc == 'connect':
        r = subprocess.run(['adb', 'start-server'], capture_output=True, text=True, timeout=20)
        return r.returncode == 0, 'adb server 已启动' if r.returncode == 0 else (r.stderr or '启动失败')
    elif svc == 'escrcpy':
        from escrcpy.launcher import launch
        ok, info = launch()
        if not ok:
            return False, info
        return True, 'escrcpy 已启动'
    else:
        return False, '该服务不支持托管启停（平台自身模块）'
    try:
        subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    except Exception as e:
        return False, '启动失败: %s' % str(e)[:120]
    # 轮询就绪：避免「命令已下发但状态还没起来」的窗口期
    if svc == 'appui':
        return (True, 'Appium 已就绪 (:4726/wd/hub)') if _wait_appui_ready(30) \
            else (False, 'Appium 启动超时（30s 未就绪），请到 logs/appium.log 查看日志')
    if svc == 'aicase':
        return (True, 'Maestro MCP 已启动') if _wait_kind('maestro', 10) \
            else (False, 'Maestro MCP 启动超时，请到 logs/maestro.log 查看')
    return True, '已启动' 


def stop_service(svc):
    """停止托管服务并【轮询确认已消失】再返回。返回 (ok, msg)。"""
    if svc == 'escrcpy':
        n = _kill_by_kinds({'escrcpy'})
        gone = all(s['kind'] != 'escrcpy' for s in _project_services())
        return (True, 'escrcpy 已关闭' if gone else '停止超时，请稍后刷新查看')
    kinds = {'appui': {'appium'}, 'aicase': {'maestro'}}.get(svc)
    if not kinds:
        return False, '该服务不支持托管启停（平台自身模块）'
    n = _kill_by_kinds(kinds)
    if not n:
        # ps 不可用/未匹配到进程时，用 HTTP 探测确认是否真的没在运行——杜绝假「未在运行」
        if 'appium' in kinds:
            from web_platform.runtime_config import check_appium
            ok, _m = check_appium('127.0.0.1', '4726')
            if ok:
                return False, '无法定位 Appium 进程（进程列表不可用），请在终端手动停止后重试'
        return True, '未在运行'
    for _ in range(8):   # 确认进程真正退出（kill 后退出有延迟）
        time.sleep(1)
        if all(s['kind'] not in kinds for s in _project_services()):
            return True, '已停止'
    return True, '已发送停止命令，进程退出稍慢，请稍后刷新查看'


def auto_close_check():
    """心跳停止满 AUTO_CLOSE_SECONDS → 关闭仍在运行的托管服务（平台自身除外）。"""
    age = last_beat_age()
    if age is None or age < AUTO_CLOSE_SECONDS:
        return None
    with _LOCK:
        _load_state()
        if time.time() - _state.get('auto_closed_at', 0) < AUTO_CLOSE_SECONDS:
            return None   # 同一轮离线期只关一次
        from web_platform.routes import _project_services
        kinds_present = {s['kind'] for s in _project_services()}
        closed = []
        for svc, kind in (('appui', 'appium'), ('aicase', 'maestro'),
                          ('escrcpy', 'escrcpy'), ('connect', 'adb')):
            if kind in kinds_present:
                ok, msg = stop_service(svc)
                if ok:
                    closed.append(svc)
        _state['auto_closed_at'] = time.time()
        _save_state()
        if closed:
            _log('心跳停止 %.1f 小时，自动关闭： %s' % (age / 3600.0, ','.join(closed)))
        return closed


def _auto_close_loop():
    while True:
        try:
            auto_close_check()
        except Exception:
            pass
        time.sleep(_CHECK_INTERVAL)


def start_auto_close_daemon():
    t = threading.Thread(target=_auto_close_loop, name='service-auto-close', daemon=True)
    t.start()
    auto_close_check()   # 启动时先查一轮
    return t
