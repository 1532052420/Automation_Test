/* 视觉测试（独立模块）· Maestro 流程管理 + 运行 + SSIM 比对看板
   一期本地模式：不依赖 Percy 云端；页面骨架与平台一致（renderSidebar + subnav 双面板）。 */

async function vtApi(path, opts) {
  // 失败要能看见原因：非 2xx / 非 JSON 都转成带状态的错误信息，不再吞成裸 null
  try {
    const r = await fetch(path, opts);
    const text = await r.text();
    try { return JSON.parse(text); }
    catch (e) { return { ok: false, msg: '服务响应异常(HTTP ' + r.status + ')' }; }
  } catch (e) {
    return { ok: false, msg: '网络请求失败: ' + e.message };
  }
}
function vtEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function vtToast(msg, ok) {
  const t = document.getElementById('vtToast');
  if (!t) return;
  t.textContent = msg;
  t.style.background = ok === false ? 'var(--bad-text, #d33)' : 'var(--ink, #222)';
  t.style.display = 'block';
  clearTimeout(vtToast._timer);
  vtToast._timer = setTimeout(() => { t.style.display = 'none'; }, 2600);
}
async function vtPost(path, body) {
  const r = await vtApi(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(body || {}) });
  if (!r) { vtToast('服务异常', false); throw new Error('服务异常'); }
  return r;
}const VT_STATE_CN = { running: '运行中', done: '已完成', failed: '失败' };
const VT_SHOT_CN = { same: '✅ 与基线一致', changed: '🆘 与基线有差异', new: '🆕 新增（无基线）' };
let _vtCurRun = null;

/* ---------------- 流程管理 ---------------- */
async function vtLoadFlows() {
  const d = await vtApi('/visual/api/flows');
  const tb = document.getElementById('vtFlowsTbody');
  const flows = (d && d.flows) || [];
  tb.innerHTML = flows.map(f => `<tr>
    <td><b>${vtEsc(f.name)}</b></td>
    <td class="muted">${vtEsc(f.file)}</td>
    <td class="muted">${vtEsc(f.mtime)}</td>
    <td class="ops">
      <button class="mini" data-vtrun="${vtEsc(f.name)}">▶ 运行</button>
      <button class="ghost mini" data-vtedit="${vtEsc(f.name)}">编辑</button>
      <button class="danger mini" data-vtdel="${vtEsc(f.name)}">删除</button>
    </td></tr>`).join('')
    || '<tr><td colspan="4" class="empty">暂无流程</td></tr>';
  document.getElementById('vtFlowsEmpty').style.display = flows.length ? 'none' : '';
  tb.querySelectorAll('[data-vtrun]').forEach(b => b.addEventListener('click', () => vtRun(b.dataset.vtrun)));
  tb.querySelectorAll('[data-vtedit]').forEach(b => b.addEventListener('click', () => vtOpenFlow(b.dataset.vtedit)));
  tb.querySelectorAll('[data-vtdel]').forEach(b => b.addEventListener('click', async () => {
    if (!confirm('确认删除流程「' + b.dataset.vtdel + '」？')) return;
    const r = await vtApi('/visual/api/flows/' + encodeURIComponent(b.dataset.vtdel), { method: 'DELETE' });
    vtToast((r && r.msg) || '删除失败', r && r.ok);
    vtLoadFlows();
  }));
}

const VT_TPL = '# 一条流程 = 启动 App → 自动操作 → 在想留证的步骤后截图\n'
  + '# ① 把 appId 换成被测 App 包名；② --- 后是具体步骤；③ takeScreenshot 后的截图自动进看板比对\n'
  + 'appId: com.recordlife.kuaige\n'
  + '---\n'
  + '- launchApp\n'
  + '- assertVisible: "推荐"\n'
  + '- takeScreenshot: 首页\n'
  + '- tapOn: "我的"\n'
  + '- assertVisible: "登录"\n'
  + '- takeScreenshot: 我的页\n';

async function vtOpenFlow(name) {
  const mask = document.getElementById('vtFlowMask');
  let content = '';
  if (name) {
    const d = await vtApi('/visual/api/flows/' + encodeURIComponent(name));
    if (!d || !d.ok) { vtToast((d && d.msg) || '读取失败', false); return; }
    content = d.content;
  }
  document.getElementById('vtFlowTitle').textContent = name ? '✎ 编辑流程 · ' + name : '新建视觉检查流程';
  document.getElementById('vtFlowName').value = name || '';
  document.getElementById('vtFlowName').disabled = !!name;
  document.getElementById('vtFlowName').placeholder = '如：快歌首页视觉检查';
  document.getElementById('vtFlowYaml').value = content;
  document.getElementById('vtFlowSave').onclick = async () => {
    const n = document.getElementById('vtFlowName').value.trim();
    const r = await vtPost('/visual/api/flows', { name: n, content: document.getElementById('vtFlowYaml').value });
    vtToast(r.msg || (r.ok ? '已保存' : '保存失败'), r.ok);
    if (r.ok) { mask.classList.remove('show'); vtLoadFlows(); }
  };
  document.getElementById('vtFlowCancel').onclick = () => mask.classList.remove('show');
  mask.classList.add('show');
}

/* ---------------- 运行 ---------------- */
async function vtRun(flow) {
  const r = await vtPost('/visual/api/runs', { flow });
  vtToast(r.msg || '运行已启动', r.ok);
  if (r.ok) {
    vtShowPanel('runs');
    _vtCurRun = r.run_id;
    vtLoadRuns();
  }
}

async function vtLoadRuns() {
  const d = await vtApi('/visual/api/runs');
  const tb = document.getElementById('vtRunsTbody');
  const runs = (d && d.runs) || [];
  tb.innerHTML = runs.map(m => `<tr>
    <td class="muted">${vtEsc(m.run_id)}</td>
    <td><b>${vtEsc(m.flow)}</b></td>
    <td>${VT_STATE_CN[m.status] || vtEsc(m.status)}${m.shots ? ' · ' + m.shots + ' 图' : ''}</td>
    <td>${m.status === 'running' ? '—' : (m.shots || 0)}</td>
    <td class="muted">${vtEsc(m.start || '')}</td>
    <td class="ops">
      <button class="mini" data-vtdetail="${vtEsc(m.run_id)}">详情</button>
      ${m.status === 'running' ? `<button class="danger mini" data-vtstop="${vtEsc(m.run_id)}">终止</button>` : ''}
    </td></tr>`).join('') || '<tr><td colspan="6" class="empty">暂无运行记录——去「流程管理」点 ▶ 运行</td></tr>';
  tb.querySelectorAll('[data-vtdetail]').forEach(b => b.addEventListener('click', () => vtOpenRun(b.dataset.vtdetail)));
  tb.querySelectorAll('[data-vtstop]').forEach(b => b.addEventListener('click', async () => {
    const r = await vtPost('/visual/api/runs/' + encodeURIComponent(b.dataset.vtstop) + '/stop');
    vtToast(r.msg || '已终止', r.ok);
    vtLoadRuns();
  }));
  // 有进行中的运行时保持轮询（详情页打开时也刷新详情）
  if (runs.some(m => m.status === 'running')) {
    clearTimeout(vtLoadRuns._timer);
    vtLoadRuns._timer = setTimeout(() => {
      vtLoadRuns();
      if (_vtCurRun && document.getElementById('vtDetail').style.display !== 'none') vtOpenRun(_vtCurRun, true);
    }, 3000);
  }
}

async function vtOpenRun(runId, silent) {
  const d = await vtApi('/visual/api/runs/' + encodeURIComponent(runId));
  if (!d || !d.ok) { if (!silent) vtToast((d && d.msg) || '记录不存在', false); return; }
  _vtCurRun = runId;
  document.getElementById('vtDetail').style.display = '';
  document.getElementById('vtDetailTitle').textContent =
    '运行详情 · ' + runId + ' · ' + (d.meta.flow || '') + ' · ' + (VT_STATE_CN[d.meta.status] || d.meta.status);
  const logEl = document.getElementById('vtLog');
  const tail = (d.log || '').split('\n').slice(-14).join('\n');
  logEl.textContent = tail || '（暂无日志）';
  logEl.scrollTop = logEl.scrollHeight;
  const box = document.getElementById('vtResults');
  box.innerHTML = (d.results || []).map(it => {
    const q = p => '/visual/api/img?path=' + encodeURIComponent('runs/' + runId + '/' + p);
    const img = p => p ? `<img loading="lazy" src="${q(p)}" style="height:150px;border-radius:8px;border:1px solid var(--line-soft)">` : '<div class="muted" style="font-size:12px">—</div>';
    return `<div class="vt-shot">
      <div style="margin:10px 0 6px"><b>${vtEsc(it.shot)}</b>
        <span class="muted" style="margin-left:8px">${VT_SHOT_CN[it.state] || ''}${it.similarity != null ? ' · 相似度 ' + it.similarity : ''}${it.msg ? ' · ' + vtEsc(it.msg) : ''}</span>
        ${it.state !== 'same' ? `<button class="ghost mini" data-vtbase="${vtEsc(it.shot)}" style="margin-left:8px">采纳为基线</button>` : ''}
      </div>
      <div style="display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap">
        <div><div class="muted" style="font-size:11.5px;margin-bottom:4px">基线</div>${img(it.baseline)}</div>
        <div><div class="muted" style="font-size:11.5px;margin-bottom:4px">本次截图</div><a href="${q(it.img)}" target="_blank" rel="noopener">${img(it.img)}</a></div>
        <div><div class="muted" style="font-size:11.5px;margin-bottom:4px">Diff（红=差异）</div>${img(it.diff)}</div>
      </div></div>`;
  }).join('') || '<div class="empty">本次运行没有可用的截图（流程里加 takeScreenshot 步骤）</div>';
  box.querySelectorAll('[data-vtbase]').forEach(b => b.addEventListener('click', async () => {
    const r = await vtPost('/visual/api/runs/' + encodeURIComponent(runId) + '/baseline', { shot: b.dataset.vtbase });
    vtToast(r.msg || (r.ok ? '已采纳' : '采纳失败'), r.ok);
    vtOpenRun(runId, true);
  }));
}

/* ---------------- 面板切换与初始化 ---------------- */
function vtShowPanel(name) {
  document.querySelectorAll('#panel-flows, #panel-runs').forEach(s => { s.hidden = s.id !== 'panel-' + name; });
  document.querySelectorAll('#subnav a').forEach(a => a.classList.toggle('on', a.dataset.panel === name));
  if (name === 'flows') vtLoadFlows(); else vtLoadRuns();
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.body.dataset.page !== 'visual') return;
  if (typeof renderSidebar === 'function') renderSidebar('/visual');
  document.querySelectorAll('#subnav a').forEach(a => {
    if (typeof icon === 'function' && a.dataset.icon) a.insertAdjacentHTML('afterbegin', icon(a.dataset.icon, 18));
    a.addEventListener('click', e => { e.preventDefault(); vtShowPanel(a.dataset.panel); history.replaceState(null, '', '#' + a.dataset.panel); });
  });
  const start = (location.hash || '').replace('#', '') === 'runs' ? 'runs' : 'flows';
  vtShowPanel(start);
  document.getElementById('btnVtNew').addEventListener('click', () => vtOpenFlow(''));
  document.getElementById('vtFlowTpl').addEventListener('click', () => {
    const y = document.getElementById('vtFlowYaml');
    if (!y.value.trim()) y.value = VT_TPL;
  });
  document.getElementById('btnVtFlowsRefresh').addEventListener('click', vtLoadFlows);
  document.getElementById('btnVtRunsRefresh').addEventListener('click', vtLoadRuns);
  document.getElementById('btnVtDetailBack').addEventListener('click', () => {
    document.getElementById('vtDetail').style.display = 'none'; _vtCurRun = null;
  });
  // 右下角 toast 容器（页面自持，不依赖平台页脚）
  const t = document.createElement('div');
  t.id = 'vtToast';
  t.style.cssText = 'display:none;position:fixed;right:22px;bottom:22px;z-index:1200;color:#fff;padding:9px 16px;border-radius:10px;font-size:13.5px;box-shadow:0 8px 24px rgba(0,0,0,.25)';
  document.body.appendChild(t);
});
