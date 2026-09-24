# -*- coding: utf-8 -*-
"""生成 Midscene 原版渲染器测试报告（v3：复用官方构建产物壳 + 平台数据适配）。

原理（按 midscene_report_ui_拆离方案.md）：su7-full.html 的渲染器代码原样保留，
仅替换数据 script（type="midscene_web_dump"）——UI/尺寸/交互与原版 100% 一致。

数据源：output/runs/<run_id>/allure-results/*.json + result.json
录屏　：output/video_evidence/**（按用例 node 匹配；ffmpeg 抽帧 → recorder 时间轴）
输出　：output/runs/<run_id>/report/report.html（单文件）

用法：python generate_midscene_report.py [run_id] [壳HTML]
"""
import base64
import glob
import json
import os
import re
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_EVIDENCE_DIR = os.path.join(BASE_DIR, 'output', 'video_evidence')
SHELL_CANDIDATES = [
    os.path.expanduser('~/Downloads/su7-full.html'),
    os.path.join(BASE_DIR, 'design', 'midscene-ref', 'su7-full.html'),
]
FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'
FRAME_INTERVAL_MS = 250          # 时间轴帧间隔（连续铺满）


def find_shell():
    for p in SHELL_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise SystemExit('找不到报告壳 su7-full.html（候选: %s）' % SHELL_CANDIDATES)


def load_run(run_id):
    run_dir = os.path.join(BASE_DIR, 'output', 'runs', run_id)
    rp = os.path.join(run_dir, 'result.json')
    if not os.path.isfile(rp):
        raise SystemExit('运行不存在: %s' % rp)
    meta = json.load(open(rp, encoding='utf-8'))
    results = []
    for f in sorted(glob.glob(os.path.join(run_dir, 'allure-results', '*-result.json'))):
        try:
            results.append(json.load(open(f, encoding='utf-8')))
        except Exception:
            pass
    return run_dir, meta, results


def b64_image(path):
    try:
        raw = open(path, 'rb').read()
        mime = 'image/png' if os.path.splitext(path)[1].lower() == '.png' else 'image/jpeg'
        return 'data:%s;base64,%s' % (mime, base64.b64encode(raw).decode())
    except Exception:
        return None


def video_duration_ms(path):
    try:
        r = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'csv=p=0', path], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip() or 0) * 1000
    except Exception:
        return 0


def video_size(path):
    try:
        r = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'v:0',
                            '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path],
                           capture_output=True, text=True, timeout=30)
        w, h = r.stdout.strip().split(',')[:2]
        return {'width': int(w), 'height': int(h), 'dpr': 1}
    except Exception:
        return {'width': 1080, 'height': 2400, 'dpr': 1}


def frame_at(video, offset_ms):
    """录屏 offset_ms 处抽一帧 → jpeg dataURI（失败返回 None）。"""
    try:
        r = subprocess.run([FFMPEG, '-ss', '%.3f' % (offset_ms / 1000.0), '-i', video,
                            '-frames:v', '1', '-q:v', '5', '-f', 'image2pipe',
                            '-vcodec', 'mjpeg', '-'], capture_output=True, timeout=30)
        if r.returncode == 0 and r.stdout:
            return 'data:image/jpeg;base64,' + base64.b64encode(r.stdout).decode()
    except Exception:
        pass
    return None


def find_case_videos(node, udid):
    if not node:
        return []
    prefix = node.replace('/', '__').replace('::', '__') + '__' + (udid or '')
    hits = []
    for sub in ('artifacts', 'tmp'):
        for f in glob.glob(os.path.join(VIDEO_EVIDENCE_DIR, sub, '**', '*.mp4'), recursive=True):
            if os.path.basename(f).startswith(prefix):
                hits.append(f)
    hits.sort(key=lambda f: -os.path.getmtime(f))
    return hits


def node_of(meta, res):
    method = (res.get('fullName') or '').split('#')[-1]
    for n in meta.get('case_nodes') or []:
        if n.endswith('::' + method):
            return n
    return ''


def step_to_action(name):
    n = name or ''
    if n.startswith('点击'):
        return 'Tap'
    if n.startswith('输入'):
        return 'Input'
    if '清除' in n[:6]:
        return 'ClearInput'
    if n.startswith('滑动'):
        return 'Swipe'
    if n.startswith('长按'):
        return 'LongPress'
    return 'Tap'


def png_size(datauri):
    try:
        import struct
        raw = base64.b64decode(datauri.split(',', 1)[1][:64] + '==')
        w, h = struct.unpack('>II', raw[16:24])
        return {'width': w, 'height': h, 'dpr': 3}
    except Exception:
        return None


def size_for(main_shot, v0):
    if not main_shot:
        return None
    return png_size(main_shot) if main_shot.startswith('data:image/png') else video_size(v0)


def build_data(run_id, meta, results, run_dir):
    """平台 Allure 数据 → Midscene 原版报告 schema（含录屏帧时间轴）。"""
    ATT = os.path.join(run_dir, 'allure-results')
    tasks = []
    for res in sorted(results, key=lambda r: r.get('start') or 0):
        case_name = res.get('name') or '用例'
        status = res.get('status') or 'unknown'
        case_start = res.get('start') or 0
        case_stop = max(res.get('stop') or case_start, case_start + 1000)
        node = node_of(meta, res)
        videos = find_case_videos(node, meta.get('udid'))
        v0 = videos[0] if videos else None
        v_dur = video_duration_ms(v0) if v0 else 0
        desc = str(res.get('description') or '')
        reason = ((res.get('statusDetails') or {}).get('message') or '')[:2000]
        failed = status != 'passed'

        # 用例级证据：失败截图 + 失败录屏
        case_shots = []
        for att in res.get('attachments', []) or []:
            if (att.get('type') or '').startswith('image/'):
                d = b64_image(os.path.join(ATT, att.get('source', '')))
                if d:
                    case_shots.append(d)

        # 1) 用例级 Plan 任务（组头）
        tasks.append({
            'status': 'finished' if not failed else 'failed',
            'type': 'Planning', 'subType': 'Plan',
            'param': {'userInstruction': case_name},
            'timing': {'start': case_start, 'end': case_stop, 'cost': case_stop - case_start},
            'uiContext': None,
            'log': {'rawResponse': desc or case_name},
            'output': {'actions': [], 'more_actions_needed_by_instruction': True,
                       'log': desc or case_name, 'yamlFlow': []},
            'recorder': [],
            'cache': {'hit': False},
        })

        # 2) 操作步骤 → Action Space（allure steps 无 time：按步骤数均分用例时间窗）
        steps = res.get('steps') or []
        n_steps = max(1, len(steps))
        win = (case_stop - case_start) / n_steps
        step_tasks = []
        for si, st in enumerate(steps):
            st_time = st.get('time') or {}
            s_start = int(st_time.get('start') or (case_start + si * win))
            s_end = int(st_time.get('stop') or st_time.get('end') or (case_start + (si + 1) * win))
            sub = step_to_action(st.get('name', ''))
            shots = []
            for att in st.get('attachments', []) or []:
                if (att.get('type') or '').startswith('image/'):
                    d = b64_image(os.path.join(ATT, att.get('source', '')))
                    if d:
                        shots.append(d)
            main_shot = shots[0] if shots else None
            rec = []
            # 录屏帧：该步骤时间窗内按 FRAME_INTERVAL_MS 取帧（时间轴连续铺满）
            if v0 and v_dur > 0:
                rel_a = max(0, s_start - case_start)
                rel_b = max(rel_a + FRAME_INTERVAL_MS, s_end - case_start)
                ts = rel_a
                while ts <= rel_b:
                    # 录屏比用例短时：超出段用录屏末帧延续（teardown 静止画面，保证全程有画面）
                    d = frame_at(v0, min(ts, v_dur - 100))
                    if d:
                        rec.append({'type': 'screenshot', 'ts': int(case_start + ts),
                                    'screenshot': d, 'timing': 'after-calling'})
                    ts += FRAME_INTERVAL_MS
            if main_shot and not any(r['ts'] == s_end for r in rec):
                rec.append({'type': 'screenshot', 'ts': s_end, 'screenshot': main_shot,
                            'timing': 'after-calling'})
            if not main_shot and rec:
                main_shot = rec[-1]['screenshot']
            # 失败用例：最后一个步骤 = 失败点，挂失败证据
            if failed and si == n_steps - 1:
                if case_shots and not main_shot:
                    main_shot = case_shots[0]
                if case_shots and not any(r['screenshot'] == case_shots[0] for r in rec):
                    rec.append({'type': 'screenshot', 'ts': s_end, 'screenshot': case_shots[0],
                                'timing': 'after-calling'})
            tasks.append({
                'status': 'finished' if not (failed and si == n_steps - 1) else 'failed',
                'type': 'Action Space', 'subType': sub,
                'param': {'locate': {'description': st.get('name', ''), 'type': 'id',
                                     'value': (re.search(r'\[id:([^\]]+)\]', st.get('name', '')) or [None, ''])[1]
                                     if re.search(r'\[id:([^\]]+)\]', st.get('name', '')) else ''}},
                'subTask': True,
                'timing': {'start': s_start, 'end': s_end, 'cost': s_end - s_start},
                'uiContext': ({'size': size_for(main_shot, v0),
                               'screenshotBase64': main_shot} if main_shot else None),
                'recorder': rec,
            })

        # 3) 失败：断言任务（Print_Assert_Result）
        if failed:
            fail_shots = case_shots
            fail_vids = [v for v in videos if '_failure' in os.path.basename(v)]
            rec = [{'type': 'screenshot', 'ts': int(case_stop), 'screenshot': d,
                    'timing': 'after-calling'} for d in fail_shots[:1]]
            main_shot = fail_shots[0] if fail_shots else None
            tasks.append({
                'status': 'failed', 'type': 'Action Space', 'subType': 'Print_Assert_Result',
                'param': {'result': 'failed', 'expect': '', 'actual': reason[:200]},
                'subTask': True,
                'timing': {'start': case_stop, 'end': case_stop, 'cost': 0},
                'uiContext': ({'size': size_for(main_shot, v0),
                               'screenshotBase64': main_shot} if main_shot else None),
                'output': {'assertion': {'type': 'assertion', 'status': 'failed',
                                         'expected': '', 'actual': reason[:200],
                                         'message': reason[:500]},
                           'log': reason[:300]},
                'recorder': rec,
            })
            if fail_vids:
                tasks[-1]['video'] = fail_vids[0]

    return {
        'sdkVersion': '1.0.3',
        'groupName': 'AutomationTest Report',
        'groupDescription': run_id,
        'executions': [{'logTime': int(time.time() * 1000),
                        'name': 'Action - %s · %s (%s)' % (meta.get('device_model') or '',
                                                           run_id, meta.get('status') or ''),
                        'tasks': tasks}],
        'modelBriefs': [],
    }


def inject_data(shell_html, data):
    """替换壳中的数据 script（官方协议 midscene_web_dump，渲染器启动时读取）。"""
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    scripts = list(re.finditer(
        r'(<script type="midscene_web_dump"[^>]*>\s*)(\{.*?\})(\s*</script>)', shell_html, re.S))
    if not scripts:
        raise SystemExit('壳中未找到数据 script（midscene_web_dump）')
    m = scripts[-1]
    return shell_html[:m.start()] + m.group(1) + payload + m.group(3) + shell_html[m.end():]


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    shell = sys.argv[2] if len(sys.argv) > 2 else find_shell()
    if not run_id:
        runs = sorted(glob.glob(os.path.join(BASE_DIR, 'output', 'runs', '*')), reverse=True)
        if not runs:
            raise SystemExit('output/runs 下没有运行记录')
        run_id = os.path.basename(runs[0])
    run_dir, meta, results = load_run(run_id)
    data = build_data(run_id, meta, results, run_dir)
    html = inject_data(open(shell, encoding='utf-8').read(), data)
    out_dir = os.path.join(run_dir, 'report')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'report.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    n_frames = sum(len(t.get('recorder') or []) for t in data['executions'][0]['tasks'])
    print('已生成: %s' % out)
    print('任务数: %d | 帧数(recorder): %d | 总大小: %.1f MB' % (
        n_tasks_len(data), n_frames, os.path.getsize(out) / 1048576))


def n_tasks_len(data):
    return len(data['executions'][0]['tasks'])


if __name__ == '__main__':
    main()
