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

const VT_TPL = {
  name: '快歌首页视觉检查',
  app: 'com.recordlife.kuaige',
  wait: '3',
  note: '回归首页主链路视觉',
  steps: 'launchApp\nassertVisible: "推荐"\ntakeScreenshot: 首页\ntapOn: "我的"\ntakeScreenshot: 我的页',
};

/* 表单 ⇄ YAML：
   生成 = 备注(注释行) + appId + --- + 每行步骤自动补「- 」前缀；
   解析 = 逆向提取（旧手写脚本也能进表单继续编辑） */
function vtBuildYaml(f) {
  const lines = [];
  if (f.note) lines.push('# 备注: ' + f.note);
  lines.push('appId: ' + f.app);
  lines.push('---');
  if (f.wait) lines.push('- sleep: ' + f.wait);
  f.steps.forEach(st => lines.push('- ' + st));
  return lines.join('\n');
}

function vtParseYaml(content) {
  const f = { name: '', app: '', wait: '', note: '', steps: [] };
  let inSteps = false;
  (content || '').split('\n').forEach(ln => {
    const t = ln.trim();
    if (!t) return;
    const mNote = t.match(/^#\s*备注[:：]\s*(.+)$/);
    if (mNote) { f.note = mNote[1].trim(); return; }
    const mApp = t.match(/^appId:\s*(\S+)$/);
    if (mApp) { f.app = mApp[1]; return; }
    if (t === '---') { inSteps = true; return; }
    if (inSteps) {
      f.steps.push(t.replace(/^-\s+/, ''));
      if (/^sleep:\s*\d+/.test(t) && !f.wait) f.wait = t.split(':')[1].trim();
    }
  });
  return f;
}

async function vtOpenFlow(name) {
  const mask = document.getElementById('vtFlowMask');
  let f = { name: '', app: '', wait: '', note: '', steps: [] };
  if (name) {
    const d = await vtApi('/visual/api/flows/' + encodeURIComponent(name));
    if (!d || !d.ok) { vtToast((d && d.msg) || '读取失败', false); return; }
    f = vtParseYaml(d.content);
    f.name = name;
  }
  document.getElementById('vtFlowTitle').textContent = name ? '✎ 编辑视觉检查流程 · ' + name : '新建视觉检查流程';
  document.getElementById('vtFlowName').value = f.name;
  document.getElementById('vtFlowName').disabled = !!name;
  document.getElementById('vtFlowApp').value = f.app;
  document.getElementById('vtFlowWait').value = f.wait;
  document.getElementById('vtFlowNote').value = f.note;
  document.getElementById('vtFlowSteps').value = f.steps.join('\n');
  document.getElementById('vtFlowHint').textContent = '';
  document.getElementById('vtFlowSave').onclick = async () => {
    const hint = document.getElementById('vtFlowHint');
    const req = (ok, msg, focusId) => {
      if (ok) return true;
      hint.textContent = '❌ ' + msg;
      vtToast(msg, false);
      if (focusId) document.getElementById(focusId).focus();
      return false;
    };
    const name = document.getElementById('vtFlowName').value.trim();
    const app = document.getElementById('vtFlowApp').value.trim();
    const wait = document.getElementById('vtFlowWait').value.trim();
    const note = document.getElementById('vtFlowNote').value.trim();
    const steps = document.getElementById('vtFlowSteps').value.split('\n')
      .map(l => l.trim().replace(/^-\s+/, '')).filter(Boolean);
    if (!req(name, '流程名为必填项', 'vtFlowName')) return;
    if (!req(app, '被测 App 包名为必填项（如 com.recordlife.kuaige）', 'vtFlowApp')) return;
    if (!req(steps.length, '操作与截图步骤为必填项（至少一行，如 launchApp）', 'vtFlowSteps')) return;
    const shot = steps.filter(l => /^takeScreenshot[:：]/.test(l));
    if (!req(shot.length, '至少需要一条 takeScreenshot 截图检查点，否则看板无图可比', 'vtFlowSteps')) return;
    const r = await vtPost('/visual/api/flows', { name, content: vtBuildYaml({ name, app, wait, note, steps }) });
    vtToast(r.msg || (r.ok ? '已保存' : '保存失败'), r.ok);
    if (r.ok) { mask.classList.remove('show'); vtLoadFlows(); }
  };
  document.getElementById('vtFlowCancel').onclick = () => mask.classList.remove('show');
  document.getElementById('vtFlowTpl').onclick = () => {
    document.getElementById('vtFlowName').value = VT_TPL.name;
    document.getElementById('vtFlowName').disabled = true;
    document.getElementById('vtFlowName').dataset.tplNew = '1';
    document.getElementById('vtFlowApp').value = VT_TPL.app;
    document.getElementById('vtFlowWait').value = VT_TPL.wait;
    document.getElementById('vtFlowNote').value = VT_TPL.note;
    document.getElementById('vtFlowSteps').value = VT_TPL.steps;
  };
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
