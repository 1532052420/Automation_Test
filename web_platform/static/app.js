/* 自动化测试平台 · 前端逻辑
   ------------------------------------------------------------------
   页面分发：body[data-page] → initXxx()（见文件末尾）
   共享件（APP UI 与接口测试共用，避免两套重复实现）：
     api / postJson / del      统一请求（自动解析 JSON + 兜底错误信息）
     esc                       唯一转义函数
     statusBadge               状态徽章（run 大写 / allure 小写归一）
     runStatsHtml / runMetaHtml 任务概要渲染
     loadCaseSelectPanel / setAllChecked / selectedCases  选择用例列表
     pollTask                  执行面板（Run 状态 + 进度 + 实时日志 + 停止）
     evHtml                    文本证据（接口请求-响应留痕）折叠块
   ------------------------------------------------------------------ */
'use strict';

/* ================= 基础工具 ================= */
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
/* 可选元素读写：同一份渲染逻辑要同时服务多个页面，元素缺失时静默跳过而不是抛错 */
function setText(sel, text) { const el = $(sel); if (el) el.textContent = text; }
function setHtml(sel, html) { const el = $(sel); if (el) el.innerHTML = html; }

/* ---------------- 线性图标（SF Symbols 风格） ----------------
   24 网格 / currentColor 描边 / 1.7 线宽 / 圆角端点。
   统一从这里取，避免彩色 emoji 破坏单色视觉（Apple 官网不出现彩色 emoji）。 */
const ICONS = {
  flask: '<path d="M9.5 3h5M10.6 3v5.6L5.9 17.2A2.4 2.4 0 0 0 8 21h8a2.4 2.4 0 0 0 2.1-3.8L13.4 8.6V3"/>'
       + '<path d="M7.8 14.4h8.4"/>',
  check: '<path d="M4.5 12.8 9.6 18 19.5 6.8"/>',
  close: '<path d="M6.2 6.2 17.8 17.8M17.8 6.2 6.2 17.8"/>',
  target: '<circle cx="12" cy="12" r="8.3"/><circle cx="12" cy="12" r="3.3"/>',
  folder: '<path d="M3.2 7.6a2 2 0 0 1 2-2h3.4l1.9 2.3h8.3a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2H5.2a2 2 0 0 1-2-2Z"/>',
  chart: '<path d="M4 20h16"/><path d="M7.5 20v-5.6M12 20V6.4M16.5 20v-9"/>',
  doc: '<path d="M6.6 3.6h6.6L18.6 9v11.4H6.6Z"/><path d="M13.2 3.6V9h5.4"/>',
  hand: '<path d="M20 11.6H8.4l3.5-3.5-1.3-1.3L5 12l5.6 5.2 1.3-1.3-3.5-3.5H20Z"/>',
  /* AppUI 二级菜单用：设置 / 录屏 / 用例清单 */
  gear: '<circle cx="12" cy="12" r="3.1"/>'
      + '<path d="M12 2.9v2.3M12 18.8v2.3M2.9 12h2.3M18.8 12h2.3M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6"/>',
  film: '<rect x="3.2" y="5.2" width="17.6" height="13.6" rx="2.4"/><path d="M10 9.2l4.6 2.8L10 14.8Z"/>',
  list: '<path d="M8.6 6.4h11.2M8.6 12h11.2M8.6 17.6h11.2"/>'
      + '<path d="M4.3 6.4h.01M4.3 12h.01M4.3 17.6h.01"/>',
  /* 首页模块入口用：取景框（元素定位器）/ 闪电（性能压测）；上传（用例管理） */
  upload: '<path d="M12 15.2V4.2M8.2 8 12 4.2 15.8 8"/>'
        + '<path d="M4.5 15.5v2.9a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2.9"/>',
  scan: '<path d="M4 8.2V6a2 2 0 0 1 2-2h2.2M15.8 4H18a2 2 0 0 1 2 2v2.2M20 15.8V18a2 2 0 0 1-2 2h-2.2M8.2 20H6a2 2 0 0 1-2-2v-2.2"/>'
      + '<circle cx="12" cy="12" r="3.1"/>',
  bolt: '<path d="M13.2 2.8 5.8 13.2h4.9L10.8 21.2 18.2 10.8h-4.9Z"/>',
  /* AppUI 编排/套件用：流程（编排）/ 层叠（套件） */
  flow: '<circle cx="5.4" cy="6" r="2.3"/><circle cx="18.6" cy="18" r="2.3"/>'
      + '<path d="M7.7 6.9c6.2 1.5 5.5 7.4 8.8 9.6"/>',
  layers: '<path d="M12 3.4 21 8.4 12 13.4 3 8.4Z"/>'
        + '<path d="m4.6 12.2-1.6.9 9 5 9-5-1.6-.9"/>',
};
function icon(name, size) {
  const n = size || 24;
  return '<svg viewBox="0 0 24 24" width="' + n + '" height="' + n + '" fill="none"' +
    ' stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
    (ICONS[name] || '') + '</svg>';
}
/* 空态图标：大号单色线性图标 + 一句人话说明 */
function emptyHtml(ico, msg) {
  return '<div class="empty"><span class="eico">' + icon(ico, 34) + '</span>' + msg + '</div>';
}

/* 状态徽章：run 状态为大写（PASSED…），用例/步骤状态来自 allure 为小写（passed…），
   统一转大写复用同一套 .st-* 样式；broken→ERROR、skipped/unknown→PENDING */
function statusBadge(st) {
  const s = String(st == null ? '' : st).toUpperCase();
  const cls = { BROKEN: 'ERROR', SKIPPED: 'PENDING', UNKNOWN: 'PENDING' }[s] || s;
  return '<span class="status st-' + esc(cls) + '">' + esc(s) + '</span>';
}
/* run 统计：带标签的 共/通过/失败/异常 */
function runStatsHtml(t) {
  return '<span>共 <b>' + (t.total || 0) + '</b></span>' +
    '<span>通过 <b class="num-ok">' + (t.passed || 0) + '</b></span>' +
    '<span>失败 <b class="num-bad">' + (t.failed || 0) + '</b></span>' +
    '<span>异常 <b class="num-err">' + (t.error || 0) + '</b></span>';
}
/* run 概要（执行面板 / 详情页共用）：接口任务展示环境与标记，设备任务展示设备与 App */
function runMetaHtml(t, withStart) {
  const isApi = t.kind === 'api';
  return '<span>状态 ' + statusBadge(t.status) + '</span>' +
    '<span>类型 <b>' + (isApi ? '接口' : '设备') + '</b></span>' +
    (isApi
      ? '<span>环境 <b>' + esc(t.env || '-') + '</b></span>'
      : '<span>设备 <b>' + esc(t.device_model || t.device_desc || '-') + ' / ' + esc(t.udid || '-') + '</b></span>' +
        '<span>App <b>' + esc(t.app_package || '-') + '</b></span>') +
    (withStart ? '<span>开始 <b>' + fmtTime(t.start_time) + '</b></span>' : '') +
    runStatsHtml(t) +
    (t.marker ? '<span>标记 <b>' + esc(t.marker) + '</b></span>' : '') +
    (t.owner ? '<span>发起 <b>' + esc(t.owner) + '</b></span>' : '');
}
function fmtTime(s) { return s ? String(s).replace('T', ' ').slice(0, 19) : '-'; }

let _toastTimer = null;
function toast(msg, ok = true) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = msg;
  el.className = ok ? 'ok' : 'bad';
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 3000);   // 提示居中展示，3 秒消失
}

/* 自绘确认模态（替代原生 confirm）；页面没有模态骨架时退回原生 confirm */
function confirmModal(title, msg, danger) {
  const mask = $('#mask');
  if (!mask) return Promise.resolve(window.confirm(title + '\n\n' + msg));
  return new Promise((resolve) => {
    const btnOk = $('#mOk'), btnCancel = $('#mCancel');
    $('#mTitle').textContent = title;
    $('#mMsg').textContent = msg;
    btnOk.className = danger ? 'danger' : '';
    btnOk.textContent = danger ? '删除' : '确定';
    mask.classList.add('show');
    const done = (v) => { mask.classList.remove('show'); btnOk.onclick = btnCancel.onclick = null; resolve(v); };
    btnOk.onclick = () => done(true);
    btnCancel.onclick = () => done(false);
    mask.onclick = (e) => { if (e.target === mask) done(false); };
  });
}

/* ================= 顶部全局导航（面包屑路径，全站共用） =================
   导航结构来自共用的 nav.js（元素定位器也用它），样式来自共用的 nav.css；
   顶部显示「首页 / 当前页面 / 当前面板」面包屑：只有首页可点击，二三级纯文本；
   这里负责平台右侧状态条（设备 / Appium / 更新日志入口）与三级路径联动。 */
function renderSidebar(active, sub) {
  const nav = $('#sidebar');
  if (!nav) return;
  PlatformNav.render(nav, active,
    '<div class="foot">' +
    '<span><i class="dot ok" id="dotDevice"></i>设备 <span id="footDevice">…</span></span>' +
    '<span><i class="dot ok" id="dotAppium"></i>Appium <span id="footAppium">…</span></span>' +
    '<span><i class="dot ok" id="dotFramework" title="框架依赖 import 自检"></i>框架 <span id="footFramework">…</span></span>' +
    '<button class="ghost mini" id="btnChangelog" title="查看各版本更新时间与变更内容">更新日志 v<span id="clVer">…</span></button>' +
    '</div>', sub);
  const clBtn = $('#btnChangelog');
  if (clBtn) clBtn.addEventListener('click', showChangelog);
  pollFootStatus();
  setInterval(pollFootStatus, 10000);
}

/* 更新顶部面包屑第三级（各页面切面板时调用；导航未渲染时静默跳过） */
function setCrumbSub(sub) {
  if (window.PlatformNav) PlatformNav.setSub($('#sidebar'), sub);
}

/* ================= 更新日志（右上角入口） ================= */
async function showChangelog() {
  const d = await api('/api/changelog');
  if (!d.ok) return toast('更新日志加载失败', false);
  let mask = $('#clMask');
  if (!mask) {
    mask = document.createElement('div');
    mask.className = 'mask';
    mask.id = 'clMask';
    mask.innerHTML =
      '<div class="modal clmodal"><h4>更新日志</h4>' +
      '<div class="cllist" id="clList"></div>' +
      '<div class="mops"><button id="clClose">关闭</button></div></div>';
    document.body.appendChild(mask);
    mask.onclick = (e) => { if (e.target === mask) mask.classList.remove('show'); };
  }
  $('#clList').innerHTML = (d.entries || []).map(e =>
    '<div class="clitem' + (e.version === d.version ? ' cur' : '') + '">' +
      '<div class="clhead"><b>v' + esc(e.version) + '</b>' +
      '<span class="cltime">' + esc(e.time) + '</span>' +
      (e.version === d.version ? '<span class="clbadge">当前版本</span>' : '') + '</div>' +
      (e.title ? '<div class="cltitle">' + esc(e.title) + '</div>' : '') +
      '<ul>' + (e.changes || []).map(c => '<li>' + esc(c) + '</li>').join('') + '</ul>' +
    '</div>').join('');
  $('#clClose').onclick = () => mask.classList.remove('show');
  mask.classList.add('show');
}

async function pollFootStatus() {
  try {
    const st = await api('/api/status');
    // 版本号只保留「更新日志」按钮一处（品牌区不再显示），统一来自后端 changelog.py
    setText('#clVer', st.version || '?');
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
    // 框架依赖自检：缺模块时执行必失败，提前在页脚与设备配置卡暴露
    const d3 = $('#dotFramework'), f3 = $('#footFramework');
    if (d3) {
      const fw = st.framework || { ok: true, msg: '' };
      d3.className = 'dot ' + (fw.ok ? 'ok' : 'bad');
      f3.textContent = fw.ok ? '正常' : '缺依赖';
      f3.title = fw.msg || '';
      const dev = $('#devState');
      if (dev && !fw.ok && !dev.querySelector('.fw-bad')) {
        dev.insertAdjacentHTML('afterbegin',
          '<span class="pill bad fw-bad">框架缺依赖 ' + esc(fw.msg.replace('框架缺依赖：', '')) +
          ' —— 执行会失败，请先补齐环境</span>');
      }
    }
  } catch (e) { /* 状态条失败不打断页面 */ }
}

/* ================= 选择用例（testhub 式列表：所属项目筛选 + 搜索 + 命名 + 单执行） =================
   数据源：/api/cases（scan_case_tree：文件/方法/docstring/中文名映射/mtime）
         + app_testing 登记实体（node→项目归属，供「所属项目」筛选）。 */
let _caseRows = [];       // 选择用例表行 [{node, file, cls, method, cn_name, mtime, desc, ent}]
let _caseCnFile = null;   // 命名弹窗当前操作的用例文件

async function loadCaseSelectPanel() {
  const [tree, ents, projs] = await Promise.all([
    api('/api/cases'), api(AT_PREFIX + '/api/cases'), api(AT_PREFIX + '/api/projects')]);
  const treeList = tree.ok ? tree.tree : [];
  const entities = ents.ok ? (ents.results || []) : [];
  const projects = projs.ok ? (projs.results || []) : [];
  const entByNode = {};
  entities.forEach(e => { if (e.node) entByNode[e.node] = e; });
  _caseRows = [];
  treeList.forEach(f => (f.methods || []).forEach(m => {
    const node = f.file + '::' + f.class_name + '::' + m;
    _caseRows.push({ node, file: f.file, cls: f.class_name, method: m,
                     cn_name: f.cn_name || '', mtime: f.mtime || 0,
                     desc: (f.method_descs || {})[m] || '', ent: entByNode[node] || null });
  }));
  /* 所属项目下拉：全部 / 未登记 / 各项目（数据源 = 项目管理） */
  const sel = $('#caseProj');
  const cur = sel.value;
  sel.innerHTML = '<option value="">所属项目：全部</option>' +
    '<option value="__none__">未登记</option>' +
    projects.map(p => '<option value="' + p.id + '">' + esc(p.name) + '</option>').join('');
  if (cur) sel.value = cur;
  renderCaseTable();
}

function renderCaseTable() {
  const kw = ($('#caseSearch').value || '').trim().toLowerCase();
  const pf = $('#caseProj').value;
  const list = _caseRows.filter(r => {
    const reg = r.ent;
    const inProj = !pf || (pf === '__none__' ? !reg : !!(reg && +reg.project_id === +pf));
    const hay = [r.method, r.file, r.cls, r.cn_name, reg && reg.name, reg && reg.description];
    return inProj && (!kw || hay.some(v => String(v || '').toLowerCase().includes(kw)));
  });
  const fmtDate = ts => {
    if (!ts) return '-';
    const d = new Date(ts * 1000), p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  };
  $('#caseTbody').innerHTML = list.map(r => {
    const reg = r.ent;
    const fileLabel = r.cn_name ? r.cn_name + '（' + r.file.split('/').pop() + '）' : r.file.split('/').pop();
    return '<tr>' +
      '<td><input type="checkbox" data-node="' + esc(r.node) + '" class="ck-node"></td>' +
      '<td><b>' + esc((reg && reg.name) || r.method) + '</b>' +
        (reg ? '' : ' <span class="proj-status" title="尚未登记到项目，点「命名」旁可先登记归属">未登记</span>') +
        '<div class="path">' + esc(fileLabel + ' · ' + r.cls) + '</div></td>' +
      '<td>' + esc((reg && reg.description) || r.desc || '—') + '</td>' +
      '<td>' + fmtDate(r.mtime) + '</td>' +
      '<td class="ops"><button class="ghost mini" data-act="cn" data-file="' + esc(r.file) + '" data-cn="' + esc(r.cn_name) + '">命名</button>' +
      '<button class="mini" data-runone="' + esc(r.node) + '">执行</button></td></tr>';
  }).join('');
  $('#caseEmpty').style.display = list.length ? 'none' : '';
}

function openCaseCnModal(file, cn) {
  _caseCnFile = file;
  $('#caseCnFile').textContent = '用例文件：' + file;
  $('#caseCnInput').value = cn || '';
  $('#caseCnMask').classList.add('show');
  $('#caseCnInput').focus();
}

async function saveCaseCn() {
  const cn = ($('#caseCnInput').value || '').trim();
  const d = await postJson('/api/cases/cn-name', { file: _caseCnFile, cn_name: cn });
  toast(d.ok ? (cn ? '已映射中文名「' + cn + '」，元素定位器同步显示' : '已清除中文名映射') : (d.msg || '保存失败'), !!d.ok);
  if (d.ok) {
    $('#caseCnMask').classList.remove('show');
    await loadCaseSelectPanel();
  }
}

/* 单用例执行：走与「开始执行」同一 /api/run（单节点） */
async function runOneCase(node) {
  const conf = $('#confSel').value;
  if (!conf) return toast('请先在「设备配置」确认默认配置来源(conf)', false);
  const d = await postJson('/api/run', {
    conf_file: conf, case_nodes: [node],
    overrides: { udid: $('#inUdid').value.trim(), appPackage: $('#inPackage').value.trim(),
                 appActivity: $('#inActivity').value.trim() },
  });
  if (!d.ok) return toast(d.msg || '执行失败', false);
  toast('已开始执行 → Run ' + d.run_id, true);
  document.querySelector('[data-panel="cases"]').click();
  const execArea = $('#execArea');
  if (execArea) execArea.style.display = '';
  pollTask(d.run_id);
}

function setAllChecked(v, boxSel) {
  document.querySelectorAll((boxSel || '#caseTree') + ' input[type=checkbox]').forEach(n => n.checked = v);
}
function selectedCases(boxSel) {
  return Array.from(document.querySelectorAll((boxSel || '#caseTree') + ' .ck-node:checked'))
    .map(n => n.dataset.node);
}

/* ================= 执行面板（APP UI 与接口测试共用） ================= */
let _pollTimer = null, _logOffset = 0;

function pollTask(runId) {
  clearInterval(_pollTimer); _logOffset = 0;
  const box = $('#logBox');
  if (box) box.innerHTML = '';
  _pollTimer = setInterval(async () => {
    const d = await api('/api/run/' + runId);
    if (!d.ok) { clearInterval(_pollTimer); return; }
    const t = d.task;
    setText('#runIdNow', t.run_id);
    setHtml('#runStatusNow', statusBadge(t.status));
    setText('#runEnvNow', t.kind === 'api' ? (t.env || '-') : (t.device_model || t.device_desc || '-'));
    setHtml('#runStatsNow', runStatsHtml(t));
    const done = t.passed + t.failed + t.error + t.skipped;
    const bar = $('#runProgress');
    if (bar) bar.style.width = (t.total ? Math.min(100, Math.round(done / t.total * 100)) : 0) + '%';
    const stop = $('#btnStop');
    if (stop) stop.disabled = !(t.status === 'RUNNING' || t.status === 'PENDING');
    const go = $('#btnGoDetail');
    if (go) go.onclick = () => { location.href = '/runs/' + runId; };
    const lg = await api('/api/run/' + runId + '/log?offset=' + _logOffset);
    if (lg.ok) { _logOffset = lg.offset; renderLog(lg.lines); }
    if (t.status !== 'RUNNING' && t.status !== 'PENDING') {
      clearInterval(_pollTimer);
      if (t.error_msg) toast('任务异常: ' + t.error_msg, false);
      else toast('任务结束: ' + t.status + ' → 去「测试报告」查看用例明细', t.status === 'PASSED');
    }
  }, 1500);
}

function renderLog(lines, boxSel) {
  const box = $(boxSel || '#logBox');
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

/* ================= 首页（模块导航；执行总览已迁至测试报告页顶部） ================= */
function initIndex() {
  renderSidebar('/');
  // 入口卡片的圆形线性图标：data-ico 声明图标名，这里统一注入
  document.querySelectorAll('.card-icon .ico[data-ico]').forEach(el => {
    el.innerHTML = icon(el.dataset.ico, 34);
  });
}

/* 统计卡右上角的淡色线性图标：图标定义只在 app.js 一处，模板只声明用哪个（测试报告页用） */
function initStatIcons() {
  document.querySelectorAll('.stat[data-ico]').forEach(el => {
    const box = el.querySelector('.bgico');
    if (box) box.innerHTML = icon(el.dataset.ico, 42);
  });
}

async function refreshStats() {
  try {
    const d = await api('/api/runs');
    const runs = d.runs || [];
    const pass = runs.filter(r => r.status === 'PASSED').length;
    const fail = runs.filter(r => r.status === 'FAILED' || r.status === 'ERROR').length;
    setText('#cardRuns', runs.length);
    setText('#cardPass', pass);
    setText('#cardFail', fail);
    setText('#cardRate', runs.length ? Math.round(pass / runs.length * 100) + '%' : '—');
  } catch (e) { /* 统计失败不打断页面 */ }
}

/* ================= 执行记录渲染（首页/报告页共用） =================
   设备列：设备任务显示真实型号（runner 启动时从 adb 取，如 FGD AL00=华为）；
   旧历史记录无 device_model 时回退显示 conf 别名 device_desc。
   接口任务没有设备，同一列改显示「接口 · 环境」，App 列改显示项目名。 */
function runTarget(r) {
  return r.kind === 'api' ? ('接口 · ' + (r.env || '-')) : (r.device_model || r.device_desc || '-');
}
function runSubject(r) {
  if (r.kind === 'api') {
    const parts = String(r.conf_file || '').split('/');
    return parts.length > 1 ? parts[1] : (parts[0] || '-');
  }
  return (r.app_package || '-').split('.').pop();
}

function runRowHtml(r, withOps) {
  return '<tr>' +
    '<td><a class="runlink" href="/runs/' + esc(r.run_id) + '">' + esc(r.run_id) + '</a></td>' +
    '<td>' + fmtTime(r.start_time) + '</td>' +
    '<td title="' + esc(r.udid || r.conf_file || '') + '">' + esc(runTarget(r)) + '</td>' +
    '<td title="' + esc(r.app_package || r.conf_file || '') + '">' + esc(runSubject(r)) + '</td>' +
    '<td><b>' + r.total + '</b> / <span class="num-ok">' + r.passed + '</span> / <span class="num-bad">' + r.failed + '</span></td>' +
    '<td>' + statusBadge(r.status) + '</td>' +
    (withOps ? '<td><div class="ops">' +
      '<a class="btn ghost mini" href="/runs/' + esc(r.run_id) + '">详情</a>' +
      '<button class="ghost mini" onclick="openReportFor(\'' + esc(r.run_id) + '\', this)">报告</button>' +
      '<button class="mini danger-ghost" onclick="deleteRunFor(\'' + esc(r.run_id) + '\')">删除</button>' +
      '</div></td>' : '') +
    '</tr>';
}

function renderRunRows(sel, runs, withOps) {
  const tbody = $(sel);
  if (!tbody) return;
  if (!runs.length) {
    tbody.innerHTML = '<tr><td colspan="7">' +
      emptyHtml('folder', '暂无执行记录<br><a class="runlink" href="/run">去执行页开始第一次测试 →</a>') +
      '</td></tr>';
    return;
  }
  tbody.innerHTML = runs.map(r => runRowHtml(r, withOps)).join('');
}

async function loadRunsTable(sel, withOps, limit) {
  const d = await api('/api/runs');
  renderRunRows(sel, (d.runs || []).slice(0, limit || 100), withOps);
}

/* ================= 分页（每页 10 条） ================= */
const PAGE_SIZE = 10;
let _reportPage = 1;

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

/* 详情占位（报告页内嵌区 / 独立详情页共用文案） */
function detailPlaceholder() {
  return emptyHtml('hand', '从上方列表选择一条执行记录查看详情');
}

async function deleteRunFor(runId) {
  const yes = await confirmModal('删除执行记录', '将删除 ' + runId + ' 的全部数据（Allure 结果、日志），不可恢复。', true);
  if (!yes) return;
  const d = await del('/api/runs/' + runId);
  toast(d.msg || (d.ok ? '已删除' : '删除失败'), d.ok);
  if (d.ok && _activeDetailRun === runId) {
    clearInterval(_detailTimer); _detailTimer = null;
    _activeDetailRun = null;
    setHtml('#runDetail', detailPlaceholder());
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
    setHtml('#runDetail', detailPlaceholder());
  }
  refreshAfterOps();
}

function refreshAfterOps() {
  const page = document.body.dataset.page;
  if (page === 'report') { refreshStats(); loadRunsTable('#recentList', true, 10); loadReportList(); }
}

/* ================= APP UI 执行页 ================= */
async function initRun() {
  renderSidebar('/run');
  initRunPanels();
  await loadExecDefaults();
  await loadRecordingConfig();
  await loadCaseSelectPanel();
  $('#btnStart').addEventListener('click', startRun);
  $('#btnStop').addEventListener('click', stopRun);
  $('#btnSelectAll').addEventListener('click', () => setAllChecked(true));
  $('#btnSelectNone').addEventListener('click', () => setAllChecked(false));
  $('#caseProj').addEventListener('change', renderCaseTable);
  $('#caseSearch').addEventListener('input', renderCaseTable);
  $('#btnCaseRefresh').addEventListener('click', loadCaseSelectPanel);
  $('#caseTbody').addEventListener('click', e => {
    const cn = e.target.closest('[data-act=cn]'), run = e.target.closest('[data-runone]');
    if (cn) return openCaseCnModal(cn.dataset.file, cn.dataset.cn);
    if (run) return runOneCase(run.dataset.runone);
  });
  $('#caseCnSave').addEventListener('click', () => saveCaseCn().catch(e => toast(e.message, false)));
  $('#caseCnCancel').addEventListener('click', () => $('#caseCnMask').classList.remove('show'));
  $('#caseCnMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });
  $('#confSel').addEventListener('change', () => loadExecDefaults($('#confSel').value));
  $('#btnRecSave').addEventListener('click', saveRecordingConfig);
  initElementsPanel();
  adminPanelInit();   // 用例管理面板（原独立模块并入，绑定见 admin.js）
  appTestingInit();   // 用例编排 / 测试套件面板（绑定见 app_testing.js）
  // 测试报告面板（原一级模块并入）：首次进入才加载 iframe，避免每次进 /run 都拉报告数据
  const reportLink = document.querySelector('[data-panel="report"]');
  if (reportLink) reportLink.addEventListener('click', () => {
    if (!$('#reportFrame').src) $('#reportFrame').src = '/report';
  });
}

/* ---------------- 左侧二级菜单：hash 深链 + 记住上次所在面板 ---------------- */
const RUN_PANELS = ['projects', 'elements', 'cases', 'caselist', 'orch', 'suites', 'report', 'admin', 'exec'];
/* 面板名 → 顶部面包屑第三级文案 */
const RUN_PANEL_NAMES = {
  projects: '项目管理', elements: '元素管理', cases: '选择用例', caselist: '测试用例',
  orch: '用例编排', suites: '测试套件', report: '测试报告', admin: '用例上传', exec: '设备配置',
};
function showRunPanel(name) {
  if (!RUN_PANELS.includes(name)) name = 'exec';
  RUN_PANELS.forEach(p => {
    const sec = $('#panel-' + p);
    if (sec) sec.hidden = (p !== name);
  });
  document.querySelectorAll('#subnav a').forEach(a =>
    a.classList.toggle('on', a.dataset.panel === name));
  setCrumbSub(RUN_PANEL_NAMES[name]);
}
function initRunPanels() {
  document.querySelectorAll('#subnav a').forEach(a => {
    if (a.dataset.icon) a.insertAdjacentHTML('afterbegin', icon(a.dataset.icon, 18));
    a.addEventListener('click', (e) => {
      e.preventDefault();
      showRunPanel(a.dataset.panel);
      history.replaceState(null, '', '#' + a.dataset.panel);
    });
  });
  /* 初始面板：hash 深链优先，否则默认第一个（项目管理）——不恢复上次停留 */
  let start = (location.hash || '').replace('#', '');
  if (!RUN_PANELS.includes(start)) start = RUN_PANELS[0];
  showRunPanel(start);
}

/* ================= 元素管理（元素库列表 / 编辑 / 复制 / 删除） =================
   数据源与元素定位器、执行框架同一份元素库（page_objects/.../elements/*.py）；
   编辑/复制走后端 /api/appui/elements/save，写回复用定位器同一套行生成逻辑。 */
let _elements = [], _elFiles = [], _elTypes = [], _elWaits = [];
let _elModalMode = 'edit', _elModalOrig = null;

async function loadElements() {
  const d = await api('/api/appui/elements');
  if (!d.ok) return toast(d.msg || '元素列表加载失败', false);
  _elements = d.elements || [];
  _elFiles = d.files || [];
  _elTypes = d.locator_types || ['ID', 'XPATH'];
  _elWaits = d.wait_types || ['VISIBILITY_OF'];
  /* 元素文件筛选下拉：排除备份文件，重建时保留当前选择；弹窗规则库只读展示（见 renderElements） */
  const curFile = $('#elFileFilter').value;
  $('#elFileFilter').innerHTML = '<option value="">全部元素文件</option>' +
    _elFiles.filter(f => !f.includes('_backup')).map(f =>
      '<option value="' + esc(f) + '"' + (f === curFile ? ' selected' : '') + '>' + esc(f) + '</option>').join('') +
    (_elements.some(e => e.popup)
      ? '<option value="popupElements.py">popupElements.py（弹窗规则库）</option>' : '');
  renderElements();
}

function renderElements() {
  const kw = ($('#elSearch').value || '').trim().toLowerCase();
  const ff = $('#elFileFilter').value;
  const list = _elements.filter(e =>
    (!ff || e.file === ff) &&
    (!kw || [e.name, e.cn_name, e.value, e.desc, e.type, e.file].some(v =>
      String(v || '').toLowerCase().includes(kw))));
  const fmtDate = ts => {
    if (!ts) return '-';
    const d = new Date(ts * 1000), p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  };
  $('#elTbody').innerHTML = list.map(e => {
    /* 名称列：有中文名 → 主行中文、副行代码名；无 → 主行代码名、副行文件名（旧行为） */
    const nameCell = e.cn_name
      ? '<b>' + esc(e.cn_name) + '</b>' + (e.popup ? ' <span class="el-popup-badge">规则</span>' : '') + '<br><span class="el-file">' + esc(e.name) + '</span>'
      : '<b>' + esc(e.name) + '</b>' + (e.popup ? ' <span class="el-popup-badge">规则</span>' : '') + '<br><span class="el-file">' + esc(e.file) + '</span>';
    /* 弹窗规则库行只读：文件里 RULE_OPTIONS/WHITELIST 与元素行共存，普通编辑会重写整文件抹掉规则 */
    const actions = e.popup
      ? '<span class="el-popup-note" title="由元素定位器「登记随机弹窗」专管（锚点/冷却/白名单同文件存放），此处只读">规则库 · 到定位器「登记随机弹窗」管理</span>'
      : '<div class="ops">' +
    '<button class="ghost mini" data-act="edit" data-name="' + esc(e.name) + '" data-file="' + esc(e.file) + '">编辑</button>' +
    '<button class="ghost mini" data-act="copy" data-name="' + esc(e.name) + '" data-file="' + esc(e.file) + '">复制</button>' +
    '<button class="mini danger-ghost" data-act="del" data-name="' + esc(e.name) + '" data-file="' + esc(e.file) + '">删除</button>' +
    '</div>';
    return '<tr>' +
    '<td>' + nameCell + '</td>' +
    '<td>' + esc(e.type) + '</td>' +
    '<td>' + esc(e.desc || '-') + '</td>' +
    '<td><span class="el-preview" title="' + esc(e.value) + '">' + esc(e.value) + '</span></td>' +
    '<td><span class="usage-num' + (e.usage_count ? '' : ' zero') + '">' + e.usage_count + '</span></td>' +
    '<td>' + fmtDate(e.created_at) + '</td>' +
    '<td>' + actions + '</td></tr>';
  }).join('');
  $('#elEmpty').style.display = list.length ? 'none' : '';
}

function fillSelect(sel, options, val) {
  sel.innerHTML = options.map(o =>
    '<option value="' + esc(o) + '"' + (o === val ? ' selected' : '') + '>' + esc(o) + '</option>').join('');
}

/* 编辑 / 复制共用一个弹窗：编辑 = 名称可改（改名=删旧增新）+ 文件固定；
   复制 = 预填原元素内容、名称留待修改 + 目标文件可选。 */
function openElModal(mode, name, file) {
  const el = _elements.find(e => e.name === name && e.file === file) || {};
  _elModalMode = mode;
  _elModalOrig = mode === 'edit' ? name : null;
  $('#elModalTitle').textContent = mode === 'edit' ? '✎ 编辑元素' : '⧉ 复制元素';
  $('#elMName').value = mode === 'edit' ? (el.name || '') : '';
  $('#elMName').placeholder = mode === 'copy' ? '新元素名称（不能与已有元素同名）' : '';
  $('#elMCnName').value = mode === 'edit' ? (el.cn_name || '') : '';
  fillSelect($('#elMType'), _elTypes, el.type || 'ID');
  fillSelect($('#elMWait'), _elWaits, el.wait_type || 'VISIBILITY_OF');
  $('#elMValue').value = el.value || '';
  $('#elMWaitSec').value = el.wait_seconds || 6;
  $('#elMDesc').value = el.desc || '';
  fillSelect($('#elMFile'), _elFiles, mode === 'edit' ? (el.file || _elFiles[0]) : (file || _elFiles[0]));
  $('#elMFile').disabled = (mode === 'edit');   // 编辑不挪窝：换文件=先删后增，容易把页面引用弄丢
  $('#elMFileWrap').style.display = mode === 'edit' ? 'none' : '';
  $('#elMask').classList.add('show');
}

async function saveElModal() {
  const name = $('#elMName').value.trim();
  const value = $('#elMValue').value.trim();
  if (!name) return toast('请填写元素名称', false);
  if (!value) return toast('请填写定位值', false);
  const btn = $('#elMSave');
  btn.disabled = true; btn.textContent = '保存中…';
  try {
    const d = await postJson('/api/appui/elements/save', {
      file: $('#elMFile').value,
      orig_name: _elModalOrig,
      name: name,
      cn_name: $('#elMCnName').value.trim(),
      locator_type: $('#elMType').value,
      value: value,
      wait_type: $('#elMWait').value,
      wait_seconds: $('#elMWaitSec').value,
      desc: $('#elMDesc').value.trim(),
    });
    toast(d.msg || (d.ok ? '已保存' : '保存失败'), !!d.ok);
    if (d.ok) {
      $('#elMask').classList.remove('show');
      await loadElements();
    }
  } finally {
    btn.disabled = false; btn.textContent = '保存';
  }
}

async function deleteElement(name, file) {
  const yes = await confirmModal('删除元素',
    '将从 ' + file + ' 中删除元素 ' + name + ' 的定义。若页面方法仍在引用它，执行时会找不到元素。确定删除？', true);
  if (!yes) return;
  const d = await postJson('/api/appui/elements/delete', { file: file, name: name });
  toast(d.msg || (d.ok ? '已删除' : '删除失败'), !!d.ok);
  if (d.ok) loadElements();
}

function onElTableClick(e) {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const name = btn.dataset.name, file = btn.dataset.file;
  if (btn.dataset.act === 'edit') openElModal('edit', name, file);
  else if (btn.dataset.act === 'copy') openElModal('copy', name, file);
  else if (btn.dataset.act === 'del') deleteElement(name, file);
}

function initElementsPanel() {
  $('#btnElRefresh').addEventListener('click', loadElements);
  $('#elSearch').addEventListener('input', renderElements);
  $('#elFileFilter').addEventListener('change', renderElements);
  $('#elTbody').addEventListener('click', onElTableClick);
  $('#elMCancel').addEventListener('click', () => $('#elMask').classList.remove('show'));
  $('#elMSave').addEventListener('click', saveElModal);
  $('#elMask').addEventListener('click', (e) => {
    if (e.target === $('#elMask')) $('#elMask').classList.remove('show');
  });
  loadElements();
}

/* ================= 录屏配置（失败证据视频的开关与时间参数，存 config/recording.conf） ================= */
async function loadRecordingConfig() {
  try {
    const d = await api('/api/recording/config');
    if (!d.ok) return;
    const c = d.config || {};
    $('#recBefore').value = c.before_seconds;
    $('#recAfter').value = c.after_seconds;
    $('#recMaxSeg').value = c.max_segment_seconds;
    $('#recBitRate').value = c.bit_rate;
    $('#recEnabled').checked = !!c.enabled;
    $('#recKeep').checked = !!c.keep_on_success;
    $('#recRequired').checked = !!c.required;
  } catch (e) { /* 配置加载失败不打断执行页 */ }
}

async function saveRecordingConfig() {
  const payload = {
    before_seconds: $('#recBefore').value.trim(),
    after_seconds: $('#recAfter').value.trim(),
    max_segment_seconds: $('#recMaxSeg').value.trim(),
    bit_rate: $('#recBitRate').value.trim(),
    enabled: $('#recEnabled').checked,
    keep_on_success: $('#recKeep').checked,
    required: $('#recRequired').checked,
  };
  const d = await postJson('/api/recording/config', payload);
  toast(d.msg || (d.ok ? '已保存' : '保存失败'), !!d.ok);
  if (d.ok) loadRecordingConfig();   // 回读校准（含边界裁剪后的值）
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
    '<span class="pill ' + (online ? 'ok' : 'bad') + '">' + (online ? '设备在线' : '未检测到在线设备') + '</span>' +
    '<span>设备 <b>' + esc(d.defaults.udid || '-') + '</b>' +
    (!online && d.defaults.udid ? ' <span class="muted">(conf 预填，未连接)</span>' : '') + '</span>' +
    '<span>型号 <b>' + esc(d.defaults.model || '-') + '</b></span>' +
    '<span>Appium <b>' + (d.defaults.appium_ok ? '正常' : '不可用') + '</b></span>' +
    '<span>服务 <b>' + esc(d.defaults.server || '-') + '</b></span>' +
    (d.defaults.occupied ? '<span class="pill bad">有任务执行中</span>' : '');
}

async function startRun() {
  const conf = $('#confSel').value;
  const cases = selectedCases();
  if (!conf) return toast('请选择默认配置来源(conf)', false);
  if (!cases.length) return toast('请至少勾选一个用例', false);
  const btn = $('#btnStart');
  btn.disabled = true; btn.textContent = '启动中…';
  const d = await postJson('/api/run', {
    conf_file: conf,
    case_nodes: cases,
    overrides: {
      udid: $('#inUdid').value.trim(),
      appPackage: $('#inPackage').value.trim(),
      appActivity: $('#inActivity').value.trim(),
    },
  });
  btn.disabled = false; btn.textContent = '开始执行';
  if (!d.ok) return toast(d.msg || '启动失败', false);
  $('#execArea').style.display = 'block';
  $('#execArea').scrollIntoView({ behavior: 'smooth', block: 'start' });
  toast('任务 ' + d.run_id + ' 已启动');
  pollTask(d.run_id);
}

/* ================= 接口测试页 =================
   接口测试已整体移植 testhub_platform 功能（接口管理/套件/定时任务/环境），
   页面初始化由 static/api_testing.js 接管；这里不再保留旧 pytest 选例逻辑。 */

/* ================= 执行详情页 ================= */
let _detailTimer = null;

async function initRunDetail() {
  renderSidebar('/run', '执行详情');
  await renderRunDetail('#detailBody', document.body.dataset.runId);
}

/* ================= 详情组件：run 概要 + 用例执行记录 + 证据 + 执行日志 =================
   自建视图，直接解析 allure-results；报告页「详情」与 run_detail 页共用 */
let _activeDetailRun = null, _activeSel = null;

function shotHtml(runId, shot) {
  const src = '/api/runs/' + encodeURIComponent(runId) + '/res/' + encodeURIComponent(shot.source);
  return '<img class="thumb" src="' + src + '" title="' + esc(shot.name || shot.source) + '"' +
    ' onclick="openLightbox(\'' + src + '\', \'' + esc(shot.name || shot.source) + '\')">';
}

/* 文本证据折叠块：接口用例的请求-响应留痕、失败原因等 */
function evHtml(texts) {
  if (!texts || !texts.length) return '';
  return texts.map(t =>
    '<details class="ev"><summary>' + esc(t.name || '文本证据') + '</summary>' +
    '<pre>' + esc(t.content || '（空）') + '</pre></details>').join('');
}

function caseRowHtml(runId, c, idx) {
  const dur = c.duration_ms ? (c.duration_ms / 1000).toFixed(1) + 's' : '-';
  const steps = c.steps || [];
  const shots = c.screenshots || [];
  const texts = c.texts || [];
  const stepHtml = steps.length ? '<ul class="steps">' + steps.map(s => {
    const ss = s.attachments || [];
    return '<li class="st-' + esc(s.status) + '"><span class="sico">' +
      (s.status === 'passed' ? '✓' : s.status === 'failed' ? '✗' : '○') + '</span>' +
      esc(s.name) +
      (ss.length ? '<span class="shots">' + ss.map(a => shotHtml(runId, a)).join('') + '</span>' : '') +
      evHtml(s.texts) +
      '</li>';
  }).join('') + '</ul>' : '';
  const errHtml = c.error_message ? '<div class="err">' + esc(c.error_message) + '</div>' : '';
  const oldShots = (!steps.length && shots.length)
    ? '<div class="shots">' + shots.map(a => shotHtml(runId, a)).join('') + '</div>' : '';
  const none = (!steps.length && !shots.length && !texts.length)
    ? '<p class="muted">该用例无步骤/截图/文本数据（旧版执行记录，仅保留统计）</p>' : '';
  const evCount = texts.length ? ' · ' + texts.length + ' 文' : '';
  return '<tr class="case-row"><td class="xpand"><button class="ghost mini" data-t="' + idx + '">展开</button></td>' +
    '<td>' + esc(c.name) + '</td><td>' + statusBadge(c.status) + '</td>' +
    '<td class="muted">' + dur + '</td><td class="muted">' + shots.length + ' 图' + evCount + '</td></tr>' +
    '<tr class="detail-row" data-t="' + idx + '" style="display:none"><td colspan="5">' +
    stepHtml + errHtml + evHtml(texts) + oldShots + none + '</td></tr>';
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
    box.innerHTML = '<div class="card">' + emptyHtml('doc', esc(d.msg || '任务不存在')) + '</div>';
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
    '<div class="meta" id="detailMeta">' + runMetaHtml(t, true) + '</div>' +
    (t.error_msg ? '<p class="mt" style="color:var(--bad-text)">' + esc(t.error_msg) + '</p>' : '') +
    (cases.length ? '<div class="tblwrap mt"><table><thead><tr><th></th><th>用例</th><th>结果</th><th>耗时</th><th>证据</th></tr></thead><tbody>' +
      cases.map((c2, i) => caseRowHtml(runId, c2, i)).join('') +
      '</tbody></table></div>' :
      '<div class="mt">' + emptyHtml('doc', '该 run 没有用例数据（allure-results 缺失或已删除）') + '</div>') +
    '</div>' +
    '<div class="card"><div class="cardhead"><h3>执行日志 <span class="muted" id="logCount"></span></h3></div>' +
    '<div class="logbox" id="detailLogBox"></div></div>';
  // 用例行展开/收起（事件委托，避免轮询重建后按钮失效）
  box.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-t]');
    if (!b) return;
    const tr = box.querySelector('tr.detail-row[data-t="' + b.dataset.t + '"]');
    if (tr) tr.style.display = tr.style.display === 'none' ? '' : 'none';
  });
  // 日志：全量加载；RUNNING 时增量轮询
  const lg0 = await api('/api/run/' + runId + '/log?offset=0');
  if (lg0.ok) { setText('#logCount', '共 ' + lg0.lines.length + ' 行'); renderLog(lg0.lines, '#detailLogBox'); }
  if (!running) return;
  let off = lg0.ok ? lg0.offset : 0;
  _detailTimer = setInterval(async () => {
    const lg = await api('/api/run/' + runId + '/log?offset=' + off);
    if (lg.ok) {
      off = lg.offset;
      setText('#logCount', '共 ' + off + ' 行');
      renderLog(lg.lines, '#detailLogBox');
    }
    const st = await api('/api/run/' + runId);
    if (!st.ok) return;
    if (st.task.status !== 'RUNNING' && st.task.status !== 'PENDING') {
      clearInterval(_detailTimer); _detailTimer = null;
      renderRunDetail(_activeSel, runId);   // 收尾：刷新最终状态与用例
    } else {
      setHtml('#detailMeta', runMetaHtml(st.task, true));
    }
  }, 3000);
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
  lb.innerHTML = '<img src="' + src + '" alt="' + esc(name) + '"><button class="lb-close">✕</button>';
  lb.classList.add('show');
  lb.onclick = () => lb.classList.remove('show');
}

/* ================= 测试报告页（含执行总览：统计卡 + 最近执行） ================= */
async function initReport() {
  renderSidebar('/report');
  $('#btnClearAll3').addEventListener('click', clearAllRuns);
  initStatIcons();
  setHtml('#runDetail', detailPlaceholder());
  await Promise.all([refreshStats(), loadRunsTable('#recentList', true, 10), loadReportList()]);
  setInterval(() => { refreshStats(); loadRunsTable('#recentList', true, 10); }, 8000);
  setInterval(loadReportList, 8000);
}

async function loadReportList() {
  const d = await api('/api/runs');
  const tb = $('#reportList');
  if (!tb) return;
  const runs = d.runs || [];
  if (!runs.length) {
    tb.innerHTML = '<tr><td colspan="6">' +
      emptyHtml('chart', '暂无执行记录，先生成一次执行') + '</td></tr>';
    setHtml('#reportPager', '');
    return;
  }
  const pages = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  _reportPage = Math.min(Math.max(1, _reportPage), pages);
  const slice = runs.slice((_reportPage - 1) * PAGE_SIZE, _reportPage * PAGE_SIZE);
  tb.innerHTML = slice.map(r =>
    '<tr><td><a class="runlink" href="/runs/' + esc(r.run_id) + '">' + esc(r.run_id) + '</a></td>' +
    '<td>' + fmtTime(r.start_time) + '</td>' +
    '<td>' + statusBadge(r.status) + '</td>' +
    '<td class="muted">' + esc(runTarget(r)) + '</td>' +
    '<td>' + (r.report_dir ? '<span class="num-ok">已生成</span>' : '<span class="muted">未生成</span>') + '</td>' +
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
  if (btn) { btn.disabled = true; btn.textContent = '打开中…'; }
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

/* ================= 性能压测页 ================= */
let perfSchema = [], perfValues = {}, perfRunId = '', perfLogOffset = 0, perfTimer = null;

function perfInputId(f) {
  return 'pf_' + (f.section ? f.section.replace(/\./g, '_') + '__' : '') + f.key;
}
function perfCollect() {
  const out = {};
  perfSchema.forEach(g => g.fields.forEach(f => {
    const el = document.getElementById(perfInputId(f));
    if (!el) return;
    const fk = (f.section ? f.section + '.' : '') + f.key;
    out[fk] = (f.type === 'bool') ? el.checked : el.value;
  }));
  return out;
}
/* show_if 字段可见性：加压策略参数随「压测模式」二选一显示（隐藏字段的值仍随表单一起提交/保存） */
function perfFieldVisible(f) {
  if (!f.show_if) return true;
  const modeEl = document.getElementById('pf_mode');
  return !modeEl || modeEl.value === f.show_if;
}
function perfApplyVisibility() {
  perfSchema.forEach(g => g.fields.forEach(f => {
    if (!f.show_if) return;
    const el = document.getElementById(perfInputId(f));
    const wrap = el && el.closest('.field');
    if (wrap) wrap.style.display = perfFieldVisible(f) ? '' : 'none';
  }));
}
function perfRenderForm() {
  const box = $('#perfForm');
  box.innerHTML = perfSchema.map(g => {
    const fields = g.fields.map(f => {
      const id = perfInputId(f);
      const fk = (f.section ? f.section + '.' : '') + f.key;
      const v = perfValues[fk];
      let input = '';
      if (f.type === 'select') {
        input = '<select id="' + id + '">' + f.options.map(o =>
          '<option value="' + o + '"' + (String(v) === o ? ' selected' : '') + '>' + o + '</option>').join('') + '</select>';
      } else if (f.type === 'bool') {
        input = '<label class="chk"><input type="checkbox" id="' + id + '"' + (v ? ' checked' : '') + '> ' + esc(f.label) + '</label>';
      } else if (f.type === 'dict') {
        const txt = Object.keys(v || {}).map(k => k + ': ' + (v[k] === undefined ? '' : v[k])).join('\n');
        input = '<textarea id="' + id + '" placeholder="每行一条：名: 值">' + esc(txt) + '</textarea>';
      } else if (f.type === 'text') {
        input = '<textarea id="' + id + '">' + esc(v === undefined || v === null ? '' : v) + '</textarea>';
      } else {
        input = '<input type="text" id="' + id + '" value="' + esc(v === undefined || v === null ? '' : v) + '">';
      }
      const wide = (f.type === 'dict' || f.type === 'text') ? ' wide' : '';
      const tip = f.help ? ' <span class="muted">' + esc(f.help) + '</span>' : '';
      const label = f.type === 'bool' ? '' : '<label>' + esc(f.label) + tip + '</label>';
      return '<div class="field' + wide + '">' + label + input + '</div>';
    }).join('');
    const head = '<h4>' + esc(g.group) + '</h4><div class="gdesc">' + esc(g.desc) + '</div>';
    const body = '<div class="perf-fields">' + fields + '</div>';
    /* 高级组收进折叠区（details.adv 为平台全局样式），默认收起，展开才见全部低频项 */
    return g.advanced
      ? '<details class="adv perf-group-adv"><summary>高级参数（默认即可，无需改动）</summary>' +
        '<div class="perf-group">' + head + body + '</div></details>'
      : '<div class="perf-group">' + head + body + '</div>';
  }).join('');
  const modeSel = document.getElementById('pf_mode');
  if (modeSel) modeSel.addEventListener('change', perfApplyVisibility);
  perfApplyVisibility();
}
function perfResult(msg, ok) {
  const el = $('#perfResult');
  if (!el) return;
  el.className = 'el-result ' + (ok ? 'ok' : 'err');
  el.textContent = msg;
}
async function perfStart() {
  const r = await postJson('/api/perf/run', { values: perfCollect() });
  if (!r.ok) { perfResult(r.msg || '启动失败', false); return; }
  perfRunId = r.run_id; perfLogOffset = 0;
  $('#perfLog').textContent = '';
  $('#btnPerfReport').style.display = 'none';
  perfResult(r.msg, true);
  perfTimer = setInterval(perfPoll, 1500);
  perfPoll();
}
async function perfStop() {
  if (!perfRunId) return;
  const r = await postJson('/api/perf/stop', { run_id: perfRunId });
  perfResult(r.msg, r.ok);
}
async function perfPoll() {
  if (!perfRunId) return;
  const [st, lg] = await Promise.all([
    api('/api/perf/run/' + perfRunId),
    api('/api/perf/run/' + perfRunId + '/log?offset=' + perfLogOffset),
  ]);
  if (lg.ok && lg.lines && lg.lines.length) {
    const box = $('#perfLog');
    box.textContent += lg.lines.join('\n') + '\n';
    box.scrollTop = box.scrollHeight;
    perfLogOffset = lg.offset;
  }
  if (!st.ok) return;
  const run = st.run;
  const badge = { RUNNING: '<span class="badge run">运行中</span>', FINISHED: '<span class="badge ok">已完成</span>',
    FAILED: '<span class="badge bad">失败</span>', STOPPED: '<span class="badge stop">已停止</span>' }[run.status] || run.status;
  $('#perfStatus').innerHTML = badge + ' · ' + esc(run.run_id) + ' · ' + Math.round(run.duration_ms / 1000) + 's'
    + (run.error ? ' · ' + esc(run.error) : '');
  if (run.status !== 'RUNNING') {
    clearInterval(perfTimer); perfTimer = null;
    if (run.report) { $('#btnPerfReport').style.display = ''; perfResult('压测结束，报告已生成', true); }
    else perfResult('压测结束（未生成报告，请查看日志）', false);
  }
}
async function initPerf() {
  renderSidebar('/perf');
  const r = await api('/api/perf/config');
  perfSchema = r.schema || []; perfValues = r.values || {};
  perfRenderForm();
  setText('#perfEnv', r.venv_ready
    ? '压测环境就绪（perf_test/.venv · Python 3.13 + locust，与平台主环境隔离）'
    : '压测环境未就绪：执行 python3 -m venv perf_test/.venv && perf_test/.venv/bin/pip install -r perf_test/requirements-perf.txt');
  $('#btnPerfStart').addEventListener('click', perfStart);
  $('#btnPerfStop').addEventListener('click', perfStop);
  $('#btnPerfSave').addEventListener('click', async () => {
    const r2 = await postJson('/api/perf/config', perfCollect());
    perfResult(r2.msg || (r2.ok ? '已保存' : '保存失败'), r2.ok);
    if (r2.ok) {
      const rf = await api('/api/perf/config');
      perfValues = rf.values || {};
      perfRenderForm();
    }
  });
  $('#btnPerfReport').addEventListener('click', () => { if (perfRunId) location.href = '/perf/report/' + perfRunId; });
}

/* ================= 页面分发 ================= */
document.addEventListener('DOMContentLoaded', () => {
  const page = document.body.dataset.page;
  if (page === 'index') initIndex();
  else if (page === 'run') initRun();
  else if (page === 'detail') initRunDetail();
  else if (page === 'report') initReport();
  else if (page === 'perf') initPerf();
  /* api-test 页由 static/api_testing.js 自行初始化 */
});
