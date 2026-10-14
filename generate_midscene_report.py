# -*- coding: utf-8 -*-
"""生成 Midscene 原版渲染器风格的测试报告（一比一复刻 su7.html）。

原理（按 midscene_report_ui_拆离方案.md）：复用官方报告构建产物 su7-full.html 的
渲染器（webpack 内嵌 script），仅替换其中的报告数据 JSON——UI/交互/尺寸与原版
100% 一致（同一份代码），本脚本只承担「Adapter」职责：平台 Allure 数据 →
Midscene 报告 schema（拆离方案第 6/7/8/10/12 节统一数据协议）。

数据源：output/runs/<run_id>/allure-results/*.json + result.json
输出　：output/runs/<run_id>/report/report.html（单文件，双击即可打开）

用法：python generate_midscene_report.py [run_id] [壳HTML]（缺省 = 最新运行 + ~/Downloads/su7-full.html）
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
    os.path.join(BASE_DIR, 'design', 'midscene-ref', 'su7-full.html'),
    os.path.expanduser('~/Downloads/su7-full.html'),
]
FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'


def report_version():
    """报告版本号 = 平台版本号（web_platform/changelog.py 唯一数据源）。

    报告顶部展示 v<该值>；报告相关改动随平台版本号一起递增，
    不再展示官方壳的 sdkVersion 1.0.3。正则提取避免 import 副作用。"""
    m = re.search(r"APP_VERSION\s*=\s*'([\d.]+)'",
                  open(os.path.join(BASE_DIR, 'web_platform', 'changelog.py'),
                       encoding='utf-8').read())
    return m.group(1) if m else 'unknown'


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
        probe = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'csv=p=0', path], capture_output=True, text=True, timeout=30)
        return float(probe.stdout.strip() or 0) * 1000
    except Exception:
        return 0


def video_resolution(path):
    """ffprobe 获取录屏真实分辨率，返回 {'width','height'} 或 None。

    渲染器 iG 以首个 uiContext.size 作为全局画布尺寸——录屏分辨率
    就是回放画布的权威来源。"""
    try:
        probe = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'v:0',
                                '-show_entries', 'stream=width,height',
                                '-of', 'csv=p=0', path],
                               capture_output=True, text=True, timeout=30)
        parts = (probe.stdout.strip() or '').split(',')
        if len(parts) >= 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            return {'width': int(parts[0]), 'height': int(parts[1]), 'dpr': 1}
    except Exception:
        pass
    return None


def frame_datauri(video, offset_ms):
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


def quoted_text(name):
    """从步骤名抽「」内的实际输入值，如 输入「su7」 → su7。"""
    m = re.search(r'[「"]([^」"]{1,200})[」"]', name or '')
    return m.group(1) if m else (name or '')


def image_size(datauri):
    """从 dataURI 解析图片真实像素尺寸。

    坑史：旧版 png_size() 用 PNG IHDR 结构去解 JPEG 字节，解出
    width=8 亿像素的天文数字，渲染器画布直接爆炸（replay 全废）。
    JPEG 需扫 SOF0/1/2 标记段取宽高，PNG 读 IHDR，两者不可混用。"""
    try:
        raw = base64.b64decode(datauri.split(',', 1)[1][:65536])
        if raw[:8] == b'\x89PNG\r\n\x1a\n':
            import struct
            w, h = struct.unpack('>II', raw[16:24])
            if 0 < w < 100000 and 0 < h < 100000:
                return {'width': w, 'height': h, 'dpr': 1}
        if raw[:2] == b'\xff\xd8':
            import struct
            i = 2
            while i + 9 < len(raw):
                if raw[i] != 0xFF:
                    i += 1
                    continue
                marker = raw[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                    h, w = struct.unpack('>HH', raw[i + 5:i + 9])
                    if 0 < w < 100000 and 0 < h < 100000:
                        return {'width': w, 'height': h, 'dpr': 1}
                    break
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                else:
                    seg_len = struct.unpack('>H', raw[i + 2:i + 4])[0]
                    i += 2 + seg_len
    except Exception:
        pass
    return None


def build_data(run_id, meta, results, run_dir):
    """平台 Allure 数据 → Midscene 原版报告 schema。"""
    ATT = os.path.join(run_dir, 'allure-results')
    run_start = None
    tasks = []
    for res in sorted(results, key=lambda r: r.get('start') or 0):
        case_name = res.get('name') or '用例'
        status = res.get('status') or 'unknown'
        case_start = res.get('start') or 0
        case_stop = res.get('stop') or case_start
        run_start = case_start if run_start is None else min(run_start, case_start)
        node = node_of(meta, res)
        videos = find_case_videos(node, meta.get('udid'))
        v0 = videos[0] if videos else None
        v_dur = video_duration_ms(v0) if v0 else 0
        v_res = video_resolution(v0) if v0 else None
        desc = str(res.get('description') or '')
        # 回放画布尺寸：录屏分辨率优先；无录屏时回落首个能解析出尺寸的截图。
        case_size = dict(v_res) if v_res else None

        def frames_for(ws, we, want):
            """时间窗内从录屏取 want 帧 dataURI（窗口均分）。"""
            out = []
            if not v0 or v_dur <= 0:
                return out
            ra = max(0, ws - case_start)
            rb = max(0, min(v_dur, we - case_start))
            if rb <= ra:
                ra, rb = 0, min(v_dur, 1000)
            n = max(1, min(want, int((rb - ra) / 200) or 1))
            for i in range(n):
                ts = ra + (rb - ra) * (i + 0.5) / n
                d = frame_datauri(v0, ts)
                if d:
                    out.append((int(case_start + ts), d))
            return out

        # 每个步骤 → 官方三段式任务（与 su7 任务序列一致）：
        #   Planning/Plan（计划组头）→ Planning/Locate（元素定位）→ Action Space/动作（执行）
        # 每个步骤的 Plan 点开即有 Replay（渲染器按「到下一个 Plan 之间」生成回放帧）。
        steps = res.get('steps') or []
        n_steps = max(1, len(steps))
        win = (case_stop - case_start) / n_steps
        for si, st in enumerate(steps):
            st_time = st.get('time') or {}
            s_start = int(st_time.get('start') or (case_start + si * win))
            s_end = int(st_time.get('stop') or st_time.get('end') or (case_start + (si + 1) * win))
            raw_name = st.get('name', '')
            sub = step_to_action(raw_name)
            m = re.search(r'\[id:([^\]]+)\]', raw_name)
            desc_clean = re.sub(r'\s*\[[^\]]*\]\s*', ' ', raw_name).strip() or raw_name
            locate = {'description': raw_name}
            if m:
                locate.update({'value': m.group(1), 'type': 'id'})
            # 元素真实坐标：执行框架 click/sendText 写入的 element_rect 附件（官方高亮框数据源）
            el_rect = el_center = None
            for att in st.get('attachments', []) or []:
                if att.get('name') == 'element_rect' and (att.get('type') or '').startswith('application/json'):
                    try:
                        meta_r = json.load(open(os.path.join(ATT, att.get('source', '')), encoding='utf-8'))
                        el_rect = meta_r.get('rect')
                        el_center = meta_r.get('center')
                    except Exception:
                        pass
            if el_rect and el_center:
                locate['rect'] = el_rect
                locate['center'] = el_center
            # 官方 Input 任务 param 带 value（实际输入内容）
            action_param = {'locate': locate}
            if sub == 'Input':
                action_param['value'] = quoted_text(raw_name)
            # yamlFlow 官方键名：aiTap/aiInput/aiClearInput/aiSwipe/aiLongPress
            yf = {({**{'Tap': 'aiTap', 'Input': 'aiInput', 'ClearInput': 'aiClearInput',
                      'Swipe': 'aiSwipe', 'LongPress': 'aiLongPress'}}.get(sub, 'aiTap')): ''}
            if sub == 'Input':
                yf['value'] = action_param.get('value', '')
            yf['locate'] = desc_clean

            # 帧来源：录屏抽帧优先；无录屏回落步骤附件截图
            shots = []
            for att in st.get('attachments', []) or []:
                if (att.get('type') or '').startswith('image/'):
                    d = b64_image(os.path.join(ATT, att.get('source', '')))
                    if d:
                        shots.append(d)
            fr = frames_for(s_start, s_end, max(3, int((s_end - s_start) / 700) or 1)) if v0 else []
            if not fr and shots:
                fr = [((2 * s_start + s_end) // 3, shots[0])]
            fr_plan, fr_loc, fr_act = fr[:1], fr[1:2], fr[2:]

            def _rec(frames):
                return [{'type': 'screenshot', 'ts': ts, 'screenshot': d,
                         'timing': 'after-calling', 'description': desc_clean}
                        for ts, d in frames]

            # 时间窗三段连续衔接（官方模式：Plan → Locate(极短) → Action）
            p_end = s_start + max(200, int((s_end - s_start) * 0.25))
            l_end = p_end + min(200, max(1, s_end - p_end - 200))
            st_status = 'finished' if (st.get('status') in (None, 'passed', 'finished')) else 'failed'

            def _uc(frames, fallback_shot):
                shot = frames[-1][1] if frames else fallback_shot
                if not shot:
                    return None
                sz = image_size(shot) or (dict(case_size) if case_size else None)
                if sz is None and shot:
                    sz = image_size(shot)
                return {'size': sz, 'screenshotBase64': shot} if sz else None

            # ① Plan（计划组头：下发动作）
            uc_p = _uc(fr_plan, shots[0] if shots else None)
            if uc_p and not case_size:
                case_size = image_size(uc_p['screenshotBase64'])
            tasks.append({
                'status': st_status,
                'type': 'Planning', 'subType': 'Plan',
                'param': {'userInstruction': desc_clean, 'imagesIncludeCount': len(fr_plan)},
                'timing': {'start': s_start, 'end': p_end, 'cost': p_end - s_start},
                'uiContext': uc_p,
                'log': {'rawResponse': json.dumps(
                    {'log': desc_clean, 'more_actions_needed_by_instruction': si < len(steps) - 1},
                    ensure_ascii=False)},
                'output': {'actions': ([{'type': sub, 'param': action_param}]
                                       if st_status == 'finished' else []),
                           'more_actions_needed_by_instruction': si < len(steps) - 1,
                           'log': desc_clean, 'yamlFlow': [yf]},
                'recorder': _rec(fr_plan),
                'cache': {'hit': False},
            })

            # ② Locate（元素定位；有坐标带高亮框，element=null 亦为官方合法形态）
            has_el = bool(el_rect and el_center)
            bbox = ([el_rect['left'], el_rect['top'],
                     el_rect['left'] + el_rect['width'], el_rect['top'] + el_rect['height']]
                    if has_el else None)
            tasks.append({
                'status': st_status,
                'type': 'Planning', 'subType': 'Locate',
                'subTask': True,
                'param': ({'prompt': desc_clean, 'bbox': bbox} if has_el
                          else {'prompt': desc_clean}),
                'thought': '',
                'timing': {'start': p_end, 'end': l_end, 'cost': l_end - p_end},
                'uiContext': _uc(fr_loc, shots[0] if shots else None),
                'output': {'element': ({'rect': el_rect, 'center': el_center,
                                        'description': desc_clean} if has_el else None)},
                'hitBy': {'from': 'Plan', 'context': ({'bbox': bbox} if has_el else {})},
                'recorder': _rec(fr_loc),
            })

            # ③ Action（执行动作）
            main_shot = fr_act[-1][1] if fr_act else (shots[0] if shots else None)
            tasks.append({
                'status': st_status,
                'type': 'Action Space', 'subType': sub,
                'param': action_param,
                'subTask': True,
                'timing': {'start': l_end, 'end': s_end, 'cost': s_end - l_end},
                'uiContext': _uc(fr_act, shots[0] if shots else None),
                'recorder': _rec(fr_act) if fr_act else (
                    [{'type': 'screenshot', 'ts': s_end, 'screenshot': main_shot,
                      'timing': 'after-calling', 'description': desc_clean}] if main_shot else []),
            })

        # 3) 失败：断言任务（含失败截图/录屏/原因）
        if status != 'passed':
            reason = ((res.get('statusDetails') or {}).get('message') or '')[:2000]
            fail_shots = []
            for att in res.get('attachments', []) or []:
                if (att.get('type') or '').startswith('image/'):
                    d = b64_image(os.path.join(ATT, att.get('source', '')))
                    if d:
                        fail_shots.append(d)
            fr = frames_for(case_stop - 1000, case_stop + 500, 3) if v0 else []
            rec = [{'type': 'screenshot', 'ts': ts, 'screenshot': d, 'timing': 'after-calling'}
                   for ts, d in fr]
            main_shot = fail_shots[0] if fail_shots else (rec[-1]['screenshot'] if rec else None)
            assert_size = (image_size(main_shot) if main_shot else None) or (dict(case_size) if case_size else None)
            # 官方 Print_Assert_Result 结构：param{condition, thought, result:bool}
            # + status:'failed' + errorMessage；无 output 字段（原自创的
            # expect/actual/assertion 结构渲染器不消费，已删）。
            for r in rec:
                r.setdefault('description', '断言失败')
            tasks.append({
                'status': 'failed', 'type': 'Action Space', 'subType': 'Print_Assert_Result',
                'param': {'condition': case_name, 'thought': reason[:200] or '断言未通过',
                          'result': False},
                'subTask': True,
                'errorMessage': reason[:500] or '断言未通过',
                'timing': {'start': case_stop, 'end': case_stop, 'cost': 0},
                'uiContext': ({'size': assert_size, 'screenshotBase64': main_shot}
                              if main_shot else None),
                'recorder': rec,
            })

    return {
        'sdkVersion': report_version(),
        'groupName': 'AutomationTest Report',
        'groupDescription': run_id,
        'deviceType': 'android',
        'executions': [{'logTime': int(time.time() * 1000),
                        'name': 'Action - %s · %s (%s)' % (meta.get('device_model') or '',
                                                           run_id, meta.get('status') or ''),
                        'tasks': tasks}],
        'modelBriefs': [],
    }


def inject_data(shell_html, data):
    """替换壳中的数据 script（官方协议：<script type="midscene_web_dump" type="application/json">，
    位于文档尾；渲染器启动时读取该 dump 渲染报告——替换它即注入我们的数据）。"""
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    scripts = list(re.finditer(
        r'(<script type="midscene_web_dump"[^>]*>\s*)(\{.*?})(\s*</script>)', shell_html, re.S))
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
    print('已生成: %s（壳: %s）' % (out, os.path.basename(shell)))
    print('任务数: %d | 数据: %.1f MB | 总大小: %.1f MB' % (
        len(data['executions'][0]['tasks']),
        len(json.dumps(data)) / 1048576, os.path.getsize(out) / 1048576))


if __name__ == '__main__':
    main()
