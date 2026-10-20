/* ================= 视觉断言日志 · 三级页（/visual-logs） =================
   无左侧菜单，顶部 PlatformNav 面包屑（首页 / APP自动化 / 视觉断言日志）。
   数据源：执行用例时 appOperator._va_log_write 落盘的
   output/visual_logs/records.jsonl + imgs/（后端 /api/appui/visual_logs）。
   本页自含初始化，不依赖 app.js（避免牵连其未发布改动）。 */
(function () {
  'use strict';

  var $ = function (s) { return document.querySelector(s); };
  var page = 1, size = 20;
  var SCOPE_CN = { element: '元素', region: '框选区域', screen: '整屏' };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function imgUrl(fn) { return '/api/appui/visual_logs/img/' + encodeURIComponent(fn); }

  function toast(msg, ok) {
    var t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'show' + (ok === false ? ' err' : '');
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.className = ''; }, 2400);
  }

  function load() {
    var q = new URLSearchParams();
    var scope = $('#vlScope').value, ok = $('#vlResult').value, kw = $('#vlSearch').value.trim();
    if (scope) q.set('scope', scope);
    if (ok !== '') q.set('ok', ok);
    if (kw) q.set('kw', kw);
    q.set('page', page); q.set('size', size);
    fetch('/api/appui/visual_logs?' + q.toString())
      .then(function (x) { return x.json(); })
      .then(function (r) {
        if (!r || !r.ok) { toast((r && r.msg) || '加载失败', false); return; }
        render(r);
      })
      .catch(function () { toast('加载失败（网络异常）', false); });
  }

  function render(r) {
    var rows = r.records || [];
    $('#vlTbody').innerHTML = rows.map(function (rec) {
      var im = rec.imgs || {};
      var badge = rec.ok
        ? '<span style="color:var(--ok,#16803c);font-weight:500">无差异</span>'
        : '<span style="color:var(--danger,#b42318);font-weight:500">有差异</span>';
      var th = rec.threshold;
      var thTxt = (th == null || th === '') ? '—' : Math.round(parseFloat(th) * 100) + '%';
      var errTxt = rec.err ? '<div class="muted" style="max-width:260px;white-space:normal;font-size:12px">' + esc(rec.err) + '</div>' : '';
      return '<tr>' +
        '<td class="muted">' + esc(rec.time || '—') + '</td>' +
        '<td><b>' + esc(rec.name || '—') + '</b></td>' +
        '<td>' + (rec.case ? esc(rec.case) : '<span class="muted">—</span>') + '</td>' +
        '<td>' + (SCOPE_CN[rec.scope] || esc(rec.scope || '—')) + '</td>' +
        '<td>' + (rec.match_mode === 'layout' ? '结构·忽略细节' : '像素级·严格') + '</td>' +
        '<td>' + (im.baseline
          ? '<img class="as-thumb" src="' + imgUrl(im.baseline) + '" data-full="' + imgUrl(im.baseline) + '" data-cap="基线图 · ' + esc(rec.name) + '" title="点击查看大图">'
          : '<span class="muted">—</span>') + '</td>' +
        '<td>' + (im.actual
          ? '<img class="as-thumb" src="' + imgUrl(im.actual) + '" data-full="' + imgUrl(im.actual) + '" data-cap="对比图 · ' + esc(rec.name) + '" title="点击查看大图">'
          : '<span class="muted">—</span>') + '</td>' +
        '<td>' + badge + ' ' + (im.triple
          ? '<img class="as-thumb" src="' + imgUrl(im.triple) + '" data-full="' + imgUrl(im.triple) + '" data-cap="三联图 · ' + esc(rec.name) + '" title="点击查看差异三联图">'
          : errTxt || '') + '</td>' +
        '<td>' + thTxt + '</td>' +
        '</tr>';
    }).join('') || '<tr><td colspan="9" class="empty">暂无记录——跑用例触发视觉断言后自动生成</td></tr>';
    $('#vlPagerInfo').textContent = '共 ' + r.total + ' 条';
    $('#vlPageNow').textContent = r.page + ' / ' + r.pages;
    $('#btnVlPrev').disabled = r.page <= 1;
    $('#btnVlNext').disabled = r.page >= r.pages;
    bindThumbs();
  }

  function bindThumbs() {
    $('#vlTbody').querySelectorAll('.as-thumb').forEach(function (img) {
      img.addEventListener('click', function () {
        $('#vlViewerImg').src = img.dataset.full;
        $('#vlViewerCap').textContent = img.dataset.cap || '';
        $('#vlViewer').classList.add('show');
      });
    });
  }

  /* ---------- 初始化：顶部面包屑（左上角路径）+ 事件绑定 + 首载 ---------- */
  if (window.PlatformNav) {
    PlatformNav.render(document.getElementById('sidebar'), '/run', '', ['视觉断言', '视觉断言日志']);
  }
  ['vlScope', 'vlResult'].forEach(function (id) {
    document.getElementById(id).addEventListener('change', function () { page = 1; load(); });
  });
  $('#vlSearch').addEventListener('input', function () { page = 1; load(); });
  $('#vlPageSize').addEventListener('change', function () {
    size = parseInt(this.value, 10) || 20; page = 1; load();
  });
  $('#btnVlReset').addEventListener('click', function () {
    $('#vlSearch').value = ''; $('#vlScope').value = ''; $('#vlResult').value = '';
    page = 1; load();
  });
  $('#btnVlRefresh').addEventListener('click', load);
  $('#btnVlPrev').addEventListener('click', function () { page--; load(); });
  $('#btnVlNext').addEventListener('click', function () { page++; load(); });
  $('#vlViewerX').addEventListener('click', function () { $('#vlViewer').classList.remove('show'); });
  $('#vlViewer').addEventListener('click', function (e) {
    if (e.target === this) this.classList.remove('show');
  });
  load();
})();
