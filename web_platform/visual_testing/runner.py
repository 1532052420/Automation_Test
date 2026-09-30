# -*- coding: utf-8 -*-
"""视觉测试 · Maestro 运行编排（一期本地模式）

maestro test <flow.yaml> 后台子进程：日志落 run 目录，结束后从 ~/.maestro/tests
收集本run产生的截图，与基线（data/baselines/<流程>/<截图名>.png）做 SSIM 比对，
产出 results.json（same/changed/new 三态 + diff 三联图）。零云端依赖。

 Percy 二期接入点：start_run 内将命令替换为 `percy app:exec -- maestro test ...`
 即可把截图同时推 Percy 云端（见调研文档 Percy_Maestro_视觉测试调研方案.md）。
"""
import glob
import json
import os
import shutil
import subprocess
import threading
import time

from common.appium.visual_assertions import compare_images

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FLOWS_DIR = os.path.join(DATA_DIR, 'flows')
RUNS_DIR = os.path.join(DATA_DIR, 'runs')
BASELINES_DIR = os.path.join(DATA_DIR, 'baselines')
MAESTRO_TESTS_DIR = os.path.expanduser('~/.maestro/tests')
THRESHOLD = 0.95

_procs = {}   # run_id -> Popen（运行中的进程句柄）


def _ts():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _write(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def list_flows():
    if not os.path.isdir(FLOWS_DIR):
        return []
    out = []
    for f in sorted(os.listdir(FLOWS_DIR)):
        if f.endswith(('.yaml', '.yml')):
            p = os.path.join(FLOWS_DIR, f)
            out.append({'name': f.rsplit('.', 1)[0], 'file': f,
                        'size': os.path.getsize(p),
                        'mtime': time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p)))})
    return out


def flow_path(name):
    """流程名 → 安全路径（禁止路径穿越）；不存在返回 None"""
    safe = os.path.basename(str(name or '').strip())
    if not safe:
        return None
    for ext in ('.yaml', '.yml'):
        p = os.path.join(FLOWS_DIR, safe + ext)
        if os.path.isfile(p):
            return p
    return None


def save_flow(name, content):
    safe = os.path.basename(str(name or '').strip())
    if not safe:
        return False, '流程名不能为空'
    if not content or not content.strip():
        return False, '流程内容不能为空（YAML）'
    os.makedirs(FLOWS_DIR, exist_ok=True)
    with open(os.path.join(FLOWS_DIR, safe + '.yaml'), 'w', encoding='utf-8') as f:
        f.write(content)
    return True, '流程已保存'


def delete_flow(name):
    p = flow_path(name)
    if not p:
        return False, '流程不存在'
    os.remove(p)
    return True, '流程已删除'


def list_runs():
    runs = []
    if os.path.isdir(RUNS_DIR):
        for rid in sorted(os.listdir(RUNS_DIR), reverse=True):
            m = _read(os.path.join(RUNS_DIR, rid, 'meta.json'))
            if m:
                runs.append(m)
    return runs


def get_run(run_id):
    rid = os.path.basename(str(run_id or '').strip())
    d = os.path.join(RUNS_DIR, rid)
    if not os.path.isdir(d):
        return None
    meta = _read(os.path.join(d, 'meta.json')) or {}
    results = _read(os.path.join(d, 'results.json')) or []
    log = ''
    logp = os.path.join(d, 'log.txt')
    if os.path.isfile(logp):
        with open(logp, encoding='utf-8', errors='ignore') as f:
            log = f.read()
    return {'meta': meta, 'results': results, 'log': log, 'running': rid in _procs}


def start_run(flow_name):
    p = flow_path(flow_name)
    if not p:
        return None, '流程不存在'
    if _procs:
        return None, '已有运行在进行中（本期单并发）'
    run_id = time.strftime('%Y%m%d_%H%M%S')
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    meta = {'run_id': run_id, 'flow': os.path.basename(p).rsplit('.', 1)[0],
            'status': 'running', 'start': _ts(), 'end': None, 'shots': 0}
    _write(os.path.join(run_dir, 'meta.json'), meta)
    _start(run_id, p, run_dir, meta)
    return run_id, '运行已启动'


def stop_run(run_id):
    proc = _procs.get(os.path.basename(str(run_id or '')))
    if not proc:
        return False, '该运行不在进行中'
    proc.terminate()
    return True, '已发送终止信号'


def _start(run_id, flow_path_, run_dir, meta):
    log_f = open(os.path.join(run_dir, 'log.txt'), 'w', encoding='utf-8')
    mark = time.time() - 1
    proc = subprocess.Popen(['maestro', 'test', flow_path_],
                            stdout=log_f, stderr=subprocess.STDOUT)
    _procs[run_id] = proc
    threading.Thread(target=_finish_when_done, args=(run_id, proc, log_f, mark, run_dir, meta),
                     daemon=True).start()


def _finish_when_done(run_id, proc, log_f, mark, run_dir, meta):
    proc.wait()
    log_f.close()
    _procs.pop(run_id, None)
    meta['status'] = 'failed' if proc.returncode else 'done'
    meta['end'] = _ts()
    try:
        shots = _collect_shots(mark, run_dir)
        meta['shots'] = len(shots)
        _write(os.path.join(run_dir, 'results.json'), _compare_all(meta['flow'], run_dir, shots))
    except Exception as e:
        meta['error'] = str(e)[:200]
    _write(os.path.join(run_dir, 'meta.json'), meta)


def _collect_shots(mark, run_dir):
    """收集本次 run 在 ~/.maestro/tests 新产生的截图（目录 mtime 晚于启动标记）"""
    out_dir = os.path.join(run_dir, 'screenshots')
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    for d in sorted(glob.glob(os.path.join(MAESTRO_TESTS_DIR, '*')), reverse=True):
        if os.path.getmtime(d) < mark:
            continue
        for png in glob.glob(os.path.join(d, '*', 'screenshots', '*.png')):
            base = os.path.basename(png)
            dst = os.path.join(out_dir, base)
            if base not in {s[1] for s in saved}:
                shutil.copyfile(png, dst)
                saved.append((png, base))
    return [b for _, b in saved]


def _compare_all(flow, run_dir, shot_names):
    results = []
    base_dir = os.path.join(BASELINES_DIR, flow)
    for name in shot_names:
        actual = os.path.join(run_dir, 'screenshots', name)
        baseline = os.path.join(base_dir, name)
        item = {'shot': name, 'img': 'screenshots/' + name,
                'baseline': 'baselines/%s/%s' % (flow, name) if os.path.isfile(baseline) else None,
                'state': 'new', 'similarity': None, 'diff': None, 'msg': ''}
        if item['baseline']:
            diff_out = os.path.join(run_dir, 'diffs', name)
            os.makedirs(os.path.dirname(diff_out), exist_ok=True)
            passed, actual_info, err, _ = compare_images(baseline, actual, THRESHOLD, diff_out)
            item['state'] = 'same' if passed else 'changed'
            item['similarity'] = (actual_info or {}).get('similarity')
            item['diff'] = 'diffs/' + name if os.path.isfile(diff_out) else None
            item['msg'] = err or ''
        results.append(item)
    return results


def adopt_baseline(run_id, shot):
    """把某次运行的截图采纳为该流程的基线（Percy「approve」的本地等价动作）"""
    rid = os.path.basename(str(run_id or '').strip())
    shot = os.path.basename(str(shot or '').strip())
    src = os.path.join(RUNS_DIR, rid, 'screenshots', shot)
    if not os.path.isfile(src):
        return False, '截图不存在'
    meta = _read(os.path.join(RUNS_DIR, rid, 'meta.json')) or {}
    dst_dir = os.path.join(BASELINES_DIR, meta.get('flow', ''))
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copyfile(src, os.path.join(dst_dir, shot))
    return True, '已采纳为基线'
