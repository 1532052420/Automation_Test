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
  { v: 'hide_keyboard', n: '收起键盘', el: false, param: false, ph: '', group: '长流程·等待与分支' },
  { v: 'custom', n: '自定义代码', el: false, param: true, ph: '代码行', group: '长流程·等待与分支', defv: '' },
];
const stepTypeInfo = (v) => STEP_TYPES.find(t => t.v === v) || STEP_TYPES[0];

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
  const lab = document.createElement('span');
  lab.className = 'bar-label';
  lab.textContent = '📂 快速打开';
  bar.appendChild(lab);
  ['open-case-sel', 'open-ele-sel', 'open-page-sel'].forEach(id => {
    const el = $(id);
    if (el) { el.style.maxWidth = '160px'; bar.appendChild(el); }
  });
  // 右侧设备组：📱 前缀标识 + 切换下拉 + 状态，成组靠右不换行（D2 修复）
  const group = document.createElement('span');
  group.className = 'dev-group';
  const devTag = document.createElement('span');
  devTag.className = 'bar-label';
  devTag.textContent = '📱 设备';
  group.appendChild(devTag);
  const devSel = $('device-sel');
  if (devSel) { devSel.style.maxWidth = '180px'; group.appendChild(devSel); }
  const dv = $('dev-info');
  if (dv) { dv.style.marginLeft = '0'; group.appendChild(dv); }
  bar.appendChild(group);
}

async function init() {
  setupEmbedBar();
  // 「返回平台」链接跟随实际访问地址（写死 127.0.0.1 的话，局域网同事点了会指向他自己机器）
  const bp = document.querySelector('.back-platform');
  if (bp) bp.href = location.origin + '/';   // 定位器已内嵌平台，同端口同源，返回平台即站点根
  // 先加载设备下拉并确定 state.serial（恢复上次选中），status/refresh 都按它请求
  await loadDevices();
  const st = await fetch('api/status?serial=' + encodeURIComponent(state.serial || '')).then(r => r.json()).catch(() => null);
  const devInfo = $('dev-info');
  // 版本号以服务端为准（页面缓存旧版本时也能纠正显示）
  if (st && st.version) $('app-version').textContent = st.version;
  if (st && st.ok) {
    state.serial = st.serial || state.serial;
    devInfo.textContent = '📱 ' + st.device.model + ' · Android ' + st.device.platformVersion;
    devInfo.className = 'dev-info ok';
  } else {
    devInfo.textContent = st ? st.msg : '连接失败';
    devInfo.className = 'dev-info bad';
  }
  loadLibraryFiles();
  loadPages();
  renderTutorials();
  if (st && st.ok) refresh();
  $('btn-refresh').addEventListener('click', refresh);
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
  $('tut-search').addEventListener('input', onTutSearch);
  $('btn-add').addEventListener('click', openModal);
  $('btn-modal-cancel').addEventListener('click', () => {
    if (state.continuousAdd) { state.continuousAdd = false; updateContChip(); }
    $('modal-mask').style.display = 'none';
  });
  $('btn-modal-save').addEventListener('click', () => onSaveElement(false));
  $('btn-modal-save-continue').addEventListener('click', () => onSaveElement(true));
  // 连续添加确认弹窗：点「好」仅关闭弹窗（不退出连续添加）；已有元素复用面板三按钮
  $('cont-alert-ok').addEventListener('click', () => { $('cont-add-chip').style.display = 'none'; });
  $('btn-dup-reuse').addEventListener('click', () => { const r = dupResolver; closeDupPanel(); if (r) r('reuse'); });
  $('btn-dup-update').addEventListener('click', () => { const r = dupResolver; closeDupPanel(); if (r) r('update'); });
  $('btn-dup-cancel').addEventListener('click', () => { const r = dupResolver; closeDupPanel(); if (r) r('cancel'); });
  document.querySelectorAll('input[name="el-purpose"]').forEach(r => r.addEventListener('change', onPurposeChange));
  $('el-op-type').addEventListener('change', onOpTypeChange);
  $('el-op-param').addEventListener('input', () => { paramAuto = false; updatePreview(); });
  $('el-case-file').addEventListener('change', onCaseFileChange);
  $('el-case-method').addEventListener('change', updatePreview);
  // 新建文件输入联动：元素文件切「新建」显隐输入行；用例名输入实时派生页面/元素文件名
  $('el-file').addEventListener('change', () => {
    $('el-file-new-wrap').style.display = isNewElementFile() ? '' : 'none';
    updatePreview();
  });
  $('el-case-new').addEventListener('input', () => {
    onCaseFileChange();
    updatePreview();
  });
  $('el-file-new').addEventListener('input', updatePreview);
  // 「保存测试用例包」弹窗按钮
  $('btn-pkg-cancel').addEventListener('click', () => { $('pkg-mask').style.display = 'none'; });
  $('btn-pkg-save').addEventListener('click', () => submitPackage('save'));
  $('btn-pkg-download').addEventListener('click', () => submitPackage('download'));
  // 三栏字段变动 → 三个示例代码区实时刷新
  ['el-name', 'el-value', 'el-comment', 'el-case-comment'].forEach(id => $(id).addEventListener('input', updatePreview));
  $('el-op-comment').addEventListener('input', () => { opCommentAuto = false; updatePreview(); });
  $('el-wait').addEventListener('change', updatePreview);
  // 定位方式切换：从当前元素的定位候选里取该类型的值回填（ID→ID值，XPATH→XPATH值…）
  $('el-type').addEventListener('change', onElTypeChange);
  $('el-wait-sec').addEventListener('input', updatePreview);
  $('el-insert-pos').addEventListener('change', () => { renderStepsList(currentSteps()); updatePreview(); });
  // 顶部快速打开：用例 / 元素文件 / 页面操作 下拉打开编辑
  loadHeaderOpeners();
  $('open-case-sel').addEventListener('change', (e) => { onOpenHdrFile('case', e.target.value); e.target.value = ''; });
  $('open-ele-sel').addEventListener('change', (e) => { onOpenHdrFile('element', e.target.value); e.target.value = ''; });
  $('open-page-sel').addEventListener('change', (e) => { onOpenHdrFile('page', e.target.value); e.target.value = ''; });
  $('btn-view-close').addEventListener('click', () => { $('view-mask').style.display = 'none'; });
  $('btn-view-save').addEventListener('click', onSaveHdrFile);
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
  const contentWidth = () => {
    const m = document.querySelector('main');
    return m.getBoundingClientRect().width - 24;   // 减去 main 左右 padding
  };
  // 恢复上次拖拽的宽度（仅宽屏生效；窄屏纵向堆叠忽略）
  try {
    const saved = JSON.parse(localStorage.getItem('locator_col_widths') || 'null');
    if (saved && window.matchMedia('(min-width: 921px)').matches) {
      const cw = contentWidth();
      if (cw > 600 && saved.leftFrac && saved.midFrac) {
        left.style.flex = '0 1 ' + Math.round(cw * saved.leftFrac) + 'px';
        mid.style.flex = '0 1 ' + Math.round(cw * saved.midFrac) + 'px';
      }
    }
  } catch (e) {}
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
          const avail = cw - 60 - 280;                 // 60=4个gap+2个手柄，280=右栏下限
          const leftW = clamp(relX, 280, avail - 280);
          left.style.flex = '0 1 ' + Math.round(leftW) + 'px';
          mid.style.flex = '0 1 ' + Math.round(avail - leftW) + 'px';
        } else {
          const leftW = left.getBoundingClientRect().width;
          const avail = cw - 60 - Math.round(leftW) - 280;
          const midW = clamp(relX - leftW - 20, 280, Math.max(280, avail));
          mid.style.flex = '0 1 ' + Math.round(midW) + 'px';
        }
        // 宽度按内容宽度比例记忆（窗口尺寸变化也能按比例恢复）
        try {
          localStorage.setItem('locator_col_widths', JSON.stringify({
            leftFrac: left.getBoundingClientRect().width / cw,
            midFrac: mid.getBoundingClientRect().width / cw,
          }));
        } catch (err) {}
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

/* ---------- 顶部快速打开：用例 / 元素定位 / 页面操作 文件编辑 ---------- */
async function loadHeaderOpeners() {
  const cs = await fetch('api/cases').then(r => r.json()).catch(() => null);
  const caseSel = $('open-case-sel');
  if (cs && cs.ok && caseSel) {
    caseSel.innerHTML = '<option value="">📂 打开用例…</option>' +
      (cs.case_info || []).map(c => '<option value="' + esc(c.file) + '">' + esc(c.file) + '</option>').join('');
  }
  const lib = await fetch('api/library').then(r => r.json()).catch(() => null);
  const eleSel = $('open-ele-sel');
  if (lib && lib.ok && eleSel) {
    eleSel.innerHTML = '<option value="">🗂 打开元素文件…</option>' +
      (lib.files || []).map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('');
  }
  const pg = await fetch('api/pages').then(r => r.json()).catch(() => null);
  const pageSel = $('open-page-sel');
  if (pg && pg.ok && pageSel) {
    pageSel.innerHTML = '<option value="">🧩 打开页面操作…</option>' +
      (pg.pages || []).map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('');
  }
}

// 当前打开的文件（{kind, filename}），保存时用
let viewFile = null;

async function onOpenHdrFile(kind, filename) {
  if (!filename) return;
  const q = { case: 'case=', element: 'element=', page: 'page=' }[kind];
  const r = await fetch('api/file_content?' + q + encodeURIComponent(filename)).then(r => r.json()).catch(() => null);
  if (!r || !r.ok) { alert((r && r.msg) || '读取失败'); return; }
  viewFile = { kind: kind, filename: filename };
  $('view-title').textContent = '📄 ' + r.title;
  $('view-content').value = r.content;
  setViewStatus('可直接修改，点「💾 保存修改」写回文件（保存前自动做语法检查）', '');
  $('view-mask').style.display = 'flex';
}

function setViewStatus(msg, cls) {
  const el = $('view-status');
  el.textContent = msg;
  el.className = 'hint' + (cls ? ' ' + cls : '');
}

async function onSaveHdrFile() {
  if (!viewFile) return;
  const btn = $('btn-view-save');
  btn.disabled = true; btn.textContent = '保存中…';
  setViewStatus('正在保存…', '');
  const r = await fetch('api/save_file', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind: viewFile.kind, filename: viewFile.filename, content: $('view-content').value }),
  }).then(r => r.json()).catch(() => null);
  btn.disabled = false; btn.textContent = '💾 保存修改';
  if (!r || !r.ok) {
    setViewStatus((r && r.msg) || '保存失败：服务异常', 'bad');
    alert((r && r.msg) || '保存失败：服务异常');
    return;
  }
  setViewStatus('✓ ' + r.msg, 'ok');
  // 元素/用例/页面文件可能被手改，刷新相关下拉与状态
  loadHeaderOpeners(); loadLibraryFiles(); loadCaseFiles(); loadPages();
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
/* 设备下拉选项文案：同型号多台设备（如同一台手机的 USB+WiFi 双通道）靠 serial 尾段区分 */
function deviceOptionText(d) {
  let tail = d.serial || '';
  if (tail.length > 9) tail = '…' + tail.slice(-8);
  return d.model + ' · Android ' + d.platformVersion + '（' + tail + '）';
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
  refresh();
}

/* ---------- 刷新：截图 + 元素树 ----------
   token 竞态防护：刷新期间用户切换/连切设备时，慢的旧响应若后到会覆盖新设备画面——
   每次请求带自增 token，响应回来时 token 已不是最新 → 丢弃；
   服务端标记 fallback（请求设备掉线回退）→ 校正下拉；其余 serial 不一致（过期响应）→ 丢弃 */
let refreshSeq = 0;
async function refresh() {
  const myToken = ++refreshSeq;
  $('btn-refresh').textContent = '刷新中…'; $('btn-refresh').disabled = true;
  try {
    const r = await fetch('api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serial: state.serial }),
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
      dv.textContent = '📱 ' + r.device.model + ' · Android ' + r.device.platformVersion;
      dv.title = r.device.model + '（' + (r.serial || '') + '）';
      dv.className = 'dev-info ok';
    }
    // 统一分配 uid（DFS 先父后子，tree 与 all 顺序一致）
    let seq = 1;
    (function assign(node) { node.uid = seq++; node.children.forEach(assign); })(state.tree);
    let k = 0;
    (function assignAll(node) { state.all[k++].uid = node.uid; node.children.forEach(assignAll); })(state.tree);
    state.selUid = null; state.selNode = null;
    state.hitCands = null;
    $('detail').style.display = 'none';
    $('shot-empty').style.display = 'none';
    const img = $('shot');
    img.src = r.screenshot; img.style.display = 'block';
    renderTree(state.tree);
  } catch (err) {
    console.error('[locator] refresh error:', err);
    // 把错误直接显示在页面上，避免 try/finally 静默吞掉异常导致"点了没反应"
    $('shot-empty').textContent = '刷新出错: ' + (err && err.message ? err.message : String(err));
    $('shot-empty').style.display = 'block';
  } finally {
    $('btn-refresh').textContent = '🔄 刷新'; $('btn-refresh').disabled = false;
  }
}

/* ---------- 截图点击命中 ---------- */
// 由点击事件算出命中的最内层元素 + 所有包含该点的候选（按面积升序）
function hitFromEvent(e) {
  if (!state.all.length) return null;
  const img = $('shot');
  const rect = img.getBoundingClientRect();
  if (rect.width <= 0) return null;
  // 点击换算：先按截图(PNG)实际像素定位，再映射到 uiautomator XML 坐标。
  // 关键：PNG 尺寸(如720x1600)与 XML 尺寸(如720x1536)可能不一致——
  // 华为机的 PNG 底部多了虚拟导航条(64px)，XML 是顶部对齐的内容区坐标。
  // 所以宽度同值，高度用 PNG 像素点亮的 y，超过 XML 高度部分按导航条处理。
  const natW = img.naturalWidth || state.width;
  const natH = img.naturalHeight || state.height;
  const pngX = (e.clientX - rect.left) / rect.width * natW;
  const pngY = (e.clientY - rect.top) / rect.height * natH;
  const px = pngX;                          // 宽同值
  const py = Math.min(pngY, state.height);  // 顶部对齐同值，多余的底部是导航条
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
  const r = hitFromEvent(e);
  if (!r) return;
  state.hitCands = r.cands;
  selectNode(r.hit.uid);
}
// 双击执行器：双击截图 = 在设备上真实点击该元素（验证定位是否准确）
function onShotDblClick(e) {
  const r = hitFromEvent(e);
  if (!r) return;
  state.hitCands = r.cands;
  selectNode(r.hit.uid);
  tapOnDevice(r.hit.center, r.hit.text || r.hit['resource-id'] || '双击元素');
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
    refresh();
  } else {
    tip.textContent = (r && r.msg ? r.msg : '点击失败');
    tip.className = 'tap-tip err';
  }
}

/* ---------- 树渲染 ---------- */
function renderTree(tree) {
  const box = $('tree');
  box.innerHTML = '';
  box.appendChild(buildTreeUl(tree));
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

/* 树搜索：按 text / resource-id / class 过滤（命中节点保留，父链保留） */
function onTreeSearch(e) {
  if (!state.tree) return;
  const kw = e.target.value.trim().toLowerCase();
  if (!kw) { renderTree(state.tree); return; }
  const filtered = filterTree(state.tree, kw);
  $('tree').innerHTML = '';
  $('tree').appendChild(buildTreeUl(filtered));
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
  // 连续添加模式：选中元素即自动弹出「添加到元素库」——点一个录一步，直到退出
  if (state.continuousAdd) openModal();
}
function highlightShot(node) {
  const ov = $('shot-overlay');
  const img = $('shot');
  if (!node.bounds_num || img.style.display === 'none') { ov.style.display = 'none'; return; }
  const scale = img.clientWidth / state.width;
  const [x1, y1, x2, y2] = node.bounds_num;
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
  const rows = ATTRS.filter(k => node[k] !== undefined && node[k] !== '' && node[k] !== false)
    .map(k => '<tr><td>' + esc(k) + '</td><td>' + esc(node[k]) + '</td></tr>')
    .join('');
  // 重复 resource-id 提示
  const rid = node['resource-id'];
  const sameCount = rid ? state.all.filter(n => n['resource-id'] === rid).length : 0;
  const dupTip = sameCount > 1
    ? '<div class="dup-tip">⚠ 该 resource-id 页面有 <b>' + sameCount + '</b> 个相同的，定位会不准。' +
      '用例里用 <code>appOperator.getElements(元素)[i]</code> 按下标取第 i 个（0 开始），' +
      '或用下面带 <code>instance</code> / 下标 的写法。</div>' : '';
  $('detail-attrs').innerHTML = rows + '<tr><td>中心坐标</td><td>' + (node.center ? node.center.join(', ') : '-') + '</td></tr>';
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
  updatePreview();
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
  if (!state.selNode) { alert('请先在截图或元素树里选中一个元素'); return; }
  const node = state.selNode;
  // 自动名称：优先 resource-id 末段，其次 text 截断
  let auto = '';
  const rid = node['resource-id'] || '';
  if (rid && rid.includes('/')) auto = rid.split('/').pop();
  else if (node.text && node.text.trim()) auto = node.text.trim().replace(/\s+/g, '_').slice(0, 20);
  else auto = 'element_' + state.selUid;
  $('el-name').value = auto;
  const loc = selectedLocator() || { type: 'ID', value: node['resource-id'] || '' };
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
  $('el-op-type').innerHTML = opTypeOptions();
  $('el-op-type').value = 'click';
  $('el-op-param').value = '';
  paramAuto = true;  // 打开弹窗重置为「自动预填」状态
  // 步骤描述自动预填：优先元素文本（报告更友好），无文本则留空由后端按元素名生成
  $('el-op-comment').value = autoStepComment('click', node.text);  // 默认按「点击」生成；切类型时自动跟随
  opCommentAuto = true;
  $('el-comment').value = '';
  $('el-case-comment').value = '';
  $('el-page-file').value = '';
  closeDupPanel();
  setElLinkNote('');
  onOpTypeChange();
  await loadCaseFiles();
  document.querySelector('input[name="el-purpose"][value="all"]').checked = true;
  onPurposeChange();
  $('modal-mask').style.display = 'flex';
}
/* ---- 新建文件输入（元素文件 / 用例文件）：选「➕ 新建…」时显示 ---- */
const NEW_FILE_OPT = '__new__';
function capFirst(s) { s = String(s || ''); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
function resetNewFileInputs() {
  const fw = $('el-file-new-wrap'), cw = $('el-case-new-wrap');
  if (fw) { fw.style.display = 'none'; $('el-file-new').value = ''; }
  if (cw) { cw.style.display = 'none'; $('el-case-new').value = ''; }
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
/* ---- 已有元素复用面板：命中相同定位时弹出，默认「直接复用」防元素库膨胀 ---- */
let dupResolver = null;
function askDuplicatePanel(dup) {
  const used = dup.used_in || [];
  const usedTxt = used.length
    ? '已被用例使用：' + used.map(u => u.file + '（' + u.count + ' 处）').join('、')
    : '暂无用例使用';
  $('el-dup-info').textContent = '已有元素「' + dup.name + '」（' + dup.filename + '）· ' + usedTxt
    + '。直接复用不在元素库新增条目，且不阻止你继续添加「用例 + 操作」；'
    + '「更新元素定义」才会用当前定位/等待覆盖它。';
  $('el-dup-panel').style.display = '';
  return new Promise(resolve => { dupResolver = resolve; });
}
function closeDupPanel() {
  $('el-dup-panel').style.display = 'none';
  dupResolver = null;
}
/* ---- 连续添加模式：保存并继续后开启；点截图/元素树选中新元素自动弹出添加窗口 ----
   确认弹窗：本次页面会话内只在第一次开启时弹出一次（避免每次保存并继续都打扰），
   点「好」关闭；退出连续添加走「添加测试用例」弹窗的取消按钮 */
let contAlertShown = false;
function updateContChip() {
  const chip = $('cont-add-chip');
  if (!chip) return;
  if (state.continuousAdd && !contAlertShown) {
    contAlertShown = true;
    chip.style.display = '';
  } else {
    chip.style.display = 'none';
  }
}
/* ---- 目标方法已有步骤 + 插入位置（②栏） ---- */
function currentSteps() {
  const f = $('el-case-file').value;
  const method = $('el-case-method').value;
  if (!f || !method) return [];
  const info = (state.caseFiles || []).find(c => c.file === f && (c.method_steps || {})[method]);
  return info ? (info.method_steps[method] || []) : [];
}
function insertPos() { return parseInt($('el-insert-pos').value, 10) || 0; }
function newStepNo() { const p = insertPos(); return p > 0 ? p + 1 : currentSteps().length + 1; }
function renderStepsList(steps) {
  const box = $('el-steps-list');
  if (!box) return;
  if (purposeValue() === 'only' || !$('el-case-method').value) { box.innerHTML = ''; box.style.display = 'none'; return; }
  box.style.display = '';
  const pos = insertPos();
  const newNo = pos > 0 ? pos + 1 : steps.length + 1;
  const step = { type: $('el-op-type').value, element: $('el-name').value.trim() || '<元素名>', param: $('el-op-param').value.trim() };
  const desc = $('el-op-comment').value.trim() || genStepDesc(step);
  let html = steps.length
    ? '<div class="sl-title">当前用例已有 ' + steps.length + ' 步：</div>'
    : '<div class="sl-title">当前方法还没有步骤，这一步将是第 1 步：</div>';
  steps.forEach((s, i) => {
    html += '<div class="sl-row"><span class="sl-idx">' + (i + 1) + '</span><span>' + esc(s) + '</span></div>';
  });
  html += '<div class="sl-row new"><span class="sl-idx">' + newNo + '</span><span>➕ 本步：'
    + esc(desc) + (pos > 0 ? '（插到第 ' + pos + ' 步之后）' : '') + '</span></div>';
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
    comment: $('el-comment').value.trim(),                          // 元素备注 → 元素行行尾注释
    check_dup: checkDup ? 1 : 0,
  };
  if (!payload.name || !payload.value) { showElResult('元素名称和定位值不能为空', false); return null; }
  const r = await fetch('api/add_element', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    .then(r => r.json()).catch(() => null);
  if (!r) { showElResult('保存失败：服务异常', false); return null; }
  return r;
}
/* 用途单选：① 仅元素 → ②③栏熄灭；② 元素+用例 → ③栏只生成用例行；③ 三件套全联动 */
function onPurposeChange() {
  const p = purposeValue();
  $('col-case').classList.toggle('dim', p === 'only');
  $('col-op').classList.toggle('dim', p === 'only');
  if (p !== 'only') { onOpTypeChange(); onCaseFileChange(); }
  else { renderStepsList([]); updateOpNote(); }
  updatePreview();
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
  const t = stepTypeInfo($('el-op-type').value);
  const purposeNote = p === 'all'
    ? '🔗 保存时将自动生成/更新页面操作方法（三件套一次完成）'
    : (p === 'case' ? '⚠ 不会生成页面方法——目标页面须已存在同名方法，否则执行报错' : '');
  const notes = {
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

function autoStepComment(type, elementText) {
  /* 按类型自动生成步骤描述（用元素文本更友好，无文本回退元素名） */
  const t = (elementText || '').trim();
  switch (type) {
    case 'click': return t ? '点击「' + t + '」' : '';
    case 'input': return t ? '在「' + t + '」输入' : '';
    case 'long_press': return t ? '长按「' + t + '」' : '';
    case 'wait_element': return t ? '等待「' + t + '」出现' : '';
    case 'assert_gone': return t ? '断言「' + t + '」已消失' : '';
    case 'if_click': return t ? '若「' + t + '」出现则点击' : '';
    case 'assert_visible': return t ? '断言「' + t + '」出现' : '';
    default: return '';
  }
}

function onOpTypeChange() {
  const t = stepTypeInfo($('el-op-type').value);
  $('el-op-param-wrap').style.display = t.param ? '' : 'none';
  $('el-op-param').placeholder = t.ph || '参数';
  // 换类型时：参数为空或是上个类型的自动预填值 → 换成当前类型默认值（用户手输过则保留）
  if (t.param && (paramAuto || !$('el-op-param').value.trim())) {
    if (t.defv !== undefined) $('el-op-param').value = t.defv;
    paramAuto = true;
  }
  // 步骤描述是自动预填时跟随类型重生成（避免「等待」步骤还挂着「点击…」描述）
  if (opCommentAuto) {
    $('el-op-comment').value = autoStepComment(t.v, $('el-name').value);
  }
  // 无需元素的类型（收键盘/Toast/坐标/截图/固定等待/自定义）：元素栏弱化示意「这步不依赖元素」
  // （元素本身仍会照常入库——从截图选进来的元素攒在库里，后续步骤可用）
  $('col-element').classList.toggle('soft', t.el === false);
  $('col-element').classList.toggle('dim', false);
  updateOpNote();
  updatePreview();
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
/* 页面方法名预览：与后端 method_name 派生规则一致（sleep/custom 无页面方法） */
function pageMethodName(step) {
  const t = step.type, el = step.element || '<元素名>';
  return {
    click: 'click_' + el, input: 'input_' + el, long_press: 'long_press_' + el,
    assert_visible: 'assert_' + el, assert_text: 'assert_' + el + '_text',
    assert_toast: 'assert_toast', screenshot: 'wait_and_shot', tap: 'tap_xy',
    wait_element: 'wait_' + el, assert_gone: 'assert_' + el + '_gone',
    if_click: 'click_' + el + '_if_visible', hide_keyboard: 'dismiss_keyboard',
  }[t] || '';
}
/* 目标用例的页面文件（来自 /api/cases 的三件套归属信息） */
function targetPageInfo() {
  const f = $('el-case-file').value;
  const info = (state.caseFiles || []).find(c => c.file === f && c.page_file);
  return info || null;
}
/* ---- 三个实时预览：元素代码 / 用例代码 / 页面方法代码（与后端生成规则保持一致） ---- */
/* 元素栏：将写入元素库的那一行 */
function elementLinePreview() {
  const name = $('el-name').value.trim() || '<元素名>';
  const val = $('el-value').value.trim();
  const sec = parseInt($('el-wait-sec').value, 10);
  let line = "self." + name + " = CreateElement.create(Locator_Type." + $('el-type').value
    + ", '" + escQ(val) + "', wait_type=Wait_By." + $('el-wait').value;
  if (!isNaN(sec) && sec >= 1) line += ", wait_seconds=" + sec;
  line += ')';
  const c = $('el-comment').value.trim();
  if (c) line += '  # ' + c;
  return line;
}
/* 用例栏：将插入到目标方法的注释行 + 代码行（注释=步骤描述，留空后端自动生成） */
function caseLinesPreview(step) {
  const c = $('el-case-comment').value.trim();
  const desc = c || genStepDesc(step);
  return '# ' + desc + '\n' + previewLine(step);
}
/* 操作栏：选③时将生成到页面文件的页面方法（镜像后端 page_method_code） */
function probeBodyLines(el, secondsVar) {
  return "probe = CreateElement.create(self._elements." + el + ".locator_type,\n"
    + "                             self._elements." + el + ".locator_value,\n"
    + "                             wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n"
    + "                             wait_seconds=" + secondsVar + ")";
}
function pageMethodPreview(step) {
  const pm = pageMethodName(step);
  if (!pm) return '（该操作类型无需页面方法）';
  const el = step.element || '<元素名>';
  const doc = $('el-op-comment').value.trim() || genStepDesc(step);
  const t = step.type;
  const p = step.param || '';
  let sig = pm, body = '';
  if (t === 'click') body = 'self.appOperator.click(self._elements.' + el + ')';
  else if (t === 'input') { sig += '(self, text)'; body = 'self.appOperator.sendText(self._elements.' + el + ', text)'; }
  else if (t === 'long_press') body = 'self.appOperator.touch_long_press(self._elements.' + el + ', duration_sconds=2)';
  else if (t === 'assert_visible') body = 'self.appOperator.getElement(self._elements.' + el + ')';
  else if (t === 'assert_text') { sig += '(self, expected)'; body = "assert self.appOperator.getText(self._elements." + el + ") == expected, '" + escQ(doc) + "'"; }
  else if (t === 'assert_toast') { sig += '(self, text)'; body = "assert self.appOperator.is_toast_visible(text, wait_seconds=5), '" + escQ(doc) + "'"; }
  else if (t === 'wait_element') {
    const n = parseInt(p, 10);
    sig += '(self, timeout_seconds=' + (isNaN(n) ? 60 : n) + ')';
    body = probeBodyLines(el, 'timeout_seconds') + '\nself.appOperator.getElement(probe)';
  }
  else if (t === 'assert_gone') {
    sig += '(self, wait_seconds=2)';
    body = probeBodyLines(el, 'wait_seconds') + '\ngone = True\ntry:\n    self.appOperator.getElement(probe)\n    gone = False\nexcept Exception:\n    pass\n'
      + "self.appOperator.assert_true_with_shot('" + escQ(doc) + "', gone,\n"
      + "                                   '等待' + str(wait_seconds) + '秒内元素仍可见')";
  }
  else if (t === 'if_click') {
    const n = parseInt(p, 10);
    sig += '(self, timeout_seconds=' + (isNaN(n) ? 3 : n) + ')';
    body = probeBodyLines(el, 'timeout_seconds') + '\ntry:\n    self.appOperator.click(self.appOperator.getElement(probe))\nexcept Exception:\n    pass';
  }
  else if (t === 'hide_keyboard') {
    body = 'try:\n    if self.appOperator.is_keyboard_shown():\n        self.appOperator.hide_keyboard()\nexcept Exception:\n    self.appOperator.press_keycode(4)\nimport time\ntime.sleep(1)';
  }
  else if (t === 'screenshot') { sig += '(self, tag)'; body = 'import time\ntime.sleep(1)\nself.appOperator.get_screenshot(tag)'; }
  else if (t === 'tap') { sig += '(self, x, y)'; body = 'self.appOperator.tap(x, y)'; }
  return 'def ' + sig + ':\n    """' + doc + '"""\n    ' + body.replace(/\n/g, '\n    ');
}
function updatePreview() {
  // 元素代码：任何用途都实时显示（元素栏是必走的第一步）
  $('el-code-element').textContent = elementLinePreview();
  const p = purposeValue();
  const step = {
    type: $('el-op-type').value,
    element: $('el-name').value.trim() || '<元素名>',
    param: $('el-op-param').value.trim(),
  };
  // 步骤列表的「本步」描述跟随类型/参数/描述实时刷新（避免列表里还挂着旧类型文案）
  if (p !== 'only') renderStepsList(currentSteps());
  // 用例代码 / 页面方法：按用途显示
  if (p === 'only') {
    $('el-code-case').textContent = '';
    $('el-code-preview').textContent = '';
    return;
  }
  $('el-code-case').textContent = caseLinesPreview(step);
  if (p === 'all') $('el-code-preview').textContent = pageMethodPreview(step);
  else $('el-code-preview').textContent = '（② 不生成页面方法；目标页面须已存在同名方法）';
}
/* ---- 目标用例文件 + 方法（两级联动；③ 时元素文件自动对齐页面引用的元素文件） ---- */
async function loadCaseFiles() {
  const r = await fetch('api/cases').then(r => r.json()).catch(() => null);
  if (!r || !r.ok) return;
  state.caseFiles = r.case_info || [];
  const sel = $('el-case-file');
  const cur = sel.value;
  const files = [];
  (state.caseFiles || []).forEach(c => { if (files.indexOf(c.file) < 0) files.push(c.file); });
  // 「➕ 新建…」永远在最后：选择后显示 test_ 前缀锁定输入行（保存走「保存测试用例包」）
  sel.innerHTML = files.map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('')
    + '<option value="' + NEW_FILE_OPT + '">➕ 新建用例文件…</option>';
  if (cur === NEW_FILE_OPT || (cur && files.indexOf(cur) >= 0)) sel.value = cur;
  else if (files.length) sel.value = files[0];
  onCaseFileChange();
}
function onCaseFileChange() {
  // 新建用例：切换到「新建输入模式」——方法/插入位置无意义，页面/元素文件自动派生
  const newCase = isNewCase();
  $('el-case-new-wrap').style.display = newCase ? '' : 'none';
  $('el-case-method').disabled = newCase;
  $('el-insert-pos').disabled = newCase;
  $('el-page-file').value = newCase ? (newCaseBase() ? capFirst(newCaseBase()) + 'Page.py（随用例包新建）' : '（输入用例名后自动派生）')
                                    : '';
  if (newCase) { renderStepsList([]); updatePkgPreview(); return; }
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
  let posOpts = '<option value="0">末尾（成为第 ' + (steps.length + 1) + ' 步）</option>';
  for (let i = 1; i <= steps.length; i++) {
    posOpts += '<option value="' + i + '">第 ' + i + ' 步之后 · ' + esc(String(steps[i - 1]).slice(0, 12)) + '</option>';
  }
  posSel.innerHTML = posOpts;
  posSel.value = (curPos !== '' && curPos !== null && parseInt(curPos, 10) <= steps.length) ? curPos : '0';
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
      $('el-file').value = info.elements_file;
      setElLinkNote('🔗 页面 ' + info.page_file + ' 引用元素文件 ' + info.elements_file + '，「写入元素文件」已自动对齐');
    } else {
      setElLinkNote('🔗 三件套去向：页面 ' + info.page_file + ' ← 元素文件 ' + info.elements_file);
    }
  } else if (info) {
    setElLinkNote('该用例的页面: ' + info.page_file + (info.elements_file ? '（元素: ' + info.elements_file + '）' : ''));
  } else {
    setElLinkNote('');
  }
  updatePreview();
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
  return { type: $('el-op-type').value, element: $('el-name').value.trim() || '<元素名>', param: $('el-op-param').value.trim() };
}
/* 与后端 page_method_code 同规则的页面方法块（包生成用；pageMethodPreview 是展示格式，无签名不能执行） */
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
  const casePy = '# -*- coding: utf-8 -*-\n'
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
/* 包弹窗预览：三个文件落点 */
function updatePkgPreview() {
  const box = $('pkg-files-preview');
  if (!box) return;
  const files = pkgFiles();
  box.textContent = files.map(f => f.dir + '/' + f.name).join('\n');
}
function openPackageModal() {
  $('pkg-name').value = pkgBase();
  updatePkgPreview();
  $('pkg-result').className = 'el-result'; $('pkg-result').textContent = '';
  $('pkg-content').textContent = '';
  $('pkg-mask').style.display = 'flex';
}
/* 生成三件套 zip：mode=save（交平台做校验/备份/登记后入库）/ download（浏览器下载 zip） */
async function submitPackage(mode) {
  const base = ($('pkg-name').value || '').trim().replace(/[^A-Za-z0-9_\-]/g, '_');
  if (!base) { showPkgResult('请填写用例包名称', false); return; }
  const files = pkgFiles().map(f => ({ dir: f.dir, name: f.name, content: f.content }));
  const btn = mode === 'save' ? $('btn-pkg-save') : $('btn-pkg-download');
  btn.textContent = '⏳ 处理中…'; btn.disabled = true;
  try {
    if (mode === 'save') {
      const r = await fetch('api/save_case_package', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package: base, uploader: 'locator', files: files }),
      }).then(x => x.json()).catch(() => null);
      if (!r) { showPkgResult('保存失败：服务异常', false); return; }
      showPkgResult(r.msg || (r.ok ? '已保存到框架' : '保存失败'), !!r.ok);
      if (r.ok) {
        loadPages(); loadLibraryFiles(); loadCaseFiles();
        setTimeout(() => { $('pkg-mask').style.display = 'none'; $('modal-mask').style.display = 'none'; }, 1500);
      }
    } else {
      const resp = await fetch('api/build_case_package', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package: base, files: files }),
      });
      if (!resp.ok) { showPkgResult('生成 zip 失败', false); return; }
      const blob = await resp.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = base + '.zip';
      a.click();
      URL.revokeObjectURL(a.href);
      showPkgResult('用例包 ' + base + '.zip 已下载——请到测试平台「用例管理 → 📦 上传用例包」入库', true);
    }
  } finally {
    btn.textContent = mode === 'save' ? '💾 保存到框架' : '⬇ 下载用例包（zip）';
    btn.disabled = false;
  }
}
function showPkgResult(msg, ok) {
  const box = $('pkg-result');
  box.className = 'el-result ' + (ok ? 'ok' : 'err');
  box.textContent = msg;
}

async function onSaveElement(continueMode) {
  const purpose = purposeValue();
  if (!purpose) return;
  const name = $('el-name').value.trim();
  // 新建用例文件场景：不走「追加到已有用例」，改走「保存测试用例包」（三件套一次生成）
  if (purpose !== 'only' && (isNewCase() || isNewElementFile())) {
    if (!pkgBase()) { showElResult('请先输入新用例名（test_ 后面的部分）', false); return; }
    if (!$('el-name').value.trim()) { showElResult('元素名称不能为空', false); return; }
    openPackageModal();
    return;
  }
  // 选②：前置校验用例栏（保存元素前就拦住，避免元素入库了代码却追加不了）
  let caseFile = '', methodName = '';
  if (purpose !== 'only') {
    caseFile = $('el-case-file').value;
    methodName = $('el-case-method').value;
    if (!(state.caseFiles || []).some(c => c.file === caseFile)) {
      showElResult('请选择目标用例文件（或选「➕ 新建用例文件…」一次生成三件套）', false); return;
    }
    if (!methodName) { showElResult('请选择目标方法', false); return; }
  }
  // 同名（同文件）覆盖确认：防止误覆盖已有元素
  const fname = $('el-file').value;
  if (name && (state.elementsAll[fname] || []).indexOf(name) >= 0) {
    if (!confirm('元素库文件 ' + fname + ' 里已有同名元素「' + name + '」，保存将覆盖更新原定义。\n\n' +
      '点「确定」= 覆盖更新\n点「取消」= 不保存')) return;
  }
  let r = await saveElement(true);
  if (!r) return;
  let savedName = name;
  let dupHandled = false;   // 已处理「相同定位重复」：复用=使用已有元素 / 更新=覆盖定义 / 取消
  if (r.duplicate) {
    dupHandled = true;
    const choice = await askDuplicatePanel(r.duplicate);
    if (choice === 'cancel') { showElResult('已取消，元素未保存（可改用途或直接关闭）', false); return; }
    if (choice === 'reuse') {
      savedName = r.duplicate.name;        // 直接复用：不新建，防元素库膨胀；用例+操作继续
    } else {
      r = await saveElement(false);        // 更新元素定义：用当前定位/等待覆盖
      if (!r || !r.ok) { if (r) showElResult(r.msg, false); return; }
      savedName = $('el-name').value.trim();
    }
  }
  // 非重复场景失败 → 报错返回；重复但已「使用已有元素」→ 继续后续流程
  if (!r || (!r.ok && !dupHandled)) { if (r) showElResult(r.msg, false); return; }

  const finishContinue = () => {
    loadPages(); loadLibraryFiles(); loadCaseFiles();
    state.continuousAdd = true;
    updateContChip();
    $('modal-mask').style.display = 'none';
  };

  if (purpose === 'only') {
    if (dupHandled && r.duplicate) {
      showElResult('已复用已有元素「' + savedName + '」（未新建，避免元素库重复）', true);
    } else {
      if (r.ok && r.content) $('el-content').textContent = r.content;
      showElResult(r.msg + ' —— 已保存到元素库', true);
    }
    if (continueMode) finishContinue();
    else setTimeout(() => { $('modal-mask').style.display = 'none'; }, 600);
    return;
  }
  // purpose ②/③：追加一步代码到目标用例方法体末尾（③ 同时生成/更新页面方法）
  const step = {
    type: $('el-op-type').value,
    element: savedName,
    param: $('el-op-param').value.trim(),
    desc: '',
    comment: $('el-op-comment').value.trim(),        // 操作备注 → 页面方法 docstring
    case_comment: $('el-case-comment').value.trim(), // 用例备注 → 追加行上方注释
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
  res.textContent = (dupHandled ? '已使用已有元素「' + savedName + '」' : r.msg)
    + '；' + cr.msg + '（三件套已联动完成）';
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
  loadPages(); loadLibraryFiles(); loadCaseFiles();
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
