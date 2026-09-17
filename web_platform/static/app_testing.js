/* AppUI 用例编排 / 测试套件 · 面板逻辑（testhub SceneBuilder + SuiteList 移植版）
   ------------------------------------------------------------------
   与 testhub 的差异（架构适配）：
   - 步骤来源不是组件面板，而是本平台 cases/app_ui 的用例方法树（scan_case_tree）；
   - 拖拽用原生 HTML5 DnD（不引 vuedraggable）；保存后执行直接走 /api/run 同一链路。
   依赖 app.js 的公共件：$ / api / postJson / del / esc / toast / confirmModal / statusBadge。 */
'use strict';

const AT_PREFIX = '/app-testing';
let _orchTree = [];        // 原始用例树（编排左栏）
let _orchSteps = [];       // 当前编排的步骤 [{node, name}]
let _orchCaseId = 0;       // 正在编辑的用例 id（0 = 新建）
let _cases = [];           // 用例列表（套件弹窗用）
let _suiteSel = [];        // 套件弹窗已选用例 [{id, name, step_count}]
let _suiteId = 0;          // 弹窗正在编辑的套件 id（0 = 新建）

/* ================= 用例编排（三栏） ================= */
function renderOrchTree(kw) {
  const box = $('#orchTree');
  if (!_orchTree.length) {
    box.innerHTML = '<div class="empty" style="padding:24px">cases/app_ui 下没有可编排的用例</div>';
    return;
  }
  const k = (kw || '').trim().toLowerCase();
  let html = '<ul>';
  _orchTree.forEach(f => {
    const methods = f.methods.filter(m =>
      !k || (f.file + ' ' + f.class_name + ' ' + m).toLowerCase().includes(k));
    if (!methods.length) return;
    html += '<li><div class="orch-file">' + esc(f.file.split('/').pop()) +
      ' <span class="path">' + esc(f.class_name) + '</span></div><ul>';
    methods.forEach(m => {
      const node = f.file + '::' + f.class_name + '::' + m;
      html += '<li><span class="orch-add" data-node="' + esc(node) + '" data-name="' +
        esc(f.class_name + '::' + m) + '">' + esc(m) + '</span></li>';
    });
    html += '</ul></li>';
  });
  box.innerHTML = html + '</ul>';
  if (!box.querySelector('.orch-add')) box.innerHTML = '<div class="empty" style="padding:24px">没有匹配的方法</div>';
}

function renderOrchSteps() {
  const box = $('#orchSteps');
  if (!_orchSteps.length) {
    box.innerHTML = '<div class="orch-empty">从左侧点击方法加入步骤，拖拽可调整顺序</div>';
    return;
  }
  box.innerHTML = _orchSteps.map((s, i) =>
    '<div class="orch-step" draggable="true" data-idx="' + i + '">' +
    '<span class="drag-handle">⋮⋮</span><span class="orch-index">' + (i + 1) + '</span>' +
    '<span class="orch-step-name">' + esc(s.name) + '</span>' +
    '<span class="orch-step-node" title="' + esc(s.node) + '">' + esc(s.node) + '</span>' +
    '<button class="orch-del" data-idx="' + i + '" title="移除">✕</button></div>').join('');
}

function bindNativeDnD(box, onReorder) {
  /* 原生 HTML5 拖拽排序：dragstart 记起点，dragover 计算落点并实时预览，drop 回调 */
  let dragIdx = -1;
  box.addEventListener('dragstart', e => {
    const item = e.target.closest('.orch-step');
    if (!item) return;
    dragIdx = +item.dataset.idx;
    item.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
  });
  box.addEventListener('dragend', e => {
    box.querySelectorAll('.dragging').forEach(el => el.classList.remove('dragging'));
    box.querySelectorAll('.drop-before').forEach(el => el.classList.remove('drop-before'));
  });
  box.addEventListener('dragover', e => {
    e.preventDefault();
    const item = e.target.closest('.orch-step');
    box.querySelectorAll('.drop-before').forEach(el => el.classList.remove('drop-before'));
    if (item && +item.dataset.idx !== dragIdx) item.classList.add('drop-before');
  });
  box.addEventListener('drop', e => {
    e.preventDefault();
    const item = e.target.closest('.orch-step');
    if (!item || dragIdx < 0) return;
    let to = +item.dataset.idx;
    if (to !== dragIdx) onReorder(dragIdx, to);
    dragIdx = -1;
  });
}

function moveStep(from, to) {
  const [s] = _orchSteps.splice(from, 1);
  _orchSteps.splice(from < to ? to - 1 : to, 0, s);
  renderOrchSteps();
}

async function loadOrchData() {
  const [tree, cases] = await Promise.all([api(AT_PREFIX + '/api/case-tree'), api(AT_PREFIX + '/api/cases')]);
  _orchTree = tree.ok ? (tree.tree || []) : [];
  _cases = cases.ok ? (cases.results || []) : [];
  $('#orchSel').innerHTML = '<option value="">＋ 新建用例</option>' +
    _cases.map(c => '<option value="' + c.id + '">' + esc(c.name) + '（' + (c.steps || []).length + ' 步）</option>').join('');
  renderOrchTree($('#orchSearch').value);
  renderOrchSteps();
}

function selectOrchCase(id) {
  _orchCaseId = +id || 0;
  const c = _cases.find(x => x.id === _orchCaseId);
  _orchSteps = c ? (c.steps || []).map(s => ({ node: s.node, name: s.name })) : [];
  $('#orchName').value = c ? c.name : '';
  $('#orchDesc').value = c ? (c.description || '') : '';
  $('#orchMeta').textContent = c ? ('创建于 ' + new Date((c.created_at || 0) * 1000).toLocaleString() +
    (c.created_by ? ' · ' + c.created_by : '')) : '';
  $('#btnOrchRun').disabled = !c;
  renderOrchSteps();
}

async function saveOrchCase() {
  const name = ($('#orchName').value || '').trim();
  if (!name) return toast('请填写用例名称', false);
  if (!_orchSteps.length) return toast('请至少编排一个步骤', false);
  const body = { name, description: $('#orchDesc').value.trim(), steps: _orchSteps,
                 created_by: $('#orchBy').value.trim() };
  const d = _orchCaseId ? await api(AT_PREFIX + '/api/cases/' + _orchCaseId,
    { method: 'PUT', body: JSON.stringify(body) })
    : await postJson(AT_PREFIX + '/api/cases', body);
  if (!d.ok) return toast(d.msg || '保存失败', false);
  toast('用例已保存', true);
  await loadOrchData();
  $('#orchSel').value = d.case.id;
  selectOrchCase(d.case.id);
}

/* ================= 测试套件（列表 + 双栏弹窗） ================= */
function suiteResultHtml(s) {
  /* NOT_RUN 复用 PENDING 徽章样式（statusBadge 只认 PENDING/RUNNING/PASSED/FAILED/ERROR） */
  const raw = s.execution_result || s.execution_status || 'NOT_RUN';
  return statusBadge(raw === 'NOT_RUN' ? 'PENDING' : raw);
}

function fmtTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false }) : '—';
}

async function renderSuites() {
  const d = await api(AT_PREFIX + '/api/suites');
  if (!d.ok) return toast(d.msg || '套件加载失败', false);
  const list = d.results || [];
  $('#suiteEmpty').style.display = list.length ? 'none' : '';
  $('#suiteTbody').innerHTML = list.map(s => {
    const stats = (s.execution_status === 'NOT_RUN') ? '—' :
      '<b class="num-ok">' + (s.passed_count || 0) + '</b> / <b class="num-bad">' + (s.failed_count || 0) + '</b>';
    const detail = (s.cases || []).map(c => esc(c.name)).join('、') || '<span class="muted">未选用例</span>';
    return '<tr>' +
      '<td><b>' + esc(s.name) + '</b>' + (s.description ? '<div class="path">' + esc(s.description) + '</div>' : '') + '</td>' +
      '<td>' + (s.cases || []).length + ' 个<div class="path" style="max-width:260px">' + detail + '</div></td>' +
      '<td>' + statusBadge(s.execution_status) + '</td>' +
      '<td>' + suiteResultHtml(s) + '</td>' +
      '<td>' + stats + '</td>' +
      '<td>' + fmtTime(s.last_run_at) + '</td>' +
      '<td class="ops"><button class="mini" data-run="' + s.id + '">执行</button>' +
      '<button class="ghost mini" data-edit="' + s.id + '">编辑</button>' +
      (s.last_run_id ? '<a class="ghost mini" href="/runs/' + esc(s.last_run_id) + '">详情</a>' : '') +
      '<button class="danger mini" data-del="' + s.id + '">删除</button></td></tr>';
  }).join('');
}

function renderSuiteModal() {
  const kw = ($('#suMSearch').value || '').trim().toLowerCase();
  const selIds = new Set(_suiteSel.map(c => c.id));
  const avail = _cases.filter(c => !selIds.has(c.id) &&
    (!kw || c.name.toLowerCase().includes(kw)));
  $('#suMAvail').innerHTML = avail.length ? avail.map(c =>
    '<div class="case-item" data-add="' + c.id + '"><b>' + esc(c.name) + '</b>' +
    '<span class="path">' + (c.steps || []).length + ' 步' +
    (c.description ? ' · ' + esc(c.description) : '') + '</span></div>').join('')
    : '<div class="orch-empty">没有可添加的用例</div>';
  $('#suMSelected').innerHTML = _suiteSel.length ? _suiteSel.map((c, i) =>
    '<div class="orch-step" draggable="true" data-idx="' + i + '">' +
    '<span class="drag-handle">⋮⋮</span><span class="orch-index">' + (i + 1) + '</span>' +
    '<span class="orch-step-name">' + esc(c.name) + '</span>' +
    '<span class="orch-step-node">' + (c.step_count || 0) + ' 步</span>' +
    '<button class="orch-del" data-rm="' + i + '" title="移除">✕</button></div>').join('')
    : '<div class="orch-empty">从左侧点击用例加入</div>';
}

async function openSuiteModal(sid) {
  _suiteId = +sid || 0;
  if (!_cases.length) {
    const d = await api(AT_PREFIX + '/api/cases');
    _cases = d.ok ? (d.results || []) : [];
  }
  if (_suiteId) {
    const d = await api(AT_PREFIX + '/api/suites/' + _suiteId);
    if (!d.ok) return toast(d.msg || '套件加载失败', false);
    $('#suiteModalTitle').textContent = '编辑套件';
    $('#suMName').value = d.suite.name;
    $('#suMDesc').value = d.suite.description || '';
    _suiteSel = (d.suite.cases || []).map(c => ({ ...c }));
  } else {
    $('#suiteModalTitle').textContent = '新建套件';
    $('#suMName').value = '';
    $('#suMDesc').value = '';
    _suiteSel = [];
  }
  $('#suMSearch').value = '';
  renderSuiteModal();
  $('#suiteMask').classList.add('show');
}

async function saveSuite() {
  const name = ($('#suMName').value || '').trim();
  if (!name) return toast('请填写套件名称', false);
  const body = { name, description: $('#suMDesc').value.trim(),
                 case_ids: _suiteSel.map(c => c.id) };
  const d = _suiteId ? await api(AT_PREFIX + '/api/suites/' + _suiteId,
    { method: 'PUT', body: JSON.stringify(body) })
    : await postJson(AT_PREFIX + '/api/suites', body);
  if (!d.ok) return toast(d.msg || '保存失败', false);
  $('#suiteMask').classList.remove('show');
  toast('套件已保存', true);
  renderSuites();
}

async function runSuite(sid) {
  const d = await postJson(AT_PREFIX + '/api/suites/' + sid + '/run', {});
  if (!d.ok) return toast(d.msg || '执行失败', false);
  toast('套件已开始执行 → Run ' + d.run_id, true);
  renderSuites();
}

/* ================= 面板初始化（initRun 调用） ================= */
async function appTestingInit() {
  if (!$('#panel-orch')) return;

  /* 编排：左栏树 */
  $('#orchSearch').addEventListener('input', () => renderOrchTree($('#orchSearch').value));
  $('#orchTree').addEventListener('click', e => {
    const add = e.target.closest('.orch-add');
    if (!add) return;
    _orchSteps.push({ node: add.dataset.node, name: add.dataset.name });
    renderOrchSteps();
  });
  /* 编排：中栏步骤（点击移除 + 拖拽排序） */
  $('#orchSteps').addEventListener('click', e => {
    const btn = e.target.closest('.orch-del');
    if (btn) { _orchSteps.splice(+btn.dataset.idx, 1); renderOrchSteps(); }
  });
  bindNativeDnD($('#orchSteps'), moveStep);
  /* 编排：右栏表单 */
  $('#orchSel').addEventListener('change', () => selectOrchCase($('#orchSel').value));
  $('#btnOrchSave').addEventListener('click', saveOrchCase);
  $('#btnOrchRun').addEventListener('click', async () => {
    if (!_orchCaseId) return;
    const d = await postJson(AT_PREFIX + '/api/cases/' + _orchCaseId + '/run', {});
    if (!d.ok) return toast(d.msg || '执行失败', false);
    toast('用例已开始执行 → Run ' + d.run_id, true);
    location.href = '/runs/' + d.run_id;
  });

  /* 套件：列表操作 */
  $('#btnSuiteRefresh').addEventListener('click', renderSuites);
  $('#btnSuiteNew').addEventListener('click', () => openSuiteModal(0));
  $('#suiteTbody').addEventListener('click', async e => {
    const run = e.target.closest('[data-run]'), edit = e.target.closest('[data-edit]'),
          del = e.target.closest('[data-del]');
    if (run) return runSuite(+run.dataset.run);
    if (edit) return openSuiteModal(+edit.dataset.edit);
    if (del) {
      const ok = await confirmModal('删除套件', '确定删除该套件？用例本身不受影响。');
      if (!ok) return;
      const d = await del(AT_PREFIX + '/api/suites/' + del.dataset.del);
      toast(d.ok ? '已删除' : (d.msg || '删除失败'), d.ok);
      renderSuites();
    }
  });
  /* 套件：双栏弹窗 */
  $('#suMSearch').addEventListener('input', renderSuiteModal);
  $('#suMAvail').addEventListener('click', e => {
    const add = e.target.closest('[data-add]');
    if (!add) return;
    const c = _cases.find(x => x.id === +add.dataset.add);
    if (c) { _suiteSel.push({ ...c }); renderSuiteModal(); }
  });
  $('#suMSelected').addEventListener('click', e => {
    const rm = e.target.closest('[data-rm]');
    if (rm) { _suiteSel.splice(+rm.dataset.rm, 1); renderSuiteModal(); }
  });
  bindNativeDnD($('#suMSelected'), (from, to) => {
    const [c] = _suiteSel.splice(from, 1);
    _suiteSel.splice(from < to ? to - 1 : to, 0, c);
    renderSuiteModal();
  });
  $('#suMSave').addEventListener('click', saveSuite);
  $('#suMCancel').addEventListener('click', () => $('#suiteMask').classList.remove('show'));
  $('#suiteMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });

  await loadOrchData();
  await renderSuites();
}
