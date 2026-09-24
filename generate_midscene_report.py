# -*- coding: utf-8 -*-
"""生成 Midscene 风格的 App UI 测试报告（一比一复刻 su7.html 的 UI 布局与交互）。

数据源：output/runs/<run_id>/allure-results/*.json + result.json
输出　：output/runs/<run_id>/midscene-report.html（单文件，双击即可打开）

用法：python generate_midscene_report.py [run_id]（缺省 = 最新一次运行）
"""
import json
import glob
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_run(run_id):
    run_dir = os.path.join(BASE_DIR, 'output', 'runs', run_id)
    result_path = os.path.join(run_dir, 'result.json')
    if not os.path.isfile(result_path):
        raise SystemExit('运行不存在: %s' % result_path)
    meta = json.load(open(result_path, encoding='utf-8'))
    results = []
    for f in sorted(glob.glob(os.path.join(run_dir, 'allure-results', '*-result.json'))):
        try:
            results.append(json.load(open(f, encoding='utf-8')))
        except Exception:
            pass
    return run_dir, meta, results


def build_data(run_id, meta, results, run_dir_abs):
    """把 Allure results 映射成 Midscene 报告 schema（executions/tasks）。"""
    run_start = meta.get('start_time')
    run_end = meta.get('end_time')
    executions = []
    exec_name = 'APP UI 自动化 · %s · %s' % (meta.get('device_model') or meta.get('device_desc') or '设备',
                                            run_id)
    ATT_BASE = '../allure-results/'          # 报告输出在 runs/<id>/report/ 下
    tasks = []
    for res in sorted(results, key=lambda r: r.get('start') or 0):
        case_name = res.get('name') or '用例'
        status = res.get('status') or 'unknown'
        case_start = res.get('start')
        case_stop = res.get('stop')
        # 用例级证据附件（失败截图 / 失败录屏 / 失败原因）
        case_shots, case_videos, case_reason = [], [], ''
        for att in res.get('attachments', []) or []:
            src = ATT_BASE + att.get('source', '')
            t = att.get('type') or ''
            if t.startswith('image/'):
                case_shots.append(src)
            elif t.startswith('video/'):
                case_videos.append(src)
            elif att.get('name') == 'failure_reason':
                try:
                    fp = os.path.join(run_dir_abs, 'allure-results', att.get('source', ''))
                    case_reason = open(fp, encoding='utf-8', errors='replace').read().strip()[:2000]
                except Exception:
                    pass
        # 用例组头（Plan 类型任务，展示为 Action 分组标题；携带用例级证据）
        tasks.append({
            'status': 'finished' if status == 'passed' else 'failed',
            'type': 'Planning', 'subType': 'Case',
            'param': {'name': case_name, 'node': (res.get('fullName') or ''),
                      'reason': case_reason},
            'timing': {'start': case_start, 'end': case_stop,
                       'cost': (case_stop or 0) - (case_start or 0)},
            'uiContext': None,
            'output': {'title': case_name},
        })
        step_tasks = []
        for st in res.get('steps') or []:
            st_time = st.get('time') or {}
            start = st_time.get('start')
            end = st_time.get('stop') or st_time.get('end')
            shots = []
            for att in st.get('attachments', []) or []:
                if (att.get('type') or '').startswith('image/'):
                    shots.append(ATT_BASE + att.get('source', ''))
            if not shots and case_shots:
                shots = list(case_shots)
            step_tasks.append({
                'status': ('finished' if st.get('status') in (None, 'passed', 'finished')
                           else st.get('status')),
                'type': 'Action Space', 'subType': 'Step',
                'param': {'name': st.get('name', ''), 'case': case_name},
                'timing': {'start': start, 'end': end, 'cost': st_time.get('duration')},
                'uiContext': None,
                'output': {'title': st.get('name', '')},
            })
        # 非通过用例：失败证据（截图+录屏+原因）挂到最后一个步骤（失败点），便于步进直达
        if status != 'passed' and step_tasks:
            last = step_tasks[-1]
            last['status'] = 'failed'
            last['uiContext'] = {'size': None, 'screenshots': case_shots, 'videos': case_videos}
            last['param']['reason'] = case_reason
        tasks.extend(step_tasks)
    executions.append({'logTime': int(time.time() * 1000), 'name': exec_name, 'tasks': tasks})
    return {
        'sdkVersion': '6.12.0',
        'groupName': 'AutomationTest Report',
        'groupDescription': run_id,
        'meta': {
            'run_id': run_id, 'status': meta.get('status'), 'device': meta.get('device_model'),
            'udid': meta.get('udid'), 'app_package': meta.get('app_package'),
            'start_time': run_start, 'end_time': run_end,
            'cases': len(results),
            'passed': sum(1 for r in results if r.get('status') == 'passed'),
            'failed': sum(1 for r in results if r.get('status') != 'passed'),
        },
        'executions': executions,
    }


TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Report - AutomationTest</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #f5f5f7; --panel: #ffffff; --line: #e5e7eb; --ink: #1d1d1f; --ink2: #3a3a3c;
  --muted: #86868b; --sky: #0071e3; --sky-tint: rgba(0, 113, 227, .08);
  --ok: #1d9a4e; --ok-bg: rgba(52, 199, 89, .12);
  --bad: #d70015; --bad-bg: rgba(255, 59, 48, .1);
  --shadow: 0 4px 24px rgba(0,0,0,.06);
}
html.night {
  --bg: #101012; --panel: #1b1c1f; --line: #303236; --ink: #f3f4f6; --ink2: #d1d5db;
  --muted: #9ca3af; --sky: #409cff; --sky-tint: rgba(64, 156, 255, .12);
  --ok: #30d158; --ok-bg: rgba(48, 209, 88, .14);
  --bad: #ff453a; --bad-bg: rgba(255, 69, 58, .14);
  --shadow: 0 4px 24px rgba(0,0,0,.4);
}
body { font: 14px/1.5 -apple-system, "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg); color: var(--ink); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
.page-nav { height: 52px; background: var(--panel); border-bottom: 1px solid var(--line);
  display: flex; align-items: center; padding: 0 20px; gap: 10px; flex: none; }
.logo { width: 30px; height: 30px; border-radius: 8px; background: var(--sky); color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 15px; }
.logo-tx { font-weight: 700; font-size: 16px; }
.page-nav-right { margin-left: auto; display: flex; align-items: center; gap: 14px; color: var(--muted); font-size: 12.5px; }
.icon-btn { width: 30px; height: 30px; border-radius: 8px; border: none; background: transparent;
  cursor: pointer; font-size: 15px; color: var(--ink); }
.icon-btn:hover { background: var(--sky-tint); }
.layout { flex: 1; display: flex; gap: 14px; padding: 14px; min-height: 0; }
/* 左栏：步骤时间线 */
.side { width: 340px; flex: none; background: var(--panel); border-radius: 14px; box-shadow: var(--shadow);
  display: flex; flex-direction: column; min-height: 0; }
.side-head { padding: 16px 18px 10px; }
.side-title { font-size: 20px; font-weight: 800; letter-spacing: -.02em; }
.side-switch { font-size: 11px; color: var(--muted); margin-top: 3px; }
.side-exec { display: flex; align-items: center; gap: 8px; padding: 8px 18px; font-weight: 700; font-size: 13.5px;
  border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.side-exec .ic { font-size: 14px; }
.side-exec label { margin-left: auto; display: flex; align-items: center; gap: 5px; font-weight: 400;
  font-size: 11.5px; color: var(--muted); cursor: pointer; }
.side-body { flex: 1; overflow-y: auto; padding: 10px 10px 16px; }
.case-group { margin-top: 12px; }
.case-title { font-weight: 700; font-size: 13.5px; line-height: 1.45; padding: 4px 8px; cursor: default; }
.case-title .st { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; }
.case-title .st.passed { background: var(--ok); }
.case-title .st.failed { background: var(--bad); }
.step-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px 6px 14px; border-radius: 8px;
  cursor: pointer; font-size: 12.8px; }
.step-row:hover { background: var(--sky-tint); }
.step-row.cur { background: var(--sky-tint); box-shadow: inset 2px 0 0 var(--sky); }
.step-row .mark { flex: none; width: 15px; text-align: center; }
.step-row.ok .mark { color: var(--ok); }
.step-row.bad .mark { color: var(--bad); }
.step-row .tx { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-row .tx .kind { font-weight: 600; margin-right: 5px; }
.step-row .dur { color: var(--muted); font-size: 11.5px; flex: none; font-variant-numeric: tabular-nums; }
/* 右栏：Record 播放器 */
.main { flex: 1; min-width: 0; background: var(--panel); border-radius: 14px; box-shadow: var(--shadow);
  display: flex; flex-direction: column; min-height: 0; }
.main-title { padding: 14px 20px 8px; font-size: 18px; font-weight: 800; letter-spacing: -.02em; }
.timeline { flex: none; overflow-x: auto; border-bottom: 1px solid var(--line); padding: 6px 0 0; }
.tl-inner { display: flex; min-width: max-content; }
.tl-cell { width: 96px; flex: none; text-align: center; cursor: pointer; }
.tl-cell .ms { font-size: 10.5px; color: var(--muted); margin-bottom: 3px; font-variant-numeric: tabular-nums; }
.tl-cell img { width: 84px; height: 150px; object-fit: cover; border-radius: 6px 6px 0 0; border: 2px solid transparent;
  background: #000; display: block; margin: 0 auto; }
.tl-cell.cur img { border-color: var(--sky); }
.tl-cell .bar { height: 3px; background: transparent; }
.tl-cell.cur .bar { background: var(--sky); }
.viewer { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center;
  background: var(--sky-tint); position: relative; overflow: hidden; }
.viewer img { max-width: 92%; max-height: 92%; border-radius: 6px; box-shadow: 0 6px 30px rgba(0,0,0,.25); }
.viewer .noimg { color: var(--muted); font-size: 13px; text-align: center; line-height: 1.8; }
.viewer .noimg .big { font-size: 40px; display: block; margin-bottom: 8px; }
.progress { height: 5px; background: var(--line); flex: none; position: relative; }
.progress .fill { position: absolute; left: 0; top: 0; bottom: 0; background: var(--sky); transition: width .25s; }
.detail-bar { flex: none; padding: 12px 20px; border-top: 1px solid var(--line); }
.detail-bar .row1 { display: flex; align-items: center; gap: 10px; }
.detail-bar .kind { font-weight: 800; font-size: 14.5px; }
.detail-bar .chev { margin-left: auto; color: var(--muted); cursor: pointer; border: none; background: none; font-size: 14px; }
.detail-bar .desc { color: var(--ink2); font-size: 13px; margin-top: 4px; }
.detail-bar .extra { display: none; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line);
  font-size: 12px; color: var(--muted); line-height: 1.7; word-break: break-all; }
.detail-bar.open .extra { display: block; }
.overview { display: flex; gap: 12px; padding: 10px 18px; flex-wrap: wrap; }
.ov-chip { background: var(--sky-tint); color: var(--sky-deep, var(--sky)); border-radius: 8px;
  padding: 5px 12px; font-size: 12px; font-weight: 600; }
.ov-chip b { font-size: 14px; }
.ov-chip.ok { background: var(--ok-bg); color: var(--ok); }
.ov-chip.bad { background: var(--bad-bg); color: var(--bad); }
html.night .viewer { background: #0c0d0f; }
</style>
</head>
<body>
<nav class="page-nav">
  <div class="logo">AT</div>
  <div class="logo-tx">AutomationTest</div>
  <div class="page-nav-right">
    <span id="navMeta"></span>
    <button class="icon-btn" id="themeBtn" title="切换日间/夜间">☀️</button>
  </div>
</nav>
<div class="layout">
  <aside class="side">
    <div class="side-head">
      <div class="side-title">Report</div>
      <div class="side-switch">Switch: ↑ / ↓ 或点击切换步骤</div>
    </div>
    <div class="side-exec"><span class="ic">☰</span> Execution
      <label><input type="checkbox" id="chkDetail"> 步骤参数</label>
    </div>
    <div class="overview" id="overview"></div>
    <div class="side-body" id="sideBody"></div>
  </aside>
  <section class="main">
    <div class="main-title">Record</div>
    <div class="timeline"><div class="tl-inner" id="tlInner"></div></div>
    <div class="viewer" id="viewer"></div>
    <div class="progress"><div class="fill" id="progFill" style="width:0%"></div></div>
    <div class="detail-bar" id="detailBar">
      <div class="row1"><span class="kind" id="dKind">—</span>
        <button class="chev" id="dChev" title="展开详情">⌃</button></div>
      <div class="desc" id="dDesc">—</div>
      <div class="extra" id="dExtra"></div>
    </div>
  </section>
</div>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
(function () {
  const DATA = JSON.parse(document.getElementById('report-data').textContent);
  const META = DATA.meta || {};
  const EXEC = DATA.executions[0];
  /* 平铺步骤：组头（用例）+ 步骤，统一索引 */
  const FLAT = [];
  EXEC.tasks.forEach((t, ti) => {
    if (t.type === 'Planning') { FLAT.push({ kind: 'case', task: t, groupTitle: t.output.title, status: t.status }); }
    else { FLAT.push({ kind: 'step', task: t, groupTitle: (t.param && t.param.case) || '' }); }
  });
  let cur = FLAT.findIndex(x => x.kind === 'step');
  if (cur < 0) cur = 0;

  /* 概览 chips */
  (function () {
    const m = META;
    const dur = (m.start_time && m.end_time) ? '总时长 ' + m.start_time.slice(11) + ' → ' + m.end_time.slice(11, 19) : '';
    document.getElementById('overview').innerHTML =
      '<span class="ov-chip">用例 <b>' + (m.cases || 0) + '</b></span>' +
      '<span class="ov-chip ok">通过 <b>' + (m.passed || 0) + '</b></span>' +
      '<span class="ov-chip ' + ((m.failed || 0) > 0 ? 'bad' : '') + '">失败 <b>' + (m.failed || 0) + '</b></span>' +
      '<span class="ov-chip">' + (m.device || '') + ' · ' + (m.udid || '') + '</span>' +
      (dur ? '<span class="ov-chip">' + dur + '</span>' : '');
    document.getElementById('navMeta').textContent =
      'v' + DATA.sdkVersion + ' | ' + (m.device || '') + ' (' + (m.udid || '') + ') | ' + (m.status || '');
  })();

  /* 左栏时间线 */
  const sideBody = document.getElementById('sideBody');
  const runStart = Math.min.apply(null, FLAT.filter(x => x.task.timing && x.task.timing.start).map(x => x.task.timing.start));
  const runEnd = Math.max.apply(null, FLAT.filter(x => x.task.timing && x.task.timing.end).map(x => x.task.timing.end));
  const KIND_LABEL = { Plan: 'Plan', Step: 'Step', Locate: 'Locate', Tap: 'Tap', Input: 'Input', ClearInput: 'ClearInput' };
  function stepLine(it) {
    const t = it.task;
    const cost = (t.timing && t.timing.cost) ? (t.timing.cost / 1000).toFixed(2) + 's' : '—';
    const name = (t.param && t.param.name) || (t.output && t.output.title) || t.subType;
    const kind = it.kind === 'case' ? 'Case' : (KIND_LABEL[t.subType] || t.subType);
    const ok = it.kind === 'case' ? t.status === 'finished' : (t.status !== 'failed');
    return '<div class="step-row ' + (ok ? 'ok' : 'bad') + '" data-i="' + it.i + '">' +
      '<span class="mark">' + (ok ? '✓' : '✗') + '</span>' +
      '<span class="tx"><span class="kind">' + kind + '</span>' + esc(name) + '</span>' +
      '<span class="dur">' + cost + '</span></div>';
  }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
  (function renderSide() {
    let html = '', lastGroup = null;
    FLAT.forEach((it, i) => { it.i = i; });
    FLAT.forEach(it => {
      if (it.kind === 'case') {
        html += '<div class="case-group"><div class="case-title"><span class="st ' +
          (it.task.status === 'finished' ? 'passed' : 'failed') + '"></span>Action - ' + esc(it.groupTitle) + '</div>';
        lastGroup = it;
      } else {
        html += stepLine(it);
      }
    });
    html += '</div>';
    sideBody.innerHTML = html;
    sideBody.querySelectorAll('.step-row').forEach(el => {
      el.addEventListener('click', () => { cur = +el.dataset.i; render(); });
    });
  })();

  /* 右栏渲染 */
  const tlInner = document.getElementById('tlInner');
  const viewer = document.getElementById('viewer');
  function shotUrls(it) {
    const uc = (it.task && it.task.uiContext) || {};
    return uc.screenshots || (uc.screenshotBase64 ? [uc.screenshotBase64] : []);
  }
  function render() {
    const it = FLAT[cur];
    /* 左栏高亮 + 滚动 */
    sideBody.querySelectorAll('.step-row').forEach(el => {
      el.classList.toggle('cur', +el.dataset.i === cur);
      if (+el.dataset.i === cur) el.scrollIntoView({ block: 'nearest' });
    });
    /* 时间轴：所有含截图的步骤 */
    const withShots = FLAT.filter(x => shotUrls(x).length);
    tlInner.innerHTML = withShots.map(x => {
      const t = x.task.timing || {};
      const rel = (t.start && runEnd) ? Math.max(0, t.start - runStart) : 0;
      return '<div class="tl-cell' + (x.i === cur ? ' cur' : '') + '" data-i="' + x.i + '">' +
        '<div class="ms">' + rel + 'ms</div>' +
        '<img src="' + shotUrls(x)[0] + '" loading="lazy"><div class="bar"></div></div>';
    }).join('');
    tlInner.querySelectorAll('.tl-cell').forEach(c => {
      c.addEventListener('click', () => { cur = +c.dataset.i; render(); });
    });
    const curCell = tlInner.querySelector('.tl-cell.cur');
    if (curCell) curCell.scrollIntoView({ block: 'nearest', inline: 'center' });
    /* 主视图：失败录屏优先，其次截图；用例组头无证据时给占位说明 */
    const urls = shotUrls(it);
    const vids = ((it.task.uiContext || {}).videos) || [];
    if (vids.length) {
      viewer.innerHTML = '<video controls playsinline preload="metadata" src="' + vids[0] +
        '" style="max-width:92%;max-height:92%;border-radius:6px;box-shadow:0 6px 30px rgba(0,0,0,.25)"></video>' +
        (urls.length ? '<div style="position:absolute;bottom:10px;left:14px;color:var(--muted);font-size:11.5px">录屏证据 · 失败截图见时间轴</div>' : '');
    } else if (urls.length) {
      viewer.innerHTML = '<img src="' + urls[0] + '">';
    } else if (it.kind === 'case') {
      viewer.innerHTML = '<div class="noimg"><span class="big">📋</span>用例分组：' + esc(it.groupTitle) +
        '<br>下方为该用例的执行步骤，↑↓ 或点击步骤查看</div>';
    } else {
      viewer.innerHTML = '<div class="noimg"><span class="big">🖼</span>该步骤无截图附件' +
        '<br>（通过用例仅记录操作步骤；失败截图 / 录屏证据会在此展示）</div>';
    }
    /* 进度条 */
    const t = it.task.timing || {};
    const pct = (t.start && runEnd && runEnd > runStart)
      ? Math.min(100, Math.max(0, (t.start - runStart) / (runEnd - runStart) * 100)) : 0;
    document.getElementById('progFill').style.width = pct + '%';
    /* 详情条 */
    document.getElementById('dKind').textContent =
      it.kind === 'case' ? 'Case' : (it.task.subType || 'Step');
    document.getElementById('dDesc').textContent =
      (it.task.param && it.task.param.name) || (it.task.output && it.task.output.title) || '—';
    const extra = [];
    if (it.task.timing && it.task.timing.cost) extra.push('耗时 ' + (it.task.timing.cost / 1000).toFixed(2) + 's');
    if (it.task.timing && it.task.timing.start) extra.push('开始 ' + new Date(it.task.timing.start).toLocaleTimeString());
    if (it.task.status) extra.push('状态 ' + it.task.status);
    if (it.task.param && it.task.param.node) extra.push('节点 ' + it.task.param.node);
    const reason = it.task.param && it.task.param.reason;
    document.getElementById('dExtra').innerHTML =
      (reason ? '<div style="color:var(--bad);margin-bottom:6px;white-space:pre-wrap">✗ 失败原因：<br>' + esc(reason) + '</div>' : '') +
      extra.map(x => '· ' + esc(x)).join('<br>');
    document.getElementById('detailBar').classList.remove('open');
  }
  document.getElementById('dChev').addEventListener('click', () => {
    document.getElementById('detailBar').classList.toggle('open');
  });
  /* 键盘导航：↑↓ 或 Cmd/Ctrl+↑↓ */
  document.addEventListener('keydown', (e) => {
    if (!(e.key === 'ArrowUp' || e.key === 'ArrowDown')) return;
    const step = e.key === 'ArrowDown' ? 1 : -1;
    let n = cur;
    do { n += step; } while (n >= 0 && n < FLAT.length && FLAT[n].kind === 'case');
    if (n < 0 || n >= FLAT.length) return;
    e.preventDefault();
    cur = n; render();
  });
  /* 主题切换（与平台一致的 day/night） */
  const themeBtn = document.getElementById('themeBtn');
  function applyTheme(mode) {
    document.documentElement.classList.toggle('night', mode === 'night');
    themeBtn.textContent = mode === 'night' ? '🌙' : '☀️';
    try { localStorage.setItem('report_theme', mode); } catch (e) {}
  }
  themeBtn.addEventListener('click', () => {
    applyTheme(document.documentElement.classList.contains('night') ? 'day' : 'night');
  });
  let saved = 'day';
  try { saved = localStorage.getItem('report_theme') || 'day'; } catch (e) {}
  applyTheme(saved);
  render();
})();
</script>
</body>
</html>
'''


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not run_id:
        runs = sorted(glob.glob(os.path.join(BASE_DIR, 'output', 'runs', '*')), reverse=True)
        if not runs:
            raise SystemExit('output/runs 下没有运行记录')
        run_id = os.path.basename(runs[0])
    run_dir, meta, results = load_run(run_id)
    data = build_data(run_id, meta, results, run_dir)
    payload = json.dumps(data, ensure_ascii=False)
    html = TEMPLATE.replace('__REPORT_DATA__', payload.replace('</', '<\\/'))
    os.makedirs(os.path.join(run_dir, 'report'), exist_ok=True)
    out = os.path.join(run_dir, 'report', 'midscene-report.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print('已生成:', out)
    print('用例:', data['meta']['cases'], '通过:', data['meta']['passed'],
          '失败:', data['meta']['failed'], '| 数据大小: %.1f KB' % (len(payload) / 1024))


if __name__ == '__main__':
    main()
