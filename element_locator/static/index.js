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
  stepTypes: null,        // 后端 /api/cases 返回的支持操作类型（v6.15.33 能力探测；老后端无此字段 → 隐藏 v2 操作）
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
  // v6.15.33 框架原生手势/设备能力（appOperator 直映射）；v2 标记：老后端不放行时隐藏
  { v: 'swipe_up', n: '上滑', el: true, param: true, ph: '时长ms(默认500)', group: '手势·设备', defv: '500', v2: true },
  { v: 'swipe_down', n: '下滑', el: true, param: true, ph: '时长ms(默认500)', group: '手势·设备', defv: '500', v2: true },
  { v: 'swipe_left', n: '左滑', el: true, param: true, ph: '时长ms(默认500)', group: '手势·设备', defv: '500', v2: true },
  { v: 'swipe_right', n: '右滑', el: true, param: true, ph: '时长ms(默认500)', group: '手势·设备', defv: '500', v2: true },
  { v: 'drag_to', n: '拖拽到元素', el: true, param: true, ph: '目标元素名(元素库已有)', group: '手势·设备', defv: '', v2: true },
];
/* 特殊操作：与元素无关的用例级动作，单独下拉（el-op-special）。不写元素库、元素栏禁用；
   选中后只需选目标用例 + 插入位置。deal_first_launch_dialogs 固定前插（见 onCaseFileChange） */
const SPECIAL_OPS = {
  hide_keyboard: { v: 'hide_keyboard', n: '收起键盘', el: false, param: false },
  deal_first_launch_dialogs: { v: 'deal_first_launch_dialogs', n: '首次启动弹窗处理', el: false, param: false },
};
const stepTypeInfo = (v) => SPECIAL_OPS[v] || STEP_TYPES.find(t => t.v === v) || STEP_TYPES[0];

/* ④断言栏：组合断言类型（操作与断言解耦）——5 种，勾选即启用，全量执行 */
var ASSERT_KINDS = [
  { v: 'exists', n: '断言元素是否可见', d: '元素可见', p: { wait: 3 } },
  { v: 'text', n: '断言文本是否正确', d: '文案相等', p: { text: '' } },
  { v: 'toast', n: '断言Toast是否出现', d: '页面级', p: { toast: '' } },
  { v: 'text_page', n: '断言页面文本出现', d: '页面级', p: { text: '' } },
  { v: 'text_page_gone', n: '断言文案不再出现', d: '页面级', p: { text: '' } },
  { v: 'gone', n: '断言元素是否消失', d: '弹窗已关闭', p: { wait: 2 } },
  { v: 'visual', n: '视觉资产', d: '采集图片入资产库，执行时基线比对', p: { threshold: 0.95, asset: '' }, isNew: true, needVa: true },
];

function assertState() { return state.modalAsserts || (state.modalAsserts = []); }

/* 断言开关：开启=显示断言卡组；关闭=隐藏并清空勾选（toast 提示） */
function bindAssertToggle() {
  var tg = $('asToggle');
  if (!tg) return;
  tg.addEventListener('change', function () {
    var on = tg.checked;
    $('asArea').style.display = on ? '' : 'none';
    if (!on) { state.modalAsserts = []; renderAssertCol(); }
    if (opCommentAuto) $('el-op-comment').value = autoStepComment(currentOpType(), opElementLabel(), $('el-op-param').value) + assertsDescSuffix();
    showToast(on ? '断言开启' : '断言关闭');
  });
}
function resetAssertToggle() {
  var tg = $('asToggle');
  if (tg) tg.checked = false;
  $('asArea').style.display = 'none';
  state.modalAsserts = [];
  renderAssertCol();
}
function findAssert(v) { return assertState().find(x => x.v === v); }

function renderAssertCol() {
  var box = $('asGrid');
  if (!box) return;
  box.innerHTML = ASSERT_KINDS.map(function (d) {
    var r = findAssert(d.v), on = !!r;
    var greyed = (d.v === 'visual' && d.needVa && !(typeof va !== 'undefined' && va.on));
    var html = '<div class="as-item' + (on ? ' on' : '') + (greyed ? ' greyed' : '') + '" data-as="' + d.v + '">' +
      '<input type="checkbox" ' + (on ? 'checked' : '') + (greyed ? ' disabled' : '') + '>' +
      '<span class="ai-n">' + d.n + '</span>' +
      (d.isNew ? '<span class="visual-tag">视觉断言</span>' : '') +
      '<span class="ai-d">' + d.d + '</span></div>';
    if (on) {
      var p = '';
      if (d.v === 'exists') p = '<label>等待秒数<input type="number" value="' + esc(r.wait == null ? 3 : r.wait) + '" data-af="wait"></label>';
      if (d.v === 'text') p = '<label>期望文本<input value="' + esc(r.text == null ? '' : r.text) + '" data-af="text" placeholder="如：写新歌"></label>';
      if (d.v === 'toast') p = '<label class="wide">Toast 文本<input value="' + esc(r.toast == null ? '' : r.toast) + '" data-af="toast" placeholder="如：已加入歌单"></label>';
      if (d.v === 'text_page') p = '<label class="wide">期望文本（页面包含即可）<input value="' + esc(r.text == null ? '' : r.text) + '" data-af="text" placeholder="如：发布成功"></label>';
      if (d.v === 'text_page_gone') p = '<label class="wide">期望消失的文案<input value="' + esc(r.text == null ? '' : r.text) + '" data-af="text" placeholder="如：已删除的歌曲名"></label>';
      if (d.v === 'gone') p = '<label>等待秒数<input type="number" value="' + esc(r.wait == null ? 2 : r.wait) + '" data-af="wait"></label>';
      if (d.v === 'visual') {
        var vaOn = (typeof va !== 'undefined' && va.on);
        var hasAsset = !!(r.asset);
        var th = (r.threshold == null ? 0.95 : +r.threshold);
        if (!vaOn) {
          p = '<div class="as-hint" style="color:var(--muted,#9ca3af)">🔒 视觉资产需先在左侧开启「视觉断言」采集模式（当前关闭，不可勾选）</div>';
        } else {
          p = '<label>相似度阈值（低于阈值判失败）<div class="thresh"><input type="range" min="0.8" max="1" step="0.01" value="' + th + '" data-af="threshold">' +
              '<span class="val" id="asTv">' + th.toFixed(2) + '</span></div></label>' +
              '<div><button class="btn" id="asCapBtn" style="font-size:11.5px;padding:5px 14px;width:100%">' +
              (hasAsset ? '🔄 重新采集视觉资产' : '📷 采集图片（跳转视觉断言采集）') + '</button></div>' +
              (hasAsset
                ? '<div class="va-shot-wrap" style="position:relative;display:inline-block;margin-top:6px">' +
                  '<img id="vaShotThumb" src="' + (r.thumbnail || '') + '" style="max-width:150px;max-height:88px;border-radius:8px;border:1px solid var(--line,#dcdfe6);cursor:zoom-in">' +
                  '<span id="vaShotX" title="移除已采集图片" style="position:absolute;top:-8px;right:-8px;width:20px;height:20px;border-radius:50%;background:#EF4444;color:#fff;font-size:11px;line-height:20px;text-align:center;cursor:pointer">✕</span>' +
                  '<div class="as-hint">资产「' + esc(r.asset) + '」已采集（点击图片放大）</div></div>'
                : '<div class="as-hint">勾选后点上方按钮：暂时关闭本弹窗，在右侧「视觉断言采集」设置参数并保存，保存后自动回到本弹窗（已填内容保留）</div>');
        }
      }
      html += '<div class="as-param' + (d.v === 'visual' ? ' as-param--visual' : '') + '" data-pv="' + d.v + '">' + p + '</div>';
    }
    return html;
  }).join('');
  box.querySelectorAll('.as-item').forEach(function (it) {
    it.addEventListener('click', function (e) {
      if (e.target.tagName === 'INPUT' && e.target.type === 'checkbox') e.stopPropagation();
      var v = it.dataset.as, r = findAssert(v);
      if (v === 'visual' && !(typeof va !== 'undefined' && va.on)) {
        showToast('视觉断言未开启：请先点左侧「视觉断言」开启采集模式', false);
        return;
      }
      if (r) state.modalAsserts = assertState().filter(function (x) { return x.v !== v; });
      else {
        r = Object.assign({ v: v }, ASSERT_KINDS.find(function (k) { return k.v === v; }).p);
        state.modalAsserts.push(r);
      }
      renderAssertCol(); syncAssertSide();
    });
  });
  box.querySelectorAll('[data-af]').forEach(function (inp) {
    inp.addEventListener('input', function () {
      var r = findAssert(inp.closest('.as-param').dataset.pv);
      r[inp.dataset.af] = inp.type === 'range' ? +inp.value : inp.value;
      if (inp.type === 'range') document.getElementById('asTv').textContent = (+inp.value).toFixed(2);
      if (opCommentAuto) $('el-op-comment').value = autoStepComment(currentOpType(), opElementLabel(), $('el-op-param').value);
    });
  });
  var cap = box.querySelector('#asCapBtn');
  if (cap) cap.addEventListener('click', function () {
    var r = findAssert('visual');
    if (!r) return;
    if (!(typeof va !== 'undefined' && va.on)) { showToast('请先在左侧开启「视觉断言」', false); return; }
    // 视觉资产采集流程：暂时关闭本弹窗（字段保留，回来即回显），右侧已是视觉断言采集面板
    state.vaCapture = {
      active: true,
      caseFile: (function () {
        var cf = $('el-case-file').value;
        return (cf && cf !== '__new__') ? cf : (($('el-case-new').value || '').trim() ? 'test_' + newCaseBase() + '.py' : '');
      })(),
      threshold: (r.threshold == null ? 0.95 : +r.threshold),
    };
    $('modal-mask').style.display = 'none';
    // 选中元素列切换为采集面板（设参数、保存视觉断言）；面板状态由 va 对象保持
    va.panelActive = true;
    $('detail').style.display = 'none';
    vaRenderPanel();
    showToast('请在右侧「视觉断言采集」设置参数并点「保存视觉断言」，完成后自动回到本弹窗');
  });
  // 采集图片缩略图：点击放大（lightbox）；右上角 ✕ = 移除已采集
  var thumb = box.querySelector('#vaShotThumb');
  if (thumb) thumb.addEventListener('click', function () {
    var lb = document.getElementById('va-shot-lightbox');
    if (lb) { document.getElementById('vaShotBig').src = thumb.src; lb.style.display = 'flex'; }
  });
  var shotX = box.querySelector('#vaShotX');
  if (shotX) shotX.addEventListener('click', function () {
    var r = findAssert('visual');
    if (r) { r.asset = ''; r.thumbnail = ''; renderAssertCol(); }
  });
}


/* 断言副作用：特殊操作时断言卡置灰（无断言语义） */
function syncAssertSide() {
  var sp = !!$('el-op-special').value;
  ['asArea', 'asLabel'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.classList.toggle('locked', sp);
  });
  var row = document.querySelector('.as-switch-row');
  if (row) row.classList.toggle('locked', sp);
  renderAssertCol();
  followStepDesc();
}
/* 当前生效的操作类型：特殊操作优先，否则用常规操作类型下拉 */
function currentOpType() { return $('el-op-special').value || $('el-op-type').value || ''; }

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

/* 视觉断言采集保存成功 → 自动回到添加测试用例弹窗（字段原样回显），把资产回填断言区 */
function vaCaptureReturn(assetName, thumbnail) {
  var cap = state.vaCapture || {};
  if (!cap.active) return false;
  state.vaCapture = { active: false, assetName: assetName, thumbnail: thumbnail };
  var r = findAssert('visual');
  if (!r) {
    r = Object.assign({ v: 'visual' }, ASSERT_KINDS.find(function (k) { return k.v === 'visual'; }).p);
    state.modalAsserts.push(r);
  }
  r.asset = assetName;
  r.thumbnail = thumbnail;
  $('modal-mask').style.display = 'flex';   // 不走 openModal：字段原样回显
  // 采集完成：选中元素列还原为元素详情（va 仍开启；下次点「采集」再切面板）
  va.panelActive = false;
  $('visualPanel').style.display = 'none';
  if (state.selNode) { $('detail').style.display = 'block'; renderDetail(state.selNode); }
  renderAssertCol(); syncAssertSide();
  showToast('视觉资产「' + assetName + '」已采集保存，请继续配置断言');
  return true;
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
  // 设备切换下拉迁到顶栏右上角（独立使用时；内嵌模式仍由 setupEmbedBar 走 embed-bar）。
  // dev-info 状态文本不再入顶栏——下拉已含同份信息（型号·系统·serial），重复展示去掉
  if (el && !document.documentElement.classList.contains('embedded')) {
    const group = document.createElement('span');
    group.className = 'dev-group gnav-dev';
    const tag = document.createElement('span');
    tag.className = 'bar-label';
    tag.textContent = '📱 设备';
    group.appendChild(tag);
    const sel = $('device-sel');
    if (sel) group.appendChild(sel);
    el.appendChild(group);
    const foot = document.querySelector('.side-foot');
    if (foot) foot.style.display = 'none';   // 节点已迁走/不再展示，侧栏底部空壳隐藏
  }
}

async function init() {
  renderTopNav();
  setupEmbedBar();
  // 先加载设备下拉并确定 state.serial（恢复上次选中），status/refresh 都按它请求
  await loadDevices();
  const st = await fetch('api/status?serial=' + encodeURIComponent(state.serial || '')).then(r => r.json()).catch(() => null);
  const devInfo = $('dev-info');
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
  bindAssertToggle();
  $('btn-modal-cancel').addEventListener('click', () => {
    $('modal-mask').style.display = 'none';
  });
  $('btn-modal-save').addEventListener('click', () => onSaveElement(false));
  $('btn-modal-save-continue').addEventListener('click', () => onSaveElement(true));
  const bdr = $('btn-debug-run');
  if (bdr) bdr.addEventListener('click', debugRun);   // 🔍 调试：临时用例真机执行
  // 树 Diff 开关 / 定位器体检 / 会话步骤撤销
  initDialog();
  $('btn-tree-diff').addEventListener('click', toggleTreeDiff);
  $('btn-tree-diff').classList.toggle('on', state.treeDiffOn);   // 默认开，初始即高亮
  $('btn-coord-mode').addEventListener('click', toggleCoordMode);
  $('btn-visual-mode').addEventListener('click', vaToggleMode);
  // 采集图片放大层：点击遮罩/✕ 关闭
  const vaLb = $('va-shot-lightbox');
  if (vaLb) {
    vaLb.addEventListener('click', function () { vaLb.style.display = 'none'; });
    $('vaShotBigX').addEventListener('click', function (e) { e.stopPropagation(); vaLb.style.display = 'none'; });
  }
  const sideToggle = $('side-toggle');
  if (sideToggle) sideToggle.addEventListener('click', () => {
    const off = document.body.classList.toggle('side-collapsed');
    sideToggle.title = off ? '展开菜单' : '收起菜单';
  });
  vaBindShotDrag();
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
  $('el-op-comment').addEventListener('input', () => { renderStepsList(currentSteps()); });
  $('el-case-file').addEventListener('change', onCaseFileChange);
  // 切换用例方法：插入位置/步骤列表按新方法重建（此前残留上一方法的步骤——真 bug，v6.15.40 修复）
  $('el-case-method').addEventListener('change', () => {
    const steps = currentSteps();
    renderInsertPos(steps, false);
    renderStepsList(steps);
  });
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
  // 新建用例的页面选择：新建（随包生成）或复用已有页面（页面方法追加进该文件），
  // 选已有页面时元素文件自动对齐其绑定的元素文件
  const pageNewSel = $('el-page-new');
  if (pageNewSel) pageNewSel.addEventListener('change', () => {
    $('el-page-file').value = isNewPageSel()
      ? (pkgBase() ? capFirst(pkgBase()) + 'Page.py（随用例包新建）' : '（输入用例名后自动派生）')
      : pkgPageSelValue();
    syncNewCaseElFile();
  });
  // 目标页面切换（已有用例·多页面 v6.15.33）：元素文件对齐所选页面绑定的元素文件
  const pageFileSel = $('el-page-file');
  if (pageFileSel) pageFileSel.addEventListener('change', () => {
    if (isNewCase() || purposeValue() !== 'all') return;
    const pe = selectedPageElementsFile();
    const sel = $('el-file');
    if (pe && !isNewElementFile()) {
      if (!Array.from(sel.options).some(o => o.value === pe)) sel.add(new Option(pe, pe));
      sel.value = pe;
      setElLinkNote('🔗 页面 ' + pageFileSel.value + ' 绑定元素文件 ' + pe + '，「写入元素文件」已自动对齐'
        + (state.pageElements && !((state.caseFiles || []).filter(c => c.file === $('el-case-file').value)
            .some(c => (c.page_targets || []).some(t => t.page_file === pageFileSel.value)))
          ? '；⚠ 这条用例还没用到该页面，点「保存」后自动接进去（自动补 import 和初始化代码），不用手动改用例' : ''));
    } else if (pe) {
      setElLinkNote('🔗 页面 ' + pageFileSel.value + ' 绑定元素文件 ' + pe);
    } else {
      setElLinkNote('🔗 页面 ' + pageFileSel.value + '（未绑定元素文件，元素将写入所选文件并补 import）');
    }
    fillCaseHead();
  });
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
  // 栏宽默认交给 CSS（三栏 30/30/40 屏幕自适应，v6.14.81）；拖拽时才写内联 flex（仅本次会话生效）
  try { localStorage.removeItem('locator_col_widths'); } catch (e) {}
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
          // 右栏固定 700（v6.14.23），中栏 flex:1 吸收差值
          const rightW = right.getBoundingClientRect().width || 700;
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
  // 横排单行：型号 · 系统版本 · 设备ID（顶栏右上角设备组，不再分两行）
  return '📱 ' + esc(device.model) + ' · Android ' + esc(device.platformVersion) +
    ' · <span class="dev-id" title="设备ID（adb serial）">' + esc(serial || '') + '</span>';
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
/* ---------- 刷新/重启按钮读秒徽标 ----------
   点击开始逐秒计时，接口返回即停表（成功/失败都停——失败不收敛秒会一直走），2s 内渐隐移除。
   计时状态挂在按钮元素上：_timerInterval 为计时句柄，_timerToken 记录归属的刷新序号，
   过期响应（token 已被更新的刷新覆盖）的 finally 不会误停新一次的计时。 */
function btnTimerStart(btn) {
  if (btn._timerInterval) { clearInterval(btn._timerInterval); btn._timerInterval = null; }
  const old = btn.querySelector('.btn-timer');
  if (old) old.remove();
  const t = document.createElement('span');
  t.className = 'btn-timer';
  t.textContent = '0s';
  btn.appendChild(t);                                    // 文字（.bt-tx）右侧
  const started = Date.now();
  btn._timerToken = refreshSeq;
  btn._timerInterval = setInterval(() => {
    t.textContent = Math.floor((Date.now() - started) / 1000) + 's';
  }, 1000);
}
function btnTimerStop(btn) {
  if (btn._timerInterval) { clearInterval(btn._timerInterval); btn._timerInterval = null; }
  const t = btn.querySelector('.btn-timer');
  if (!t) return;
  t.classList.add('fade');                               // CSS：1.2s 渐隐，1.5s 后移除节点（整体 <2s）
  setTimeout(() => t.remove(), 1500);
}
/* fast=true ⚡刷新：单次 dump 最快路径；fast=false ♻ 重启：完整自愈链（可重启 adb） */
async function refresh(fast = false) {
  const myToken = ++refreshSeq;
  const btn = $(fast ? 'btn-refresh' : 'btn-restart');
  const other = $(fast ? 'btn-restart' : 'btn-refresh');
  btn.querySelector('.bt-tx').textContent = fast ? '刷新中…' : '重启中…'; btn.disabled = true; other.disabled = true;
  btnTimerStart(btn);
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
    // 过期响应（期间已发起更新的刷新/切换）不动按钮态与读秒——由最新一次的 finally 收尾
    if (myToken === refreshSeq) {
      btn.querySelector('.bt-tx').textContent = fast ? '刷新' : '重启';
      btn.disabled = false; other.disabled = false;
      btnTimerStop(btn);
    }
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
/* ================= 视觉断言采集模式（三范围 + 忽略区域 + Layout + 业务类型） ================= */
/* 状态机：va.on 模式开关；scope=element/region/screen；region 框选设备坐标；
   ignores 相对视觉区域左上角存（执行侧裁剪出区域图后直接可用，元素位移时随区域整体平移）。 */
var va = { on: false, panelActive: false, scope: 'element', match: 'strict', region: null, ignores: [], ignoreArmed: false,
           preview: null, els: {} };

function vaShotRect() { return $('shot').getBoundingClientRect(); }
function vaDevicePoint(e) {
  const img = $('shot'), r = img.getBoundingClientRect();
  if (r.width <= 0) return null;
  const natW = img.naturalWidth || state.width, natH = img.naturalHeight || state.height;
  return [Math.round((e.clientX - r.left) / r.width * natW),
          Math.round(Math.min((e.clientY - r.top) / r.height * natH, state.height))];
}
function vaScreenBox(box) {   // 设备坐标 [x,y,w,h] → 截图上 div 的 left/top/w/h
  const img = $('shot');
  const k = img.clientWidth / state.width;
  return { l: img.offsetLeft + box[0] * k, t: img.offsetTop + box[1] * k,
           w: box[2] * k, h: box[3] * k };
}
function vaClearRects() {
  document.querySelectorAll('.va-rect, .va-ignore').forEach(el => el.remove());
}
function vaDrawRects() {
  vaClearRects();
  const host = $('shot-wrap');
  if (!host) return;
  const box = vaTargetBox();   // 当前视觉区域（设备坐标）
  if (box) {
    const d = document.createElement('div');
    d.className = 'va-rect';
    const s = vaScreenBox(box);
    d.style.cssText = `left:${s.l}px;top:${s.t}px;width:${s.w}px;height:${s.h}px`;
    d.innerHTML = '<span class="va-tag">视觉区域</span>';
    host.appendChild(d);
  }
  const o = vaTargetOrigin();
  va.ignores.forEach((ig, i) => {
    const d = document.createElement('div');
    d.className = 'va-ignore';
    const s = vaScreenBox([o[0] + ig[0], o[1] + ig[1], ig[2], ig[3]]);
    d.style.cssText = `left:${s.l}px;top:${s.t}px;width:${s.w}px;height:${s.h}px`;
    d.innerHTML = '<span class="va-tag">忽略' + (i + 1) + '</span>';
    host.appendChild(d);
  });
}
function vaTargetBox() {   // 视觉区域设备坐标：element=选中元素 bounds；region=框选；screen=null(全屏)
  if (va.scope === 'region') return va.region;
  if (va.scope === 'element') {
    const b = state.selNode && (state.selNode._bounds || state.selNode.bounds_num);
    if (b && b.length === 4) return [b[0], b[1], b[2] - b[0], b[3] - b[1]];
  }
  return null;
}
function vaTargetOrigin() {
  if (va.scope === 'region' && va.region) return [va.region[0], va.region[1]];
  const b = vaTargetBox();
  return b ? [b[0], b[1]] : [0, 0];
}
function vaCollect() {   // 面板 → API 参数
  const c = {
    scope: va.scope,
    biz_type: $('va-biz').value,
    match_mode: va.match || 'strict',
    threshold: Math.min(1, Math.max(0.5, (parseFloat($('va-th').value) || 98) / 100)),
    ignore_regions: va.ignores,
  };
  if (va.scope === 'element') {
    const rid = (state.selNode && state.selNode['resource-id']) || '';
    c.locator_type = 'ID';
    c.locator_value = rid;
  }
  if (va.scope === 'region' && va.region) c.region = va.region;
  return c;
}
function vaRenderPanel() {
  const p = $('visualPanel');
  if (!p) return;
  p.style.display = 'block';
  /* V5 渐变强调（design_vacl/V5_SPEC.md）：渐变描边卡 + 红琥珀绿三色小节 + 分段控件 */
  p.innerHTML = `
    <div class="va5-card"><div class="va5-in">
      <div class="va5-hd"><span class="t">🧪 视觉断言采集</span><span class="hint">基线比对</span></div>
      <div class="field"><label>名称 <b style="color:#e34d4d">*</b></label>
        <input id="va-name" placeholder="如：登录成功用户卡片"></div>
      <div class="va5-sec"><span class="va5-dot r"></span>断言范围</div>
      <div class="va5-seg" id="va-scope-seg">
        <button data-v="element">元素</button><button data-v="region">自定义区域</button><button data-v="screen">整屏</button>
      </div>
      <div class="hint" id="va-scope-hint"></div>
      <div class="va5-sec"><span class="va5-dot a"></span>比对参数</div>
      <div class="field"><label>视觉对象类型 <span class="hint" style="display:inline">（仅用于资产分类管理）</span></label>
        <select id="va-biz">${['region|普通区域','icon|Icon','logo|Logo','image|图片','card|卡片','banner|Banner','toast|Toast','popup|弹窗','custom|自定义'].map(o=>{const [v,n]=o.split('|');return `<option value="${v}">${n}</option>`}).join('')}</select>
        <div class="hint" id="va-biz-hint"></div></div>
      <div class="field"><label>比较模式</label>
        <div class="va5-seg" id="va-match-seg">
          <button data-v="strict">Strict（像素）</button><button data-v="layout">Layout（布局）</button>
        </div>
        <div class="hint">Strict 逐像素比对；Layout 缩成粗粒度结构图比对——文字/数字变化不敏感，位置与尺寸变化敏感</div></div>
      <div class="field"><label>相似度阈值（% · 默认 98）</label>
        <input id="va-th" type="number" min="50" max="100" step="1" value="98"></div>
      <div class="va5-sec"><span class="va5-dot g"></span>忽略与预览</div>
      <div class="field"><button class="ghost mini" id="va-add-ignore">＋ 添加忽略区域</button>
        <div class="hint" id="va-ignore-hint">点击后回到左侧截图，在视觉区域内拖拽一块</div>
        <div class="va-chips" id="va-chips"></div></div>
      <div class="field"><label>基线预览</label>
        <div id="va-preview" class="muted" style="font-size:12px">点「预览」实时截图按范围裁剪确认</div></div>
      <div class="detail-foot" style="justify-content:flex-start">
        <button class="btn small" id="va-preview-btn">预览</button>
        <button class="btn small primary" id="va-save-btn">保存视觉断言</button>
      </div>
    </div></div>`;
  const syncSeg = (segId, val) => {
    const seg = $(segId);
    seg.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === val));
  };
  // 名称自动预填（可改）：空名称点保存只会收到「名称必填」提示，从根上消除矛盾反馈
  if (!$('va-name').value.trim()) {
    var _base = (va.scope === 'element' && state.selNode && state.selNode['resource-id'])
      ? state.selNode['resource-id'].split('/').pop()
      : ({ element: '元素', region: '区域', screen: '整屏' })[va.scope] || '视觉';
    $('va-name').value = _base + '_' + new Date().toTimeString().slice(0, 8).replace(/:/g, '');
  }
  syncSeg('va-scope-seg', va.scope);
  syncSeg('va-match-seg', va.match);
  $('va-scope-seg').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b || b.dataset.v === va.scope) return;
    va.scope = b.dataset.v; va.ignores = []; va.region = null;   // 与旧 radio 语义一致：换范围清空框选与忽略
    syncSeg('va-scope-seg', va.scope);
    vaRenderChips(); vaDrawRects(); vaSyncHints();
  });
  $('va-match-seg').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    va.match = b.dataset.v;
    syncSeg('va-match-seg', va.match);
  });
  $('va-biz').addEventListener('change', vaSyncHints);
  $('va-add-ignore').addEventListener('click', () => {
    if (!vaTargetBox()) { showToast('请先选定视觉区域（选元素或框选区域）'); return; }
    va.ignoreArmed = true;
    $('va-ignore-hint').textContent = '🟡 已进入忽略框选：在左侧截图的视觉区域内拖拽一块（点面板任意处取消）';
    showToast('在左侧截图上拖拽出忽略区域');
  });
  $('va-preview-btn').addEventListener('click', async () => {
    const err = vaValidate(false);
    if (err) { showToast(err); return; }
    $('va-preview').textContent = '截图中…';
    const r = await fetch('api/visual_asset/preview', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(vaCollect()) })
      .then(x => x.json()).catch(() => null);
    if (!r || !r.ok) { $('va-preview').textContent = '❌ ' + ((r && r.msg) || '预览失败'); return; }
    $('va-preview').innerHTML = `<img class="va5-pv" src="${r.thumb}">` +
      `<div class="muted" style="font-size:11.5px;margin-top:4px">${r.size[0]}×${r.size[1]} px</div>`;
  });
  $('va-save-btn').addEventListener('click', async () => {
    const err = vaValidate(true);
    if (err) { showToast(err); return; }
    const body = Object.assign({ name: $('va-name').value.trim() }, vaCollect());
    // 所属用例绑定：从添加用例弹窗跳转采集时，记录当前目标用例（视觉断言管理列表「所属用例」列）
    if (state.vaCapture && state.vaCapture.active && state.vaCapture.caseFile) body.case_name = state.vaCapture.caseFile;
    const r = await fetch('api/visual_asset/save', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(x => x.json()).catch(() => null);
    showToast((r && r.msg) || (r && r.ok ? '视觉断言已保存' : '保存失败'), r && r.ok);
    if (r && r.ok) {
      // 视觉资产采集链：从「添加测试用例」弹窗跳转而来 → 回填资产并自动恢复弹窗（字段原样回显）
      var cap = state.vaCapture;
      if (cap && cap.active) {
        var assetName = $('va-name').value.trim() || (cap.assetName || '');
        var thumb = (r.asset && r.asset.thumb) || '';
        vaCaptureReturn(assetName, thumb);
        $('va-name').value = '';
        return;
      }
      $('va-name').value = '';
    }
  });
  vaSyncHints(); vaRenderChips();
}
function vaValidate(needName) {
  if (needName && !$('va-name').value.trim()) return '名称必填';
  if (va.scope === 'element') {
    const rid = (state.selNode && state.selNode['resource-id']) || '';
    if (!state.selNode) return '元素范围：请先在左侧截图点击选择元素';
    if (!rid) return '该元素无 resource-id——建议改用「自定义区域」框选';
  }
  if (va.scope === 'region' && !va.region) return '自定义区域：请在左侧截图上拖拽框选';
  return null;
}
function vaSyncHints() {
  const hints = {
    element: '点击左侧截图中的元素（蓝框=当前视觉区域）',
    region: '在左侧截图上按住拖拽框选（可重复框选，后者覆盖前者）',
    screen: '无需选择——保存时截取整屏；忽略区域可叠加多个',
  };
  if ($('va-scope-hint')) $('va-scope-hint').textContent = hints[va.scope] || '';
  const biz = $('va-biz') && $('va-biz').value;
  if ($('va-biz-hint')) $('va-biz-hint').textContent = biz === 'toast'
    ? 'Toast 类型：先让 Toast 出现在屏幕上，再框选它的区域保存' : '';
}
function vaRenderChips() {
  const box = $('va-chips');
  if (!box) return;
  box.innerHTML = va.ignores.map((ig, i) =>
    `<span class="va-chip">忽略${i + 1} (${ig[0]},${ig[1]},${ig[2]}×${ig[3]}) <b data-vaig="${i}">✕</b></span>`).join('');
  box.querySelectorAll('[data-vaig]').forEach(b => b.addEventListener('click', () => {
    va.ignores.splice(+b.dataset.vaig, 1); vaRenderChips(); vaDrawRects();
  }));
}
function vaToggleMode() {
  va.on = !va.on;
  document.body.classList.toggle('va-mode', va.on);
  const btn = $('btn-visual-mode');
  if (btn) { btn.querySelector('.bt-tx').textContent = va.on ? '视觉断言：开' : '视觉断言：关'; btn.classList.toggle('on', va.on); }
  if (va.on) {
    if (state.coordMode) $('btn-coord-mode').click();   // 与坐标模式互斥
    if ($('modal-mask').style.display !== 'none') renderAssertCol();   // 弹窗开着：视觉资产勾选项即时解禁
    // 开启不动选中元素列：详情照常显示，采集面板只在点「采集」时才切换过来
    va.panelActive = false;
    $('visualPanel').style.display = 'none';
    if (state.selNode) { $('detail').style.display = 'block'; renderDetail(state.selNode); }
    va.scope = 'element'; va.match = 'strict'; va.region = null; va.ignores = []; va.ignoreArmed = false;
    vaDrawRects();
    showToast('视觉断言已开启：点选元素正常查看详情；在添加用例弹窗勾选「视觉资产」后点采集');
  } else {
    va.panelActive = false;
    $('visualPanel').style.display = 'none';
    vaClearRects();
    if (state.selNode) $('detail').style.display = '';
    if ($('modal-mask').style.display !== 'none') renderAssertCol();   // 弹窗开着：视觉资产勾选项即时置灰
  }
}
/* 截图拖拽框选：region 范围主框 + 忽略区域追加框 */
function vaBindShotDrag() {
  const wrap = $('shot-wrap');
  if (!wrap || wrap.dataset.vaBound) return;
  wrap.dataset.vaBound = '1';
  let drag = null;
  wrap.addEventListener('mousedown', (e) => {
    if (!va.on || e.button !== 0) return;
    if (!(va.scope === 'region' || va.ignoreArmed || (e.target.id === 'shot'))) return;
    const pt = vaDevicePoint(e);
    if (!pt) return;
    e.preventDefault();
    drag = { x0: pt[0], y0: pt[1], el: document.createElement('div') };
    drag.el.className = va.ignoreArmed ? 'va-ignore' : 'va-rect';
    drag.el.style.opacity = '.6';
    wrap.appendChild(drag.el);
    document.body.classList.add('va-dragging');
    // 每次按下都挂一次收尾监听（finish 收尾后自移除）——只挂一次的话，首次 mouseup
    // 就把监听消费掉，之后所有拖拽永远无法收尾（va.region 不赋值 = 自定义区域失效）
    document.addEventListener('mouseup', finish);
  });
  // move/up 挂 document：拖拽中鼠标冲出截图区也能持续跟踪（快速拖拽必踩 wrap 丢事件）
  const onMove = (e) => {
    if (!drag) return;
    const pt = vaDevicePoint(e);
    if (!pt) return;
    const x = Math.min(drag.x0, pt[0]), y = Math.min(drag.y0, pt[1]);
    const w = Math.abs(pt[0] - drag.x0), h = Math.abs(pt[1] - drag.y0);
    const s = vaScreenBox([x, y, w, h]);
    drag.el.style.cssText = `left:${s.l}px;top:${s.t}px;width:${s.w}px;height:${s.h}px`;
    drag.box = [x, y, w, h];
  };
  const finish = () => {
    if (!drag) return;
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', finish);
    document.body.classList.remove('va-dragging');
    drag.el.remove();
    const b = drag.box;
    drag = null;
    if (!b || b[2] < 8 || b[3] < 8) { if (va.ignoreArmed) showToast('框选太小，已忽略'); return; }
    if (va.ignoreArmed) {           // 忽略区域：裁到视觉区域内并转相对坐标
      const o = vaTargetOrigin(), box = vaTargetBox();
      let ix = Math.max(b[0], o[0]), iy = Math.max(b[1], o[1]);
      let ix2 = Math.min(b[0] + b[2], o[0] + (box ? box[2] : state.width));
      let iy2 = Math.min(b[1] + b[3], o[1] + (box ? box[3] : state.height));
      if (ix2 - ix < 4 || iy2 - iy < 4) { showToast('忽略区域须在视觉区域内部'); return; }
      va.ignores.push([ix - o[0], iy - o[1], ix2 - ix, iy2 - iy]);
      va.ignoreArmed = false;
      $('va-ignore-hint') && ($('va-ignore-hint').textContent = '点击后回到左侧截图，在视觉区域内拖拽一块');
      vaRenderChips();
    } else {
      va.region = b;
    }
    vaDrawRects(); vaCapSyncScopeTxt && vaCapSyncScopeTxt();
  };
  wrap.addEventListener('mousemove', onMove);
  document.addEventListener('mousemove', onMove);
  // mouseup 收尾监听改在 mousedown 时挂（finish 自移除）——见上方 mousedown 处注释
}


function onShotClick(e) {
  // 视觉断言采集模式：点选元素确定断言范围
  if (va.on) {
    const rr = hitFromEvent(e);
    if (rr && rr.hit) selectNode(rr.hit.uid);
    return;
  }
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
  if (va.on && va.panelActive) {
    // 采集面板占据选中元素列：点选截图只更新视觉范围（蓝框随选中元素走），不切回详情
    vaDrawRects();
    return;
  }
  $('detail').style.display = 'block';
  if (va.on) vaDrawRects();   // 视觉断言开启：视觉区域蓝框随选中元素刷新
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
  state.eleReferenced = r.referenced || [];   // 已被页面对象 import 的元素文件（「活文件」）
  // v6.15.33：新建元素文件改到自动化后台（平台用例上传）——弹窗只在已有文件里选
  $('el-file').innerHTML = r.files.map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('');
}
async function loadPages() {
  const r = await fetch('api/pages').then(r => r.json()).catch(() => null);
  if (!r || !r.ok) return;
  state.pages = r.pages || [];
  state.elementsAll = r.elements || {};
  state.pageElements = r.page_elements || {};   // 页面文件 → 绑定的元素文件（新建用例复用页面时对齐）
}
async function openModal() {
  // ⌖ 坐标模式：选了精确坐标即可打开（不需要树里有选中元素）
  const coordPick = state.coordMode && state.coordPoint;
  if (!state.selNode && !coordPick) { uiAlert('请先在截图或元素树里选中一个元素（或开启坐标模式点选坐标）'); return; }
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
  $('el-wait-sec').value = 2;
  $('el-result').className = 'el-result'; $('el-result').textContent = '';
  $('el-content').textContent = '';
  // 写入文件默认定位器自己的元素库文件（避免误写进框架自带文件；② 会在选目标用例后自动对齐）
  resetNewFileInputs();
  $('el-file').value = state.defaultEleFile || 'locator_gui_elements.py';
  // 用途默认：直接选②（三件套一次完成：选已有用例或新建都可以）
  document.querySelector('input[name="el-purpose"][value="all"]').checked = true;
  onPurposeChange();   // 栏位显示复位（上次若用了用途③，弹窗栏要藏回、三件套栏恢复）
  $('el-op-type').innerHTML = opTypeOptions();
  $('el-op-type').value = 'click';
  $('el-op-type').disabled = false;
  $('el-op-special').value = '';   // 特殊操作每次打开复位为「无」
  ['el-name', 'el-type', 'el-value', 'el-cn-name'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.disabled = false;
  });
  resetAssertToggle();              // 断言开关复位：关 + 清空勾选
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
  const psel = $('el-page-new'); if (psel) psel.value = '__new__';   // 页面选择复位为「新建」
}
/* 当前是否新建用例（选择器值为 __new__ 或元素文件为 __new__） */
function isNewCase() { return $('el-case-file').value === NEW_FILE_OPT; }
function isNewElementFile() { return $('el-file').value === NEW_FILE_OPT; }
/* 新用例基础名（test_ 后面的部分）：非法字符过滤；同时派生元素文件名。
   容错：用户常把「完整文件名」填进输入框（test_xxx.py / xxx.py），这里统一剥掉
   test_ 前缀与 .py 后缀，避免二次包装成 test_test_xxx_py.py 这类畸形文件名。 */
function newCaseBase() {
  let v = ($('el-case-new').value || '').trim();
  v = v.replace(/\.py$/i, '');              // 剥 .py（放前面，避免 . 被过滤成 _）
  v = v.replace(/^test_/i, '');             // 剥 test_ 前缀（前缀由 newCaseFileName 统一补）
  return v.replace(/[^A-Za-z0-9_]/g, '_');
}
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
  return r ? r.value : 'all';
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
/* 用例方法/插入位置联动：按所选方法重建插入位置选项。
   preservePos=true（用例重入，如同用例切操作类型）保留已选位置；
   false（切换用例方法）重置为末尾——不同方法的步骤序列不同，位置语义不延续（v6.15.40） */
function renderInsertPos(steps, preservePos) {
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
    if (preservePos && curPos !== '' && curPos !== null && parseInt(curPos, 10) <= steps.length) {
      posSel.value = curPos;
    } else {
      posSel.value = '0';
      if (preservePos && curPos !== '' && curPos !== null && curPos !== '0') showToast('原插入位置超出当前方法步骤数，已改为末尾');
    }
  }
}
function insertPos() {
  if ($('el-insert-pos').value === 'front') return 'front';   // 第 1 步之前（首启弹窗类操作锁定）
  return parseInt($('el-insert-pos').value, 10) || 0;
}
function newStepNo() { const p = insertPos(); if (p === 'front') return 1; return p > 0 ? p + 1 : currentSteps().length + 1; }
function renderStepsList(steps) {
  const box = $('el-steps-list');
  if (!box) return;
  if (!$('el-case-method').value) { box.innerHTML = ''; box.style.display = 'none'; return; }
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
  $('btn-coord-mode').classList.toggle('on', state.coordMode);
  showToast(state.coordMode ? '开启成功' : '已关闭');
}

/* 分段控件选中态同步：程序赋值 checked 不触发 change，统一在这里刷 .on 类 */
function syncSegClasses() {
  document.querySelectorAll('.seg-group .seg').forEach(lb => {
    lb.classList.toggle('on', lb.querySelector('input').checked);
  });
}

function onPurposeChange() {
  syncSegClasses();
  let p = purposeValue();
  const tb = $('tri-bar');
  if (tb) tb.style.display = p === 'popup' ? 'none' : '';   // 弹窗规则库：无三件套落点
  // 特殊操作必须写用例（不写元素库），用途不允许停在「仅元素」
  if (false && $('el-op-special').value) {   // 旧「仅元素」互斥已随该用途移除
    document.querySelector('input[name="el-purpose"][value="all"]').checked = true;
    p = 'all';
  }
  const popup = p === 'popup';
  $('col-popup').style.display = popup ? '' : 'none';
  ['col-element', 'col-case', 'col-op'].forEach(id => {
    $(id).style.display = popup ? 'none' : '';
  });
  // 用途 = 元素+用例+操作（all）或登记随机弹窗（popup）；popup 只亮①栏
  $('col-element').classList.remove('dim');
  $('col-case').classList.toggle('dim', popup);
  $('col-op').classList.toggle('dim', popup);
  if (popup) { ppPrefill(); loadPopupRules(); return; }
  onOpTypeChange(); onCaseFileChange();
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
/* 操作下拉分组渲染（见名知意：基本操作 / 长流程·等待与分支） */
/* 四栏改版：③操作只留动作类（4 种传统断言移至④栏，组合断言走开关勾选） */
const OP_HIDDEN = ['assert_visible', 'assert_text', 'assert_toast', 'assert_gone'];
function visibleOpTypes() {
  // v2 类型（v6.15.33 手势/设备）依赖新后端 /api/cases 的 step_types 放行：
  // 老后端（未重启实例）不返回该字段 → 隐藏，界面自动降级为旧操作集，互不影响
  return STEP_TYPES.filter(t => OP_HIDDEN.indexOf(t.v) < 0
    && (!t.v2 || !state.stepTypes || state.stepTypes.indexOf(t.v) >= 0));
}
function opTypeInfo(v) { return stepTypeInfo(v); }
function opTypeOptions() {
  const groups = [];
  visibleOpTypes().forEach(t => {
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
  /* 步骤描述实时拼接：操作类型 + 元素中文名（+ 参数）随输入即时刷新；手输过描述(opCommentAuto=false)则不覆盖。
     同时刷新②栏步骤预览（断言勾选/元素名/参数变化都要同步）——修复预览滞留旧内容 */
  if (opCommentAuto) {
    $('el-op-comment').value = autoStepComment(currentOpType(), opElementLabel(), $('el-op-param').value) + assertsDescSuffix();
  }
  renderStepsList(currentSteps());
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

/* ④断言栏：描述后缀（· 含N断言） */
function assertsDescSuffix() {
  const n = assertState().length;
  return n ? ('· 含' + n + '断言') : '';
}

function onOpTypeChange() {
  const noAssert = currentOpType() === 'sleep' || currentOpType() === 'custom';
  const tg = $('asToggle');
  if (tg) {
    tg.disabled = noAssert;
    if (noAssert && tg.checked) { tg.click(); showToast('固定等待/自定义代码步骤不支持挂断言，已自动关闭'); }
  }
  const special = $('el-op-special').value;
  const t = opTypeInfo(currentOpType());
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
  syncAssertSide();   // ④断言栏：特殊操作时置灰；描述跟随重算
  updateOpNote();
}

/* 特殊操作下拉：选中 → 常规操作类型禁用、用途强制②（必须写用例）、元素栏禁用；
   取消（选「无」）→ 全部恢复。deal_first_launch_dialogs 的插入位置锁定由 onCaseFileChange 处理 */
function onSpecialOpChange() {
  syncAssertSide();
  const isSpecial = !!$('el-op-special').value;
  // 特殊操作不写元素库：元素栏置灰（防误以为名称参与保存）；与代码注释声明一致
  ['el-name', 'el-type', 'el-value', 'el-cn-name'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.disabled = isSpecial;
  });
  // 操作类型的禁用改由 applyOpMutual 视觉互斥承担（物理 disabled 会造成两侧都无法切回的死锁）
  if (isSpecial && purposeValue() !== 'all') {
    document.querySelector('input[name="el-purpose"][value="all"]').checked = true;
    onPurposeChange();
  }
  onOpTypeChange();
  onCaseFileChange();
}
/* 目标用例的页面文件（来自 /api/cases 的三件套归属信息） */
function targetPageInfo() {
  const f = $('el-case-file').value;
  const info = (state.caseFiles || []).find(c => c.file === f && c.page_file);
  return info || null;
}
/* ---- 目标用例文件 + 方法（两级联动；③ 时元素文件自动对齐页面引用的元素文件） ---- */
async function loadCaseFiles() {
  const r = await fetch('api/cases').then(r => r.json()).catch(() => null);
  if (!r || !r.ok) return;
  state.caseFiles = r.case_info || [];
  state.stepTypes = r.step_types || null;   // 能力探测：老后端无此字段 → v2 操作隐藏（v6.15.33）
  const sel = $('el-case-file');
  const cur = sel.value;
  /* 用例文件下拉：有中文名映射的显示「中文名（文件名）」（与平台选择用例同步） */
  const cnMap = {};
  (state.caseFiles || []).forEach(c => { if (c.cn_name && !cnMap[c.file]) cnMap[c.file] = c.cn_name; });
  const files = [];
  (state.caseFiles || []).forEach(c => { if (files.indexOf(c.file) < 0) files.push(c.file); });
  // v6.15.33：新建用例文件改到自动化后台（平台用例上传）——弹窗只在已有用例里选
  sel.innerHTML = files.map(f => '<option value="' + esc(f) + '">' +
    esc(cnMap[f] ? cnMap[f] + '（' + f + '）' : f) + '</option>').join('');
  // 预选：用户已显式选中的有效用例 > 第一个
  if (cur && files.indexOf(cur) >= 0) sel.value = cur;
  else if (files.length) sel.value = files[0];
  onCaseFileChange();
}
function pkgPageSelValue() { const s = $('el-page-new'); return s ? s.value : '__new__'; }
function isNewPageSel() { return pkgPageSelValue() === '__new__' || !pkgPageSelValue(); }
function updatePkgTrio() {
  /* 新建用例模式：回显三件套落点（新页面=全部随包生成；已有页面=页面方法追加进该文件） */
  const el = $('pkg-trio');
  if (!el) return;
  if (!isNewCase()) { el.textContent = ''; return; }
  if (!pkgBase()) { el.textContent = '输入用例名后，用例 / 页面 / 元素 文件名自动派生（元素文件可改选已有共享文件）'; return; }
  if (isNewPageSel()) {
    el.textContent = '将生成：test_' + pkgBase() + '.py · ' + pkgPageFileName() + ' · '
      + (isNewElementFile() ? pkgElementFileName() : $('el-file').value);
  } else {
    const pe = (state.pageElements || {})[pkgPageSelValue()] || '';
    el.textContent = '将生成 test_' + pkgBase() + '.py；页面方法追加到 ' + pkgPageSelValue()
      + (pe ? '（元素 → ' + pe + '，同定位自动复用原名）' : '');
  }
}
/* 新建用例模式下对齐「写入元素文件」：
   选了已有页面 → 元素文件强制对齐该页面绑定的元素文件（静态绑定，服务端也会校验）；
   新建页面 → 保留用户选择（默认随包新建，可改选已有共享文件，同定位自动复用原名） */
function syncNewCaseElFile() {
  const sel = $('el-file');
  if (isNewPageSel()) {
    setElLinkNote(isNewElementFile()
      ? '🔗 元素将写入新文件 ' + (pkgElementFileName() || '（输入用例名后自动派生）')
      : '🔗 元素将写入已有文件 ' + sel.value + '（新页面 import 该文件；同定位自动复用原名，不覆盖原定义）');
    updatePkgTrio();
    return;
  }
  const pe = (state.pageElements || {})[pkgPageSelValue()] || '';
  if (pe) {
    if (!Array.from(sel.options).some(o => o.value === pe)) sel.add(new Option(pe, pe));
    sel.value = pe;
    $('el-file-new-wrap').style.display = 'none';
    setElLinkNote('🔗 页面 ' + pkgPageSelValue() + ' 绑定元素文件 ' + pe
      + '，「写入元素文件」已自动对齐（同定位复用原名，不覆盖原定义）');
  } else {
    setElLinkNote('⚠ 页面 ' + pkgPageSelValue() + ' 未绑定元素文件——元素将写入所选文件并由页面补 import');
  }
  updatePkgTrio();
}

function syncElFileNote() {
  /* 手动改「写入元素文件」时如实提示：与所选页面绑定的元素文件不一致 → 保存时会自动同步过去（同名覆盖），
     不再留着上次「已自动对齐」的过期提示让人生疑 */
  const f = $('el-case-file').value;
  const infos = (state.caseFiles || []).filter(c => c.file === f);
  const info = infos.find(c => c.page_file);
  if (purposeValue() !== 'all' || isNewElementFile() || !info) return;
  const pe = selectedPageElementsFile();
  if (!pe) return;
  if ($('el-file').value !== pe) {
    setElLinkNote('⚠ 「写入元素文件」(' + $('el-file').value + ') 与页面 ' + $('el-page-file').value + ' 绑定的 ' +
                  pe + ' 不一致——保存时会自动把元素同步到 ' + pe + '（同名覆盖，不影响保存）');
  }
}

function onCaseFileChange() {
  // 新建用例：切换到「新建输入模式」——方法/插入位置无意义；页面可选新建或复用已有页面，
  // 元素文件默认随包新建、也可改选已有共享文件（不再强制与用例同态，v6.15.30）
  const newCase = isNewCase();
  const psel = $('el-page-new');
  $('el-case-new-wrap').style.display = newCase ? '' : 'none';
  $('el-case-method').disabled = newCase;
  $('el-insert-pos').disabled = newCase;
  if (psel) psel.style.display = newCase ? '' : 'none';
  $('el-page-file').style.display = newCase ? 'none' : '';
  if (newCase) {
    if (psel) {
      const cur = psel.value;
      psel.innerHTML = '<option value="__new__">➕ 新建页面文件…（随用例包生成）</option>'
        + (state.pages || []).map(p => '<option value="' + esc(p) + '">' + esc(p) + '</option>').join('');
      psel.value = (cur && cur !== '__new__' && (state.pages || []).indexOf(cur) >= 0) ? cur : '__new__';
    }
    $('el-page-file').value = isNewPageSel()
      ? (pkgBase() ? capFirst(pkgBase()) + 'Page.py（随用例包新建）' : '（输入用例名后自动派生）')
      : pkgPageSelValue();
    updatePkgTrio();
    syncNewCaseElFile();
    fillCaseHead();
    renderStepsList([]);
    return;
  }
  // 页面下拉的清空/重建统一交给下方 targets 块（先取 curPageSel 再重建，保留用户选择）
  updatePkgTrio();
  fillCaseHead();
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
  renderInsertPos(steps, true);
  renderStepsList(steps);
  // 三件套联动：写入元素文件 ← 所选页面绑定的元素文件（必须一致）
  // 写入页面文件 = 下拉（v6.15.33 多页面）：该用例已实例化的页面（self.page/page2…）任选，
  // 选未实例化的页面保存时自动挂接（补 import + self.pageN 实例化）；老后端无 page_targets
  // 时降级为单选项展示，行为与旧版一致
  const p = purposeValue();
  const info = infos.find(c => c.page_file);
  const amb = infos.find(c => (c.page_ambiguous || []).length);
  const pfsel = $('el-page-file');
  const targets = [];
  infos.forEach(c => (c.page_targets || []).forEach(t => {
    if (!targets.some(x => x.page_file === t.page_file)) targets.push(t);
  }));
  // 先取用户当前选中再重建：同用例内的重入（切操作类型等）保留页面选择；
  // 切换目标用例则重置——旧选择属于旧用例的页面，不能带过来（E2E 两次实测教训）
  const curPageSel = (state._pageSelCase === f) ? pfsel.value : '';
  state._pageSelCase = f;
  if (targets.length) {
    pfsel.innerHTML = targets.map(t => '<option value="' + esc(t.page_file) + '">'
      + esc(t.page_file + '（self.' + t.var + '）') + '</option>').join('')
      + (state.pages || []).filter(pf => !targets.some(t => t.page_file === pf))
        .map(pf => '<option value="' + esc(pf) + '">' + esc(pf + '（用例还没用到·保存自动接入）') + '</option>').join('');
    if (curPageSel && Array.from(pfsel.options).some(o => o.value === curPageSel)) {
      pfsel.value = curPageSel;
    } else {
      pfsel.value = targets[0].page_file;
    }
  } else if (info && info.page_file) {
    pfsel.innerHTML = '<option value="' + esc(info.page_file) + '">' + esc(info.page_file) + '</option>';
  } else {
    pfsel.innerHTML = (state.pages || []).map(pf => '<option value="' + esc(pf) + '">' + esc(pf + '（用例还没用到·保存自动接入）') + '</option>').join('');
  }
  if (amb) {
    setElLinkNote('⚠ 页面类 ' + amb.page_class + ' 在多个文件里重名：' + amb.page_ambiguous.join('、')
                  + '——归属不唯一，已禁止写入页面方法，请先改名或删除重名文件');
  } else if (!targets.length && !info) {
    setElLinkNote('这条用例还没有任何页面——在「写入页面文件」里选一个，保存时自动接进用例（自动补 import 和初始化代码）');
  } else if (p === 'all') {
    const pe = selectedPageElementsFile();
    if (pe) {
      if ($('el-file').value !== pe) {
        const sel = $('el-file');
        // 下拉里没有该文件时 set value 会静默失效（提示却说已对齐）——缺选项就先补上
        if (!Array.from(sel.options).some(o => o.value === pe)) {
          sel.add(new Option(pe, pe));
        }
        sel.value = pe;
        setElLinkNote('🔗 页面 ' + pfsel.value + ' 绑定元素文件 ' + pe + '，「写入元素文件」已自动对齐');
      } else {
        setElLinkNote('🔗 三件套去向：页面 ' + pfsel.value + ' ← 元素文件 ' + pe);
      }
    } else {
      setElLinkNote('🔗 页面 ' + pfsel.value + '（未绑定元素文件，元素将写入所选文件并补 import）');
    }
  } else {
    setElLinkNote('');
  }
}
/* 所选目标页面（写入页面文件下拉）绑定的元素文件：先查用例已实例化页面（page_targets），
   再查全局页面→元素映射；都没有返回 '' */
function selectedPageElementsFile() {
  const pf = $('el-page-file').value;
  if (!pf) return '';
  const cfs = (state.caseFiles || []).filter(c => c.file === $('el-case-file').value);
  for (let i = 0; i < cfs.length; i++) {
    const t = (cfs[i].page_targets || []).find(t => t.page_file === pf);
    if (t) return t.elements_file || '';
  }
  return (state.pageElements || {})[pf] || '';
}
/* 保存：按「用途」单选分流 —— ① 仅保存到元素库 / ② 保存并追加到目标用例方法 */
/* 保存：按「保存到哪一步」分流 ① 仅元素 / ② +用例 / ③ +操作；
 * continueMode=true（保存并继续）= 保存后回到定位器，开启连续添加（点下一个元素自动弹本窗） */
/* ---------- 保存测试用例包（新建用例文件场景）：一次生成三件套 ----------
   用例/页面/元素三个完整文件由前端按框架风格组装，后端 /api/save_case_package
   与平台同进程直调用例管理入库（语法校验、备份、登记一条龙）；
   局域网访问者可选「下载用例包 zip」交由平台「用例管理 → 上传用例包」入库。 */
function pkgBase() { return newCaseBase(); }
function pkgElementFileName() {
  const raw = ($('el-file-new').value || '').trim().replace(/\.py$/i, '');  // 先剥 .py（过滤会把 . 变 _）
  const v = raw.replace(/[^A-Za-z0-9_]/g, '_');
  const b = pkgBase();
  const stem = v || (b ? b + 'Elements' : '');
  if (!stem) return '';
  // 元素文件名必须以 Elements 结尾（页面/用例生成逻辑依赖该后缀判定归属）：
  // 用户漏写或写成单数 Element 时自动规范化，.py 后缀同样自动补
  const norm = stem.replace(/elements?$/i,'') + 'Elements';   // 大小写不敏感归一（防止 xxx_elementsElements.py）
  return norm + '.py';
}
function pkgPageFileName() { const b = pkgBase(); return b ? b + 'Page.py' : ''; }   // 小写文件名（与元素文件派生风格统一）；类名仍驼峰
function pkgStepComment() { return $('el-op-comment').value.trim() || genStepDesc(currentStepObj()); }
function currentStepObj() {
  const obj = { type: currentOpType(), element: $('el-name').value.trim() || '<元素名>', param: $('el-op-param').value.trim() };
  if (!$('el-op-special').value && assertState().length) {
    obj.asserts = assertState().map(a => Object.assign({}, a));
  }
  return obj;
}
/* 用例包三件套的文件内容由后端 assemble_case_package 权威组装（v6.15.30）：
   前端只传意图（用例名/步骤/元素/落点选择），查重复用与页面复用统一在后端做，
   原前端 pkgFiles()/pkgMethodBlock() 双源实现已删除，落点预览走 updatePkgTrio。 */
/* ---------- 调试（临时用例真跑，v6.14.107） ----------
   当前操作 + 勾选断言 → 服务端临时生成一条单步用例 → 现有 runner 真机执行 → 轮询取临时结果。
   临时数据：用例跑完自动删除；结果只在页面临时展示，不入元素库/不入用例。 */
var debugPolling = false;

function collectDebugPayload() {
  return {
    serial: state.serial,
    locator_type: $('el-type').value,
    locator_value: $('el-value').value,
    wait_type: $('el-wait').value,
    wait_sec: $('el-wait-sec').value,
    op_type: currentOpType(),
    param: $('el-op-param').value,
    asserts: assertState().map(function (r) {
      return { type: r.v, wait: r.wait, text: r.text, toast: r.toast, threshold: r.threshold, asset: r.asset };
    }),
  };
}

async function debugRun() {
  if (debugPolling) return;
  const btn = $('btn-debug-run'), box = $('debug-result');
  const payload = collectDebugPayload();
  debugPolling = true;
  btn.disabled = true;
  box.style.display = 'block';
  box.innerHTML = '<div class="dbg-line">⏳ 正在生成临时用例并提交真机执行…（约 20~40s）</div>';
  try {
    const r = await fetch('api/debug_run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(x => x.json()).catch(() => null);
    if (!r || !r.ok) {
      box.innerHTML = '<div class="dbg-line err">✕ ' + esc((r && r.msg) || '调试提交失败') + '</div>';
      return;
    }
    const deadline = Date.now() + 180000;   // 3 分钟兜底
    while (Date.now() < deadline) {
      await new Promise(res => setTimeout(res, 2500));
      const s = await fetch('api/debug_result?token=' + encodeURIComponent(r.token)
        + '&run_id=' + encodeURIComponent(r.run_id)).then(x => x.json()).catch(() => null);
      if (!s || !s.ok) { box.innerHTML = '<div class="dbg-line err">✕ 调试状态查询失败</div>'; return; }
      if (s.state === 'running') {
        box.innerHTML = '<div class="dbg-line">⏳ 真机执行中…（Appium 会话 + 单步用例）</div>';
        continue;
      }
      renderDebugResult(s, box);
      if (payload.op_type) refresh(true);   // 操作真跑了：刷新画面立刻看到效果
      return;
    }
    box.innerHTML = '<div class="dbg-line err">✕ 调试超时（3 分钟未完成）——到「执行用例」页查看任务状态</div>';
  } finally {
    debugPolling = false;
    btn.disabled = false;
  }
}

function renderDebugResult(s, box) {
  const rs = s.results;
  if (!rs) {
    box.innerHTML = '<div class="dbg-line err">✕ 任务已结束(' + esc(s.task_status || '未知')
      + ')但未取到调试结果——到「执行用例」页看日志定位原因</div>';
    return;
  }
  let html = '';
  if (rs.op) {
    html += '<div class="dbg-line ' + (rs.op.ok ? 'ok' : 'err') + '">'
      + (rs.op.ok ? '✓ 操作成功' : '✕ 操作失败') + ' · ' + esc(rs.op.desc)
      + (rs.op.error ? '：' + esc(rs.op.error) : '') + '</div>';
  }
  (rs.asserts || []).forEach(function (a) {
    html += '<div class="dbg-line ' + (a.ok ? 'ok' : 'err') + '">'
      + (a.ok ? '✓ ' : '✕ ') + esc(a.name || a.kind)
      + (a.detail ? '：' + esc(a.detail) : '') + '</div>';
  });
  html += '<div class="dbg-line dbg-meta">临时用例已删除 · 结果为临时数据不入库'
    + (s.run_id ? ' · <a href="#" id="dbg-report-link">查看完整报告</a>' : '') + '</div>';
  box.innerHTML = html;
  const link = $('dbg-report-link');
  if (link) link.addEventListener('click', function (e) {
    e.preventDefault();
    fetch('/api/run/' + s.run_id + '/report/open', { method: 'POST' })
      .then(x => x.json()).then(j => {
        if (j && j.ok && j.url) window.open(j.url, '_blank');
        else showToast((j && j.msg) || '报告打开失败', false);
      });
  });
}

async function onSaveElement(continueMode) {
  // 防重入：上一笔保存未完成（含确认框挂起）时拒绝新保存——并发保存会互相污染状态/丢步骤
  if (state._saving) { showToast('上一步保存还在进行，请稍候…', false); return; }
  state._saving = true;
  try {
    return await _doSaveElement(continueMode);
  } finally {
    state._saving = false;
    document.getElementById('btn-modal-save').disabled = false;
    document.getElementById('btn-modal-save-continue').disabled = false;
  }
}
async function _doSaveElement(continueMode) {
  const purpose = purposeValue();
  if (!purpose) return;
  // 用途③：登记随机弹窗——写规则库，与元素库/用例三件套完全无关
  if (purpose === 'popup') { await savePopupRule(continueMode); return; }
  const special = $('el-op-special').value;   // 特殊操作：不碰元素库，只写用例
  // v6.15.33 v2 设备操作（按键/前后台/开关）无元素主体：跳过元素名/定位校验与元素入库
  const _opT0 = $('el-op-type').value;
  const noElOp = !special && stepTypeInfo(_opT0).v2 && !stepTypeInfo(_opT0).el;
  let name = special ? '' : $('el-name').value.trim();
  if (purpose === 'all') {   // popup 已在入口分流；旧「仅元素」用途已移除
    // v6.15.30：新建用例支持「复用已有元素文件 / 复用已有页面」，不再强制两下拉同态；
    // 合法性由保存时服务端统一校验（已有页面 → 元素文件必须为其绑定文件，此处自动对齐）
    // 必填字段统一校验（保存失败后弹窗字段可能被重置——缺字段时生成残缺代码
    // def : / Locator_Type. 让后端语法校验兜底，不如在这里明确提示）
    if (!special) {
      const missing = [];
      if (!noElOp && !name) missing.push('元素名（左侧点选元素或手填）');
      if (!noElOp && !$('el-type').value) missing.push('定位方式');
      if (!noElOp && !$('el-value').value.trim()) missing.push('定位值');
      if (!$('el-op-type').value) missing.push('操作类型');
      if (missing.length) {
        showElResult('⚠️ 请补齐必填项：' + missing.join('、'), false);
        return;
      }
      // 数字类参数格式校验：非数字会被后端拦截，但前端先拦体验更直接
      const opT = $('el-op-type').value, pVal = $('el-op-param').value.trim();
      if (opT === 'sleep' && pVal && isNaN(parseFloat(pVal))) {
        showElResult('⚠️ 固定等待秒数需为数字（示例：3 或 1.5），收到：' + pVal, false); return;
      }
      if (opT === 'tap') {
        const xy = pVal.split(',').map(x => x.trim());
        if (xy.length !== 2 || xy.some(x => x === '' || isNaN(parseFloat(x)))) {
          showElResult('⚠️ 坐标点击参数需为 x,y 数字格式（示例：320,540），收到：' + pVal, false); return;
        }
      }
      if ((opT === 'press_keycode' || opT === 'background_app') && pVal && !/^-?\d+$/.test(pVal)) {
        showElResult('⚠️ 按键码/后台秒数需为整数（示例：4；后台 -1=停用），收到：' + pVal, false); return;
      }
      if (opT === 'drag_to' && !pVal) {
        showElResult('⚠️ 拖拽需填目标元素名（须已保存在元素库）', false); return;
      }
      if (opT === 'activate_app' && !pVal) {
        showElResult('⚠️ 拉起应用需填应用包名（如 com.recordlife.kuaige）', false); return;
      }
      // 自定义代码原样写入用例（不转义），落盘前二次确认
      if (opT === 'custom' && pVal) {
        if (!await uiConfirm('自定义代码将原样写入用例文件（不经过任何转义），请确认内容安全：\n\n' + pVal)) return;
      }
    }
    // 新建用例（填写了自定义文件名）：首次「保存并继续/保存」即三件套（元素+用例+页面，
    // 已含当前步骤）直接入库——v6.15.30 起由服务端权威组装：元素查重复用（同定位复用原名
    // 不写重复行 / 同名异定位硬拦）+ 页面复用（已有页面方法 upsert、用例 import 已有页面类）
    if (isNewCase()) {
      if (!pkgBase()) { showElResult('请先输入新用例名（test_ 后面的部分）', false); return; }
      if (!special && !name) { showElResult('元素名称不能为空', false); return; }
      if (state.tempCase && state.tempCase.base !== pkgBase()) {
        if (!confirm('上次录制会话是「' + state.tempCase.base + '」。换用例名将切换会话，继续？')) return;
      }
      // 页面/元素落点：已有页面 → 元素文件强制对齐其绑定文件（与服务端校验同规则）
      const pageNew = isNewPageSel();
      const pageFile = pageNew ? pkgPageFileName() : pkgPageSelValue();
      let elFile = isNewElementFile() ? pkgElementFileName() : $('el-file').value;
      let elNew = isNewElementFile();
      if (!pageNew) {
        const pe = (state.pageElements || {})[pageFile] || '';
        if (pe && elFile !== pe) { elFile = pe; elNew = false; }
      }
      const tc = state.tempCase = { base: pkgBase() };
      const stepObj = currentStepObj();
      stepObj.comment = pkgStepComment();
      const waitSec = parseInt($('el-wait-sec').value, 10);
      const payload = {
        package: tc.base,
        assemble: true,
        cn_name: ($('el-case-cn').value || '').trim(),
        uploader: special ? 'locator' : name,
        step: stepObj,
        element: special ? null : {
          name: name,
          locator_type: $('el-type').value,
          value: $('el-value').value.trim(),
          wait_type: $('el-wait').value,
          wait_seconds: (isNaN(waitSec) || waitSec < 1) ? '' : waitSec,
          cn_name: $('el-cn-name').value.trim(),
        },
        element_file: elFile,
        element_file_new: elNew,
        page_file: pageFile,
        page_file_new: pageNew,
      };
      const r = await fetch('api/save_case_package', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then(x => x.json()).catch(() => null);
      if (!r || !r.ok) { showElResult('用例包保存失败：' + ((r && r.msg) || '服务异常'), false); return; }
      // 查重复用：回填库内元素名，后续步骤继续引用同一元素定义
      if (r.element_final) $('el-name').value = r.element_final;
      const noteMsg = (r.notes || []).join('；');
      showToast(noteMsg ? ('保存成功 · ' + noteMsg.slice(0, 90)) : (continueMode ? '请继续添加用例' : '保存成功'));
      // 本步已随三件套写入 → 切回已有文件模式（回显用例/页面/元素文件），后续步骤走 add_code 追加
      await loadCaseFiles();
      const cfSel = $('el-case-file');
      cfSel.value = 'test_' + tc.base + '.py';
      if (cfSel.value !== 'test_' + tc.base + '.py') cfSel.value = NEW_FILE_OPT;   // 选项缺失兜底（防下拉空白）
      onCaseFileChange();
      $('modal-mask').style.display = 'none';
      return;
    }
    // 都选已有文件 → 继续走「元素入库 + 追加用例行」（下方既有流程）
  }
  // 选②：前置校验用例栏（保存元素前就拦住，避免元素入库了代码却追加不了）
  let caseFile = '', methodName = '';
  if (purpose === 'all') {
    caseFile = $('el-case-file').value;
    methodName = $('el-case-method').value;
    if (!(state.caseFiles || []).some(c => c.file === caseFile)) {
      showElResult('请选择目标用例文件（新建用例请到自动化后台「用例管理 → ＋新建用例」，创建后重开本窗即可选到）', false); return;
    }
    if (!methodName) { showElResult('请选择页面操作', false); return; }
  }
  // 同名（同文件）覆盖确认：防止误覆盖已有元素（特殊操作不碰元素库，整段跳过）
  const fname = $('el-file').value;
  if (!special && !noElOp && name && (state.elementsAll[fname] || []).indexOf(name) >= 0) {
    if (!await uiConfirm('元素库文件 ' + fname + ' 里已有同名元素「' + name + '」，保存将覆盖更新原定义。\n\n' +
      '点「确定」= 覆盖更新\n点「取消」= 不保存')) return;
  }
  // 仅元素模式落点防呆（v6.15.30）：写入未被任何页面对象 import 的文件 → 元素静默失效
  if (false && name && !noElOp && !(state.eleReferenced || []).includes(fname)) {   // 旧「仅元素」防呆已随该用途移除
    if (!await uiConfirm('「' + fname + '」没有被任何页面对象 import，元素保存后不会在任何用例中生效（静默失效）。\n\n' +
      '建议：改用「元素+用例+操作」用途，元素会自动写入目标页面绑定的元素文件。\n仍要保存到该文件？')) return;
  }
  // 按需求：添加测试用例不判断重复——同名直接覆盖、同定位直接新增，元素照常入库
  let r = (special || noElOp) ? { ok: true, msg: '' } : await saveElement(true);
  if (!r) return;
  if (!r.ok && r.duplicate) {
    // 同定位已有元素：推荐复用（避免同定位多元素条目）；跨文件复用会破坏页面静态绑定，仅提示不自动切
    if (r.duplicate.filename === fname) {
      const reuse = await uiConfirm(
        '已存在相同定位的元素「' + r.duplicate.name + '」（' + r.duplicate.filename + '）。\n\n' +
        '点「确定」= 使用已有元素「' + r.duplicate.name + '」继续（推荐，避免重复条目）\n' +
        '点「取消」= 仍要新建/覆盖当前名称「' + name + '」', { okText: '使用已有元素' });
      if (reuse) {
        $('el-name').value = r.duplicate.name;
        name = r.duplicate.name;
        r = { ok: true, msg: '复用已有元素 ' + r.duplicate.name };
      } else {
        r = await saveElement(false);   // 用户坚持新建（同名走覆盖确认）/覆盖
      }
    } else {
      showElResult('⚠️ 相同定位已存在于元素文件 ' + r.duplicate.filename + '（元素「' +
        r.duplicate.name + '」），与本页引用的 ' + fname + ' 不同文件——请改用已有元素名或修改定位值', false);
      return;
    }
  }
  if (!r) return;
  if (!r.ok) { showElResult(r.msg || '元素保存失败', false); return; }
  let savedName = (special || noElOp) ? '' : name;

  const finishContinue = () => {
    $('modal-mask').style.display = 'none';
    // 不自动弹窗：用户自由点选元素查看，点「添加测试用例」再录下一步（用例/方法预选已保持）
    showToast('保存成功，请继续添加用例');
    // 下拉刷新延后到 toast 显示之后，避免与蒙层关闭、toast 出现同帧挤占渲染
    setTimeout(() => { loadPages(); loadLibraryFiles(); loadCaseFiles(); }, 260);
  };

  // purpose ②/③：追加一步代码到目标用例方法体末尾（③ 同时生成/更新页面方法）
  const step = {
    type: special || $('el-op-type').value,   // 特殊操作优先（不依赖元素）
    element: savedName,
    element_file: (special || noElOp) ? '' : fname,  // 元素刚保存进的文件（元素不在页面引用文件时后端优先从这复制）
    param: $('el-op-param').value.trim(),
    desc: '',
    comment: $('el-op-comment').value.trim(),        // 操作备注 → 页面方法 docstring
    case_comment: $('el-op-comment').value.trim(),   // 步骤描述 → 追加行上方注释（与弹窗所见一致）
  };
  const comboObj = currentStepObj();               // ④断言栏：组合断言随保存下发（特殊操作时不带）
  if (!special && comboObj.asserts && comboObj.asserts.length) {
    step.asserts = comboObj.asserts;
  }
  const res = $('el-result');
  res.className = 'el-result'; res.textContent = purpose === 'all'
    ? '元素已保存，正在追加用例代码 + 生成页面操作…'
    : '元素已保存，正在追加用例代码…';
  const cr = await fetch('api/add_code', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_file: caseFile, method_name: methodName, step: step,
                           gen_page_method: purpose === 'all' ? 1 : 0,
                           insert_after_step: insertPos(),
                           page_file: $('el-page-file').value || '' }),
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
  // 二次确认：采集会解析当前页全部节点并生成候选，误触成本高
  if (!window.confirm('确认采集当前页面全部元素？\n（将解析当前屏幕全部节点 → 过滤去重 → 生成候选清单）')) return;
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
const OP_GRID_TYPES = visibleOpTypes().map(t => t.v);   // 动作类铺满图标卡（4种传统断言移至④栏）
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
    const t = opTypeInfo(v);
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
    '用例行 → ' + ($('el-case-file').value === NEW_FILE_OPT ? '新建 ' + ($('el-case-new').value || '?') : ($('el-case-file').value || '—')),
    '页面方法 → ' + ($('el-page-file').value || '选择用例后带出'),
    '元素 → ' + ($('el-file').value || '—'),
  ];
  const bar = $('tri-bar');
  bar.textContent = '🛡 点保存后三件一起写入：' + parts.join(' · ');
  bar.style.display = purposeValue() === 'popup' ? 'none' : '';
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


