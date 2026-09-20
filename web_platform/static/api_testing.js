/* 接口测试（testhub_platform 功能移植版）· 前端工作台
   ------------------------------------------------------------------
   标签页：接口管理（项目/集合/请求树 + 调试编辑器 + 历史） /
           测试套件（编排 + 执行 + 记录）/ 定时任务（CRUD + 日志）/ 环境与通知。
   数据全部走 /api-testing/api/* REST 端点；本文件不写业务规则，只做交互。 */
'use strict';

const AT = (function () {
  const API = '/api-testing/api';
  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  const state = {
    projects: [], collections: [], requests: [], envs: [],
    suites: [], tasks: [], selReqId: null, selSuiteId: null,
  };

  async function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
    const res = await fetch(API + path, opts);
    const d = await res.json().catch(() => ({ ok: false, msg: '响应解析失败' }));
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

  /* ---------------- 通用小表单弹窗 ---------------- */
  let fmSave = null;
  function openForm(title, bodyHtml, onSave) {
    $('#fmTitle').textContent = title;
    $('#fmBody').innerHTML = bodyHtml;
    $('#fmCancel').style.display = '';            // 复位：展示型弹窗会隐藏取消/改保存文案
    $('#fmSave').textContent = '保存';
    $('#formMask').classList.add('show');
    fmSave = onSave;
  }
  function closeForm() { $('#formMask').classList.remove('show'); fmSave = null; }
  function fmField(label, id, value, type) {
    return `<div class="field mt"><label>${esc(label)}</label>` +
      `<input type="${type || 'text'}" id="${id}" value="${esc(value == null ? '' : value)}"></div>`;
  }
  function fmSelect(label, id, options, value) {
    return `<div class="field mt"><label>${esc(label)}</label><select id="${id}">` +
      options.map(o => `<option value="${esc(o[0])}" ${String(o[0]) === String(value) ? 'selected' : ''}>${esc(o[1])}</option>`).join('') +
      '</select></div>';
  }

  /* ---------------- 统计条 ---------------- */
  async function loadDashboard() {
    try {
      const d = (await api('/dashboard')).data;
      const rate = d.success_rate == null ? '—' : d.success_rate + '%';
      $('#dashStats').innerHTML = [
        ['接口项目', d.projects, ''], ['API 请求', d.requests, 's-blue'],
        ['测试套件', d.suites, ''], ['执行请求次数', d.request_total, ''],
        ['请求成功率', rate, d.success_rate == null ? '' : (d.success_rate >= 90 ? 's-green' : 's-red')],
        ['激活定时任务', d.tasks_active, 's-slate'],
      ].map(([label, num, cls]) =>
        `<div class="stat ${cls}"><div class="num">${esc(num)}</div><div class="label">${esc(label)}</div>` +
        `<div class="bgico"></div></div>`).join('');
    } catch (e) { /* 统计失败不打断 */ }
  }

  /* ---------------- 二级菜单（左侧：概览/接口管理/测试套件/定时任务/环境与通知） ---------------- */
  const PANELS = ['overview', 'requests', 'suites', 'tasks', 'envs'];
  /* 面板名 → 顶部面包屑第三级文案 */
  const PANEL_NAMES = { overview: '概览', requests: '接口管理', suites: '测试套件', tasks: '定时任务', envs: '环境与通知' };
  function switchTab(name) {
    if (PANELS.indexOf(name) < 0) name = 'requests';
    document.querySelectorAll('#subnav a').forEach(a =>
      a.classList.toggle('on', a.dataset.panel === name));
    PANELS.forEach(t => { const el = $('#panel-' + t); if (el) el.hidden = (t !== name); });
    if (window.setCrumbSub) setCrumbSub(PANEL_NAMES[name]);
    history.replaceState(null, '', '#' + name);
  }

  /* ---------------- 接口管理：树 ---------------- */
  async function reloadAll() {
    const [p, c, r, e] = await Promise.all([
      api('/projects'), api('/collections'), api('/requests'), api('/environments')]);
    state.projects = p.data; state.collections = c.data;
    state.requests = r.data; state.envs = e.data;
    renderTree(); renderSuiteSelectors(); renderEnvTable();
  }

  function renderTree() {
    const kw = ($('#apiSearch').value || '').trim().toLowerCase();
    const box = $('#apiTree');
    if (!state.projects.length) { box.innerHTML = '<div class="empty">还没有项目 —— 点「新建项目」开始</div>'; return; }
    box.innerHTML = state.projects.map(proj => {
      const cols = state.collections.filter(c => c.project_id === proj.id);
      let html = `<div class="t-proj"><b>${esc(proj.name)}</b>` +
        `<span class="mockbadge">项目</span></div>`;
      const colGroups = cols.map(col => {
        const reqs = state.requests.filter(r =>
          r.collection_id === col.id &&
          (!kw || (r.name + r.url + r.method).toLowerCase().includes(kw)));
        if (kw && !reqs.length) return '';
        return `<div class="t-coll">📁 ${esc(col.name)}</div>` +
          reqs.map(r => reqRow(r)).join('');
      }).join('');
      // 未归集的请求
      const loose = state.requests.filter(r =>
        r.project_id === proj.id && !r.collection_id &&
        (!kw || (r.name + r.url + r.method).toLowerCase().includes(kw)));
      html += colGroups + loose.map(r => reqRow(r)).join('');
      return html;
    }).join('');
    box.querySelectorAll('.t-req').forEach(el => {
      el.addEventListener('click', () => selectRequest(+el.dataset.id));
    });
  }
  const reqRow = (r) =>
    `<div class="t-req ${r.id === state.selReqId ? 'sel' : ''}" data-id="${r.id}">` +
    mBadge(r.method) + `<span class="t-name" title="${esc(r.url)}">${esc(r.name)}</span></div>`;

  function currentReq() { return state.requests.find(r => r.id === state.selReqId); }

  /* ---------------- 请求编辑器 ---------------- */
  /* testhub Params/Headers 同款表格行：启用勾选 + Key + Value + 描述 + 删除 */
  const kvRow = (k, v, en, desc) =>
    `<div class="kvrow"><input type="checkbox" class="en" title="启用" ${en === false ? '' : 'checked'}>` +
    `<input type="text" class="k" placeholder="Key" value="${esc(k)}">` +
    `<input type="text" class="v" placeholder="Value" value="${esc(v)}">` +
    `<input type="text" class="d" placeholder="描述（仅备注）" value="${esc(desc == null ? '' : desc)}">` +
    `<button type="button" class="kv-del" title="删除">×</button></div>`;

  function readKv(container) {
    const out = [];
    container.querySelectorAll('.kvrow').forEach(row => {
      const k = row.querySelector('.k').value.trim();
      /* Key 为空的行丢弃；启用勾选必须生效（此前版本勾选被忽略——已修） */
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
      // 一个音视频断言行：选对象（音频/视频）+ 格式 + 时长 + 有无声音；视频多一个分辨率。
      // 旧数据（media_video / media_audio / media_volume / media_stream）打开时归一成 media_check。
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
      `<select class="a-type">${ASSERT_TYPES.map(t =>
        `<option value="${t[0]}" ${a.type === t[0] ? 'selected' : ''}>${t[1]}</option>`).join('')}</select>` +
      `<input type="text" class="a-extra1" placeholder="JSONPath / 头名（按类型）" value="${esc(a.type === 'header' ? (a.header_name || '') : (a.json_path || ''))}">` +
      `<input type="text" class="a-expected" placeholder="期望值" value="${esc(a.expected == null ? '' : a.expected)}">` +
      `<button type="button" class="kv-del" title="删除">×</button></div>`;
  };
  function readRow(row) {
    // data-type 是这一行"当前渲染结构"对应的类型：切换类型时 select 已变，
    // 必须按原类型解析旧字段，否则会去读新类型才有的输入框（null.value 报错）
    const type = row.dataset.type || row.querySelector('.a-type').value;
    if (MEDIA_TYPES.indexOf(type) >= 0) {
      // 统一落成 media_check（旧类型打开即归一，保存时完成迁移）
      const mediaType = row.querySelector('.a-media').value;
      const a = { name: 'media_check', type: 'media_check', media_type: mediaType };
      const codec = row.querySelector('.a-expected').value.trim();
      if (codec) a.codec = codec;
      const dur = row.querySelector('.a-extra1').value.trim();
      if (dur) {
        const [mn, mx] = dur.split('-');
        if (mn) a.duration_min = mn;
        if (mx) a.duration_max = mx;
      }
      if (mediaType === 'video') {                    // 音频跳过分辨率
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
    const a = { name: type, type, expected: expected };
    if (type === 'json_path') a.json_path = extra;
    if (type === 'header') { a.header_name = extra; a.expected_value = expected; }
    return a;
  }
  function readAssertions() {
    return Array.from($('#reqAssertions').querySelectorAll('.assertrow')).map(readRow);
  }

  /* ---------------- 参数 Tab ---------------- */
  function switchRtab(name) {
    document.querySelectorAll('.reqtabs a').forEach(a =>
      a.classList.toggle('on', a.dataset.rtab === name));
    ['params', 'headers', 'body', 'asserts', 'history'].forEach(t => {
      const el = $('#rtab-' + t); if (el) el.hidden = (t !== name);
    });
    if (name === 'history' && state.selReqId) loadHistory().catch(() => {});
  }

  function fillCollectionSelect(req) {
    const opts = [['', '— 无集合 —']]
      .concat(state.collections.filter(c => !req || !req.project_id || c.project_id === req.project_id)
        .map(c => [c.id, c.name]));
    $('#reqCollection').innerHTML = opts.map(o =>
      `<option value="${esc(o[0])}" ${req && req.collection_id === o[0] ? 'selected' : ''}>${esc(o[1])}</option>`).join('');
  }

  function openEditor(req) {
    $('#reqWelcome').style.display = 'none';
    $('#reqEditor').style.display = '';
    $('#respArea').style.display = 'none';
    fillCollectionSelect(req);
    $('#reqName').value = req ? req.name : '';
    $('#reqUrl').value = req ? req.url : '';
    $('#reqMethod').innerHTML = Object.keys(METHOD_COLOR).map(m =>
      `<option ${req && req.method === m ? 'selected' : ''}>${m}</option>`).join('');
    const hs = (req ? req.headers : []) || [];
    $('#reqHeaders').innerHTML = (hs.length ? hs : [{ key: '', value: '', enabled: true }])
      .map(h => kvRow(h.key, h.value, h.enabled, h.description)).join('');
    /* params：新数组格式 [{key,value,description,enabled}]；旧对象格式 {k:v} 打开时转数组 */
    const rawPs = (req ? req.params : null) || [];
    const ps = Array.isArray(rawPs)
      ? rawPs.map(p => [p.key, p.value, p.enabled, p.description])
      : Object.entries(rawPs).map(([k, v]) => [k, v, true, '']);
    $('#reqParams').innerHTML = (ps.length ? ps : [['', '', true, '']])
      .map(([k, v, en, d]) => kvRow(k, v, en, d)).join('');
    const as = (req ? req.assertions : []) || [];
    $('#reqAssertions').innerHTML = (as.length ? as : []).map(assertRow).join('') || assertRow({ type: 'status_code', expected: '200' });
    const bt = (req && req.body && req.body.type) || 'none';
    $('#reqBodyType').value = bt;
    $('#reqBody').value = bt === 'none' ? '' :
      (typeof (req.body || {}).data === 'string' ? (req.body || {}).data : JSON.stringify((req.body || {}).data || '', null, 2));
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
    /* params 落数组格式（含描述与启用），testhub Params 表格同构 */
    const params = readKv($('#reqParams')).map(p =>
      ({ key: p.key, value: p.value, description: p.description, enabled: p.enabled }));
    const col = state.collections.find(c => c.id === +$('#reqCollection').value);
    const proj = col ? state.projects.find(p => p.id === col.project_id) : currentReq() && currentReq().project_id;
    return {
      name: $('#reqName').value.trim() || '未命名接口',
      method: $('#reqMethod').value, url: $('#reqUrl').value.trim(),
      headers: readKv($('#reqHeaders')), params,
      body: { type: bodyType, data: bodyData },
      assertions: readAssertions(),
      collection_id: col ? col.id : null,
      project_id: (col ? col.project_id : null) || (currentReq() && currentReq().project_id) ||
        (state.projects[0] ? state.projects[0].id : null),
    };
  }

  async function saveRequest() {
    const req = currentReq();
    const payload = collectRequest();
    if (req) {
      await api('/requests/' + req.id, { method: 'PUT', body: payload });
      Object.assign(req, payload);
    } else {
      const d = (await api('/requests', { method: 'POST', body: payload })).data;
      state.requests.push(d); state.selReqId = d.id;
    }
    toast('已保存', true); renderTree();
  }

  async function sendRequest() {
    const req = currentReq();
    const activeEnv = state.envs.find(e => e.is_active);
    $('#respArea').style.display = '';
    $('#respBody').textContent = '发送中…';
    try {
      let overrides = collectRequest();
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

  /* ---------------- 导入 cURL（testhub「导入」） ---------------- */
  function parseCurl(text) {
    /* 解析常用 curl 形式：-X/--request、-H/--header、-d/--data/--data-raw/--data-binary、URL */
    const s = text.replace(/\\\n/g, ' ').trim();
    const out = { method: 'GET', url: '', headers: [], body: '' };
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
      } else if (!t.startsWith('-') && !out.url && /^https?:\/\//.test(t)) { out.url = t; }
    }
    if (bodyFlags) out.method = out.method === 'GET' ? 'POST' : out.method;
    if (!out.url) throw new Error('未识别到 URL（需以 http(s):// 开头）');
    return out;
  }

  function importCurl() {
    openForm('导入 cURL 命令',
      `<div class="field mt"><label>粘贴 curl 命令（识别 -X / -H / -d 与 URL）</label>` +
      `<textarea id="ciText" rows="7" placeholder="curl -X POST 'http://...' -H 'Content-Type: application/json' -d '{...}'"></textarea></div>`,
      async () => {
        const c = parseCurl($('#ciText').value);
        closeForm();
        state.selReqId = null;                     // 导入进新建编辑器，确认后再保存
        renderTree();
        openEditor(null);
        $('#reqMethod').value = c.method;
        $('#reqUrl').value = c.url;
        $('#reqName').value = '导入的接口';
        $('#reqHeaders').innerHTML = (c.headers.length ? c.headers : [{ key: '', value: '', enabled: true }])
          .map(h => kvRow(h.key, h.value, h.enabled, h.description)).join('');
        if (c.body) {
          $('#reqBodyType').value = 'json';
          try { $('#reqBody').value = JSON.stringify(JSON.parse(c.body), null, 2); }
          catch (e) { $('#reqBodyType').value = 'raw'; $('#reqBody').value = c.body; }
        }
        toast('已解析，确认后点「保存」', true);
      });
  }

  /* ---------------- 生成代码（testhub「生成代码」：cURL / Python） ---------------- */
  function genCode() {
    let r;
    try { r = collectRequest(); } catch (e) { return toast(e.message, false); }
    const q = (s) => "'" + String(s == null ? '' : s).replace(/'/g, `'\\''`) + "'";
    const r0 = r.url;
    /* query 参数拼进 url */
    const enabledParams = r.params.filter(p => p.enabled !== false);
    const curlUrl = enabledParams.length
      ? r0 + (r0.includes('?') ? '&' : '?') + enabledParams.map(p => encodeURIComponent(p.key) + '=' + encodeURIComponent(p.value)).join('&')
      : r0;
    const curlHeaders = r.headers.filter(h => h.enabled !== false).map(h => `  -H ${q(h.key + ': ' + h.value)}`).join(' \\\n');
    let curl = `curl -X ${r.method} ${q(curlUrl)}`;
    if (curlHeaders) curl += ` \\\n${curlHeaders}`;
    if (r.body.type !== 'none' && r.body.data) curl += ` \\\n  -d ${q(typeof r.body.data === 'string' ? r.body.data : JSON.stringify(r.body.data))}`;
    const pyHeaders = r.headers.filter(h => h.enabled !== false);
    const pyLines = [
      'import requests',
      '',
      `url = ${q(curlUrl)}`,
      `headers = {${pyHeaders.map(h => `${q(h.key)}: ${q(h.value)}`).join(', ')}}`,
      r.body.type === 'json' && r.body.data ? `json_payload = ${JSON.stringify(r.body.data, null, 2)}` : null,
      '',
      r.body.type === 'json' && r.body.data ? 'resp = requests.request(' + q(r.method) + ', url, headers=headers, json=json_payload)'
        : r.body.type !== 'none' && r.body.data ? 'resp = requests.request(' + q(r.method) + ', url, headers=headers, data=' + q(r.body.data) + ')'
        : 'resp = requests.request(' + q(r.method) + ', url, headers=headers)',
      'print(resp.status_code, resp.text)',
    ].filter(x => x !== null).join('\n');
    openForm('生成代码',
      `<div class="field mt"><label>cURL</label><textarea id="gcCurl" rows="6" readonly>${esc(curl)}</textarea></div>` +
      `<div class="field mt"><label>Python (requests)</label><textarea id="gcPy" rows="8" readonly>${esc(pyLines)}</textarea></div>`,
      null);
    $('#fmSave').textContent = '关闭';
    fmSave = closeForm; $('#fmCancel').style.display = 'none';
  }

  async function selectRequest(id) {
    state.selReqId = id;
    renderTree();
    openEditor(currentReq());
  }

  /* ---------------- 测试套件 ---------------- */
  function renderSuiteSelectors() {
    const projOpts = state.projects.map(p => [p.id, p.name]);
    $('#suiteProjectSel').innerHTML = projOpts.map(o => `<option value="${o[0]}">${esc(o[1])}</option>`).join('') || '<option>—</option>';
    const envOpts = [['', '套件默认环境']].concat(state.envs.map(e => [e.id, e.name + (e.is_active ? '（激活）' : '')]));
    $('#suiteEnvSel').innerHTML = envOpts.map(o => `<option value="${esc(o[0])}">${esc(o[1])}</option>`).join('');
  }

  async function loadSuites() {
    state.suites = (await api('/suites')).data;
    $('#suiteTbody').innerHTML = state.suites.map(s => {
      const env = state.envs.find(e => e.id === s.environment_id);
      return `<tr><td><b>${esc(s.name)}</b><div class="muted">${esc(s.description || '')}</div></td>` +
        `<td>${(s.suite_requests || []).length}</td>` +
        `<td>${env ? esc(env.name) : '<span class="muted">默认</span>'}</td>` +
        `<td><div class="ops"><button class="ghost mini" data-open="${s.id}">编排 / 记录</button>` +
        `<button class="mini danger-ghost" data-del="${s.id}">删除</button></div></td></tr>`;
    }).join('') || '<tr><td colspan="4" class="empty">暂无套件 —— 选项目后「新建套件」</td></tr>';
    $('#suiteTbody').querySelectorAll('[data-open]').forEach(b =>
      b.addEventListener('click', () => openSuite(+b.dataset.open)));
    $('#suiteTbody').querySelectorAll('[data-del]').forEach(b =>
      b.addEventListener('click', async () => {
        if (!(await confirmModal('删除套件', '删除套件及其定时任务，执行记录保留。确定？'))) return;
        await api('/suites/' + b.dataset.del, { method: 'DELETE' });
        $('#suiteDetail').style.display = 'none'; state.selSuiteId = null;
        loadSuites(); toast('已删除', true);
      }));
  }

  async function openSuite(id) {
    const s = state.suites.find(x => x.id === id);
    if (!s) return;
    state.selSuiteId = id;
    $('#suiteDetail').style.display = '';
    $('#suiteDetailTitle').textContent = '套件：' + s.name;
    $('#suiteEnvSel').value = s.environment_id || '';
    const srs = s.suite_requests || [];
    $('#suiteReqTbody').innerHTML = srs.map((sr, i) => {
      const r = state.requests.find(x => x.id === sr.request_id) || { name: '已删除', method: '-', url: '-' };
      return `<tr><td>${i + 1}</td><td>${esc(r.name)}</td><td>${mBadge(r.method)}</td>` +
        `<td class="muted" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.url)}</td>` +
        `<td><input type="checkbox" data-tg="${i}" ${sr.enabled ? 'checked' : ''}></td>` +
        `<td><div class="ops"><button class="ghost mini" data-up="${i}" ${i === 0 ? 'disabled' : ''}>↑</button>` +
        `<button class="ghost mini" data-down="${i}" ${i === srs.length - 1 ? 'disabled' : ''}>↓</button>` +
        `<button class="mini danger-ghost" data-rm="${i}">移除</button></div></td></tr>`;
    }).join('') || '<tr><td colspan="6" class="empty">还没有请求 —— 下方选择添加</td></tr>';
    const allReqs = state.requests.filter(r => !srs.some(x => x.request_id === r.id));
    $('#suiteAddReqSel').innerHTML = allReqs.map(r =>
      `<option value="${r.id}">${esc(r.method + ' ' + r.name)}</option>`).join('') || '<option>全部请求已添加</option>';
    // 绑定行内操作
    $('#suiteReqTbody').querySelectorAll('[data-tg]').forEach(el => el.addEventListener('change', () => updSuiteReq(+el.dataset.tg, { enabled: el.checked })));
    $('#suiteReqTbody').querySelectorAll('[data-up]').forEach(el => el.addEventListener('click', () => moveSuiteReq(+el.dataset.up, -1)));
    $('#suiteReqTbody').querySelectorAll('[data-down]').forEach(el => el.addEventListener('click', () => moveSuiteReq(+el.dataset.down, 1)));
    $('#suiteReqTbody').querySelectorAll('[data-rm]').forEach(el => el.addEventListener('click', () => rmSuiteReq(+el.dataset.rm)));
    loadExecutions(id);
  }

  async function updSuiteReq(idx, patch) {
    const s = state.suites.find(x => x.id === state.selSuiteId);
    s.suite_requests[idx] = { ...s.suite_requests[idx], ...patch };
    await api('/suites/' + s.id, { method: 'PUT', body: { suite_requests: s.suite_requests } });
    loadSuites();
  }
  async function moveSuiteReq(idx, delta) {
    const s = state.suites.find(x => x.id === state.selSuiteId);
    const srs = s.suite_requests;
    const j = idx + delta;
    [srs[idx], srs[j]] = [srs[j], srs[idx]];
    srs.forEach((x, i) => x.order = i + 1);
    await api('/suites/' + s.id, { method: 'PUT', body: { suite_requests: srs } });
    openSuite(s.id);
  }
  async function rmSuiteReq(idx) {
    const s = state.suites.find(x => x.id === state.selSuiteId);
    s.suite_requests.splice(idx, 1);
    s.suite_requests.forEach((x, i) => x.order = i + 1);
    await api('/suites/' + s.id, { method: 'PUT', body: { suite_requests: s.suite_requests } });
    openSuite(s.id); loadSuites();
  }

  async function loadExecutions(sid) {
    const d = (await api('/executions?suite=' + sid + '&page_size=20')).data;
    $('#execTbody').innerHTML = d.results.map(x => {
      const cls = x.status === 'COMPLETED' ? 'st-PASSED' : x.status === 'RUNNING' ? 'st-RUNNING' : 'st-FAILED';
      return `<tr><td>${x.id}</td><td><span class="status ${cls}">${x.status}</span></td>` +
        `<td class="muted">${fmtTime(x.start_time)}</td>` +
        `<td>${x.passed_requests}/${x.total_requests}</td>` +
        `<td class="muted">${esc(x.executed_by)}</td>` +
        `<td><button class="ghost mini" data-see="${x.id}">结果</button></td></tr>`;
    }).join('') || '<tr><td colspan="6" class="empty">暂无执行记录</td></tr>';
    $('#execTbody').querySelectorAll('[data-see]').forEach(b =>
      b.addEventListener('click', () => showExecution(+b.dataset.see)));
  }

  async function showExecution(eid) {
    const x = (await api('/executions/' + eid)).data;
    const rows = (x.results || []).map(r => {
      const rs = r.assertions_results || [];
      const ok = rs.filter(a => a.passed).length;
      return `<tr><td>${r.passed ? '<span class="num-ok">✓</span>' : '<span class="num-bad">✗</span>'} ${esc(r.name)}</td>` +
        `<td>${r.status_code != null ? r.status_code : '-'}</td>` +
        `<td>${r.response_time != null ? r.response_time + 'ms' : '-'}</td>` +
        `<td>${rs.length ? ok + '/' + rs.length : '-'}</td>` +
        `<td class="muted" style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.error || '')}</td></tr>`;
    }).join('');
    openForm('执行 #' + eid + ' · ' + x.passed_requests + '/' + x.total_requests + ' 通过',
      `<div class="tblwrap"><table><thead><tr><th>请求</th><th>状态码</th><th>耗时</th><th>断言</th><th>错误</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div>`, null);
    $('#fmSave').textContent = '关闭';
    fmSave = closeForm; $('#fmCancel').style.display = 'none';
  }

  /* ---------------- 定时任务 ---------------- */
  async function loadTasks() {
    state.tasks = (await api('/tasks')).data;
    $('#taskTbody').innerHTML = state.tasks.map(t => {
      const target = t.task_type === 'TEST_SUITE'
        ? ((state.suites.find(s => s.id === t.suite_id) || {}).name || '#' + t.suite_id)
        : ((state.requests.find(r => r.id === t.request_id) || {}).name || '#' + t.request_id);
      const stCls = t.status === 'ACTIVE' ? 'st-PASSED' : t.status === 'PAUSED' ? 'st-PENDING' : 'st-FAILED';
      const trig = t.trigger_type === 'CRON' ? ('CRON ' + t.cron_expression)
        : t.trigger_type === 'INTERVAL' ? ('每 ' + t.interval_seconds + ' 秒') : ('单次 ' + fmtTime(t.execute_at));
      return `<tr><td><b>${esc(t.name)}</b><div class="muted">${esc(target)}</div></td>` +
        `<td>${t.task_type === 'TEST_SUITE' ? '套件执行' : '单请求'}</td>` +
        `<td class="muted">${esc(trig)}</td><td class="muted">${fmtTime(t.next_run_time)}</td>` +
        `<td><span class="status ${stCls}">${t.status}</span></td>` +
        `<td>${t.successful_runs}/${t.total_runs}</td>` +
        `<td><div class="ops">` +
        `<button class="ghost mini" data-run="${t.id}">立即执行</button>` +
        (t.status === 'ACTIVE'
          ? `<button class="ghost mini" data-pause="${t.id}">暂停</button>`
          : `<button class="ghost mini" data-act="${t.id}">激活</button>`) +
        `<button class="mini danger-ghost" data-del="${t.id}">删除</button></div></td></tr>`;
    }).join('') || '<tr><td colspan="7" class="empty">暂无定时任务</td></tr>';
    $('#taskTbody').querySelectorAll('[data-run]').forEach(b => b.addEventListener('click', async () => {
      await api('/tasks/' + b.dataset.run + '/run-now', { method: 'POST' });
      toast('已触发，稍后刷新查看日志', true); setTimeout(loadLogs, 1500);
    }));
    $('#taskTbody').querySelectorAll('[data-pause]').forEach(b => b.addEventListener('click', async () => {
      await api('/tasks/' + b.dataset.pause + '/pause', { method: 'POST' }); loadTasks();
    }));
    $('#taskTbody').querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
      await api('/tasks/' + b.dataset.act + '/activate', { method: 'POST' }); loadTasks();
    }));
    $('#taskTbody').querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      if (!(await confirmModal('删除任务', '任务及其执行日志将删除，确定？'))) return;
      await api('/tasks/' + b.dataset.del, { method: 'DELETE' }); loadTasks(); loadLogs();
    }));
  }

  async function loadLogs() {
    const d = (await api('/task-logs?page_size=20')).data;
    $('#taskLogTbody').innerHTML = d.results.map(l => {
      const cls = l.status === 'COMPLETED' ? 'st-PASSED' : l.status === 'RUNNING' ? 'st-RUNNING' : l.status === 'PENDING' ? 'st-PENDING' : 'st-FAILED';
      return `<tr><td>${esc(l.task_name)}</td><td class="muted">${l.trigger === 'manual' ? '手动' : l.trigger === 'scheduler' ? '调度' : esc(l.trigger)}</td>` +
        `<td><span class="status ${cls}">${l.status}</span></td>` +
        `<td class="muted">${fmtTime(l.start_time)}</td><td class="muted">${fmtTime(l.end_time)}</td>` +
        `<td class="muted" style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(l.error_message || '')}</td></tr>`;
    }).join('') || '<tr><td colspan="6" class="empty">暂无日志</td></tr>';
  }

  function openTaskForm(task) {
    const isEdit = !!task;
    const suiteOpts = [['', '— 选择套件 —']].concat(state.suites.map(s => [s.id, s.name]));
    const reqOpts = [['', '— 选择请求 —']].concat(state.requests.map(r => [r.id, r.method + ' ' + r.name]));
    const envOpts = [['', '默认（激活环境）']].concat(state.envs.map(e => [e.id, e.name]));
    openForm(isEdit ? '编辑定时任务' : '新建定时任务',
      fmField('任务名称', 'tfName', task && task.name) +
      fmSelect('任务类型', 'tfType', [['TEST_SUITE', '测试套件执行'], ['API_REQUEST', 'API 请求执行']], task && task.task_type) +
      `<div id="tfSuiteWrap">${fmSelect('测试套件', 'tfSuite', suiteOpts, task && task.suite_id)}</div>` +
      `<div id="tfReqWrap" style="display:none">${fmSelect('API 请求', 'tfReq', reqOpts, task && task.request_id)}</div>` +
      fmSelect('执行环境', 'tfEnv', envOpts, task && task.environment_id) +
      fmSelect('触发器', 'tfTrigger', [['CRON', 'Cron 表达式'], ['INTERVAL', '固定间隔'], ['ONCE', '单次执行']], task && task.trigger_type || 'INTERVAL') +
      `<div id="tfCronWrap" style="display:none">${fmField('Cron 表达式（分 时 日 月 周）', 'tfCron', task && task.cron_expression, 'text')}</div>` +
      `<div id="tfIntervalWrap">${fmField('间隔秒数', 'tfInterval', task && task.interval_seconds || 60, 'number')}</div>` +
      `<div id="tfOnceWrap" style="display:none">${fmField('执行时间（epoch 秒）', 'tfOnce', task && task.execute_at, 'number')}</div>`,
      async () => {
        const payload = {
          name: $('#tfName').value.trim(),
          task_type: $('#tfType').value,
          trigger_type: $('#tfTrigger').value,
          suite_id: +$('#tfSuite').value || null,
          request_id: +$('#tfReq').value || null,
          environment_id: +$('#tfEnv').value || null,
          cron_expression: $('#tfCron').value.trim(),
          interval_seconds: +$('#tfInterval').value || null,
          execute_at: +$('#tfOnce').value || null,
          status: (task && task.status) || 'ACTIVE',
        };
        if (isEdit) await api('/tasks/' + task.id, { method: 'PUT', body: payload });
        else await api('/tasks', { method: 'POST', body: payload });
        closeForm(); loadTasks(); loadDashboard();
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

  /* ---------------- 环境 ---------------- */
  function renderEnvTable() {
    $('#envTbody').innerHTML = state.envs.map(e =>
      `<tr><td><b>${esc(e.name)}</b></td><td>${e.scope === 'GLOBAL' ? '全局' : '局部'}</td>` +
      `<td class="muted">${Object.entries(e.variables || {}).map(([k, v]) => k + '=' + v).join('、') || '—'}</td>` +
      `<td>${e.is_active ? '<span class="status st-PASSED">激活</span>' : '<button class="ghost mini" data-act="' + e.id + '">激活</button>'}</td>` +
      `<td><div class="ops"><button class="ghost mini" data-edit="${e.id}">编辑</button>` +
      `<button class="mini danger-ghost" data-del="${e.id}">删除</button></div></td></tr>`).join('') ||
      '<tr><td colspan="5" class="empty">暂无环境</td></tr>';
    $('#envTbody').querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
      await api('/environments/' + b.dataset.act + '/activate', { method: 'POST' });
      reloadAll(); toast('已激活', true);
    }));
    $('#envTbody').querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      if (!(await confirmModal('删除环境', '确定删除该环境？'))) return;
      await api('/environments/' + b.dataset.del, { method: 'DELETE' }); reloadAll();
    }));
    $('#envTbody').querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => {
      const e = state.envs.find(x => x.id === +b.dataset.edit);
      const varPairs = Object.entries(e.variables || {});
      openForm('编辑环境',
        fmField('环境名称', 'efName', e.name) +
        fmSelect('作用域', 'efScope', [['LOCAL', '局部环境变量'], ['GLOBAL', '全局环境变量']], e.scope) +
        `<div class="field mt"><label>变量（每行 key=value）</label>` +
        `<textarea id="efVars" rows="6">${esc(varPairs.map(([k, v]) => k + '=' + v).join('\n'))}</textarea></div>`,
        async () => {
          const variables = {};
          $('#efVars').value.split('\n').forEach(line => {
            const i = line.indexOf('=');
            if (i > 0) variables[line.slice(0, i).trim()] = line.slice(i + 1).trim();
          });
          await api('/environments/' + e.id, { method: 'PUT', body: { name: $('#efName').value.trim(), scope: $('#efScope').value, variables } });
          closeForm(); reloadAll(); toast('已保存', true);
        });
    }));
  }

  function openEnvForm() {
    openForm('新建环境',
      fmField('环境名称', 'efName', '') +
      fmSelect('作用域', 'efScope', [['LOCAL', '局部环境变量'], ['GLOBAL', '全局环境变量']], 'LOCAL') +
      `<div class="field mt"><label>变量（每行 key=value）</label>` +
      `<textarea id="efVars" rows="6" placeholder="base_url=http://127.0.0.1:8080"></textarea></div>`,
      async () => {
        const variables = {};
        $('#efVars').value.split('\n').forEach(line => {
          const i = line.indexOf('=');
          if (i > 0) variables[line.slice(0, i).trim()] = line.slice(i + 1).trim();
        });
        await api('/environments', { method: 'POST', body: { name: $('#efName').value.trim(), scope: $('#efScope').value, variables } });
        closeForm(); reloadAll(); toast('已创建', true);
      });
  }

  /* ---------------- 通知设置 ---------------- */
  async function loadSettings() {
    const s = (await api('/settings')).data;
    $('#setWebhook').value = s.webhook_url || '';
    $('#setEmails').value = (s.notify_emails || []).join(', ');
    $('#setSmtpHost').value = s.smtp_host || '';
    $('#setSmtpPort').value = s.smtp_port || '';
    $('#setSmtpUser').value = s.smtp_user || '';
    $('#setNotifyFail').checked = !!s.notify_on_failure;
    $('#setNotifyOk').checked = !!s.notify_on_success;
  }
  async function saveSettings() {
    await api('/settings', {
      method: 'PUT', body: {
        webhook_url: $('#setWebhook').value.trim(),
        notify_emails: $('#setEmails').value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        smtp_host: $('#setSmtpHost').value.trim(),
        smtp_port: +$('#setSmtpPort').value || null,
        smtp_user: $('#setSmtpUser').value.trim(),
        notify_on_failure: $('#setNotifyFail').checked,
        notify_on_success: $('#setNotifyOk').checked,
      },
    });
    toast('通知设置已保存', true);
  }

  /* ---------------- 绑定 ---------------- */
  function bind() {
    /* 左侧二级菜单：图标注入 + 点击切换（与 AppUI 页 initRunPanels 同款交互） */
    document.querySelectorAll('#subnav a').forEach(a => {
      if (a.dataset.icon) a.insertAdjacentHTML('afterbegin', icon(a.dataset.icon, 18));
      a.addEventListener('click', e => { e.preventDefault(); switchTab(a.dataset.panel); });
    });
    $('#apiSearch').addEventListener('input', renderTree);
    /* 参数 Tab 切换 */
    document.querySelectorAll('.reqtabs a').forEach(a =>
      a.addEventListener('click', () => switchRtab(a.dataset.rtab)));
    $('#btnReqSave').addEventListener('click', () => saveRequest().catch(e => toast(e.message, false)));
    $('#btnReqSend').addEventListener('click', () => sendRequest().catch(e => toast(e.message, false)));
    $('#btnReqImport').addEventListener('click', importCurl);
    $('#btnReqCode').addEventListener('click', genCode);
    $('#btnAddHeader').addEventListener('click', () => $('#reqHeaders').insertAdjacentHTML('beforeend', kvRow('', '', true, '')));
    $('#btnAddParam').addEventListener('click', () => $('#reqParams').insertAdjacentHTML('beforeend', kvRow('', '', true, '')));
    $('#btnAddAssertion').addEventListener('click', () => $('#reqAssertions').insertAdjacentHTML('beforeend', assertRow()));
    // 切换断言类型时按新类型重渲染该行（media 行与普通行字段结构不同），保留已填值
    $('#reqAssertions').addEventListener('change', (e) => {
      const row = e.target.closest('.assertrow');
      if (!row) return;
      if (e.target.classList.contains('a-type')) {
        row.outerHTML = assertRow({ ...readRow(row), type: e.target.value });
        return;
      }
      // 音视频行：对象选「音频」时分辨率不适用（禁用并清空），选「视频」时恢复
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
    $('#btnNewRequest').addEventListener('click', () => { state.selReqId = null; renderTree(); openEditor(null); });
    $('#btnNewProject').addEventListener('click', () => openForm('新建项目',
      fmField('项目名称', 'pfName', '') + fmField('描述', 'pfDesc', ''), async () => {
        await api('/projects', { method: 'POST', body: { name: $('#pfName').value.trim(), description: $('#pfDesc').value.trim() } });
        closeForm(); reloadAll(); toast('已创建', true);
      }));
    $('#btnNewCollection').addEventListener('click', () => {
      if (!state.projects.length) return toast('请先创建项目', false);
      openForm('新建集合',
        fmField('集合名称', 'cfName', '') +
        fmSelect('所属项目', 'cfProj', state.projects.map(p => [p.id, p.name])), async () => {
          await api('/collections', { method: 'POST', body: { name: $('#cfName').value.trim(), project_id: +$('#cfProj').value } });
          closeForm(); reloadAll(); toast('已创建', true);
        });
    });
    // 套件
    $('#btnNewSuite').addEventListener('click', async () => {
      const pid = +($('#suiteProjectSel').value || 0);
      if (!pid) return toast('请先创建项目', false);
      const d = (await api('/suites', { method: 'POST', body: { name: '新套件 ' + new Date().toLocaleTimeString(), project_id: pid } })).data;
      await loadSuites(); openSuite(d.id); toast('套件已创建', true);
    });
    $('#btnSuiteAddReq').addEventListener('click', async () => {
      const rid = +$('#suiteAddReqSel').value;
      if (!rid || !state.selSuiteId) return;
      await api('/suites/' + state.selSuiteId + '/add-requests', { method: 'POST', body: { request_ids: [rid] } });
      const s = state.suites.find(x => x.id === state.selSuiteId);
      s.suite_requests = (await api('/suites')).data.find(x => x.id === s.id).suite_requests;
      openSuite(s.id); loadSuites();
    });
    $('#btnSuiteRun').addEventListener('click', async () => {
      if (!state.selSuiteId) return;
      const envId = +$('#suiteEnvSel').value || null;
      await api('/suites/' + state.selSuiteId + '/execute', { method: 'POST', body: { environment_id: envId } });
      toast('套件已开始执行，记录会实时刷新', true);
      setTimeout(() => loadExecutions(state.selSuiteId), 1200);
    });
    // 任务
    $('#btnNewTask').addEventListener('click', () => openTaskForm(null));
    $('#btnLogsRefresh').addEventListener('click', loadLogs);
    // 环境
    $('#btnNewEnv').addEventListener('click', openEnvForm);
    $('#btnSaveSettings').addEventListener('click', saveSettings);
    // 弹窗
    $('#fmCancel').addEventListener('click', closeForm);
    $('#fmSave').addEventListener('click', () => { if (fmSave) fmSave(); });
  }

  async function init() {
    renderSidebar('/api-test');
    bind();
    /* 初始面板：hash 深链优先，否则默认第一个（概览）——不恢复上次停留 */
    let start = (location.hash || '').replace('#', '');
    if (PANELS.indexOf(start) < 0) start = PANELS[0];
    switchTab(start);
    $('#reqMethod').innerHTML = Object.keys(METHOD_COLOR).map(m => `<option>${m}</option>`).join('');
    try {
      await reloadAll();
      await Promise.all([loadDashboard(), loadSuites(), loadTasks(), loadLogs(), loadSettings()]);
    } catch (e) {
      toast('接口测试模块加载失败: ' + e.message, false);
    }
    setInterval(loadDashboard, 15000);
  }

  document.addEventListener('DOMContentLoaded', init);
  return { init };
})();
