/* 接口测试（testhub_platform api_testing 完整移植版）· 前端工作台
   ------------------------------------------------------------------
   面板：仪表盘 / 项目管理 / 接口管理（集合树+调试+WebSocket+AI） /
         自动化测试（套件编排+执行+记录）/ 请求历史 / 环境管理 /
         测试报告（Allure）/ 定时任务 / 通知列表+配置 / AI 服务配置。
   数据全部走 /api-testing/api/* REST 端点；用例数据 YAML 存储（预留数据库迁移）。 */
'use strict';

const AT = (function () {
  const API = '/api-testing/api';
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  const state = {
    projects: [], collections: [], requests: [], envs: [], suites: [], tasks: [],
    users: [], selReqId: null, selSuiteId: null, selProject: null,
    histTab: 'HTTP', histPage: 1, histSel: new Set(), envTab: 'GLOBAL',
    ws: null, wsLogLines: [], lastVarTarget: null, varCatalog: null,
  };

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
    const res = await fetch(API + path, opts);
    const d = await res.json().catch(() => ({ ok: false, msg: '响应解析失败(' + res.status + ')' }));
    if (!res.ok || d.ok === false) throw new Error(d.msg || ('HTTP ' + res.status));
    return d;
  }
  const fmtTime = (ts) => {
    if (!ts) return '-';
    const d = new Date(ts * 1000), p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  };
  const METHOD_COLOR = {
    GET: '#1d7a3a', POST: '#0071e3', PUT: '#b25000', DELETE: '#d70015',
    PATCH: '#8944ab', HEAD: '#6e6e73', OPTIONS: '#6e6e73',
  };
  const mBadge = (m) => `<span class="m-badge" style="background:rgba(0,113,227,.1);color:${METHOD_COLOR[m] || '#6e6e73'}">${esc(m)}</span>`;
  const ST = {
    COMPLETED: 'st-PASSED', PASSED: 'st-PASSED', success: 'st-PASSED', ACTIVE: 'st-PASSED',
    RUNNING: 'st-RUNNING', sending: 'st-RUNNING',
    PENDING: 'st-PENDING', PAUSED: 'st-PENDING', pending: 'st-PENDING',
    FAILED: 'st-FAILED', failed: 'st-FAILED', CANCELLED: 'st-FAILED',
  };
  const stTag = (s, label) => `<span class="status ${ST[s] || 'st-PENDING'}">${esc(label || s)}</span>`;
  const ts2date = (ts) => ts ? new Date(ts * 1000).toISOString().slice(0, 10) : '';

  /* ---------------- 通用小表单弹窗 ---------------- */
  let fmSave = null;
  function openForm(title, bodyHtml, onSave, opts) {
    opts = opts || {};
    $('#fmTitle').textContent = title;
    $('#fmBody').innerHTML = bodyHtml;
    $('#fmCancel').style.display = opts.hideCancel ? 'none' : '';
    $('#fmSave').textContent = opts.saveText || '保存';
    $('#fmSave').style.display = opts.hideSave ? 'none' : '';
    $('#formMask').classList.add('show');
    fmSave = onSave;
  }
  function closeForm() { $('#formMask').classList.remove('show'); fmSave = null; }
  function fmField(label, id, value, type, ph) {
    return `<div class="field mt"><label>${esc(label)}</label>` +
      `<input type="${type || 'text'}" id="${id}" value="${esc(value == null ? '' : value)}" placeholder="${esc(ph || '')}"></div>`;
  }
  function fmSelect(label, id, options, value) {
    return `<div class="field mt"><label>${esc(label)}</label><select id="${id}">` +
      options.map(o => `<option value="${esc(o[0])}" ${String(o[0]) === String(value) ? 'selected' : ''}>${esc(o[1])}</option>`).join('') +
      '</select></div>';
  }
  function fmTextarea(label, id, value, rows, ph) {
    return `<div class="field mt"><label>${esc(label)}</label>` +
      `<textarea id="${id}" rows="${rows || 4}" placeholder="${esc(ph || '')}">${esc(value == null ? '' : value)}</textarea></div>`;
  }
  function showInfo(title, html) {
    openForm(title, html, closeForm, { hideCancel: true, saveText: '关闭' });
  }

  /* ---------------- 面板切换（左侧二级菜单） ---------------- */
  const PANELS = ['dashboard', 'projects', 'requests', 'suites', 'history', 'envs',
                  'reports', 'tasks', 'notifications', 'ai'];
  const PANEL_NAMES = {
    dashboard: '仪表盘', projects: '项目管理', requests: '接口管理', suites: '自动化测试',
    history: '请求历史', envs: '环境管理', reports: '测试报告', tasks: '定时任务',
    notifications: '通知列表', ai: 'AI 服务配置',
  };
  function switchTab(name) {
    if (PANELS.indexOf(name) < 0) name = 'dashboard';
    $$('#subnav a').forEach(a => a.classList.toggle('on', a.dataset.panel === name));
    PANELS.forEach(t => { const el = $('#panel-' + t); if (el) el.hidden = (t !== name); });
    if (window.setCrumbSub) setCrumbSub(PANEL_NAMES[name]);
    history.replaceState(null, '', '#' + name);
    const loaders = {
      dashboard: loadDashboard, projects: loadProjects, requests: reloadTreeData,
      suites: loadSuites, history: loadHistories, envs: renderEnvTable,
      reports: loadReports, tasks: loadTasks, notifications: loadNotifLogs, ai: loadAiConfigs,
    };
    (loaders[name] || (() => {}))().catch(e => toast(e.message, false));
  }

  /* ================= 仪表盘 ================= */
  const OP_ICO = { create: '➕', edit: '✏️', delete: '🗑', execute: '▶', run: '▶', save: '💾' };
  async function loadDashboard() {
    try {
      const [d, logs] = await Promise.all([api('/dashboard'), api('/operation-logs?page_size=12')]);
      const rate = d.data.success_rate == null ? '—' : d.data.success_rate + '%';
      $('#dashStats').innerHTML = [
        ['接口项目', d.data.projects, ''], ['API 接口', d.data.requests, 's-blue'],
        ['测试套件', d.data.suites, ''], ['执行请求次数', d.data.request_total, ''],
        ['请求成功率', rate, d.data.success_rate == null ? '' : (d.data.success_rate >= 90 ? 's-green' : 's-red')],
        ['激活定时任务', d.data.tasks_active, 's-slate'],
      ].map(([label, num, cls]) =>
        `<div class="stat ${cls}"><div class="num">${esc(num)}</div><div class="label">${esc(label)}</div>` +
        `<div class="bgico"></div></div>`).join('');
      $('#dashQuick').innerHTML = [
        ['projects', '📁', '项目管理'], ['requests', '🔌', '接口管理'], ['suites', '🎬', '自动化测试'],
        ['history', '🧾', '请求历史'], ['envs', '🌍', '环境管理'], ['reports', '📊', '测试报告'],
      ].map(([h, ico, name]) =>
        `<a class="nav-card" style="min-width:150px" href="#${h}" data-go="${h}">` +
        `<div style="font-size:26px">${ico}</div><h3>${name}</h3></a>`).join('');
      $$('#dashQuick [data-go]').forEach(a =>
        a.addEventListener('click', (e) => { e.preventDefault(); switchTab(a.dataset.go); }));
      $('#dashActivity').innerHTML = (logs.data.results || []).map(l =>
        `<tr><td>${OP_ICO[l.operation_type] || '•'} ${esc(l.operation_type)}</td>` +
        `<td>${esc(l.description || l.resource_name || '')}</td>` +
        `<td class="muted">${esc(l.resource_type || '')}</td>` +
        `<td class="muted">${fmtTime(l.created_at)}</td></tr>`).join('') ||
        '<tr><td colspan="4" class="empty">暂无活动</td></tr>';
    } catch (e) { /* 统计失败不打断 */ }
  }

  /* ================= 项目管理 ================= */
  const PROJ_STATUS = { NOT_STARTED: '未开始', IN_PROGRESS: '进行中', COMPLETED: '已结束' };
  async function loadUsers() {
    if (!state.users.length) state.users = (await api('/users')).data;
    return state.users;
  }
  async function loadProjects() {
    await loadUsers();
    const ftype = $('#projFilterType').value, fstatus = $('#projFilterStatus').value;
    const items = (await api('/projects')).data
      .filter(p => (!ftype || p.project_type === ftype) && (!fstatus || p.status === fstatus));
    $('#projTbody').innerHTML = items.map(p =>
      `<tr><td><b>${esc(p.name)}</b><div class="muted">${esc(p.description || '')}</div></td>` +
      `<td>${p.project_type === 'WEBSOCKET' ? 'WebSocket' : 'HTTP'}</td>` +
      `<td>${esc(PROJ_STATUS[p.status] || p.status)}</td>` +
      `<td>${esc(p.owner || '-')}</td>` +
      `<td class="muted">${esc((p.members || []).join('、') || '—')}</td>` +
      `<td class="muted">${esc(p.start_date || '-')}</td><td class="muted">${esc(p.end_date || '-')}</td>` +
      `<td><div class="ops">` +
      `<button class="ghost mini" data-view="${p.id}">查看</button>` +
      `<button class="ghost mini" data-edit="${p.id}">编辑</button>` +
      `<button class="mini danger-ghost" data-del="${p.id}">删除</button></div></td></tr>`).join('') ||
      '<tr><td colspan="8" class="empty">暂无项目 —— 「新建项目」或「一键示例项目」开始</td></tr>';
    $('#projTbody').querySelectorAll('[data-view]').forEach(b =>
      b.addEventListener('click', () => viewProject(+b.dataset.view)));
    $('#projTbody').querySelectorAll('[data-edit]').forEach(b =>
      b.addEventListener('click', () => openProjectForm(+b.dataset.edit)));
    $('#projTbody').querySelectorAll('[data-del]').forEach(b =>
      b.addEventListener('click', async () => {
        if (!(await confirmModal('删除项目', '将级联删除项目下的集合/接口/环境/套件/任务，确定？'))) return;
        await api('/projects/' + b.dataset.del, { method: 'DELETE' });
        loadProjects(); reloadTreeData(); toast('项目已删除', true);
      }));
  }
  function viewProject(pid) {
    const p = state.projectsAll && state.projectsAll.find(x => x.id === pid);
    if (!p) return;
    showInfo('项目：' + p.name,
      fmField('描述', 'vpD', p.description) +
      fmField('类型', 'vpT', p.project_type === 'WEBSOCKET' ? 'WebSocket' : 'HTTP') +
      fmField('状态', 'vpS', PROJ_STATUS[p.status] || p.status) +
      fmField('负责人', 'vpO', p.owner || '-') +
      fmField('成员', 'vpM', (p.members || []).join('、') || '—') +
      fmField('起止日期', 'vpD2', `${p.start_date || '-'} ~ ${p.end_date || '-'}`));
  }
  async function openProjectForm(pid) {
    await loadUsers();
    let p = null;
    if (pid) p = (await api('/projects/' + pid)).data;
    const userOpts = state.users.map(u => [u.id, u.username]);
    openForm(pid ? '编辑项目' : '新建项目',
      fmField('项目名称', 'pfName', p && p.name) +
      fmTextarea('项目描述', 'pfDesc', p && p.description, 2) +
      `<div class="field mt"><label>项目类型</label>` +
      `<label class="chk"><input type="radio" name="pfType" value="HTTP" ${(!p || p.project_type === 'HTTP') ? 'checked' : ''}> HTTP</label> ` +
      `<label class="chk"><input type="radio" name="pfType" value="WEBSOCKET" ${p && p.project_type === 'WEBSOCKET' ? 'checked' : ''}> WebSocket</label></div>` +
      fmSelect('项目状态', 'pfStatus', [['NOT_STARTED', '未开始'], ['IN_PROGRESS', '进行中'], ['COMPLETED', '已结束']], p && p.status) +
      fmSelect('负责人', 'pfOwner', userOpts, p && p.owner_id) +
      fmField('开始日期', 'pfStart', p && p.start_date, 'date') +
      fmField('结束日期', 'pfEnd', p && p.end_date, 'date') +
      `<div class="field mt"><label>团队成员（多选）</label>` +
      `<select id="pfMembers" multiple style="height:80px">` +
      userOpts.map(u => `<option value="${esc(u[0])}">${esc(u[1])}</option>`).join('') +
      `</select></div>`,
      async () => {
        const payload = {
          name: $('#pfName').value.trim(), description: $('#pfDesc').value.trim(),
          project_type: ($$('input[name="pfType"]').find(r => r.checked) || {}).value || 'HTTP',
          status: $('#pfStatus').value,
          owner: (state.users.find(u => u.id === +$('#pfOwner').value) || {}).username || 'platform',
          owner_id: +$('#pfOwner').value || null,
          start_date: $('#pfStart').value || null, end_date: $('#pfEnd').value || null,
          member_ids: Array.from($('#pfMembers').selectedOptions).map(o => +o.value),
        };
        if (!payload.name) return toast('项目名称不能为空', false);
        if (pid) await api('/projects/' + pid, { method: 'PUT', body: payload });
        else await api('/projects', { method: 'POST', body: payload });
        closeForm(); reloadTreeData(); loadProjects(); loadDashboard();
        toast('项目已保存', true);
      });
  }

  /* ================= 接口管理：数据与树 ================= */
  async function reloadTreeData() {
    const [p, c, r, e] = await Promise.all([
      api('/projects'), api('/collections'), api('/requests'), api('/environments')]);
    state.projects = p.data; state.projectsAll = p.data;
    state.collections = c.data; state.requests = r.data; state.envs = e.data;
    if (!state.selProject || !state.projects.find(x => x.id === state.selProject)) {
      state.selProject = state.projects.length ? state.projects[0].id : null;
    }
    renderProjectSelect(); renderTree(); renderSuiteSelectors(); renderEnvSelect(); renderEnvTable();
  }
  function renderProjectSelect() {
    $('#reqProjectSel').innerHTML = state.projects.map(p =>
      `<option value="${p.id}" ${p.id === state.selProject ? 'selected' : ''}>${esc(p.name)}（${p.project_type === 'WEBSOCKET' ? 'WebSocket' : 'HTTP'}）</option>`).join('') ||
      '<option value="">— 无项目 —</option>';
  }

  /* 搜索：走后端 /collections/search（testhub 同款，防抖 300ms） */
  let searchTimer = null;
  function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      const kw = ($('#apiSearch').value || '').trim();
      if (!kw) { renderTree(); return; }
      try {
        const hits = (await api('/collections/search?project=' + (state.selProject || '') +
                                 '&keyword=' + encodeURIComponent(kw))).data;
        $('#apiTree').innerHTML = hits.length ? hits.map(h => h.type === 'request'
          ? reqRow(Object.assign({ id: h.id, method: h.method, name: h.name, url: h.url }, { collection_id: h.collection_id }), h.match_type)
          : `<div class="t-coll">📁 ${esc(h.name)}<span class="mockbadge">集合·${esc(h.match_type)}</span></div>`).join('')
          : '<div class="empty">无匹配结果</div>';
        $('#apiTree').querySelectorAll('.t-req').forEach(el =>
          el.addEventListener('click', () => selectRequest(+el.dataset.id)));
      } catch (e) { toast(e.message, false); }
    }, 300);
  }

  function renderTree() {
    const kw = ($('#apiSearch').value || '').trim().toLowerCase();
    const box = $('#apiTree');
    if (!state.projects.length) { box.innerHTML = '<div class="empty">还没有项目 —— 到「项目管理」新建</div>'; return; }
    box.innerHTML = state.projects.filter(p => p.id === state.selProject).map(proj => {
      const rootCols = state.collections.filter(c => c.project_id === proj.id && !c.parent_id);
      const renderCol = (col, depth) => {
        const childCols = state.collections.filter(c => c.parent_id === col.id);
        const reqs = state.requests.filter(r =>
          r.collection_id === col.id &&
          (!kw || (r.name + r.url + r.method).toLowerCase().includes(kw)));
        if (kw && !reqs.length && !childCols.length) return '';
        return `<div class="t-coll" data-cid="${col.id}" title="双击重命名 / 右键更多操作" style="padding-left:${depth * 14}px">📁 ${esc(col.name)}` +
          `<span class="t-ops" data-cops="${col.id}">✎</span></div>` +
          childCols.map(cc => renderCol(cc, depth + 1)).join('') +
          reqs.map(r => reqRow(r, null, depth + 1)).join('');
      };
      const loose = state.requests.filter(r =>
        r.project_id === proj.id && !r.collection_id &&
        (!kw || (r.name + r.url + r.method).toLowerCase().includes(kw)));
      return `<div class="t-proj"><b>${esc(proj.name)}</b><span class="mockbadge">项目</span></div>` +
        rootCols.map(c => renderCol(c, 0)).join('') + loose.map(r => reqRow(r, null, 0)).join('');
    }).join('');
    box.querySelectorAll('.t-req').forEach(el => {
      el.addEventListener('click', () => selectRequest(+el.dataset.id));
      el.addEventListener('contextmenu', (ev) => { ev.preventDefault(); requestOps(+el.dataset.id); });
    });
    box.querySelectorAll('[data-cops]').forEach(el => {
      el.addEventListener('click', (ev) => { ev.stopPropagation(); collectionOps(+el.dataset.cops); });
    });
    box.querySelectorAll('.t-coll').forEach(el => {
      el.addEventListener('dblclick', () => renameCollection(+el.dataset.cid));
    });
  }
  const reqRow = (r, match, depth) =>
    `<div class="t-req ${r.id === state.selReqId ? 'sel' : ''}" data-id="${r.id}" style="padding-left:${(depth || 0) * 14 + 8}px">` +
    (r.request_type === 'WEBSOCKET' ? '<span class="m-badge" style="background:rgba(89,44,171,.12);color:#8944ab">WS</span>' : mBadge(r.method)) +
    `<span class="t-name" title="${esc(r.url)}">${esc(r.name)}</span>` +
    (match ? `<span class="mockbadge">${esc(match)}</span>` : '') + '</div>';

  function currentReq() { return state.requests.find(r => r.id === state.selReqId); }

  async function collectionOps(cid) {
    const col = state.collections.find(c => c.id === cid);
    if (!col) return;
    openForm('集合操作：' + col.name,
      `<div class="mops" style="justify-content:flex-start;gap:10px">` +
      `<button class="ghost" id="coRename">重命名</button>` +
      `<button class="ghost" id="coAddReq">添加接口</button>` +
      `<button class="ghost" id="coAddSub">添加子集合</button>` +
      `<button class="danger-ghost" id="coDel">删除集合</button></div>`, closeForm, { hideSave: true });
    $('#coRename').addEventListener('click', () => { closeForm(); renameCollection(cid); });
    $('#coAddReq').addEventListener('click', () => { closeForm(); openEditor(null, cid); });
    $('#coAddSub').addEventListener('click', () => { closeForm(); openCollectionForm(cid); });
    $('#coDel').addEventListener('click', async () => {
      closeForm();
      if (!(await confirmModal('删除集合', '集合内接口将挪出集合（不删除），确定？'))) return;
      await api('/collections/' + cid, { method: 'DELETE' });
      reloadTreeData(); toast('集合已删除', true);
    });
  }
  function renameCollection(cid) {
    const col = state.collections.find(c => c.id === cid);
    if (!col) return;
    openForm('重命名集合', fmField('集合名称', 'cnName', col.name), async () => {
      await api('/collections/' + cid, { method: 'PUT', body: { name: $('#cnName').value.trim() } });
      closeForm(); reloadTreeData();
    });
  }
  function openCollectionForm(parentId) {
    if (!state.projects.length) return toast('请先在「项目管理」创建项目', false);
    openForm('新建集合',
      fmField('集合名称', 'cfName', '') +
      fmTextarea('描述', 'cfDesc', '', 2) +
      fmSelect('父级集合', 'cfParent', [['', '— 无（顶级集合）—']]
        .concat(state.collections.filter(c => c.project_id === state.selProject).map(c => [c.id, c.name])), parentId || ''),
      async () => {
        const name = $('#cfName').value.trim();
        if (!name) return toast('集合名称不能为空', false);
        await api('/collections', { method: 'POST', body: {
          name, description: $('#cfDesc').value.trim(), project_id: state.selProject,
          parent_id: +$('#cfParent').value || null } });
        closeForm(); reloadTreeData(); toast('集合已创建', true);
      });
  }

  /* ---------------- 请求编辑器：KV 行 ---------------- */
  const kvRow = (k, v, en, desc) =>
    `<div class="kvrow"><input type="checkbox" class="en" title="启用" ${en === false ? '' : 'checked'}>` +
    `<input type="text" class="k" placeholder="Key" value="${esc(k)}">` +
    `<input type="text" class="v" placeholder="Value（支持 {{var}} 与 \${fn()}）" value="${esc(v)}">` +
    `<input type="text" class="d" placeholder="描述（仅备注）" value="${esc(desc == null ? '' : desc)}">` +
    `<button type="button" class="kv-del" title="删除">×</button></div>`;

  function readKv(container) {
    const out = [];
    container.querySelectorAll('.kvrow').forEach(row => {
      const k = row.querySelector('.k').value.trim();
      if (k) out.push({ key: k, value: row.querySelector('.v').value,
                        description: row.querySelector('.d').value.trim(),
                        enabled: row.querySelector('.en').checked });
    });
    return out;
  }

  const ASSERT_TYPES = [
    ['status_code', '状态码 ='], ['contains', '包含文本'], ['json_path', 'JSONPath'],
    ['header', '响应头'], ['equals', '正文等于'], ['response_time', '响应时间≤ms'],
    ['media_check', '音视频检测（格式/时长/有无声音/分辨率）'],
  ];
  const MEDIA_TYPES = ['media_check', 'media_video', 'media_audio', 'media_volume', 'media_stream'];
  const assertRow = (a) => {
    a = a || {};
    if (MEDIA_TYPES.indexOf(a.type) >= 0) {
      const isVideo = a.type === 'media_video' || a.type === 'media_stream'
        ? ((a.media_type || '') !== 'audio')
        : (a.type === 'media_check' && (a.media_type || '') === 'video');
      const rng = (mn, mx) => (mn != null || mx != null)
        ? [mn == null ? '' : mn, mx == null ? '' : mx].join('-') : '';
      const dur = rng(a.duration_min, a.duration_max);
      const sound = a.type === 'media_volume' ? (a.expected == null ? '-40' : a.expected)
        : (a.sound_threshold == null ? '' : a.sound_threshold);
      return `<div class="assertrow assertrow-media" data-type="media_check">` +
        `<select class="a-type">${ASSERT_TYPES.map(x =>
          `<option value="${x[0]}" ${x[0] === 'media_check' ? 'selected' : ''}>${x[1]}</option>`).join('')}</select>` +
        `<select class="a-media" title="检测音频还是视频">${[['audio', '音频'], ['video', '视频']].map(x =>
          `<option value="${x[0]}" ${x[0] === (isVideo ? 'video' : 'audio') ? 'selected' : ''}>${x[1]}</option>`).join('')}</select>` +
        `<input type="text" class="a-expected" placeholder="格式，如 h264 / aac（可空）" value="${esc(a.codec || '')}">` +
        `<input type="text" class="a-extra1" placeholder="时长范围 秒，如 0.5-30（可空）" value="${esc(dur)}">` +
        `<input type="text" class="a-res" placeholder="分辨率，如 1280x720（仅视频）" value="${esc(a.resolution || '')}" ${isVideo ? '' : 'disabled'}>` +
        `<input type="text" class="a-sound" placeholder="有无声音：静音阈值 dB，如 -40（可空=不检测）" value="${esc(sound)}">` +
        `<input type="text" class="a-br" placeholder="码率 kbps，如 200-2000（可空）" value="${esc(rng(a.bitrate_min, a.bitrate_max))}">` +
        `<span class="a-hint">留空 = 不检查</span>` +
        `<button type="button" class="kv-del" title="删除">×</button></div>`;
    }
    return `<div class="assertrow" data-type="${a.type || 'status_code'}">` +
      `<input type="text" class="a-name" placeholder="断言名（可空）" value="${esc(a.name || '')}" style="max-width:130px">` +
      `<select class="a-type">${ASSERT_TYPES.map(t =>
        `<option value="${t[0]}" ${a.type === t[0] ? 'selected' : ''}>${t[1]}</option>`).join('')}</select>` +
      `<input type="text" class="a-extra1" placeholder="JSONPath / 头名（按类型）" value="${esc(a.type === 'header' ? (a.header_name || '') : (a.json_path || ''))}">` +
      `<input type="text" class="a-expected" placeholder="期望值" value="${esc(a.expected == null ? '' : a.expected)}">` +
      `<button type="button" class="kv-del" title="删除">×</button></div>`;
  };
  function readRow(row) {
    const type = row.dataset.type || row.querySelector('.a-type').value;
    const name = (row.querySelector('.a-name') || {}).value || '';
    if (MEDIA_TYPES.indexOf(type) >= 0) {
      const mediaType = row.querySelector('.a-media').value;
      const a = { name: name || 'media_check', type: 'media_check', media_type: mediaType };
      const codec = row.querySelector('.a-expected').value.trim();
      if (codec) a.codec = codec;
      const dur = row.querySelector('.a-extra1').value.trim();
      if (dur) {
        const [mn, mx] = dur.split('-');
        if (mn) a.duration_min = mn;
        if (mx) a.duration_max = mx;
      }
      if (mediaType === 'video') {
        const res = row.querySelector('.a-res').value.trim();
        if (res) a.resolution = res;
      }
      const sound = row.querySelector('.a-sound').value.trim();
      if (sound) a.sound_threshold = sound;
      const br = row.querySelector('.a-br').value.trim();
      if (br) {
        const [lo, hi] = br.split('-');
        if (lo) a.bitrate_min = lo;
        if (hi) a.bitrate_max = hi;
      }
      return a;
    }
    const extra = row.querySelector('.a-extra1').value.trim();
    const expected = row.querySelector('.a-expected').value;
    const a = { name: name || type, type, expected: expected };
    if (type === 'json_path') a.json_path = extra;
    if (type === 'header') { a.header_name = extra; a.expected_value = expected; }
    return a;
  }
  function readAssertions() {
    return Array.from($('#reqAssertions').querySelectorAll('.assertrow')).map(readRow);
  }

  /* ---------------- 请求编辑器：Tab / 打开 / 保存 / 发送 ---------------- */
  function switchRtab(name) {
    $$('.reqtabs a[data-rtab]').forEach(a =>
      a.classList.toggle('on', a.dataset.rtab === name));
    ['params', 'headers', 'body', 'asserts', 'wsmsg', 'history'].forEach(t => {
      const el = $('#rtab-' + t); if (el) el.hidden = (t !== name);
    });
    if (name === 'history' && state.selReqId) loadHistory().catch(() => {});
  }
  function syncTypeTabs() {
    const isWs = $('#reqType').value === 'WEBSOCKET';
    $('#rtabBodyLink').style.display = isWs ? 'none' : '';
    $('#rtabWsLink').style.display = isWs ? '' : 'none';
    $('#btnWsConnect').style.display = isWs ? '' : 'none';
    $('#btnWsDisconnect').style.display = isWs ? '' : 'none';
    $('#btnReqSend').textContent = isWs ? '发送(HTTP不可用)' : '发送';
    if (isWs) switchRtab('wsmsg'); else if ($('#rtab-wsmsg').hidden === false) switchRtab('params');
  }

  function renderEnvSelect() {
    const opts = [['', '无环境（全局激活）']].concat(
      state.envs.filter(e => e.scope === 'GLOBAL' || e.project_id === state.selProject)
        .map(e => [e.id, e.name + (e.is_active ? '（激活）' : '')]));
    $('#reqEnvSel').innerHTML = opts.map(o =>
      `<option value="${esc(o[0])}">${esc(o[1])}</option>`).join('');
  }
  function fillCollectionSelect(req) {
    /* 集合选择并入树操作；这里仅展示归属（不可编辑），拖拽/右键改归属 */
    return;
  }

  function openEditor(req, collectionId) {
    $('#reqWelcome').style.display = 'none';
    $('#reqEditor').style.display = '';
    $('#respArea').style.display = 'none';
    $('#reqName').value = req ? req.name : '';
    $('#reqUrl').value = req ? req.url : '';
    $('#reqType').value = (req && req.request_type) || 'HTTP';
    $('#reqMethod').innerHTML = Object.keys(METHOD_COLOR).map(m =>
      `<option ${req && req.method === m ? 'selected' : ''}>${m}</option>`).join('');
    const hs = (req ? req.headers : []) || [];
    $('#reqHeaders').innerHTML = (hs.length ? hs : [{ key: '', value: '', enabled: true }])
      .map(h => kvRow(h.key, h.value, h.enabled, h.description)).join('');
    const rawPs = (req ? req.params : null) || [];
    const ps = Array.isArray(rawPs)
      ? rawPs.map(p => [p.key, p.value, p.enabled, p.description])
      : Object.entries(rawPs).map(([k, v]) => [k, v, true, '']);
    $('#reqParams').innerHTML = (ps.length ? ps : [['', '', true, '']])
      .map(([k, v, en, d]) => kvRow(k, v, en, d)).join('');
    const as = (req ? req.assertions : []) || [];
    $('#reqAssertions').innerHTML = as.map(assertRow).join('') || assertRow({ type: 'status_code', expected: '200' });
    const bt = (req && req.body && req.body.type) || 'none';
    $('#reqBodyType').value = bt;
    $('#reqBody').value = bt === 'none' ? '' :
      (typeof (req.body || {}).data === 'string' ? (req.body || {}).data : JSON.stringify((req.body || {}).data || '', null, 2));
    state._newCollectionId = collectionId || (req && req.collection_id) || null;
    syncTypeTabs();
    switchRtab('params');
    if (req) loadHistory().catch(() => {});
    else $('#histTbody').innerHTML = '<tr><td colspan="5" class="empty">保存并发送后生成历史</td></tr>';
  }

  function collectRequest() {
    const bodyType = $('#reqBodyType').value;
    let bodyData = null;
    if (bodyType !== 'none') {
      const raw = $('#reqBody').value;
      if (bodyType === 'json') { try { bodyData = JSON.parse(raw || '{}'); } catch (e) { throw new Error('请求体 JSON 不合法: ' + e.message); } }
      else bodyData = raw;
    }
    const params = readKv($('#reqParams')).map(p =>
      ({ key: p.key, value: p.value, description: p.description, enabled: p.enabled }));
    const proj = state.projects.find(p => p.id === state.selProject);
    return {
      name: $('#reqName').value.trim() || '未命名接口',
      request_type: $('#reqType').value,
      method: $('#reqMethod').value, url: $('#reqUrl').value.trim(),
      headers: readKv($('#reqHeaders')), params,
      body: { type: bodyType, data: bodyData },
      assertions: readAssertions(),
      collection_id: state._newCollectionId,
      project_id: (proj ? proj.id : null) || (currentReq() && currentReq().project_id) || null,
    };
  }

  async function saveRequest() {
    const req = currentReq();
    const payload = collectRequest();
    if (!payload.project_id) return toast('请先创建并选择项目', false);
    if (req) {
      await api('/requests/' + req.id, { method: 'PUT', body: payload });
      Object.assign(req, payload);
    } else {
      const d = (await api('/requests', { method: 'POST', body: payload })).data;
      state.requests.push(d); state.selReqId = d.id;
    }
    toast('已保存', true); renderTree(); loadDashboard();
  }

  async function sendRequest() {
    const req = currentReq();
    const envId = +$('#reqEnvSel').value || null;
    const activeEnv = envId ? state.envs.find(e => e.id === envId)
      : state.envs.find(e => e.is_active);
    $('#respArea').style.display = '';
    $('#respBody').textContent = '发送中…';
    try {
      const overrides = collectRequest();
      const hist = (await api('/requests/' + (req ? req.id : 0) + '/execute',
        { method: 'POST', body: { environment_id: activeEnv ? activeEnv.id : null, ...overrides } })).data;
      renderResponse(hist);
      loadHistory().catch(() => {});
    } catch (e) { $('#respBody').textContent = '执行失败: ' + e.message; }
  }

  function renderResponse(h) {
    $('#respStatus').textContent = h.status_code != null ? h.status_code : '错误';
    $('#respStatus').style.color = h.status_code && h.status_code < 400 ? 'var(--ok-text)' : 'var(--bad-text)';
    $('#respTime').textContent = h.response_time != null ? h.response_time + 'ms' : '-';
    const results = h.assertions_results || [];
    const passCount = results.filter(a => a.passed).length;
    $('#respAssertSummary').innerHTML = results.length ?
      `<b style="color:${passCount === results.length ? 'var(--ok-text)' : 'var(--bad-text)'}">断言 ${passCount}/${results.length} 通过</b>` : '';
    let body = h.error_message || (h.response_data || {}).body || '(空)';
    try { body = JSON.stringify(JSON.parse(body), null, 2); } catch (e) { /* 非 JSON 原样显示 */ }
    $('#respBody').textContent = body;
    $('#respAssertions').innerHTML = results.map(a =>
      `<div class="pill ${a.passed ? 'ok' : 'bad'}" style="margin:0 8px 8px 0">${a.passed ? '✓' : '✗'} ${esc(a.name || a.type)} ` +
      `期望 ${esc(a.expected)} / 实际 ${esc(a.actual == null ? (a.error || '-') : a.actual)}</div>`).join('');
  }

  async function loadHistory() {
    const req = currentReq();
    if (!req) { $('#histTbody').innerHTML = '<tr><td colspan="5" class="empty">新接口尚未保存</td></tr>'; return; }
    const d = (await api('/requests/' + req.id + '/histories?page_size=20')).data;
    $('#histTbody').innerHTML = d.results.map(h => {
      const rs = h.assertions_results || [];
      const ok = rs.filter(a => a.passed).length;
      return `<tr><td class="muted">${fmtTime(h.executed_at)}</td>` +
        `<td>${h.status_code != null ? h.status_code : '<span class="num-bad">ERR</span>'}</td>` +
        `<td>${h.response_time != null ? h.response_time : '-'}</td>` +
        `<td>${rs.length ? ok + '/' + rs.length : '-'}</td>` +
        `<td class="muted" style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(h.error_message || '')}</td></tr>`;
    }).join('') || '<tr><td colspan="5" class="empty">暂无历史 —— 发送一次即生成</td></tr>';
  }

  async function selectRequest(id) {
    state.selReqId = id;
    const req = currentReq();
    if (req && req.project_id) { state.selProject = req.project_id; renderProjectSelect(); }
    renderTree();
    openEditor(req);
  }

  async function requestOps(rid) {
    const r = state.requests.find(x => x.id === rid);
    if (!r) return;
    openForm('接口操作：' + r.name,
      `<div class="mops" style="justify-content:flex-start;gap:10px">` +
      `<button class="ghost" id="roCopy">复制接口</button>` +
      `<button class="ghost" id="roMove">移动到集合</button>` +
      `<button class="danger-ghost" id="roDel">删除接口</button></div>`, closeForm, { hideSave: true });
    $('#roCopy').addEventListener('click', async () => {
      closeForm();
      await api('/requests/' + rid + '/copy', { method: 'POST' });
      reloadTreeData(); toast('已复制', true);
    });
    $('#roMove').addEventListener('click', () => {
      closeForm();
      openForm('移动到集合',
        fmSelect('目标集合', 'roCol', [['', '— 无集合 —']]
          .concat(state.collections.filter(c => c.project_id === r.project_id).map(c => [c.id, c.name])), r.collection_id),
        async () => {
          await api('/requests/' + rid, { method: 'PUT', body: { collection_id: +$('#roCol').value || null } });
          closeForm(); reloadTreeData(); toast('已移动', true);
        });
    });
    $('#roDel').addEventListener('click', async () => {
      closeForm();
      if (!(await confirmModal('删除接口', '接口及其历史将删除，并从套件移除，确定？'))) return;
      await api('/requests/' + rid, { method: 'DELETE' });
      if (state.selReqId === rid) { state.selReqId = null; $('#reqEditor').style.display = 'none'; $('#reqWelcome').style.display = ''; }
      reloadTreeData(); toast('已删除', true);
    });
  }

  /* ================= WebSocket 调试（testhub 同款：浏览器原生直连） ================= */
  function wsUrl(u) { return String(u || '').replace(/^http/, 'ws'); }
  function wsLogAdd(kind, text) {
    state.wsLogLines.push('[' + kind + '] ' + text);
    if (state.wsLogLines.length > 200) state.wsLogLines = state.wsLogLines.slice(-200);
    $('#wsLog').textContent = state.wsLogLines.join('\n') || '未连接';
    $('#wsLog').scrollTop = $('#wsLog').scrollHeight;
  }
  function wsConnect() {
    if (state.ws) { toast('已连接，先断开', false); return; }
    const url = wsUrl($('#reqUrl').value.trim());
    if (!/^wss?:\/\//.test(url)) return toast('URL 需以 ws:// 或 wss:// 开头（由 http(s) 转换）', false);
    try {
      const sock = new WebSocket(url);
      state.ws = sock;
      wsLogAdd('info', '连接中: ' + url);
      sock.onopen = () => { wsLogAdd('connected', '已连接 ' + url); toast('WebSocket 已连接', true); };
      sock.onmessage = (ev) => {
        let body = ev.data;
        try { body = JSON.stringify(JSON.parse(ev.data), null, 2); } catch (e) { /* 原样 */ }
        wsLogAdd('received', body);
      };
      sock.onerror = (ev) => wsLogAdd('error', '连接错误');
      sock.onclose = (ev) => { wsLogAdd('info', '已关闭（code=' + ev.code + '）'); state.ws = null; };
    } catch (e) { toast('连接失败: ' + e.message, false); state.ws = null; }
  }
  function wsDisconnect() {
    if (state.ws) { state.ws.close(); state.ws = null; }
    else toast('未连接', false);
  }
  function wsSend() {
    if (!state.ws) return toast('请先点「连接」', false);
    const type = $('#wsMsgType').value;
    let text = $('#wsMsgText').value;
    if (type === 'json') {
      try { text = JSON.stringify(JSON.parse(text)); }
      catch (e) { return toast('消息 JSON 不合法: ' + e.message, false); }
    }
    state.ws.send(text);
    wsLogAdd('sent', text);
  }

  /* ================= 变量助手 / 数据工厂（testhub 变量助手） ================= */
  async function openVarHelper() {
    if (!state.varCatalog) {
      state.varCatalog = (await api('/data-factory/functions')).data;
    }
    const cats = Object.keys(state.varCatalog);
    $('#varCats').innerHTML = ['全部'].concat(cats).map((c, i) =>
      `<a data-varcat="${esc(c)}" class="${i === 0 ? 'on' : ''}">${esc(c)}</a>`).join('');
    const renderList = (cat, kw) => {
      let items = [];
      cats.forEach(c => {
        if (cat && cat !== '全部' && c !== cat) return;
        state.varCatalog[c].forEach(f => {
          if (kw && !(f.name + f.desc).toLowerCase().includes(kw)) return;
          items.push(Object.assign({ cat: c }, f));
        });
      });
      $('#varList').innerHTML = items.map(f =>
        `<div class="kvrow" data-var="${esc(f.name)}" data-args="${esc(f.args)}" style="cursor:pointer" title="点击插入">` +
        `<b style="min-width:210px">\${${esc(f.name)}()}</b>` +
        `<span class="muted" style="flex:1">${esc((f.desc || '').slice(0, 60))}</span>` +
        `<span class="muted" style="font-size:11px">${esc(f.cat)}</span></div>`).join('') ||
        '<div class="empty">无匹配函数</div>';
      $('#varList').querySelectorAll('[data-var]').forEach(row =>
        row.addEventListener('click', () => insertVar(row.dataset.var)));
    };
    renderList('全部', '');
    $('#varSearch').value = '';
    $('#varSearch').oninput = () => {
      const on = $('#varCats a.on');
      renderList(on ? on.dataset.varcat : '全部', ($('#varSearch').value || '').trim().toLowerCase());
    };
    $('#varCats').querySelectorAll('a').forEach(a =>
      a.addEventListener('click', () => {
        $$('#varCats a').forEach(x => x.classList.toggle('on', x === a));
        renderList(a.dataset.varcat, ($('#varSearch').value || '').trim().toLowerCase());
      }));
    $('#varMask').classList.add('show');
  }
  function insertVar(name) {
    const t = state.lastVarTarget;
    const snippet = '${' + name + '()}';
    if (t && document.body.contains(t)) {
      const s = t.selectionStart == null ? t.value.length : t.selectionStart;
      const e = t.selectionEnd == null ? t.value.length : t.selectionEnd;
      t.value = t.value.slice(0, s) + snippet + t.value.slice(e);
      t.dispatchEvent(new Event('input', { bubbles: true }));
      t.focus();
      toast('已插入 ' + snippet + '（记得填参数）', true);
    } else {
      toast('请先点击要插入的输入框，再选择函数', false);
    }
    $('#varMask').classList.remove('show');
  }

  /* ================= 生成代码（16 种语言原生生成；testhub 为 curlconverter 29 种，内网不可引入 npm 库，取常用语言原生实现） ================= */
  function buildCurlText(r) {
    const q = (s) => "'" + String(s == null ? '' : s).replace(/'/g, `'\\''`) + "'";
    const enabledParams = (r.params || []).filter(p => p.enabled !== false && p.key);
    const url = enabledParams.length
      ? r.url + (r.url.includes('?') ? '&' : '?') + enabledParams.map(p =>
          encodeURIComponent(p.key) + '=' + encodeURIComponent(p.value)).join('&')
      : r.url;
    const hs = (r.headers || []).filter(h => h.enabled !== false && h.key);
    let curl = `curl -X ${r.method} ${q(url)}`;
    hs.forEach(h => { curl += ` \\\n  -H ${q(h.key + ': ' + h.value)}`; });
    if (r.body.type !== 'none' && r.body.data != null && r.body.data !== '') {
      curl += ` \\\n  -d ${q(typeof r.body.data === 'string' ? r.body.data : JSON.stringify(r.body.data))}`;
    }
    return { q, url, hs, curl };
  }
  function genCode() {
    let r;
    try { r = collectRequest(); } catch (e) { return toast(e.message, false); }
    if (r.request_type === 'WEBSOCKET') return toast('WebSocket 接口不支持代码生成', false);
    const { url, hs, curl } = buildCurlText(r);
    const bodyStr = (r.body.type !== 'none' && r.body.data != null && r.body.data !== '')
      ? (typeof r.body.data === 'string' ? r.body.data : JSON.stringify(r.body.data)) : '';
    const isJson = r.body.type === 'json';
    const LANGS = {
      'cURL': () => curl,
      'HTTP(原文)': () => {
        let s = `${r.method} ${url} HTTP/1.1\nHost: ${(url.match(/^https?:\/\/([^\/]+)/) || [])[1] || 'localhost'}\n`;
        hs.forEach(h => { s += `${h.key}: ${h.value}\n`; });
        if (bodyStr) s += `Content-Type: ${isJson ? 'application/json' : 'text/plain'}\n\n${bodyStr}`;
        return s;
      },
      'Python(requests)': () => {
        const H = hs.length ? `headers = {\n` + hs.map(h => `    '${h.key}': '${h.value}',`).join('\n') + `\n}\n` : 'headers = {}\n';
        const B = bodyStr ? (isJson ? `json_payload = ${JSON.stringify(r.body.data, null, 4)}\n` : `data = '''${bodyStr}'''\n`) : '';
        const args = `headers=headers` + (bodyStr ? (isJson ? ', json=json_payload' : `, data=data`) : '');
        return `import requests\n\nurl = '${url}'\n${H}${B}\nresp = requests.request('${r.method}', url, ${args})\nprint(resp.status_code, resp.text)\n`;
      },
      'JavaScript(fetch)': () => {
        const H = hs.length ? `  headers: {\n` + hs.map(h => `    '${h.key}': '${h.value}',`).join('\n') + `\n  },\n` : '';
        const B = bodyStr ? `  method: '${r.method}',\n${H}  body: ${isJson ? `JSON.stringify(${JSON.stringify(r.body.data)})` : `'${bodyStr.replace(/'/g, "\\'")}'`},\n` : `  method: '${r.method}',\n${H}`;
        return `fetch('${url}',\n${B})\n  .then(res => res.text())\n  .then(t => console.log(t));\n`;
      },
      'Node.js(axios)': () => {
        const H = hs.length ? `  headers: { ${hs.map(h => `'${h.key}': '${h.value}'`).join(', ')} },\n` : '';
        const B = bodyStr ? `  method: '${r.method.toLowerCase()}',\n${H}  ${isJson ? 'data: ' + JSON.stringify(r.body.data) : 'data: ' + JSON.stringify(bodyStr)},\n` : `  method: '${r.method.toLowerCase()}',\n${H}`;
        return `const axios = require('axios');\n\naxios({\n  url: '${url}',\n${B}})\n  .then(res => console.log(res.status, res.data))\n  .catch(e => console.error(e));\n`;
      },
      'Java(HttpURLConnection)': () => {
        const H = hs.map(h => `            conn.setRequestProperty("${h.key}", "${h.value}");`).join('\n');
        return `import java.io.*;\nimport java.net.*;\n\npublic class Main {\n    public static void main(String[] args) throws Exception {\n        URL url = new URL("${url}");\n        HttpURLConnection conn = (HttpURLConnection) url.openConnection();\n        conn.setRequestMethod("${r.method}");\n${H}\n        conn.setDoOutput(true);\n${bodyStr ? `        try (OutputStream os = conn.getOutputStream()) {\n            os.write(("${bodyStr.replace(/"/g, '\\"').replace(/\n/g, '\\n')}").getBytes());\n        }\n` : ''}        try (BufferedReader in = new BufferedReader(new InputStreamReader(conn.getInputStream()))) {\n            String line;\n            while ((line = in.readLine()) != null) System.out.println(line);\n        }\n    }\n}\n`;
      },
      'Go(net/http)': () => {
        const H = hs.map(h => `    req.Header.Set("${h.key}", "${h.value}")`).join('\n');
        return `package main\n\nimport (\n\t"fmt"\n\t"io"\n\t"net/http"\n\t"strings"\n)\n\nfunc main() {\n${bodyStr ? `\tbody := strings.NewReader(\`${bodyStr.replace(/`/g, '\\`')}\`)\n\treq, _ := http.NewRequest("${r.method}", "${url}", body)\n` : `\treq, _ := http.NewRequest("${r.method}", "${url}", nil)\n`}${H}\n\tresp, err := http.DefaultClient.Do(req)\n\tif err != nil { panic(err) }\n\tdefer resp.Body.Close()\n\tb, _ := io.ReadAll(resp.Body)\n\tfmt.Println(resp.StatusCode, string(b))\n}\n`;
      },
      'PHP(curl)': () => {
        const H = hs.map(h => `curl_setopt($ch, CURLOPT_HTTPHEADER, array_merge(curl_getinfo($ch) ? [] : [], ['${h.key}: ${h.value}']));`).join('\n');
        return `<?php\n$ch = curl_init();\ncurl_setopt($ch, CURLOPT_URL, '${url}');\ncurl_setopt($ch, CURLOPT_CUSTOMREQUEST, '${r.method}');\ncurl_setopt($ch, CURLOPT_RETURNTRANSFER, true);\n${hs.map(h => `curl_setopt($ch, CURLOPT_HTTPHEADER, ['${h.key}: ${h.value}']);`).join('\n')}\n${bodyStr ? `curl_setopt($ch, CURLOPT_POSTFIELDS, '${bodyStr.replace(/'/g, "\\'")}');\n` : ''}$resp = curl_exec($ch);\necho $resp;\ncurl_close($ch);\n`;
      },
      'C#(HttpClient)': () => {
        const H = hs.map(h => `    client.DefaultRequestHeaders.Add("${h.key}", "${h.value}");`).join('\n');
        return `using System;\nusing System.Net.Http;\nusing System.Text;\n\nclass Program {\n    static void Main() {\n        using var client = new HttpClient();\n${H}\n        var content = ${bodyStr ? `new StringContent(@"${bodyStr.replace(/"/g, '""')}", Encoding.UTF8, "${isJson ? 'application/json' : 'text/plain'}");` : 'null;'}\n        var resp = ${bodyStr ? `client.${cap(r.method)}Async("${url}", content).Result;` : `client.${cap(r.method)}Async("${url}").Result;`}\n        Console.WriteLine((int)resp.StatusCode);\n        Console.WriteLine(resp.Content.ReadAsStringAsync().Result);\n    }\n}\n`;
      },
      'Ruby(net/http)': () => {
        const H = hs.map(h => `  req["${h.key}"] = "${h.value}"`).join('\n');
        return `require 'net/http'\nrequire 'uri'\n\nuri = URI('${url}')\nreq = Net::HTTP::${cap(r.method)}.new(uri)\n${H}\n${bodyStr ? `req.body = <<~BODY\n${bodyStr}\nBODY\n` : ''}res = Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == 'https') { |http| http.request(req) }\nputs res.code, res.body\n`;
      },
      'PowerShell': () => {
        const H = hs.length ? `@{\n` + hs.map(h => `    '${h.key}' = '${h.value}'`).join('\n') + `\n}` : '@{}';
        const B = bodyStr ? ` -Body @'\n${bodyStr}\n'@` : '';
        return `Invoke-WebRequest -Uri '${url}' -Method ${r.method} -Headers ${H}${B}\n`;
      },
      'HTTPie': () => {
        const H = hs.map(h => ` \\\n  '${h.key}:${h.value}'`).join('');
        const B = bodyStr ? ` \\\n  --raw '${bodyStr.replace(/'/g, "'\\''")}'` : '';
        return `http ${r.method} '${url}'${H}${B}\n`;
      },
      'Wget': () => {
        const H = hs.map(h => ` \\\n  --header='${h.key}: ${h.value}'`).join('');
        const B = bodyStr ? ` \\\n  --body-data='${bodyStr.replace(/'/g, "'\\''")}'` : '';
        return `wget -O- --method=${r.method} '${url}'${H}${B}\n`;
      },
      'Swift(URLSession)': () => {
        const H = hs.map(h => `request.addValue("${h.value}", forHTTPHeaderField: "${h.key}")`).join('\n        ');
        return `import Foundation\n\nlet url = URL(string: "${url}")!\nvar request = URLRequest(url: url)\nrequest.httpMethod = "${r.method}"\n        ${H}\n${bodyStr ? `request.httpBody = """\n${bodyStr}\n""".data(using: .utf8)\n` : ''}let task = URLSession.shared.dataTask(with: request) { data, resp, err in\n    if let data = data { print(String(data: data, encoding: .utf8)!) }\n}\ntask.resume()\n`;
      },
      'Rust(reqwest)': () => {
        const H = hs.map(h => `    .header("${h.key}", "${h.value}")`).join('\n');
        return `use std::collections::HashMap;\n\n#[tokio::main]\nasync fn main() -> Result<(), Box<dyn std::error::Error>> {\n    let client = reqwest::Client::new();\n    let resp = client.${r.method.toLowerCase()}("${url}")\n${H}\n${bodyStr ? `        .body(r#"${bodyStr}"#)\n` : ''}        .send()\n        .await?;\n    println!("{}", resp.text().await?);\n    Ok(())\n}\n`;
      },
      'Dart(http)': () => {
        const H = hs.map(h => `    request.headers['${h.key}'] = '${h.value}';`).join('\n');
        return `import 'package:http/http.dart' as http;\n\nvoid main() async {\n  var request = http.Request('${r.method}', Uri.parse('${url}'));\n${H}\n${bodyStr ? `  request.body = r'''${bodyStr}''';\n` : ''}  var resp = await http.Client().send(request);\n  print(await resp.stream.bytesToString());\n}\n`;
      },
    };
    const cap = (m) => m.charAt(0) + m.slice(1).toLowerCase();
    window._cap = cap;
    const langs = Object.keys(LANGS);
    openForm('生成代码',
      `<div class="field mt"><label>语言（16 种常用语言原生生成）</label>` +
      `<select id="gcLang">${langs.map(l => `<option>${esc(l)}</option>`).join('')}</select></div>` +
      `<div class="field mt"><label>代码</label><textarea id="gcCode" rows="16" readonly></textarea></div>` +
      `<div class="mops"><button class="ghost" id="gcCopy" type="button">复制代码</button></div>`,
      closeForm, { hideCancel: true, saveText: '关闭' });
    const update = () => { $('#gcCode').value = LANGS[$('#gcLang').value](); };
    $('#gcLang').addEventListener('change', update);
    update();
    $('#gcCopy').addEventListener('click', () => {
      navigator.clipboard.writeText($('#gcCode').value).then(() => toast('已复制', true));
    });
  }

  /* ================= cURL 导入（增强版：--form / -G / --url） ================= */
  function parseCurl(text) {
    const s = text.replace(/\\\n/g, ' ').trim();
    const out = { method: 'GET', url: '', headers: [], body: '', form: [] };
    const tokens = s.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) || [];
    let bodyFlags = 0;
    for (let i = 1; i < tokens.length; i++) {
      const t = tokens[i].replace(/^['"]|['"]$/g, '');
      const nx = () => (tokens[i + 1] || '').replace(/^['"]|['"]$/g, '');
      if (t === '-X' || t === '--request') { out.method = nx().toUpperCase(); i++; }
      else if (t === '-H' || t === '--header') {
        const hv = nx(); const j = hv.indexOf(':');
        if (j > 0) out.headers.push({ key: hv.slice(0, j).trim(), value: hv.slice(j + 1).trim(), enabled: true, description: '' });
        i++;
      } else if (t === '-d' || t === '--data' || t === '--data-raw' || t === '--data-binary' || t === '--data-urlencode') {
        out.body = nx(); bodyFlags++; i++;
      } else if (t === '-F' || t === '--form') {
        const fv = nx(); const j = fv.indexOf('=');
        if (j > 0) out.form.push({ key: fv.slice(0, j).trim(), value: fv.slice(j + 1).trim(), enabled: true, description: '' });
        bodyFlags++; i++;
      } else if (t === '--url') { out.url = nx(); i++; }
      else if (!t.startsWith('-') && !out.url && /^https?:\/\//.test(t)) { out.url = t; }
    }
    if (bodyFlags) out.method = out.method === 'GET' ? 'POST' : out.method;
    if (!out.url) throw new Error('未识别到 URL（需以 http(s):// 开头）');
    return out;
  }
  function importCurl() {
    openForm('导入 cURL 命令',
      `<div class="field mt"><label>粘贴 curl 命令（识别 -X / -H / -d / -F / --url 与 URL）</label>` +
      `<textarea id="ciText" rows="7" placeholder="curl -X POST 'http://...' -H 'Content-Type: application/json' -d '{...}'"></textarea></div>`,
      async () => {
        const c = parseCurl($('#ciText').value);
        closeForm();
        state.selReqId = null;
        state._newCollectionId = null;
        renderTree();
        openEditor(null);
        $('#reqMethod').value = c.method;
        $('#reqUrl').value = c.url;
        $('#reqName').value = '导入的接口';
        $('#reqHeaders').innerHTML = (c.headers.length ? c.headers : [{ key: '', value: '', enabled: true }])
          .map(h => kvRow(h.key, h.value, h.enabled, h.description)).join('');
        if (c.form.length) {
          $('#reqBodyType').value = 'form-data';
          $('#reqParams').innerHTML = c.form.map(p => kvRow(p.key, p.value, true, '')).join('');
        } else if (c.body) {
          $('#reqBodyType').value = 'json';
          try { $('#reqBody').value = JSON.stringify(JSON.parse(c.body), null, 2); }
          catch (e) { $('#reqBodyType').value = 'raw'; $('#reqBody').value = c.body; }
        }
        toast('已解析，确认后点「保存」', true);
      });
  }

  /* ================= 自动化测试（套件） ================= */
  function renderSuiteSelectors() {
    const projOpts = state.projects.filter(p => p.project_type !== 'WEBSOCKET').map(p => [p.id, p.name]);
    $('#suiteProjectSel').innerHTML = projOpts.map(o =>
      `<option value="${o[0]}">${esc(o[1])}</option>`).join('') || '<option value="">— 无项目 —</option>';
    const envOpts = [['', '套件默认环境']].concat(state.envs.map(e => [e.id, e.name + (e.is_active ? '（激活）' : '')]));
    $('#suiteEnvSel').innerHTML = envOpts.map(o => `<option value="${esc(o[0])}">${esc(o[1])}</option>`).join('');
  }
  async function loadSuites() {
    state.suites = (await api('/suites')).data;
    const pid = +($('#suiteProjectSel').value || 0);
    const items = state.suites.filter(s => !pid || s.project_id === pid);
    $('#suiteListBox').innerHTML = items.map(s =>
      `<div class="t-req ${s.id === state.selSuiteId ? 'sel' : ''}" data-suite="${s.id}">` +
      `<b>${esc(s.name)}</b><span class="mockbadge">${(s.suite_requests || []).length} 请求</span></div>`).join('') ||
      '<div class="empty">暂无套件 —— 「新建套件」</div>';
    $('#suiteListBox').querySelectorAll('[data-suite]').forEach(el =>
      el.addEventListener('click', () => openSuite(+el.dataset.suite)));
  }
  async function openSuite(id) {
    /* 自取最新（不依赖列表缓存）：新建/变更后立即打开不丢数据 */
    let s = state.suites.find(x => x.id === id);
    if (!s) {
      try { s = (await api('/suites/' + id)).data; } catch (e) { return; }
    }
    if (!s) return;
    state.selSuiteId = id;
    $('#suiteWelcome').style.display = 'none';
    $('#suiteDetail').style.display = '';
    $('#suiteDetailTitle').textContent = '套件：' + s.name;
    $('#suiteEnvSel').value = s.environment_id || '';
    const env = state.envs.find(e => e.id === s.environment_id);
    $('#suiteMeta').textContent = (s.description || '无描述') +
      ' · 环境: ' + (env ? env.name : '默认') + ' · 创建人: ' + (s.created_by || 'platform');
    const srs = s.suite_requests || [];
    $('#suiteReqTbody').innerHTML = srs.map((sr, i) => {
      const r = state.requests.find(x => x.id === sr.request_id) || { name: '已删除', method: '-', url: '-' };
      return `<tr><td>${i + 1}</td><td>${esc(r.name)}</td><td>${mBadge(r.method)}</td>` +
        `<td class="muted" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.url)}</td>` +
        `<td><input type="checkbox" data-tg="${sr.request_id}" ${sr.enabled ? 'checked' : ''}></td>` +
        `<td><div class="ops"><button class="ghost mini" data-up="${i}" ${i === 0 ? 'disabled' : ''}>↑</button>` +
        `<button class="ghost mini" data-down="${i}" ${i === srs.length - 1 ? 'disabled' : ''}>↓</button>` +
        `<button class="mini danger-ghost" data-rm="${sr.request_id}">移除</button></div></td></tr>`;
    }).join('') || '<tr><td colspan="6" class="empty">还没有请求 —— 「＋ 添加接口」</td></tr>';
    $('#suiteReqTbody').querySelectorAll('[data-tg]').forEach(el => el.addEventListener('change', () =>
      api('/suites/' + id + '/requests/' + el.dataset.tg, { method: 'PUT', body: { enabled: el.checked } })
        .then(() => { const i = state.suites.findIndex(x => x.id === id); if (i >= 0) refreshSuite(id); })));
    $('#suiteReqTbody').querySelectorAll('[data-up]').forEach(el => el.addEventListener('click', () => moveSuiteReq(+el.dataset.up, -1)));
    $('#suiteReqTbody').querySelectorAll('[data-down]').forEach(el => el.addEventListener('click', () => moveSuiteReq(+el.dataset.up ? +el.dataset.up : +el.dataset.down, 1)));
    $('#suiteReqTbody').querySelectorAll('[data-rm]').forEach(el => el.addEventListener('click', () =>
      api('/suites/' + id + '/requests/' + el.dataset.rm, { method: 'DELETE' })
        .then(() => { refreshSuite(id); toast('已移除', true); })));
    loadExecutions(id);
  }
  async function refreshSuite(id) {
    const d = (await api('/suites/' + id)).data;
    const idx = state.suites.findIndex(x => x.id === id);
    if (idx >= 0) state.suites[idx] = d;
    openSuite(id);
  }
  async function moveSuiteReq(idx, delta) {
    const s = state.suites.find(x => x.id === state.selSuiteId);
    const srs = s.suite_requests;
    const j = idx + delta;
    if (j < 0 || j >= srs.length) return;
    [srs[idx], srs[j]] = [srs[j], srs[idx]];
    await Promise.all(srs.map((x, i) =>
      api('/suites/' + s.id + '/requests/' + x.request_id, { method: 'PUT', body: { order: i + 1 } })));
    refreshSuite(s.id);
  }
  async function openSuiteAddReqs() {
    const sid = state.selSuiteId;
    const s = state.suites.find(x => x.id === sid);
    const [c, r] = await Promise.all([api('/collections?project=' + s.project_id), api('/requests?project=' + s.project_id)]);
    const inSuite = new Set((s.suite_requests || []).map(x => x.request_id));
    const cols = c.data, reqs = r.data;
    openForm('添加接口到套件：' + s.name,
      cols.map(col => {
        const rs = reqs.filter(x => x.collection_id === col.id && !inSuite.has(x.id));
        if (!rs.length) return '';
        return `<div class="mt"><b>${esc(col.name)}</b></div>` +
          rs.map(x => `<label class="chk" style="display:block;margin:4px 0 4px 14px">` +
            `<input type="checkbox" value="${x.id}" class="arChk"> ${mBadge(x.method)} ${esc(x.name)}</label>`).join('');
      }).join('') +
      reqs.filter(x => !x.collection_id && !inSuite.has(x.id)).map(x =>
        `<label class="chk" style="display:block;margin:4px 0">` +
        `<input type="checkbox" value="${x.id}" class="arChk"> ${mBadge(x.method)} ${esc(x.name)}</label>`).join('') +
      (!reqs.filter(x => !inSuite.has(x.id)).length ? '<div class="empty mt">全部接口已在套件内</div>' : ''),
      async () => {
        const ids = $$('#fmBody .arChk').filter(x => x.checked).map(x => +x.value);
        if (!ids.length) return toast('未勾选任何接口', false);
        await api('/suites/' + sid + '/add-requests', { method: 'POST', body: { request_ids: ids } });
        closeForm(); refreshSuite(sid); toast('已添加 ' + ids.length + ' 个接口', true);
      });
  }
  async function loadExecutions(sid) {
    const d = (await api('/executions?suite=' + sid + '&page_size=20')).data;
    $('#execTbody').innerHTML = d.results.map(x =>
      `<tr><td>${x.id}</td><td>${stTag(x.status)}</td>` +
      `<td class="muted">${fmtTime(x.start_time)}</td>` +
      `<td>${x.passed_requests}/${x.total_requests}</td>` +
      `<td class="muted">${esc(x.executed_by)}</td>` +
      `<td><div class="ops"><button class="ghost mini" data-see="${x.id}">结果</button>` +
      `<button class="ghost mini" data-rep="${x.id}">报告</button></div></td></tr>`).join('') ||
      '<tr><td colspan="6" class="empty">暂无执行记录</td></tr>';
    $('#execTbody').querySelectorAll('[data-see]').forEach(b =>
      b.addEventListener('click', () => showExecution(+b.dataset.see)));
    $('#execTbody').querySelectorAll('[data-rep]').forEach(b =>
      b.addEventListener('click', () => makeReport(+b.dataset.rep)));
  }
  async function showExecution(eid) {
    const x = (await api('/executions/' + eid)).data;
    const rows = (x.results || []).map(r => {
      const rs = r.assertions_results || [];
      const ok = rs.filter(a => a.passed).length;
      return `<tr><td>${r.passed ? '<span class="num-ok">✓</span>' : '<span class="num-bad">✗</span>'} ${esc(r.name)}</td>` +
        `<td>${mBadge(r.method || 'GET')}</td>` +
        `<td>${r.status_code != null ? r.status_code : '-'}</td>` +
        `<td>${r.response_time != null ? r.response_time + 'ms' : '-'}</td>` +
        `<td>${rs.length ? ok + '/' + rs.length : '-'}</td>` +
        `<td class="muted" style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.error || '')}</td></tr>`;
    }).join('');
    const rate = x.total_requests ? Math.round(x.passed_requests * 100 / x.total_requests) : 0;
    showInfo('执行 #' + eid,
      `<div class="stats" style="grid-template-columns:repeat(4,1fr)">` +
      `<div class="stat"><div class="num">${x.total_requests}</div><div class="label">总数</div></div>` +
      `<div class="stat s-green"><div class="num">${x.passed_requests}</div><div class="label">通过</div></div>` +
      `<div class="stat s-red"><div class="num">${x.failed_requests}</div><div class="label">失败</div></div>` +
      `<div class="stat s-blue"><div class="num">${rate}%</div><div class="label">通过率</div></div></div>` +
      `<div class="tblwrap mt"><table><thead><tr><th>请求</th><th>方式</th><th>状态码</th><th>耗时</th><th>断言</th><th>错误</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div>`);
  }

  /* ================= 请求历史 ================= */
  async function loadHistories() {
    $$('.reqtabs a[data-htab]').forEach(a => a.classList.toggle('on', a.dataset.htab === state.histTab));
    const kw = ($('#histSearch').value || '').trim();
    let d;
    try {
      d = (await api('/histories?page=' + state.histPage + '&page_size=20&request__request_type=' + state.histTab)).data;
    } catch (e) { throw e; }
    let results = d.results || [];
    if (kw) results = results.filter(h =>
      ((h.request || {}).name || '').toLowerCase().includes(kw.toLowerCase()) ||
      ((h.request_data || {}).url || '').toLowerCase().includes(kw.toLowerCase()));
    $('#histListTbody').innerHTML = results.map(h => {
      const r = h.request || {};
      return `<tr>` +
        `<td><input type="checkbox" data-hsel="${h.id}" ${state.histSel.has(h.id) ? 'checked' : ''}></td>` +
        `<td><b>${esc(r.name || '已删除接口')}</b></td><td>${mBadge((h.request_data || {}).method || r.method || 'GET')}</td>` +
        `<td class="muted" style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc((h.request_data || {}).url || '')}</td>` +
        `<td>${h.status_code != null ? h.status_code : '<span class="num-bad">ERR</span>'}</td>` +
        `<td>${h.response_time != null ? h.response_time : '-'}</td>` +
        `<td class="muted">${esc((h.environment || {}).name || '-')}</td>` +
        `<td class="muted">${fmtTime(h.executed_at)}</td>` +
        `<td><div class="ops"><button class="ghost mini" data-hview="${h.id}">详情</button>` +
        `<button class="ghost mini" data-hretry="${h.id}">重试</button>` +
        `<button class="mini danger-ghost" data-hdel="${h.id}">删除</button></div></td></tr>`;
    }).join('') || '<tr><td colspan="9" class="empty">暂无历史</td></tr>';
    const pages = Math.max(1, Math.ceil(d.count / (d.page_size || 20)));
    $('#histPager').textContent = `共 ${d.count} 条 · 第 ${state.histPage}/${pages} 页`;
    $('#histListTbody').querySelectorAll('[data-hsel]').forEach(el => el.addEventListener('change', () => {
      if (el.checked) state.histSel.add(+el.dataset.hsel); else state.histSel.delete(+el.dataset.hsel);
      $('#btnHistBatchDel').disabled = !state.histSel.size;
    }));
    $('#histListTbody').querySelectorAll('[data-hview]').forEach(b =>
      b.addEventListener('click', () => showHistory(+b.dataset.hview)));
    $('#histListTbody').querySelectorAll('[data-hretry]').forEach(b =>
      b.addEventListener('click', async () => {
        const h = (await api('/histories?page_size=100')).data.results.find(x => x.id === +b.dataset.hretry);
        if (!h || !h.request || !h.request.id) return toast('原接口已删除，无法重试', false);
        await api('/requests/' + h.request.id + '/execute', { method: 'POST',
          body: { environment_id: (h.environment || {}).id || null } });
        toast('已重试，历史已刷新', true);
        loadHistories();
      }));
    $('#histListTbody').querySelectorAll('[data-hdel]').forEach(b =>
      b.addEventListener('click', async () => {
        await api('/histories/' + b.dataset.hdel, { method: 'DELETE' });
        loadHistories();
      }));
  }
  async function showHistory(hid) {
    const d = (await api('/histories?page_size=200')).data;
    const h = (d.results || []).find(x => x.id === hid);
    if (!h) return toast('记录不存在', false);
    const rd = h.request_data || {}, rs = h.response_data || {};
    const kvTable = (obj) => `<div class="tblwrap"><table><tbody>` +
      Object.entries(obj || {}).map(([k, v]) =>
        `<tr><td style="width:180px"><b>${esc(k)}</b></td><td class="muted" style="word-break:break-all">${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</td></tr>`).join('') +
      `</tbody></table></div>`;
    let respBody = h.error_message || rs.body || '(空)';
    try { respBody = JSON.stringify(JSON.parse(respBody), null, 2); } catch (e) { /* 原样 */ }
    showInfo('历史详情：' + ((h.request || {}).name || '#' + h.id),
      fmField('状态码 / 耗时', 'hvS', `${h.status_code != null ? h.status_code : 'ERR'} · ${h.response_time != null ? h.response_time + 'ms' : '-'}`) +
      fmField('执行时间', 'hvT', fmtTime(h.executed_at)) +
      `<h4 class="mt">请求信息</h4>` + kvTable({ URL: rd.url, 方式: rd.method, 请求头: rd.headers, 参数: rd.params, 请求体: rd.body }) +
      `<h4 class="mt">响应信息</h4><pre class="logbox" style="max-height:260px">${esc(respBody)}</pre>`);
  }

  /* ================= 环境管理 ================= */
  function envVarsText(e) {
    return Object.entries(e.variables || {}).map(([k, v]) => {
      if (v && typeof v === 'object') return k + '=' + (v.initialValue == null ? '' : v.initialValue) + '|' + (v.currentValue == null ? '' : v.currentValue);
      return k + '=' + v;
    }).join('\n');
  }
  function parseEnvVars(text) {
    const variables = {};
    (text || '').split('\n').forEach(line => {
      const i = line.indexOf('=');
      if (i <= 0) return;
      const k = line.slice(0, i).trim();
      const rest = line.slice(i + 1).trim();
      const j = rest.indexOf('|');
      if (j >= 0) variables[k] = { initialValue: rest.slice(0, j), currentValue: rest.slice(j + 1) };
      else variables[k] = rest;
    });
    return variables;
  }
  function renderEnvTable() {
    $$('.reqtabs a[data-etab]').forEach(a => a.classList.toggle('on', a.dataset.etab === state.envTab));
    const items = state.envs.filter(e => e.scope === state.envTab);
    $('#envTbody2').innerHTML = items.map(e =>
      `<tr><td><b>${esc(e.name)}</b></td>` +
      `<td>${e.scope === 'GLOBAL' ? '全局环境' : '项目环境'}</td>` +
      `<td class="muted">${esc((state.projects.find(p => p.id === e.project_id) || {}).name || '—')}</td>` +
      `<td>${Object.keys(e.variables || {}).length}</td>` +
      `<td>${e.is_active ? '<span class="status st-PASSED">已激活</span>' : '<button class="ghost mini" data-act="' + e.id + '">激活</button>'}</td>` +
      `<td><div class="ops"><button class="ghost mini" data-view="${e.id}">查看变量</button>` +
      `<button class="ghost mini" data-edit="${e.id}">编辑</button>` +
      `<button class="ghost mini" data-copy="${e.id}">复制</button>` +
      `<button class="mini danger-ghost" data-del="${e.id}">删除</button></div></td></tr>`).join('') ||
      '<tr><td colspan="6" class="empty">暂无环境</td></tr>';
    $('#envTbody2').querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
      await api('/environments/' + b.dataset.act + '/activate', { method: 'POST' });
      reloadTreeData(); toast('已激活', true);
    }));
    $('#envTbody2').querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => {
      const e = state.envs.find(x => x.id === +b.dataset.view);
      showInfo('环境变量：' + e.name,
        `<div class="tblwrap"><table><thead><tr><th>Key</th><th>初始值</th><th>当前值</th></tr></thead><tbody>` +
        Object.entries(e.variables || {}).map(([k, v]) => {
          const iv = v && typeof v === 'object' ? v.initialValue : v;
          const cv = v && typeof v === 'object' ? v.currentValue : v;
          return `<tr><td><b>${esc(k)}</b></td><td class="muted">${esc(iv == null ? '' : iv)}</td><td>${esc(cv == null ? '' : cv)}</td></tr>`;
        }).join('') + '</tbody></table></div>');
    }));
    $('#envTbody2').querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {
      const e = state.envs.find(x => x.id === +b.dataset.copy);
      await api('/environments', { method: 'POST', body: {
        name: e.name + ' - Copy', scope: e.scope, variables: e.variables, project_id: e.project_id } });
      reloadTreeData(); toast('已复制', true);
    }));
    $('#envTbody2').querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      if (!(await confirmModal('删除环境', '确定删除该环境？'))) return;
      await api('/environments/' + b.dataset.del, { method: 'DELETE' }); reloadTreeData();
    }));
    $('#envTbody2').querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => {
      const e = state.envs.find(x => x.id === +b.dataset.edit);
      openEnvForm(e);
    }));
  }
  function openEnvForm(e) {
    const isEdit = !!e;
    openForm(isEdit ? '编辑环境' : '新建环境',
      fmField('环境名称', 'efName', e && e.name) +
      fmSelect('作用域', 'efScope', [['LOCAL', '项目环境'], ['GLOBAL', '全局环境']], e && e.scope || 'LOCAL') +
      fmSelect('关联项目（项目环境必选）', 'efProj', [['', '— 无 —']].concat(state.projects.map(p => [p.id, p.name])), e && e.project_id) +
      `<div class="field mt"><label>变量（每行 key=初始值|当前值；无 | 则两者相同）</label>` +
      `<textarea id="efVars" rows="6" placeholder="base_url=http://127.0.0.1:8080|http://127.0.0.1:8080">${esc(e ? envVarsText(e) : '')}</textarea></div>`,
      async () => {
        const payload = {
          name: $('#efName').value.trim(), scope: $('#efScope').value,
          variables: parseEnvVars($('#efVars').value),
          project_id: +$('#efProj').value || null,
        };
        if (!payload.name) return toast('环境名称不能为空', false);
        if (payload.scope === 'LOCAL' && !payload.project_id) return toast('项目环境必须关联项目', false);
        if (payload.scope === 'GLOBAL') payload.project_id = null;
        if (isEdit) await api('/environments/' + e.id, { method: 'PUT', body: payload });
        else await api('/environments', { method: 'POST', body: payload });
        closeForm(); reloadTreeData(); toast('环境已保存', true);
      });
  }

  /* ================= 测试报告（Allure） ================= */
  async function loadReports() {
    const d = (await api('/executions?page_size=30')).data;
    $('#reportTbody').innerHTML = (d.results || []).map(x =>
      `<tr><td>${x.id}</td><td>${esc((state.suites.find(s => s.id === x.suite_id) || {}).name || '#' + x.suite_id)}</td>` +
      `<td>${stTag(x.status)}</td><td>${x.total_requests}</td><td>${x.passed_requests}</td><td>${x.failed_requests}</td>` +
      `<td class="muted">${esc(x.executed_by)}</td><td class="muted">${fmtTime(x.created_at)}</td>` +
      `<td><button class="ghost mini" data-rep="${x.id}">生成并查看报告</button></td></tr>`).join('') ||
      '<tr><td colspan="9" class="empty">暂无执行记录 —— 先到「自动化测试」运行套件</td></tr>';
    $('#reportTbody').querySelectorAll('[data-rep]').forEach(b =>
      b.addEventListener('click', () => makeReport(+b.dataset.rep)));
  }
  async function makeReport(eid) {
    toast('报告生成中…', true);
    try {
      const d = (await api('/executions/' + eid + '/allure-report', { method: 'POST' })).data;
      window.open(d.report_url, '_blank');
      toast('报告已生成', true);
    } catch (e) { toast(e.message, false); }
  }

  /* ================= 定时任务 ================= */
  async function loadTasks() {
    state.tasks = (await api('/tasks')).data;
    const fs = $('#taskFilterStatus').value;
    const items = state.tasks.filter(t => !fs || t.status === fs);
    $('#taskTbody').innerHTML = items.map(t => {
      const target = t.task_type === 'TEST_SUITE'
        ? ((state.suites.find(s => s.id === t.suite_id) || {}).name || '#' + t.suite_id)
        : ((state.requests.find(r => r.id === t.request_id) || {}).name || '#' + t.request_id);
      const trig = t.trigger_type === 'CRON' ? ('CRON ' + t.cron_expression)
        : t.trigger_type === 'INTERVAL' ? ('每 ' + t.interval_seconds + ' 秒') : ('单次 ' + fmtTime(t.execute_at));
      const ntype = { email: '邮件', webhook: 'Webhook', both: '邮件+Webhook' }[t.notification_type] || '邮件+Webhook';
      return `<tr><td><b>${esc(t.name)}</b><div class="muted">${esc(target)}</div></td>` +
        `<td>${t.task_type === 'TEST_SUITE' ? '套件执行' : '单请求'}</td>` +
        `<td class="muted">${esc(trig)}</td><td class="muted">${esc(ntype)}</td>` +
        `<td class="muted">${fmtTime(t.next_run_time)}</td><td class="muted">${fmtTime(t.last_run_time)}</td>` +
        `<td>${stTag(t.status)}</td><td>${t.successful_runs}/${t.total_runs}</td>` +
        `<td><div class="ops">` +
        `<button class="ghost mini" data-run="${t.id}">立即执行</button>` +
        `<button class="ghost mini" data-edit="${t.id}">编辑</button>` +
        `<button class="ghost mini" data-logs="${t.id}">日志</button>` +
        (t.status === 'ACTIVE'
          ? `<button class="ghost mini" data-pause="${t.id}">暂停</button>`
          : `<button class="ghost mini" data-act="${t.id}">激活</button>`) +
        `<button class="mini danger-ghost" data-del="${t.id}">删除</button></div></td></tr>`;
    }).join('') || '<tr><td colspan="9" class="empty">暂无定时任务</td></tr>';
    $('#taskTbody').querySelectorAll('[data-run]').forEach(b => b.addEventListener('click', async () => {
      await api('/tasks/' + b.dataset.run + '/run-now', { method: 'POST' });
      toast('已触发，稍后刷新查看日志', true);
    }));
    $('#taskTbody').querySelectorAll('[data-edit]').forEach(b =>
      b.addEventListener('click', () => openTaskForm(state.tasks.find(t => t.id === +b.dataset.edit))));
    $('#taskTbody').querySelectorAll('[data-logs]').forEach(b =>
      b.addEventListener('click', () => showTaskLogs(+b.dataset.logs)));
    $('#taskTbody').querySelectorAll('[data-pause]').forEach(b => b.addEventListener('click', async () => {
      await api('/tasks/' + b.dataset.pause + '/pause', { method: 'POST' }); loadTasks();
    }));
    $('#taskTbody').querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
      await api('/tasks/' + b.dataset.act + '/activate', { method: 'POST' }); loadTasks();
    }));
    $('#taskTbody').querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      if (!(await confirmModal('删除任务', '任务及其执行日志将删除，确定？'))) return;
      await api('/tasks/' + b.dataset.del, { method: 'DELETE' }); loadTasks();
    }));
  }
  async function showTaskLogs(tid) {
    const d = (await api('/tasks/' + tid + '/logs?page_size=30')).data;
    showInfo('任务执行日志',
      `<div class="tblwrap"><table><thead><tr><th>状态</th><th>开始</th><th>结束</th><th>错误</th></tr></thead><tbody>` +
      (d.results || []).map(l =>
        `<tr><td>${stTag(l.status)}</td><td class="muted">${fmtTime(l.start_time)}</td>` +
        `<td class="muted">${fmtTime(l.end_time)}</td>` +
        `<td class="muted" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(l.error_message || '')}</td></tr>`).join('') +
      '</tbody></table></div>');
  }
  async function openTaskForm(task) {
    await Promise.all([loadSuites(), loadUsers()]);
    const isEdit = !!task;
    const suiteOpts = [['', '— 选择套件 —']].concat(state.suites.map(s => [s.id, s.name]));
    const reqOpts = [['', '— 选择请求 —']].concat(state.requests.map(r => [r.id, r.method + ' ' + r.name]));
    const envOpts = [['', '默认（激活环境）']].concat(state.envs.map(e => [e.id, e.name]));
    const emailOpts = state.users.map(u => [u.email || u.username, u.username + (u.email ? '（' + u.email + '）' : '')]);
    openForm(isEdit ? '编辑定时任务' : '新建定时任务',
      fmField('任务名称', 'tfName', task && task.name) +
      fmTextarea('任务描述', 'tfDesc', task && task.description, 2) +
      fmSelect('任务类型', 'tfType', [['TEST_SUITE', '测试套件执行'], ['API_REQUEST', 'API 请求执行']], task && task.task_type) +
      `<div id="tfSuiteWrap">${fmSelect('测试套件', 'tfSuite', suiteOpts, task && task.suite_id)}</div>` +
      `<div id="tfReqWrap" style="display:none">${fmSelect('API 请求', 'tfReq', reqOpts, task && task.request_id)}</div>` +
      fmSelect('执行环境', 'tfEnv', envOpts, task && task.environment_id) +
      fmSelect('触发器', 'tfTrigger', [['CRON', 'Cron 表达式'], ['INTERVAL', '固定间隔'], ['ONCE', '单次执行']], task && task.trigger_type || 'INTERVAL') +
      `<div id="tfCronWrap" style="display:none">${fmField('Cron 表达式（分 时 日 月 周）', 'tfCron', task && task.cron_expression)}</div>` +
      `<div id="tfIntervalWrap">${fmField('间隔秒数（≥60）', 'tfInterval', task && task.interval_seconds || 60, 'number')}</div>` +
      `<div id="tfOnceWrap" style="display:none">${fmField('执行时间（epoch 秒）', 'tfOnce', task && task.execute_at, 'number')}</div>` +
      `<div class="mt" style="display:flex;gap:20px">` +
      `<label class="chk"><input type="checkbox" id="tfNotifyFail" ${!task || task.notify_on_failure !== false ? 'checked' : ''}> 失败时通知</label>` +
      `<label class="chk"><input type="checkbox" id="tfNotifyOk" ${task && task.notify_on_success ? 'checked' : ''}> 成功时通知</label></div>` +
      fmSelect('通知方式', 'tfNotifyType', [['both', '邮件+Webhook'], ['email', '邮件'], ['webhook', 'Webhook']], task && task.notification_type) +
      `<div class="field mt"><label>通知邮箱（多选）</label><select id="tfEmails" multiple style="height:70px">` +
      emailOpts.map(o => `<option value="${esc(o[0])}" ${(task && (task.notify_emails || []).includes(o[0])) ? 'selected' : ''}>${esc(o[1])}</option>`).join('') +
      `</select></div>`,
      async () => {
        const payload = {
          name: $('#tfName').value.trim(), description: $('#tfDesc').value.trim(),
          task_type: $('#tfType').value,
          trigger_type: $('#tfTrigger').value,
          suite_id: +$('#tfSuite').value || null,
          request_id: +$('#tfReq').value || null,
          environment_id: +$('#tfEnv').value || null,
          cron_expression: $('#tfCron').value.trim(),
          interval_seconds: +$('#tfInterval').value || null,
          execute_at: +$('#tfOnce').value || null,
          status: (task && task.status) || 'ACTIVE',
          notify_on_success: $('#tfNotifyOk').checked,
          notify_on_failure: $('#tfNotifyFail').checked,
          notification_type: $('#tfNotifyType').value,
          notify_emails: Array.from($('#tfEmails').selectedOptions).map(o => o.value),
        };
        if (isEdit) await api('/tasks/' + task.id, { method: 'PUT', body: payload });
        else await api('/tasks', { method: 'POST', body: payload });
        closeForm(); loadTasks(); loadDashboard();
        toast('任务已保存', true);
      });
    const sync = () => {
      const tt = $('#tfType').value, tr = $('#tfTrigger').value;
      $('#tfSuiteWrap').style.display = tt === 'TEST_SUITE' ? '' : 'none';
      $('#tfReqWrap').style.display = tt === 'API_REQUEST' ? '' : 'none';
      $('#tfCronWrap').style.display = tr === 'CRON' ? '' : 'none';
      $('#tfIntervalWrap').style.display = tr === 'INTERVAL' ? '' : 'none';
      $('#tfOnceWrap').style.display = tr === 'ONCE' ? '' : 'none';
    };
    ['tfType', 'tfTrigger'].forEach(id => $('#' + id).addEventListener('change', sync));
    sync();
  }

  /* ================= 通知列表 + 配置 ================= */
  async function loadNotifLogs() {
    const st = $('#notifFilterStatus').value, ch = $('#notifFilterChannel').value;
    let url = '/notification-logs?page_size=30';
    if (st) url += '&status=' + st;
    const d = (await api(url)).data;
    let items = d.results || [];
    if (ch) items = items.filter(x => x.channel === ch);   // 渠道为本地字段，前端过滤
    $('#notifTbody').innerHTML = items.map(l => {
      const bot = l.webhook_bot_info || {};
      const rcpt = (l.recipient_info || []).map(r => r.name || r.email).join('、') ||
                   (bot.bot_name || '未知');
      return `<tr><td>${esc(l.task_name)}</td>` +
        `<td>${l.channel === 'webhook' ? 'Webhook' + (bot.bot_name ? '·' + esc(bot.bot_name) : '') : '邮件'}</td>` +
        `<td class="muted">${esc(rcpt)}</td>` +
        `<td>${stTag(l.status)}</td>` +
        `<td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(l.error_message || '')}</td>` +
        `<td class="muted">${fmtTime(l.sent_at)}</td>` +
        `<td><button class="ghost mini" data-nview="${l.id}">详情</button></td></tr>`;
    }).join('') || '<tr><td colspan="7" class="empty">暂无通知记录（任务执行并配置通知后生成）</td></tr>';
    $('#notifTbody').querySelectorAll('[data-nview]').forEach(b =>
      b.addEventListener('click', async () => {
        const x = (await api('/notification-logs/' + b.dataset.nview)).data;
        showInfo('通知详情',
          fmField('任务', 'nvT', x.task_name) +
          fmField('渠道 / 类型', 'nvC', (x.channel === 'webhook' ? 'Webhook' : '邮件') + ' · ' + x.notification_type) +
          fmField('收件人', 'nvR', x.recipients_display) +
          fmField('状态 / 重试', 'nvS', x.status + ' · ' + x.retry_status) +
          fmField('错误', 'nvE', x.error_message || '—') +
          fmTextarea('通知内容', 'nvB', x.notification_content, 8));
      }));
  }
  async function loadNotifConfig() {
    const s = (await api('/settings')).data;
    $('#setSmtpHost').value = s.smtp_host || '';
    $('#setSmtpPort').value = s.smtp_port || 465;
    $('#setSmtpUser').value = s.smtp_user || '';
    $('#setSmtpFrom').value = s.smtp_from || '';
    $('#setSmtpSsl').value = s.smtp_use_ssl === false ? '0' : '1';
    $('#setNotifyFail').checked = !!s.notify_on_failure;
    $('#setNotifyOk').checked = !!s.notify_on_success;
    $('#setEmails').value = (s.notify_emails || []).join(', ');
    const bots = (await api('/settings/webhook-bots')).data;
    $('#botTbody').innerHTML = bots.map((b, i) =>
      `<tr><td><b>${esc(b.name)}</b></td><td>${esc(b.type)}</td>` +
      `<td class="muted" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(b.webhook_url)}</td>` +
      `<td>${b.enabled ? '<span class="status st-PASSED">启用</span>' : '<span class="status st-PENDING">停用</span>'}</td>` +
      `<td><div class="ops"><button class="ghost mini" data-bedit="${i}">编辑</button>` +
      `<button class="mini danger-ghost" data-bdel="${i}">删除</button></div></td></tr>`).join('') ||
      '<tr><td colspan="5" class="empty">暂无机器人 —— 添加飞书/企微/钉钉/通用 Webhook</td></tr>';
    $('#botTbody').querySelectorAll('[data-bedit]').forEach(b => {
      const idx = +b.dataset.bedit;
      b.addEventListener('click', () => openBotForm(Object.assign({}, bots[idx], { _idx: idx })));
    });
    $('#botTbody').querySelectorAll('[data-bdel]').forEach(b =>
      b.addEventListener('click', async () => {
        const rest = bots.filter((_, i) => i !== +b.dataset.bdel);
        await api('/settings/webhook-bots', { method: 'PUT', body: { bots: rest } });
        loadNotifConfig(); toast('已删除', true);
      }));
  }
  function openBotForm(bot) {
    const isEdit = !!bot;
    openForm(isEdit ? '编辑机器人' : '添加机器人',
      fmField('名称', 'bfName', bot && bot.name) +
      fmSelect('类型', 'bfType', [['feishu', '飞书'], ['wechat', '企业微信'], ['dingtalk', '钉钉（支持加签）'], ['generic', '通用']], bot && bot.type) +
      fmField('Webhook 地址', 'bfUrl', bot && bot.webhook_url) +
      fmField('加签密钥（仅钉钉）', 'bfSecret', bot && bot.secret) +
      `<label class="chk mt"><input type="checkbox" id="bfEnabled" ${!bot || bot.enabled ? 'checked' : ''}> 启用</label>`,
      async () => {
        (async () => {
          const cur = (await api('/settings/webhook-bots')).data;
          const item = {
            name: $('#bfName').value.trim(), type: $('#bfType').value,
            webhook_url: $('#bfUrl').value.trim(), secret: $('#bfSecret').value.trim(),
            enabled: $('#bfEnabled').checked,
          };
          if (!item.name || !item.webhook_url) return toast('名称与地址不能为空', false);
          if (isEdit) cur.splice(bot._idx, 1, item);
          else cur.push(item);
          await api('/settings/webhook-bots', { method: 'PUT', body: { bots: cur } });
          closeForm(); loadNotifConfig(); toast('已保存', true);
        })();
      });
  }

  /* ================= AI 服务配置 ================= */
  async function loadAiConfigs() {
    const items = (await api('/ai-configs')).data;
    $('#aiTbody').innerHTML = items.map(c =>
      `<tr><td><b>${esc(c.name)}</b></td><td>${esc(c.service_type_display)}</td>` +
      `<td>${esc(c.role_display)}</td><td class="muted">${esc(c.model_name)}</td>` +
      `<td>${c.is_active ? '<span class="status st-PASSED">启用</span>' : '<span class="status st-PENDING">停用</span>'}</td>` +
      `<td><div class="ops"><button class="ghost mini" data-atest="${c.id}">测试连接</button>` +
      `<button class="ghost mini" data-aedit="${c.id}">编辑</button>` +
      `<button class="mini danger-ghost" data-adel="${c.id}">删除</button></div></td></tr>`).join('') ||
      '<tr><td colspan="6" class="empty">暂无配置</td></tr>';
    $('#aiTbody').querySelectorAll('[data-atest]').forEach(b => b.addEventListener('click', async () => {
      toast('连接测试中…', true);
      try {
        const d = await api('/ai-configs/test-connection', { method: 'POST', body: { config_id: +b.dataset.atest } });
        toast(d.msg || '连接成功', true);
      } catch (e) { toast(e.message, false); }
    }));
    $('#aiTbody').querySelectorAll('[data-aedit]').forEach(b =>
      b.addEventListener('click', () => openAiForm(+b.dataset.aedit)));
    $('#aiTbody').querySelectorAll('[data-adel]').forEach(b => b.addEventListener('click', async () => {
      if (!(await confirmModal('删除配置', '确定删除该 AI 配置？'))) return;
      await api('/ai-configs/' + b.dataset.adel, { method: 'DELETE' }); loadAiConfigs();
    }));
  }
  async function openAiForm(aid) {
    let c = null;
    if (aid) c = (await api('/ai-configs')).data.find(x => x.id === aid);
    openForm(aid ? '编辑 AI 配置' : '新建 AI 配置',
      fmField('配置名称', 'afName', c && c.name) +
      fmSelect('服务类型', 'afType', [['openai', 'OpenAI'], ['azure', 'Azure OpenAI'], ['anthropic', 'Anthropic'],
        ['deepseek', 'DeepSeek'], ['qwen', '通义千问'], ['siliconflow', 'SiliconFlow'], ['other', '其他(OpenAI兼容)']], c && c.service_type) +
      fmSelect('角色', 'afRole', [['doc_extractor', '文档提取'], ['naming', '命名规范'],
        ['mock_data', '模拟数据'], ['description', '描述补全']], c && c.role) +
      fmField('API Key', 'afKey', '', 'password', c ? '（留空=不修改）' : 'sk-...') +
      fmField('Base URL', 'afUrl', c && c.base_url, 'text', 'https://api.openai.com/v1') +
      fmField('模型名称', 'afModel', c && c.model_name, 'text', 'gpt-4o-mini') +
      fmField('max_tokens', 'afMax', (c && c.max_tokens) || 4096, 'number') +
      fmField('temperature (0~2)', 'afTemp', (c && c.temperature) || 0.7, 'number') +
      `<label class="chk mt"><input type="checkbox" id="afActive" ${!c || c.is_active ? 'checked' : ''}> 启用</label>`,
      async () => {
        const payload = {
          name: $('#afName').value.trim(), service_type: $('#afType').value, role: $('#afRole').value,
          base_url: $('#afUrl').value.trim(), model_name: $('#afModel').value.trim(),
          max_tokens: +$('#afMax').value || 4096, temperature: +$('#afTemp').value || 0.7,
          is_active: $('#afActive').checked,
        };
        const key = $('#afKey').value.trim();
        if (key) payload.api_key = key;
        if (!payload.name || !payload.base_url || !payload.model_name) return toast('名称/BaseURL/模型不能为空', false);
        if (!aid && !key) return toast('API Key 不能为空', false);
        if (aid) await api('/ai-configs/' + aid, { method: 'PUT', body: payload });
        else await api('/ai-configs', { method: 'POST', body: payload });
        closeForm(); loadAiConfigs(); toast('已保存', true);
      });
  }

  /* ================= 绑定与初始化 ================= */
  function bind() {
    $$('#subnav a').forEach(a => {
      if (a.dataset.icon) a.insertAdjacentHTML('afterbegin', icon(a.dataset.icon, 18));
      a.addEventListener('click', e => { e.preventDefault(); switchTab(a.dataset.panel); });
    });
    /* 仪表盘 */
    $('#btnDashRefresh').addEventListener('click', loadDashboard);
    /* 项目 */
    $('#btnNewProject').addEventListener('click', () => openProjectForm(null));
    $('#btnCreateSample').addEventListener('click', async () => {
      try {
        const d = await api('/projects/create-sample', { method: 'POST' });
        toast(d.msg || '示例项目已创建', true);
        reloadTreeData(); loadProjects();
      } catch (e) { toast(e.message, false); }
    });
    $('#projFilterType').addEventListener('change', loadProjects);
    $('#projFilterStatus').addEventListener('change', loadProjects);
    /* 接口管理 */
    $('#reqProjectSel').addEventListener('change', () => {
      state.selProject = +$('#reqProjectSel').value || null;
      renderTree(); renderEnvSelect();
    });
    $('#apiSearch').addEventListener('input', onSearch);
    $$('.reqtabs a[data-rtab]').forEach(a =>
      a.addEventListener('click', () => switchRtab(a.dataset.rtab)));
    $('#reqType').addEventListener('change', syncTypeTabs);
    $('#btnReqSave').addEventListener('click', () => saveRequest().catch(e => toast(e.message, false)));
    $('#btnReqSend').addEventListener('click', () => sendRequest().catch(e => toast(e.message, false)));
    $('#btnWsConnect').addEventListener('click', wsConnect);
    $('#btnWsDisconnect').addEventListener('click', wsDisconnect);
    $('#btnWsSend').addEventListener('click', wsSend);
    $('#btnWsClear').addEventListener('click', () => { state.wsLogLines = []; $('#wsLog').textContent = ''; });
    $('#btnReqImport').addEventListener('click', importCurl);
    $('#btnReqCode').addEventListener('click', genCode);
    $('#btnVarHelper').addEventListener('click', () => openVarHelper().catch(e => toast(e.message, false)));
    $('#btnReqCopy').addEventListener('click', async () => {
      const req = currentReq();
      if (!req) return toast('请先保存接口后再复制', false);
      await api('/requests/' + req.id + '/copy', { method: 'POST' });
      reloadTreeData(); toast('已复制为新接口', true);
    });
    $('#btnAddHeader').addEventListener('click', () => $('#reqHeaders').insertAdjacentHTML('beforeend', kvRow('', '', true, '')));
    $('#btnAddParam').addEventListener('click', () => $('#reqParams').insertAdjacentHTML('beforeend', kvRow('', '', true, '')));
    $('#btnAddAssertion').addEventListener('click', () => $('#reqAssertions').insertAdjacentHTML('beforeend', assertRow()));
    $$('[data-varinsert]').forEach(b => b.addEventListener('click', () => openVarHelper().catch(e => toast(e.message, false))));
    $$('[data-varinsert-text]').forEach(b => b.addEventListener('click', () => openVarHelper().catch(e => toast(e.message, false))));
    document.addEventListener('focusin', (e) => {
      if (e.target.matches('input[type=text], textarea')) state.lastVarTarget = e.target;
    });
    $('#varClose').addEventListener('click', () => $('#varMask').classList.remove('show'));
    $('#reqAssertions').addEventListener('change', (e) => {
      const row = e.target.closest('.assertrow');
      if (!row) return;
      if (e.target.classList.contains('a-type')) {
        row.outerHTML = assertRow({ ...readRow(row), type: e.target.value });
        return;
      }
      if (e.target.classList.contains('a-media')) {
        const res = row.querySelector('.a-res');
        if (!res) return;
        const isVideo = e.target.value === 'video';
        res.disabled = !isVideo;
        if (!isVideo) res.value = '';
      }
    });
    document.addEventListener('click', (e) => {
      if (e.target.classList && e.target.classList.contains('kv-del')) e.target.closest('.kvrow,.assertrow').remove();
    });
    $('#btnNewCollection').addEventListener('click', () => openCollectionForm(null));
    $('#btnNewRequest').addEventListener('click', () => { state.selReqId = null; renderTree(); openEditor(null); });
    /* 套件 */
    $('#suiteProjectSel').addEventListener('change', loadSuites);
    $('#btnNewSuite').addEventListener('click', async () => {
      const pid = +($('#suiteProjectSel').value || 0);
      if (!pid) return toast('请先创建 HTTP 项目', false);
      openForm('新建套件',
        fmField('套件名称', 'sfName', '新套件 ' + new Date().toLocaleTimeString()) +
        fmTextarea('描述', 'sfDesc', '', 2) +
        fmSelect('执行环境', 'sfEnv', [['', '套件默认环境']].concat(state.envs.map(e => [e.id, e.name]))),
        async () => {
          const d = (await api('/suites', { method: 'POST', body: {
            name: $('#sfName').value.trim(), description: $('#sfDesc').value.trim(),
            project_id: pid, environment_id: +$('#sfEnv').value || null } })).data;
          closeForm(); await loadSuites(); openSuite(d.id); toast('套件已创建', true);
        });
    });
    $('#btnSuiteEdit').addEventListener('click', async () => {
      const s = state.suites.find(x => x.id === state.selSuiteId);
      if (!s) return;
      openForm('编辑套件',
        fmField('套件名称', 'sfName', s.name) + fmTextarea('描述', 'sfDesc', s.description, 2) +
        fmSelect('执行环境', 'sfEnv', [['', '套件默认环境']].concat(state.envs.map(e => [e.id, e.name])), s.environment_id),
        async () => {
          await api('/suites/' + s.id, { method: 'PUT', body: {
            name: $('#sfName').value.trim(), description: $('#sfDesc').value.trim(),
            environment_id: +$('#sfEnv').value || null } });
          closeForm(); await loadSuites(); refreshSuite(s.id); toast('已保存', true);
        });
    });
    $('#btnSuiteCopy').addEventListener('click', async () => {
      const s = state.suites.find(x => x.id === state.selSuiteId);
      if (!s) return;
      const d = (await api('/suites', { method: 'POST', body: {
        name: s.name + ' - Copy', description: s.description,
        project_id: s.project_id, environment_id: s.environment_id } })).data;
      if ((s.suite_requests || []).length) {
        await api('/suites/' + d.id + '/add-requests', { method: 'POST',
          body: { request_ids: s.suite_requests.map(x => x.request_id) } });
      }
      await loadSuites(); openSuite(d.id); toast('已复制套件', true);
    });
    $('#btnSuiteAddReqs').addEventListener('click', () => openSuiteAddReqs().catch(e => toast(e.message, false)));
    $('#btnSuiteRun').addEventListener('click', async () => {
      if (!state.selSuiteId) return;
      const envId = +$('#suiteEnvSel').value || null;
      await api('/suites/' + state.selSuiteId + '/execute', { method: 'POST', body: { environment_id: envId } });
      toast('套件已开始执行，记录会实时刷新', true);
      setTimeout(() => loadExecutions(state.selSuiteId), 1500);
    });
    /* 历史 */
    $$('.reqtabs a[data-htab]').forEach(a => a.addEventListener('click', () => {
      state.histTab = a.dataset.htab; state.histPage = 1; loadHistories();
    }));
    $('#histSearch').addEventListener('input', () => { state.histPage = 1; loadHistories(); });
    $('#histChkAll').addEventListener('change', (e) => {
      $$('#histListTbody [data-hsel]').forEach(c => { c.checked = e.target.checked; });
    });
    $('#btnHistBatchDel').addEventListener('click', async () => {
      const ids = $$('#histListTbody [data-hsel]').filter(c => c.checked).map(c => +c.dataset.hsel);
      if (!ids.length) return toast('未勾选记录', false);
      await api('/histories/batch-delete', { method: 'POST', body: { ids } });
      toast('已删除 %s 条'.replace('%s', ids.length), true); loadHistories();
    });
    $('#btnHistClear').addEventListener('click', async () => {
      if (!(await confirmModal('清空历史', `将清空全部 ${state.histTab} 请求历史，不可恢复，确定？`))) return;
      await api('/histories/clear?request_type=' + state.histTab, { method: 'POST' });
      toast('历史已清空', true); loadHistories();
    });
    /* 环境 */
    $$('.reqtabs a[data-etab]').forEach(a => a.addEventListener('click', () => {
      state.envTab = a.dataset.etab; renderEnvTable();
    }));
    $('#btnNewEnv').addEventListener('click', () => openEnvForm(null));
    /* 报告 */
    $('#btnReportsRefresh').addEventListener('click', loadReports);
    /* 任务 */
    $('#btnNewTask').addEventListener('click', () => openTaskForm(null));
    $('#taskFilterStatus').addEventListener('change', loadTasks);
    /* 通知 */
    $$('.reqtabs a[data-ntab]').forEach(a => a.addEventListener('click', () => {
      $$('.reqtabs a[data-ntab]').forEach(x => x.classList.toggle('on', x === a));
      const isLogs = a.dataset.ntab === 'logs';
      $('#ntab-logs').style.display = isLogs ? '' : 'none';
      $('#ntab-config').style.display = isLogs ? 'none' : '';
      if (!isLogs) loadNotifConfig();
    }));
    $('#notifFilterStatus').addEventListener('change', loadNotifLogs);
    $('#notifFilterChannel').addEventListener('change', loadNotifLogs);
    $('#btnNotifRefresh').addEventListener('click', loadNotifLogs);
    $('#btnSaveSettings').addEventListener('click', async () => {
      await api('/settings', { method: 'PUT', body: {
        smtp_host: $('#setSmtpHost').value.trim(),
        smtp_port: +$('#setSmtpPort').value || null,
        smtp_user: $('#setSmtpUser').value.trim(),
        smtp_from: $('#setSmtpFrom').value.trim(),
        smtp_use_ssl: $('#setSmtpSsl').value === '1',
        notify_emails: $('#setEmails').value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        notify_on_failure: $('#setNotifyFail').checked,
        notify_on_success: $('#setNotifyOk').checked,
      } });
      toast('通知配置已保存', true);
    });
    $('#btnNewBot').addEventListener('click', () => openBotForm(null));
    /* AI */
    $('#btnNewAi').addEventListener('click', () => openAiForm(null));
    /* 弹窗 */
    $('#fmCancel').addEventListener('click', closeForm);
    $('#fmSave').addEventListener('click', () => { if (fmSave) fmSave(); });
  }

  async function init() {
    renderSidebar('/api-test');
    bind();
    let start = (location.hash || '').replace('#', '');
    if (PANELS.indexOf(start) < 0) start = 'dashboard';
    switchTab(start);
    $('#reqMethod').innerHTML = Object.keys(METHOD_COLOR).map(m => `<option>${m}</option>`).join('');
    try {
      await reloadTreeData();
      await loadDashboard();
    } catch (e) {
      toast('接口测试模块加载失败: ' + e.message, false);
    }
    setInterval(() => { if (!$('#panel-dashboard').hidden) loadDashboard(); }, 15000);
  }

  document.addEventListener('DOMContentLoaded', init);
  return { init };
})();
