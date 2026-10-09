/* AI 用例生成 · 工作台页脚本（P1：建任务 / 需求解析展示 / 澄清确认 / SSE 事件流）
   约定与 app.js 一致：api()/postJson() 封装、#toast 轻提示、PlatformNav 面包屑 */
(function () {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  async function api(url, opts) {
    const res = await fetch(url, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
    const data = await res.json().catch(() => ({ ok: false, msg: '响应解析失败(' + res.status + ')' }));
    if (!res.ok && !data.msg) data.msg = 'HTTP ' + res.status;
    return data;
  }
  const postJson = (url, body) => api(url, { method: 'POST', body: JSON.stringify(body || {}) });

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
  let CFG = null;        // /config 结果（设备/锁/设置/maestro 可用性）
  let curShotTs = 0;     // 当前画面时间戳（判断刷新按钮是否出新图）

  function fmtTime(ts) {
    if (!ts) return '-';
    const d = new Date(ts * 1000);
    const p = (n) => String(n).padStart(2, '0');
    return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  /* ---------- 初始化 ---------- */
  async function init() {
    if (window.PlatformNav) {
      PlatformNav.render(document.getElementById('sidebar'), PAGE_PATH);
    }
    await loadConfig();
    await loadRecent();
    bindCreate();
    $('#aicCancel').addEventListener('click', cancelJob);
  }

  async function loadConfig() {
    const d = await api('/api/ai-case/config');
    if (!d.ok) return;
    CFG = d;
    const projSel = $('#aicProject');
    (d.projects || []).forEach((p) => {
      const o = document.createElement('option');
      o.value = p.id; o.textContent = p.name;
      projSel.appendChild(o);
    });
    if (!(d.projects || []).length) {
      $('#aicPkg').placeholder = '未配置项目，请直接填写包名（如 com.example.app）';
    }
    const devSel = $('#aicDevice');
    devSel.innerHTML = '';
    if ((d.devices || []).length) {
      d.devices.forEach((v) => {
        const o = document.createElement('option');
        o.value = v.udid;
        o.textContent = v.udid + (v.model && v.model !== v.udid ? ' · ' + v.model : '') + ' · 在线';
        devSel.appendChild(o);
      });
    } else {
      const o = document.createElement('option');
      o.value = ''; o.textContent = '（无在线设备 — 真机探索需先连接）';
      devSel.appendChild(o);
    }
    devSel.addEventListener('change', updateObserveTags);
    $('#aicDeviceNote').textContent = d.device_note || '';
    const box = $('#aicEntryModes');
    (d.entry_modes || []).forEach((m, i) => {
      const lab = document.createElement('label');
      lab.className = 'aic-opt';
      lab.innerHTML = '<input type="radio" name="aicEntry" value="' + esc(m.value) + '"' +
        (i === 0 ? ' checked' : '') + '><span>' + esc(m.label) + '</span>';
      box.appendChild(lab);
    });
    $('#aicPhase').textContent = d.model_configured
      ? 'P2 已接入：设备观察 · 独占锁 · Maestro MCP'
      : 'P2 已接入：设备观察 · 独占锁 · 解析器=规则兜底（未配置 AI_CASE_MODEL_URL）';
    updateObserveTags();
    bindObserve();
  }

  /* ---------- P2 设备观察 ---------- */
  function obUdid() { return $('#aicDevice').value || ''; }
  function obLock() {
    if (!CFG || !CFG.devices) return null;
    const d = CFG.devices.find(x => x.udid === obUdid());
    return d ? (d.lock || null) : null;
  }
  function updateObserveTags() {
    const udid = obUdid();
    $('#aicObMaestro').textContent = 'Maestro: ' + (CFG && CFG.maestro ? '✓' : '✗ 未安装');
    $('#aicObMaestro').className = 'aic-tag ' + (CFG && CFG.maestro ? 'ok' : 'warn');
    $('#aicObDev').textContent = '设备：' + (udid || '未连接');
    $('#aicObDev').className = 'aic-tag ' + (udid ? 'ok' : '');
    const s = (CFG && CFG.settings) || {};
    $('#aicObLimit').textContent = '上限：' + (s.max_steps || '—') + ' 跳 / ' + (s.max_minutes || '—') + ' 分钟';
    const lock = obLock();
    $('#aicObLock').textContent = '锁：' + (lock ? ('#' + (lock.job_id || '人工')) : '未锁定');
    $('#aicObLock').className = 'aic-tag ' + (lock ? 'warn' : '');
    const lockBtn = $('#aicLockBtn');
    lockBtn.textContent = lock ? '解锁设备' : '锁定设备';
    lockBtn.classList.toggle('danger', !!lock);
    const offline = !udid;
    ['aicShotBtn', 'aicHierBtn', 'aicLockBtn'].forEach((id) => { $('#' + id).disabled = offline; });
    if (offline) $('#aicShotEmpty').textContent = '设备未连接：插上真机（USB 调试）后刷新本页';
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
      updateObserveTags();
      toast(lock ? '设备已解锁' : '设备已锁定（独占）');
    });
  }

  async function loadRecent() {
    const d = await api('/api/ai-case/jobs?limit=8');
    const box = $('#aicRecent');
    if (!d.ok || !(d.results || []).length) return;
    box.innerHTML = '';
    d.results.forEach((j) => {
      const b = document.createElement('button');
      b.className = 'aic-jobrow';
      b.innerHTML = '<span class="jid">#' + j.id + '</span>' +
        '<span class="jtxt">' + esc(j.requirement.slice(0, 24)) + '</span>' +
        '<span class="aic-tag">' + esc(j.status) + '</span>';
      b.addEventListener('click', () => openJob(j.id));
      box.appendChild(b);
    });
  }

  /* ---------- 创建任务 ---------- */
  function bindCreate() {
    $('#aicCreate').addEventListener('click', async () => {
      const requirement = $('#aicReq').value.trim();
      const btn = $('#aicCreate');
      if (requirement.length < 5) return toast('需求描述太短：请描述测试场景与断言', false);
      const pkg = $('#aicPkg').value.trim();
      if (!pkg) return toast('App 包名不能为空（AI 不猜测包名）', false);
      const entry = document.querySelector('input[name="aicEntry"]:checked');
      btn.disabled = true; btn.textContent = '解析中…';
      const d = await postJson('/api/ai-case/jobs', {
        requirement: requirement,
        project_id: $('#aicProject').value || null,
        app_package: pkg,
        device: $('#aicDevice').value || '',
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
    evtSource.onerror = () => { /* 断流后 EventSource 自动重连；任务终态服务端会收流 */ };
  }

  function renderJob(job) {
    if (!job) return;
    // 状态条：FLOW_STATUSES 带 * 的是后续阶段（锁定展示）
    const flow = job.flow_statuses || [];
    const curIdx = flow.indexOf(job.status);
    $('#aicStates').innerHTML = flow.map((s) => {
      const name = s.replace('*', '');
      const locked = s.startsWith('*');
      const cls = name === job.status ? 'cur' : (curIdx >= 0 && flow.indexOf(s) >= 0 && flow.indexOf(s) < curIdx ? 'past' : (locked ? 'locked' : ''));
      return '<span class="st ' + cls + '">' + esc(name) + '</span>';
    }).join('');

    $('#aicMeta').innerHTML =
      '<span>任务 <b>#' + job.id + '</b></span>' +
      '<span>项目 <b>' + esc(job.project_name || '-') + '</b></span>' +
      '<span>包名 <b>' + esc(job.app_package || '-') + '</b></span>' +
      '<span>设备 <b>' + esc(job.device || '-') + '</b></span>' +
      '<span>入口 <b>' + esc(job.entry_mode_label) + '</b></span>' +
      '<span>更新 <b>' + fmtTime(job.updated_at) + '</b></span>';

    // 澄清问题（未回答的可点，已回答的展示结论）
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

    // 事件流
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

    // 解析结果
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

    // 步骤
    const steps = a.steps || [];
    $('#aicSteps').innerHTML = steps.length ? steps.map((s) =>
      '<div class="aic-step"><span class="no">' + esc(s.sid) + '</span>' +
      '<span class="tt">' + esc(ACTION_LABEL[s.action] || s.action) + ' ' + esc(s.target) +
      (s.value ? '（' + esc(s.value) + '）' : '') + '</span>' +
      '<span class="aic-tag ' + (s.source === 'inferred' ? 'warn' : '') + '">' +
      (s.source === 'inferred' ? '规则推断' : '需求原句') + '</span>' +
      '<span class="aic-tag">待映射</span></div>').join('') : '<p class="aic-empty">—</p>';

    // 断言
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

  document.addEventListener('DOMContentLoaded', init);
})();
