# -*- coding: utf-8 -*-
"""App 用例失败现场 · 外部观察者（调试阶段 · 与框架零耦合）

平台跑真实 App 用例时，本观察者在旁边**只读旁观**，框架（appOperator/runner/conftest）
一行不改：
- 轮询 ExecutionManager 公开状态 → 发现 app_ui 任务 RUNNING 即开始采集；
- 经 Appium HTTP 旁路抓取会话截图 + UI 树（page_source），经 adb 抓全程 logcat；
- 顺读 run 日志里已有的「▶ 步骤N · 动作 / └ ✔|✖ 结果」行做步骤标定；
- 产物落该 run 目录 trace/ 子目录（只放数据）：steps.jsonl（步骤）+ caps.jsonl（连续采证）
  + caps/*.png|*.xml + logcat.log + meta.json；
- 用例 PASSED → 现场自动删除；失败/停止/异常 → 自动保留（失败自动归档）。

「接入框架」（进程内精确埋点）为调试通过后的下一阶段，本模块届时可整体下线。
"""
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_DIR = os.path.join(BASE_DIR, 'output', 'runs')

POLL_INTERVAL = 5        # 空闲轮询执行状态（秒）
CAPTURE_INTERVAL = 1.5   # 采证间隔（秒）
_SESSION_TIMEOUT = 120   # 等 Appium 会话出现的上限（秒）

# 可在单测中替换的注入口
_running_task = None     # lambda: task dict 或 None（默认接 runner.manager，只读）
_task_status = None      # lambda run_id: 终态字符串
_logcat_factory = None   # lambda udid, log_path: Popen


def _default_running_task():
    """默认数据源：ExecutionManager 公开 API（只读）。延迟导入避免循环依赖。"""
    try:
        from web_platform.runner import manager
        return manager.running_task()
    except Exception:
        return None


def _default_task_status(run_id):
    try:
        from web_platform.runner import manager
        t = manager.get_task(run_id)
        return (t or {}).get('status') or ''
    except Exception:
        return ''


def _default_logcat_factory(udid, log_path):
    env = {k: v for k, v in os.environ.items()
           if k not in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                        'ALL_PROXY', 'all_proxy', 'PYTHONPATH')}
    return subprocess.Popen(['adb', '-s', udid, 'logcat', '-v', 'time'],
                            stdout=open(log_path, 'w', encoding='utf-8'),
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env=env)


_running_task = _running_task or _default_running_task
_task_status = _task_status or _default_task_status
_logcat_factory = _logcat_factory or _default_logcat_factory

# 运行日志里的步骤行（runner 对 app_ui 任务固定开 --log-cli-level=INFO）：
# `▶ 步骤1 · 点击元素` ... `   └ ✔ 成功 · 耗时 120ms` / `   └ ✖ 失败 · xxx`
# 行首时间戳在 run 日志里可能缺失（log_cli 默认格式），有则用、无则用观察墙钟
_STEP_START_RE = re.compile(r'^(?:(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+)?\S*\s*▶ (步骤\d+) · (.+?)\s*$')
_STEP_END_RE = re.compile(r'^.*└ ([✔✖]) (成功|失败)')

_state = {'phase': 'idle', 'run_id': None, 'started': 0, 'steps': 0, 'caps': 0, 'error': ''}
_lock = threading.Lock()


def status():
    with _lock:
        return dict(_state)


def _set_state(**kw):
    with _lock:
        _state.update(kw)


def _http_get(url, timeout=10):
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _appium_base(conf_file):
    """从设备 conf 解析 Appium 地址（只读复用 runtime_config 的解析函数）"""
    try:
        from web_platform.runtime_config import parse_devices_info
        infos = parse_devices_info(conf_file)
        if infos:
            return 'http://%s:%s/wd/hub' % (infos[0]['server_ip'], infos[0]['server_port'])
    except Exception:
        pass
    return ''


def _find_session(base, udid, timeout):
    """在 Appium 服务器上找到目标设备的活动会话（框架创建的同一个 session，只读访问）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = json.loads(_http_get(base + '/sessions').decode('utf-8', 'ignore'))
            sessions = data.get('value') or []
            for s in sessions:
                caps = s.get('capabilities') or s.get('desiredCapabilities') or {}
                if str(caps.get('udid') or caps.get('deviceUDID') or '') == udid:
                    return s.get('sessionId') or s.get('id')
        except Exception:
            pass
        time.sleep(3)
    return None


def _tail_steps(log_path, offset, pending, done, now):
    """顺读 run 日志，把 ▶/└ 行拼成步骤记录。返回新 offset。"""
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(offset)
            new = f.read()
    except OSError:
        return offset
    for line in new.splitlines():
        m = _STEP_START_RE.match(line.strip())
        if m:
            ts = m.group(1) or time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))
            pending.append({'no': m.group(2), 'action': m.group(3), 'ts': ts, 'ok': None, 'detail': ''})
            continue
        m = _STEP_END_RE.search(line)
        if m and pending:
            step = pending.pop(0)
            step['ok'] = (m.group(1) == '✔')
            done.append(step)
    return offset + len(new)


def _observe_run(task):
    """旁观一次 app_ui 执行：从任务 RUNNING 到终态。"""
    run_id = task['run_id']
    run_dir = os.path.join(RUNS_DIR, run_id)
    trace_dir = os.path.join(run_dir, 'trace')
    caps_dir = os.path.join(trace_dir, 'caps')
    os.makedirs(caps_dir, exist_ok=True)
    _set_state(phase='watching', run_id=run_id, started=int(time.time()), steps=0, caps=0, error='')

    base = _appium_base(task.get('conf_file'))
    session_id = None
    logcat = None
    if base and task.get('udid'):
        session_id = _find_session(base, task['udid'], _SESSION_TIMEOUT)
        try:
            logcat = _logcat_factory(task['udid'], os.path.join(trace_dir, 'logcat.log'))
        except Exception:
            logcat = None

    steps_pending, steps_done, caps = [], [], 0
    log_offset = 0
    log_path = os.path.join(BASE_DIR, task.get('log_path') or '')
    n = 0
    while True:
        try:
            log_offset = _tail_steps(log_path, log_offset, steps_pending, steps_done, time.time())
        except Exception:
            pass
        st = _task_status(run_id)
        if st not in ('PENDING', 'RUNNING', ''):
            final = st
            break
        if session_id and base:
            n += 1
            stamp = time.strftime('%Y%m%d_%H%M%S')
            try:
                png = base64.b64decode(json.loads(
                    _http_get('%s/session/%s/screenshot' % (base, session_id)).decode())['value'])
                img_rel = 'caps/cap_%03d_%s.png' % (n, stamp)
                with open(os.path.join(caps_dir, os.path.basename(img_rel)), 'wb') as f:
                    f.write(png)
                xml = json.loads(
                    _http_get('%s/session/%s/source' % (base, session_id)).decode())['value']
                src_rel = 'caps/cap_%03d_%s.xml' % (n, stamp)
                with open(os.path.join(caps_dir, os.path.basename(src_rel)), 'w', encoding='utf-8') as f:
                    f.write(xml or '')
                caps += 1
                with open(os.path.join(trace_dir, 'caps.jsonl'), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'n': n,
                                        'img': img_rel, 'src': src_rel}, ensure_ascii=False) + '\n')
                _set_state(caps=caps, steps=len(steps_done))
            except Exception as e:
                # 会话可能已结束/驱动忙：本次跳过，连续失败不再硬抓
                _set_state(error=str(e)[:120])
        time.sleep(CAPTURE_INTERVAL)

    # 收尾：未闭合的步骤也落盘（崩溃场景）
    steps_done.extend(steps_pending)
    with open(os.path.join(trace_dir, 'steps.jsonl'), 'a', encoding='utf-8') as f:
        for s in steps_done:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')
    meta = {
        'run_id': run_id, 'status': final, 'kind': 'app_ui',
        'udid': task.get('udid') or '', 'device_model': task.get('device_model') or '',
        'app_package': task.get('app_package') or '',
        'started': _state.get('started'), 'ended': int(time.time()),
        'steps': len(steps_done), 'caps': caps,
    }
    with open(os.path.join(trace_dir, 'meta.json'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=2))
    if logcat:
        try:
            logcat.terminate()
        except Exception:
            pass
    if final == 'PASSED':
        shutil.rmtree(trace_dir, ignore_errors=True)   # 通过不留现场（失败自动归档的镜像）


def _loop():
    while True:
        try:
            task = _running_task()
            if task and task.get('kind') == 'app_ui':
                _observe_run(task)
                _set_state(phase='idle', run_id=None)
        except Exception as e:
            _set_state(phase='idle', run_id=None, error=str(e)[:200])
        time.sleep(POLL_INTERVAL)


def start_daemon():
    """平台进程内启动一次（幂等）。"""
    t = threading.Thread(target=_loop, daemon=True, name='app-trace-observer')
    t.start()
    return t


def list_traces():
    """扫描 output/runs/*/trace/meta.json：保留的失败现场（最新在前）。"""
    out = []
    for meta_path in sorted(glob.glob(os.path.join(RUNS_DIR, '*', 'trace', 'meta.json')), reverse=True):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            meta['run_dir'] = os.path.dirname(os.path.dirname(meta_path))
            out.append(meta)
        except Exception:
            continue
    return out


def load_trace(run_id):
    """单条现场：meta + 步骤 + 采证索引（回放页数据源）。"""
    if not re.match(r'^\d{8}_\d{3}$', str(run_id)):
        return None
    trace_dir = os.path.join(RUNS_DIR, run_id, 'trace')
    if not os.path.isdir(trace_dir):
        return None

    def _read_jsonl(name):
        path = os.path.join(trace_dir, name)
        if not os.path.isfile(path):
            return []
        out = []
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
        return out

    meta = {}
    try:
        with open(os.path.join(trace_dir, 'meta.json'), 'r', encoding='utf-8') as f:
            meta = json.load(f)
    except Exception:
        pass
    steps = _read_jsonl('steps.jsonl')
    caps = _read_jsonl('caps.jsonl')
    # 每个步骤挂「步骤后最近的一张采证」（失败现场=动作后的画面）
    for i, s in enumerate(steps):
        s['img'] = None
        s['src'] = None
        try:
            cand = [c for c in caps if str(c.get('ts', '')) >= str(s.get('ts', ''))]
            pick = cand[0] if cand else (caps[-1] if caps else None)
            if pick:
                s['img'] = pick.get('img')
                s['src'] = pick.get('src')
        except Exception:
            continue
        s['index'] = i
    return {'meta': meta, 'steps': steps, 'caps_total': len(caps),
            'has_logcat': os.path.isfile(os.path.join(trace_dir, 'logcat.log'))}


TRACE_FILE_RE = re.compile(r'^(caps/[A-Za-z0-9_]+\.png|caps/[A-Za-z0-9_]+\.xml|logcat\.log)$')


def trace_file(run_id, rel):
    """采证文件路径（白名单校验，杜绝路径穿越）。返回绝对路径或 None。"""
    if not re.match(r'^\d{8}_\d{3}$', str(run_id)):
        return None
    rel = rel.replace('\\', '/')
    if not TRACE_FILE_RE.match(rel):
        return None
    path = os.path.join(RUNS_DIR, run_id, 'trace', rel)
    return path if os.path.isfile(path) else None
