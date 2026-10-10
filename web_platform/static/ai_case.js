/* AI 用例生成 · 前端脚本
   面板：生成工作台（建任务/SSE/步骤审核） + 配置项（模型/提示词/Skill/项目与设备）
   约定与 app.js 一致：api()/postJson() 封装、#toast 轻提示、PlatformNav 面包屑 */
(function () {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.prototype.slice.call(document.querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  async function api(url, opts) {
    const res = await fetch(url, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
    const data = await res.json().catch(() => ({ ok: false, msg: '响应解析失败(' + res.status + ')' }));
    if (!res.ok && !data.msg) data.msg = 'HTTP ' + res.status;
    return data;
  }
  const postJson = (url, body) => api(url, { method: 'POST', body: JSON.stringify(body || {}) });
  const putJson = (url, body) => api(url, { method: 'PUT', body: JSON.stringify(body || {}) });

  function toast(msg, ok) {
    const t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.style.background = ok === false ? 'var(--bad)' : 'var(--dark)';
    t.style.opacity = '1';
    clearTimeout(t._h);
    t._h = setTimeout(() => { t.style.opacity = '0'; }, 2600);
  }

  const ACTION_LABEL = { launch: '启动', click: '点击', input: '输入', select: '选择' };
  const ASSERT_LABEL = { text_contains: '文案出现', text_gone: '文案不再出现', list_added: '列表新增', visual: '视觉断言' };
  const PAGE_PATH = '/ai-case';
  let curJob = null;     // 当前打开的任务
  let evtSource = null;  // SSE 连接
  let CFG = null;        // /config 结果（模型/提示词/Skill/项目/设备）
  let curShotTs = 0;

  function fmtTime(ts) {
    if (!ts) return '-';
    const d = new Date(ts * 1000);
    const p = (n) => String(n).padStart(2, '0');
    return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  /* ---------- 菜单栏：面板切换（平台约定：.submain .panel[hidden]） ---------- */
  function initPanels() {
    const links = $$('#subnav a[data-panel]');
    links.forEach((a) => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        links.forEach(x => x.classList.toggle('on', x === a));
        $('#panel-workbench').hidden = a.dataset.panel !== 'workbench';
        $('#panel-config').hidden = a.dataset.panel !== 'config';
        history.replaceState(null, '', a.getAttribute('href'));
      });
    });
    if (location.hash === '#config') links[1] && links[1].click();
  }

  /* ---------- 初始化 ---------- */
  async function init() {
    if (window.PlatformNav) PlatformNav.render(document.getElementById('sidebar'), PAGE_PATH);
    initPanels();
    await loadConfig();
    await loadRecent();
    bindCreate();
    bindObserve();
    bindConfig();
    $('#aicCancel').addEventListener('click', cancelJob);
  }

  async function loadConfig() {
    const d = await api('/api/ai-case/config');
    if (!d.ok) return;
    CFG = d;
    renderPhase();
    renderResolved();
    renderEntryModes();
    renderObserveTags();
    renderConfigPanel();
  }

  function renderPhase() {
    const m = CFG.model || {};
    const usingModel = m.enabled && m.base_url;
    const parser = (CFG.skills || {}).parser_mode;
    let txt;
    if (parser === 'rule') txt = '解析技能=仅规则（Skill 配置中设定）';
    else if (usingModel) txt = '模型解析已启用：' + (m.model || '未命名模型') + ' · 设备观察 · 独占锁';
    else txt = '设备观察 · 独占锁 · 解析器=规则兜底（未启用模型，去「配置项」开启）';
    $('#aicPhase').textContent = txt;
  }

  function defProject() {
    const skills = CFG.skills || {};
    return (CFG.ai_projects || []).find(p => p.id === skills.default_project_id) || null;
  }
  function defDevice() { return (CFG.skills || {}).default_device || ''; }

  function renderResolved() {
    const p = defProject(), dev = defDevice();
    $('#aicResolved').innerHTML = '目标项目：' +
      (p ? '<b>' + esc(p.name) + '</b> · <code style="font-size:11px">' + esc(p.app_package) + '</code>' : '—') +
      ' · 设备：' + (dev ? '<b>' + esc(dev) + '</b>' : '—') +
      '（在<a href="#config" id="gotoConfig">配置项</a>中修改）';
    const g = $('#gotoConfig');
    if (g) g.addEventListener('click', (e) => { e.preventDefault(); $$('#subnav a[data-panel]')[1].click(); });
  }

  function renderEntryModes() {
    const box = $('#aicEntryModes');
    box.innerHTML = '';
    (CFG.entry_modes || []).forEach((m, i) => {
      const lab = document.createElement('label');
      lab.className = 'aic-opt';
      lab.innerHTML = '<input type="radio" name="aicEntry" value="' + esc(m.value) + '"' +
        (i === 0 ? ' checked' : '') + '><span>' + esc(m.label) + '</span>';
      box.appendChild(lab);
    });
  }

  async function loadRecent() {
    const d = await api('/api/ai-case/jobs?limit=8');
    const box = $('#aicRecent');
    if (!d.ok || !(d.results || []).length) return;
    box.innerHTML = '';
    d.results.forEach((j) => {
      const btn = document.createElement('button');
      btn.className = 'aic-jobrow';
      btn.innerHTML = '<span class="jid">#' + j.id + '</span>' +
        '<span class="jtxt">' + esc(j.requirement.slice(0, 24)) + '</span>' +
        '<span class="aic-tag">' + esc(j.status) + '</span>';
      btn.addEventListener('click', () => openJob(j.id));
      box.appendChild(btn);
    });
  }

  /* ---------- 创建任务 ---------- */
  function bindCreate() {
    $('#aicCreate').addEventListener('click', async () => {
      const requirement = $('#aicReq').value.trim();
      const btn = $('#aicCreate');
      if (requirement.length < 5) return toast('需求描述太短：请描述测试场景与断言', false);
      btn.disabled = true; btn.textContent = '解析中…';
      const entry = document.querySelector('input[name="aicEntry"]:checked');
      const d = await postJson('/api/ai-case/jobs', {
        requirement: requirement,
        entry_mode: entry ? entry.value : 'ai_explore',
      });
      btn.disabled = false; btn.textContent = '分析需求';
      if (!d.ok) return toast(d.msg || '创建失败', false);
      toast('任务 #' + d.job.id + ' 创建成功');
      openJob(d.job.id);
      loadRecent();
    });
  }

  /* ---------- 任务展示（SSE 驱动） ---------- */
  function openJob(jid) {
    if (evtSource) { evtSource.close(); evtSource = null; }
    curJob = jid;
    evtSource = new EventSource('/api/ai-case/jobs/' + jid + '/events');
    evtSource.addEventListener('update', (e) => {
      try { renderJob(JSON.parse(e.data)); } catch (err) { /* 忽略坏帧 */ }
    });
    evtSource.onerror = () => { /* 断流自动重连；任务终态服务端会收流 */ };
  }

  function renderJob(job) {
    if (!job) return;
    const flow = job.flow_statuses || [];
    const curIdx = flow.indexOf(job.status);
    let statesHtml = flow.map((s) => {
      const name = s.replace('*', '');
      const locked = s.startsWith('*');
      const cls = name === job.status ? 'cur' : (curIdx >= 0 && flow.indexOf(s) >= 0 && flow.indexOf(s) < curIdx ? 'past' : (locked ? 'locked' : ''));
      return '<span class="st ' + cls + '">' + esc(name) + '</span>';
    }).join('');
    if (curIdx < 0) {   // 终态（已取消等）不在流程链上，红标单列
      statesHtml += '<span class="st" style="background:var(--bad);color:#fff;font-weight:600">' +
        esc(job.status) + '</span>';
    }
    $('#aicStates').innerHTML = statesHtml;

    $('#aicMeta').innerHTML =
      '<span>任务 <b>#' + job.id + '</b></span>' +
      '<span>项目 <b>' + esc(job.project_name || '-') + '</b></span>' +
      '<span>包名 <b>' + esc(job.app_package || '-') + '</b></span>' +
      '<span>设备 <b>' + esc(job.device || '-') + '</b></span>' +
      '<span>入口 <b>' + esc(job.entry_mode_label) + '</b></span>' +
      '<span>更新 <b>' + fmtTime(job.updated_at) + '</b></span>';

    const cbox = $('#aicClarify');
    const cls = job.clarifications || [];
    if (!cls.length) {
      cbox.innerHTML = '';
    } else {
      cbox.innerHTML = cls.map((c) => {
        if (c.answer) {
          return '<div class="aic-clarify"><h4>❓ ' + esc(c.question) + '</h4>' +
            '<span class="aic-tag ok">✓ ' + esc(c.answer) + '</span></div>';
        }
        return '<div class="aic-clarify"><h4>❓ ' + esc(c.question) + '</h4><p style="font-size:12px;color:var(--muted)">需求没写明的信息 AI 不编造，请确认：</p>' +
          '<div class="opts">' + (c.options || []).map((o) =>
            '<button data-qid="' + esc(c.qid) + '" data-opt="' + esc(o) + '">' + esc(o) + '</button>').join('') +
          '</div></div>';
      }).join('');
      cbox.querySelectorAll('.opts button').forEach((b) => {
        b.addEventListener('click', () => answerClarify(b.dataset.qid, b.dataset.opt, b));
      });
    }

    const ev = $('#aicEvents');
    ev.innerHTML = (job.events || []).map((e) => {
      const d = new Date(e.t * 1000);
      const p = (n) => String(n).padStart(2, '0');
      return '<div class="ln"><span class="tm">' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()) +
        '</span><span class="ty ' + esc(e.type) + '">[' + esc(e.type) + ']</span><span>' + esc(e.msg) + '</span></div>';
    }).join('');
    ev.scrollTop = ev.scrollHeight;
    $('#aicCancel').hidden = false;
    $('#aicCancel').disabled = false;

    const a = job.analysis;
    const abox = $('#aicAnalysis');
    if (!a) { abox.innerHTML = '<p class="aic-empty">解析中…</p>'; return; }
    let html = '<div class="aic-goal">' + esc(a.goal || '（未识别出测试目标）') + '</div>';
    html += '<div class="aic-tags">' +
      '<span class="aic-tag ai">' + esc(a.analyzer || '-') + '</span>' +
      '<span class="aic-tag">步骤 ' + (a.steps || []).length + '</span>' +
      '<span class="aic-tag">断言 ' + (a.assertions || []).length + '</span>' +
      (a.entry_path ? '<span class="aic-tag ok">入口：' + esc(a.entry_path.join(' → ')) + '</span>' : '') +
      (a.preconditions || []).map((p) => '<span class="aic-tag ok">前置：' + esc(p.slice(0, 18)) + '</span>').join('') +
      (a.risks || []).map(() => '<span class="aic-tag bad">高风险动作 · 需人工确认</span>').join('') +
      '</div>';
    if (a.analyzer_note) html += '<p class="aic-note">' + esc(a.analyzer_note) + '</p>';
    (a.notes || []).forEach((n) => { html += '<p class="aic-note">· ' + esc(n) + '</p>'; });
    abox.innerHTML = html;

    const steps = a.steps || [];
    $('#aicSteps').innerHTML = steps.length ? steps.map((s) =>
      '<div class="aic-step"><span class="no">' + esc(s.sid) + '</span>' +
      '<span class="tt">' + esc(ACTION_LABEL[s.action] || s.action) + ' ' + esc(s.target) +
      (s.value ? '（' + esc(s.value) + '）' : '') + '</span>' +
      '<span class="aic-tag ' + (s.source === 'inferred' ? 'warn' : '') + '">' +
      (s.source === 'inferred' ? '规则推断' : '需求原句') + '</span>' +
      '<span class="aic-tag">待映射</span></div>').join('') : '<p class="aic-empty">—</p>';

    const asserts = a.assertions || [];
    $('#aicAsserts').innerHTML = asserts.length ? asserts.map((x) =>
      '<div class="aic-step"><span class="tt">' + esc(ASSERT_LABEL[x.type] || x.type) +
      '：' + esc(x.target) + '</span><span class="aic-tag">待配置参数</span></div>').join('')
      : '<p class="aic-empty">—</p>';
  }

  async function answerClarify(qid, opt, btn) {
    const d = await postJson('/api/ai-case/jobs/' + curJob + '/clarifications', { answers: { [qid]: opt } });
    if (!d.ok) return toast(d.msg || '提交失败', false);
    btn.classList.add('picked');
    toast('已确认：' + opt);
    renderJob(d.job);
  }

  async function cancelJob() {
    if (!curJob) return;
    const d = await postJson('/api/ai-case/jobs/' + curJob + '/cancel', {});
    if (!d.ok) return toast(d.msg || '取消失败', false);
    toast('任务已取消');
    renderJob(d.job);
  }

  /* ---------- P2 设备观察 ---------- */
  function obUdid() { return defDevice(); }
  function obLock() {
    if (!CFG || !CFG.devices) return null;
    const d = CFG.devices.find(x => x.udid === obUdid());
    return d ? (d.lock || null) : null;
  }
  function renderObserveTags() {
    const udid = obUdid();
    $('#aicObMaestro').textContent = 'Maestro: ' + (CFG && CFG.maestro ? '✓' : '✗ 未安装');
    $('#aicObMaestro').className = 'aic-tag ' + (CFG && CFG.maestro ? 'ok' : 'warn');
    $('#aicObDev').textContent = '设备：' + (udid || '未绑定');
    $('#aicObDev').className = 'aic-tag ' + (udid ? 'ok' : '');
    const s = (CFG && CFG.skills) || {};
    $('#aicObLimit').textContent = '上限：' + (s.max_steps || '—') + ' 跳 / ' + (s.max_minutes || '—') + ' 分钟';
    const lock = obLock();
    $('#aicObLock').textContent = '锁：' + (lock ? ('#' + (lock.job_id || '人工')) : '未锁定');
    $('#aicObLock').className = 'aic-tag ' + (lock ? 'warn' : '');
    const lockBtn = $('#aicLockBtn');
    lockBtn.textContent = lock ? '解锁设备' : '锁定设备';
    lockBtn.classList.toggle('danger', !!lock);
    const offline = !udid;
    ['aicShotBtn', 'aicHierBtn', 'aicLockBtn'].forEach((id) => { $('#' + id).disabled = offline; });
    if (offline) $('#aicShotEmpty').textContent = '在「配置项 → 项目与设备」绑定默认设备（USB 调试在线）';
  }

  function bindObserve() {
    $('#aicShotBtn').addEventListener('click', async () => {
      const btn = $('#aicShotBtn');
      btn.disabled = true; btn.textContent = '截图…';
      const d = await postJson('/api/ai-case/observe/screenshot', { udid: obUdid() });
      btn.disabled = false; btn.textContent = '刷新画面';
      if (!d.ok) { $('#aicShotEmpty').textContent = d.msg || '截图失败'; return toast(d.msg || '截图失败', false); }
      curShotTs = d.ts;
      const img = $('#aicShot');
      img.src = d.image_url + '?t=' + d.ts;
      img.classList.remove('hidden');
      $('#aicShotEmpty').classList.add('hidden');
      toast('画面已更新（' + (d.source === 'maestro' ? 'Maestro' : 'adb 兜底') + '）'
        + (d.note ? ' · ' + d.note : ''));
    });
    $('#aicHierBtn').addEventListener('click', async () => {
      const btn = $('#aicHierBtn');
      btn.disabled = true; btn.textContent = '读取中…';
      const d = await postJson('/api/ai-case/observe/hierarchy', { udid: obUdid() });
      btn.disabled = false; btn.textContent = '读取层级';
      const out = $('#aicHierOut');
      if (!d.ok) { out.textContent = '层级读取失败：' + d.msg; return toast(d.msg || '读取失败', false); }
      const s = d.summary || {};
      let txt = '来源 ' + d.source + ' · 节点 ' + (s.nodes || 0) + ' · 可点 ' + (s.clickable || 0) + '\n';
      (s.texts || []).forEach((t) => { txt += '· ' + t + '\n'; });
      if (d.raw) txt += d.raw.slice(0, 600);
      out.textContent = txt;
      toast('层级已读取（' + (s.nodes || 0) + ' 节点）');
    });
    $('#aicLockBtn').addEventListener('click', async () => {
      const lock = obLock();
      const d = lock
        ? await api('/api/ai-case/devices/' + encodeURIComponent(obUdid()) + '/lock', { method: 'DELETE' })
        : await postJson('/api/ai-case/devices/' + encodeURIComponent(obUdid()) + '/lock', { job_id: curJob });
      if (!d.ok) return toast(d.msg || '锁定失败（可能被其他任务持有）', false);
      if (CFG && CFG.devices) {
        const dev = CFG.devices.find(x => x.udid === obUdid());
        if (dev) dev.lock = d.lock || null;
      }
      renderObserveTags();
      toast(lock ? '设备已解锁' : '设备已锁定（独占）');
    });
  }

  /* ---------- 配置中心 ---------- */
  function bindConfig() {
    $('#aicProjAdd').addEventListener('click', addProject);
    $('#aicDefSave').addEventListener('click', saveDefaults);
    $('#aicMlSave').addEventListener('click', saveModel);
    $('#aicMlTest').addEventListener('click', testModel);
    $('#aicPSave').addEventListener('click', savePrompts);
    $('#aicPReset').addEventListener('click', resetPrompts);
    $('#aicSkFileSave').addEventListener('click', saveSkillFile);
    $('#aicSkFileReset').addEventListener('click', resetSkillFile);
    $('#aicSkSave').addEventListener('click', saveSkills);
  }

  function renderConfigPanel() {
    renderProjects();
    renderModel();
    renderPrompts();
    renderSkills();
  }

  function renderProjects() {
    const list = CFG.ai_projects || [];
    $('#aicProjCnt').textContent = list.length + ' 个项目';
    const box = $('#aicProjList');
    box.innerHTML = list.length ? '' : '<p class="aic-empty">还没有绑定项目</p>';
    const defId = (CFG.skills || {}).default_project_id;
    list.forEach((p) => {
      const row = document.createElement('div');
      row.className = 'aic-projrow';
      row.innerHTML = '<span class="pname">' + esc(p.name) + '</span>' +
        '<span class="ppkg">' + esc(p.app_package) + '</span>' +
        (p.id === defId ? '<span class="aic-tag ok">默认</span>' : '') +
        '<button class="bind" data-id="' + p.id + '">设为默认</button>' +
        '<button data-del="' + p.id + '">删除</button>';
      box.appendChild(row);
    });
    box.querySelectorAll('button[data-id]').forEach((b) => b.addEventListener('click', async () => {
      const d = await putJson('/api/ai-case/skills', { default_project_id: +b.dataset.id });
      if (!d.ok) return toast(d.msg || '设置失败', false);
      CFG.skills = d.skills; renderProjects(); renderResolved(); renderObserveTags();
      toast('已设为默认项目');
    }));
    box.querySelectorAll('button[data-del]').forEach((b) => b.addEventListener('click', async () => {
      const d = await api('/api/ai-case/ai-projects/' + b.dataset.del, { method: 'DELETE' });
      if (!d.ok) return toast(d.msg || '删除失败', false);
      toast('项目已删除');
      await loadConfig();
    }));

    // 默认项目 / 默认设备下拉
    const dp = $('#aicDefProject');
    dp.innerHTML = '<option value="">（不指定）</option>';
    list.forEach((p) => {
      const o = document.createElement('option');
      o.value = p.id; o.textContent = p.name + ' · ' + p.app_package;
      if (p.id === (CFG.skills || {}).default_project_id) o.selected = true;
      dp.appendChild(o);
    });
    const dd = $('#aicDefDevice');
    dd.innerHTML = '<option value="">（不指定）</option>';
    (CFG.devices || []).forEach((v) => {
      const o = document.createElement('option');
      o.value = v.udid;
      o.textContent = v.udid + (v.state === 'device' ? ' · 在线' : ' · ' + v.state);
      if (v.udid === (CFG.skills || {}).default_device) o.selected = true;
      dd.appendChild(o);
    });
    $('#aicDeviceNote').textContent = CFG.device_note || '';
  }

  async function addProject() {
    const name = $('#aicProjName').value.trim();
    const pkg = $('#aicProjPkg').value.trim();
    if (!name || !pkg) return toast('项目名称与包名都要填', false);
    const d = await postJson('/api/ai-case/ai-projects', { name: name, app_package: pkg });
    if (!d.ok) return toast(d.msg || '添加失败', false);
    $('#aicProjName').value = ''; $('#aicProjPkg').value = '';
    toast('项目已添加');
    await loadConfig();
  }

  async function saveDefaults() {
    const d = await putJson('/api/ai-case/skills', {
      default_project_id: $('#aicDefProject').value || null,
      default_device: $('#aicDefDevice').value || '',
    });
    if (!d.ok) return toast(d.msg || '保存失败', false);
    CFG.skills = d.skills;
    renderProjects(); renderResolved(); renderObserveTags();
    toast('默认项目与设备已保存');
  }

  function renderModel() {
    const m = CFG.model || {};
    $('#aicMlEnabled').checked = !!m.enabled;
    $('#aicMlUrl').value = m.base_url || '';
    $('#aicMlKey').value = '';
    $('#aicMlKey').placeholder = m.api_key || '未设置';
    $('#aicMlName').value = m.model || '';
    $('#aicMlTimeout').value = m.timeout || 20;
    const tag = $('#aicModelState');
    const on = m.enabled && m.base_url;
    tag.textContent = on ? ('已启用 · ' + (m.model || '未命名')) : '未启用';
    tag.className = 'aic-tag ' + (on ? 'ok' : '');
  }

  async function saveModel() {
    const d = await putJson('/api/ai-case/model-config', {
      enabled: $('#aicMlEnabled').checked,
      base_url: $('#aicMlUrl').value.trim(),
      api_key: $('#aicMlKey').value.trim(),
      model: $('#aicMlName').value.trim(),
      timeout: +$('#aicMlTimeout').value || 20,
    });
    if (!d.ok) return toast(d.msg || '保存失败', false);
    CFG.model = d.model;
    renderModel(); renderPhase();
    toast('模型配置已保存');
  }

  async function testModel() {
    const out = $('#aicMlTestOut');
    out.textContent = '测试中…';
    const d = await postJson('/api/ai-case/model/test', {
      base_url: $('#aicMlUrl').value.trim(),
      api_key: $('#aicMlKey').value.trim() || undefined,
      model: $('#aicMlName').value.trim(),
      timeout: +$('#aicMlTimeout').value || 20,
    });
    if (!d.ok) { out.textContent = '❌ ' + d.msg; return; }
    out.innerHTML = '<span class="aic-tag ok">✓ 连通 ' + d.latency_ms + 'ms</span> <span style="color:var(--muted)">回复：' +
      esc(d.reply || '(空)') + '</span>';
  }

  function renderPrompts() {
    const p = CFG.prompts || {};
    $('#aicPSys').value = p.parse_system || '';
    $('#aicPUsr').value = p.parse_user_template || '';
    $('#aicPromptFlag').textContent = p.customized ? '已自定义' : '默认模板';
    $('#aicPromptFlag').className = 'aic-tag ' + (p.customized ? 'warn' : '');
  }

  async function savePrompts() {
    const d = await putJson('/api/ai-case/prompts', {
      parse_system: $('#aicPSys').value,
      parse_user_template: $('#aicPUsr').value,
    });
    if (!d.ok) return toast(d.msg || '保存失败', false);
    CFG.prompts = d.prompts;
    renderPrompts();
    toast('提示词已保存');
  }

  async function resetPrompts() {
    const d = await postJson('/api/ai-case/prompts/reset', {});
    if (!d.ok) return toast(d.msg || '重置失败', false);
    CFG.prompts = d.prompts;
    renderPrompts();
    toast('已恢复默认提示词');
  }

  function renderSkills() {
    renderSkillFiles();
    const s = CFG.skills || {};
    const r = document.querySelector('input[name="skillParser"][value="' + (s.parser_mode || 'model') + '"]');
    if (r) r.checked = true;
    $('#aicSkExplore').checked = !!s.explore_enabled;
    $('#aicSkSteps').value = s.max_steps || 15;
    $('#aicSkMinutes').value = s.max_minutes || 5;
  }

  /* Skill 文件库：skill = 给模型读的 Markdown 指令文件 */
  let curSkillKey = 'parse';
  function renderSkillFiles() {
    const files = CFG.skill_files || [];
    const box = $('#aicSkTabs');
    box.innerHTML = '';
    files.forEach((f) => {
      const btn = document.createElement('button');
      btn.className = f.key === curSkillKey ? 'on' : '';
      btn.innerHTML = esc(f.name) + (f.enabled ? '' : ' <span class="off">停用</span>');
      btn.addEventListener('click', () => { curSkillKey = f.key; renderSkillFiles(); });
      box.appendChild(btn);
    });
    const f = files.find(x => x.key === curSkillKey) || files[0];
    if (!f) return;
    $('#aicSkName').value = f.name;
    $('#aicSkWhen').value = f.when || '';
    $('#aicSkContent').value = f.content || '';
    $('#aicSkFileEnabled').checked = !!f.enabled;
    const flag = $('#aicSkFlag');
    flag.textContent = f.customized ? '已自定义' : '内置版';
    flag.className = 'aic-tag ' + (f.customized ? 'warn' : '');
  }

  async function saveSkillFile() {
    const d = await putJson('/api/ai-case/skill-files/' + curSkillKey, {
      name: $('#aicSkName').value.trim(),
      when: $('#aicSkWhen').value.trim(),
      content: $('#aicSkContent').value,
      enabled: $('#aicSkFileEnabled').checked,
    });
    if (!d.ok) return toast(d.msg || '保存失败', false);
    CFG.skill_files = (CFG.skill_files || []).map(f => (f.key === curSkillKey ? Object.assign({}, f, d.skill) : f));
    renderSkillFiles(); renderObserveTags();
    toast('技能文件已保存（对应阶段将注入模型上下文）');
  }

  async function resetSkillFile() {
    const d = await postJson('/api/ai-case/skill-files/' + curSkillKey + '/reset', {});
    if (!d.ok) return toast(d.msg || '重置失败', false);
    CFG.skill_files = CFG.skill_files.map(f => (f.key === curSkillKey ? Object.assign({}, f, d.skill, { customized: false }) : f));
    renderSkillFiles(); renderObserveTags();
    toast('已恢复内置技能文件');
  }

  async function saveSkills() {
    const parser = document.querySelector('input[name="skillParser"]:checked');
    const d = await putJson('/api/ai-case/skills', {
      parser_mode: parser ? parser.value : 'model',
      explore_enabled: $('#aicSkExplore').checked,
      max_steps: +$('#aicSkSteps').value || 15,
      max_minutes: +$('#aicSkMinutes').value || 5,
    });
    if (!d.ok) return toast(d.msg || '保存失败', false);
    CFG.skills = d.skills;
    renderSkills(); renderPhase(); renderObserveTags();
    toast('执行参数已保存');
  }

  /* ---------- 自适应缩放占位（面板自适应由 CSS 负责） ---------- */
  document.addEventListener('DOMContentLoaded', init);
})();
