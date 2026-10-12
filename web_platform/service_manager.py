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
import re
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
        from escrcpy.launcher import is_running
        if not is_running():
            return True, 'escrcpy 未在运行'
        # pgrep 直取 pid 再 kill（is_running 同款匹配，不依赖 ps 清点）
        try:
            pr = subprocess.run(['pgrep', '-f', r'Escrcpy\.app/Contents/MacOS'],
                                capture_output=True, text=True, timeout=8)
            for pid in [int(x) for x in pr.stdout.split() if x.isdigit()]:
                try:
                    os.kill(pid, 15)
                except Exception:
                    pass
        except Exception:
            pass
        for _ in range(8):
            time.sleep(1)
            if not is_running():
                return True, 'escrcpy 已关闭'
        # 仍存活：macOS 桌面 App 标准退出兜底
        try:
            subprocess.run(['osascript', '-e', 'tell application "Escrcpy" to quit'],
                           capture_output=True, timeout=10)
        except Exception:
            pass
        for _ in range(5):
            time.sleep(1)
            if not is_running():
                return True, 'escrcpy 已关闭'
        return True, '已发送停止命令，请稍后刷新查看'
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


# ---------------------------------------------------------------- 服务体检与清理
# 术语（2026-10-12 定稿）：未登记占用 = 占端口但不在服务清单的进程；
# 陈旧实例 = 启动时间早于当前主实例的同类服务；健康 / 已停止 = 正常运行 / 未运行。
_TERM_UNREG = '未登记占用'
_TERM_STALE = '陈旧实例'

_WATCH_PORTS = ['8080', '4726', '4000', '4001', '4002', '4003', '4004', '4005']


def _ps_lines():
    """ps axo pid=,lstart=,command=（沙箱/权限受限时返回 []）"""
    try:
        return subprocess.run(['ps', 'axo', 'pid=,lstart=,command='],
                              capture_output=True, text=True, timeout=10).stdout.splitlines()
    except Exception:
        return []


def _port_users():
    """netstat 找监听中的 pid → {port: [pid]}（沙箱可用；不依赖 ps）"""
    users = {}
    try:
        out = subprocess.run(['netstat', '-anv', '-p', 'tcp'], capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return users
    for line in out.splitlines():
        if 'LISTEN' not in line:
            continue
        port_m = re.search(r'\.(%s)\s' % '|'.join(_WATCH_PORTS), line)
        pid_m = re.search(r'LISTEN\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)\s', line)
        if port_m and pid_m and pid_m.group(1) != '0':
            users.setdefault(port_m.group(1), []).append(int(pid_m.group(1)))
    return users


def _svc_start_ts():
    """从 ps 行解析各 pid 启动时间戳"""
    import datetime
    ts = {}
    for line in _ps_lines():
        parts = line.strip().split(None, 6)
        if len(parts) < 7 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        try:
            dt = datetime.datetime.strptime(' '.join(parts[1:6]), '%a %b %d %H:%M:%S %Y')
            ts[pid] = dt.timestamp()
        except Exception:
            continue
    return ts


def inspect_services():
    """全量服务体检：状态 + 判定（健康/未登记占用/陈旧实例）+ 元数据。ps 不可用时降级。"""
    from web_platform.routes import _project_services
    import datetime

    rows = []
    now = datetime.datetime.now().timestamp()
    try:
        services = _project_services()
    except Exception:
        services = []
    svc_pids = {s['pid'] for s in services}
    starts = _svc_start_ts()
    self_pid = os.getpid()
    self_start = starts.get(self_pid, now)

    def add(name, level, status, ports, pid=None, note='', ops=None, started=None):
        rows.append({'name': name, 'level': level, 'status': status,
                     'ports': ports or [], 'pid': pid, 'started': started,
                     'note': note, 'ops': ops or []})

    # 1) 平台服务（登记类别 platform）：自己=当前主实例，早于自己的=陈旧实例
    platforms = sorted([s for s in services if s['kind'] == 'platform'],
                       key=lambda s: starts.get(s['pid'], 0))
    if not platforms:   # ps 不可用降级：至少报告自己
        platforms = [{'pid': self_pid, 'cmd': '(当前实例)'}]
    for s in platforms:
        pid = s['pid']
        st = starts.get(pid)
        started = datetime.datetime.fromtimestamp(st).strftime('%m-%d %H:%M') if st else '—'
        if pid == self_pid:
            add('平台服务', 'ok', '运行中', ['8080'], pid, '当前主实例 · v' + _app_version(),
                ['restart'], started)
        else:
            add('平台服务', 'stale', '运行中', ['8080'], pid,
                _TERM_STALE + '：早于当前实例启动，占用 8080 会导致端口冲突', ['kill'], started)

    # 2) Appium（HTTP 探测）
    from web_platform.runtime_config import check_appium
    appium_ok, _m = check_appium('127.0.0.1', '4726')
    if appium_ok:
        apid = next((s['pid'] for s in services if s['kind'] == 'appium'), None)
        add('Appium', 'ok', '运行中', ['4726'], apid, '真机自动化引擎', ['stop'], _started_of(starts, apid))
    else:
        add('Appium', 'off', '已停止', ['4726'], None, '执行用例时按需自动拉起', ['start'])

    # 3) Maestro MCP（pgrep）
    maestro = _pgrep_pids(r'maestro')
    if maestro:
        add('Maestro MCP', 'ok', '运行中', [], maestro[0], 'AI 用例生成引擎', ['stop'], _started_of(starts, maestro[0]))
    else:
        add('Maestro MCP', 'off', '已停止', [], None, 'AI 用例生成引擎', ['start'])

    # 4) adb（命令探测）
    r = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        add('adb server', 'ok', '运行中', [], None, '手机通信 · 由平台心跳按需管理', [])
    else:
        add('adb server', 'off', '已停止', [], None, '手机通信', ['start'])

    # 5) 报告静态服务（登记类别 report）
    reports = [s for s in services if s['kind'] == 'report']
    if reports:
        stale_n = sum(1 for s in reports if starts.get(s['pid'], now) < self_start - 60)
        level = 'stale' if stale_n else 'ok'
        note = ('%s：%d 个实例早于当前版本，建议清理' % (_TERM_STALE, stale_n)) if stale_n \
            else 'Allure 报告静态服务'
        add('报告静态服务', level, '运行中 ×%d' % len(reports),
            sorted({p for s in reports for p in s['ports']}), reports[0]['pid'], note,
            ['kill_all'] if stale_n else [])
    else:
        add('报告静态服务', 'off', '已停止', [], None, '查看报告时按需拉起', [])

    # 6) escrcpy（launcher 检测）
    try:
        from escrcpy.launcher import status as esc_status
        esc = esc_status()
        if esc.get('running'):
            add('escrcpy 投屏', 'ok', '运行中', [], None, '桌面投屏 App', ['stop'])
        else:
            add('escrcpy 投屏', 'off', esc.get('installed') and '已部署 · 未运行' or '未部署', [], None,
                '桌面投屏 App（escrcpy/ 目录）', ['start'] if esc.get('installed') else [])
    except Exception:
        add('escrcpy 投屏', 'off', '未部署', [], None, 'escrcpy/ 目录缺失', [])

    # 7) 未登记占用：监听中的 pid 不在任何登记服务里（ps 可用才判定，避免误报主实例）
    if services:
        unreg = []
        for port, pids in _port_users().items():
            for pid in pids:
                if pid != self_pid and pid not in svc_pids and pid not in [r.get('pid') for r in rows]:
                    unreg.append((port, pid))
        for port, pid in unreg:
            add('%s :%s' % (_TERM_UNREG, port), 'unreg', '占用端口 %s' % port, [port], pid,
                '占端口但不在服务清单——可能是旧版本残留或手动启动的程序', ['kill'])
    # ps 不可用：不再伪装成服务行，以 notice 形式提示（前端渲染为顶部警示条）
    notice = ('进程清单不可用（ps 权限受限），「陈旧实例/未登记占用」判定降级——'
              '真实判定请在服务器本机终端查看') if not services else None

    return {'ok': True, 'services': rows,
            'summary': {'ok': sum(1 for r in rows if r['level'] == 'ok'),
                        'stale': sum(1 for r in rows if r['level'] == 'stale'),
                        'unreg': sum(1 for r in rows if r['level'] == 'unreg'),
                        'off': sum(1 for r in rows if r['level'] == 'off')},
            'degraded': not services, 'notice': notice}


def _pgrep_pids(pattern):
    try:
        out = subprocess.run(['pgrep', '-f', pattern], capture_output=True, text=True, timeout=8).stdout
        return [int(x) for x in out.split() if x.isdigit()]
    except Exception:
        return []


def _started_of(starts, pid):
    import datetime
    st = starts.get(pid) if pid else None
    return datetime.datetime.fromtimestamp(st).strftime('%m-%d %H:%M') if st else '—'


def _app_version():
    try:
        from web_platform.changelog import APP_VERSION
        return APP_VERSION
    except Exception:
        return '?'


def cleanup_services(targets):
    """清理：stale=杀陈旧实例 pid；unreg=杀未登记占用 pid。返回 (ok, msg)。"""
    killed, failed = 0, 0
    for row in inspect_services()['services']:
        if row['level'] in ('stale', 'unreg') and row['level'] in targets and row.get('pid'):
            try:
                os.kill(row['pid'], 15)
                killed += 1
            except Exception:
                failed += 1
    if not killed and not failed:
        return True, '没有需要清理的%s' % ('陈旧实例与未登记占用' if len(targets) > 1 else '目标')
    return True, '已清理 %d 个进程%s' % (killed, ('，%d 个失败' % failed) if failed else '')

