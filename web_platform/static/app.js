/* App UI 自动化测试平台 v1.6 · 前端逻辑 */
'use strict';

/* ---------------- 基础工具 ---------------- */
async function api(url, opts) {
  const res = await fetch(url, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
  const data = await res.json().catch(() => ({ ok: false, msg: '响应解析失败(' + res.status + ')' }));
  if (!res.ok && !data.msg) data.msg = 'HTTP ' + res.status;
  return data;
}
const postJson = (url, body) => api(url, { method: 'POST', body: JSON.stringify(body || {}) });
const del = (url) => api(url, { method: 'DELETE' });
const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
/* 状态徽章：run 状态为大写（PASSED…），用例/步骤状态来自 allure 为小写（passed…），
   统一转大写复用同一套 .st-* 样式；broken→ERROR、skipped/unknown→PENDING */
function statusBadge(st) {
  const s = String(st == null ? '' : st).toUpperCase();
  const cls = { BROKEN: 'ERROR', SKIPPED: 'PENDING', UNKNOWN: 'PENDING' }[s] || s;
  return '<span class="status st-' + esc(cls) + '">' + esc(s) + '</span>';
}
/* run 统计：带标签的 通过/失败/异常 三个数值 */
function runStatsHtml(t) {
  return '<span>共 <b>' + (t.total || 0) + '</b> 条</span>' +
    '<span>通过 <b class="num-ok">' + (t.passed || 0) + '</b></span>' +
    '<span>失败 <b class="num-bad">' + (t.failed || 0) + '</b></span>' +
    '<span>异常 <b class="num-err">' + (t.error || 0) + '</b></span>';
}
function fmtTime(s) { return s ? String(s).replace('T', ' ').slice(0, 19) : '-'; }

let _toastTimer = null;
function toast(msg, ok = true) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = ok ? 'ok' : 'bad';
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

/* 自绘确认模态（替代原生 confirm） */
function confirmModal(title, msg, danger) {
  return new Promise((resolve) => {
    const mask = $('#mask'), mTitle = $('#mTitle'), mMsg = $('#mMsg'),
          btnOk = $('#mOk'), btnCancel = $('#mCancel');
    mTitle.textContent = title;
    mMsg.textContent = msg;
    btnOk.className = danger ? 'danger' : '';
    btnOk.textContent = danger ? '删除' : '确定';
    mask.classList.add('show');
    const done = (v) => { mask.classList.remove('show'); btnOk.onclick = btnCancel.onclick = null; resolve(v); };
    btnOk.onclick = () => done(true);
    btnCancel.onclick = () => done(false);
    mask.onclick = (e) => { if (e.target === mask) done(false); };
  });
}

/* ---------------- 侧边栏（全局） ---------------- */
function renderSidebar(active) {
  const sb = $('#sidebar');
  if (!sb) return;
  const items = [
    ['/', '📊', '首页'],
    ['/run', '🚀', '执行'],
    ['/report', '📈', '测试报告'],
    ['/admin', '🗂', '管理后台'],
    ['/locator', '🎯', '元素定位器'],
  ];
  sb.innerHTML =
    '<div class="brand"><div class="logo">🤖</div><div>AppUI 自动化<br><small>测试平台 v<span id="brandVer">…</span></small></div></div>' +
    '<nav>' + items.map(([href, ico, name]) =>
      '<a href="' + href + '" class="' + (href === active ? 'on' : '') + '"><span class="ico">' + ico + '</span>' + name + '</a>'
    ).join('') + '</nav>' +
    '<div class="foot">' +
    '<span><i class="dot ok" id="dotDevice"></i>设备 <span id="footDevice">…</span></span>' +
    '<span><i class="dot ok" id="dotAppium"></i>Appium <span id="footAppium">…</span></span>' +
    '<button class="ghost mini" id="btnChangelog" title="查看各版本更新时间与变更内容">📋 更新日志 v<span id="clVer">…</span></button>' +
    '</div>';
  const clBtn = $('#btnChangelog');
  if (clBtn) clBtn.addEventListener('click', showChangelog);
  pollFootStatus();
  setInterval(pollFootStatus, 10000);
}

/* ---------------- 更新日志（左下角入口） ---------------- */
function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
}

async function showChangelog() {
  const d = await api('/api/changelog');
  if (!d.ok) return toast('更新日志加载失败', false);
  let mask = $('#clMask');
  if (!mask) {
    mask = document.createElement('div');
    mask.className = 'mask';
    mask.id = 'clMask';
    mask.innerHTML =
      '<div class="modal clmodal"><h4>📋 更新日志</h4>' +
      '<div class="cllist" id="clList"></div>' +
      '<div class="mops"><button id="clClose">关闭</button></div></div>';
    document.body.appendChild(mask);
    mask.onclick = (e) => { if (e.target === mask) mask.classList.remove('show'); };
  }
  $('#clList').innerHTML = (d.entries || []).map(e =>
    '<div class="clitem' + (e.version === d.version ? ' cur' : '') + '">' +
      '<div class="clhead"><b>v' + escHtml(e.version) + '</b>' +
      '<span class="cltime">' + escHtml(e.time) + '</span>' +
      (e.version === d.version ? '<span class="clbadge">当前版本</span>' : '') + '</div>' +
      (e.title ? '<div class="cltitle">' + escHtml(e.title) + '</div>' : '') +
      '<ul>' + (e.changes || []).map(c => '<li>' + escHtml(c) + '</li>').join('') + '</ul>' +
    '</div>').join('');
  $('#clClose').onclick = () => mask.classList.remove('show');
  mask.classList.add('show');
}

async function pollFootStatus() {
  try {
    const st = await api('/api/status');
    // 版本号（平台与元素定位器统一，来自后端 changelog.py 单一数据源）
    const bv = $('#brandVer'), cv = $('#clVer');
    if (bv) bv.textContent = st.version || '?';
    if (cv) cv.textContent = st.version || '?';
    const d = $('#dotDevice'), f = $('#footDevice');
    if (d) {
      const on = st.device_online > 0;
      d.className = 'dot ' + (on ? 'ok' : 'bad');
      // 在线数量 + 首台设备序列号（长序列号截断，悬停看全）
      let txt = on ? '在线×' + st.device_online : '离线';
      if (on && st.devices && st.devices[0] && st.devices[0].udid) {
        const udid = st.devices[0].udid;
        txt += ' · ' + (udid.length > 14 ? udid.slice(0, 13) + '…' : udid);
        f.title = '设备序列号: ' + udid;
      }
      f.textContent = txt;
    }
    const d2 = $('#dotAppium'), f2 = $('#footAppium');
    if (d2) {
      d2.className = 'dot ' + (st.appium.ok ? 'ok' : 'bad');
      f2.textContent = st.appium.ok ? '正常' : '不可用';
    }
  } catch (e) {}
}

/* ---------------- 首页 ---------------- */
async function initIndex() {
  renderSidebar('/');
  const refresh = async () => { await refreshStats(); await loadRunsTable('#recentList', true, 10); };
  $('#btnClearAll').addEventListener('click', clearAllRuns);
  await refresh();
  setInterval(refresh, 8000);
}

async function refreshStats() {
  try {
    const d = await api('/api/runs');
    const runs = d.runs || [];
    const pass = runs.filter(r => r.status === 'PASSED').length;
    const fail = runs.filter(r => r.status === 'FAILED' || r.status === 'ERROR').length;
    $('#cardRuns').textContent = runs.length;
    $('#cardPass').textContent = pass;
    $('#cardFail').textContent = fail;
    $('#cardRate').textContent = runs.length ? Math.round(pass / runs.length * 100) + '%' : '—';
  } catch (e) {}
}

/* ---------------- 执行记录渲染（首页/执行页共用） ----------------
   设备列显示真实型号（runner 启动时从 adb 取，如 FGD AL00=华为）；
   旧历史记录无 device_model 时回退显示 conf 别名 device_desc */
function runRowHtml(r, withOps) {
  const dev = r.device_model || r.device_desc || '-';
  return '<tr>' +
    '<td><a class="runlink" href="/runs/' + esc(r.run_id) + '">' + esc(r.run_id) + '</a></td>' +
    '<td>' + fmtTime(r.start_time) + '</td>' +
    '<td title="' + esc(dev) + ' · ' + esc(r.udid || '') + '">' + esc(dev) + '</td>' +
    '<td title="' + esc(r.app_package) + '">' + esc((r.app_package || '-').split('.').pop()) + '</td>' +
    '<td><b>' + r.total + '</b> / <span style="color:#4ade80">' + r.passed + '</span> / <span style="color:#ff8787">' + r.failed + '</span></td>' +
    '<td>' + statusBadge(r.status) + '</td>' +
    (withOps ? '<td><div class="ops">' +
      '<a class="btn ghost mini" style="text-decoration:none" href="/runs/' + esc(r.run_id) + '">详情</a>' +
      '<button class="ghost mini" onclick="openReportFor(\'' + esc(r.run_id) + '\', this)">报告</button>' +
      '<button class="mini danger-ghost" onclick="deleteRunFor(\'' + esc(r.run_id) + '\')">删除</button>' +
      '</div></td>' : '') +
    '</tr>';
}

function renderRunRows(sel, runs, withOps) {
  const tbody = $(sel);
  if (!tbody) return;
  if (!runs.length) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty"><span class="eico">🗂️</span>暂无执行记录<br>' +
      '<a class="runlink" href="/run">去执行页开始第一次测试 →</a></div></td></tr>';
    return;
  }
  tbody.innerHTML = runs.map(r => runRowHtml(r, withOps)).join('');
}

/* 首页：只取最近 N 条，无分页 */
async function loadRunsTable(sel, withOps, limit) {
  const d = await api('/api/runs');
  renderRunRows(sel, (d.runs || []).slice(0, limit || 100), withOps);
}

/* ---------------- 分页（每页 10 条） ---------------- */
const PAGE_SIZE = 10;
let _runsPage = 1, _reportPage = 1;

function renderPager(sel, page, pages, onPage, total) {
  const el = $(sel);
  if (!el) return;
  if (!total) { el.innerHTML = ''; return; }
  const totalHtml = '<span class="muted" style="align-self:center;margin-left:8px">共 ' + total + ' 条</span>';
  // 单页时不显示页码按钮，但保留「共 N 条」让分页始终可见
  if (pages <= 1) { el.innerHTML = totalHtml; return; }
  const btn = (p, label, cur, dis) =>
    '<button class="' + (cur ? 'mini' : 'ghost mini') + '"' + (dis ? ' disabled' : '') +
    ' data-p="' + p + '">' + label + '</button>';
  let html = btn(page - 1, '‹', false, page <= 1);
  const s = Math.max(1, Math.min(page - 2, pages - 4));
  const e = Math.min(pages, s + 4);
  if (s > 1) html += '<span class="muted" style="align-self:center">…</span>';
  for (let p = s; p <= e; p++) html += btn(p, p, p === page, false);
  if (e < pages) html += '<span class="muted" style="align-self:center">…</span>';
  html += btn(page + 1, '›', false, page >= pages);
  html += totalHtml;
  el.innerHTML = html;
  el.querySelectorAll('button[data-p]').forEach(b =>
    b.addEventListener('click', () => onPage(parseInt(b.dataset.p, 10))));
}

/* 执行页：执行记录已并入测试报告页，这里不再需要分页版加载；
   保留 renderPager/分页状态供报告页使用 */
async function loadRunsPaged() {}

async function deleteRunFor(runId) {
  const yes = await confirmModal('删除执行记录', '将删除 ' + runId + ' 的全部数据（Allure 结果、日志），不可恢复。', true);
  if (!yes) return;
  const d = await del('/api/runs/' + runId);
  toast(d.msg || (d.ok ? '已删除' : '删除失败'), d.ok);
  if (d.ok && _activeDetailRun === runId) {
    clearInterval(_detailTimer); _detailTimer = null;
    _activeDetailRun = null;
    const box = $('#runDetail');
    if (box) box.innerHTML = '<div class="empty"><span class="eico">👈</span>从上方列表选择一条执行记录查看详情</div>';
    // run_detail 独立页：删完回到报告页（当前 run 已不存在）
    if (document.body.dataset.page === 'detail') { location.href = '/report'; return; }
  }
  refreshAfterOps();
}

async function clearAllRuns() {
  const yes = await confirmModal('清空全部执行记录', '将删除所有已结束执行记录的全部数据（正在运行的保留），不可恢复。', true);
  if (!yes) return;
  const d = await postJson('/api/runs/clear', {});
  toast(d.msg || '已清空', d.ok);
  if (d.ok && _activeDetailRun) {
    clearInterval(_detailTimer); _detailTimer = null;
    _activeDetailRun = null;
    const box = $('#runDetail');
    if (box) box.innerHTML = '<div class="empty"><span class="eico">👈</span>从上方列表选择一条执行记录查看详情</div>';
  }
  refreshAfterOps();
}

function refreshAfterOps() {
  const page = document.body.dataset.page;
  if (page === 'index') { refreshStats(); loadRunsTable('#recentList', true, 10); }
  else if (page === 'report') { loadReportList(); }
}

/* ---------------- 执行页（配置+设备+用例+记录 合并） ---------------- */
async function initRun() {
  renderSidebar('/run');
  await loadExecDefaults();
  await loadCaseTree();
  $('#btnStart').addEventListener('click', startRun);
  $('#btnStop').addEventListener('click', stopRun);
  $('#btnSelectAll').addEventListener('click', () => setAllChecked(true));
  $('#btnSelectNone').addEventListener('click', () => setAllChecked(false));
  $('#confSel').addEventListener('change', () => loadExecDefaults($('#confSel').value));
}

async function loadExecDefaults(conf) {
  const url = '/api/exec_defaults' + (conf ? '?conf=' + encodeURIComponent(conf) : '');
  const d = await api(url);
  if (!d.ok) return toast(d.msg || '加载执行配置失败', false);
  const sel = $('#confSel');
  sel.innerHTML = (d.confs || []).map(f =>
    '<option value="' + esc(f) + '"' + (f === d.defaults.conf_file ? ' selected' : '') + '>' +
    esc(f.split('/').pop()) + '</option>').join('');
  // 默认值填充：当前在线设备 + conf 默认
  $('#inUdid').value = d.defaults.udid || '';
  $('#inPackage').value = d.defaults.app_package || '';
  $('#inActivity').value = d.defaults.app_activity || '';
  // 设备状态卡：在线状态以 adb 实测为准（device_online），conf 里的 udid 仅作预填
  const online = !!d.defaults.device_online;
  $('#devState').innerHTML =
    '<span class="pill ' + (online ? 'ok' : 'bad') + '">' + (online ? '● 设备在线' : '● 未检测到在线设备') + '</span>' +
    '<span>设备 <b>' + esc(d.defaults.udid || '-') + '</b>' +
    (!online && d.defaults.udid ? ' <span class="muted" style="font-size:12px">(conf 预填，未连接)</span>' : '') + '</span>' +
    '<span>型号 <b>' + esc(d.defaults.model || '-') + '</b></span>' +
    '<span>Appium <b>' + (d.defaults.appium_ok ? '<span style="color:#4ade80">正常</span>' : '<span style="color:#ff8787">不可用</span>') + '</b></span>' +
    '<span>服务 <b>' + esc(d.defaults.server || '-') + '</b></span>' +
    (d.defaults.occupied ? '<span class="pill bad">有任务执行中</span>' : '');
}

async function loadCaseTree() {
  const d = await api('/api/cases');
  const box = $('#caseTree');
  if (!d.ok || !(d.tree || []).length) {
    box.innerHTML = '<div class="empty"><span class="eico">📂</span>cases/app_ui 下没有可执行用例</div>';
    return;
  }
  let html = '<ul>';
  d.tree.forEach(f => {
    html += '<li><label class="chk"><input type="checkbox" data-file="' + esc(f.file) + '" class="ck-file">' +
      '<span class="file">' + esc(f.file.split('/').pop()) + '</span> <span class="muted">' + esc(f.file) + '</span></label><ul>';
    f.methods.forEach(m => {
      const node = f.file + '::' + f.class_name + '::' + m;
      html += '<li><label class="chk"><input type="checkbox" data-node="' + esc(node) + '" class="ck-node">' +
        '<span class="cls">' + esc(f.class_name) + '::' + esc(m) + '</span></label></li>';
    });
    html += '</ul></li>';
  });
  html += '</ul>';
  box.innerHTML = html;
  box.addEventListener('change', (e) => {
    if (e.target.classList.contains('ck-file')) {
      Array.from(box.querySelectorAll('input[data-node]')).forEach(n => {
        if (n.dataset.node.startsWith(e.target.dataset.file + '::')) n.checked = e.target.checked;
      });
    }
  });
}

function setAllChecked(v) { document.querySelectorAll('#caseTree input[type=checkbox]').forEach(n => n.checked = v); }
function selectedCases() { return Array.from(document.querySelectorAll('#caseTree .ck-node:checked')).map(n => n.dataset.node); }

async function startRun() {
  const conf = $('#confSel').value;
  const cases = selectedCases();
  if (!conf) return toast('请选择默认配置来源(conf)', false);
  if (!cases.length) return toast('请至少勾选一个用例', false);
  const btn = $('#btnStart');
  btn.disabled = true; btn.textContent = '启动中…';
  const body = {
    conf_file: conf,
    case_nodes: cases,
    overrides: {
      udid: $('#inUdid').value.trim(),
      appPackage: $('#inPackage').value.trim(),
      appActivity: $('#inActivity').value.trim(),
    },
  };
  const d = await postJson('/api/run', body);
  btn.disabled = false; btn.textContent = '🚀 开始执行';
  if (!d.ok) return toast(d.msg || '启动失败', false);
  $('#execArea').style.display = 'block';
  $('#execArea').scrollIntoView({ behavior: 'smooth', block: 'start' });
  toast('任务 ' + d.run_id + ' 已启动');
  pollTask(d.run_id);
}

let _pollTimer = null, _logOffset = 0;
function pollTask(runId) {
  clearInterval(_pollTimer); _logOffset = 0;
  const box = $('#logBox'); box.innerHTML = '';
  _pollTimer = setInterval(async () => {
    const d = await api('/api/run/' + runId);
    if (!d.ok) { clearInterval(_pollTimer); return; }
    const t = d.task;
    $('#runIdNow').textContent = t.run_id;
    $('#runStatusNow').innerHTML = statusBadge(t.status);
    $('#runStatsNow').textContent = '共 ' + t.total + ' · 通过 ' + t.passed + ' · 失败 ' + t.failed + ' · 异常 ' + (t.error || 0);
    const done = t.passed + t.failed + t.error + t.skipped;
    $('#runProgress').style.width = (t.total ? Math.min(100, Math.round(done / t.total * 100)) : 0) + '%';
    $('#btnStop').disabled = !(t.status === 'RUNNING' || t.status === 'PENDING');
    $('#btnGoDetail').onclick = () => location.href = '/runs/' + runId;
    const lg = await api('/api/run/' + runId + '/log?offset=' + _logOffset);
    if (lg.ok) { _logOffset = lg.offset; renderLog(lg.lines); }
    if (t.status !== 'RUNNING') {
      clearInterval(_pollTimer);
      if (t.error_msg) toast('任务异常: ' + t.error_msg, false);
      else toast('任务结束: ' + t.status + ' → 去「测试报告」查看用例明细与截图', t.status === 'PASSED');
    }
  }, 1500);
}

function renderLog(lines, boxSel) {
  const box = boxSel ? $(boxSel) : $('#logBox');
  if (!box || !lines.length) return;
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  lines.forEach(l => {
    let cls = '';
    if (/断言「.+」失败|FAILED|ERROR|TimeoutException|AssertionError/.test(l)) cls = 'fail';
    else if (/断言「.+」通过|PASSED/.test(l)) cls = 'pass';
    else if (/toast「.+」未出现|WARNING/.test(l)) cls = 'warn';
    else if (/^[-=]+$|^platform darwin|^cachedir|^rootdir|^plugins/.test(l)) cls = 'dim';
    const div = document.createElement('div');
    if (cls) div.className = cls;
    div.textContent = l;
    box.appendChild(div);
  });
  if (nearBottom) box.scrollTop = box.scrollHeight;
}

async function stopRun() {
  const runId = $('#runIdNow').textContent;
  if (!runId || runId === '-') return;
  const d = await postJson('/api/run/' + runId + '/stop', {});
  toast(d.msg || '停止信号已发送', d.ok);
}

/* ---------------- 执行详情页 ---------------- */
let _detailTimer = null;

async function initRunDetail() {
  renderSidebar('/run');
  const runId = document.body.dataset.runId;
  await renderRunDetail('#detailBody', runId);
}

/* ---------------- 详情组件：run 概要 + 用例执行记录 + 断言截图 + 执行日志 ----------------
   自建视图，直接解析 allure-results；报告页「详情」与 run_detail 页共用 */
let _activeDetailRun = null, _activeSel = null;

function shotHtml(runId, shot) {
  const src = '/api/runs/' + encodeURIComponent(runId) + '/res/' + encodeURIComponent(shot.source);
  return '<img class="thumb" src="' + src + '" title="' + esc(shot.name || shot.source) + '"' +
    ' onclick="openLightbox(\'' + src + '\', \'' + esc(shot.name || shot.source) + '\')">';
}

function caseRowHtml(runId, c, idx) {
  const dur = c.duration_ms ? (c.duration_ms / 1000).toFixed(1) + 's' : '-';
  const steps = c.steps || [];
  const shots = c.screenshots || [];
  const stepHtml = steps.length ? '<ul class="steps">' + steps.map(s => {
    const ss = s.attachments || [];
    return '<li class="st-' + esc(s.status) + '"><span class="sico">' +
      (s.status === 'passed' ? '✓' : s.status === 'failed' ? '✗' : '○') + '</span>' +
      esc(s.name) +
      (ss.length ? '<span class="shots">' + ss.map(a => shotHtml(runId, a)).join('') + '</span>' : '') +
      '</li>';
  }).join('') + '</ul>' : '';
  const errHtml = c.error_message ? '<div class="err">' + esc(c.error_message) + '</div>' : '';
  const oldShots = (!steps.length && shots.length)
    ? '<div class="shots">' + shots.map(a => shotHtml(runId, a)).join('') + '</div>' : '';
  const none = (!steps.length && !shots.length)
    ? '<p class="muted">该用例无步骤/截图数据（旧版执行记录，仅保留统计）</p>' : '';
  return '<tr class="case-row"><td class="xpand"><button class="ghost mini" data-t="' + idx + '">展开</button></td>' +
    '<td>' + esc(c.name) + '</td><td>' + statusBadge(c.status) + '</td>' +
    '<td class="muted">' + dur + '</td><td>' + shots.length + ' 图</td></tr>' +
    '<tr class="detail-row" data-t="' + idx + '" style="display:none"><td colspan="5">' +
    stepHtml + errHtml + oldShots + none + '</td></tr>';
}

async function renderRunDetail(sel, runId) {
  _activeDetailRun = runId; _activeSel = sel;
  clearInterval(_detailTimer); _detailTimer = null;
  const box = $(sel);
  if (!box) return;
  box.innerHTML = '<div class="card"><div class="empty">加载中…</div></div>';
  const [d, c] = await Promise.all([
    api('/api/run/' + runId),
    api('/api/run/' + runId + '/cases'),
  ]);
  if (!d.ok) {
    box.innerHTML = '<div class="card"><div class="empty"><span class="eico">🫥</span>' + esc(d.msg || '任务不存在') + '</div></div>';
    return;
  }
  const t = d.task;
  const cases = c.ok ? c.cases : [];
  const running = t.status === 'RUNNING' || t.status === 'PENDING';
  box.innerHTML =
    '<div class="card">' +
    '<div class="cardhead"><h3>用例执行记录 <span class="muted">· ' + esc(runId) + '</span></h3>' +
    '<div class="ops">' +
    '<button class="ghost mini" onclick="openReportFor(\'' + esc(runId) + '\', this)">打开报告</button>' +
    '<button class="mini danger-ghost" onclick="deleteRunFor(\'' + esc(runId) + '\')">删除本记录</button>' +
    '</div></div>' +
    '<div class="meta"><span>状态 ' + statusBadge(t.status) + '</span>' +
    '<span>设备 <b>' + esc(t.device_model || t.device_desc) + ' / ' + esc(t.udid) + '</b></span>' +
    '<span>App <b>' + esc(t.app_package) + '</b></span>' +
    '<span>开始 <b>' + fmtTime(t.start_time) + '</b></span>' +
    runStatsHtml(t) +
    (running ? '<span class="pill ok">执行中</span>' : '') + '</div>' +
    (t.error_msg ? '<p class="mt" style="color:#ff8787">' + esc(t.error_msg) + '</p>' : '') +
    (cases.length ? '<div class="tblwrap mt"><table><thead><tr><th></th><th>用例</th><th>结果</th><th>耗时</th><th>截图</th></tr></thead><tbody>' +
      cases.map((c2, i) => caseRowHtml(runId, c2, i)).join('') +
      '</tbody></table></div>' :
      '<div class="empty mt"><span class="eico">📄</span>该 run 没有用例数据（allure-results 缺失或已删除）</div>') +
    '</div>' +
    '<div class="card"><div class="cardhead"><h3>执行日志 <span class="muted" id="logCount"></span></h3></div>' +
    '<div class="logbox" id="detailLogBox"></div></div>';
  // 用例行展开/收起（事件委托，避免 8s 轮询重建后按钮失效）
  box.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-t]');
    if (b) {
      const tr = box.querySelector('tr.detail-row[data-t="' + b.dataset.t + '"]');
      if (tr) tr.style.display = tr.style.display === 'none' ? '' : 'none';
    }
  });
  // 日志：全量加载；RUNNING 时增量轮询
  const lg0 = await api('/api/run/' + runId + '/log?offset=0');
  if (lg0.ok) { $('#logCount').textContent = '共 ' + lg0.lines.length + ' 行'; renderLog(lg0.lines, '#detailLogBox'); }
  if (running) {
    let off = lg0.ok ? lg0.offset : 0;
    _detailTimer = setInterval(async () => {
      const lg = await api('/api/run/' + runId + '/log?offset=' + off);
      if (lg.ok) { off = lg.offset; $('#logCount').textContent = '共 ' + off + ' 行'; renderLog(lg.lines, '#detailLogBox'); }
      const st = await api('/api/run/' + runId);
      if (st.ok && st.task.status !== 'RUNNING' && st.task.status !== 'PENDING') {
        clearInterval(_detailTimer); _detailTimer = null;
        renderRunDetail(_activeSel, runId); // 收尾：刷新最终状态与用例
      } else if (st.ok) {
        const tb = box.querySelector('.meta');
        if (tb) {
          const t2 = st.task;
          tb.innerHTML = '<span>状态 ' + statusBadge(t2.status) + '</span>' +
            '<span>设备 <b>' + esc(t2.device_model || t2.device_desc) + ' / ' + esc(t2.udid) + '</b></span>' +
            '<span>App <b>' + esc(t2.app_package) + '</b></span>' +
            runStatsHtml(t2) +
            '<span class="pill ok">执行中</span>';
        }
      }
    }, 3000);
  }
}

async function showRunDetail(runId) {
  const box = $('#runDetail');
  if (!box) return;
  box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  await renderRunDetail('#runDetail', runId);
}

/* 截图 lightbox（点击缩略图放大） */
function openLightbox(src, name) {
  let lb = $('#lightbox');
  if (!lb) { lb = document.createElement('div'); lb.id = 'lightbox'; document.body.appendChild(lb); }
  lb.innerHTML = '<img src="' + src + '" alt=""><button class="lb-close">✕</button>';
  lb.classList.add('show');
  lb.onclick = () => lb.classList.remove('show');
}

/* ---------------- 测试报告页 ---------------- */
async function initReport() {
  renderSidebar('/report');
  $('#btnClearAll3').addEventListener('click', clearAllRuns);
  await loadReportList();
  setInterval(loadReportList, 8000);
}

/* 报告页：列表分页 */
async function loadReportList() {
  const d = await api('/api/runs');
  const tb = $('#reportList');
  const runs = d.runs || [];
  if (!runs.length) {
    tb.innerHTML = '<tr><td colspan="6"><div class="empty"><span class="eico">📈</span>暂无执行记录，先生成一次执行</div></td></tr>';
    const pg = $('#reportPager'); if (pg) pg.innerHTML = '';
    return;
  }
  const pages = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  if (_reportPage > pages) _reportPage = pages;
  if (_reportPage < 1) _reportPage = 1;
  const slice = runs.slice((_reportPage - 1) * PAGE_SIZE, _reportPage * PAGE_SIZE);
  tb.innerHTML = slice.map(r =>
    '<tr><td><a class="runlink" href="/runs/' + esc(r.run_id) + '">' + esc(r.run_id) + '</a></td>' +
    '<td>' + fmtTime(r.start_time) + '</td>' +
    '<td>' + statusBadge(r.status) + '</td>' +
    '<td class="muted">' + esc(r.allure_dir || '-') + '</td>' +
    '<td>' + (r.report_dir ? '<span style="color:#4ade80">已生成</span>' : '<span class="muted">未生成</span>') + '</td>' +
    '<td><div class="ops">' +
    '<button class="ghost mini" onclick="showRunDetail(\'' + esc(r.run_id) + '\')">详情</button>' +
    '<button class="ghost mini" onclick="openReportFor(\'' + esc(r.run_id) + '\', this)">打开报告</button>' +
    '<button class="mini danger-ghost" onclick="deleteRunFor(\'' + esc(r.run_id) + '\')">删除数据</button>' +
    '</div></td></tr>').join('');
  renderPager('#reportPager', _reportPage, pages, (p) => { _reportPage = p; loadReportList(); }, runs.length);
}

/* 打开报告（统一入口）：按钮 loading + 5 秒冷却防重复点击。
   冷却用全局时间锁而非按钮状态——报告页每 8s 轮询会重建表格 DOM，
   按钮级的 disabled 挡不住重建出来的新按钮。
   后端等报告服务就绪才返回，返回后只 window.open 一次（不会双开） */
let _openReportLockUntil = 0;
async function openReportFor(runId, btn) {
  if (Date.now() < _openReportLockUntil) return;
  _openReportLockUntil = Date.now() + 5000;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 打开中…'; }
  const started = Date.now();
  try {
    toast('正在生成/打开 ' + runId + ' 的报告…');
    const d = await postJson('/api/run/' + runId + '/report/open', {});
    if (d.ok) { toast(d.reused ? '报告服务已就绪: ' + d.url : '报告已生成并打开: ' + d.url); window.open(d.url, '_blank'); }
    else toast('打开失败: ' + (d.msg || ''), false);
  } finally {
    // 5 秒冷却：即使请求已返回，也要等满 5 秒才恢复按钮可点
    const remain = 5000 - (Date.now() - started);
    setTimeout(() => {
      _openReportLockUntil = 0;
      if (btn) { btn.disabled = false; btn.textContent = orig; }
    }, Math.max(0, remain));
  }
}

/* ---------------- 页面分发 ---------------- */
document.addEventListener('DOMContentLoaded', () => {
  const page = document.body.dataset.page;
  if (page === 'index') initIndex();
  else if (page === 'run') initRun();
  else if (page === 'detail') initRunDetail();
  else if (page === 'report') initReport();
});