/* AppUI 用例编排 / 测试用例 / 测试套件 · 面板逻辑
   （布局与产品模型对齐 testhub SceneBuilder：用例 = 元素 + 页面操作的有序组合）
   ------------------------------------------------------------------
   与 testhub 的对应与适配：
   - 左「操作面板」（14 种页面操作，同定位器 STEP_TYPES 词表）+ 中「步骤画布」+ 右「参数配置」；
   - 步骤引用的元素来自定位器/元素管理同一份元素库（保存时校验元素在所选元素文件里）；
   - 保存时后端把编排编译成框架三件套（页面+用例文件）接入现有 Appium/pytest 执行与报告链路；
   - 套件 = 有序用例集合，按编译产物 nodeid 顺序执行，统计读时惰性同步。
   依赖 app.js 公共件：$ / api / postJson / del / esc / toast / confirmModal / statusBadge / showRunPanel。 */
'use strict';

const AT_PREFIX = '/app-testing';
let _orchSteps = [];       // 当前编排的步骤 [{type, element, param, desc}]
let _orchSelStep = -1;     // 画布中选中的步骤下标（-1 = 未选，右栏显示用例信息）
let _orchMeta = null;      // 正在编辑用例的原始信息
let _orchCaseId = 0;       // 正在编辑的用例 id（0 = 新建）
let _atElements = [];        // 元素库（定位器/元素管理同一份数据）
let _atElFiles = [];         // 元素文件清单
let _cases = [];           // 用例列表（用例面板 / 套件弹窗共用）
let _projects = [];        // 项目列表（项目管理面板 / 各处项目下拉共用）
let _projId = 0;           // 弹窗正在编辑的项目 id（0 = 新建）
let _suiteSel = [];        // 套件弹窗已选用例 [{id, name, step_count}]
let _suiteId = 0;          // 弹窗正在编辑的套件 id（0 = 新建）

/* 操作词表（与 element_locator.case_generator.STEP_TYPES 一致） */
const STEP_META = {
  click:         { label: '点击元素',   group: '基本操作',   el: true,  param: null },
  input:         { label: '输入文本',   group: '基本操作',   el: true,  param: '输入内容' },
  long_press:    { label: '长按元素',   group: '基本操作',   el: true,  param: null },
  tap:           { label: '点击坐标',   group: '基本操作',   el: false, param: '坐标 x,y' },
  assert_visible:{ label: '断言出现',   group: '断言',       el: true,  param: null },
  assert_text:   { label: '断言文本',   group: '断言',       el: true,  param: '期望文本' },
  assert_toast:  { label: '断言 Toast', group: '断言',       el: false, param: 'toast 文本' },
  assert_gone:   { label: '断言消失',   group: '断言',       el: true,  param: null },
  wait_element:  { label: '等待出现',   group: '等待与分支', el: true,  param: '最长等待秒（默认60）' },
  if_click:      { label: '出现才点击', group: '等待与分支', el: true,  param: '探测秒（默认3）' },
  sleep:         { label: '固定等待',   group: '等待与分支', el: false, param: '秒数' },
  hide_keyboard: { label: '收起键盘',   group: '等待与分支', el: false, param: null },
  screenshot:    { label: '截图',       group: '其他',       el: false, param: '截图标签（可选）' },
  custom:        { label: '自定义代码', group: '其他',       el: false, param: '一行 Python 代码' },
};
const STEP_GROUPS = ['基本操作', '断言', '等待与分支', '其他'];

function stepLabel(type) { return (STEP_META[type] || {}).label || type; }

/* ================= 工具 ================= */
function fmtTs(ts) {
  return ts ? new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false }) : '—';
}

function suiteResultHtml(s) {
  /* NOT_RUN 复用 PENDING 徽章样式（statusBadge 只认 PENDING/RUNNING/PASSED/FAILED/ERROR） */
  const raw = s.execution_result || s.execution_status || 'NOT_RUN';
  return statusBadge(raw === 'NOT_RUN' ? 'PENDING' : raw);
}

function projName(id) {
  const p = _projects.find(x => x.id === +id);
  return p ? p.name : '';
}

/* ================= 项目管理（对齐 testhub APP项目管理：搜索/全列/详情/分页） ================= */
let _projFilters = { name: '', status: '' };
let _projPage = 1, _projPageSize = 20;

async function loadProjects() {
  const d = await api(AT_PREFIX + '/api/projects');
  if (!d.ok) return toast(d.msg || '项目加载失败', false);
  _projects = d.results || [];
  fillProjectSelects();
  renderProjects();
}

/* 各处项目下拉：筛选用（全部项目 / 未分组 / 各项目），归属用（未分组 / 各项目）。
   只重建选项并尽量保留当前选中值，不打断正在填的表单。 */
function fillProjectSelects() {
  const fill = (sel, opts) => {
    const cur = sel.value;
    sel.innerHTML = opts.map(o =>
      '<option value="' + esc(o.v) + '"' + (String(o.v) === cur ? ' selected' : '') + '>' + esc(o.t) + '</option>').join('');
    if (cur && sel.value !== cur) sel.value = cur;   // 选项仍在则保住原选择
  };
  const projOpts = _projects.map(p => ({ v: p.id, t: p.name }));
  fill($('#orchProj'), [{ v: '', t: '— 未分组 —' }].concat(projOpts));
  fill($('#suMProj'), [{ v: '', t: '— 未分组 —' }].concat(projOpts));
  fill($('#clProj'), [{ v: '', t: '全部项目' }, { v: 'none', t: '未分组' }].concat(projOpts));
  fill($('#suiteProj'), [{ v: '', t: '全部项目' }, { v: 'none', t: '未分组' }].concat(projOpts));
}

function matchProj(item, filterVal) {
  /* 列表按项目过滤：'' = 全部，'none' = 未分组，其余 = 项目 id */
  if (!filterVal) return true;
  if (filterVal === 'none') return !item.project_id;
  return +item.project_id === +filterVal;
}

function _projFiltered() {
  return _projects.filter(p =>
    (!_projFilters.name || (p.name || '').toLowerCase().includes(_projFilters.name)) &&
    (!_projFilters.status || (p.status || '进行中') === _projFilters.status));
}

function renderProjects() {
  const list = _projFiltered();
  const pages = Math.max(1, Math.ceil(list.length / _projPageSize));
  if (_projPage > pages) _projPage = pages;
  const view = list.slice((_projPage - 1) * _projPageSize, _projPage * _projPageSize);
  $('#projEmpty').style.display = list.length ? 'none' : '';
  $('#projTbody').innerHTML = view.map(p =>
    '<tr><td><b>' + esc(p.name) + '</b></td>' +
    '<td>' + esc(p.description || '—') + '</td>' +
    '<td><span class="proj-status">' + esc(p.status || '进行中') + '</span></td>' +
    '<td>' + (p.case_count || 0) + '</td>' +
    '<td>' + (p.suite_count || 0) + '</td>' +
    '<td>' + esc(p.owner || p.created_by || '—') + '</td>' +
    '<td>' + fmtTs(p.created_at) + '</td>' +
    '<td class="ops"><button class="mini" data-detail="' + p.id + '">详情</button>' +
    '<button class="ghost mini" data-edit="' + p.id + '">编辑</button>' +
    '<button class="danger mini" data-del="' + p.id + '">删除</button></td></tr>').join('');
  /* 分页条：共 N 条 · 第 x/y 页 */
  $('#projPagerInfo').textContent = '共 ' + list.length + ' 条';
  $('#projPageNow').textContent = _projPage + ' / ' + pages;
  $('#btnProjPrev').disabled = _projPage <= 1;
  $('#btnProjNext').disabled = _projPage >= pages;
}

function _projQuery(reset) {
  if (reset) {
    $('#projSearchName').value = '';
    $('#projSearchStatus').value = '';
    _projFilters = { name: '', status: '' };
  } else {
    _projFilters = { name: ($('#projSearchName').value || '').trim().toLowerCase(),
                     status: $('#projSearchStatus').value };
  }
  _projPage = 1;
  renderProjects();
}

function openProjModal(pid) {
  _projId = +pid || 0;
  const p = _projects.find(x => x.id === _projId);
  $('#projModalTitle').textContent = _projId ? '编辑项目' : '新建项目';
  $('#pjMName').value = p ? p.name : '';
  $('#pjMOwner').value = p ? (p.owner || p.created_by || '') : '';
  $('#pjMStatus').value = p ? (p.status || '进行中') : '进行中';
  $('#pjMDesc').value = p ? (p.description || '') : '';
  $('#projMask').classList.add('show');
  $('#pjMName').focus();
}

async function saveProj() {
  const name = ($('#pjMName').value || '').trim();
  if (!name) return toast('请填写项目名称', false);
  const body = { name, description: $('#pjMDesc').value.trim(),
                 owner: $('#pjMOwner').value.trim(), status: $('#pjMStatus').value };
  const d = _projId ? await api(AT_PREFIX + '/api/projects/' + _projId,
    { method: 'PUT', body: JSON.stringify(body) })
    : await postJson(AT_PREFIX + '/api/projects', body);
  if (!d.ok) return toast(d.msg || '保存失败', false);
  $('#projMask').classList.remove('show');
  toast('项目已保存', true);
  await loadProjects();
  renderCaseList();
  renderSuites();
}

async function openProjDetail(pid) {
  const p = _projects.find(x => x.id === +pid);
  if (!p) return;
  const [cd, sd] = await Promise.all([
    api(AT_PREFIX + '/api/cases'), api(AT_PREFIX + '/api/suites')]);
  const cases = (cd.ok ? cd.results : []).filter(c => +c.project_id === +pid);
  const suites = (sd.ok ? sd.results : []).filter(s => +s.project_id === +pid);
  $('#pjdTitle').textContent = '项目详情 · ' + p.name;
  $('#pjdMeta').innerHTML =
    '状态 <b>' + esc(p.status || '进行中') + '</b> · 负责人 <b>' + esc(p.owner || p.created_by || '—') + '</b>' +
    (p.description ? ' · ' + esc(p.description) : '');
  $('#pjdCaseCount').textContent = cases.length + ' 个';
  $('#pjdSuiteCount').textContent = suites.length + ' 个';
  $('#pjdCases').innerHTML = cases.length ? cases.map(c =>
    '<div class="orch-add">' + esc(c.name) + ' <span class="muted">(' + (c.steps || []).length + ' 步)</span></div>').join('')
    : '<div class="orch-empty">项目下还没有用例</div>';
  $('#pjdSuites').innerHTML = suites.length ? suites.map(s =>
    '<div class="orch-add">' + esc(s.name) + ' <span class="muted">(' + (s.case_ids || []).length + ' 个用例)</span></div>').join('')
    : '<div class="orch-empty">项目下还没有套件</div>';
  $('#projDetailMask').classList.add('show');
}

async function deleteProj(pid) {
  const p = _projects.find(x => x.id === +pid);
  if (!p) return;
  const ok = await confirmModal('删除项目「' + p.name + '」',
    '将级联删除：' + (p.case_count || 0) + ' 个用例（生成的页面/用例文件一并清理）、' +
    (p.suite_count || 0) + ' 个套件；其他套件里对这些用例的引用同步移除。此操作不可恢复。', true);
  if (!ok) return;
  const d = await del(AT_PREFIX + '/api/projects/' + pid);
  toast(d.ok ? (d.msg || '已删除') : (d.msg || '删除失败'), d.ok);
  if (d.ok) {
    await loadProjects();
    await loadOrchData();
    if (_orchCaseId && !_cases.some(c => c.id === _orchCaseId)) selectOrchCase(0);   // 正在编辑的用例随项目删除 → 重置表单
    renderCaseList();
    renderSuites();
  }
}

/* ================= 新建用例弹窗（测试用例模块 · 三栏） =================
   左：设备截图（滚轮/按钮缩放，点击拾取元素）；中：元素坐标定位（命中坐标/边界/定位候选）；
   右：元素 + 用例 + 页面操作 表单。截图与元素树复用元素定位器 /locator/api/refresh，
   元素落库复用 /locator/api/add_element，保存走 /app-testing/api/cases 编译生成三件套。 */
let _cnAll = [];          // 定位器扁平节点（bounds_num / locators）
let _cnZoomPct = 100;     // 截图缩放百分比（100 = 适应容器宽）
let _cnSteps = [];        // 步骤 [{type, element, param, desc}]
let _cnPicked = {};       // 拾取元素：name -> {locator_type, value}
let _cnSelNode = null;    // 当前命中节点

function openCnModal() {
  _cnSteps = []; _cnPicked = {}; _cnSelNode = null; _cnAll = []; _cnZoomPct = 100;
  $('#cnName').value = ''; $('#cnBy').value = ''; $('#cnDesc').value = '';
  $('#cnElName').value = ''; $('#cnElLocVal').value = ''; $('#cnElComment').value = '';
  $('#cnElWait').value = 'VISIBILITY_OF'; $('#cnElWaitSec').value = 6;
  $('#cnImg').style.display = 'none'; $('#cnImg').style.width = ''; $('#cnImg').src = '';
  $('#cnSelBox').style.display = 'none';
  $('#cnEmptyHint').style.display = '';
  $('#cnPickInfo').style.display = 'none';
  $('#cnEmptyMid').style.display = '';
  $('#cnDeviceInfo').textContent = '未获取截图';
  $('#cnElLocType').innerHTML = ['ID', 'XPATH', 'ACCESSIBILITY_ID', 'ANDROID_UIAUTOMATOR'].map(t =>
    '<option value="' + t + '">' + t + '</option>').join('');
  $('#cnElemFile').innerHTML = _atElFiles.filter(f => !f.includes('_backup')).map(f =>
    '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('');
  $('#cnProj').innerHTML = '<option value="">— 未分组 —</option>' +
    _projects.map(p => '<option value="' + p.id + '">' + esc(p.name) + '</option>').join('');
  $('#cnStepType').innerHTML = Object.keys(STEP_META).map(t =>
    '<option value="' + t + '">' + STEP_META[t].label + '</option>').join('');
  $('#cnPageFile').value = '';
  syncCnParam();
  renderCnSteps();
  $('#caseNewMask').classList.add('show');
  cnShot();
}

function cnShot() {
  $('#cnDeviceInfo').textContent = '截图获取中…';
  fetch('/locator/api/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    .then(r => r.json())
    .then(d => {
      if (!d.ok || !d.screenshot) { $('#cnDeviceInfo').textContent = d.msg || '截图失败（未连接设备？）'; return; }
      _cnAll = d.all || [];
      const img = $('#cnImg');
      img.style.width = _cnZoomPct + '%';
      img.src = d.screenshot;
      img.style.display = '';
      $('#cnEmptyHint').style.display = 'none';
      $('#cnSelBox').style.display = 'none';
      _cnSelNode = null;
      $('#cnPickInfo').style.display = 'none';
      $('#cnEmptyMid').style.display = '';
      $('#cnDeviceInfo').textContent = ((d.device && (d.device.model || d.device.serial)) || '') +
        ' · ' + d.width + '×' + d.height + (_qcSize(_cnAll) ? ' · ' + _qcSize(_cnAll) : '');
      $('#cnDeviceInfo').title = _cnAll.length + ' 个可定位节点；滚轮或 ＋/－ 缩放截图';
    })
    .catch(e => { $('#cnDeviceInfo').textContent = '元素定位器不可达（' + e.message + '）'; });
}
function _qcSize(arr) { return arr.length ? arr.length + ' 个节点' : ''; }

function cnZoom(delta) {
  const img = $('#cnImg');
  if (img.style.display === 'none') return;
  _cnZoomPct = Math.min(400, Math.max(40, _cnZoomPct + delta));
  img.style.width = _cnZoomPct + '%';
}
function cnZoomReset() {
  const img = $('#cnImg');
  if (img.style.display === 'none') return;
  _cnZoomPct = 100;
  img.style.width = '100%';
}

function cnPick(e) {
  const img = $('#cnImg');
  if (!img.naturalWidth || !_cnAll.length) return;
  const rect = img.getBoundingClientRect();
  const scale = rect.width / img.naturalWidth;
  const dx = (e.clientX - rect.left) / scale, dy = (e.clientY - rect.top) / scale;
  /* 命中包含坐标的最小节点（bounds [l,t,r,b] 为设备坐标） */
  let best = null, bestArea = Infinity;
  _cnAll.forEach(n => {
    const b = n.bounds_num || (n.center ? [n.center[0] - 1, n.center[1] - 1, n.center[0] + 1, n.center[1] + 1] : null);
    if (!b) return;
    if (dx >= b[0] && dx <= b[2] && dy >= b[1] && dy <= b[3]) {
      const area = (b[2] - b[0]) * (b[3] - b[1]);
      if (area < bestArea) { bestArea = area; best = n; }
    }
  });
  _cnSelNode = best;
  const box = $('#cnSelBox');
  if (!best) { box.style.display = 'none'; toast('该位置没有可定位的元素，试试相邻元素', false); return; }
  const b = best.bounds_num;
  box.style.display = '';
  box.style.left = (b[0] * scale) + 'px';
  box.style.top = (b[1] * scale) + 'px';
  box.style.width = ((b[2] - b[0]) * scale) + 'px';
  box.style.height = ((b[3] - b[1]) * scale) + 'px';
  /* 中栏：坐标 + 边界 + 定位候选 */
  $('#cnPickInfo').style.display = '';
  $('#cnEmptyMid').style.display = 'none';
  const cx = Math.round((b[0] + b[2]) / 2), cy = Math.round((b[1] + b[3]) / 2);
  $('#cnCoord').value = cx + ', ' + cy;
  $('#cnBounds').value = b.join(', ');
  const cands = (best.locators || []).filter(l => l.value);
  $('#cnLocator').innerHTML = cands.map((l, i) =>
    '<option value="' + i + '">' + esc((l.desc || l.locator_type) + '：' + String(l.value).slice(0, 42)) + '</option>').join('') ||
    '<option value="">（该节点无可用定位）</option>';
  $('#cnLocVal').value = cands[0] ? cands[0].value : '';
  cnApply();                                    // 点中即回显到右侧表单
}

/* 中栏选中内容 → 回显右侧表单（① 元素：名称/定位方式/定位值 + ③ 步骤描述建议） */
function cnApply() {
  const n = _cnSelNode;
  if (!n) return toast('请先点击截图中的元素', false);
  const li = +$('#cnLocator').value;
  const cand = (n.locators || [])[li];
  if (cand && cand.value) {
    $('#cnLocVal').value = cand.value;
    const sel = $('#cnElLocType');
    if (![...sel.options].some(o => o.value === cand.locator_type))
      sel.insertAdjacentHTML('beforeend', '<option value="' + esc(cand.locator_type) + '">' + esc(cand.locator_type) + '</option>');
    sel.value = cand.locator_type;
    $('#cnElLocVal').value = cand.value;
    const sug = (n.text || '').trim() || ((n['resource-id'] || '').split('/').pop() || '').trim();
    if (!$('#cnElName').value.trim())
      $('#cnElName').value = sug.replace(/[^A-Za-z0-9_\u4e00-\u9fa5]/g, '_').replace(/^_+|_+$/g, '').slice(0, 30);
    if (!$('#cnStepDesc').value.trim())
      $('#cnStepDesc').value = (n.text || '').trim() ? '点击「' + n.text.trim() + '」' : '';
  } else {
    toast('该节点没有可用定位，换候选或相邻元素', false);
  }
}

function syncCnParam() {
  const meta = STEP_META[$('#cnStepType').value] || {};
  $('#cnStepParam').style.display = meta.param ? '' : 'none';
  $('#cnStepParamLabel').textContent = '操作参数' + (meta.param ? '：' + meta.param : '');
}

function cnAddStep() {
  const name = ($('#cnElName').value || '').trim();
  const locType = ($('#cnElLocType').value || '').trim();
  const locVal = ($('#cnElLocVal').value || '').trim();
  if (!name) return toast('请填写元素名称', false);
  if (!locVal) return toast('请先点击截图中的元素回显定位，或手填定位值', false);
  const type = $('#cnStepType').value;
  const meta = STEP_META[type] || {};
  if (meta.el === false) return toast('该操作不需要元素，请改用「用例编排」面板添加', false);
  const param = $('#cnStepParam').style.display !== 'none' ? $('#cnStepParam').value.trim() : '';
  _cnPicked[name] = {
    locator_type: locType, value: locVal,
    wait_type: $('#cnElWait').value,
    wait_seconds: +$('#cnElWaitSec').value || null,
    comment: ($('#cnElComment').value || '').trim(),
  };
  _cnSteps.push({ type, element: name, param, desc: $('#cnStepDesc').value.trim() || (meta.label + ' ' + name) });
  $('#cnSelBox').style.display = 'none';
  _cnSelNode = null;
  renderCnSteps();
  toast('已加入第 ' + _cnSteps.length + ' 步：' + (meta.label || type) + ' ' + name, true);
}

function renderCnSteps() {
  const box = $('#cnSteps');
  if (!box) return;
  const count = $('#cnStepCount');
  if (count) count.textContent = _cnSteps.length ? '（共 ' + _cnSteps.length + ' 步）' : '';
  if (!_cnSteps.length) {
    box.innerHTML = '<div class="orch-empty">还没有步骤 —— 点左侧截图元素回显定位，「＋ 加入步骤」</div>';
    return;
  }
  box.innerHTML = _cnSteps.map((s, i) => {
    const meta = STEP_META[s.type] || {};
    return '<div class="cnstep">' +
      '<span class="orch-index">' + (i + 1) + '</span>' +
      '<span class="cn-step-type" title="' + esc(meta.label || s.type) + '">' + esc(meta.label || s.type) + '</span>' +
      '<span class="cn-step-el" title="' + esc(s.element) + '">' + esc(s.element) + '</span>' +
      '<span class="cn-step-param muted" title="' + esc(s.desc || '') + '">' + esc(s.param || s.desc || '—') + '</span>' +
      '<button class="orch-del" data-rm="' + i + '" title="移除">✕</button></div>';
  }).join('');
}

async function saveCnCase() {
  const name = ($('#cnName').value || '').trim();
  const elementsFile = $('#cnElemFile').value;
  if (!name) return toast('请填写用例名称', false);
  if (!elementsFile) return toast('请选择写入元素文件', false);
  if (!_cnSteps.length) return toast('请至少加入一个步骤（点左侧截图拾取元素）', false);
  /* 1) 拾取的元素先入元素库（含等待方式/时间/备注）；命中重复定位自动复用已有元素 */
  for (const [en, loc] of Object.entries(_cnPicked)) {
    const r = await fetch('/locator/api/add_element', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: elementsFile, name: en,
        locator_type: loc.locator_type, value: loc.value,
        wait_type: loc.wait_type || 'VISIBILITY_OF', wait_seconds: loc.wait_seconds,
        comment: loc.comment }),
    }).then(x => x.json());
    if (!r.ok && r.duplicate && r.duplicate.name) {
      const old = en;
      _cnSteps.forEach(s => { if (s.element === old) s.element = r.duplicate.name; });
      delete _cnPicked[old];
    } else if (!r.ok) {
      return toast('元素「' + en + '」入库失败：' + (r.msg || '未知错误'), false);
    }
  }
  /* 2) 创建用例（后端校验元素存在性并编译生成 页面+用例 文件） */
  const body = { name, description: ($('#cnDesc').value || '').trim(),
                 created_by: ($('#cnBy').value || '').trim(),
                 project_id: $('#cnProj').value || null,
                 elements_file: elementsFile,
                 steps: _cnSteps.map(s => ({ type: s.type, element: s.element, param: s.param, desc: s.desc })) };
  const d = await postJson(AT_PREFIX + '/api/cases', body);
  if (!d.ok) return toast(d.msg || '保存失败', false);
  $('#caseNewMask').classList.remove('show');
  toast('用例「' + name + '」已创建并编译生成执行文件', true);
  await loadOrchData();
  renderCaseList();
  renderSuites();
}

/* ================= 用例编排（SceneBuilder：顶栏 + 三栏） ================= */
function renderPalette() {
  const box = $('#orchTree');
  let html = '';
  STEP_GROUPS.forEach(g => {
    html += '<div class="palette-group">' + g + '</div><div class="palette-items">';
    Object.keys(STEP_META).filter(t => STEP_META[t].group === g).forEach(t => {
      html += '<span class="palette-item orch-add" draggable="true" data-type="' + t + '" title="' +
        STEP_META[t].label + '">' + STEP_META[t].label + '</span>';
    });
    html += '</div>';
  });
  box.innerHTML = html;
}

function renderOrchSteps() {
  const box = $('#orchSteps');
  if (!_orchSteps.length) {
    box.innerHTML = '<div class="orch-empty">从左侧点选操作加入步骤并选元素；拖拽可调整顺序，点步骤卡在右栏配置</div>';
    return;
  }
  box.innerHTML = _orchSteps.map((s, i) => {
    const meta = STEP_META[s.type] || {};
    const miss = (meta.el && !s.element) ? ' missing' : '';
    return '<div class="orch-step' + (i === _orchSelStep ? ' active' : '') + miss + '" draggable="true" data-idx="' + i + '">' +
      '<span class="drag-handle">⋮⋮</span><span class="orch-index">' + (i + 1) + '</span>' +
      '<span class="orch-step-name">' + esc(s.desc || meta.label || s.type) + '</span>' +
      '<span class="orch-step-node">' + esc((meta.label || s.type) + (s.element ? ' · ' + s.element : '')) + '</span>' +
      '<button class="orch-mini" data-dup="' + i + '" title="复制此步骤">⧉</button>' +
      '<button class="orch-del" data-del="' + i + '" title="移除">✕</button></div>';
  }).join('');
}

function _elementOptions(selected) {
  const file = $('#orchElemFile').value;
  const pool = _atElements.filter(e => !file || e.file === file);
  return '<option value="">— 选择元素 —</option>' +
    pool.map(e => '<option value="' + esc(e.name) + '"' +
      (e.name === selected ? ' selected' : '') + '>' + esc(e.name) +
      (e.desc ? '（' + esc(e.desc) + '）' : '') + '</option>').join('');
}

function renderOrchCfg() {
  const box = $('#orchCfg'), title = $('#orchCfgTitle');
  if (_orchSelStep >= 0 && _orchSteps[_orchSelStep]) {
    const s = _orchSteps[_orchSelStep];
    const meta = STEP_META[s.type] || { param: null };
    title.textContent = '步骤配置 · 第 ' + (_orchSelStep + 1) + ' 步';
    box.innerHTML =
      '<div class="field"><label>操作类型</label>' +
      '<select id="cfgType">' + Object.keys(STEP_META).map(t =>
        '<option value="' + t + '"' + (t === s.type ? ' selected' : '') + '>' + STEP_META[t].label + '</option>').join('') + '</select></div>' +
      '<div class="field"><label>元素（来自元素库）</label>' +
      '<select id="cfgElement">' + _elementOptions(s.element) + '</select></div>' +
      (meta.param
        ? '<div class="field"><label>参数：' + meta.param + '</label>' +
          '<input type="text" id="cfgParam" value="' + esc(s.param || '') + '" placeholder="' + esc(meta.param) + '"></div>'
        : '') +
      '<div class="field"><label>步骤描述（用例与报告里展示）</label>' +
      '<input type="text" id="cfgDesc" value="' + esc(s.desc || '') + '" placeholder="缺省自动生成"></div>' +
      '<div class="orchops"><button class="danger mini" id="cfgDel">删除此步骤</button></div>';
    $('#cfgType').addEventListener('change', () => { s.type = $('#cfgType').value; renderOrchCfg(); renderOrchSteps(); });
    $('#cfgElement').addEventListener('change', () => { s.element = $('#cfgElement').value; renderOrchSteps(); });
    const pi = $('#cfgParam');
    if (pi) pi.addEventListener('input', () => { s.param = pi.value; });
    $('#cfgDesc').addEventListener('input', () => { s.desc = $('#cfgDesc').value; renderOrchSteps(); });
    $('#cfgDel').addEventListener('click', () => removeStep(_orchSelStep));
  } else {
    title.textContent = '用例信息';
    box.innerHTML = (_orchCaseId
      ? '<div class="cfg-meta">元素文件 <b>' + esc(_orchMeta && _orchMeta.elements_file || '—') + '</b></div>' +
        '<div class="cfg-meta">步骤数 <b>' + _orchSteps.length + '</b></div>' +
        '<div class="cfg-meta">创建人 <b>' + esc(_orchMeta && _orchMeta.created_by || '—') + '</b></div>' +
        '<div class="cfg-meta">创建时间 <b>' + fmtTs(_orchMeta && _orchMeta.created_at) + '</b></div>'
      : '<div class="cfg-meta muted">新用例 —— 顶栏选元素文件并填名称，点左侧操作编排步骤后「保存用例」</div>') +
      '<p class="muted" style="font-size:12px">保存时平台会把编排编译成页面 + 用例文件（元素只引用不复制），自动进入「选择用例」与执行链路。</p>';
  }
}

function selectStep(i) {
  _orchSelStep = (i === _orchSelStep ? -1 : i);
  renderOrchSteps();
  renderOrchCfg();
}

function moveStep(from, to) {
  const [s] = _orchSteps.splice(from, 1);
  _orchSteps.splice(from < to ? to - 1 : to, 0, s);
  if (_orchSelStep === from) _orchSelStep = from < to ? to - 1 : to;
  else if (from < to && _orchSelStep > from && _orchSelStep <= to) _orchSelStep--;
  else if (from > to && _orchSelStep >= to && _orchSelStep < from) _orchSelStep++;
  renderOrchSteps();
}

function removeStep(i) {
  _orchSteps.splice(i, 1);
  if (_orchSelStep === i) _orchSelStep = -1;
  else if (_orchSelStep > i) _orchSelStep--;
  renderOrchSteps();
  renderOrchCfg();
}

function addOrchStep(type, at) {
  const step = { type, element: '', param: '', desc: '' };
  if (at === undefined || at >= _orchSteps.length) _orchSteps.push(step);
  else _orchSteps.splice(at, 0, step);
  _orchSelStep = _orchSteps.indexOf(step);
  renderOrchSteps();
  renderOrchCfg();
}

async function loadOrchData() {
  const [el, cases] = await Promise.all([api('/api/appui/elements'), api(AT_PREFIX + '/api/cases')]);
  _atElements = el.ok ? (el.elements || []) : [];
  _atElFiles = el.ok ? (el.files || []) : [];
  _cases = cases.ok ? (cases.results || []) : [];
  const cur = $('#orchElemFile').value;
  $('#orchElemFile').innerHTML = '<option value="">— 选择元素文件 —</option>' +
    _atElFiles.filter(f => !f.includes('_backup')).map(f =>
      '<option value="' + esc(f) + '"' + (f === cur ? ' selected' : '') + '>' + esc(f) + '</option>').join('');
  refreshOrchCaseOptions();
  renderOrchSteps();
  renderOrchCfg();
}

function refreshOrchCaseOptions() {
  /* 只重建下拉选项（不动正在编辑的表单/画布），保持当前选中项 */
  const sel = $('#orchSel');
  sel.innerHTML = '<option value="">＋ 新建用例</option>' +
    _cases.map(c => '<option value="' + c.id + '">' + esc(c.name) + '（' + (c.steps || []).length + ' 步）</option>').join('');
  if (_orchCaseId && _cases.some(c => c.id === _orchCaseId)) sel.value = _orchCaseId;
}

function selectOrchCase(id) {
  _orchCaseId = +id || 0;
  const c = _cases.find(x => x.id === _orchCaseId);
  _orchSteps = c ? (c.steps || []).map(s => ({
    type: s.type, element: s.element || '', param: s.param || '', desc: s.desc || '' })) : [];
  _orchMeta = c || null;
  _orchSelStep = -1;
  $('#orchName').value = c ? c.name : '';
  $('#orchDesc').value = c ? (c.description || '') : '';
  $('#orchBy').value = c && c.created_by ? c.created_by : '';
  if (c && c.elements_file) $('#orchElemFile').value = c.elements_file;
  $('#orchProj').value = c && c.project_id ? c.project_id : '';
  $('#btnOrchRun').disabled = !c;
  renderOrchSteps();
  renderOrchCfg();
}

async function saveOrchCase() {
  const name = ($('#orchName').value || '').trim();
  if (!name) return toast('请填写用例名称', false);
  if (!$('#orchElemFile').value) return toast('请选择元素文件（元素来自定位器采集的元素库）', false);
  if (!_orchSteps.length) return toast('请至少编排一个步骤', false);
  const body = { name, description: $('#orchDesc').value.trim(),
                 created_by: $('#orchBy').value.trim(),
                 project_id: $('#orchProj').value || '',
                 elements_file: $('#orchElemFile').value, steps: _orchSteps };
  const d = _orchCaseId ? await api(AT_PREFIX + '/api/cases/' + _orchCaseId,
    { method: 'PUT', body: JSON.stringify(body) })
    : await postJson(AT_PREFIX + '/api/cases', body);
  if (!d.ok) return toast(d.msg || '保存失败', false);
  toast('用例已保存并生成执行文件', true);
  await loadOrchData();
  $('#orchSel').value = d.case.id;
  selectOrchCase(d.case.id);
  renderCaseList();   // 「测试用例」列表与套件表中的用例名同步刷新
  renderSuites();
}

function _runBody() {
  return { conf_file: $('#suiteConf') ? $('#suiteConf').value : '',
           overrides: { udid: ($('#suiteUdid') && $('#suiteUdid').value.trim()) || '' },
           owner: ($('#suiteOwner') && $('#suiteOwner').value.trim()) || '' };
}

async function runOrchCase() {
  if (!_orchCaseId) return;
  const d = await postJson(AT_PREFIX + '/api/cases/' + _orchCaseId + '/run', _runBody());
  if (!d.ok) return toast(d.msg || '执行失败', false);
  /* 不跳转：留在编排页继续编辑，进度到「测试报告」面板或 /runs 详情看 */
  toast('用例已开始执行 → Run ' + d.run_id + '，进度见「测试报告」面板', true);
}

/* ================= 测试用例列表（TestCaseList） ================= */
async function renderCaseList() {
  const d = await api(AT_PREFIX + '/api/cases');
  if (!d.ok) return toast(d.msg || '用例加载失败', false);
  _cases = d.results || [];
  const kw = ($('#clSearch').value || '').trim().toLowerCase();
  const pf = $('#clProj') ? $('#clProj').value : '';
  const list = _cases.filter(c => matchProj(c, pf) &&
    (!kw || [c.name, c.description, c.created_by].some(v => String(v || '').toLowerCase().includes(kw))));
  $('#clEmpty').style.display = list.length ? 'none' : '';
  $('#clTbody').innerHTML = list.map(c =>
    '<tr><td><b>' + esc(c.name) + '</b>' +
    (c.description ? '<div class="path">' + esc(c.description) + '</div>' : '') + '</td>' +
    '<td>' + esc(projName(c.project_id) || '未分组') + '</td>' +
    '<td>' + (c.steps || []).length + ' 步<div class="path">' + esc(c.elements_file || '') + '</div></td>' +
    '<td>' + esc(c.created_by || '—') + '</td>' +
    '<td>' + fmtTs(c.created_at) + '</td>' +
    '<td class="ops"><button class="mini" data-orch="' + c.id + '">编排</button>' +
    '<button class="ghost mini" data-run="' + c.id + '">执行</button>' +
    '<button class="danger mini" data-del="' + c.id + '">删除</button></td></tr>').join('');
}

function goOrch(cid) {
  showRunPanel('orch');
  $('#orchSel').value = cid;
  selectOrchCase(cid);
}

async function runCaseById(cid) {
  const d = await postJson(AT_PREFIX + '/api/cases/' + cid + '/run', _runBody());
  if (!d.ok) return toast(d.msg || '执行失败', false);
  toast('用例已开始执行 → Run ' + d.run_id + '，进度见「测试报告」面板', true);
}

/* ================= 测试套件（SuiteList：配置卡 + 表格 + 双栏弹窗 + 历史） ================= */
async function loadSuiteConfs() {
  const d = await api('/api/confs');
  const confs = d.ok ? (d.confs || []) : [];
  $('#suiteConf').innerHTML = confs.map(c => {
    const dev = (c.devices || [])[0] || {};
    return '<option value="' + esc(c.file) + '">' + esc(c.file.split('/').pop()) +
      (dev.udid ? ' · ' + esc(dev.udid) : '') + '</option>';
  }).join('');
}

async function renderSuites() {
  const d = await api(AT_PREFIX + '/api/suites');
  if (!d.ok) return toast(d.msg || '套件加载失败', false);
  const pf = $('#suiteProj') ? $('#suiteProj').value : '';
  const list = (d.results || []).filter(s => matchProj(s, pf));
  $('#suiteEmpty').style.display = list.length ? 'none' : '';
  $('#suiteTbody').innerHTML = list.map(s => {
    const stats = (s.execution_status === 'NOT_RUN') ? '—' :
      '<b class="num-ok">' + (s.passed_count || 0) + '</b> / <b class="num-bad">' + (s.failed_count || 0) + '</b>';
    const detail = (s.cases || []).map(c => esc(c.name)).join('、') || '<span class="muted">未选用例</span>';
    const proj = projName(s.project_id);
    return '<tr>' +
      '<td><b>' + esc(s.name) + '</b>' +
      ((proj || s.description) ? '<div class="path">' + esc([proj && '项目：' + proj, s.description].filter(Boolean).join(' · ')) + '</div>' : '') + '</td>' +
      '<td>' + (s.cases || []).length + ' 个<div class="path" style="max-width:260px">' + detail + '</div></td>' +
      '<td>' + statusBadge(s.execution_status) + '</td>' +
      '<td>' + suiteResultHtml(s) + '</td>' +
      '<td>' + stats + '</td>' +
      '<td>' + fmtTs(s.last_run_at) + '</td>' +
      '<td class="ops"><button class="mini" data-run="' + s.id + '">执行</button>' +
      '<button class="ghost mini" data-edit="' + s.id + '">编辑</button>' +
      '<button class="ghost mini" data-hist="' + s.id + '">历史</button>' +
      '<button class="danger mini" data-del="' + s.id + '">删除</button></td></tr>';
  }).join('');
}

function renderSuiteModal() {
  const kw = ($('#suMSearch').value || '').trim().toLowerCase();
  const selIds = new Set(_suiteSel.map(c => c.id));
  /* 套件选了项目 → 可选用例只列同项目与未分组（跨项目用例不允许混入） */
  const pj = $('#suMProj') ? $('#suMProj').value : '';
  const avail = _cases.filter(c => !selIds.has(c.id) && matchProj(c, pj) &&
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
    '<span class="orch-step-node">' + (c.step_count != null ? c.step_count : (c.steps || []).length) + ' 步</span>' +
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
    $('#suMProj').value = d.suite.project_id || '';
    _suiteSel = (d.suite.cases || []).map(c => ({ ...c }));
  } else {
    $('#suiteModalTitle').textContent = '新建套件';
    $('#suMName').value = '';
    $('#suMDesc').value = '';
    $('#suMProj').value = $('#suiteProj').value !== 'none' ? $('#suiteProj').value : '';
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
                 project_id: $('#suMProj').value || '',
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
  const d = await postJson(AT_PREFIX + '/api/suites/' + sid + '/run', _runBody());
  if (!d.ok) return toast(d.msg || '执行失败', false);
  toast('套件已开始执行 → Run ' + d.run_id + '，稍后可看「历史」或「测试报告」', true);
  renderSuites();
  setTimeout(renderSuites, 3000);   // 3 秒后刷一次，把 RUNNING 状态刷出来（对齐 testhub 延迟刷新）
}

async function openSuiteHist(sid) {
  const d = await api(AT_PREFIX + '/api/suites/' + sid);
  if (!d.ok) return toast(d.msg || '历史加载失败', false);
  $('#histTitle').textContent = '执行历史 · ' + d.suite.name;
  const runs = d.suite.runs || [];
  $('#histTbody').innerHTML = runs.length ? runs.map(r =>
    '<tr><td>' + esc(r.run_id || '—') + '</td>' +
    '<td>' + fmtTs(r.start_time) + '</td>' +
    '<td>' + (r.status ? statusBadge(r.status) : statusBadge('RUNNING')) + '</td>' +
    '<td>' + (r.passed != null ? r.passed : '—') + '</td>' +
    '<td>' + (r.failed != null ? r.failed : '—') + '</td>' +
    '<td class="ops"><a class="ghost mini" href="/runs/' + esc(r.run_id) + '">查看详情</a></td></tr>').join('')
    : '<tr><td colspan="6" class="muted" style="text-align:center;padding:18px">该套件还没有执行记录</td></tr>';
  $('#histMask').classList.add('show');
}

/* ================= 原生拖拽（画布内排序 + 面板拖入） ================= */
function bindCanvasDnD(box, onReorder, onExternal) {
  let dragIdx = -1;
  box.addEventListener('dragstart', e => {
    const item = e.target.closest('.orch-step');
    if (item) {
      dragIdx = +item.dataset.idx;
      item.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      return;
    }
    const add = e.target.closest('.orch-add');   // 面板项拖入
    if (add) {
      e.dataTransfer.setData('text/plain', add.dataset.type || '');
      e.dataTransfer.effectAllowed = 'copy';
    }
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
    if (dragIdx >= 0) {                           // 画布内排序
      if (item && +item.dataset.idx !== dragIdx) onReorder(dragIdx, +item.dataset.idx);
      dragIdx = -1;
      return;
    }
    const type = e.dataTransfer.getData('text/plain');   // 面板拖入
    if (type && STEP_META[type] && onExternal) onExternal(type, item ? +item.dataset.idx : undefined);
  });
}

/* ================= 面板初始化（initRun 调用） ================= */
async function appTestingInit() {
  if (!$('#panel-orch')) return;

  /* ---- 项目管理 ---- */
  $('#btnProjNew').addEventListener('click', () => openProjModal(0));
  $('#btnProjQuery').addEventListener('click', async () => { _projQuery(false); await loadProjects(); });
  $('#btnProjReset').addEventListener('click', async () => { _projQuery(true); await loadProjects(); });
  $('#projSearchName').addEventListener('keydown', e => { if (e.key === 'Enter') $('#btnProjQuery').click(); });
  $('#projPageSize').addEventListener('change', () => { _projPageSize = +$('#projPageSize').value || 20; _projPage = 1; renderProjects(); });
  $('#btnProjPrev').addEventListener('click', () => { if (_projPage > 1) { _projPage--; renderProjects(); } });
  $('#btnProjNext').addEventListener('click', () => { _projPage++; renderProjects(); });
  $('#projTbody').addEventListener('click', async e => {
    const detail = e.target.closest('[data-detail]'), edit = e.target.closest('[data-edit]'),
          delBtn = e.target.closest('[data-del]');
    if (detail) return openProjDetail(+detail.dataset.detail);
    if (edit) return openProjModal(+edit.dataset.edit);
    if (delBtn) return deleteProj(+delBtn.dataset.del);
  });
  $('#pjMSave').addEventListener('click', saveProj);
  $('#pjMCancel').addEventListener('click', () => $('#projMask').classList.remove('show'));
  $('#projMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });
  $('#pjdClose').addEventListener('click', () => $('#projDetailMask').classList.remove('show'));
  $('#projDetailMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });

  /* ---- 编排：顶栏 ---- */
  $('#orchSel').addEventListener('change', () => selectOrchCase($('#orchSel').value));
  $('#orchElemFile').addEventListener('change', () => { renderOrchCfg(); });
  $('#btnOrchSave').addEventListener('click', saveOrchCase);
  $('#btnOrchRun').addEventListener('click', runOrchCase);

  /* ---- 编排：左栏操作面板 ---- */
  renderPalette();
  $('#orchTree').addEventListener('click', e => {
    const add = e.target.closest('.orch-add');
    if (add) addOrchStep(add.dataset.type);
  });
  $('#orchTree').addEventListener('dragstart', e => {   // 拖入时的数据（与画布 drop 对接）
    const add = e.target.closest('.orch-add');
    if (add) {
      e.dataTransfer.setData('text/plain', add.dataset.type);
      e.dataTransfer.effectAllowed = 'copy';
    }
  });

  /* ---- 编排：中栏画布（点选 / 复制 / 删除 / 排序 / 拖入） ---- */
  $('#orchSteps').addEventListener('click', e => {
    const dup = e.target.closest('[data-dup]');
    if (dup) {
      const i = +dup.dataset.dup;
      _orchSteps.splice(i + 1, 0, { ..._orchSteps[i] });
      renderOrchSteps();
      return;
    }
    const del = e.target.closest('[data-del]');
    if (del) return removeStep(+del.dataset.del);
    const card = e.target.closest('.orch-step');
    if (card) selectStep(+card.dataset.idx);
  });
  bindCanvasDnD($('#orchSteps'), moveStep,
    (type, at) => { addOrchStep(type, at); });

  /* ---- 测试用例列表 ---- */
  $('#clSearch').addEventListener('input', renderCaseList);
  $('#clProj').addEventListener('change', renderCaseList);
  $('#btnClRefresh').addEventListener('click', renderCaseList);
  $('#btnClNew').addEventListener('click', openCnModal);

  /* ---- 新建用例弹窗（三栏：截图缩放拾取 / 元素坐标定位 / 表单） ---- */
  $('#btnCnShot').addEventListener('click', cnShot);
  $('#btnCnZoomIn').addEventListener('click', () => cnZoom(15));
  $('#btnCnZoomOut').addEventListener('click', () => cnZoom(-15));
  $('#btnCnZoomReset').addEventListener('click', cnZoomReset);
  $('#cnImgWrap').addEventListener('wheel', e => {
    if ($('#cnImg').style.display === 'none') return;
    e.preventDefault();
    cnZoom(e.deltaY < 0 ? 10 : -10);
  }, { passive: false });
  $('#cnImg').addEventListener('click', cnPick);
  $('#cnLocator').addEventListener('change', () => {
    const cand = (_cnSelNode && _cnSelNode.locators || []) [+$('#cnLocator').value];
    if (cand) { $('#cnLocVal').value = cand.value; cnApply(); }
  });
  $('#btnCnApply').addEventListener('click', cnApply);
  $('#cnStepType').addEventListener('change', syncCnParam);
  $('#btnCnAddStep').addEventListener('click', cnAddStep);
  $('#cnSteps').addEventListener('click', e => {
    const rm = e.target.closest('[data-rm]');
    if (rm) { _cnSteps.splice(+rm.dataset.rm, 1); renderCnSteps(); }
  });
  $('#cnSave').addEventListener('click', () => saveCnCase().catch(e => toast(e.message, false)));
  $('#cnCancel').addEventListener('click', () => $('#caseNewMask').classList.remove('show'));
  $('#caseNewMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });
  $('#clTbody').addEventListener('click', async e => {
    const orch = e.target.closest('[data-orch]'), run = e.target.closest('[data-run]'),
          del = e.target.closest('[data-del]');
    if (orch) return goOrch(+orch.dataset.orch);
    if (run) return runCaseById(+run.dataset.run);
    if (del) {
      const ok = await confirmModal('删除用例', '确定删除该用例？引用它的套件会同步移除该用例，生成的页面/用例文件也会一并清理。', true);
      if (!ok) return;
      const d = await del(AT_PREFIX + '/api/cases/' + del.dataset.del);
      toast(d.ok ? '已删除' : (d.msg || '删除失败'), d.ok);
      if (d.ok) {
        if (+del.dataset.del === _orchCaseId) selectOrchCase(0);   // 删的是正在编辑的用例 → 重置编排表单
        refreshOrchCaseOptions();
        renderCaseList();
        renderSuites();
      }
    }
  });

  /* ---- 套件：执行配置卡 + 表格 ---- */
  loadSuiteConfs();
  $('#suiteProj').addEventListener('change', renderSuites);
  $('#btnSuiteRefresh').addEventListener('click', renderSuites);
  $('#btnSuiteNew').addEventListener('click', () => openSuiteModal(0));
  $('#suiteTbody').addEventListener('click', async e => {
    const run = e.target.closest('[data-run]'), edit = e.target.closest('[data-edit]'),
          hist = e.target.closest('[data-hist]'), del = e.target.closest('[data-del]');
    if (run) return runSuite(+run.dataset.run);
    if (edit) return openSuiteModal(+edit.dataset.edit);
    if (hist) return openSuiteHist(+hist.dataset.hist);
    if (del) {
      const ok = await confirmModal('删除套件', '确定删除该套件？用例本身不受影响。', true);
      if (!ok) return;
      const d = await del(AT_PREFIX + '/api/suites/' + del.dataset.del);
      toast(d.ok ? '已删除' : (d.msg || '删除失败'), d.ok);
      renderSuites();
    }
  });

  /* ---- 套件：双栏编辑弹窗 ---- */
  $('#suMSearch').addEventListener('input', renderSuiteModal);
  $('#suMProj').addEventListener('change', renderSuiteModal);
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
  bindCanvasDnD($('#suMSelected'), (from, to) => {
    const [c] = _suiteSel.splice(from, 1);
    _suiteSel.splice(from < to ? to - 1 : to, 0, c);
    renderSuiteModal();
  });
  $('#suMSave').addEventListener('click', saveSuite);
  $('#suMCancel').addEventListener('click', () => $('#suiteMask').classList.remove('show'));
  $('#suiteMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });

  /* ---- 套件：执行历史弹窗 ---- */
  $('#histClose').addEventListener('click', () => $('#histMask').classList.remove('show'));
  $('#histMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });

  await loadProjects();
  await loadOrchData();
  await renderCaseList();
  await renderSuites();
}
