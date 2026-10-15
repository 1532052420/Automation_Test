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


def link_case_video(run_dir, v0, case_no):
    """把用例录屏以相对软链放进报告目录（http.server/file:// 均可访问）。
    软链避免 mp4 双份落盘；失败（如跨盘）退回复制。返回供 HTML 引用的文件名或 None。"""
    if not v0:
        return None
    rep_dir = os.path.join(run_dir, 'report')
    os.makedirs(rep_dir, exist_ok=True)
    link = os.path.join(rep_dir, 'recording_%d.mp4' % case_no)
    try:
        if os.path.lexists(link):
            os.remove(link)
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
        videos = find_case_videos(node, meta.get('udid'))
        v0 = videos[0] if videos else None
        v_dur = video_duration_ms(v0) if v0 else 0
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
        assert_tail = (len(doc_steps) == len(steps) + 1
                       and (doc_steps[-1] or '').startswith('断言'))
        if assert_tail:
            last_end = int((steps[-1].get('stop') if steps else 0) or case_stop)
            steps.append({'name': doc_steps[-1], 'status': res.get('status') or 'passed',
                          'start': last_end, 'stop': case_stop})
        use_cn = bool(doc_steps) and len(doc_steps) == max(1, len(steps))

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
                'uiContext': ({'size': png_size(main_shot), 'screenshotBase64': main_shot}
                              if main_shot else None),
                'recorder': rec,
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
            tasks.append(assert_task)

        # 录屏回放定位（自定义扩展字段，官方渲染器忽略）：_atVideo = 报告目录内的录屏相对地址，
        # _atT0 = 录屏零点对应的 epoch ms（= 用例开始），供注入脚本换算「步骤开始前 2 秒」的起点
        for t in tasks[n_tasks_before:]:
            t['_atVideo'] = rel_video
            t['_atT0'] = case_start

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
      '#atReplayTip{position:absolute;left:10px;top:10px;background:rgba(0,0,0,.55);color:#fff;font-size:12px;padding:3px 10px;border-radius:6px;z-index:5;pointer-events:none}';
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
      if (curEnd < Infinity && video.currentTime >= curEnd) video.pause();
    });

    function ensureUI() {
      // 播放期间中间区域只保留视频：官方详情内容（截图/JSON）整体隐藏；
      // React 重渲染会摘节点、还原类名——每次都补插+补类
      var panel = document.querySelector('.detail-panel');
      if (!panel) return;
      if (box.parentElement !== panel) panel.insertBefore(box, panel.firstChild);
      if (!panel.classList.contains('at-replaying')) panel.classList.add('at-replaying');
    }

    function play(task, label) {
      if (!task || !task._atVideo) {
        box.style.display = 'none';
        var p = document.querySelector('.detail-panel');
        if (p) p.classList.remove('at-replaying');
        return;
      }
      ensureUI();
      [80, 300, 900, 2000].forEach(function (d) { setTimeout(ensureUI, d); });
      var from = Math.max(0, (task.timing.start - task._atT0) / 1000 - 2);  // 步骤开始前 2 秒：留缓冲看清上下文
      var to = (task.timing.end - task._atT0) / 1000;
      var startPlay = function () {
        curEnd = to;
        tip.textContent = '▶ 录屏回放 · ' + label + ' · 从开始前 2 秒播放';
        box.style.display = 'block';
        video.play().catch(function () {});
      };
      if (video.getAttribute('src') !== task._atVideo) {
        video.setAttribute('src', task._atVideo);
        video.addEventListener('loadedmetadata', function () {
          video.currentTime = from;
          startPlay();
        }, { once: true });
      } else {
        video.currentTime = from;
        startPlay();
      }
    }

    // 左侧 antd 表格点击代理：tr.task-row 第 i 行 ↔ executions[0].tasks[i]（官方渲染器重渲染不影响代理）
    document.addEventListener('click', function (ev) {
      var tr = ev.target.closest ? ev.target.closest('tr.task-row') : null;
      if (!tr) return;
      var i = Array.prototype.indexOf.call(document.querySelectorAll('tr.task-row'), tr);
      if (i < 0 || !tasks[i]) return;
      var t = tasks[i];
      var isPlan = t.type === 'Planning';
      var label = isPlan ? '整个操作（用例全程）'
        : ((t.param && t.param.locate && t.param.locate.description) || t.subType || ('步骤 ' + i));
      play(t, label);
    }, true);
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
