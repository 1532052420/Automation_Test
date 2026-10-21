/* 服务管理面板（方案 D：右下角悬浮球 + 右侧抽屉）
   ------------------------------------------------------------------
   能力：服务体检（运行状态 / 陈旧实例 / 未登记占用判定）、启动停止、清理、重启/关闭平台。
   术语：健康=ok · 陈旧实例=stale（启动早于当前版本）· 未登记占用=unreg（占端口但不在清单）· 已停止=off。
   数据源：/api/services/inspect、/api/services/cleanup、/api/services/toggle、/api/service/restart。
   15s 周期体检，抽屉打开时即时刷新。 */
(function () {
  'use strict';

  var LEVEL_LABEL = { ok: '健康', stale: '陈旧实例', unreg: '未登记占用', off: '已停止' };
  var _timer = null;

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* 忽略 */ }
    document.body.removeChild(ta);
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function ensureDom() {
    if (document.getElementById('svcFab')) return;
    var fab = document.createElement('button');
    fab.id = 'svcFab';
    fab.className = 'svc-fab';
    fab.title = '服务管理：体检 / 清理 / 启停';
    fab.innerHTML = '<span class="svc-fab-ic">⚙</span><span class="svc-fab-tx">服务</span>';
    document.body.appendChild(fab);

    var mask = document.createElement('div');
    mask.id = 'svcMask';
    mask.className = 'svc-mask';
    mask.innerHTML =
      '<div class="svc-drawer" role="dialog" aria-label="服务管理面板">' +
      '  <div class="svc-drawer-hd">' +
      '    <h3>服务管理</h3>' +
      '    <span class="svc-badges" id="svcBadges"></span>' +
      '    <button type="button" class="svc-btn ghost" id="svcBtnInspect">🩺 体检</button>' +
      '    <button type="button" class="svc-btn ghost" id="svcBtnClose">✕</button>' +
      '  </div>' +
      '  <div class="svc-notice" id="svcNotice" hidden><span id="svcNoticeText"></span><button type="button" class="svc-notice-copy" id="svcNoticeCopy">复制修复命令</button></div>' +
      '  <div class="svc-list" id="svcList"></div>' +
      '  <div class="svc-drawer-ft">' +
      '    <button type="button" class="svc-btn danger-ghost" id="svcBtnCleanup">🧹 清理陈旧实例与未登记占用</button>' +
      '    <span class="svc-ft-sep"></span>' +
      '    <button type="button" class="svc-btn ghost" id="svcBtnRestart">🔄 重启服务</button>' +
      '    <button type="button" class="svc-btn danger" id="svcBtnShutdown">⏹ 关闭服务</button>' +
      '  </div>' +
      '</div>';
    document.body.appendChild(mask);

    makeDraggable(fab);
    document.getElementById('svcBtnClose').addEventListener('click', closeDrawer);
    mask.addEventListener('click', function (e) { if (e.target === mask) closeDrawer(); });
    document.getElementById('svcBtnInspect').addEventListener('click', function () {
      var b = this;
      b.disabled = true;
      b.textContent = '体检中…';
      fetch('/api/services/inspect', { headers: { 'Content-Type': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (d.ok) render(d); })
        .catch(function () { toast('体检失败：请稍后重试', false); })
        .finally(function () { b.disabled = false; b.textContent = '🩺 体检'; });
    });
    document.getElementById('svcBtnCleanup').addEventListener('click', cleanup);
    document.getElementById('svcBtnRestart').addEventListener('click', restartService);
    document.getElementById('svcBtnShutdown').addEventListener('click', shutdownService);
  }

  /* 把悬浮球拉回视口内（自适应不同屏幕/窗口尺寸）：
     换小屏幕或缩小窗口后，记忆位置或默认位置都可能出界——出界即拉回 */
  function clampToViewport(fab) {
    var w = fab.offsetWidth || 120, h = fab.offsetHeight || 44;
    var x = Math.max(4, Math.min(window.innerWidth - w - 4, fab.offsetLeft));
    var y = Math.max(4, Math.min(window.innerHeight - h - 4, fab.offsetTop));
    if (x !== fab.offsetLeft || y !== fab.offsetTop) {
      fab.style.left = x + 'px';
      fab.style.top = y + 'px';
    }
  }

  function makeDraggable(fab) {
    var POS_KEY = 'svcFabPos';
    var drag = null, moved = false;
    // 恢复上次位置（超出现口边界时先拉回，避免换屏/缩窗后悬浮球消失）
    try {
      var saved = JSON.parse(localStorage.getItem(POS_KEY) || 'null');
      if (saved && saved.x != null) {
        fab.style.left = saved.x + 'px';
        fab.style.top = saved.y + 'px';
        fab.style.right = 'auto';
        fab.style.bottom = 'auto';
        clampToViewport(fab);
      }
    } catch (e) { /* 忽略 */ }
    function save() {
      try { localStorage.setItem(POS_KEY, JSON.stringify({ x: fab.offsetLeft, y: fab.offsetTop })); }
      catch (e) { /* 忽略 */ }
    }
    fab.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      drag = { dx: e.clientX - fab.offsetLeft, dy: e.clientY - fab.offsetTop };
      moved = false;
      fab.style.right = 'auto';
      fab.style.bottom = 'auto';
      fab.style.transition = 'none';
      e.preventDefault();
    });
    document.addEventListener('mousemove', function (e) {
      if (!drag) return;
      var x = Math.max(4, Math.min(window.innerWidth - fab.offsetWidth - 4, e.clientX - drag.dx));
      var y = Math.max(4, Math.min(window.innerHeight - fab.offsetHeight - 4, e.clientY - drag.dy));
      if (Math.abs(e.clientX - (drag.dx + fab.offsetLeft)) > 3 || Math.abs(e.clientY - (drag.dy + fab.offsetTop)) > 3) {
        moved = true;
      }
      fab.style.left = x + 'px';
      fab.style.top = y + 'px';
    });
    document.addEventListener('mouseup', function () {
      if (!drag) return;
      drag = null;
      fab.style.transition = '';
      if (moved) save();
    });
    // click 兜底：真实点击（mousedown→mouseup 未移动）与程序化 click() 都能开抽屉
    fab.addEventListener('click', function () {
      if (!moved) toggleDrawer();
    });
    // 窗口尺寸变化（缩窗/换屏/外接显示器切换）时把出界的悬浮球拉回视口
    window.addEventListener('resize', function () { clampToViewport(fab); });
  }

  function toggleDrawer() {
    var mask = document.getElementById('svcMask');
    if (mask.classList.contains('show')) {
      closeDrawer();
    } else {
      mask.classList.add('show');
      refresh(true);
    }
  }
  function closeDrawer() {
    document.getElementById('svcMask').classList.remove('show');
  }

  function post(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body || {}) }).then(function (r) { return r.json(); });
  }

  function opBtn(row) {
    var btns = [];
    (row.ops || []).forEach(function (op) {
      var label = { start: '启动', stop: '停止', kill: '清理', kill_all: '清理旧实例', restart: '重启' }[op] || op;
      var cls = (op === 'kill' || op === 'kill_all') ? 'danger-ghost' : '';
      btns.push('<button type="button" class="svc-btn mini ' + cls + '" data-op="' + op +
                '" data-name="' + esc(row.name) + '" data-pid="' + (row.pid || '') + '">' + label + '</button>');
    });
    return btns.join('');
  }

  function rowHtml(row) {
    var meta = [];
    if (row.ports && row.ports.length) meta.push(':' + row.ports.join('/'));
    if (row.pid) meta.push('pid ' + row.pid);
    if (row.started) meta.push('启动 ' + row.started);
    return '<div class="svc-item lv-' + row.level + '">' +
      '<div class="svc-item-r1"><span class="svc-dot ' + row.level + '"></span>' +
      '<b>' + esc(row.name) + '</b><span class="svc-lv">' + LEVEL_LABEL[row.level] + '</span>' +
      '<span class="svc-ops">' + opBtn(row) + '</span></div>' +
      '<div class="svc-item-r2"><span class="svc-st">' + esc(row.status) + '</span>' +
      '<span class="svc-meta mono">' + esc(meta.join(' · ')) + '</span></div>' +
      (row.note ? '<div class="svc-note">' + esc(row.note) + '</div>' : '') +
      '</div>';
  }

  function render(d) {
    ensureDom();
    var list = document.getElementById('svcList');
    list.innerHTML = (d.services || []).map(rowHtml).join('');
    list.querySelectorAll('button[data-op]').forEach(function (b) {
      b.addEventListener('click', function () { runOp(b.dataset.op, b); });
    });
    var s = d.summary || {};
    var badges = [];
    if (s.unreg) badges.push('<span class="svc-tag unreg">未登记 ' + s.unreg + '</span>');
    if (s.stale) badges.push('<span class="svc-tag stale">陈旧 ' + s.stale + '</span>');
    if (!badges.length) badges.push('<span class="svc-tag ok">全部健康</span>');
    document.getElementById('svcBadges').innerHTML = badges.join('');
    // 降级警示条（ps 不可用等）——提示而非服务行
    var notice = document.getElementById('svcNotice');
    if (notice) {
      var ntx = document.getElementById('svcNoticeText');
      if (d.notice) {
        if (ntx) ntx.textContent = d.notice;
        var cp = document.getElementById('svcNoticeCopy');
        if (cp && !cp.dataset.bound) {
          cp.dataset.bound = '1';
          cp.addEventListener('click', function () {
            var done = function () { cp.textContent = '已复制'; setTimeout(function () { cp.textContent = '复制修复命令'; }, 2000); };
            var cmd = 'cd /Users/ouyang/Desktop/AutomationTest && ./run.command restart-platform';
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(cmd).then(done, function () { fallbackCopy(cmd); done(); });
            } else { fallbackCopy(cmd); done(); }
          });
        }
        notice.hidden = false;
      } else {
        if (ntx) ntx.textContent = '';
        notice.hidden = true;
      }
    }
  }

  function runOp(op, btn) {
    var rowName = btn.dataset.name;
    if (op === 'kill' || op === 'kill_all') {
      if (!confirm('确认清理「' + rowName + '」？该进程将被结束。')) return;
    }
    btn.disabled = true;
    var req;
    if (op === 'start' || op === 'stop') {
      var svc = rowName.indexOf('Appium') === 0 ? 'appui'
        : (rowName.indexOf('Maestro') === 0 ? 'aicase' : 'escrcpy');
      req = post('/api/services/toggle', { svc: svc, on: op === 'start' });
    } else if (op === 'restart') {
      req = post('/api/service/restart', {}).catch(function () { return { ok: true }; });
    } else if (op === 'kill' || op === 'kill_all') {
      req = post('/api/services/cleanup', { targets: ['stale', 'unreg'] });
    } else {
      return;
    }
    req.then(function (d) {
      toast(d.msg || (d.ok ? '操作完成' : '操作失败'), !!d.ok);
      refresh(true);
    }).catch(function () { toast('请求失败', false); });
  }

  function cleanup() {
    if (!confirm('将结束所有陈旧实例与未登记占用进程（不影响当前主实例），确认？')) return;
    post('/api/services/cleanup', { targets: ['stale', 'unreg'] }).then(function (d) {
      toast(d.msg || '完成', !!d.ok);
      refresh(true);
    }).catch(function () { toast('请求失败', false); });
  }

  function restartService() {
    if (!confirm('重启平台服务？将结束所有服务进程并拉起全新实例（3~5 秒）。')) return;
    /* 复用 app.js 全局重启流程：boot_id 轮询 → 「重启成功」横幅 → 2 秒后带缓存标记刷新。
       （上一版本面板自带一份轮询实现，与首页按钮逻辑分叉：首页仍是旧的
       /api/changelog 轮询、不校验身份证——现统一收口到 app.js restartServiceRun） */
    restartServiceRun(document.getElementById('svcBtnRestart'));
  }

  function shutdownService() {
    if (!confirm('关闭所有平台服务？页面将不可用，重启请在终端执行 web_platform/app.py。')) return;
    toast('正在关闭全部服务…');
    post('/api/service/shutdown', {}).catch(function () {});
  }

  function refresh(immediate) {
    fetch('/api/services/inspect', { headers: { 'Content-Type': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) render(d); })
      .catch(function () { /* 体检失败不打扰页面 */ });
    if (immediate) return;
  }

  function start() {
    ensureDom();
    refresh(true);
    _timer = setInterval(refresh, 15000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
