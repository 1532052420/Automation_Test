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
  fill($('#cnRegProj'), [{ v: '', t: '— 未分组 —' }].concat(projOpts));   // 新建用例弹窗 ④ 项目
  fill($('#mvProj'), [{ v: '', t: '— 未分组 —' }].concat(projOpts));      // 移动用例到项目弹窗
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
   完全照搬元素定位器「添加测试用例」弹窗（横改竖）：用途 ① 仅元素 / ② 元素+用例+操作；
   ① 元素（名称/定位方式/定位值/等待方式/等待时间/备注/写入元素文件，支持 ➕新建元素文件）；
   ② 用例（目标用例文件（支持 ➕新建，临时用例三件套打包入库）/ 目标测试方法 / 用例备注 / 插入位置 /
      当前用例步骤列表）；③ 操作（类型/参数/描述/写入页面文件）。
   数据与写入全部复用定位器接口：/locator/api/{cases,refresh,add_element,add_code,save_case_package}。 */
let _cnAll = [];          // 定位器扁平节点（bounds_num / locators）
let _cnZoomPct = 100;     // 截图缩放百分比（100 = 适应容器宽）
let _cnSelNode = null;    // 当前命中节点
let _cnCaseInfo = [];     // /locator/api/cases 三件套归属信息
let _cnCaseSel = null;    // 当前选中的目标用例信息
let _cnMethodSteps = [];  // 目标方法已有步骤描述列表
let _cnWritten = 0;       // 本次弹窗已写入的步骤数
let _cnTemp = null;       // 新建用例文件模式：临时步骤会话 {steps:[{comment,line,elemName,elemLine,methodBlock}]}
const CN_NEW_FILE = '__new__';

/* ---------------- 照搬定位器的代码生成辅助（临时用例三件套打包用） ---------------- */
const cnEscQ = (s) => String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
function cnCapFirst(s) { s = String(s || ''); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
function cnCapCamel(s) { return String(s || '').split('_').filter(Boolean).map(cnCapFirst).join(''); }
function cnIsNewCase() { return $('#cnCaseFile').value === CN_NEW_FILE; }
function cnNewCaseBase() { return ($('#cnCaseNew').value || '').trim().replace(/[^A-Za-z0-9_]/g, '_'); }
function cnElemFileNameNew() {
  const raw = ($('#cnElemFileNew').value || '').trim().replace(/\.py$/i, '');
  const v = raw.replace(/[^A-Za-z0-9_]/g, '_');
  if (!v) return '';
  return v.replace(/Elements?$/, '') + 'Elements.py';   // 结尾必须 Elements（页面/用例依赖后缀判归属）
}
function cnGenDesc(type, element, param) {
  switch (type) {
    case 'click': return '点击' + element;
    case 'input': return '在' + element + '输入「' + param + '」';
    case 'long_press': return '长按' + element;
    case 'assert_visible': return '断言' + element + '出现';
    case 'assert_text': return '断言' + element + '文本为「' + param + '」';
    case 'assert_toast': return '断言toast「' + param + '」';
    case 'assert_gone': return '断言' + element + '消失';
    case 'wait_element': return '等待' + element + '出现';
    case 'if_click': return element + '出现才点击';
    case 'sleep': return '固定等待' + (param || '1') + '秒';
    case 'tap': return '点击坐标(' + param + ')';
    case 'screenshot': return '截图' + (param ? '「' + param + '」' : '');
    case 'hide_keyboard': return '收起键盘';
    case 'custom': return param || '自定义代码';
    default: return (STEP_META[type] || {}).label || type;
  }
}
/* 用例行（与定位器 previewLine 同规则） */
function cnPreviewLine(step) {
  const t = step.type, el = step.element, p = step.param || '';
  switch (t) {
    case 'click': return 'page.click_' + el + '()';
    case 'input': return "page.input_" + el + "('" + cnEscQ(p) + "')";
    case 'long_press': return 'page.long_press_' + el + '()';
    case 'assert_visible': return 'page.assert_' + el + '()';
    case 'assert_text': return "page.assert_" + el + "_text('" + cnEscQ(p) + "')";
    case 'assert_toast': return "page.assert_toast('" + cnEscQ(p) + "')";
    case 'wait_element': { const n = parseInt(p, 10); return 'page.wait_' + el + (isNaN(n) ? '()' : '(' + n + ')'); }
    case 'assert_gone': return 'page.assert_' + el + '_gone()';
    case 'if_click': { const n = parseInt(p, 10); return 'page.click_' + el + '_if_visible(' + (isNaN(n) ? '' : n) + ')'; }
    case 'hide_keyboard': return 'page.dismiss_keyboard()';
    case 'screenshot': return "page.wait_and_shot('" + cnEscQ(p) + "')";
    case 'tap': { const parts = p.split(',').map(x => x.trim()).filter(Boolean);
      return parts.length >= 2 ? 'page.tap_xy(' + parts[0] + ', ' + parts[1] + ')' : 'page.tap_xy(' + (parts[0] || '0') + ')'; }
    case 'sleep': { const n = parseFloat(p); return 'time.sleep(' + (isNaN(n) ? (p || '1') : n) + ')'; }
    case 'custom': return p || 'page.xxx()';
    default: return '';
  }
}
/* 页面方法名（与后端派生规则一致） */
function cnPageMethodName(type, el) {
  return { click: 'click_' + el, input: 'input_' + el, long_press: 'long_press_' + el,
    assert_visible: 'assert_' + el, assert_text: 'assert_' + el + '_text', assert_toast: 'assert_toast',
    screenshot: 'wait_and_shot', tap: 'tap_xy', wait_element: 'wait_' + el,
    assert_gone: 'assert_' + el + '_gone', if_click: 'click_' + el + '_if_visible',
    hide_keyboard: 'dismiss_keyboard' }[type] || '';
}
function cnProbeBodyLines(el, secondsVar) {
  return "probe = CreateElement.create(self._elements." + el + ".locator_type,\n"
    + "                             self._elements." + el + ".locator_value,\n"
    + "                             wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n"
    + "                             wait_seconds=" + secondsVar + ")";
}
/* 页面方法块（与定位器 pkgMethodBlock 同规则；doc=步骤描述） */
function cnMethodBlock(step, doc) {
  const t = step.type, el = step.element, p = (step.param || '').trim();
  let sig = '', body = '';
  if (t === 'click') sig = 'click_' + el + '(self)';
  else if (t === 'input') { sig = 'input_' + el + '(self, text)'; body = 'self.appOperator.sendText(self._elements.' + el + ', text)'; }
  else if (t === 'long_press') { sig = 'long_press_' + el + '(self)'; body = 'self.appOperator.touch_long_press(self._elements.' + el + ', duration_sconds=2)'; }
  else if (t === 'assert_visible') { sig = 'assert_' + el + '(self)'; body = 'self.appOperator.getElement(self._elements.' + el + ')'; }
  else if (t === 'assert_text') { sig = 'assert_' + el + '_text(self, expected)'; body = "assert self.appOperator.getText(self._elements." + el + ") == expected, '" + cnEscQ(doc) + "'"; }
  else if (t === 'assert_toast') { sig = 'assert_toast(self, text)'; body = "assert self.appOperator.is_toast_visible(text, wait_seconds=5), '" + cnEscQ(doc) + "'"; }
  else if (t === 'wait_element') { const n = parseInt(p, 10); sig = 'wait_' + el + '(self, timeout_seconds=' + (isNaN(n) ? 60 : n) + ')'; body = cnProbeBodyLines(el, 'timeout_seconds') + '\nself.appOperator.getElement(probe)'; }
  else if (t === 'assert_gone') { sig = 'assert_' + el + '_gone(self, wait_seconds=2)'; body = cnProbeBodyLines(el, 'wait_seconds') + '\ngone = True\ntry:\n    self.appOperator.getElement(probe)\n    gone = False\nexcept Exception:\n    pass\n' + "self.appOperator.assert_true_with_shot('" + cnEscQ(doc) + "', gone,\n                                   '等待' + str(wait_seconds) + '秒内元素仍可见')"; }
  else if (t === 'if_click') { const n = parseInt(p, 10); sig = 'click_' + el + '_if_visible(self, timeout_seconds=' + (isNaN(n) ? 3 : n) + ')'; body = cnProbeBodyLines(el, 'timeout_seconds') + '\ntry:\n    self.appOperator.click(self.appOperator.getElement(probe))\nexcept Exception:\n    pass'; }
  else if (t === 'hide_keyboard') { sig = 'dismiss_keyboard(self)'; body = 'try:\n    if self.appOperator.is_keyboard_shown():\n        self.appOperator.hide_keyboard()\nexcept Exception:\n    self.appOperator.press_keycode(4)\nimport time\ntime.sleep(1)'; }
  else if (t === 'screenshot') { sig = 'wait_and_shot(self, tag)'; body = 'import time\ntime.sleep(1)\nself.appOperator.get_screenshot(tag)'; }
  else if (t === 'tap') { sig = 'tap_xy(self, x, y)'; body = 'self.appOperator.tap(x, y)'; }
  if (t === 'click') body = 'self.appOperator.click(self._elements.' + el + ')';
  return '    def ' + sig + ':\n        """' + doc + '"""\n        ' + body.replace(/\n/g, '\n        ');
}
function cnElementLine() {
  const name = $('#cnElName').value.trim() || '<元素名>';
  const val = $('#cnElLocVal').value.trim();
  const sec = parseInt($('#cnElWaitSec').value, 10);
  let line = "self." + name + " = CreateElement.create(Locator_Type." + $('#cnElLocType').value
    + ", '" + cnEscQ(val) + "', wait_type=Wait_By." + $('#cnElWait').value;
  if (!isNaN(sec) && sec >= 1) line += ', wait_seconds=' + sec;
  line += ')';
  const c = $('#cnElComment').value.trim();
  return c ? line + '  # ' + c : line;
}

/* ---------------- 弹窗打开 / 截图 / 缩放 / 拾取 ---------------- */
function openCnModal() {
  _cnSelNode = null; _cnAll = []; _cnZoomPct = 100;
  _cnCaseInfo = []; _cnCaseSel = null; _cnMethodSteps = []; _cnWritten = 0; _cnTemp = null;
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
    '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('') +
    '<option value="' + CN_NEW_FILE + '">➕ 新建元素文件…</option>';
  $('#cnElemFileNew').value = ''; $('#cnElemFileNewWrap').style.display = 'none';
  $('#cnCaseNew').value = ''; $('#cnCaseNewWrap').style.display = 'none';
  $('#cnCaseCnName').value = '';
  $('#cnStepType').innerHTML = Object.keys(STEP_META).map(t =>
    '<option value="' + t + '">' + STEP_META[t].label + '</option>').join('');
  $('#cnPageFile').value = '';
  $('#cnCaseComment').value = '';
  $('#cnRegName').value = ''; $('#cnRegBy').value = ''; $('#cnRegDesc').value = ''; $('#cnRegProj').value = '';
  syncCnParam();
  renderCnMethodSteps();
  $('#caseNewMask').classList.add('show');
  cnShot();
  loadCnCases();
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
        ' · ' + d.width + '×' + d.height + (_cnAll.length ? ' · ' + _cnAll.length + ' 个节点' : '');
      $('#cnDeviceInfo').title = '滚轮或 ＋/－ 缩放截图；点击画面元素自动回显定位';
    })
    .catch(e => { $('#cnDeviceInfo').textContent = '元素定位器不可达（' + e.message + '）'; });
}

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
  $('#cnPickInfo').style.display = '';
  $('#cnEmptyMid').style.display = 'none';
  const cx = Math.round((b[0] + b[2]) / 2), cy = Math.round((b[1] + b[3]) / 2);
  $('#cnCoord').value = cx + ', ' + cy;
  $('#cnBounds').value = b.join(', ');
  const cands = (best.locators || []).filter(l => l.value);
  $('#cnLocator').innerHTML = cands.map((l, i) =>
    '<option value="' + i + '">' + esc(l.desc || l.locator_type) + '</option>').join('') ||
    '<option value="">（该节点无可用定位）</option>';
  $('#cnLocVal').value = cands[0] ? cands[0].value : '';
  cnApply();                                    // 点中即回显到右侧表单
}

/* 中栏选中内容 → 回显右侧表单（① 元素 + ③ 步骤描述建议） */
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

/* ---------------- ② 用例：目标用例文件 / 测试方法 / 插入位置（数据来自框架文件） ---------------- */
async function loadCnCases() {
  $('#cnCaseFile').innerHTML = '<option value="">加载中…</option>';
  try {
    const d = await fetch('/locator/api/cases').then(r => r.json());
    _cnCaseInfo = d.ok ? (d.case_info || []) : [];
  } catch (e) { _cnCaseInfo = []; }
  $('#cnCaseFile').innerHTML = _cnCaseInfo.map(c =>
    '<option value="' + esc(c.file) + '">' + esc(c.file) + '（' + esc(c.class) + '）</option>').join('') +
    '<option value="' + CN_NEW_FILE + '">➕ 新建用例文件…</option>';
  onCnCaseChange();
}

function onCnCaseChange() {
  const isNew = cnIsNewCase();
  $('#cnCaseNewWrap').style.display = isNew ? '' : 'none';
  if (isNew) {                                   // 新建模式：方法/页面文件按用例名生成
    _cnCaseSel = null; _cnMethodSteps = [];
    const base = cnNewCaseBase();
    $('#cnCaseMethod').innerHTML = '<option value="test_' + esc(base || 'x') + '">test_' + esc(base || 'x') + '（新建后自动生成）</option>';
    $('#cnPageFile').value = base ? cnCapFirst(base) + 'Page.py' : '（输入用例名后自动派生）';
    renderCnMethodSteps();
    return;
  }
  const file = $('#cnCaseFile').value;
  _cnCaseSel = _cnCaseInfo.find(c => c.file === file) || null;
  if (!_cnCaseSel) {
    $('#cnCaseMethod').innerHTML = '<option>—</option>';
    _cnMethodSteps = []; renderCnMethodSteps();
    return;
  }
  const methods = (_cnCaseSel.methods || []).filter(m => m !== 'setup_class' && m !== 'teardown_class');
  $('#cnCaseMethod').innerHTML = methods.length ? methods.map(m =>
    '<option value="' + esc(m) + '">' + esc(m) + '</option>').join('') : '<option value="">（该文件没有测试方法）</option>';
  /* 三件套联动：元素文件 / 页面文件 按目标用例自动带出（与定位器同一数据源） */
  if (_cnCaseSel.elements_file) {
    const sel = $('#cnElemFile');
    if (![...sel.options].some(o => o.value === _cnCaseSel.elements_file))
      sel.insertAdjacentHTML('beforeend', '<option value="' + esc(_cnCaseSel.elements_file) + '">' + esc(_cnCaseSel.elements_file) + '</option>');
    sel.value = _cnCaseSel.elements_file;
  }
  $('#cnPageFile').value = _cnCaseSel.page_file || '（未解析到页面文件）';
  onCnMethodChange();
}

function onCnMethodChange() {
  const m = $('#cnCaseMethod').value;
  _cnMethodSteps = (_cnCaseSel && _cnCaseSel.method_steps && _cnCaseSel.method_steps[m]) || [];
  renderCnMethodSteps();
}

function renderCnMethodSteps() {
  const box = $('#cnSteps');
  if (!box) return;
  const isNew = cnIsNewCase();
  const pending = _cnTemp ? _cnTemp.steps : [];
  let n, rows;
  if (isNew) {
    n = pending.length;
    rows = pending.map((s, i) =>
      '<div class="cnstep"><span class="orch-index">' + (i + 1) + '</span>' +
      '<span class="cn-step-el" style="grid-column:2 / span 3" title="' + esc(s.comment) + '">' + esc(s.comment) + '</span></div>').join('') ||
      '<div class="orch-empty">新用例还没有步骤 —— 录制的第一步将成为第 1 步</div>';
    $('#cnStepCount').textContent = n ? '（已录 ' + n + ' 步，未入库）' : '（还没有步骤）';
  } else {
    n = _cnMethodSteps.length;
    rows = _cnMethodSteps.map((s, i) =>
      '<div class="cnstep"><span class="orch-index">' + (i + 1) + '</span>' +
      '<span class="cn-step-el" style="grid-column:2 / span 3" title="' + esc(s) + '">' + esc(s) + '</span></div>').join('') ||
      '<div class="orch-empty">目标方法还没有步骤 —— 录制的第一步将成为第 1 步</div>';
    $('#cnStepCount').textContent = n ? '（已有 ' + n + ' 步）' : '（还没有步骤）';
  }
  box.innerHTML = rows;
  /* 插入位置：末尾 / 第 k 步之后（新建模式恒为末尾） */
  const pos = $('#cnInsertPos');
  const cur = pos.value;
  if (isNew) { pos.innerHTML = '<option value="">末尾（成为第 ' + (n + 1) + ' 步）</option>'; return; }
  let opts = '<option value="">末尾（成为第 ' + (n + 1) + ' 步）</option>';
  for (let k = 1; k <= n; k++) opts += '<option value="' + k + '"' + (String(k) === cur ? ' selected' : '') + '>第 ' + k + ' 步之后</option>';
  pos.innerHTML = opts;
}

/* ---------------- 写入：元素入库 + 用例行追加 + 页面方法生成（三件套一次完成） ---------------- */
async function writeCnStep() {
  const name = ($('#cnElName').value || '').trim();
  const locType = ($('#cnElLocType').value || '').trim();
  const locVal = ($('#cnElLocVal').value || '').trim();
  if (!name) return toast('请填写元素名称', false);
  if (!locVal) return toast('请先点击截图中的元素回显定位，或手填定位值', false);
  const type = $('#cnStepType').value;
  const meta = STEP_META[type] || {};
  if (meta.el === false) return toast('该操作不需要元素，请改用「用例编排」面板添加', false);
  const param = $('#cnStepParam').style.display !== 'none' ? $('#cnStepParam').value.trim() : '';
  const desc = $('#cnStepDesc').value.trim() || cnGenDesc(type, name, param);
  /* 1) 元素入库（等待方式/时间/备注一并写入；命中重复定位自动复用已有元素） */
  const el = await fetch('/locator/api/add_element', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: currentCnElemFile(), name,
      locator_type: locType, value: locVal,
      wait_type: $('#cnElWait').value, wait_seconds: +$('#cnElWaitSec').value || null,
      comment: ($('#cnElComment').value || '').trim() }),
  }).then(x => x.json());
  let elemNameUsed = name;
  if (!el.ok && el.duplicate && el.duplicate.name) {
    elemNameUsed = el.duplicate.name;
    toast('元素已存在，复用「' + elemNameUsed + '」', true);
  } else if (!el.ok) {
    return toast('元素入库失败：' + (el.msg || '未知错误'), false);
  }
  const descUsed = desc === cnGenDesc(type, name, param) ? cnGenDesc(type, elemNameUsed, param) : desc;
  /* 2a) 新建用例文件：临时三件套打包入库（与定位器「保存并继续」同语义） */
  if (cnIsNewCase()) {
    const base = cnNewCaseBase();
    if (!base) return toast('请填写新用例名', false);
    const tc = _cnTemp = (_cnTemp || { steps: [] });
    tc.base = base;
    tc.steps.push({
      type, param,                               // 结构化字段：④ 项目登记回填 steps 用
      comment: ($('#cnCaseComment').value || '').trim() || descUsed,
      line: cnPreviewLine({ type, element: elemNameUsed, param }),
      elemName: elemNameUsed, elemLine: cnElementLine().replace('self.' + name + ' ', 'self.' + elemNameUsed + ' '),
      methodBlock: cnMethodBlock({ type, element: elemNameUsed, param }, descUsed),
    });
    const files = cnTempFiles(tc);
    const r = await fetch('/locator/api/save_case_package', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package: base, files, uploader: ($('#cnElComment').value || '').trim() || 'platform' }),
    }).then(x => x.json());
    if (!r.ok) { tc.steps.pop(); return toast('新建用例入库失败：' + (r.msg || '未知错误'), false); }
    _cnWritten++;
    toast('用例包「' + base + '」已入库（' + tc.steps.length + ' 步），后续步骤默认继续写入', true);
    await loadCnCases();                       // 新文件已存在 → 自动切回已有文件模式继续追加
    $('#cnCaseFile').value = 'test_' + base + '.py';
    onCnCaseChange();
    $('#cnStepDesc').value = ''; $('#cnStepParam').value = '';
    await cnRegister();                        // ④ 已填用例名称则登记到用例列表与项目管理
    return;
  }
  /* 2b) 已有用例文件：操作行追加 + 页面方法生成（与定位器同一接口） */
  const caseFile = $('#cnCaseFile').value, method = $('#cnCaseMethod').value;
  if (!caseFile || !method) return toast('请选择目标用例文件与测试方法', false);
  const pos = +$('#cnInsertPos').value || null;
  const r = await fetch('/locator/api/add_code', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_file: caseFile, method_name: method,
      step: { type, element: elemNameUsed, param, desc: descUsed,
              case_comment: ($('#cnCaseComment').value || '').trim() },
      gen_page_method: true, insert_after_step: pos }),
  }).then(x => x.json());
  if (!r.ok) return toast('写入用例失败：' + (r.msg || '未知错误'), false);
  _cnWritten++;
  const at = pos || _cnMethodSteps.length;
  _cnMethodSteps.splice(at, 0, r.line || descUsed);
  renderCnMethodSteps();
  $('#cnStepDesc').value = ''; $('#cnStepParam').value = '';
  toast('已写入第 ' + (at + 1) + ' 步 → ' + caseFile + ' · ' + method, true);
  await cnRegister();                          // ④ 已填用例名称则登记到用例列表与项目管理
}

/* ④ 项目登记：把已写入框架文件的用例登记回平台（用例列表 + 项目管理 case_count/详情）。
   用例名称留空 = 不登记；带 node 走后端仅登记模式（不重复编译生成框架文件）；
   按 node 幂等：已登记 → PUT 更新，未登记 → POST 新建。
   步骤回填：仅本会话新建的用例文件回填结构化 steps（追加已有文件的已有步骤无法结构化还原，置空）。 */
async function cnRegister() {
  const name = ($('#cnRegName').value || '').trim();
  const method = $('#cnCaseMethod').value;
  if (!name || !_cnCaseSel || !method) return null;
  const node = 'cases/app_ui/android/demoProject/' + _cnCaseSel.file + '::' + _cnCaseSel.class + '::' + method;
  const body = { name,
    description: ($('#cnRegDesc').value || '').trim(),
    created_by: ($('#cnRegBy').value || '').trim(),
    project_id: $('#cnRegProj').value || '',
    elements_file: _cnCaseSel.elements_file || currentCnElemFile(),
    node };
  if (_cnTemp && _cnCaseSel.file === 'test_' + _cnTemp.base + '.py')
    body.steps = _cnTemp.steps.map(s => ({ type: s.type, element: s.elemName, param: s.param || '', desc: s.comment }));
  const prev = _cases.find(c => c.node === node);
  const d = prev ? await api(AT_PREFIX + '/api/cases/' + prev.id, { method: 'PUT', body: JSON.stringify(body) })
    : await postJson(AT_PREFIX + '/api/cases', body);
  if (!d.ok) { toast('用例登记失败：' + (d.msg || '未知错误'), false); return null; }
  await renderCaseList();                      // 用例列表即时可见
  await loadProjects();                        // 项目管理用例数即时可见
  return d.case;
}

function currentCnElemFile() {
  if ($('#cnElemFile').value === CN_NEW_FILE) {
    const f = cnElemFileNameNew();
    if (!f) return '';
    if (![...$('#cnElemFile').options].some(o => o.value === f))
      $('#cnElemFile').insertAdjacentHTML('beforeend', '<option value="' + esc(f) + '">' + esc(f) + '</option>');
    $('#cnElemFile').value = f;
  }
  return $('#cnElemFile').value;
}

/* 新建用例文件模式：按用例名生成三件套内容（用例+页面+元素，一次打包入库） */
function cnTempFiles(tc) {
  const base = tc.base;
  const caseName = 'test_' + base + '.py';
  const pageFile = cnCapFirst(base) + 'Page.py';
  const pageClass = cnCapFirst(pageFile.replace('.py', ''));
  const elemFile = ($('#cnElemFile').value && $('#cnElemFile').value !== CN_NEW_FILE)
    ? $('#cnElemFile').value : cnElemFileNameNew() || (base + 'Elements.py');
  const elemClass = cnCapFirst(elemFile.replace('.py', ''));
  /* 元素文件：同名元素取最后一次定义 */
  const eOrder = [], eMap = {};
  tc.steps.forEach(s => {
    if (!s.elemName || !s.elemLine) return;
    if (!(s.elemName in eMap)) eOrder.push(s.elemName);
    eMap[s.elemName] = s.elemLine;
  });
  const elemContent = '# -*- coding: utf-8 -*-\n'
    + '# 用例包 ' + base + ' · 元素库\n'
    + 'from page_objects.createElement import CreateElement\n'
    + 'from page_objects.app_ui.locator_type import Locator_Type\n'
    + 'from page_objects.app_ui.wait_type import Wait_Type as Wait_By\n\n\n'
    + 'class ' + elemClass + ':\n    def __init__(self):\n'
    + (eOrder.length ? eOrder.map(n => '        ' + eMap[n]).join('\n') + '\n' : '        pass\n');
  /* 页面文件：同名方法取最后一次 */
  const mOrder = [], mMap = {};
  tc.steps.forEach(s => {
    const mn = (s.methodBlock.match(/def (\w+)/) || [])[1];
    if (!mn) return;
    if (!(mn in mMap)) mOrder.push(mn);
    mMap[mn] = s.methodBlock;
  });
  const pageContent = '# -*- coding: utf-8 -*-\n'
    + '# 用例包 ' + base + ' · 页面操作\n'
    + 'from page_objects.app_ui.android.demoProject.elements.' + elemFile.replace('.py', '') + ' import ' + elemClass + '\n\n\n'
    + 'class ' + pageClass + ':\n\n'
    + '    def __init__(self, appOperator):\n'
    + '        self.appOperator = appOperator\n'
    + '        self._elements = ' + elemClass + '()\n'
    + (mOrder.length ? '\n' + mOrder.map(n => mMap[n]).join('\n') + '\n' : '');
  /* 用例文件：头部流程注释 + 方法体逐步骤 */
  const flow = ['# 1. 拉起快歌主页面'].concat(tc.steps.map((s, i) => '# ' + (i + 2) + '. ' + s.comment));
  const cnTitle = ($('#cnCaseCnName').value || '').trim();
  const caseContent = '# -*- coding: utf-8 -*-\n'
    + (cnTitle ? '# 用例中文名：' + cnTitle + '\n' : '')
    + '# 用例包 ' + base + ' · ' + tc.steps.length + ' 步\n'
    + flow.join('\n') + '\n'
    + 'import time\nimport allure\n'
    + 'from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client\n'
    + 'from page_objects.app_ui.android.demoProject.pages.' + pageFile.replace('.py', '') + ' import ' + pageClass + '\n\n\n'
    + "@allure.parent_suite('快歌APP自动化')\n"
    + "@allure.suite('" + base + "')\n"
    + 'class Test' + cnCapCamel(base) + ':\n\n'
    + '    def setup_class(self):\n'
    + '        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App\n'
    + '        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)\n'
    + '        self.appOperator = self.demoProjectClient.appOperator\n'
    + "        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')\n"
    + '        time.sleep(3)\n'
    + '        self.page = ' + pageClass + '(self.appOperator)\n\n'
    + "    @allure.title('" + base + ' · ' + tc.steps.length + " 步')\n"
    + '    def test_' + base + '(self):\n        page = self.page\n\n'
    + tc.steps.map((s, i) => '        # ' + (i + 1) + '. ' + s.comment + '\n        ' + s.line + '\n\n').join('')
    + '    def teardown_class(self):\n        self.appOperator.close_app()\n';
  return [
    { dir: 'cases/app_ui/android/demoProject', name: caseName, content: caseContent },
    { dir: 'page_objects/app_ui/android/demoProject/pages', name: pageFile, content: pageContent },
    { dir: 'page_objects/app_ui/android/demoProject/elements', name: elemFile, content: elemContent },
  ];
}

async function cnFinish() {
  const n = _cnWritten;
  $('#caseNewMask').classList.remove('show');
  if (!n && !($('#cnRegName').value || '').trim()) return toast('未写入任何步骤', false);
  /* 兜底登记：用户往往录完步骤才填 ④ 项目；已登记过则走 PUT 更新（幂等） */
  const c = await cnRegister();
  if (c) toast('本次共写入 ' + n + ' 步，用例「' + c.name + '」已登记到用例列表与项目管理', true);
  else if (n) toast('本次共写入 ' + n + ' 步，已入库框架文件（④ 用例名称为空或未选目标用例，未登记）', true);
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
      '<p class="muted" style="font-size:12px">保存时平台会把编排编译成页面 + 用例文件（元素只引用不复制），自动进入「执行用例」与执行链路。</p>';
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
  // 前后置清理走「前后置清理」卡片保存的持久化配置，执行时不随请求传
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

/* ================= 测试用例列表（数据源：框架 cases/app_ui 测试用例 + 平台登记信息按 node 合并） ================= */
let _fwCases = [];        // 框架用例行 [{node, file, class, method, step_count, case|null}]
let _mvNode = null;       // 移动到项目弹窗当前操作的框架用例 node

async function renderCaseList() {
  const [fd, cd] = await Promise.all([
    api(AT_PREFIX + '/api/cases/framework'), api(AT_PREFIX + '/api/cases')]);
  if (!fd.ok) return toast(fd.msg || '框架用例加载失败', false);
  _fwCases = fd.results || [];
  /* 用例中文名映射（文件头「# 用例中文名：」，与元素定位器「添加测试用例」同源）：
     没有就回填（登记名 > 方法名去 test_ 前缀），有就直接用；只补缺，不覆盖已有映射 */
  const miss = _fwCases.filter(c => !c.cn_name);
  if (miss.length) {
    await Promise.all(miss.map(async c => {
      const reg0 = c.case;
      const fallback = (reg0 && reg0.name) || (c.method || '').replace(/^test_/, '') || c.method || '';
      try {
        const d = await api('/api/cases/cn-name', { method: 'POST', body: JSON.stringify({ file: c.file, cn_name: fallback }) });
        if (d.ok) c.cn_name = d.cn_name;
      } catch (_) {}   // 单条回填失败只影响该行显示，不阻塞列表
    }));
  }
  _cases = cd.ok ? (cd.results || []) : [];    // 编排/套件面板仍用登记实体
  const kw = ($('#clSearch').value || '').trim().toLowerCase();
  const pf = $('#clProj') ? $('#clProj').value : '';
  const list = _fwCases.filter(c => {
    const reg = c.case;
    const inProj = !pf || (pf === 'none' ? !(reg && reg.project_id) : !!(reg && +reg.project_id === +pf));
    const hay = [c.file, c.class, c.method, c.cn_name, reg && reg.name, reg && reg.description, reg && reg.created_by];
    return inProj && (!kw || hay.some(v => String(v || '').toLowerCase().includes(kw)));
  });
  $('#clEmpty').style.display = list.length ? 'none' : '';
  $('#clTbody').innerHTML = list.map(c => {
    const reg = c.case;
    /* 用例字段：优先取中文名映射（定位器/重命名写入），悬停 title 附方法名便于对照 */
    const name = c.cn_name || (reg ? reg.name : c.method);
    const title = c.cn_name ? (c.cn_name + '（' + c.method + '）') : name;
    const sub = (reg && reg.description) ? reg.description : '';   // 用例列只显示名称+描述，不显示文件路径
    /* 列宽固定（table-layout:fixed），超长内容 .clip 单行截断，title 悬停看全称 */
    return '<tr><td><div class="clip" title="' + esc(title) + '"><b>' + esc(name) + '</b>' +
      (reg ? '' : ' <span class="proj-status" title="尚未登记到平台，可在「移动项目」时登记">未登记</span>') +
      '</div>' +
      (sub ? '<div class="path clip" title="' + esc(sub) + '">' + esc(sub) + '</div>' : '') + '</td>' +
      '<td class="clip" title="' + esc(reg ? (projName(reg.project_id) || '未分组') : '—') + '">' +
      esc(reg ? (projName(reg.project_id) || '未分组') : '—') + '</td>' +
      '<td>' + (c.step_count || 0) + ' 步</td>' +
      '<td class="clip" title="' + esc((reg && reg.created_by) || '—') + '">' + esc((reg && reg.created_by) || '—') + '</td>' +
      '<td>' + (reg ? fmtTs(reg.created_at) : '—') + '</td>' +
      '<td class="ops">' +
      '<button class="mini" data-editsteps="' + esc(c.node) + '">编辑步骤</button>' +
      '<button class="ghost mini" data-cncase="' + esc(c.file) + '" data-cn="' + esc(c.cn_name || '') + '">重命名</button>' +
      '<button class="mini" data-mvnode="' + esc(c.node) + '">移动项目</button>' +
      (reg ? '<button class="danger mini" data-del="' + reg.id + '">删除</button>' : '') +
      '</td></tr>';
  }).join('');
}

/* ---- 移动用例到项目：已登记 = 只改归属；未登记 = 移动时顺带登记（仅登记模式，不动框架文件） ---- */
function openCaseMove(node) {
  _mvNode = node;
  const row = _fwCases.find(c => c.node === node);
  const reg = row && row.case;
  $('#mvWho').textContent = row ? (row.file + ' · ' + row.class + ' · ' + row.method) : node;
  $('#mvProj').value = reg && reg.project_id ? reg.project_id : '';
  $('#mvNameWrap').style.display = reg ? 'none' : '';
  $('#mvByWrap').style.display = reg ? 'none' : '';
  if (!reg) {
    const base = (row.file.split('/').pop() || '').replace(/^test_/, '').replace(/\.py$/, '');
    $('#mvName').value = row.method.replace(/^test_/, '') || base;
    $('#mvBy').value = '';
  }
  $('#caseMoveMask').classList.add('show');
}

async function saveCaseMove() {
  if (!_mvNode) return;
  const row = _fwCases.find(c => c.node === _mvNode);
  const projVal = $('#mvProj').value || '';
  let d;
  if (row && row.case) {
    d = await api(AT_PREFIX + '/api/cases/' + row.case.id + '/project',
      { method: 'PUT', body: JSON.stringify({ project_id: projVal }) });
  } else {
    const name = ($('#mvName').value || '').trim();
    if (!name) return toast('请填写登记用例名称', false);
    d = await postJson(AT_PREFIX + '/api/cases', {
      name, created_by: ($('#mvBy').value || '').trim(),
      project_id: projVal, node: _mvNode });
  }
  if (!d.ok) return toast(d.msg || '保存失败', false);
  $('#caseMoveMask').classList.remove('show');
  toast('已移动到「' + (projName(projVal) || '未分组') + '」', true);
  await renderCaseList();
  await loadProjects();                        // 项目管理用例数同步刷新
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
  $('#btnClRefresh').addEventListener('click', () => {
    /* 重置：清空本面板已选择项（搜索词 / 项目筛选），列表回到初始视图 */
    $('#clSearch').value = '';
    $('#clProj').value = '';
    renderCaseList();
  });
  /* 新建用例：跳转元素定位器（截图点选 → 添加测试用例弹窗在定位器内完成） */
  $('#btnClNew').addEventListener('click', () => { window.open('/locator', '_blank', 'noopener'); });

  /* ---- 步骤编辑（三级页）：布局对照 design/case-step-editor-prototype.html；
     数据 = /api/case/steps 反解（方法体注释 + 调用行），编辑仅当前页预览，写回未接入 ---- */
  const CE_GROUP_CSS = { '基本操作': 'var(--brand)', '断言': '#6e46c8', '等待与分支': '#b26a00', '其他': '#86868b' };
  const CE_EXTRA_TYPES = { deal_first_launch_dialogs: { label: '首启弹窗处理', group: '其他', param: null } };
  let _ceCtx = null, _ceSel = -1, _ceElements = null;

  function ceTypeMeta(t) { return STEP_META[t] || CE_EXTRA_TYPES[t] || { label: t || '未知', group: '其他', param: null }; }

  async function openCaseEditor(node) {
    const row = _fwCases.find(c => c.node === node);
    if (!row) return toast('用例行数据未就绪，请刷新列表后重试', false);
    const d = await api(AT_PREFIX + '/api/case/steps?file=' + encodeURIComponent(row.file) + '&method=' + encodeURIComponent(row.method));
    if (!d.ok) return toast(d.msg || '步骤反解失败', false);
    _ceCtx = { row, steps: d.steps || [] };
    _ceSel = _ceCtx.steps.length ? 0 : -1;
    $('#ceDirty').style.display = 'none';
    if (!_ceElements) {
      const ed = await api('/api/appui/elements');
      _ceElements = ed.ok ? (ed.elements || []) : [];
    }
    renderCeShell();
    renderCeSteps();
    renderCeEditor();
    showRunPanel('caseedit');
  }

  function renderCeShell() {
    const { row, steps } = _ceCtx;
    const reg = row.case;
    $('#ceTitle').textContent = row.cn_name || (reg && reg.name) || row.method;
    $('#ceMeta').innerHTML =
      '<span class="chip">' + esc(row.file) + '</span>' +
      '<span class="chip">' + esc(row.class) + '</span>' +
      '<span class="chip">' + esc(row.method) + '</span>' +
      '<span class="chip">' + steps.length + ' 步</span>' +
      '<span class="chip">' + esc(reg ? (projName(reg.project_id) || '未分组') : '未登记') + '</span>';
    const sel = $('#ceType');
    sel.innerHTML = '';
    Object.keys(Object.assign({}, STEP_META, CE_EXTRA_TYPES)).forEach(k => {
      const t = ceTypeMeta(k);
      sel.insertAdjacentHTML('beforeend', '<option value="' + k + '">' + esc(t.label) + '（' + t.group + '）</option>');
    });
    const elSel = $('#ceEl');
    elSel.innerHTML = '';
    _ceElements.forEach(e => {
      elSel.insertAdjacentHTML('beforeend',
        '<option value="' + esc(e.name) + '">' + esc(e.cn_name ? e.cn_name + '（' + e.name + '）' : e.name) + '</option>');
    });
  }

  function renderCeSteps() {
    if (!_ceCtx) return;
    const kw = ($('#ceQ').value || '').trim().toLowerCase();
    const box = $('#ceSteps');
    box.innerHTML = '';
    const items = _ceCtx.steps.map((s, i) => ({ s, i }))
      .filter(({s}) => !kw || [s.desc, s.element, s.param, ceTypeMeta(s.type).label]
        .some(v => String(v || '').toLowerCase().includes(kw)));
    items.forEach(({s, i}) => {
      const t = ceTypeMeta(s.type);
      const row = document.createElement('div');
      row.className = 'ce-step' + (i === _ceSel ? ' sel' : '');
      row.innerHTML =
        '<span class="ce-grip">☰</span>' +
        '<span class="ce-node" style="background:' + (CE_GROUP_CSS[t.group] || '#86868b') + '">' + (i + 1) + '</span>' +
        '<div class="ce-main"><div class="ce-type">' + esc(t.label) + '</div>' +
        '<div class="ce-desc">' + (s.element ? esc(s.element) + (s.param ? ' · <b>' + esc(s.param) + '</b>' : '')
          : (s.param ? '<b>' + esc(s.param) + '</b>' : '')) +
        (s.desc ? ' <span style="color:var(--muted2)">' + esc(s.desc) + '</span>' : '') + '</div></div><span></span>';
      row.addEventListener('click', () => { _ceSel = i; renderCeSteps(); renderCeEditor(); });
      box.appendChild(row);
    });
    if (!items.length) box.innerHTML = '<div class="ce-none">没有匹配的步骤</div>';
    $('#ceCnt').textContent = _ceCtx.steps.length + ' 步';
  }

  function renderCeEditor() {
    if (!_ceCtx) return;
    const s = _ceCtx.steps[_ceSel];
    $('#ceNone').style.display = s ? 'none' : '';
    $('#ceBody').style.display = s ? '' : 'none';
    $('#ceDup').style.display = s ? '' : 'none';
    $('#ceDel').style.display = s ? '' : 'none';
    if (!s) { $('#ceIdx').textContent = ''; return; }
    $('#ceIdx').textContent = '第 ' + (_ceSel + 1) + ' 步';
    const t = ceTypeMeta(s.type);
    $('#ceType').value = (STEP_META[s.type] || CE_EXTRA_TYPES[s.type]) ? s.type : 'custom';
    $('#ceElWrap').style.display = t.el === false ? 'none' : '';
    $('#ceParamWrap').style.display = (t.param || s.param) ? '' : 'none';
    $('#ceParamLab').textContent = t.param || '参数';
    const elSel = $('#ceEl');
    elSel.querySelectorAll('option[data-tmp]').forEach(o => o.remove());   // 清掉上次的临时回显项
    if (s.element && ![...elSel.options].some(o => o.value === s.element)) {
      elSel.insertAdjacentHTML('afterbegin',
        '<option data-tmp value="' + esc(s.element) + '">' + esc(s.element) + '（不在元素库）</option>');
    }
    elSel.value = s.element || '';
    $('#ceParam').value = s.param || '';
    $('#ceWait').value = s.wait || '出现即可';
    $('#ceSec').value = s.sec || '10';
    $('#ceDesc').value = s.desc || '';
    ceElPreview();
  }

  function ceElPreview() {
    const name = $('#ceEl').value;
    const e = (_ceElements || []).find(x => x.name === name);
    $('#ceElPreview').innerHTML = e ? '定位：<code>' + esc((e.type || '') + ' = ' + (e.value || '')) + '</code>'
      : (name ? '元素「' + esc(name) + '」不在元素库（页面对象内引用）' : '未选择元素');
  }

  function ceTouch() {
    const s = _ceCtx.steps[_ceSel]; if (!s) return;
    s.type = $('#ceType').value; s.element = $('#ceEl').value || '';
    s.param = $('#ceParam').value.trim();
    s.wait = $('#ceWait').value; s.sec = $('#ceSec').value.trim();
    s.desc = $('#ceDesc').value.trim();
    $('#ceDirty').style.display = '';
    renderCeSteps(); ceElPreview();
  }

  /* ＋ 添加步骤：按分组的下拉菜单（词表与定位器生成器同源）；预览语义，写回未接入 */
  function ceBuildAddMenu() {
    const menu = $('#ceAddMenu');
    if (menu.dataset.built) return;
    menu.dataset.built = '1';
    const types = Object.assign({}, STEP_META, CE_EXTRA_TYPES);
    Object.keys(types).forEach(k => {
      const t = types[k];
      let grp = menu.querySelector('[data-g="' + t.group + '"]');
      if (!grp) {
        grp = document.createElement('div');
        grp.className = 'grp'; grp.dataset.g = t.group; grp.textContent = t.group;
        menu.appendChild(grp);
      }
      const b = document.createElement('button');
      b.type = 'button';
      b.innerHTML = '<span class="mini-node" style="background:' + (CE_GROUP_CSS[t.group] || '#86868b') + '"></span>' + esc(t.label);
      b.addEventListener('click', () => {
        menu.classList.remove('open');
        const s = { type: k, element: t.el === false ? '' : ((_ceElements || [])[0] || {}).name || '',
                    param: '', wait: '出现即可', sec: '10', desc: '' };
        _ceCtx.steps.push(s);
        _ceSel = _ceCtx.steps.length - 1;
        $('#ceDirty').style.display = '';
        renderCeSteps(); renderCeEditor();
      });
      menu.appendChild(b);
    });
  }

  $('#ceQ').addEventListener('input', renderCeSteps);
  $('#ceType').addEventListener('change', ceTouch);
  $('#ceEl').addEventListener('change', ceTouch);
  $('#ceParam').addEventListener('input', ceTouch);
  $('#ceWait').addEventListener('change', ceTouch);
  $('#ceSec').addEventListener('input', ceTouch);
  $('#ceDesc').addEventListener('input', ceTouch);
  $('#ceAddBtn').addEventListener('click', e => {
    e.stopPropagation();
    ceBuildAddMenu();
    $('#ceAddMenu').classList.toggle('open');
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('.ce-add-wrap')) $('#ceAddMenu').classList.remove('open');
  });
  $('#ceDup').addEventListener('click', () => {
    if (!_ceCtx || _ceSel < 0) return;
    _ceCtx.steps.splice(_ceSel + 1, 0, Object.assign({}, _ceCtx.steps[_ceSel]));
    _ceSel = _ceSel + 1;
    $('#ceDirty').style.display = '';
    renderCeSteps(); renderCeEditor();
  });
  $('#ceDel').addEventListener('click', () => {
    if (!_ceCtx || _ceSel < 0) return;
    if (!confirm('删除第 ' + (_ceSel + 1) + ' 步？（仅当前页预览，写回未接入）')) return;
    _ceCtx.steps.splice(_ceSel, 1);
    _ceSel = Math.min(_ceSel, _ceCtx.steps.length - 1);
    $('#ceDirty').style.display = '';
    renderCeSteps(); renderCeEditor();
  });
  $('#ceBack').addEventListener('click', e => { e.preventDefault(); showRunPanel('caselist'); });
  $('#ceDiscard').addEventListener('click', () => { if (_ceCtx) openCaseEditor(_ceCtx.row.node); });  // 重拉反解 = 真放弃
  $('#ceSave').addEventListener('click', () => toast('编辑已更新当前页预览；写回用例文件的能力未接入'));

  /* ---- 移动用例到项目 弹窗 ---- */
  $('#mvSave').addEventListener('click', () => saveCaseMove().catch(e => toast(e.message, false)));
  $('#mvCancel').addEventListener('click', () => $('#caseMoveMask').classList.remove('show'));
  $('#caseMoveMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });

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
  $('#cnElemFile').addEventListener('change', () => {
    $('#cnElemFileNewWrap').style.display = $('#cnElemFile').value === CN_NEW_FILE ? '' : 'none';
  });
  $('#cnCaseFile').addEventListener('change', onCnCaseChange);
  $('#cnCaseNew').addEventListener('input', () => {
    // 新建用例：输入用例名实时派生「写入页面文件」显示（与三件套实际生成的文件名一致）
    if (!cnIsNewCase()) return;
    const base = cnNewCaseBase();
    $('#cnPageFile').value = base ? cnCapFirst(base) + 'Page.py' : '（输入用例名后自动派生）';
  });
  $('#cnCaseMethod').addEventListener('change', onCnMethodChange);
  $('#cnSave').addEventListener('click', () => writeCnStep().catch(e => toast(e.message, false)));
  $('#cnClose').addEventListener('click', cnFinish);
  $('#cnCancel').addEventListener('click', () => $('#caseNewMask').classList.remove('show'));
  $('#caseNewMask').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('show');
  });
  $('#clTbody').addEventListener('click', async e => {
    const mv = e.target.closest('[data-mvnode]'), del = e.target.closest('[data-del]'),
          cn = e.target.closest('[data-cncase]'), ed = e.target.closest('[data-editsteps]');
    if (ed) return openCaseEditor(ed.dataset.editsteps);
    if (cn) return openCaseCnModal(cn.dataset.cncase, cn.dataset.cn);   // 复用执行用例的中文名弹窗
    if (mv) return openCaseMove(mv.dataset.mvnode);
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
        await loadCaseSelectPanel();   // 执行用例面板同步刷新（删掉的节点立即消失）
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
