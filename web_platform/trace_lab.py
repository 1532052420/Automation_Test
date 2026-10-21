# -*- coding: utf-8 -*-
"""Trace 失败诊断（调试阶段 · 与主框架解耦）

Playwright Trace 级失败诊断的调试链路：操作步骤 + 截图 + DOM 快照 + 网络请求合一回放。
- 录制跑在独立环境 trace_lab/.venv（含 playwright），平台主环境零依赖；
- 子进程：trace_lab/.venv/bin/python trace_lab/record.py <url> <out.zip>
- 产物落 output/trace_runs/<run_id>/（trace.zip + trace.png 整页截图 + run.log）
- 回放用 Playwright 官方 trace viewer（web_platform/static/trace_viewer/ 内置离线副本）

接入用例框架（runner 按步骤埋点）为下一步；届时录制走框架，本模块保留为独立调试入口。
"""
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, redirect, render_template, request, send_file

from web_platform import app_trace_observer as app_observer

bp = Blueprint('trace_lab', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_LAB_DIR = os.path.join(BASE_DIR, 'trace_lab')
VENV_PYTHON = os.path.join(TRACE_LAB_DIR, '.venv', 'bin', 'python')
RECORDER = os.path.join(TRACE_LAB_DIR, 'record.py')
RUNS_DIR = os.path.join(BASE_DIR, 'output', 'trace_runs')

# 产物文件白名单：杜绝 API 直调路径穿越
_FILE_RE = re.compile(r'^(trace\.zip|trace\.png|run\.log)$')
_RUN_ID_RE = re.compile(r'^trace_\d{8}_\d{3}$')
_URL_RE = re.compile(r'^https?://\S{1,500}$')

DEFAULT_URL = 'https://www.baidu.com'

_lock = threading.RLock()   # RLock：list_runs 持锁时嵌套调 get_run（与 perf_runner 同构）
_tasks = {}          # run_id -> task dict
_pw_version_cache = None


def _next_run_id():
    today = datetime.now().strftime('%Y%m%d')
    seq = 1
    if os.path.isdir(RUNS_DIR):
        for name in os.listdir(RUNS_DIR):
            m = re.match(r'^trace_%s_(\d{3})$' % today, name)
            if m:
                seq = max(seq, int(m.group(1)) + 1)
    return 'trace_%s_%03d' % (today, seq)


def venv_ready():
    return os.path.isfile(VENV_PYTHON)


def chromium_ready():
    """浏览器是否已下载：默认缓存在 ~/Library/Caches/ms-playwright/chromium-*，
    设了 PLAYWRIGHT_BROWSERS_PATH=0 时在 driver 包 .local-browsers/ 下，两处都探。"""
    cache_glob = os.path.join(os.path.expanduser('~'), 'Library', 'Caches',
                              'ms-playwright', 'chromium-*')
    local_glob = os.path.join(TRACE_LAB_DIR, '.venv', 'lib', 'python3.*', 'site-packages',
                              'playwright', 'driver', 'package', '.local-browsers', 'chromium-*')
    return bool(glob.glob(cache_glob)) or bool(glob.glob(local_glob))


def playwright_version():
    """venv 内 playwright 版本号（子进程查询，结果缓存；未就绪返回 ''）"""
    global _pw_version_cache
    if not venv_ready():
        return ''
    if _pw_version_cache is None:
        try:
            out = subprocess.run(
                [VENV_PYTHON, '-c',
                 'from importlib.metadata import version;print(version("playwright"))'],
                capture_output=True, text=True, timeout=20)
            _pw_version_cache = (out.stdout or '').strip() or '?'
        except Exception:
            _pw_version_cache = '?'
    return _pw_version_cache


def env_hint():
    """环境未就绪时给人话指引（design-spec：文案说人话，给可执行命令）"""
    if not venv_ready():
        return ('录制环境未就绪：执行 python3 -m venv trace_lab/.venv && '
                'trace_lab/.venv/bin/pip install -r trace_lab/requirements-trace.txt')
    if not chromium_ready():
        return ('浏览器未下载：执行 trace_lab/.venv/bin/playwright install chromium'
                '（约 150MB，仅需一次）')
    return ''


def start_record(url=None):
    """启动一次录制。返回 (ok, msg, run_id)"""
    url = (url or DEFAULT_URL).strip()
    if not _URL_RE.match(url):
        return False, '地址需以 http:// 或 https:// 开头', ''
    if not venv_ready() or not chromium_ready():
        return False, env_hint(), ''
    with _lock:
        running = [t for t in _tasks.values() if t['status'] == 'RUNNING']
        if running:
            return False, '已有录制任务运行中（%s），请先停止或等待结束' % running[0]['run_id'], ''
        run_id = _next_run_id()
        run_dir = os.path.join(RUNS_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)
        log_path = os.path.join(run_dir, 'run.log')
        task = {
            'run_id': run_id, 'run_dir': run_dir, 'url': url,
            'log': log_path, 'status': 'RUNNING', 'started_at': time.time(),
            'ended_at': None, 'error': '', 'proc': None,
        }
        _tasks[run_id] = task

    log_f = open(log_path, 'w', encoding='utf-8')
    env = dict(os.environ)
    env['PYTHONUNBUFFERED'] = '1'
    cmd = [VENV_PYTHON, RECORDER, url, os.path.join(run_dir, 'trace.zip')]
    try:
        proc = subprocess.Popen(cmd, cwd=TRACE_LAB_DIR, stdout=log_f, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    except Exception as e:
        with _lock:
            task['status'] = 'FAILED'
            task['error'] = str(e)
            task['ended_at'] = time.time()
        return False, '启动录制失败：%s' % e, run_id
    with _lock:
        task['proc'] = proc
    threading.Thread(target=_wait, args=(run_id, proc, log_f), daemon=True).start()
    return True, '录制已启动（%s，目标 %s）' % (run_id, url), run_id


def _wait(run_id, proc, log_f):
    code = proc.wait()
    try:
        log_f.close()
    except Exception:
        pass
    with _lock:
        task = _tasks.get(run_id)
        if not task:
            return
        task['ended_at'] = time.time()
        task['status'] = 'FINISHED' if code == 0 else 'FAILED'
        if code != 0:
            task['error'] = '录制进程退出码 %s（详见日志）' % code


def stop_record(run_id):
    with _lock:
        task = _tasks.get(run_id)
        if not task:
            return False, '任务不存在'
        if task['status'] != 'RUNNING':
            return False, '任务已结束'
        proc = task.get('proc')
    if proc:
        try:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
    with _lock:
        task['status'] = 'STOPPED'
        task['ended_at'] = time.time()
    return True, '已停止录制（%s）' % run_id


def get_run(run_id):
    """单次录制详情：状态 + 是否已产出 trace.zip（列表页与详情轮询共用）"""
    with _lock:
        t = _tasks.get(run_id)
        task = {k: v for k, v in t.items() if k != 'proc'} if t else None
    if task is None:
        # 进程重启后内存任务丢失，仅从磁盘恢复产物信息
        run_dir = os.path.join(RUNS_DIR, run_id)
        if not _RUN_ID_RE.match(run_id) or not os.path.isdir(run_dir):
            return None
        task = {'run_id': run_id, 'run_dir': run_dir, 'url': '',
                'status': 'FINISHED', 'error': '',
                'started_at': os.path.getmtime(os.path.join(run_dir, 'run.log'))
                if os.path.isfile(os.path.join(run_dir, 'run.log')) else time.time(),
                'ended_at': None}
    task['has_zip'] = os.path.isfile(os.path.join(task['run_dir'], 'trace.zip'))
    task['has_png'] = os.path.isfile(os.path.join(task['run_dir'], 'trace.png'))
    task['duration_ms'] = int(((task['ended_at'] or time.time()) - task['started_at']) * 1000)
    return task


def list_runs():
    """全部录制：内存任务 + 磁盘上的历史产物（进程重启不丢）"""
    run_ids = set()
    with _lock:
        run_ids.update(_tasks)
    if os.path.isdir(RUNS_DIR):
        run_ids.update(n for n in os.listdir(RUNS_DIR) if _RUN_ID_RE.match(n))
    runs = [get_run(r) for r in sorted(run_ids, reverse=True)]
    return [r for r in runs if r]


def read_log(run_id, offset=0):
    if not _RUN_ID_RE.match(run_id):
        return [], 0
    path = os.path.join(RUNS_DIR, run_id, 'run.log')
    if not os.path.isfile(path):
        return [], 0
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    return lines[offset:], len(lines)


def delete_run(run_id):
    if not _RUN_ID_RE.match(run_id):
        return False, '非法任务号'
    with _lock:
        task = _tasks.get(run_id)
        if task and task['status'] == 'RUNNING':
            return False, '录制运行中，请先停止再删除'
    run_dir = os.path.join(RUNS_DIR, run_id)
    if not os.path.isdir(run_dir):
        return False, '产物目录不存在'
    shutil.rmtree(run_dir, ignore_errors=True)
    return True, '已删除（%s）' % run_id


# ---------------------------------------------------------------- 页面与 API
@bp.route('/trace-lab')
def page_trace_lab():
    return render_template('trace_lab.html')


@bp.route('/api/trace-lab/status')
def api_status():
    return jsonify({
        'ok': True, 'running': any(t['status'] == 'RUNNING' for t in _tasks.values()),
        'venv_ready': venv_ready(), 'chromium_ready': chromium_ready(),
        'playwright_version': playwright_version(), 'hint': env_hint(),
    })


@bp.route('/api/trace-lab/record', methods=['POST'])
def api_record():
    ok, msg, run_id = start_record((request.json or {}).get('url'))
    return jsonify({'ok': ok, 'msg': msg, 'run_id': run_id})


@bp.route('/api/trace-lab/stop', methods=['POST'])
def api_stop():
    run_id = (request.json or {}).get('run_id') or ''
    with _lock:
        running = [t for t in _tasks if t and _tasks[t]['status'] == 'RUNNING']
    ok, msg = stop_record(running[0] if (not run_id and running) else run_id)
    return jsonify({'ok': ok, 'msg': msg})


@bp.route('/api/trace-lab/runs')
def api_runs():
    return jsonify({'ok': True, 'runs': list_runs()})


@bp.route('/api/trace-lab/run/<run_id>')
def api_run_detail(run_id):
    offset = request.args.get('offset', 0, type=int)
    task = get_run(run_id)
    if not task:
        return jsonify({'ok': False, 'msg': '任务不存在'}), 404
    lines, total = read_log(run_id, offset)
    task['log_lines'] = lines
    task['log_total'] = total
    return jsonify(task)


@bp.route('/api/trace-lab/run/<run_id>/delete', methods=['POST'])
def api_run_delete(run_id):
    ok, msg = delete_run(run_id)
    return jsonify({'ok': ok, 'msg': msg})


@bp.route('/trace-lab/file/<run_id>/<fname>')
def api_run_file(run_id, fname):
    if not _RUN_ID_RE.match(run_id) or not _FILE_RE.match(fname):
        return jsonify({'ok': False, 'msg': '非法路径'}), 404
    path = os.path.join(RUNS_DIR, run_id, fname)
    if not os.path.isfile(path):
        return jsonify({'ok': False, 'msg': '文件不存在'}), 404
    if fname.endswith('.log'):
        return send_file(path, mimetype='text/plain')
    return send_file(path, as_attachment=(request.args.get('dl') == '1'))


@bp.route('/trace-lab/viewer/<run_id>')
def page_viewer(run_id):
    """跳转内置 Playwright trace viewer 并加载该次 trace（同源加载，无需 CORS）。
    trace 参数必须是绝对 URL：viewer 的 service worker 只认带 scheme+host 的地址，
    相对路径会以其自身作用域解析导致加载失败（实测 SW 转发 500）。"""
    if not _RUN_ID_RE.match(run_id):
        return jsonify({'ok': False, 'msg': '非法任务号'}), 404
    target = request.host_url.rstrip('/') + '/trace-lab/file/%s/trace.zip' % run_id
    return redirect('/static/trace_viewer/index.html?trace=' + quote(target, safe=''))


# ---------------------------------------------------------------- App 失败现场（外部观察者，与框架零耦合）
# 观察者守护线程随平台进程启动：只读旁观真实 app_ui 执行（Appium HTTP 旁路采证 + adb logcat），
# 框架代码零改动；用例 PASSED 自动清现场，失败自动保留。
app_observer.start_daemon()

_RUN_ID_APP_RE = re.compile(r'^\d{8}_\d{3}$')


@bp.route('/api/trace-lab/app/status')
def api_app_observer_status():
    return jsonify(dict(app_observer.status(), ok=True))


@bp.route('/api/trace-lab/app/traces')
def api_app_traces():
    return jsonify({'ok': True, 'traces': app_observer.list_traces()})


@bp.route('/api/trace-lab/app/<run_id>')
def api_app_trace_detail(run_id):
    data = app_observer.load_trace(run_id)
    if not data:
        return jsonify({'ok': False, 'msg': '现场不存在或已清理'}), 404
    return jsonify(dict(data, ok=True, run_id=run_id))


@bp.route('/api/trace-lab/app/<run_id>/logcat')
def api_app_trace_logcat(run_id):
    """logcat 切片：取某步骤时间点前后各 lines/2 行（logcat -v time 无年份，按 MM-DD HH:MM 匹配）。"""
    ts = request.args.get('ts') or ''
    lines = max(20, min(int(request.args.get('lines', 200)), 800))
    path = app_observer.trace_file(run_id, 'logcat.log')
    if not path:
        return jsonify({'ok': False, 'msg': 'logcat 不存在'}), 404
    key = ts[5:16] if len(ts) >= 16 else ''
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        all_lines = f.read().splitlines()
    idx = 0
    if key:
        for i, l in enumerate(all_lines):
            if key in l:
                idx = i
                break
    half = lines // 2
    return jsonify({'ok': True, 'lines': all_lines[max(0, idx - half):idx + half],
                    'total': len(all_lines), 'hit': bool(key)})


@bp.route('/trace-lab/app/<run_id>/<path:rel>')
def api_app_trace_file(run_id, rel):
    path = app_observer.trace_file(run_id, rel)
    if not path:
        return jsonify({'ok': False, 'msg': '文件不存在'}), 404
    if path.endswith('.xml'):
        return send_file(path, mimetype='text/xml')
    return send_file(path)


@bp.route('/trace-lab/app-replay/<run_id>')
def page_app_replay(run_id):
    if not _RUN_ID_APP_RE.match(run_id) or not app_observer.load_trace(run_id):
        return jsonify({'ok': False, 'msg': '现场不存在或已清理'}), 404
    return render_template('app_trace.html', run_id=run_id)
