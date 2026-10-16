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
    os.path.expanduser('~/Downloads/su7-full.html'),
    os.path.join(BASE_DIR, 'design', 'midscene-ref', 'su7-full.html'),
]
FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'


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


def parse_recording_log(v0):
    """解析录屏会话目录的 recording.log，返回 {'start': 起录 epoch 秒, 'span': 墙钟跨度秒}。
    log 行时间只有当日时分秒，日期取视频文件 mtime 所在日；解析失败返回 None。"""
    log = os.path.join(os.path.dirname(v0), 'recording.log')
    if not os.path.isfile(log):
        return None
    try:
        text = open(log, encoding='utf-8', errors='ignore').read()
        tods = re.findall(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\]', text)
        if not tods:
            return None
        stop_tod = None
        for line in text.splitlines():
            if '录制已停止' in line:
                m = re.search(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\]', line)
                if m:
                    stop_tod = m.group(1)
                break
        if not stop_tod:
            stop_tod = tods[-1]
        date = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(v0)))

        def epoch_ms(tod):
            base = time.mktime(time.strptime(date + ' ' + tod[:8], '%Y-%m-%d %H:%M:%S'))
            return (base + float(tod[9:]) / 1000) * 1000

        start_ms = epoch_ms(tods[0])
        stop_ms = epoch_ms(stop_tod)
        span = (stop_ms - start_ms) / 1000
        if not 0 < span < 3600:
            return None
        return {'start': start_ms, 'span': span}
    except Exception:
        return None


def find_case_videos(node, udid, near_epoch=None):
    if not node:
        return []
    prefix = node.replace('/', '__').replace('::', '__') + '__' + (udid or '')
    hits = []
    for sub in ('artifacts', 'tmp'):
        for f in glob.glob(os.path.join(VIDEO_EVIDENCE_DIR, sub, '**', '*.mp4'), recursive=True):
            if os.path.basename(f).startswith(prefix):
                hits.append(f)
    # 同一用例可能有多份历史会话录屏：取 mtime 最接近用例结束的（±30 分钟内），防跨 run 错拿
    near = near_epoch if near_epoch else (hits and max(os.path.getmtime(f) for f in hits) or 0)
    hits = [f for f in hits if abs(os.path.getmtime(f) - near) <= 1800]
    hits.sort(key=lambda f: abs(os.path.getmtime(f) - near))
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
        return {'width': 1080, 'height': 2400, 'dpr': 3}


def load_registry_desc():
    """用例登记库（config/app_testing/cases.yaml）的 node → description（「操作步骤」字段）。
    读取失败不致命——报告生成退回 allure description（docstring）。"""
    try:
        import yaml
        p = os.path.join(BASE_DIR, 'config', 'app_testing', 'cases.yaml')
        doc = yaml.safe_load(open(p, encoding='utf-8')) or {}
        return {it.get('node'): (it.get('description') or '').strip()
                for it in doc.get('items') or [] if it.get('node')}
    except Exception:
        return {}


def split_doc_steps(desc):
    """「步骤A → 步骤B」拆成中文步骤列表（弹窗 openStepFlowModal 同款规则）。"""
    return [s.strip() for s in (desc or '').split('→') if s.strip()]


# ---------------------------------------------------------------- 断言详情（v6.15.71）
# 左侧列表断言行二级展开「预期 vs 实际」的数据构建：
# ① 框架 _assert_step 挂的 AT_ASSERT_JSON 附件（多断言，通过/失败都有预期实际值）；
# ② 裸 assert/旧数据兜底：从断言描述句式解析预期，从失败原因解析实际。

def assert_type_of(text):
    """从断言名/描述推断断言类型标签（顺序敏感：先长词后短词，防「页面文本」命中「文本」）。"""
    t = text or ''
    if '文案消失' in t or '不再出现' in t:
        return '页面文本消失'
    if '页面文本' in t or '页面出现' in t:
        return '页面文本'
    if 'toast' in t.lower():
        return 'Toast'
    if '文本' in t:
        return '文本'
    if '视觉' in t or '相似度' in t:
        return '视觉'
    if '消失' in t:
        return '控件消失'
    if '存在' in t or '出现' in t:
        return '控件存在'
    return '断言'


def parse_assert_desc(text):
    """从断言描述解析预期值（裸 assert / 旧数据无 JSON 附件时的兜底）。
    句式来自 case_generator：断言「X」文本为「Y」/ 断言toast「Y」/ 断言X出现 / 断言【X】已消失。"""
    t = text or ''
    m = re.search(r'文本为「(.+?)」', t)
    if m:
        return m.group(1)
    m = re.search(r'toast[「](.+?)」', t)
    if m:
        return '出现含「%s」的toast' % m.group(1)
    if '消失' in t:
        return '元素已从页面消失'
    if '视觉' in t:
        return '与基线一致（相似度达标）'
    if '存在' in t or '出现' in t:
        return '元素出现且可见'
    return ''


def parse_actual_from_reason(reason):
    """从失败原因解析实际值：期望「X」实际「Y」或 pytest 断言重写 assert 'X' == 'Y'。"""
    r = reason or ''
    m = re.search(r'期望「(.+?)」实际「(.+?)」', r)
    if m:
        return m.group(2)
    m = re.search(r"assert\s+'(.+?)'\s*==\s*'", r)
    if m:
        return m.group(1)
    return ''


def load_assert_json(atts, att_dir):
    """读步骤的 AT_ASSERT_JSON JSON 附件（框架 _assert_step 挂的结构化断言数据）。"""
    for att in atts or []:
        if (att.get('name') or '') == 'AT_ASSERT_JSON':
            try:
                return json.load(open(os.path.join(att_dir, att.get('source', '')), encoding='utf-8'))
            except Exception:
                return None
    return None


def build_assert_detail(st, att_dir, case_reason=''):
    """allure 断言步骤 → 任务上的 _assert 详情 dict（无则 None）。
    优先取框架 JSON 附件；缺字段时用描述句式/失败原因兜底解析。"""
    name = st.get('name') or ''
    if not name.startswith('断言'):
        return None
    ok = st.get('status') in (None, 'passed')
    data = load_assert_json(st.get('attachments'), att_dir) or {}
    desc = data.get('desc') or name
    typ = assert_type_of(name + ' ' + desc)
    expected = data.get('expected') or parse_assert_desc(name) or '（未记录）'
    actual = data.get('actual') or ''
    detail = data.get('detail') or ''
    if not actual:
        actual = parse_actual_from_reason(name + ' ' + detail + ' ' + (case_reason or ''))
        if not actual and ok and typ == '文本' and expected not in ('', '（未记录）'):
            # 通过的相等断言：实际值=预期值（断言通过在数学上保证相等），直接展示真实文本
            actual = expected
        if not actual:
            actual = '与预期一致' if ok else (case_reason or '（未记录）')[:200]
    return {'type': typ, 'desc': str(desc)[:120], 'ok': ok,
            'expected': str(expected)[:200], 'actual': str(actual)[:200], 'detail': str(detail)[:200]}


def link_case_video(run_dir, v0, case_no):
    """把用例录屏压缩转码后放进报告目录（用户反馈原片太大：1440x3168 原片 25s ≈ 7.4MB）。
    高度压到 1280（宽等比）、CRF 28、去音轨、faststart 便于边下边播；25s ≈ 1~2MB。
    转码失败退回相对软链原片（不阻断报告生成）。返回供 HTML 引用的文件名或 None。"""
    if not v0:
        return None
    rep_dir = os.path.join(run_dir, 'report')
    os.makedirs(rep_dir, exist_ok=True)
    # 文件名带录屏 mtime 戳：重新生成时 URL 变化，绕开浏览器启发式缓存拿旧片
    link = os.path.join(rep_dir, 'recording_%d_%d.mp4' % (case_no, int(os.path.getmtime(v0))))
    for old in glob.glob(os.path.join(rep_dir, 'recording_*.mp4')) + \
               glob.glob(os.path.join(rep_dir, 'recording_*.mp4.tmp.mp4')):
        try:
            os.remove(old)
        except OSError:
            pass
    tmp = link + '.tmp.mp4'
    try:
        if os.path.lexists(link):
            os.remove(link)
        r = subprocess.run([FFMPEG, '-y', '-i', v0, '-vf', 'scale=-2:1280', '-c:v', 'libx264',
                            '-crf', '28', '-preset', 'fast', '-an', '-movflags', '+faststart', tmp],
                           capture_output=True, timeout=300)
        if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, link)
            return os.path.basename(link)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        if os.path.isfile(tmp):
            os.remove(tmp)
        os.symlink(os.path.relpath(v0, rep_dir), link)
        return os.path.basename(link)
    except OSError:
        try:
            import shutil
            shutil.copyfile(v0, link)
            return os.path.basename(link)
        except OSError:
            return None


def build_data(run_id, meta, results, run_dir):
    """平台 Allure 数据 → Midscene 原版报告 schema。"""
    ATT = os.path.join(run_dir, 'allure-results')
    registry = load_registry_desc()
    run_start = None
    tasks = []
    for case_no, res in enumerate(sorted(results, key=lambda r: r.get('start') or 0)):
        case_name = res.get('name') or '用例'
        status = res.get('status') or 'unknown'
        case_start = res.get('start') or 0
        case_stop = res.get('stop') or case_start
        run_start = case_start if run_start is None else min(run_start, case_start)
        node = node_of(meta, res)
        videos = find_case_videos(node, meta.get('udid'), near_epoch=(res.get('stop') or 0) / 1000)
        v0 = videos[0] if videos else None
        v_dur = video_duration_ms(v0) if v0 else 0
        # 回放/抽帧时间映射（2026-10-15 修正）：录屏起点 ≠ 用例起点（录制含启动 App 等前置，
        # 且 adb 录屏墙钟跨度 ≠ 视频容器时长）。以 recording.log 的录制起点为原点、
        # 视频时长/墙钟跨度为伸缩系数换算；无日志时退回旧假设（用例开始=视频零点）。
        rec = parse_recording_log(v0) if v0 else None
        if rec and v_dur:
            v_origin_ms = rec['start']                    # epoch ms：视频零点
            v_scale = (v_dur / 1000.0) / rec['span']      # 视频秒 / 墙钟秒
        else:
            v_origin_ms, v_scale = case_start, 1.0
        n_tasks_before = len(tasks)
        rel_video = link_case_video(run_dir, v0, case_no)
        desc = str(res.get('description') or '')
        # 中文步骤名（v6.15.54）：左侧任务列表显示「操作步骤」字段的中文参数。
        # 来源：用例登记 description 优先，allure description（方法 docstring）兜底。
        # 与 allure 步骤一一对应时逐条映射；断言是方法内裸 assert、不生成 allure step——
        # 描述恰好多一条且末条以「断言」开头时，合成末条断言任务
        # （时间窗 = 末步骤结束 ~ 用例结束，截图取该窗口录屏帧），
        # 使报告步骤与用例「操作步骤」弹窗逐条对齐；其余数量对不上仍保持英文动作词（宁缺勿错）。
        doc_steps = split_doc_steps(registry.get(node) or desc)
        steps = list(res.get('steps') or [])
        case_reason = ((res.get('statusDetails') or {}).get('message') or '')[:2000]
        assert_tail = (len(doc_steps) == len(steps) + 1
                       and (doc_steps[-1] or '').startswith('断言'))
        if assert_tail:
            last_end = int((steps[-1].get('stop') if steps else 0) or case_stop)
            steps.append({'name': doc_steps[-1], 'status': res.get('status') or 'passed',
                          'start': last_end, 'stop': case_stop})
        use_cn = bool(doc_steps) and len(doc_steps) == max(1, len(steps))

        def frames_for(ws, we, want):
            """时间窗内从录屏取 want 帧 dataURI（窗口均分）。ws/we 为 epoch ms，
            经录制起点原点 + 伸缩系数换算为视频内时间。"""
            out = []
            if not v0 or v_dur <= 0:
                return out
            ra = max(0, (ws / 1000.0 - v_origin_ms / 1000.0) * v_scale * 1000)
            rb = max(0, min(v_dur, (we / 1000.0 - v_origin_ms / 1000.0) * v_scale * 1000))
            if rb <= ra:
                ra, rb = 0, min(v_dur, 1000)
            n = max(1, min(want, int((rb - ra) / 200) or 1))
            for i in range(n):
                ts = ra + (rb - ra) * (i + 0.5) / n
                d = frame_datauri(v0, ts)
                if d:
                    out.append((int(case_start + ts), d))
            return out

        # 1) 用例级 Plan 任务（组头）——只保留标题/时间/状态，不再抽视频帧
        #    （v6.15.53：去掉组头顶部的视频帧截图，报告更清爽、体积更小）
        tasks.append({
            'status': 'finished' if status == 'passed' else 'failed',
            'type': 'Planning', 'subType': 'Plan',
            'param': {'userInstruction': case_name, 'imagesIncludeCount': 0},
            'timing': {'start': case_start, 'end': case_stop, 'cost': case_stop - case_start},
            'uiContext': None,
            'log': {'rawResponse': desc or case_name},
            'output': {'actions': [], 'more_actions_needed_by_instruction': True,
                       'log': case_name, 'yamlFlow': []},
            'recorder': [],
            'cache': {'hit': False},
        })

        # 2) 操作步骤 → Action Space
        #    时间（v6.15.53）：allure-pytest 2.7.0 的 step 时间是顶层 start/stop
        #    （attrs asdict 扁平序列化，无 time 子对象）——直接读取真实时间戳；
        #    仅当缺失时才退化为按步骤数均分用例时间窗。
        n_steps = max(1, len(steps))
        win = (case_stop - case_start) / n_steps
        for si, st in enumerate(steps):
            st_time = st.get('time') or {}
            s_start = int(st_time.get('start') or st.get('start') or (case_start + si * win))
            s_end = int(st_time.get('stop') or st_time.get('end') or st.get('stop')
                        or (case_start + (si + 1) * win))
            if s_end < s_start:
                s_end = s_start
            sub = step_to_action(st.get('name', ''))
            cn = doc_steps[si] if (use_cn and si < len(doc_steps)) else ''
            shots = []
            for att in st.get('attachments', []) or []:
                if (att.get('type') or '').startswith('image/'):
                    d = b64_image(os.path.join(ATT, att.get('source', '')))
                    if d:
                        shots.append(d)
            main_shot = shots[0] if shots else None
            rec = []
            if not main_shot and v0:
                want = max(2, int((s_end - s_start) / 700) or 1)
                fr = frames_for(s_start, s_end, want)
                rec = [{'type': 'screenshot', 'ts': ts, 'screenshot': d, 'timing': 'after-calling'}
                       for ts, d in fr]
                main_shot = rec[-1]['screenshot'] if rec else None
            else:
                rec = ([{'type': 'screenshot', 'ts': s_end, 'screenshot': main_shot,
                         'timing': 'after-calling'}] if main_shot else [])
            m = re.search(r'\[id:([^\]]+)\]', st.get('name', ''))
            locate = {'description': cn or st.get('name', '')}
            if m:
                locate.update({'value': m.group(1), 'type': 'id'})
            tasks.append({
                'status': 'finished' if (st.get('status') in (None, 'passed', 'finished')) else 'failed',
                'type': 'Action Space', 'subType': cn or sub,
                'param': {'locate': locate},
                'subTask': True,
                'timing': {'start': s_start, 'end': s_end, 'cost': s_end - s_start},
                # 全程耗时含 AI 规划等待（数据源无规划/操作分段），向用户说明时间口径
                'log': {'rawResponse': '步骤全程 %.1fs（含 AI 规划等待）；实际操作集中在窗口末尾 2~4 秒，回放已自动对准'
                                        % ((s_end - s_start) / 1000.0)},
                'uiContext': ({'size': png_size(main_shot), 'screenshotBase64': main_shot}
                              if main_shot else None),
                'recorder': rec,
            })
            # 断言行二级展开数据（v6.15.71）：断言步骤挂「预期 vs 实际」详情，报告端可展开/收起
            ad = build_assert_detail(st, ATT, case_reason)
            if ad:
                tasks[-1]['_assert'] = ad

        # 3) 失败：断言任务（含失败截图/录屏/原因）
        if status != 'passed':
            reason = case_reason
            fail_shots = []
            for att in res.get('attachments', []) or []:
                if (att.get('type') or '').startswith('image/'):
                    d = b64_image(os.path.join(ATT, att.get('source', '')))
                    if d:
                        fail_shots.append(d)
            fail_vids = [v for v in videos if '_failure' in os.path.basename(v)]
            fr = frames_for(case_stop - 1000, case_stop + 500, 3) if v0 else []
            rec = [{'type': 'screenshot', 'ts': ts, 'screenshot': d, 'timing': 'after-calling'}
                   for ts, d in fr]
            main_shot = fail_shots[0] if fail_shots else (rec[-1]['screenshot'] if rec else None)
            assert_task = {
                'status': 'failed', 'type': 'Action Space', 'subType': 'Print_Assert_Result',
                'param': {'result': 'failed', 'expect': '', 'actual': reason[:200]},
                'subTask': True,
                'timing': {'start': case_stop, 'end': case_stop, 'cost': 0},
                'uiContext': ({'size': png_size(main_shot), 'screenshotBase64': main_shot}
                              if main_shot else None),
                'output': {'assertion': {'type': 'assertion', 'status': 'failed',
                                         'expected': '', 'actual': reason[:200],
                                         'message': reason[:500]},
                           'log': reason[:300]},
                'recorder': rec,
            }
            if fail_vids:
                assert_task['video'] = 'file://' + fail_vids[0]
            assert_task['_assert'] = {
                'type': assert_type_of(reason) if reason else '断言',
                'desc': '用例断言失败',
                'ok': False,
                'expected': parse_assert_desc(reason) or '（未记录）',
                'actual': parse_actual_from_reason(reason) or reason[:200],
                'detail': reason[:200],
            }
            tasks.append(assert_task)

        # 录屏回放定位（自定义扩展字段，官方渲染器忽略）：_atVideo = 报告目录内的录屏相对地址，
        # _atT0 = 视频零点对应的 epoch ms（= 录制起点），_atScale = 视频秒/墙钟秒伸缩系数，
        # 供注入脚本换算「步骤开始前 2 秒」的真实起播位置
        for t in tasks[n_tasks_before:]:
            t['_atVideo'] = rel_video
            t['_atT0'] = v_origin_ms
            t['_atScale'] = v_scale

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
    """替换壳中的数据 script（官方协议：<script type="midscene_web_dump" type="application/json">，
    位于文档尾；渲染器启动时读取该 dump 渲染报告——替换它即注入我们的数据）。"""
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    scripts = list(re.finditer(
        r'(<script type="midscene_web_dump"[^>]*>\s*)(\{.*?})(\s*</script>)', shell_html, re.S))
    if not scripts:
        raise SystemExit('壳中未找到数据 script（midscene_web_dump）')
    m = scripts[-1]
    return shell_html[:m.start()] + m.group(1) + payload + m.group(3) + shell_html[m.end():]


def inject_style(html):
    """注入平台定制样式（2026-10-15 用户要求）：隐藏帧时间轴条（Record + canvas 帧图，
    体量大实用性低）、左上 Midscene logo（外链图片，顺带消除外网依赖）、侧栏底部
    「如何插入自定义日志条目」提示文案。类名来自官方渲染器 DOM（.logo / .main-right-header /
    .timeline-wrapper / .executions-tip），壳文件更换后重新生成报告仍会自动带上。"""
    style = ('<style>/* AutomationTest 平台定制 */\n'
             '.logo,.main-right-header,.timeline-wrapper,.executions-tip{display:none!important;}\n'
             '</style>')
    if '</head>' in html:
        return html.replace('</head>', style + '\n</head>', 1)
    return html + style


REPLAY_JS = r'''
(function () {
  function boot() {
    var dumpEl = null;
    document.querySelectorAll('script').forEach(function (s) {
      if ((s.getAttribute('type') || '').indexOf('midscene_web_dump') >= 0) dumpEl = s;
    });
    if (!dumpEl) return;
    var dump;
    try { dump = JSON.parse(dumpEl.textContent); } catch (e) { return; }
    var tasks = (dump.executions && dump.executions[0] && dump.executions[0].tasks) || [];
    if (!tasks.length) return;

    var style = document.createElement('style');
    style.textContent = '.detail-panel.at-replaying{display:flex;flex-direction:column}' +
      '.detail-panel.at-replaying > :not(#atReplayBox){display:none!important}' +
      '#atReplayBox{flex:1;min-height:0;background:#000;border-radius:8px;overflow:hidden;position:relative}' +
      '#atReplayBox video{width:100%;height:100%;flex:1;min-height:0;display:block;background:#000;object-fit:contain}' +
      '#atReplayTip{position:absolute;left:10px;top:10px;background:rgba(0,0,0,.55);color:#fff;font-size:12px;padding:3px 10px;border-radius:6px;z-index:5;pointer-events:none}' +
      /* 断言结果二级行（v6.15.72）：断言行下缩进常显结果行，点它展开/收起「预期 vs 实际」明细 */
      'tr.at-assert-res > td{padding:0 12px 3px 34px!important;border:none!important;background:transparent!important}' +
      '.at-assert-line{font-size:12px;cursor:pointer;user-select:none;white-space:nowrap}' +
      '.at-assert-line.ok{color:#389e0d}' +
      '.at-assert-line.fail{color:#cf1322}' +
      '.at-assert-arrow{font-style:normal;margin-left:6px;font-size:10px;opacity:.65}' +
      'tr.at-assert-detail > td{padding:3px 12px 8px 34px!important;border:none!important;background:transparent!important}' +
      '.at-assert-card{border:1px solid #e5e6eb;border-radius:6px;padding:8px 12px;font-size:12px;color:#333}' +
      '.at-assert-card.ok{border-color:#b7eb8f;background:#f6ffed}' +
      '.at-assert-card.fail{border-color:#ffccc7;background:#fff1f0}' +
      '.at-assert-grid{display:grid;grid-template-columns:64px 1fr;gap:3px 8px}' +
      '.at-assert-grid .lbl{color:#8c8c8c}' +
      '.at-assert-grid .val{color:#333;word-break:break-all}' +
      '.at-assert-grid .val.ok{color:#389e0d}' +
      '.at-assert-grid .val.fail{color:#cf1322}' +
      '.at-assert-note{margin-top:6px;color:#8c8c8c;white-space:pre-wrap}';
    document.head.appendChild(style);

    var box = document.createElement('div');
    box.id = 'atReplayBox';
    box.style.display = 'none';
    var video = document.createElement('video');
    video.controls = true;
    video.preload = 'auto';
    var tip = document.createElement('div');
    tip.id = 'atReplayTip';
    box.appendChild(video);
    box.appendChild(tip);

    var curEnd = Infinity;
    video.addEventListener('timeupdate', function () {
      // 到步骤结束点自动暂停；暂停后即解除限制——手动点播放可继续看完，不会被再次按住
      if (curEnd < Infinity && video.currentTime >= curEnd) {
        video.pause();
        curEnd = Infinity;
      }
    });

    function ensureUI() {
      // 播放期间中间区域只保留视频：官方详情内容（截图/JSON）整体隐藏；
      // React 重渲染会摘节点、还原类名——每次都补插+补类
      var panel = document.querySelector('.detail-panel');
      if (!panel) return;
      if (box.parentElement !== panel) panel.insertBefore(box, panel.firstChild);
      if (!panel.classList.contains('at-replaying')) panel.classList.add('at-replaying');
    }

    function play(task, label, fullVideo) {
      if (!task || !task._atVideo) {
        box.style.display = 'none';
        var p = document.querySelector('.detail-panel');
        if (p) p.classList.remove('at-replaying');
        return;
      }
      ensureUI();
      [80, 300, 900, 2000].forEach(function (d) { setTimeout(ensureUI, d); });
      var k = task._atScale || 1;
      // 用例头（Plan）= 整个操作全程：从 0 播到视频自然结束。
      // 步骤：操作（点按/输入）发生在步骤窗口末尾（前面大都是 AI 规划耗时）——
      // 以步骤结束点为中心，前 2 秒起播、结束后再放 2 秒，避免干等规划或戛然而止
      var endV = (task.timing.end - task._atT0) / 1000 * k;
      var from = fullVideo ? 0 : Math.max(0, endV - 2);
      var to = fullVideo ? Infinity : endV + 2;
      // 点击步骤即播放（用户 2026-10-16 要求）：定位到操作时刻直接开播，到步骤结束点
      // 自动暂停（timeupdate 解除限制后可手动续播看完）；进入报告仍不自动播——未点击
      // 不加载视频，播放只由点击触发
      var locate = function () {
        curEnd = to;
        tip.textContent = '▶ 正在回放：' + label;
        box.style.display = 'block';
        if (tip._t) clearTimeout(tip._t);
        tip._t = setTimeout(function () { tip.textContent = ''; }, 3000);
        var p = video.play();
        if (p && p.catch) p.catch(function () {});
      };
      if (video.getAttribute('src') !== task._atVideo) {
        video.setAttribute('src', task._atVideo);
        video.addEventListener('loadedmetadata', function () {
          video.currentTime = from;
          locate();
        }, { once: true });
      } else {
        video.currentTime = from;
        locate();
      }
    }

    // 左侧 antd 表格点击代理：tr.task-row 第 i 行 ↔ executions[0].tasks[i]（官方渲染器重渲染不影响代理）
    document.addEventListener('click', function (ev) {
      // 断言结果/明细行、用例分组箭头的点击只做展开收起，不触发录屏回放
      if (ev.target.closest && (ev.target.closest('.at-assert-sub') || ev.target.closest('.at-case-toggle'))) return;
      var tr = ev.target.closest ? ev.target.closest('tr.task-row') : null;
      if (!tr) return;
      var i = Array.prototype.indexOf.call(document.querySelectorAll('tr.task-row'), tr);
      if (i < 0 || !tasks[i]) return;
      var t = tasks[i];
      var isPlan = t.type === 'Planning';
      var label = isPlan ? '整个操作（用例全程）'
        : ((t.param && t.param.locate && t.param.locate.description) || t.subType || ('步骤 ' + i));
      play(t, label, isPlan);
    }, true);

    // ---------------- 断言结果二级行（v6.15.72）----------------
    // 断言行下方直接挂缩进的「断言结果」行（常显）：✅/❌ 结论 · 类型；
    // 点结果行展开/收起「预期结果 vs 实际结果」明细卡——默认收起，只多一行结果。
    // React 重渲染会重建表格行并摘掉注入节点，MutationObserver 触发 decorate() 自愈。
    var assertExpanded = {};
    function escHtml(s) {
      return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function assertRowIndexes() {
      var rows = document.querySelectorAll('tr.task-row');
      var hits = [];
      for (var i = 0; i < rows.length; i++) {
        if (tasks[i] && tasks[i]._assert) hits.push(i);
      }
      return { rows: rows, hits: hits };
    }
    function resLineHTML(a, expanded) {
      return '<span class="at-assert-line ' + (a.ok ? 'ok' : 'fail') + '">'
        + (a.ok ? '✅ 断言通过' : '❌ 断言失败') + ' · ' + escHtml(a.type || '断言')
        + '<i class="at-assert-arrow">' + (expanded ? '▲' : '▼') + '</i></span>';
    }
    function detailHTML(a) {
      var cls = a.ok ? 'ok' : 'fail';
      var actual = a.actual || (a.ok ? '与预期一致' : '（未记录）');
      return '<div class="at-assert-card ' + cls + '">'
        + '<div class="at-assert-grid">'
        + '<div class="lbl">预期结果</div><div class="val">' + escHtml(a.expected || '（未记录）') + '</div>'
        + '<div class="lbl">实际结果</div><div class="val ' + cls + '">' + escHtml(actual) + '</div>'
        + '</div>'
        + (a.detail ? '<div class="at-assert-note">' + escHtml(a.detail) + '</div>' : '')
        + '</div>';
    }
    function decorateAssertRows() {
      var snap = assertRowIndexes();
      var rows = snap.rows;
      // 清理：断言数据变动的行后面可能残留旧 sub 行
      for (var i = 0; i < rows.length; i++) {
        if (tasks[i] && tasks[i]._assert) continue;
        var nx = rows[i].nextElementSibling;
        if (nx && nx.classList && nx.classList.contains('at-assert-sub')) nx.parentNode.removeChild(nx);
      }
      for (var j = 0; j < snap.hits.length; j++) {
        var idx = snap.hits[j];
        var row = rows[idx];
        var a = tasks[idx]._assert;
        // 结果行（常显）
        var nx = row.nextElementSibling;
        if (!(nx && nx.classList && nx.classList.contains('at-assert-res'))) {
          var res = document.createElement('tr');
          res.className = 'at-assert-sub at-assert-res';
          var td = document.createElement('td');
          td.colSpan = row.cells.length || 6;
          res.appendChild(td);
          row.parentNode.insertBefore(res, nx);
          nx = res;
        }
        var sig = (a.ok ? '1' : '0') + '|' + (assertExpanded[idx] ? '1' : '0');
        if (nx._atSig !== sig) {           // 带签名防抖，避免触发 MutationObserver 循环
          nx._atSig = sig;
          nx.cells[0].colSpan = row.cells.length || 6;
          nx.cells[0].innerHTML = resLineHTML(a, assertExpanded[idx]);
        }
        // 明细行（展开时插入）
        var nx2 = nx.nextElementSibling;
        var hasDetail = nx2 && nx2.classList && nx2.classList.contains('at-assert-detail');
        if (assertExpanded[idx] && !hasDetail) {
          var det = document.createElement('tr');
          det.className = 'at-assert-sub at-assert-detail';
          var dtd = document.createElement('td');
          dtd.colSpan = row.cells.length || 6;
          dtd.innerHTML = detailHTML(a);
          det.appendChild(dtd);
          nx.parentNode.insertBefore(det, nx.nextSibling);
        } else if (!assertExpanded[idx] && hasDetail) {
          nx2.parentNode.removeChild(nx2);
        }
      }
    }
    document.addEventListener('click', function (ev) {
      var res = ev.target.closest ? ev.target.closest('tr.at-assert-res') : null;
      if (!res) return;
      // 第 k 个结果行 ↔ 第 k 个带 _assert 的任务（行序与 tasks 一一对应）
      var k = Array.prototype.indexOf.call(document.querySelectorAll('tr.at-assert-res'), res);
      var hits = assertRowIndexes().hits;
      if (k < 0 || k >= hits.length) return;
      assertExpanded[hits[k]] = !assertExpanded[hits[k]];
      decorateAssertRows();
    }, true);

    // ---------------- 用例分组折叠（v6.15.76）----------------
    // 每条用例的首个任务必是 Plan（组头）：组 = 本 Plan 行 → 下一个 Plan 行前。
    // ≥2 条用例时在 Plan 行注入折叠箭头，点箭头收起/展开该用例的步骤行（含断言子行）；
    // 单用例报告无分组意义，保持原样。React 重渲染后由 MutationObserver 触发
    // decorateCaseGroups() 自愈（与断言子行同一套机制）。
    var caseCollapsed = {};
    function caseGroupBounds(rows) {
      var heads = [];
      for (var i = 0; i < rows.length; i++) {
        if (tasks[i] && tasks[i].type === 'Planning') heads.push(i);
      }
      var bounds = [];
      for (var k = 0; k < heads.length; k++) {
        bounds.push([heads[k], (k + 1 < heads.length ? heads[k + 1] : rows.length) - 1]);
      }
      return { heads: heads, bounds: bounds };
    }
    function decorateCaseGroups() {
      var rows = document.querySelectorAll('tr.task-row');
      var g = caseGroupBounds(rows);
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i], td = row.cells && row.cells[0];
        var head = -1;
        for (var b = 0; b < g.bounds.length; b++) if (g.bounds[b][0] === i) { head = g.bounds[b][0]; break; }
        var chev = td && td.querySelector('.at-case-toggle');
        if (head >= 0 && g.heads.length >= 2) {
          if (!chev) {
            chev = document.createElement('i');
            chev.className = 'at-case-toggle';
            chev.style.cssText = 'font-style:normal;cursor:pointer;margin-right:2px;font-size:10px;opacity:.65;user-select:none';
            td.insertBefore(chev, td.firstChild);
          }
          var sig = caseCollapsed[head] ? '1' : '0';
          if (chev._atSig !== sig) { chev._atSig = sig; chev.textContent = caseCollapsed[head] ? '▶' : '▼'; }
        } else if (chev) {
          chev.parentNode.removeChild(chev);
        }
        // 折叠落地：组内非组头行（含断言子行）隐藏
        var hide = false;
        for (var b2 = 0; b2 < g.bounds.length; b2++) {
          if (i > g.bounds[b2][0] && i <= g.bounds[b2][1] && caseCollapsed[g.bounds[b2][0]]) { hide = true; break; }
        }
        var want = hide ? 'none' : '';
        if (row.style.display !== want) row.style.display = want;
        var nx = row.nextElementSibling;
        while (nx && nx.classList && nx.classList.contains('at-assert-sub')) {
          if (nx.style.display !== want) nx.style.display = want;
          nx = nx.nextElementSibling;
        }
      }
    }
    document.addEventListener('click', function (ev) {
      var t = ev.target.closest ? ev.target.closest('.at-case-toggle') : null;
      if (!t) return;
      ev.stopPropagation();          // 不让官方行选中逻辑跟着触发
      var rows = document.querySelectorAll('tr.task-row');
      var i = Array.prototype.indexOf.call(rows, t.closest('tr.task-row'));
      if (i < 0) return;
      caseCollapsed[i] = !caseCollapsed[i];
      decorateCaseGroups();
    }, true);

    var _atMoTick = false;
    new MutationObserver(function () {
      if (_atMoTick) return;
      _atMoTick = true;
      setTimeout(function () { _atMoTick = false; decorateAssertRows(); decorateCaseGroups(); }, 60);
    }).observe(document.body, { childList: true, subtree: true });
    decorateAssertRows();
    decorateCaseGroups();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
'''


def inject_replay(html):
    """注入录屏回放脚本（2026-10-15 用户需求）：点击左侧步骤行，在详情面板顶部内嵌
    真实录屏播放器，从「步骤开始 - 2 秒」播放到步骤结束自动暂停（2 秒为缓冲，避免
    直切看不到上下文）；点用例头（Plan）播放整个操作全程。依赖任务上的 _atVideo/_atT0
    扩展字段与报告目录内的 recording_N.mp4（link_case_video）。"""
    script = '<script>/* AutomationTest 录屏回放 */' + REPLAY_JS + '</script>\n</body>'
    return html.replace('</body>', script, 1)


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
    html = inject_replay(inject_style(inject_data(open(shell, encoding='utf-8').read(), data)))
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
