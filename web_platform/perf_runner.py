# -*- coding: utf-8 -*-
"""性能压测任务管理（平台侧）

设计：与用例执行（runner.ExecutionManager）同构但独立——压测用 perf_test/.venv
（Python 3.13 + locust 2.x）跑，与平台主环境（Python 3.8 + flask 1.1.2）完全隔离。

- 每次压测一个 run_id，产物落 output/perf_runs/<run_id>/（配置快照 + 日志 + 报告）
- 子进程：perf_test/.venv/bin/python run_load_test.py --config <快照> --headless
- 状态：RUNNING / FINISHED / FAILED / STOPPED；日志按 offset 增量读取
"""
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime

from perf_config import CONFIG_PATH, PERF_DIR, RUNNER, VENV_PYTHON, read_config, write_config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERF_RUNS_DIR = os.path.join(BASE_DIR, 'output', 'perf_runs')

_lock = threading.Lock()
_tasks = {}          # run_id -> task dict


def _next_run_id():
    today = datetime.now().strftime('%Y%m%d')
    seq = 1
    if os.path.isdir(PERF_RUNS_DIR):
        for name in os.listdir(PERF_RUNS_DIR):
            m = re.match(r'^perf_%s_(\d{3})$' % today, name)
            if m:
                seq = max(seq, int(m.group(1)) + 1)
    return 'perf_%s_%03d' % (today, seq)


def venv_ready():
    """压测专用环境是否已就绪（缺 venv 时页面给出安装指引而不是直接报错）"""
    return os.path.isfile(VENV_PYTHON)


def start_run(values=None, save_first=True):
    """启动一次压测。values=None 表示用当前已保存配置；否则先校验并保存再跑。
    返回 (ok, msg, run_id)"""
    if save_first and values:
        ok, msg = write_config(values)
        if not ok:
            return False, msg, ''
    if not venv_ready():
        return False, ('压测环境未就绪：perf_test/.venv 不存在。'
                       '执行 python3 -m venv perf_test/.venv && perf_test/.venv/bin/pip install -r perf_test/requirements-perf.txt'), ''
    cfg = read_config()
    if not str(cfg.get('common.host') or '').strip():
        return False, '被测服务地址为空，请先填写并保存配置', ''

    with _lock:
        running = [t for t in _tasks.values() if t['status'] == 'RUNNING']
        if running:
            return False, '已有压测任务运行中（%s），请先停止后再启动' % running[0]['run_id'], ''
        run_id = _next_run_id()
        run_dir = os.path.join(PERF_RUNS_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)
        cfg_snapshot = os.path.join(run_dir, 'load_test_config.yaml')
        shutil.copyfile(CONFIG_PATH, cfg_snapshot)
        log_path = os.path.join(run_dir, 'run.log')
        task = {
            'run_id': run_id, 'run_dir': run_dir, 'config': cfg_snapshot,
            'log': log_path, 'status': 'RUNNING', 'started_at': time.time(),
            'ended_at': None, 'error': '', 'report': '', 'proc': None,
        }
        _tasks[run_id] = task

    log_f = open(log_path, 'w', encoding='utf-8')
    env = dict(os.environ)
    env['PYTHONUNBUFFERED'] = '1'
    cmd = [VENV_PYTHON, RUNNER, '--config', cfg_snapshot, '--headless']
    try:
        proc = subprocess.Popen(cmd, cwd=PERF_DIR, stdout=log_f, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    except Exception as e:
        with _lock:
            task['status'] = 'FAILED'
            task['error'] = str(e)
            task['ended_at'] = time.time()
        return False, '启动压测失败：%s' % e, run_id
    with _lock:
        task['proc'] = proc
    threading.Thread(target=_wait, args=(run_id, proc, log_f), daemon=True).start()
    return True, '压测已启动（%s，模式 %s，目标 %s）' % (run_id, cfg.get('mode'), cfg.get('common.host')), run_id


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
            task['error'] = '压测进程退出码 %s（详见日志）' % code
        task['report'] = _collect_report(task)


def _collect_report(task):
    """把压测引擎产出的报告收进 run 目录，返回相对路径（无报告返回 ''）"""
    try:
        import yaml
        with open(task['config'], 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        rel = (cfg.get('report') or {}).get('output_path') or 'reports/load_test_report.html'
        src = os.path.join(PERF_DIR, rel)
        if not os.path.isfile(src):
            return ''
        dst = os.path.join(task['run_dir'], 'report.html')
        shutil.copyfile(src, dst)
        data_src = os.path.splitext(src)[0] + '.data.json'
        if os.path.isfile(data_src):
            shutil.copyfile(data_src, os.path.join(task['run_dir'], 'report.data.json'))
        return os.path.relpath(dst, BASE_DIR)
    except Exception:
        return ''


def stop_run(run_id):
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
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)   # 连 locust 子进程一起收
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
    with _lock:
        task['status'] = 'STOPPED'
        task['ended_at'] = time.time()
        task['report'] = _collect_report(task)
    return True, '已停止压测（%s）' % run_id


def get_run(run_id):
    with _lock:
        t = _tasks.get(run_id)
        if not t:
            return None
        d = {k: v for k, v in t.items() if k != 'proc'}
        d['log_rel'] = os.path.relpath(t['log'], BASE_DIR)
        d['duration_ms'] = int(((t['ended_at'] or time.time()) - t['started_at']) * 1000)
        return d


def list_runs():
    with _lock:
        return [get_run(rid) for rid in sorted(_tasks, reverse=True)]


def read_log(run_id, offset=0):
    with _lock:
        t = _tasks.get(run_id)
        if not t:
            return [], 0
        path = t['log']
    if not os.path.isfile(path):
        return [], 0
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    return lines[offset:], len(lines)
