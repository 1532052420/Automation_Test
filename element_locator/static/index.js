/* App 元素定位器前端逻辑（原生 JS，无外部依赖） */
'use strict';

const state = {
  width: 0, height: 0,
  tree: null, all: [],
  shot: null,
  selUid: null, selNode: null,
  hitCands: null,
  serial: null,           // 当前操作的设备序列号（多设备切换；null=服务端默认第一台）
  pages: [],              // 现有页面文件
  eleFiles: [],           // 现有元素文件
  elementsAll: {},        // { 元素文件: [元素名...] }
  defaultEleFile: 'locator_gui_elements.py',
  caseFiles: [],          // 现有用例文件 [{file, class, methods:[...]}]（「保存并添加到用例」目标下拉用）
  treeDiffOn: true,       // 页面树 Diff：刷新后标记 🟢 新增 / 🔴 消失
  prevSigs: null,         // 上一次刷新的元素签名集合（Diff 基线；null=尚无）
  goneSigs: [],           // 本次刷新相对上次「消失」的元素签名
  undoStack: [],          // 本次会话「添加到用例」步骤的撤销栈（LIFO，存 add_code 返回的文件快照）
  tempCase: null,         // 录制会话：上次三件套入库的用例（base），重开弹窗时回显
  coordMode: false,       // ⌖ 坐标模式：点截图选精确坐标（不再命中容器节点），用于无障碍盲区（自绘弹层等）
  coordPoint: null,       // 坐标模式下最后选中的点 [x, y]（设备坐标）
};
// 右侧教学：搜索时展开所有分类，否则默认收起（点分类标题展开）
var tutExpandAll = false;

const $ = (id) => document.getElementById(id);

/* 步骤类型（与后端 case_generator.STEP_TYPES 一致）：值 -> 中文名 + 是否需要元素 + 是否需要参数
   group 用于下拉分组（基本操作 / 断言 / 长流程·等待与分支），defv = 切到该类型时参数框自动填的默认值 */
const STEP_TYPES = [
  { v: 'click', n: '点击', el: true, param: false, ph: '', group: '基本操作', defv: '' },
  { v: 'input', n: '输入', el: true, param: true, ph: '输入内容', group: '基本操作', defv: '' },
  { v: 'long_press', n: '长按', el: true, param: false, ph: '', group: '基本操作', defv: '' },
  { v: 'tap', n: '坐标点击', el: false, param: true, ph: 'x,y', group: '基本操作', defv: '' },
  { v: 'screenshot', n: '截图', el: false, param: true, ph: '截图名', group: '基本操作', defv: '' },
  { v: 'sleep', n: '固定等待(秒)', el: false, param: true, ph: '秒数', group: '基本操作', defv: '2' },
  { v: 'assert_visible', n: '断言存在', el: true, param: false, ph: '', group: '断言' },
  { v: 'assert_text', n: '断言文本', el: true, param: true, ph: '期望文本', group: '断言', defv: '' },
  { v: 'assert_toast', n: '断言Toast', el: false, param: true, ph: 'toast文本', group: '断言', defv: '' },
  { v: 'assert_gone', n: '断言消失(弹窗已关闭)', el: true, param: false, ph: '', group: '断言' },
  { v: 'wait_element', n: '轮询等待出现(慢页面/生成中)', el: true, param: true, ph: '最长等待秒数', group: '长流程·等待与分支', defv: '60' },
  { v: 'if_click', n: '出现才点击(分支弹窗)', el: true, param: true, ph: '探测秒数', group: '长流程·等待与分支', defv: '3' },
  { v: 'custom', n: '自定义代码', el: false, param: true, ph: '代码行', group: '长流程·等待与分支', defv: '' },
];
/* 特殊操作：与元素无关的用例级动作，单独下拉（el-op-special）。不写元素库、元素栏禁用；
   选中后只需选目标用例 + 插入位置。deal_first_launch_dialogs 固定前插（见 onCaseFileChange） */
const SPECIAL_OPS = {
  hide_keyboard: { v: 'hide_keyboard', n: '收起键盘', el: false, param: false },
  deal_first_launch_dialogs: { v: 'deal_first_launch_dialogs', n: '首次启动弹窗处理', el: false, param: false },
};
const stepTypeInfo = (v) => SPECIAL_OPS[v] || STEP_TYPES.find(t => t.v === v) || STEP_TYPES[0];
/* 当前生效的操作类型：特殊操作优先，否则用常规操作类型下拉 */
function currentOpType() { return $('el-op-special').value || $('el-op-type').value; }

function genStepDesc(s) {
  const t = stepTypeInfo(s.type);
  if (s.desc && s.desc.trim()) return s.desc.trim();
  const p = s.param || '';
  switch (s.type) {
    case 'click': return '点击' + s.element;
    case 'input': return '在' + s.element + '输入「' + p + '」';
    case 'long_press': return '长按' + s.element;
    case 'assert_visible': return '断言' + s.element + '出现';
    case 'assert_text': return '断言' + s.element + '文本为「' + p + '」';
    case 'assert_toast': return '断言toast「' + p + '」';
    case 'wait_element': return '等待【' + s.element + '】出现（最长' + (p || 60) + '秒）';
    case 'assert_gone': return '断言【' + s.element + '】已消失';
    case 'if_click': return '若【' + s.element + '】出现则点击（最长等' + (p || 3) + '秒）';
    case 'screenshot': return '截图：' + p;
    case 'tap': return '点击坐标(' + p + ')';
    case 'sleep': return '等待' + p + '秒';
    case 'hide_keyboard': return '收起键盘';
    case 'deal_first_launch_dialogs': return '首次启动弹窗处理（无弹窗自动跳过）';
    case 'custom': return (p || '自定义代码').split('\n')[0];
    default: return '未定义步骤';
  }
}

/* ---------- 工具 ---------- */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function copyText(text, btn) {
  const done = () => {
    if (!btn) return;
    btn.textContent = '已复制 ✓'; btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '复制'; btn.classList.remove('copied'); }, 1500);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else { fallbackCopy(text, done); }
}
function fallbackCopy(text, done) {
  const ta = document.createElement('textarea');
  ta.value = text; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); } catch (e) {}
  document.body.removeChild(ta); done();
}

/* ---------- 初始化 ---------- */
/* 内嵌模式（平台 iframe）：自带侧栏已被 CSS 隐藏，把侧栏里的功能件搬进顶部工具条，
   避免「平台侧栏 + 定位器侧栏」双栏；独立访问 8001 时保持原布局不动 */
function setupEmbedBar() {
  if (!document.documentElement.classList.contains('embedded')) return;
  const bar = $('embed-bar');
  const rf = $('btn-refresh');
  if (rf) bar.appendChild(rf);
  // 新窗口打开：脱离平台内嵌、独立标签页使用定位器（原平台页头的入口挪到这里，紧跟刷新避免换行）
  const nb = document.createElement('a');
  nb.className = 'btn small';
  nb.textContent = '↗ 新窗口';
  nb.href = location.href;
  nb.target = '_blank';
  nb.rel = 'noopener';
  bar.appendChild(nb);
  // 右侧设备组：📱 前缀标识 + 切换下拉 + 状态，成组靠右不换行（D2 修复）
  const group = document.createElement('span');
  group.className = 'dev-group';
  const devTag = document.createElement('span');
  devTag.className = 'bar-label';
  devTag.textContent = '📱 设备';
  group.appendChild(devTag);
  const devSel = $('device-sel');
  // 不再限宽：设备下拉要完整显示 serial（截断后同型号多台无法区分）
  if (devSel) group.appendChild(devSel);
  const dv = $('dev-info');
  if (dv) { dv.style.marginLeft = '0'; group.appendChild(dv); }
  bar.appendChild(group);
}

/* 顶部全局菜单栏：结构与样式来自平台共用的 nav.js / nav.css（导航项单一数据源，
   与平台各页完全一致，加页面只改 nav.js 一处）。内嵌在平台 iframe 时由 nav.css 隐藏。 */
function renderTopNav() {
  const el = document.getElementById('gnav');
  if (el && window.PlatformNav) window.PlatformNav.render(el, '/locator');
}

async function init() {
  renderTopNav();
  setupEmbedBar();
  // 先加载设备下拉并确定 state.serial（恢复上次选中），status/refresh 都按它请求
  await loadDevices();
  const st = await fetch('api/status?serial=' + encodeURIComponent(state.serial || '')).then(r => r.json()).catch(() => null);
  const devInfo = $('dev-info');
  // 版本号以服务端为准（页面缓存旧版本时也能纠正显示）
  if (st && st.version) $('app-version').textContent = st.version;
  if (st && st.ok) {
    state.serial = st.serial || state.serial;
    devInfo.innerHTML = devInfoHtml(st.device, st.serial);
    devInfo.className = 'dev-info ok';
  } else {
    devInfo.textContent = st ? st.msg : '连接失败';
    devInfo.className = 'dev-info bad';
  }
  loadLibraryFiles();
  loadPages();
  if (st && st.ok) refresh(true);
  $('btn-refresh').addEventListener('click', () => refresh(true));
  const brs = $('btn-restart');
  if (brs) brs.addEventListener('click', () => refresh(false));
  const bc = $('btn-collect');
  if (bc) {
    bc.addEventListener('click', startCollect);
    $('collect-file').addEventListener('change', () => {
      $('collect-file-new-wrap').style.display = $('collect-file').value === '__new__' ? '' : 'none';
    });
    $('collect-check-all').addEventListener('change', e => {
      _collectItems.forEach(i => { i._pick = e.target.checked; });
      renderCollectItems();
    });
    $('btn-collect-cancel').addEventListener('click', () => { $('collect-mask').style.display = 'none'; });
    $('btn-collect-save').addEventListener('click', saveCollect);
  }
  $('shot').addEventListener('click', onShotClick);
  $('shot').addEventListener('dblclick', onShotDblClick);   // 双击执行器：设备真实点击
  // 截图显示尺寸：机型预设切换 + 记住上次选择
  // （判空防御：浏览器缓存了旧版 index.html 时该下拉不存在，避免 init 中断）
  const sizeSel = document.getElementById('shot-size-sel');
  if (sizeSel) {
    sizeSel.addEventListener('change', applyShotSize);
    try { sizeSel.value = localStorage.getItem('locator_shot_size') || 'default'; } catch (e) {}
    applyShotSize();
  }
  $('btn-tap').addEventListener('click', onTapElement);      // ▶ 设备上点击
  // 多设备切换下拉（判空防御：浏览器缓存了旧版 index.html 时该下拉不存在）
  const devSel = document.getElementById('device-sel');
  if (devSel) devSel.addEventListener('change', onDeviceChange);
  $('tree-search').addEventListener('input', onTreeSearch);
  $('tree-search').addEventListener('keydown', (e) => { if (e.key === 'Enter') locateSearchTree(); });
  const bts = $('btn-tree-search');
  if (bts) bts.addEventListener('click', locateSearchTree);
  $('btn-add').addEventListener('click', openModal);
  $('btn-modal-cancel').addEventListener('click', () => {
    $('modal-mask').style.display = 'none';
  });
  $('btn-modal-save').addEventListener('click', () => onSaveElement(false));
  $('btn-modal-save-continue').addEventListener('click', () => onSaveElement(true));
  // 树 Diff 开关 / 定位器体检 / 会话步骤撤销
  initDialog();
  $('btn-tree-diff').addEventListener('click', toggleTreeDiff);
  $('btn-coord-mode').addEventListener('click', toggleCoordMode);
  $('btn-locate-check').addEventListener('click', runLocateCheck);
  $('btn-undo-step').addEventListener('click', undoLastStep);
  // 临时用例未导出时，离开页面前提醒（防误关丢失已录步骤）
  window.addEventListener('beforeunload', (e) => {
  });
  document.querySelectorAll('input[name="el-purpose"]').forEach(r => r.addEventListener('change', onPurposeChange));
  $('el-op-type').addEventListener('change', (e) => {
    onOpTypeChange(); onCaseFileChange(); syncOpCards();
    if (e.isTrusted) {                        // 用户显式选操作类型 → 特殊操作清空并视觉置灰
      $('el-op-special').value = '';
      onSpecialOpChange();
      applyOpMutual();
    }
  });
  $('el-op-special').addEventListener('change', (e) => {
    onSpecialOpChange();
    if (e.isTrusted && $('el-op-special').value) $('el-op-type').value = currentOpType();   // 特殊侧生效时类型回显当前兜底值
    applyOpMutual();
  });
  buildOpGrid();
  $('el-op-special').addEventListener('change', onSpecialOpChange);
  $('el-op-param').addEventListener('input', () => { paramAuto = false; followStepDesc(); });
  $('el-case-file').addEventListener('change', onCaseFileChange);
  // 新建文件输入联动：元素文件切「新建」显隐输入行；用例名输入实时派生页面/元素文件名
  $('el-file').addEventListener('change', () => {
    $('el-file-new-wrap').style.display = isNewElementFile() ? '' : 'none';
    syncElFileNote();
    fillCaseHead();
  });
  $('el-case-new').addEventListener('input', () => {
    onCaseFileChange();
  });
  // 元素文件名输入：三件派生名回显行实时跟随（留空 = 自动按用例名派生）
  $('el-file-new').addEventListener('input', updatePkgTrio);
  // 定位方式切换：从当前元素的定位候选里取该类型的值回填（ID→ID值，XPATH→XPATH值…）
  $('el-type').addEventListener('change', onElTypeChange);
  $('el-op-comment').addEventListener('input', () => { opCommentAuto = false; });
  // 步骤描述实时拼接：改元素中文名/元素名称立刻刷新描述（手输过描述则不覆盖）
  $('el-cn-name').addEventListener('input', followStepDesc);
  $('el-name').addEventListener('input', followStepDesc);
  $('el-insert-pos').addEventListener('change', () => { renderStepsList(currentSteps()); });
  // （v6.11 残留的「顶部快速打开」死调用已清除——其 HTML 与函数定义早已删除，
  //   但调用漏删导致 init 在此 ReferenceError 中断，后面的问号提示/三栏拖拽全部失效）
  bindHelpIcons();
  bindColumnResizers();
}

/* ---------- 三栏拖拽调宽：手柄在左/中栏之后，拖动时相邻两栏宽度此消彼长，
   栏内内容（截图/树/教学）按栏宽等比跟随；宽度记忆在 localStorage ---------- */
function bindColumnResizers() {
  const left = document.querySelector('.col.left');
  const mid = document.querySelector('.col.middle');
  const right = document.querySelector('.col.right');
  if (!left || !mid || !right) return;
  // 右栏固定 340px（v6.11.1：历史拖拽记忆导致右栏被挤窄且无法复原——不再恢复/记忆列宽）
  try { localStorage.removeItem('locator_col_widths'); } catch (e) {}
  right.style.flex = '0 0 340px';
  mid.style.flex = '1 1 auto';
  left.style.flex = '0 1 360px';
  document.querySelectorAll('.col-resizer').forEach(handle => {
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const which = handle.dataset.resize;             // left: 左↔中；middle: 中↔右
      const mainRect = document.querySelector('main').getBoundingClientRect();
      const cw = mainRect.width - 24;
      handle.classList.add('dragging');
      document.body.classList.add('col-resizing');
      const onMove = (ev) => {
        // 手柄位置 → 栏宽（px 基准）。拖左手柄时左/中栏同时定宽（中栏吸收差值），
        // 拖中手柄时只动中栏（右栏 flex:1 吸收）；各栏 280px 下限，绝不撑出横向滚动。
        const relX = ev.clientX - mainRect.left - 12;  // 减 main 左 padding
        const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
        if (which === 'left') {
          // 右栏固定 340（v6.11.1），中栏 flex:1 吸收差值
          const rightW = right.getBoundingClientRect().width || 340;
          const avail = cw - 60 - rightW;
          const leftW = clamp(relX, 280, avail - 280);
          left.style.flex = '0 1 ' + Math.round(leftW) + 'px';
          mid.style.flex = '1 1 auto';
        }
      };
      const onUp = () => {
        handle.classList.remove('dragging');
        document.body.classList.remove('col-resizing');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });
}

/* ---------- 字段帮助：鼠标移到「?」即显示该字段有什么用 ---------- */
const HELP_TIP_W = 330;
function bindHelpIcons() {
  const tip = $('help-tip');
  let showTimer = null, hideTimer = null, tipOn = false;
  function showTip(icon) {
    clearTimeout(hideTimer);
    const text = icon.getAttribute('data-help') || '';
    tip.textContent = text;
    tip.style.display = '';
    const r = icon.getBoundingClientRect();
    let left = r.left;
    if (left + HELP_TIP_W > window.innerWidth - 10) left = Math.max(10, window.innerWidth - HELP_TIP_W - 10);
    let top = r.bottom + 6;
    const estH = text.length > 90 ? 260 : 160;
    if (top + estH > window.innerHeight - 10) top = Math.max(10, r.top - estH - 6);
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
    tipOn = true;
  }
  function hideTip() {
    // 鼠标移出问号后延迟关闭；若已移入气泡则保持
    if (tipOn) {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => { tip.style.display = 'none'; tipOn = false; }, 180);
    }
  }
  document.addEventListener('mouseover', (e) => {
    const icon = e.target.closest('.help-icon');
    if (icon) { showTip(icon); return; }
  });
  document.addEventListener('mouseout', (e) => {
    const icon = e.target.closest && e.target.closest('.help-icon');
    if (icon) return;
    const to = e.relatedTarget;
    if (to && to.closest && to.closest('.help-tip')) return;  // 移入气泡 → 保持显示
    hideTip();
  });
  // 气泡本身：移入保持、移出关闭
  tip.addEventListener('mouseenter', () => { clearTimeout(hideTimer); });
  tip.addEventListener('mouseleave', () => { tip.style.display = 'none'; tipOn = false; });
}

/* ---------- 多设备切换 ---------- */
/* 设备下拉选项文案：完整 serial，不做截断（同型号多台设备靠它区分，截断后无法分辨） */
function deviceOptionText(d) {
  return d.model + ' · Android ' + d.platformVersion + '（' + (d.serial || '') + '）';
}

/* 设备信息展示：型号+系统版本一行，设备ID（serial）单独一行完整显示。
   抽出来是因为 init() 与 refresh() 两处都要写同一份内容，避免改一处漏一处。 */
function devInfoHtml(device, serial) {
  return '📱 ' + esc(device.model) + ' · Android ' + esc(device.platformVersion) +
    '<br><span class="dev-id" title="设备ID（adb serial）">' + esc(serial || '') + '</span>';
}

async function loadDevices() {
  const sel = $('device-sel');
  if (!sel) return;
  const r = await fetch('api/devices').then(r => r.json()).catch(() => null);
  if (!r || !r.ok || !(r.devices || []).length) {
    sel.innerHTML = '<option value="">无设备</option>';
    return;
  }
  sel.innerHTML = r.devices.map(d =>
    '<option value="' + esc(d.serial) + '">' + esc(deviceOptionText(d)) + '</option>').join('');
  // 恢复上次选中的设备（同一台服务器上刷新页面不跳回第一台）
  let want = null;
  try { want = localStorage.getItem('locator_serial'); } catch (e) {}
  if (want && r.devices.some(d => d.serial === want)) {
    sel.value = want;
    state.serial = want;
  } else if (!state.serial && r.devices.length) {
    state.serial = r.devices[0].serial;
    sel.value = state.serial;
  }
}
/* 切换设备：立即清掉上一台设备的痕迹（旧截图/选中态/元素树），
   避免新截图回来前点到旧图造成坐标错位；然后马上刷新新设备画面 */
function onDeviceChange() {
  const sel = $('device-sel');
  const serial = sel.value;
  if (!serial || serial === state.serial) return;
  state.serial = serial;
  try { localStorage.setItem('locator_serial', serial); } catch (e) {}
  // 清旧设备痕迹
  state.tree = null; state.all = [];
  state.selUid = null; state.selNode = null; state.hitCands = null;
  $('shot').style.display = 'none';
  $('shot-overlay').style.display = 'none';
  $('detail').style.display = 'none';
  $('shot-empty').style.display = 'block';
  $('shot-empty').textContent = '正在切换设备…';
  $('tree').innerHTML = '';
  const dv = $('dev-info');
  dv.textContent = '切换中…'; dv.className = 'dev-info';
  refresh(true);
}

/* ---------- 刷新：截图 + 元素树 ----------
   token 竞态防护：刷新期间用户切换/连切设备时，慢的旧响应若后到会覆盖新设备画面——
   每次请求带自增 token，响应回来时 token 已不是最新 → 丢弃；
   服务端标记 fallback（请求设备掉线回退）→ 校正下拉；其余 serial 不一致（过期响应）→ 丢弃 */
let refreshSeq = 0;
/* 设备点击后的提示收尾：把「…刷新中…」替换为最终结果（修复提示永久卡在刷新中） */
function settleTapTip(ok, msg) {
  const tip = $('tap-tip');
  if (!tip || tip.textContent.indexOf('刷新中…') < 0) return;
  tip.textContent = ok ? '✓ 已点击设备，页面已刷新' : '✕ 刷新失败：' + (msg || '未知原因');
  tip.className = 'tap-tip ' + (ok ? 'ok' : 'err');
  clearTimeout(settleTapTip._t);
  settleTapTip._t = setTimeout(() => { tip.textContent = ''; tip.className = 'tap-tip'; }, 4000);
}
/* fast=true ⚡刷新：单次 dump 最快路径；fast=false ♻ 重启：完整自愈链（可重启 adb） */
async function refresh(fast = false) {
  const myToken = ++refreshSeq;
  const btn = $(fast ? 'btn-refresh' : 'btn-restart');
  const other = $(fast ? 'btn-restart' : 'btn-refresh');
  btn.querySelector('.bt-tx').textContent = fast ? '刷新中…' : '重启中…'; btn.disabled = true; other.disabled = true;
  try {
    const r = await fetch('api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serial: state.serial, fast: !!fast }),
    }).then(r => r.json()).catch(() => null);
    if (myToken !== refreshSeq) return;          // 已有更新的刷新/切换，丢弃过期响应
    if (!r || !r.ok) {
      // 失败不打断操作（不再用系统 alert）：空态区展示原因+下一步，设备下拉红色提示
      const msg = r && r.msg ? r.msg : '刷新失败';
      $('shot-empty').textContent = msg + '，请检查设备连接后点「刷新」重试';
      $('shot-empty').style.display = 'block';
      const dv = $('dev-info');
      dv.textContent = '⚠ ' + msg;
      dv.className = 'dev-info bad';
      settleTapTip(false, msg);
      if (fast) showToast('⚡ 快速刷新失败——可点「♻ 重启」走完整自愈');
      else showToast('重启失败：' + msg);
      return;
    }
    // 掉线回退校正：请求的 A 已掉线，服务端用 B 响应并标记 fallback → 更正下拉并提示
    if (r.fallback && r.serial && r.serial !== state.serial) {
      const sel = $('device-sel');
      if (sel && sel.querySelector('option[value="' + r.serial + '"]')) {
        sel.value = r.serial;
        state.serial = r.serial;
        try { localStorage.setItem('locator_serial', r.serial); } catch (e) {}
        const dv = $('dev-info');
        dv.textContent = '⚠ 原设备已掉线，已切换到第一台在线设备';
        dv.className = 'dev-info bad';
      }
    }
    state.width = r.width; state.height = r.height;
    state.tree = r.tree; state.all = r.all || [];
    // 刷新成功：状态栏同步当前设备（切换设备后从「切换中…」恢复为设备信息）。
    // 注意：上面发生掉线回退时已写入「⚠ 已掉线」警告，这里不能再覆盖掉它
    if (r.device && !r.fallback) {
      const dv = $('dev-info');
      dv.innerHTML = devInfoHtml(r.device, r.serial);
      dv.className = 'dev-info ok';
    }
    // 统一分配 uid（DFS 先父后子，tree 与 all 顺序一致）
    let seq = 1;
    (function assign(node) { node.uid = seq++; node.children.forEach(assign); })(state.tree);
    let k = 0;
    (function assignAll(node) { state.all[k++].uid = node.uid; node.children.forEach(assignAll); })(state.tree);
    applyTreeDiff();
    state.selUid = null; state.selNode = null;
    state.hitCands = null;
    $('detail').style.display = 'none';
    $('shot-empty').style.display = 'none';
    const img = $('shot');
    img.src = r.screenshot; img.style.display = 'block';
    renderTree(state.tree);
    if (!fast) showToast('重启完成');
    settleTapTip(true);
  } catch (err) {
    console.error('[locator] refresh error:', err);
    // 把错误直接显示在页面上，避免 try/finally 静默吞掉异常导致"点了没反应"
    $('shot-empty').textContent = '刷新出错: ' + (err && err.message ? err.message : String(err));
    $('shot-empty').style.display = 'block';
    settleTapTip(false, '刷新出错');
  } finally {
    btn.querySelector('.bt-tx').textContent = fast ? '刷新' : '重启';
    btn.disabled = false; other.disabled = false;
  }
}

/* ---------- 截图点击命中 ---------- */
// 由点击事件算出命中的最内层元素 + 所有包含该点的候选（按面积升序）
/* 截图点击 → 设备坐标：PNG 像素 → XML 顶部对齐坐标（华为机底部导航条差值，见 hitFromEvent 注释） */
function shotPointFromEvent(e) {
  const img = $('shot');
  const rect = img.getBoundingClientRect();
  if (rect.width <= 0) return null;
  const natW = img.naturalWidth || state.width;
  const natH = img.naturalHeight || state.height;
  const px = (e.clientX - rect.left) / rect.width * natW;
  const py = Math.min((e.clientY - rect.top) / rect.height * natH, state.height);
  return [Math.round(px), Math.round(py)];
}

function hitFromEvent(e) {
  if (!state.all.length) return null;
  const pt = shotPointFromEvent(e);
  if (!pt) return null;
  const px = pt[0], py = pt[1];
  // 收集所有包含该点的元素，按面积升序（越小越内层），作为候选列表
  const cands = [];
  for (const n of state.all) {
    const b = n.bounds_num;
    if (!b || b.length !== 4) continue;
    const [x1, y1, x2, y2] = b;
    if (x1 <= px && px <= x2 && y1 <= py && py <= y2) {
      const area = (x2 - x1) * (y2 - y1);
      if (area > 0) cands.push({ node: n, area });
    }
  }
  cands.sort((a, b) => a.area - b.area);
  if (!cands.length) return null;
  return { hit: cands[0].node, cands: cands.map(c => c.node) };
}
function onShotClick(e) {
  // ⌖ 坐标模式：选的就是这个点，不再命中容器节点（用于无障碍盲区，如自绘弹层选项）
  if (state.coordMode) {
    const pt = shotPointFromEvent(e);
    if (!pt) return;
    state.coordPoint = pt;
    highlightBounds([pt[0] - 45, pt[1] - 45, pt[0] + 45, pt[1] + 45]);
    // 中间「选中元素」窗口同步显示坐标（虚拟节点，不进元素树）——点「添加测试用例」即可录入
    const vnode = {
      uid: -1,
      text: '⌖ 坐标 (' + pt[0] + ', ' + pt[1] + ')',
      center: [pt[0], pt[1]],
      bounds: '[' + (pt[0] - 45) + ',' + (pt[1] - 45) + '][' + (pt[0] + 45) + ',' + (pt[1] + 45) + ']',
      bounds_num: [pt[0] - 45, pt[1] - 45, pt[0] + 45, pt[1] + 45],
      class: '⌖ 坐标点',
      clickable: true,
    };
    state.selNode = vnode; state.selUid = null; state.hitCands = null;
    renderDetail(vnode);
    showToast('⌖ 已选坐标 (' + pt[0] + ', ' + pt[1] + ') · 点「添加测试用例」将以「坐标点击」录入；双击 = 真机点这个点');
    return;
  }
  const r = hitFromEvent(e);
  if (!r) return;
  state.hitCands = r.cands;
  selectNode(r.hit.uid);
  // 命中提示 toast 已移除：元素树会自动跳转高亮到该元素，信息不重复（v6.11.4）
}
// 双击执行器：双击截图 = 在设备上真实点击该元素（验证定位是否准确）
function onShotDblClick(e) {
  // ⌖ 坐标模式：双击 = 真机点这个精确点
  if (state.coordMode) {
    const pt = shotPointFromEvent(e);
    if (!pt) return;
    state.coordPoint = pt;
    highlightBounds([pt[0] - 45, pt[1] - 45, pt[0] + 45, pt[1] + 45]);
    // 双击后中间窗口同样显示坐标，便于直接录步骤
    const vnode = {
      uid: -1,
      text: '⌖ 坐标 (' + pt[0] + ', ' + pt[1] + ')',
      center: [pt[0], pt[1]],
      bounds: '[' + (pt[0] - 45) + ',' + (pt[1] - 45) + '][' + (pt[0] + 45) + ',' + (pt[1] + 45) + ']',
      bounds_num: [pt[0] - 45, pt[1] - 45, pt[0] + 45, pt[1] + 45],
      class: '⌖ 坐标点',
      clickable: true,
    };
    state.selNode = vnode; state.selUid = null; state.hitCands = null;
    renderDetail(vnode);
    tapOnDevice(pt, '⌖ 坐标 (' + pt[0] + ', ' + pt[1] + ')');
    showToast('⌖ 已在设备上点击 (' + pt[0] + ', ' + pt[1] + ') · 可点「添加测试用例」以「坐标点击」录入');
    return;
  }
  const r = hitFromEvent(e);
  if (!r) return;
  state.hitCands = r.cands;
  selectNode(r.hit.uid);
  showHitToast(r.hit, r.cands.length, ' · 已在设备上真实点击');
  tapOnDevice(r.hit.center, r.hit.text || r.hit['resource-id'] || '双击元素');
}

/* ---------- 居中对话框：替代浏览器原生 alert/confirm（原生弹窗贴页面顶部，不在视觉中心） ---------- */
let _dlgResolve = null;
function _dlgShown() { return $('ui-dlg-mask').style.display !== 'none'; }
function _dlgClose(val) {
  const mask = $('ui-dlg-mask');
  if (mask) mask.style.display = 'none';
  const r = _dlgResolve; _dlgResolve = null;
  if (r) r(val);
}
function uiDialog(msg, opts) {
  opts = opts || {};
  $('ui-dlg-title').textContent = opts.title || '提示';
  $('ui-dlg-msg').textContent = msg == null ? '' : String(msg);
  $('ui-dlg-ok').textContent = opts.okText || '确定';
  const cancelBtn = $('ui-dlg-cancel');
  cancelBtn.style.display = (opts.cancel === false) ? 'none' : '';
  $('ui-dlg-mask').style.display = 'flex';
  cancelBtn.blur(); $('ui-dlg-ok').focus();
  return new Promise(resolve => { _dlgResolve = resolve; });
}
function uiAlert(msg, opts) {
  return uiDialog(msg, Object.assign({ title: '提示', okText: '好', cancel: false }, opts || {}));
}
function uiConfirm(msg, opts) {
  return uiDialog(msg, Object.assign({ title: '请确认', okText: '确定' }, opts || {}));
}
function initDialog() {
  $('ui-dlg-ok').addEventListener('click', () => _dlgClose(true));
  $('ui-dlg-cancel').addEventListener('click', () => _dlgClose(false));
  $('ui-dlg-mask').addEventListener('click', e => { if (e.target === $('ui-dlg-mask')) _dlgClose(false); });
  document.addEventListener('keydown', e => {
    if (!_dlgShown()) return;
    if (e.key === 'Escape') { e.preventDefault(); _dlgClose(false); }
    else if (e.key === 'Enter') { e.preventDefault(); _dlgClose(true); }
  });
}

/* ---------- 居中提示（通用）：原地静止显示 3 秒自动消失，pointer-events:none 不阻挡任何操作 ---------- */
let hitToastTimer = null;
let hitToastHideAt = 0;   // 应隐藏的时刻（ms）；后台标签页定时器被浏览器节流时，回到页面立即补隐藏
function hideHitToast() {
  const t = $('hit-toast');
  if (t) t.style.display = 'none';
  hitToastHideAt = 0;
}
function showToast(msg) {
  const t = $('hit-toast');
  if (!t) return;
  t.textContent = msg;
  t.style.display = '';   // 原地静止显示：无入场动画、无动画重播，弹出瞬间零重排
  clearTimeout(hitToastTimer);
  hitToastHideAt = Date.now() + 3000;
  hitToastTimer = setTimeout(hideHitToast, 3000);
}
// 页面从后台切回时：浏览器对后台标签的 setTimeout 会节流推迟，此时按应隐藏时刻立即补隐藏
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && hitToastHideAt && Date.now() >= hitToastHideAt) {
    clearTimeout(hitToastTimer);
    hideHitToast();
  }
});
function showHitToast(node, candCount, extra) {
  const name = (node.text && node.text.trim()) ? '「' + truncate(node.text.trim(), 12) + '」'
    : (node['resource-id'] ? truncate(node['resource-id'].split('/').pop(), 16) : candName(node));
  const coords = node.center ? ' · 中心坐标 (' + node.center.join(', ') + ')' : '';
  const multi = candCount > 1 ? ' · 共命中 ' + candCount + ' 层，可在中间栏选更精确的一层' : '';
  showToast('🎯 已命中 ' + name + coords + multi + extra);
}
// 「▶ 设备上点击」按钮：点击选中的元素
async function onTapElement() {
  const n = state.selNode;
  if (!n) { alert('请先选中一个元素'); return; }
  if (!n.center) { alert('该元素没有坐标，无法点击'); return; }
  tapOnDevice(n.center, n.text || n['resource-id'] || '选中元素');
}
async function tapOnDevice(center, label) {
  if (!center || center.length < 2) return;
  const x = center[0], y = center[1];
  const r = await fetch('api/tap', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ x: x, y: y, serial: state.serial }),
  }).then(r => r.json()).catch(() => null);
  const tip = $('tap-tip');
  if (r && r.ok) {
    tip.textContent = '✓ 已点击设备（' + label + '）(' + x + ',' + y + ')，刷新中…';
    tip.className = 'tap-tip ok';
    refresh(true);
  } else {
    tip.textContent = (r && r.msg ? r.msg : '点击失败');
    tip.className = 'tap-tip err';
  }
}

/* ---------- 树渲染 ---------- */
function renderTree(tree) {
  const box = $('tree');
  box.innerHTML = '';
  // 树 Diff：消失项摘要置顶（消失节点无法在重建的树里"原位"展示，集中列出）
  if (state.treeDiffOn && state.goneSigs && state.goneSigs.length) {
    const gone = document.createElement('div');
    gone.className = 'tree-gone';
    gone.textContent = '🔴 较上次刷新消失 ' + state.goneSigs.length + ' 项：'
      + state.goneSigs.slice(0, 6).map(prettySig).join('、') + (state.goneSigs.length > 6 ? ' …' : '');
    box.appendChild(gone);
  }
  box.appendChild(buildTreeUl(tree));
}
/* ---------- 页面树 Diff ---------- */
function nodeSig(n) {
  // 签名不含 bounds：滚动会整体位移，按 class/rid/text/desc 判定"新增/消失"才稳定
  return [n.class || '', n['resource-id'] || '', (n.text || '').trim(), n['content-desc'] || ''].join('|');
}
function applyTreeDiff() {
  if (!state.tree) return;
  const prev = state.treeDiffOn ? state.prevSigs : null;
  const cur = new Set();
  state.goneSigs = [];
  (function walk(n) {
    const s = nodeSig(n);
    cur.add(s);
    n._diffNew = !!(prev && !prev.has(s));
    n.children.forEach(walk);
  })(state.tree);
  if (prev) prev.forEach(s => { if (!cur.has(s)) state.goneSigs.push(s); });
  state.prevSigs = state.treeDiffOn ? cur : null;
}
function prettySig(sig) {
  const [cls, rid, text, desc] = sig.split('|');
  if (text) return '「' + truncate(text, 10) + '」';
  if (rid) return truncate(rid.split('/').pop(), 14);
  if (desc) return truncate(desc, 10);
  return truncate((cls || 'node').split('.').pop(), 12);
}
function buildTreeUl(node) {
  const ul = document.createElement('ul');
  appendNode(ul, node);
  return ul;
}
// 把节点 n 渲染成一个 li 追加到 ul；有子节点时嵌套可折叠层（递归子节点，而不是重复渲染 n 自己）
function appendNode(ul, n) {
  const li = document.createElement('li');
  const row = document.createElement('div');
  row.className = 'tnode' + (state.selUid === n.uid ? ' sel' : '');
  row.dataset.uid = n.uid;
  const hasKids = n.children && n.children.length > 0;
  const arrow = document.createElement('span');
  arrow.className = 'arrow';
  arrow.textContent = hasKids ? '▾' : '';
  const text = document.createElement('span');
  text.className = 't-text';
  text.textContent = (n.text && n.text.trim()) ? truncate(n.text, 18) : (n['resource-id'] ? truncate(n['resource-id'].split('/').pop(), 22) : (n['content-desc'] || n.class || 'node'));
  if (!n.text && !n['resource-id']) { text.style.color = '#9ca3af'; }
  row.appendChild(arrow);
  row.appendChild(text);
  if (n['resource-id']) {
    const rid = document.createElement('span');
    rid.className = 't-rid'; rid.textContent = truncate(n['resource-id'], 24);
    row.appendChild(rid);
  }
  if (n.clickable) {
    const badge = document.createElement('span');
    badge.className = 'clickable-badge'; badge.textContent = '可点';
    row.appendChild(badge);
  }
  if (state.treeDiffOn && n._diffNew) {
    const nb = document.createElement('span');
    nb.className = 'diff-new-badge'; nb.textContent = '🟢新增';
    row.appendChild(nb);
  }
  row.addEventListener('click', (ev) => { ev.stopPropagation(); selectNode(n.uid); });
  li.appendChild(row);
  if (hasKids) {
    const sub = document.createElement('div');
    const childUl = document.createElement('ul');
    n.children.forEach(c => appendNode(childUl, c));
    sub.appendChild(childUl);
    const toggle = () => { sub.style.display = sub.style.display === 'none' ? '' : 'none'; arrow.textContent = sub.style.display === 'none' ? '▸' : '▾'; };
    row.addEventListener('dblclick', toggle);
    // 保留展开
    li.appendChild(sub);
  }
  ul.appendChild(li);
}
function truncate(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; }

/* 树 Diff 开关：开启时以当前树为新基线（当前刷新不标新增），之后每次刷新对比上次 */
function toggleTreeDiff() {
  state.treeDiffOn = !state.treeDiffOn;
  $('btn-tree-diff').querySelector('.bt-tx').textContent = state.treeDiffOn ? '树对比：开' : '树对比：关';
  $('btn-tree-diff').classList.toggle('on', state.treeDiffOn);
  showToast(state.treeDiffOn ? '开启成功' : '已关闭');
  state.prevSigs = null;
  state.goneSigs = [];
  if (state.tree) {
    (function clear(n) { n._diffNew = false; n.children.forEach(clear); })(state.tree);
    applyTreeDiff();
    renderTree(state.tree);
  }
}

/* 树搜索：按 text / resource-id / class 过滤（命中节点保留，父链保留） */
function onTreeSearch(e) {
  if (!state.tree) return;
  const kw = e.target.value.trim().toLowerCase();
  searchHitIdx = -1; searchHitKw = '';       // 新搜索词重置循环定位
  if (!kw) { renderTree(state.tree); return; }
  const filtered = filterTree(state.tree, kw);
  $('tree').innerHTML = '';
  if (filtered) $('tree').appendChild(buildTreeUl(filtered));
  else $('tree').innerHTML = '<div class="empty" style="padding:16px">没有匹配的元素（改关键词或清空恢复全树）</div>';
}
function filterTree(node, kw) {
  const children = (node.children || [])
    .map(c => filterTree(c, kw))
    .filter(Boolean);
  const selfHit = [node.text, node['resource-id'], node.class].some(v => String(v || '').toLowerCase().includes(kw));
  if (selfHit || children.length) {
    return Object.assign({}, node, { children });
  }
  return null;
}

/* ---------- 选中元素 ---------- */
function findByUid(node, uid) {
  if (node.uid === uid) return node;
  for (const c of node.children || []) { const r = findByUid(c, uid); if (r) return r; }
  return null;
}
function selectNode(uid) {
  if (!state.tree) return;
  const node = findByUid(state.tree, uid);
  if (!node) return;
  state.selUid = uid; state.selNode = node;
  // 树高亮
  document.querySelectorAll('.tree .tnode').forEach(el => {
    el.classList.toggle('sel', +el.dataset.uid === uid);
  });
  renderDetail(node);
  highlightShot(node);
  scrollTreeToUid(uid);
}
/* 元素树滚动定位到指定节点并短暂高亮（截图点选 / 搜索定位共用） */
function scrollTreeToUid(uid) {
  const li = document.querySelector('.tree .tnode[data-uid="' + uid + '"]');
  if (!li) return;
  li.scrollIntoView({ block: 'nearest' });
  li.classList.remove('search-hit');
  void li.offsetWidth;
  li.classList.add('search-hit');
  setTimeout(() => li.classList.remove('search-hit'), 2600);
}
/* 搜索定位：回车/点🔍 → 循环定位到匹配节点（全树文本匹配），并联动选中与高亮 */
let searchHitIdx = -1, searchHitKw = '';
function locateSearchTree() {
  const kw = ($('tree-search').value || '').trim().toLowerCase();
  if (!kw || !state.tree) return;
  if (kw !== searchHitKw) { searchHitIdx = -1; searchHitKw = kw; }
  const nodes = (state.all || []).filter(n =>
    [n.text, n['resource-id'], n.class].some(v => String(v || '').toLowerCase().includes(kw)));
  if (!nodes.length) { showToast('没有匹配的元素'); return; }
  searchHitIdx = (searchHitIdx + 1) % nodes.length;
  const n = nodes[searchHitIdx];
  showToast('定位到匹配元素 ' + (searchHitIdx + 1) + '/' + nodes.length);
  if (n.uid != null && n.uid >= 0) selectNode(n.uid);
  else scrollTreeToUid(-1);
}
function highlightShot(node) {
  highlightBounds(node.bounds_num);
}
function highlightBounds(b) {
  const ov = $('shot-overlay');
  const img = $('shot');
  if (!b || b.length !== 4 || img.style.display === 'none') { ov.style.display = 'none'; return; }
  const scale = img.clientWidth / state.width;
  const [x1, y1, x2, y2] = b;
  ov.style.display = 'block';
  // 截图选了机型预设时居中显示，高亮框要加上图片在栏内的偏移
  ov.style.left = (img.offsetLeft + x1 * scale) + 'px';
  ov.style.top = (img.offsetTop + y1 * scale) + 'px';
  ov.style.width = ((x2 - x1) * scale) + 'px';
  ov.style.height = ((y2 - y1) * scale) + 'px';
}

/* ---------- 截图显示尺寸（默认铺满栏宽；机型预设按其逻辑屏幕尺寸居中显示） ---------- */
// iPhone15Pro 逻辑分辨率 393×852；iQOO15 为 2K(1440×3168) 按 560dpi 换算约 411×905
const SHOT_SIZES = { iphone15pro: 393, iqoo15: 411 };
function applyShotSize() {
  const sel = $('shot-size-sel');
  const img = $('shot');
  const v = sel ? sel.value : 'default';
  try { localStorage.setItem('locator_shot_size', v); } catch (e) { /* 隐私模式忽略 */ }
  const w = SHOT_SIZES[v];
  if (w) {
    img.classList.add('centered');
    img.style.width = w + 'px';
    img.style.height = 'auto';
  } else {
    img.classList.remove('centered');
    img.style.width = '';
    img.style.height = '';
  }
  if (state.selNode) highlightShot(state.selNode);
}
function renderDetail(node) {
  $('detail').style.display = 'block';
  // 候选元素：截图同一点可能命中多层（容器/文字/按钮），点选更精确的
  const candBox = $('hit-cands');
  if (state.hitCands && state.hitCands.length > 1) {
    candBox.style.display = '';
    candBox.innerHTML = '<span class="cand-label">命中 ' + state.hitCands.length + ' 层，选一个：</span>' +
      state.hitCands.map(n =>
        '<button class="cand-chip' + (n.uid === node.uid ? ' sel' : '') + '" data-uid="' + n.uid + '">'
        + esc(candName(n)) + '</button>').join('');
    candBox.querySelectorAll('.cand-chip').forEach(btn => {
      btn.addEventListener('click', () => selectNode(+btn.dataset.uid));
    });
  } else {
    candBox.style.display = 'none';
  }
  const ATTRS = ['text', 'resource-id', 'class', 'content-desc', 'bounds', 'clickable', 'focusable', 'scrollable', 'selected', 'enabled', 'package', 'index'];
  const HOT_KEYS = { 'text': 1, 'resource-id': 1 };   // 核心定位字段：值加粗强调
  const rows = ATTRS.filter(k => node[k] !== undefined && node[k] !== '' && node[k] !== false)
    .map(k => '<tr' + (HOT_KEYS[k] ? ' class="hot"' : '') + '><td>' + esc(k) + '</td><td>' + esc(node[k]) + '</td></tr>')
    .join('');
  // 重复 resource-id 提示
  const rid = node['resource-id'];
  const sameCount = rid ? state.all.filter(n => n['resource-id'] === rid).length : 0;
  const dupTip = sameCount > 1
    ? '<div class="dup-tip">⚠ 该 resource-id 页面有 <b>' + sameCount + '</b> 个相同的，定位会不准。' +
      '用例里用 <code>appOperator.getElements(元素)[i]</code> 按下标取第 i 个（0 开始），' +
      '或用下面带 <code>instance</code> / 下标 的写法。</div>' : '';
  $('detail-attrs').innerHTML = rows + '<tr class="hot"><td>中心坐标</td><td>' + (node.center ? node.center.join(', ') : '-') + '</td></tr>';
  $('dup-tip').innerHTML = dupTip;
  // 定位写法
  const locs = node.locators || [];
  const box = $('locators');
  box.innerHTML = '';
  if (!locs.length) { box.innerHTML = '<div class="loc-item">该元素无合适定位表达式</div>'; return; }
  locs.forEach((loc, i) => {
    const div = document.createElement('div');
    div.className = 'loc-item';
    div.innerHTML = '<label><input type="radio" name="loc" data-lt="' + esc(loc.locator_type) + '" data-val="' + esc(loc.value) + '"' + (i === 0 ? ' checked' : '') + '> <span class="loc-kind">' + esc(loc.kind) + '</span> <span class="loc-desc">' + esc(loc.desc || '') + '</span></label>'
      + '<code>' + esc(loc.value) + '</code>';
    box.appendChild(div);
  });
}
function candName(n) {
  if (n.text && n.text.trim()) return n.text.trim().slice(0, 12);
  const r = (n['resource-id'] || '').split('/').pop();
  if (r) return r;
  if (n['content-desc']) return n['content-desc'].slice(0, 12);
  return (n.class || 'node').split('.').pop();
}
/* ---------- 定位器体检：按选中定位在当前页面实查元素（验证定位是否仍有效） ---------- */
async function runLocateCheck() {
  const res = $('check-result');
  const loc = selectedLocator();
  if (!loc || !loc.value) {
    res.style.display = 'block'; res.className = 'check-result bad';
    res.textContent = '请先在「定位写法」里选一个定位方式';
    return;
  }
  const btn = $('btn-locate-check');
  btn.disabled = true; btn.textContent = '🎯 查找中…';
  try {
    const r = await fetch('api/locate_check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locator_type: loc.type, locator_value: loc.value, serial: state.serial }),
    }).then(x => x.json()).catch(() => null);
    res.style.display = 'block';
    if (!r || !r.ok) {
      res.className = 'check-result bad';
      res.textContent = '体检失败：' + ((r && r.msg) || '服务异常');
      return;
    }
    if (!r.found) {
      res.className = 'check-result bad';
      res.textContent = '❌ 未命中——该定位在当前页面已失效（页面可能已变化）';
      $('shot-overlay').style.display = 'none';
      return;
    }
    const multi = r.count > 1;
    res.className = 'check-result ' + (multi ? 'warn' : 'ok');
    res.textContent = multi ? '⚠️ 命中 ' + r.count + ' 处（定位不唯一，回放会取第 1 处）' : '✅ 唯一命中，定位有效';
    if (r.bounds) highlightBounds(r.bounds);
  } finally {
    btn.disabled = false; btn.textContent = '🎯 体检：实查当前页面';
  }
}
/* ---------- 本次会话步骤撤销（LIFO）：恢复 add_code 写入前的文件内容 ---------- */
function pushUndoRecord(cr) {
  if (!cr || !cr.case_before) return;   // 写盘失败/无快照的步骤不可撤销
  state.undoStack.push({
    desc: (cr.case_file || '').split('/').pop() + '::' + (cr.method_name || ''),
    case_file: cr.case_file, case_before: cr.case_before,
    page_file: cr.page_file || '', page_before: cr.page_before || '',
  });
  updateUndoBar();
}
function updateUndoBar() {
  const bar = $('step-undo-bar');
  const n = state.undoStack.length;
  bar.style.display = n ? '' : 'none';
  $('su-count').textContent = n;
  const last = state.undoStack[n - 1];
  $('su-last').textContent = last ? ' · 最近：' + last.desc : '';
}
async function undoLastStep() {
  const rec = state.undoStack[state.undoStack.length - 1];
  if (!rec) return;
  if (!confirm('撤销最近一步「' + rec.desc + '」？\n对应文件将恢复到写入前内容（撤销按倒序进行）。')) return;
  const btn = $('btn-undo-step');
  btn.disabled = true;
  try {
    const entries = [{ kind: 'case', filename: rec.case_file.split('/').pop(), content: rec.case_before }];
    if (rec.page_file && rec.page_before) {
      entries.push({ kind: 'page', filename: rec.page_file.split('/').pop(), content: rec.page_before });
    }
    for (const e of entries) {
      const r = await fetch('api/save_file', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(e),
      }).then(x => x.json()).catch(() => null);
      if (!r || !r.ok) { alert('撤销失败：' + ((r && r.msg) || '服务异常') + '（步骤记录保留，可重试）'); return; }
    }
    state.undoStack.pop();
    updateUndoBar();
    loadCaseFiles(); loadPages(); loadLibraryFiles();
  } finally {
    btn.disabled = false;
  }
}
function selectedLocator() {
  const radio = document.querySelector('input[name="loc"]:checked');
  return radio ? { type: radio.dataset.lt, value: radio.dataset.val } : null;
}
/* 定位方式下拉切换 → 定位值联动：从当前元素生成的定位候选里找该类型的值。
   同类型有多条时优先「唯一」标记的候选（如 resource-id 唯一 / text 唯一），否则取第一条；
   该类型没有候选（如元素无 content-desc 时选 ACCESSIBILITY_ID）则保留原值不动。 */
function onElTypeChange() {
  const t = $('el-type').value;
  const cands = ((state.selNode && state.selNode.locators) || []).filter(l => l.locator_type === t);
  if (cands.length) {
    const best = cands.find(c => (c.desc || '').indexOf('唯一') >= 0) || cands[0];
    $('el-value').value = best.value;
  }
}

/* ---------- 添加到元素库 ---------- */
async function loadLibraryFiles() {
  const r = await fetch('api/library').then(r => r.json()).catch(() => null);
  if (!r || !r.ok) return;
  state.eleFiles = r.files || [];
  state.defaultEleFile = r.default || 'locator_gui_elements.py';
  // 「➕ 新建…」在最后：选择后显示新建输入行（随用例包一起生成）
  $('el-file').innerHTML = r.files.map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('')
    + '<option value="' + NEW_FILE_OPT + '">➕ 新建元素文件…</option>';
}
async function loadPages() {
  const r = await fetch('api/pages').then(r => r.json()).catch(() => null);
  if (!r || !r.ok) return;
  state.pages = r.pages || [];
  state.elementsAll = r.elements || {};
}
async function openModal() {
  // ⌖ 坐标模式：选了精确坐标即可打开（不需要树里有选中元素）
  const coordPick = state.coordMode && state.coordPoint;
  if (!state.selNode && !coordPick) { alert('请先在截图或元素树里选中一个元素（或开启坐标模式点选坐标）'); return; }
  const node = state.selNode || {};
  // 自动名称：优先 resource-id 末段，其次 text 截断；坐标模式用 coord_x_y
  let auto = '';
  const rid = node['resource-id'] || '';
  if (coordPick) auto = 'coord_' + state.coordPoint[0] + '_' + state.coordPoint[1];
  else if (rid && rid.includes('/')) auto = rid.split('/').pop();
  else if (node.text && node.text.trim()) auto = node.text.trim().replace(/\s+/g, '_').slice(0, 20);
  else auto = 'element_' + state.selUid;
  $('el-name').value = auto;
  // 元素中文名：节点有中文文案时自动预填（元素管理/测试报告的显示名）
  $('el-cn-name').value = (node.text && /[\u4e00-\u9fa5]/.test(node.text)) ? node.text.trim().slice(0, 20) : '';
  const loc = (!coordPick && selectedLocator()) || { type: 'ID', value: (!coordPick && node['resource-id']) || '' };
  // 定位方式下拉：框架 Locator_Type
  $('el-type').innerHTML = ['ID', 'XPATH', 'ACCESSIBILITY_ID', 'ANDROID_UIAUTOMATOR', 'CLASS_NAME', 'NAME']
    .map(t => '<option value="' + t + '"' + (t === loc.type ? ' selected' : '') + '>' + t + '</option>').join('');
  $('el-value').value = loc.value;
  // 等待时间：每次打开弹窗恢复框架默认 30（上一个元素的设置不串扰）
  $('el-wait-sec').value = 6;
  $('el-result').className = 'el-result'; $('el-result').textContent = '';
  $('el-content').textContent = '';
  // 写入文件默认定位器自己的元素库文件（避免误写进框架自带文件；② 会在选目标用例后自动对齐）
  resetNewFileInputs();
  $('el-file').value = state.defaultEleFile || 'locator_gui_elements.py';
  // 用途默认：直接选②（三件套一次完成：选已有用例或新建都可以）
  document.querySelector('input[name="el-purpose"][value="only"]').checked = true;
  onPurposeChange();   // 栏位显示复位（上次若用了用途③，弹窗栏要藏回、三件套栏恢复）
  $('el-op-type').innerHTML = opTypeOptions();
  $('el-op-type').value = 'click';
  $('el-op-type').disabled = false;
  $('el-op-special').value = '';   // 特殊操作每次打开复位为「无」
  $('el-op-param').value = '';
  paramAuto = true;  // 打开弹窗重置为「自动预填」状态
  // ⌖ 坐标模式：默认「坐标点击」并回填最后选中的点
  if (state.coordMode && state.coordPoint) {
    $('el-op-type').value = 'tap';
    $('el-op-param').value = state.coordPoint[0] + ',' + state.coordPoint[1];
  }
  // 步骤描述自动预填：操作类型 + 「元素中文名」（中文名未填回退元素名称）；切类型/改名实时跟随
  $('el-op-comment').value = coordPick
    ? '点击坐标(' + state.coordPoint[0] + ', ' + state.coordPoint[1] + ')'
    : autoStepComment('click', opElementLabel());  // 默认按「点击」生成；切类型时自动跟随
  opCommentAuto = true;
  $('el-page-file').value = '';
  setElLinkNote('');
  onOpTypeChange();
  await loadCaseFiles();
  // 录制会话回显：预选上次入库的用例文件；元素/页面文件由 onCaseFileChange 自动对齐
  if (state.tempCase) {
    const caseFile = 'test_' + state.tempCase.base + '.py';
    if ((state.caseFiles || []).some(c => c.file === caseFile)) {
      $('el-case-file').value = caseFile;
      onCaseFileChange();
    } else {
      state.tempCase = null;   // 用例文件已不存在（被删除）→ 会话失效
    }
  }
  document.querySelector('input[name="el-purpose"][value="all"]').checked = true;
  onPurposeChange();
  // ⌖ 坐标模式：最后再回填「坐标点击」与坐标（必须在 onOpTypeChange 之后，否则参数会被默认值清掉）
  if (state.coordMode && state.coordPoint) {
    $('el-op-type').value = 'tap';
    $('el-op-param').value = state.coordPoint[0] + ', ' + state.coordPoint[1];
    $('el-op-comment').value = '点击坐标(' + state.coordPoint[0] + ', ' + state.coordPoint[1] + ')';
    paramAuto = false;   // 用户选的是具体坐标，不让自动预填逻辑覆盖
  }
  fillCaseHead(); syncOpCards(); applyOpMutual();   // 弹窗改版：锚点卡/状态条回显 + 图标卡高亮与互斥复位
  $('modal-mask').style.display = 'flex';
}
/* ---- 新建文件输入（元素文件 / 用例文件）：选「➕ 新建…」时显示 ---- */
const NEW_FILE_OPT = '__new__';
function capFirst(s) { s = String(s || ''); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
function resetNewFileInputs() {
  const fw = $('el-file-new-wrap'), cw = $('el-case-new-wrap');
  if (fw) { fw.style.display = 'none'; $('el-file-new').value = ''; }
  if (cw) { cw.style.display = 'none'; $('el-case-new').value = ''; }
  const cnInput = $('el-case-cn'); if (cnInput) cnInput.value = '';
}
/* 当前是否新建用例（选择器值为 __new__ 或元素文件为 __new__） */
function isNewCase() { return $('el-case-file').value === NEW_FILE_OPT; }
function isNewElementFile() { return $('el-file').value === NEW_FILE_OPT; }
/* 新用例基础名（test_ 后面的部分）：非法字符过滤；同时派生元素文件名 */
function newCaseBase() { return ($('el-case-new').value || '').trim().replace(/[^A-Za-z0-9_]/g, '_'); }
function newElementFileName() {
  const b = newCaseBase();
  return b ? b + 'Elements.py' : '';
}
function newCaseFileName() {
  const b = newCaseBase();
  return b ? 'test_' + b + '.py' : '';
}
/* 用途（①仅元素 / ②+用例 / ③+操作 三件套）：决定流程走到哪一栏 */
function purposeValue() {
  const r = document.querySelector('input[name="el-purpose"]:checked');
  return r ? r.value : 'only';
}
function setElLinkNote(msg) {
  const el = $('el-link-note');
  if (el) { el.textContent = msg || ''; el.style.display = msg ? '' : 'none'; }
}
/* ---- 目标方法已有步骤 + 插入位置（②栏） ---- */
function currentSteps() {
  const f = $('el-case-file').value;
  const method = $('el-case-method').value;
  if (!f || !method) return [];
  const info = (state.caseFiles || []).find(c => c.file === f && (c.method_steps || {})[method]);
  return info ? (info.method_steps[method] || []) : [];
}
function insertPos() {
  if ($('el-insert-pos').value === 'front') return 'front';   // 第 1 步之前（首启弹窗类操作锁定）
  return parseInt($('el-insert-pos').value, 10) || 0;
}
function newStepNo() { const p = insertPos(); if (p === 'front') return 1; return p > 0 ? p + 1 : currentSteps().length + 1; }
function renderStepsList(steps) {
  const box = $('el-steps-list');
  if (!box) return;
  if (purposeValue() === 'only' || !$('el-case-method').value) { box.innerHTML = ''; box.style.display = 'none'; return; }
  box.style.display = '';
  const pos = insertPos();
  const newNo = pos === 'front' ? 1 : (pos > 0 ? pos + 1 : steps.length + 1);
  const step = { type: currentOpType(), element: $('el-name').value.trim() || '<元素名>', param: $('el-op-param').value.trim() };
  const desc = $('el-op-comment').value.trim() || genStepDesc(step);
  let html = steps.length
    ? '<div class="sl-title">当前用例已有 ' + steps.length + ' 步：</div>'
    : '<div class="sl-title">当前方法还没有步骤，这一步将是第 1 步：</div>';
  steps.forEach((s, i) => {
    html += '<div class="sl-row"><span class="sl-idx">' + (i + 1) + '</span><span>' + esc(s) + '</span></div>';
  });
  const posTxt = pos === 'front' ? '（放在第 1 步之前）' : (pos > 0 ? '（插到第 ' + pos + ' 步之后）' : '');
  html += '<div class="sl-marker">＋ 新步骤将插入到这里' + posTxt + '</div>';
  html += '<div class="sl-row new"><span class="sl-idx">' + newNo + '</span><span>➕ 本步：'
    + esc(desc) + '</span></div>';
  box.innerHTML = html;
}
/* 组装添加元素请求；checkDup=true 时后端先做重复检测（命中返回 duplicate 不落盘） */
async function saveElement(checkDup) {
  const waitSec = parseInt($('el-wait-sec').value, 10);
  const payload = {
    filename: $('el-file').value,
    name: $('el-name').value.trim(),
    locator_type: $('el-type').value,
    value: $('el-value').value.trim(),
    wait_type: $('el-wait').value,
    wait_seconds: (isNaN(waitSec) || waitSec < 1) ? '' : waitSec,  // 空 = 沿用框架默认 30
    cn_name: $('el-cn-name').value.trim(),                          // 元素中文名 → desc= 参数（元素管理显示名）
    check_dup: checkDup ? 1 : 0,
  };
  const r = await fetch('api/add_element', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    .then(r => r.json()).catch(() => null);
  if (!r) { showElResult('保存失败：服务异常', false); return null; }
  return r;
}
/* 用途单选：① 仅元素 → ②③栏熄灭；② 元素+用例 → ③栏只生成用例行；③ 三件套全联动 */
/* ⌖ 坐标模式：点截图选精确坐标（无障碍盲区场景，如自绘弹层的选项） */
function toggleCoordMode() {
  state.coordMode = !state.coordMode;
  if (!state.coordMode) state.coordPoint = null;
  $('btn-coord-mode').querySelector('.bt-tx').textContent = state.coordMode ? '坐标模式：开' : '坐标模式：关';
  $('btn-coord-mode').classList.toggle('on', state.coordMode);
  showToast(state.coordMode ? '开启成功' : '已关闭');
}

function onPurposeChange() {
  let p = purposeValue();
  const tb = $('tri-bar');
  if (tb) tb.style.display = (p === 'only' || p === 'popup') ? 'none' : '';   // 仅元素/弹窗规则库：无三件套落点
  // 特殊操作必须写用例（不写元素库），用途不允许停在「仅元素」
  if (p === 'only' && $('el-op-special').value) {
    document.querySelector('input[name="el-purpose"][value="all"]').checked = true;
    p = 'all';
  }
  const popup = p === 'popup';
  $('col-popup').style.display = popup ? '' : 'none';
  ['col-element', 'col-case', 'col-op'].forEach(id => {
    $(id).style.display = popup ? 'none' : '';
  });
  // 仅元素 = 只走①栏：②③熄灭禁点；①元素栏必须保持可交互（dim 带 pointer-events:none，不能加到①上）
  $('col-element').classList.remove('dim');
  $('col-case').classList.toggle('dim', !popup && p === 'only');
  $('col-op').classList.toggle('dim', !popup && p === 'only');
  if (popup) { ppPrefill(); loadPopupRules(); return; }
  if (p !== 'only') { onOpTypeChange(); onCaseFileChange(); }
  else { renderStepsList([]); updateOpNote(); }
}

/* ---- 用途③：登记随机弹窗（写 popupElements.py 规则库，不进普通元素库） ---- */
function ppPrefill() {
  // 关闭按钮 = 当前选中元素；规则名按元素名推荐（popup_xxx_close）
  const name = $('el-name').value.trim();
  if (!$('pp-value').value.trim()) {
    $('pp-type').value = $('el-type').value === 'XPATH' ? 'XPATH' : 'ID';
    $('pp-value').value = $('el-value').value.trim();
  }
  if (!$('pp-name').value.trim() && name) $('pp-name').value = 'popup_' + name + '_close';
}
async function loadPopupRules() {
  const box = $('pp-rules');
  try {
    const r = await (await fetch('api/popup_rules')).json();
    if (!r.ok) { box.innerHTML = '<div class="pp-empty">规则库读取失败</div>'; return; }
    renderPopupRules(r.rules || []);
  } catch (e) { box.innerHTML = '<div class="pp-empty">规则库读取失败：' + esc(String(e)) + '</div>'; }
}
function renderPopupRules(rules) {
  const box = $('pp-rules');
  if (!rules.length) { box.innerHTML = '<div class="pp-empty">还没有规则——选中弹窗关闭按钮后点「保存」即可登记第一条</div>'; return; }
  box.innerHTML = rules.map(r => {
    const loc = r.locator_type + ' · ' + truncate(r.locator_value, 34);
    const opt = [
      r.anchor ? '锚点 ' + truncate(r.anchor.value, 22) : '<em>无锚点（谨慎）</em>',
      '冷却 ' + r.cooldown + 's',
      r.activity ? '仅 ' + truncate(r.activity, 26) : null,
    ].filter(Boolean).join(' · ');
    return '<div class="pp-rule"><div class="pp-rule-main"><b>' + esc(r.name) + '</b>'
      + '<span>' + esc(loc) + '</span><span class="pp-opt">' + opt + '</span>'
      + (r.comment ? '<span class="pp-cmt">' + esc(truncate(r.comment, 30)) + '</span>' : '')
      + '</div><button class="pp-del" data-name="' + esc(r.name) + '" title="删除该规则">×</button></div>';
  }).join('');
}
$('pp-rules').addEventListener('click', async (e) => {
  const btn = e.target.closest('.pp-del');
  if (!btn) return;
  const name = btn.dataset.name;
  if (!confirm('删除弹窗规则「' + name + '」？执行时将不再自动关闭该弹窗。')) return;
  const r = await (await fetch('api/delete_popup_rule', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })).json();
  showToast(r.ok ? '🗑 规则「' + name + '」已删除' : '删除失败：' + r.msg);
  if (r.ok) renderPopupRules(r.rules || []);
  showPpResult(r.ok ? '规则 ' + name + ' 已删除' : (r.msg || '删除失败'), r.ok);
});
function showPpResult(msg, ok) {
  const box = $('pp-result');
  box.className = 'el-result ' + (ok ? 'ok' : 'err');
  box.textContent = msg;
}
async function savePopupRule(continueMode) {
  const name = $('pp-name').value.trim();
  const value = $('pp-value').value.trim();
  if (!name) { showPpResult('规则名不能为空', false); return; }
  if (!value) { showPpResult('关闭按钮定位值不能为空——请先在截图上点选弹窗的关闭按钮', false); return; }
  const payload = {
    name,
    locator_type: $('pp-type').value,
    locator_value: value,
    anchor_type: $('pp-anchor-type').value || '',
    anchor_value: $('pp-anchor-value').value.trim(),
    cooldown: parseInt($('pp-cooldown').value, 10) || 2,
    activity: $('pp-activity').value.trim(),
    comment: $('pp-comment').value.trim(),
  };
  if (payload.anchor_type && !payload.anchor_value) {
    showPpResult('选了锚点方式但没填锚点定位值——或补齐、或改回「不配锚点」', false);
    return;
  }
  let r;
  try {
    r = await (await fetch('api/add_popup_rule', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })).json();
  } catch (e) { showPpResult('保存失败：' + esc(String(e)), false); return; }
  if (!r.ok) { showPpResult(r.msg || '保存失败', false); return; }
  renderPopupRules(r.rules || []);
  // 保存后立即体检：实查当前页面该关闭按钮是否命中（登记 ≠ 有效，当场验证）
  let check = '';
  try {
    const c = await (await fetch('api/locate_check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locator_type: payload.locator_type, locator_value: payload.locator_value }),
    })).json();
    if (c.ok) check = c.found
      ? (c.count === 1 ? ' · ✅ 体检：唯一命中' : ' · ⚠️ 体检：命中 ' + c.count + ' 处')
      : ' · ❌ 体检：当前页面未命中（弹窗不在屏时属正常）';
  } catch (e) { /* 体检失败不拦截登记 */ }
  if (continueMode) {
    showPpResult('✅ 规则 ' + name + ' 已登记' + check + '。可继续登记下一条（在截图上点选下一个关闭按钮）', true);
  } else {
    $('modal-mask').style.display = 'none';
    showToast('🎯 弹窗规则「' + name + '」已登记' + check + ' · 用例执行时被动生效');
  }
}
/* 操作下拉分组渲染（见名知意：基本操作 / 断言 / 长流程·等待与分支） */
function opTypeOptions() {
  const groups = [];
  STEP_TYPES.forEach(t => {
    if (!t.group) return;
    let g = groups.find(x => x.name === t.group);
    if (!g) { g = { name: t.group, items: [] }; groups.push(g); }
    g.items.push(t);
  });
  return groups.map(g =>
    '<optgroup label="' + esc(g.name) + '">' +
    g.items.map(t => '<option value="' + t.v + '">' + esc(t.n) + '</option>').join('') +
    '</optgroup>').join('');
}

/* 操作提示区：用途联动提示 + 当前类型提示，两段共存（换行分隔） */
function updateOpNote() {
  const p = purposeValue();
  const t = stepTypeInfo(currentOpType());
  const purposeNote = p === 'all'
    ? '🔗 保存时将自动生成/更新页面操作方法（三件套一次完成）'
    : (p === 'case' ? '⚠ 不会生成页面方法——目标页面须已存在同名方法，否则执行报错' : '');
  const notes = {
    assert_toast: '💬 断言 Toast 只看屏幕提示文案，不依赖元素——上方元素字段仍会照常入库（可作为该步骤的定位参考），不会被弃用。',
    wait_element: '⏱ 适合「生成中/加载慢」的页面：一直等它出现，最长 N 秒；超时用例失败。和「固定等待」不同——元素一出现立刻继续，不干等。',
    assert_gone: '✅ 反向断言：元素必须「找不到」才算通过（验证弹窗已关闭、页面已跳走）。元素还在 = 用例失败并截图。',
    if_click: '🔀 分支处理（举例）：发布歌曲后偶发「今日首次发布歌曲」领金豆弹窗——'
      + '把【去领更多金豆】按钮存为元素，这里选「出现才点击」、操作参数填 3，'
      + '生成 page.click_get_bean_if_visible(3)。执行到这步最多等 3 秒找该弹窗：'
      + '出现了就点它，没出现就跳过继续，用例不会卡死。',
    hide_keyboard: '⌨ 输入完收起键盘再点下一步按钮（防止键盘遮挡）。无需选元素，直接保存即可。',
    sleep: '⏳ 固定睡 N 秒再继续（尽量少用，优先用「轮询等待出现」）。',
  };
  const typeNote = notes[t.v] || '';
  const note = $('op-note');
  note.style.whiteSpace = 'pre-line';
  note.textContent = [purposeNote, typeNote].filter(Boolean).join('\n');
}

/* 操作类型切换：参数框按需显隐 + 默认值联动 + 无需元素时元素栏弱化 + 刷新提示与预览
   paramAuto/opCommentAuto：当前值是否为自动预填（用户手输后置 false，不再被覆盖） */
var paramAuto = true;
var opCommentAuto = true;

function opElementLabel() {
  /* 步骤描述用的元素显示名：元素中文名优先，未填回退元素名称 */
  return $('el-cn-name').value.trim() || $('el-name').value.trim();
}

function followStepDesc() {
  /* 步骤描述实时拼接：操作类型 + 元素中文名（+ 参数）随输入即时刷新；手输过描述(opCommentAuto=false)则不覆盖 */
  if (opCommentAuto) {
    $('el-op-comment').value = autoStepComment(currentOpType(), opElementLabel(), $('el-op-param').value);
  }
}

function autoStepComment(type, elementLabel, param) {
  /* 按类型自动生成步骤描述：操作类型 + 「元素中文名」拼接，带参数的类型把参数也拼进去 */
  const t = (elementLabel || '').trim();
  const p = (param == null ? '' : String(param)).trim();
  switch (type) {
    case 'click': return t ? '点击「' + t + '」' : '';
    case 'input': return t ? ('在「' + t + '」输入' + (p ? '「' + p + '」' : '')) : '';
    case 'long_press': return t ? '长按「' + t + '」' : '';
    case 'tap': return '点击坐标' + (p ? '(' + p + ')' : '');
    case 'screenshot': return '截图' + (p ? '「' + p + '」' : '');
    case 'sleep': return '固定等待 ' + (p || '2') + ' 秒';
    case 'assert_visible': return t ? '断言「' + t + '」出现' : '';
    case 'assert_text': return t ? ('断言「' + t + '」文本为「' + p + '」') : '';
    case 'assert_toast': return '断言Toast' + (p ? '包含「' + p + '」' : '');
    case 'assert_gone': return t ? '断言「' + t + '」已消失' : '';
    case 'wait_element': return t ? '等待「' + t + '」出现' : '';
    case 'if_click': return t ? '若「' + t + '」出现则点击' : '';
    case 'custom': return '执行自定义代码';
    case 'hide_keyboard': return '收起键盘（键盘在才收，否则不动）';
    case 'deal_first_launch_dialogs': return '首次启动弹窗处理（无弹窗自动跳过）';
    default: return '';
  }
}

function onOpTypeChange() {
  const special = $('el-op-special').value;
  const t = stepTypeInfo(currentOpType());
  const paramWrap = $('el-op-param-wrap');
  paramWrap.style.display = t.param ? '' : 'none';
  $('el-op-param').placeholder = t.ph || '参数';
  // 每次切换操作类型：参数（若显示）与步骤描述的字段名都高亮 3 秒，提示「随类型变化」
  flashField(paramWrap);
  flashField($('el-op-comment').closest('label'));
  // 换类型时：参数为空或是上个类型的自动预填值 → 换成当前类型默认值（用户手输过则保留）
  if (t.param && (paramAuto || !$('el-op-param').value.trim())) {
    if (t.defv !== undefined) $('el-op-param').value = t.defv;
    paramAuto = true;
  }
  // 步骤描述是自动预填时跟随类型重生成（避免「等待」步骤还挂着「点击…」描述）
  followStepDesc();
  if (special) {
    // 特殊操作：与元素无关且不写元素库 → 元素栏整体禁用（dim = 禁点 + 弱化）
    $('col-element').classList.add('dim');
    $('col-element').classList.remove('soft');
  } else {
    // 常规类型（含 Toast 断言等不依赖元素的类型）：元素栏一律正常显示——
    // 置灰会让用户误以为已选的元素失效（用户实测反馈 v6.100）；「不依赖元素」的说明走 op-note 文字提示
    $('col-element').classList.remove('soft');
    $('col-element').classList.remove('dim');
  }
  updateOpNote();
}

/* 特殊操作下拉：选中 → 常规操作类型禁用、用途强制②（必须写用例）、元素栏禁用；
   取消（选「无」）→ 全部恢复。deal_first_launch_dialogs 的插入位置锁定由 onCaseFileChange 处理 */
function onSpecialOpChange() {
  const isSpecial = !!$('el-op-special').value;
  // 操作类型的禁用改由 applyOpMutual 视觉互斥承担（物理 disabled 会造成两侧都无法切回的死锁）
  if (isSpecial && purposeValue() !== 'all') {
    document.querySelector('input[name="el-purpose"][value="all"]').checked = true;
    onPurposeChange();
  }
  onOpTypeChange();
  onCaseFileChange();
}
/* ---- 代码预览：与后端 case_step_line 保持一致（所见即所得） ---- */
function escQ(s) { return String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }
function previewLine(step) {
  const t = step.type, el = step.element || '<元素名>', p = step.param || '';
  switch (t) {
    case 'click': return 'page.click_' + el + '()';
    case 'input': return 'page.input_' + el + "('" + escQ(p) + "')";
    case 'long_press': return 'page.long_press_' + el + '()';
    case 'assert_visible': return 'page.assert_' + el + '()';
    case 'assert_text': return 'page.assert_' + el + "_text('" + escQ(p) + "')";
    case 'assert_toast': return "page.assert_toast('" + escQ(p) + "')";
    case 'wait_element': {
      const n = parseInt(p, 10);
      return 'page.wait_' + el + (isNaN(n) ? '()' : '(' + n + ')');
    }
    case 'assert_gone': return 'page.assert_' + el + '_gone()';
    case 'if_click': {
      const n = parseInt(p, 10);
      return 'page.click_' + el + '_if_visible(' + (isNaN(n) ? '' : n) + ')';
    }
    case 'hide_keyboard': return 'page.dismiss_keyboard()';
    case 'deal_first_launch_dialogs': return 'page.deal_first_launch_dialogs()';
    case 'screenshot': return "page.wait_and_shot('" + escQ(p) + "')";
    case 'tap': {
      const parts = p.split(',').map(x => x.trim()).filter(Boolean);
      return parts.length >= 2 ? 'page.tap_xy(' + parts[0] + ', ' + parts[1] + ')'
        : 'page.tap_xy(' + (parts[0] || '0') + ')';
    }
    case 'sleep': {
      const n = parseFloat(p);
      return 'time.sleep(' + (isNaN(n) ? (p || '1') : n) + ')';
    }
    case 'custom': return p || 'page.xxx()';
    default: return '';
  }
}
/* 目标用例的页面文件（来自 /api/cases 的三件套归属信息） */
function targetPageInfo() {
  const f = $('el-case-file').value;
  const info = (state.caseFiles || []).find(c => c.file === f && c.page_file);
  return info || null;
}
/* ---- 两个实时预览：元素代码 / 页面方法代码（与后端生成规则保持一致） ---- */
/* 元素栏：将写入元素库的那一行 */
function elementLinePreview() {
  const name = $('el-name').value.trim() || '<元素名>';
  const val = $('el-value').value.trim();
  const sec = parseInt($('el-wait-sec').value, 10);
  const cn = $('el-cn-name').value.trim();
  let line = "self." + name + " = CreateElement.create(Locator_Type." + $('el-type').value
    + ", '" + escQ(val) + "', wait_type=Wait_By." + $('el-wait').value;
  if (!isNaN(sec) && sec >= 1) line += ", wait_seconds=" + sec;
  if (cn) line += ", desc='" + escQ(cn) + "'";
  line += ')';
  if (cn) line += '  # ' + cn;
  return line;
}
/* 操作栏：选③时将生成到页面文件的页面方法（镜像后端 page_method_code） */
function probeBodyLines(el, secondsVar) {
  return "probe = CreateElement.create(self._elements." + el + ".locator_type,\n"
    + "                             self._elements." + el + ".locator_value,\n"
    + "                             wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n"
    + "                             wait_seconds=" + secondsVar + ")";
}
/* ---- 目标用例文件 + 方法（两级联动；③ 时元素文件自动对齐页面引用的元素文件） ---- */
async function loadCaseFiles() {
  const r = await fetch('api/cases').then(r => r.json()).catch(() => null);
  if (!r || !r.ok) return;
  state.caseFiles = r.case_info || [];
  const sel = $('el-case-file');
  const cur = sel.value;
  /* 用例文件下拉：有中文名映射的显示「中文名（文件名）」（与平台选择用例同步） */
  const cnMap = {};
  (state.caseFiles || []).forEach(c => { if (c.cn_name && !cnMap[c.file]) cnMap[c.file] = c.cn_name; });
  const files = [];
  (state.caseFiles || []).forEach(c => { if (files.indexOf(c.file) < 0) files.push(c.file); });
  // 「➕ 新建…」永远在最后：选择后显示 test_ 前缀锁定输入行（保存走「保存测试用例包」）
  sel.innerHTML = files.map(f => '<option value="' + esc(f) + '">' +
    esc(cnMap[f] ? cnMap[f] + '（' + f + '）' : f) + '</option>').join('')
    + '<option value="' + NEW_FILE_OPT + '">➕ 新建用例文件…</option>';
  // 预选优先级：用户处于「新建」模式（含临时用例会话）> 用户已显式选中的有效用例 > 第一个
  if (cur === NEW_FILE_OPT) sel.value = NEW_FILE_OPT;
  else if (cur && files.indexOf(cur) >= 0) sel.value = cur;
  else if (files.length) sel.value = files[0];
  onCaseFileChange();
}
function updatePkgTrio() {
  /* 新建用例模式：三个文件名全部由用例名派生并锁死，实时回显让锁死关系一眼可见 */
  const el = $('pkg-trio');
  if (!el) return;
  if (!isNewCase()) { el.textContent = ''; return; }
  if (!pkgBase()) { el.textContent = '输入用例名后，用例 / 页面 / 元素 三个文件名自动派生并锁死'; return; }
  el.textContent = '将生成并锁死：test_' + pkgBase() + '.py · ' + pkgPageFileName() + ' · ' + pkgElementFileName();
}

function syncElFileNote() {
  /* 手动改「写入元素文件」时如实提示：与页面引用的元素文件不一致 → 保存时会自动同步过去（同名覆盖），
     不再留着上次「已自动对齐」的过期提示让人生疑 */
  const f = $('el-case-file').value;
  const info = (state.caseFiles || []).filter(c => c.file === f).find(c => c.page_file);
  if (purposeValue() !== 'all' || isNewElementFile() || !info || !info.elements_file) return;
  if ($('el-file').value !== info.elements_file) {
    setElLinkNote('⚠ 「写入元素文件」(' + $('el-file').value + ') 与页面 ' + info.page_file + ' 引用的 ' +
                  info.elements_file + ' 不一致——保存时会自动把元素同步到 ' + info.elements_file + '（同名覆盖，不影响保存）');
  }
}

function onCaseFileChange() {
  // 新建用例：切换到「新建输入模式」——方法/插入位置无意义，页面/元素文件自动派生
  const newCase = isNewCase();
  $('el-case-new-wrap').style.display = newCase ? '' : 'none';
  $('el-case-method').disabled = newCase;
  $('el-insert-pos').disabled = newCase;
  $('el-page-file').value = newCase ? (newCaseBase() ? capFirst(newCaseBase()) + 'Page.py（随用例包新建）' : '（输入用例名后自动派生）')
                                    : '';
  updatePkgTrio();
  fillCaseHead();
  if (newCase) { renderStepsList([]); return; }
  const f = $('el-case-file').value;
  const infos = (state.caseFiles || []).filter(c => c.file === f);
  const methods = [];
  infos.forEach(c => (c.methods || []).forEach(m => { if (methods.indexOf(m) < 0) methods.push(m); }));
  const usable = methods.filter(m => m !== 'setup_class' && m !== 'teardown_class');
  const mSel = $('el-case-method');
  mSel.innerHTML = usable.length
    ? usable.map(m => '<option value="' + esc(m) + '">' + esc(m) + '</option>').join('')
    : '<option value="">（该文件暂无可用方法）</option>';
  // 已有步骤 + 插入位置（漏步骤可插中间；步骤来自方法体的 # 注释，后端 method_steps 解析）
  const selMethod = mSel.value;
  const stepsInfo = infos.find(c => (c.method_steps || {})[selMethod]);
  const steps = (stepsInfo && stepsInfo.method_steps[selMethod]) || [];
  const posSel = $('el-insert-pos');
  const curPos = posSel.value;
  if (currentOpType() === 'deal_first_launch_dialogs') {
    // 首启弹窗只能出现在所有操作之前：锁定「最前」，不允许选其他插入位置
    posSel.innerHTML = '<option value="front">最前（放在第 1 步之前）</option>';
    posSel.value = 'front';
    posSel.disabled = true;
  } else {
    posSel.disabled = false;
    let posOpts = '<option value="0">末尾（成为第 ' + (steps.length + 1) + ' 步）</option>';
    for (let i = 1; i <= steps.length; i++) {
      posOpts += '<option value="' + i + '">第 ' + i + ' 步之后 · ' + esc(String(steps[i - 1]).slice(0, 12)) + '</option>';
    }
    posSel.innerHTML = posOpts;
    posSel.value = (curPos !== '' && curPos !== null && parseInt(curPos, 10) <= steps.length) ? curPos : '0';
  }
  renderStepsList(steps);
  // 三件套联动：写入元素文件 ← 目标用例页面实际引用的元素文件（必须一致）
  // 写入页面文件 = 目标用例的 self.page 所在文件（只读展示，跟随用例）
  const p = purposeValue();
  const info = infos.find(c => c.page_file);
  const amb = infos.find(c => (c.page_ambiguous || []).length);
  $('el-page-file').value = info ? info.page_file : '';
  if (amb) {
    setElLinkNote('⚠ 页面类 ' + amb.page_class + ' 在多个文件里重名：' + amb.page_ambiguous.join('、')
                  + '——归属不唯一，已禁止写入页面方法，请先改名或删除重名文件');
  } else if (p !== 'only' && !info) {
    setElLinkNote('⚠ 该用例没有页面对象（self.page），③ 无法生成操作——请换有页面对象的用例，或先补页面文件后重试');
  } else if (p === 'all' && info && info.elements_file) {
    if ($('el-file').value !== info.elements_file) {
      const sel = $('el-file');
      // 下拉里没有该文件时 set value 会静默失效（提示却说已对齐）——缺选项就先补上
      if (!Array.from(sel.options).some(o => o.value === info.elements_file)) {
        sel.add(new Option(info.elements_file, info.elements_file));
      }
      sel.value = info.elements_file;
      setElLinkNote('🔗 页面 ' + info.page_file + ' 引用元素文件 ' + info.elements_file + '，「写入元素文件」已自动对齐');
    } else {
      setElLinkNote('🔗 三件套去向：页面 ' + info.page_file + ' ← 元素文件 ' + info.elements_file);
    }
  } else if (info) {
    setElLinkNote('该用例的页面: ' + info.page_file + (info.elements_file ? '（元素: ' + info.elements_file + '）' : ''));
  } else {
    setElLinkNote('');
  }
}
/* 保存：按「用途」单选分流 —— ① 仅保存到元素库 / ② 保存并追加到目标用例方法 */
/* 保存：按「保存到哪一步」分流 ① 仅元素 / ② +用例 / ③ +操作；
 * continueMode=true（保存并继续）= 保存后回到定位器，开启连续添加（点下一个元素自动弹本窗） */
/* ---------- 保存测试用例包（新建用例文件场景）：一次生成三件套 ----------
   用例/页面/元素三个完整文件由前端按框架风格组装，后端 /api/save_case_package
   与平台同进程直调用例管理入库（语法校验、备份、登记一条龙）；
   局域网访问者可选「下载用例包 zip」交由平台「用例管理 → 上传用例包」入库。 */
function capCamel(s) {  // login_flow -> LoginFlow（类名用）
  return String(s || '').split('_').filter(Boolean).map(capFirst).join('');
}
function pkgBase() { return newCaseBase(); }
function pkgElementFileName() {
  const raw = ($('el-file-new').value || '').trim().replace(/\.py$/i, '');  // 先剥 .py（过滤会把 . 变 _）
  const v = raw.replace(/[^A-Za-z0-9_]/g, '_');
  const b = pkgBase();
  const stem = v || (b ? b + 'Elements' : '');
  if (!stem) return '';
  // 元素文件名必须以 Elements 结尾（页面/用例生成逻辑依赖该后缀判定归属）：
  // 用户漏写或写成单数 Element 时自动规范化，.py 后缀同样自动补
  const norm = stem.replace(/Elements?$/,'') + 'Elements';
  return norm + '.py';
}
function pkgElementClassName() { const f = pkgElementFileName(); return f ? capFirst(f.replace('.py', '')) : ''; }
function pkgPageFileName() { const b = pkgBase(); return b ? capFirst(b) + 'Page.py' : ''; }
function pkgPageClassName() { const f = pkgPageFileName(); return f ? capFirst(f.replace('.py', '')) : ''; }
function pkgCaseFileName() { const b = pkgBase(); return b ? 'test_' + b + '.py' : ''; }
function pkgStepComment() { return $('el-op-comment').value.trim() || genStepDesc(currentStepObj()); }
function currentStepObj() {
  return { type: currentOpType(), element: $('el-name').value.trim() || '<元素名>', param: $('el-op-param').value.trim() };
}
/* 与后端 page_method_code 同规则的页面方法块（用例包生成用） */
function pkgMethodBlock(step) {
  const t = step.type, el = step.element || '<元素名>';
  const doc = $('el-op-comment').value.trim() || genStepDesc(step);
  const p = (step.param || '').trim();
  let sig = '', body = '';
  if (t === 'click') sig = 'click_' + el + '(self)';
  else if (t === 'input') { sig = 'input_' + el + '(self, text)'; body = 'self.appOperator.sendText(self._elements.' + el + ', text)'; }
  else if (t === 'long_press') { sig = 'long_press_' + el + '(self)'; body = 'self.appOperator.touch_long_press(self._elements.' + el + ', duration_sconds=2)'; }
  else if (t === 'assert_visible') { sig = 'assert_' + el + '(self)'; body = 'self.appOperator.getElement(self._elements.' + el + ')'; }
  else if (t === 'assert_text') { sig = 'assert_' + el + '_text(self, expected)'; body = "assert self.appOperator.getText(self._elements." + el + ") == expected, '" + escQ(doc) + "'"; }
  else if (t === 'assert_toast') { sig = 'assert_toast(self, text)'; body = "assert self.appOperator.is_toast_visible(text, wait_seconds=5), '" + escQ(doc) + "'"; }
  else if (t === 'wait_element') {
    const n = parseInt(p, 10); sig = 'wait_' + el + '(self, timeout_seconds=' + (isNaN(n) ? 60 : n) + ')';
    body = probeBodyLines(el, 'timeout_seconds') + '\nself.appOperator.getElement(probe)';
  }
  else if (t === 'assert_gone') {
    sig = 'assert_' + el + '_gone(self, wait_seconds=2)';
    body = probeBodyLines(el, 'wait_seconds') + '\ngone = True\ntry:\n    self.appOperator.getElement(probe)\n    gone = False\nexcept Exception:\n    pass\n'
      + "self.appOperator.assert_true_with_shot('" + escQ(doc) + "', gone,\n"
      + "                                   '等待' + str(wait_seconds) + '秒内元素仍可见')";
  }
  else if (t === 'if_click') {
    const n = parseInt(p, 10); sig = 'click_' + el + '_if_visible(self, timeout_seconds=' + (isNaN(n) ? 3 : n) + ')';
    body = probeBodyLines(el, 'timeout_seconds') + '\ntry:\n    self.appOperator.click(self.appOperator.getElement(probe))\nexcept Exception:\n    pass';
  }
  else if (t === 'hide_keyboard') {
    sig = 'dismiss_keyboard(self)';
    body = 'try:\n    if self.appOperator.is_keyboard_shown():\n        self.appOperator.hide_keyboard()\nexcept Exception:\n    self.appOperator.press_keycode(4)\nimport time\ntime.sleep(1)';
  }
  else if (t === 'deal_first_launch_dialogs') {
    /* 首次启动弹窗处理：与后端 page_method_code 同一标准实现（探针自包含，不依赖元素文件） */
    sig = 'deal_first_launch_dialogs(self)';
    body = 'import time\n'
      + 'for _lval, _desc in (\n'
      + '        ("//*[@text=\'同意并继续\']", \'隐私协议弹窗\'),\n'
      + '        ("//*[@text=\'允许\']", \'系统权限弹窗\'),\n'
      + '):\n'
      + '    probe = CreateElement.create(Locator_Type.XPATH, _lval,\n'
      + '                                 wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n'
      + '                                 wait_seconds=2)\n'
      + '    try:\n'
      + '        self.appOperator.click(self.appOperator.getElement(probe))\n'
      + '        time.sleep(1)  # 等弹窗收尾动画，避免点击落到下层页面\n'
      + '    except Exception:\n'
      + '        pass  # 该弹窗未出现，跳过';
  }
  else if (t === 'screenshot') { sig = 'wait_and_shot(self, tag)'; body = 'import time\ntime.sleep(1)\nself.appOperator.get_screenshot(tag)'; }
  else if (t === 'tap') { sig = 'tap_xy(self, x, y)'; body = 'self.appOperator.tap(x, y)'; }
  if (t === 'click') body = 'self.appOperator.click(self._elements.' + el + ')';
  return '    def ' + sig + ':\n        """' + doc + '"""\n        ' + body.replace(/\n/g, '\n        ');
}
function pkgFiles() {
  const elemName = $('el-name').value.trim();
  const elemFile = pkgElementFileName();
  const elemClass = pkgElementClassName();
  const pageFile = pkgPageFileName();
  const pageClass = pkgPageClassName();
  const base = pkgBase();
  const elemLine = '        ' + elementLinePreview();
  const methodBlock = pkgMethodBlock(currentStepObj());
  const stepComment = pkgStepComment();
  const elemPy = '# -*- coding: utf-8 -*-\n'
    + '# 本文件由 GUI 元素定位器自动生成/维护（用例包：' + base + '）\n'
    + 'from page_objects.createElement import CreateElement\n'
    + 'from page_objects.app_ui.locator_type import Locator_Type\n'
    + 'from page_objects.app_ui.wait_type import Wait_Type as Wait_By\n'
    + '\n\n'
    + 'class ' + elemClass + ':\n'
    + '    def __init__(self):\n'
    + elemLine + '\n';
  const pagePy = '# -*- coding: utf-8 -*-\n'
    + '# 页面对象（用例包：' + base + '）\n'
    + 'from page_objects.app_ui.android.demoProject.elements.' + elemFile.replace('.py', '') + ' import ' + elemClass + '\n'
    + '\n\n'
    + 'class ' + pageClass + ':\n'
    + '\n'
    + '    def __init__(self, appOperator):\n'
    + '        self.appOperator = appOperator\n'
    + '        self._elements = ' + elemClass + '()\n'
    + '\n'
    + methodBlock + '\n';
  const cnTitle = ($('el-case-cn').value || '').trim();
  const casePy = '# -*- coding: utf-8 -*-\n'
    + (cnTitle ? '# 用例中文名：' + cnTitle + '\n' : '')
    + '# 用例包 ' + base + ' · ' + stepComment + '\n'
    + '# 流程：\n'
    + '# 1. 拉起快歌主页面\n'
    + '# 2. ' + stepComment + '\n'
    + 'import time\n'
    + 'import allure\n'
    + 'from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client\n'
    + 'from page_objects.app_ui.android.demoProject.pages.' + pageFile.replace('.py', '') + ' import ' + pageClass + '\n'
    + '\n\n'
    + "@allure.parent_suite('快歌APP自动化')\n"
    + "@allure.suite('" + base + "')\n"
    + 'class Test' + capCamel(base) + ':\n'
    + '\n'
    + '    def setup_class(self):\n'
    + '        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App\n'
    + '        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)\n'
    + '        self.appOperator = self.demoProjectClient.appOperator\n'
    + "        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')\n"
    + '        time.sleep(3)\n'
    + '        self.page = ' + pageClass + '(self.appOperator)\n'
    + '\n'
    + "    @allure.title('" + stepComment + "')\n"
    + '    def test_' + base + '(self):\n'
    + '        """' + stepComment + '"""\n'
    + '        page = self.page\n'
    + '\n'
    + '        # 1. ' + stepComment + '\n'
    + '        ' + previewLine(currentStepObj()) + '\n'
    + '\n'
    + '    def teardown_class(self):\n'
    + '        self.appOperator.close_app()\n';
  return [
    { dir: 'cases/app_ui/android/demoProject', name: pkgCaseFileName(), content: casePy },
    { dir: 'page_objects/app_ui/android/demoProject/pages', name: pageFile, content: pagePy },
    { dir: 'page_objects/app_ui/android/demoProject/elements', name: elemFile, content: elemPy },
  ];
}
async function onSaveElement(continueMode) {
  const purpose = purposeValue();
  if (!purpose) return;
  // 用途③：登记随机弹窗——写规则库，与元素库/用例三件套完全无关
  if (purpose === 'popup') { await savePopupRule(continueMode); return; }
  const special = $('el-op-special').value;   // 特殊操作：不碰元素库，只写用例
  const name = special ? '' : $('el-name').value.trim();
  if (purpose !== 'only') {
    // 防误操作：「写入元素文件」与「目标用例文件」的新建状态必须同步——
    // 一起新建（三件套随首次保存入库）或都选已有文件；不同步时 toast 提示并阻止保存
    //（特殊操作不碰元素库，不受此约束）
    if (!special && isNewCase() !== isNewElementFile()) {
      showToast('⚠️ 「写入元素文件」与「目标用例文件」需同步：要么都用「➕ 新建」，要么都选已有文件');
      return;
    }
    // 新建用例（填写了自定义文件名）：首次「保存并继续/保存」即三件套（元素+用例+页面，
    // 已含当前步骤）直接入库——与平台「保存并继续」同语义；之后弹窗回显文件信息，继续录走 add_code 追加
    if (isNewCase()) {
      if (!pkgBase()) { showElResult('请先输入新用例名（test_ 后面的部分）', false); return; }
      if (!special && !name) { showElResult('元素名称不能为空', false); return; }
      if (state.tempCase && state.tempCase.base !== pkgBase()) {
        if (!confirm('上次录制会话是「' + state.tempCase.base + '」。换用例名将切换会话，继续？')) return;
      }
      const tc = state.tempCase = { base: pkgBase() };
      const r = await fetch('api/save_case_package', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package: tc.base, files: pkgFiles(), uploader: special ? 'locator' : name }),
      }).then(x => x.json()).catch(() => null);
      if (!r || !r.ok) { showElResult('三件套入库失败：' + ((r && r.msg) || '服务异常'), false); return; }
      // 本步已随三件套写入 → 切回已有文件模式（回显用例/页面/元素文件），后续步骤走 add_code 追加
      await loadCaseFiles();
      $('el-case-file').value = pkgCaseFileName();
      onCaseFileChange();
      $('modal-mask').style.display = 'none';
      showToast(continueMode ? '请继续添加用例' : '保存成功');
      return;
    }
    // 都选已有文件 → 继续走「元素入库 + 追加用例行」（下方既有流程）
  }
  // 选②：前置校验用例栏（保存元素前就拦住，避免元素入库了代码却追加不了）
  let caseFile = '', methodName = '';
  if (purpose !== 'only') {
    caseFile = $('el-case-file').value;
    methodName = $('el-case-method').value;
    if (!(state.caseFiles || []).some(c => c.file === caseFile)) {
      showElResult('请选择目标用例文件（或选「➕ 新建用例文件…」一次生成三件套）', false); return;
    }
    if (!methodName) { showElResult('请选择页面操作', false); return; }
  }
  // 同名（同文件）覆盖确认：防止误覆盖已有元素（特殊操作不碰元素库，整段跳过）
  const fname = $('el-file').value;
  if (!special && name && (state.elementsAll[fname] || []).indexOf(name) >= 0) {
    if (!await uiConfirm('元素库文件 ' + fname + ' 里已有同名元素「' + name + '」，保存将覆盖更新原定义。\n\n' +
      '点「确定」= 覆盖更新\n点「取消」= 不保存')) return;
  }
  // 按需求：添加测试用例不判断重复——同名直接覆盖、同定位直接新增，元素照常入库
  let r = special ? { ok: true, msg: '' } : await saveElement(false);
  if (!r) return;
  if (!r.ok) { showElResult(r.msg || '元素保存失败', false); return; }
  let savedName = special ? '' : name;

  const finishContinue = () => {
    $('modal-mask').style.display = 'none';
    // 不自动弹窗：用户自由点选元素查看，点「添加测试用例」再录下一步（用例/方法预选已保持）
    showToast('保存成功，请继续添加用例');
    // 下拉刷新延后到 toast 显示之后，避免与蒙层关闭、toast 出现同帧挤占渲染
    setTimeout(() => { loadPages(); loadLibraryFiles(); loadCaseFiles(); }, 260);
  };

  if (purpose === 'only') {
    if (r.content) $('el-content').textContent = r.content;
    showElResult(r.msg + ' —— 已保存到元素库', true);
    if (continueMode) finishContinue();
    else { showToast('保存成功'); setTimeout(() => { $('modal-mask').style.display = 'none'; }, 600); }
    return;
  }
  // purpose ②/③：追加一步代码到目标用例方法体末尾（③ 同时生成/更新页面方法）
  const step = {
    type: special || $('el-op-type').value,   // 特殊操作优先（不依赖元素）
    element: savedName,
    element_file: special ? '' : fname,       // 元素刚保存进的文件（元素不在页面引用文件时后端优先从这复制）
    param: $('el-op-param').value.trim(),
    desc: '',
    comment: $('el-op-comment').value.trim(),        // 操作备注 → 页面方法 docstring
    case_comment: '',   // 用例备注字段已删：留空由后端自动生成步骤描述
  };
  const res = $('el-result');
  res.className = 'el-result'; res.textContent = purpose === 'all'
    ? '元素已保存，正在追加用例代码 + 生成页面操作…'
    : '元素已保存，正在追加用例代码…';
  const cr = await fetch('api/add_code', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_file: caseFile, method_name: methodName, step: step,
                           gen_page_method: purpose === 'all' ? 1 : 0,
                           insert_after_step: insertPos() }),
  }).then(r => r.json()).catch(() => null);
  if (!cr || !cr.ok) {
    showElResult((cr && cr.msg ? cr.msg : '追加用例代码失败：服务异常') + '（元素已保存到元素库）', false);
    return;
  }
  res.className = 'el-result ok';
  pushUndoRecord(cr);
  res.textContent = r.msg + '；' + cr.msg + '（页面方法已写入目标页面文件）';
  // 展示追加后的目标方法片段 + ③ 生成的页面方法片段（方便确认写入位置）
  let snippets = [];
  if (cr.content) {
    const lines = cr.content.split('\n');
    const idx = lines.findIndex(l => l.indexOf('def ' + methodName) >= 0);
    if (idx >= 0) {
      let end = lines.length;
      for (let i = idx + 1; i < lines.length; i++) {
        if (lines[i] && !/^\s/.test(lines[i])) { end = i; break; }
      }
      snippets.push('# ' + caseFile + ' :: ' + methodName + '\n' + lines.slice(Math.max(0, idx - 2), end).join('\n'));
    }
  }
  if (purpose === 'all' && cr.page_content && cr.page_method) {
    const plines = cr.page_content.split('\n');
    const pidx = plines.findIndex(l => l.indexOf('def ' + cr.page_method) >= 0);
    if (pidx >= 0) {
      let pend = plines.length;
      for (let i = pidx + 1; i < plines.length; i++) {
        // 方法体结束：下一个类级 class 或同级 def
        if (/^(class |    def )/.test(plines[i])) { pend = i; break; }
      }
      snippets.push('\n# ' + cr.page_file + ' :: ' + cr.page_method + '\n' + plines.slice(pidx, pend).join('\n').replace(/^\n+/, ''));
    }
  }
  if (snippets.length) $('el-content').textContent = snippets.join('\n\n');
  // 刷新页面/元素/用例列表（可能有新元素、新页面对象/新方法）；保存并继续 → 连续添加模式
  if (continueMode) { finishContinue(); return; }
  $('modal-mask').style.display = 'none';   // 保存 = 完成本条录入，与「保存并继续」一致关闭弹窗
  showToast('保存成功');
  // 下拉刷新延后到 toast 入场动画（220ms）结束后，避免与蒙层关闭、toast 入场同帧挤占渲染
  setTimeout(() => { loadPages(); loadLibraryFiles(); loadCaseFiles(); }, 260);
}

function showElResult(msg, ok) {
  const box = $('el-result');
  box.className = 'el-result ' + (ok ? 'ok' : 'err');
  box.textContent = msg;
}

/* ---------- 右侧教学 ---------- */
var tutSearchTimer = null;
function onTutSearch(e) {
  clearTimeout(tutSearchTimer);
  tutSearchTimer = setTimeout(() => renderTutorials(e.target.value.trim()), 250);
}
async function renderTutorials(q) {
  tutExpandAll = !!(q && q.trim());
  const url = 'api/tutorials' + (q ? '?q=' + encodeURIComponent(q) : '');
  const r = await fetch(url).then(r => r.json()).catch(() => null);
  if (!r || !r.ok) return;
  const box = $('tutorials');
  box.innerHTML = '';
  const items = r.tutorials;
  if (!items.length) { box.innerHTML = '<div class="empty">没有匹配的教程，换个词试试<br>如：点击 / 滑动 / toast / 断言 / 输入</div>'; return; }
  items.forEach(item => box.appendChild(buildTutItem(item)));
}
function buildTutItem(item) {
  const isCat = item.length === 2 && Array.isArray(item[1]);
  if (isCat) {
    const wrap = document.createElement('div');
    const head = document.createElement('div');
    head.className = 'cat-head';
    const arrow = document.createElement('span');
    arrow.textContent = '▾';
    head.innerHTML = '<span>📁 ' + esc(item[0]) + '</span>';
    head.appendChild(arrow);
    const body = document.createElement('div');
    (item[1] || []).forEach(x => body.appendChild(buildTutItem(x)));
    let open = tutExpandAll;  // 默认收起；搜索命中时展开
    if (!open) body.style.display = 'none';
    arrow.textContent = open ? '▾' : '▸';
    head.appendChild(arrow);
    head.addEventListener('click', () => {
      open = !open;
      body.style.display = open ? '' : 'none';
      arrow.textContent = open ? '▾' : '▸';
    });
    wrap.appendChild(head); wrap.appendChild(body);
    return wrap;
  }
  const [title, sig, desc, code] = item;
  const leaf = document.createElement('div');
  leaf.className = 'tut-leaf';
  leaf.innerHTML = '<div class="tut-title"><span>' + esc(title) + '</span></div>'
    + (sig ? '<div class="tut-sig">' + esc(sig) + '</div>' : '')
    + (desc ? '<div class="tut-desc">' + esc(desc) + '</div>' : '');
  if (code) {
    const c = document.createElement('div');
    c.className = 'tut-code';
    const pre = document.createElement('span');
    pre.textContent = code;
    const btn = document.createElement('button');
    btn.className = 'copy-btn'; btn.textContent = '复制';
    btn.addEventListener('click', () => copyText(code, btn));
    c.appendChild(pre); c.appendChild(btn);
    leaf.appendChild(c);
  }
  return leaf;
}

document.addEventListener('DOMContentLoaded', init);
/* 日间/夜间模式切换按钮由平台的 /static/theme.js 统一注入（两端共用存储键、全局同步）；
   本文件不再创建按钮——重复创建会叠出空按钮（同 id），表现为"图标消失"。 */

/* ================= 批量采集全部元素（方案第一阶段） =================
   采集 → 结果弹层（勾选/改名）→ 批量写进选定的元素文件（复用现有元素库格式），
   平台「元素管理」读同一目录，保存后立即可见。 */
let _collectItems = [];   // 弹层当前展示的采集项（含勾选状态）

function collectTargetFile() {
  const sel = $('collect-file'), nw = $('collect-file-new');
  if (sel.value === '__new__') {
    let f = (nw.value || '').trim().replace(/\.py$/i, '');
    if (!f) return '';
    f = /Elements$/i.test(f) ? f : f + 'Elements';
    return f + '.py';
  }
  return sel.value;
}

function collectUpdateCount() {
  $('collect-pick-count').textContent = _collectItems.filter(i => i._pick).length;
}

function renderCollectItems() {
  const box = $('collect-list');
  box.innerHTML = _collectItems.map((it, i) => {
    return '<div class="collect-row">' +
      '<input type="checkbox" data-ci="' + i + '"' + (it._pick ? ' checked' : '') + '>' +
      '<input type="text" class="ci-name" data-ni="' + i + '" value="' + esc(it.name) + '" title="元素引用名（可改）">' +
      '<input type="text" class="ci-cn" data-cni="' + i + '" value="' + esc(it.cn_name) + '" placeholder="中文名（可改）" title="元素管理/报告显示的中文名（可改）">' +
      '<span class="ci-loc"><b>' + esc(it.locator_type) + '</b> ' + esc(truncate(it.value, 42)) + '</span>' +
      '<span class="ci-cand" title="' + esc(it.candidates.map(c => c.kind + ': ' + c.value).join('\n')) + '">' + it.candidates.length + ' 个候选</span>' +
      '</div>';
  }).join('') || '<div class="empty">本页没有可采集的有效元素</div>';
  box.querySelectorAll('input[type=checkbox][data-ci]').forEach(cb => {
    cb.addEventListener('change', () => { _collectItems[+cb.dataset.ci]._pick = cb.checked; collectUpdateCount(); });
  });
  box.querySelectorAll('.ci-name').forEach(inp => {
    inp.addEventListener('change', () => { _collectItems[+inp.dataset.ni].name = inp.value.trim(); });
  });
  box.querySelectorAll('.ci-cn').forEach(inp => {
    inp.addEventListener('change', () => { _collectItems[+inp.dataset.cni].cn_name = inp.value.trim(); });
  });
  collectUpdateCount();
}

async function openCollectModal(result) {
  _collectItems = (result.items || []).map(it => Object.assign({ _pick: true }, it));
  const s = result.stats || {};
  $('collect-stats').textContent = '原始节点 ' + s.raw + ' · 无效过滤 ' + s.filtered +
    ' · 重复 ' + s.dup + ' · 最终候选 ' + s.final + (result.archive ? ' · 原始树已存档 ' + result.archive : '');
  await loadLibraryFiles();   // 拿最新元素文件清单
  const files = state.eleFiles || [];
  $('collect-file').innerHTML = files.map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('')
    + '<option value="__new__">➕ 新建元素文件…</option>';
  $('collect-file-new-wrap').style.display = 'none';
  renderCollectItems();
  $('collect-filtered').innerHTML = (result.filtered || [])
    .map(f => '<div class="cf-row">' + esc(f.name) + ' <span class="muted">' + esc(f.reason) + '</span></div>').join('')
    || '<div class="muted">无</div>';
  $('collect-mask').style.display = '';
}

async function startCollect() {
  const btn = $('btn-collect');
  btn.disabled = true; btn.textContent = '⏳ 采集中…';
  try {
    const r = await fetch('api/collect_all', { method: 'POST' }).then(r => r.json()).catch(() => null);
    if (!r || !r.ok) { showToast((r && r.msg) || '采集失败'); return; }
    showToast('采集完成：候选 ' + (r.stats || {}).final + ' 个');
    await openCollectModal(r);
  } finally {
    btn.disabled = false; btn.textContent = '📦 采集全部元素';
  }
}

async function saveCollect() {
  const file = collectTargetFile();
  if (!file) return showToast('请选择或填写目标元素文件');
  const items = _collectItems.filter(i => i._pick)
    .map(i => ({ name: i.name, locator_type: i.locator_type, value: i.value,
                 cn_name: i.cn_name, comment: i.comment }));
  if (!items.length) return showToast('未勾选任何元素');
  const btn = $('btn-collect-save');
  btn.disabled = true;
  try {
    const r = await fetch('api/collect_save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file, items })
    }).then(r => r.json()).catch(() => null);
    if (!r || !r.ok) { showToast((r && r.msg) || '保存失败'); return; }
    const skips = (r.skipped || []).map(s => s.name + '（' + s.reason + '）');
    showToast('已新增 ' + r.added + ' 个' + (r.created_file ? '（新建文件 ' + file + '）' : '')
      + (skips.length ? '；跳过 ' + skips.length + '：' + skips.slice(0, 3).join('、') + (skips.length > 3 ? '…' : '') : ''));
    $('collect-mask').style.display = 'none';
  } finally {
    btn.disabled = false;
  }
}

/* ================= 弹窗改版（v6.98）：图标卡快捷选择 / 锚点卡 / 三件套状态条 =================
   纯样式配套 JS：不新增字段、不改保存逻辑。el-op-type 原生 select 保留（全量操作类型），
   图标卡只是常用 6 类的快捷入口，两者写同一字段并互相同步高亮。 */
const OP_GRID_TYPES = STEP_TYPES.map(t => t.v);   // 全部操作类型铺满图标卡，区域内滚动
/* 简约 iOS 线性图标（24×24 网格 · stroke 1.8 · currentColor，跟随选中态反白） */
const svgIcon = (inner) =>
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>';
const OP_GRID_ICONS = {
  click: svgIcon('<circle cx="12" cy="14" r="1.8" fill="currentColor" stroke="none"/><path d="M8.2 9.8a5.4 5.4 0 0 1 7.6 0"/>'),
  input: svgIcon('<rect x="4" y="7" width="16" height="10" rx="2"/><path d="M8 10.5h8M8 13.5h5"/>'),
  long_press: svgIcon('<circle cx="12" cy="14" r="1.8" fill="currentColor" stroke="none"/><path d="M8.2 9.8a5.4 5.4 0 0 1 7.6 0M5.8 7.2a8.6 8.6 0 0 1 12.4 0"/>'),
  tap: svgIcon('<circle cx="12" cy="12" r="5.5"/><path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3"/>'),
  screenshot: svgIcon('<rect x="3.5" y="7" width="17" height="12" rx="2.5"/><path d="M8.5 7l1.2-2h4.6L15.5 7"/><circle cx="12" cy="13" r="3"/>'),
  sleep: svgIcon('<circle cx="12" cy="12" r="7.5"/><path d="M12 8v4l2.8 1.8"/>'),
  assert_visible: svgIcon('<path d="M3.5 12s3.2-5.5 8.5-5.5S20.5 12 20.5 12s-3.2 5.5-8.5 5.5S3.5 12 3.5 12z"/><circle cx="12" cy="12" r="2.4"/>'),
  assert_text: svgIcon('<path d="M5 6h14M5 10h14M5 14h8"/><path d="M14.5 17.5l2 2 3.5-3.5"/>'),
  assert_toast: svgIcon('<path d="M4.5 6h15a1.5 1.5 0 0 1 1.5 1.5v6a1.5 1.5 0 0 1-1.5 1.5H11l-4 3.5V15H4.5A1.5 1.5 0 0 1 3 13.5v-6A1.5 1.5 0 0 1 4.5 6z"/>'),
  assert_gone: svgIcon('<path d="M5 5l14 14"/><path d="M3.5 12s3.2-5.5 8.5-5.5c1.6 0 3 .4 4.3 1.1M20.5 12s-3.2 5.5-8.5 5.5c-1.6 0-3-.4-4.3-1.1"/>'),
  wait_element: svgIcon('<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.7 3.5v3.6h-3.6"/>'),
  if_click: svgIcon('<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M6 8.2V14a4 4 0 0 0 4 4h7"/><path d="M14.5 15.5l2.5 2.5-2.5 2.5"/>'),
  custom: svgIcon('<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>'),
};

function syncOpCards() {
  const cur = $('el-op-type').value;
  document.querySelectorAll('#op-grid .op-card').forEach(c =>
    c.classList.toggle('on', c.dataset.op === cur));
}

function buildOpGrid() {
  const grid = $('op-grid');
  if (!grid || grid.dataset.built) return;
  grid.dataset.built = '1';
  OP_GRID_TYPES.forEach(v => {
    const t = stepTypeInfo(v);
    const card = document.createElement('div');
    card.className = 'op-card';
    card.dataset.op = v;
    const shortName = t.n.replace(/\(.*$/, '');
    card.innerHTML = '<span class="oi">' + (OP_GRID_ICONS[v] || svgIcon('<circle cx="12" cy="12" r="7.5"/>')) + '</span><span class="ot" title="' + esc(t.n) + '">' + esc(shortName) + '</span>';
    card.addEventListener('click', () => {
      $('el-op-special').value = '';            // 严格互斥：切到操作类型侧，特殊操作清空置灰
      onSpecialOpChange();
      $('el-op-type').value = v;
      $('el-op-type').dispatchEvent(new Event('change'));
    });
    grid.appendChild(card);
  });
  syncOpCards();
}

/* 视觉互斥（不物理禁用，防死锁）：一侧生效时另一侧置灰；置灰侧仍可点击，点击即切换到该侧 */
function applyOpMutual() {
  const specialOn = !!$('el-op-special').value;
  const grid = $('op-grid');
  if (grid) grid.classList.toggle('locked', specialOn);
  $('el-op-type').classList.toggle('locked', specialOn);
  $('el-op-special').classList.toggle('locked', !specialOn);
}

/* 打开弹窗时：回显锚点卡（已选元素）与三件套落点状态条 */
function fillCaseHead() {
  const name = $('el-name').value.trim();
  const cn = $('el-cn-name').value.trim();
  const typeSel = $('el-type');
  const typeTxt = typeSel.options[typeSel.selectedIndex] ? typeSel.options[typeSel.selectedIndex].textContent : (typeSel.value || '');
  $('ac-name').textContent = name || '—';
  $('ac-cn').textContent = cn ? '（' + cn + '）' : '';
  $('ac-loc').textContent = (typeSel.value || '') + ' · ' + ($('el-value').value || '—');
  const parts = [
    '元素 → ' + ($('el-file').value || '—'),
    '用例行 → ' + ($('el-case-file').value === NEW_FILE_OPT ? '新建 ' + ($('el-case-new').value || '?') : ($('el-case-file').value || '—')),
    '页面方法 → ' + ($('el-page-file').value || '选择用例后带出'),
  ];
  const bar = $('tri-bar');
  bar.textContent = '🛡 三件套一次完成：' + parts.join(' · ');
  bar.style.display = purposeValue() === 'only' ? 'none' : '';
}

/* 字段名高亮 3 秒（新字段出现时引导视线，之后恢复正常样式） */
let fieldFlashTimer = null;
function flashField(labelEl) {
  if (!labelEl) return;
  labelEl.classList.remove('field-flash');
  void labelEl.offsetWidth;             // 重启动画
  labelEl.classList.add('field-flash');
  clearTimeout(fieldFlashTimer);
  fieldFlashTimer = setTimeout(() => labelEl.classList.remove('field-flash'), 3000);
}

/* 配色切换（iPhone 18 配色：默认 → 银色 → 冰川蓝 → 灰白 循环；全站生效，夜间模式下切回日间可见） */
const SKIN_SEQ = [['', '默认'], ['silver', '银色'], ['glacier', '冰川蓝'], ['graywhite', '灰白']];
function applySkinBtn() {
  const cur = (window.__setPlatformSkin ? (localStorage.getItem('platform_skin') || '') : '');
  const label = (SKIN_SEQ.find(s => s[0] === cur) || SKIN_SEQ[0])[1];
  const tx = document.querySelector('#btn-skin .bt-tx');
  if (tx) tx.textContent = '配色：' + label;
}
function cycleSkin() {
  const cur = localStorage.getItem('platform_skin') || '';
  const idx = SKIN_SEQ.findIndex(s => s[0] === cur);
  const next = SKIN_SEQ[(idx + 1) % SKIN_SEQ.length];
  if (window.__setPlatformSkin) window.__setPlatformSkin(next[0]);
  else { localStorage.setItem('platform_skin', next[0]); document.documentElement.dataset.skin = next[0]; }
  const tx = document.querySelector('#btn-skin .bt-tx');
  if (tx) tx.textContent = '配色：' + next[1];
  showToast('配色已切换：' + next[1]);
}
const bs = $('btn-skin');
if (bs) { bs.addEventListener('click', cycleSkin); applySkinBtn(); }
