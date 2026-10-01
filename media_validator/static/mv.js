/* 媒体产物检测 · 自包含前端脚本（不依赖框架 app.js / nav.js）
   职责：任务列表轮询、上传（拖拽/多选 + 规则编辑）、检测触发、报告弹窗、日/夜切换。 */
(function () {
  'use strict';

  var $ = function (sel) { return document.querySelector(sel); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var TYPE_LABELS = { audio: '音频', video: '视频', image: '图片' };

  /* ---------------- 主题（与平台同键同契约） ---------------- */
  function applyTheme(mode) {
    var root = document.documentElement;
    root.classList.toggle('night', mode === 'night');
    root.classList.toggle('day', mode !== 'night');
  }
  $('#themeFab').addEventListener('click', function () {
    var night = document.documentElement.classList.contains('night');
    var next = night ? 'day' : 'night';
    try { localStorage.setItem('platform_theme', next); } catch (e) { /* 忽略 */ }
    applyTheme(next);
  });

  /* ---------------- 基础请求 / Toast ---------------- */
  function api(method, url, body) {
    var opt = { method: method };
    if (body instanceof FormData) opt.body = body;
    else if (body !== undefined) {
      opt.headers = { 'Content-Type': 'application/json' };
      opt.body = JSON.stringify(body);
    }
    return fetch(url, opt).then(function (r) {
      return r.json().catch(function () { return { ok: false, msg: 'HTTP ' + r.status }; })
        .then(function (d) { d._status = r.status; return d; });
    });
  }

  var toastTimer = null;
  function toast(msg, ok) {
    var el = $('#toast');
    el.textContent = msg;
    el.className = 'show' + (ok === false ? ' err' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = ''; }, 2600);
  }

  /* ---------------- 工具状态 + 统计 ---------------- */
  function loadOverview() {
    return api('GET', '/media-validator/api/overview').then(function (d) {
      if (!d.ok) return;
      var chip = $('#toolChip');
      var toolsOk = d.tools && d.tools.ffmpeg && d.tools.ffprobe;
      chip.classList.toggle('ok', !!toolsOk);
      chip.classList.toggle('bad', !toolsOk);
      chip.textContent = '';
      var dot = document.createElement('span'); dot.className = 'dot';
      chip.appendChild(dot);
      chip.appendChild(document.createTextNode(
        toolsOk ? 'ffmpeg 就绪 · 通过 ' + d.stats.passed + ' / 失败 ' + d.stats.failed
                : 'ffmpeg / ffprobe 未安装，无法检测'));
      if (!toolsOk) chip.title = 'brew install ffmpeg 后刷新本页';
    }).catch(function () { /* 首屏统计失败不打断 */ });
  }

  /* ---------------- 任务列表 ---------------- */
  var pollTimer = null;

  function fmtSize(n) {
    if (n == null) return '-';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0, v = n;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return (i ? v.toFixed(1) : v) + ' ' + units[i];
  }

  function badgeHtml(status) {
    var text = { PENDING: '待检测', RUNNING: '检测中', PASSED: 'PASS', FAILED: 'FAIL', ERROR: '错误' }[status] || status;
    return '<span class="badge ' + esc(status) + '">' + text + '</span>';
  }

  function rowHtml(t) {
    var ops = '<td class="ops">';
    if (t.status === 'PENDING') {
      ops += '<button class="btn mini primary" onclick="MV.detectOne(\'' + t.id + '\')">检测</button> ';
    } else {
      ops += '<button class="btn mini" onclick="MV.showReport(\'' + t.id + '\')">详情</button> ' +
             '<button class="btn mini" onclick="MV.detectOne(\'' + t.id + '\')">重新检测</button> ';
    }
    ops += '<button class="btn mini danger-ghost" onclick="MV.remove(\'' + t.id + '\')">删除</button></td>';
    return '<tr>' +
      '<td class="tname" title="' + esc(t.filename) + '">' + esc(t.filename) + '</td>' +
      '<td><span class="ttype ' + esc(t.media_type) + '">' + (TYPE_LABELS[t.media_type] || t.media_type) + '</span></td>' +
      '<td class="tsize">' + fmtSize(t.size_bytes) + '</td>' +
      '<td>' + badgeHtml(t.status) + (t.status === 'ERROR' && t.error ? '<div class="inote" style="font-size:12px">' + esc(t.error) + '</div>' : '') + '</td>' +
      '<td class="ttime">' + esc(t.created_at || '') + '</td>' +
      ops + '</tr>';
  }

  function loadTasks() {
    return api('GET', '/media-validator/api/tasks').then(function (d) {
      if (!d.ok) return;
      var tasks = d.tasks || [];
      var tbody = $('#taskBody');
      tbody.innerHTML = tasks.map(rowHtml).join('');
      var empty = $('#emptyBox');
      empty.innerHTML = tasks.length ? '' :
        '<div class="empty"><div class="eico">🗂</div>还没有检测任务<br>' +
        '<a href="javascript:MV.openUpload()">上传第一个媒体文件 →</a></div>';
      // 有进行中的任务就持续轮询；全部落定则拉一次统计后停表
      var busy = tasks.some(function (t) { return t.status === 'RUNNING'; });
      if (busy && !pollTimer) {
        pollTimer = setInterval(function () { loadTasks(); }, 1500);
      } else if (!busy && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
        loadOverview();
      }
    }).catch(function () { /* 轮询失败下轮再试 */ });
  }

  /* ---------------- 上传弹窗 ---------------- */
  var picked = [];   // [{file, type, reason?}]

  function openUpload() {
    picked = [];
    renderPicked();
    $('#uploadMask').classList.add('show');
  }
  function closeUpload() {
    $('#uploadMask').classList.remove('show');
    $('#fileInput').value = '';
  }

  function typeOfName(name) {
    var m = name.toLowerCase().match(/\.([a-z0-9]+)$/);
    var ext = m ? m[1] : '';
    var map = { png: 'image', jpg: 'image', jpeg: 'image', webp: 'image',
                mp3: 'audio', wav: 'audio', m4a: 'audio',
                mp4: 'video', mov: 'video', mkv: 'video' };
    return map[ext] ? { type: map[ext], ext: ext } : null;
  }

  function addFiles(fileList) {
    Array.prototype.forEach.call(fileList, function (f) {
      var t = typeOfName(f.name);
      picked.push({ file: f, type: t && t.type, ext: t && t.ext,
                    reason: t ? null : '不支持的格式（仅 PNG/JPG/WEBP、MP3/WAV/M4A、MP4/MOV/MKV）' });
    });
    renderPicked();
  }

  function renderPicked() {
    var box = $('#pickedBox');
    if (!picked.length) { box.innerHTML = ''; $('#rulesBox').innerHTML = ''; $('#uploadGo').disabled = true; return; }
    var rows = picked.map(function (p, i) {
      var type = p.reason
        ? '<span class="rej">' + esc(p.reason) + '</span>'
        : '<span class="ttype ' + p.type + '">' + TYPE_LABELS[p.type] + '</span> <span class="tsize">' + fmtSize(p.file.size) + '</span>';
      return '<div class="picked-row"><span class="name">' + esc(p.file.name) + '</span>' + type +
             '<button class="rm" title="移除" onclick="MV.removePicked(' + i + ')">✕</button></div>';
    }).join('');
    box.innerHTML = '<div class="picked-list">' + rows + '</div>';

    var types = {};
    picked.forEach(function (p) { if (p.type) types[p.type] = true; });
    $('#rulesBox').innerHTML = Object.keys(types).map(function (t) { return rulesGroupHtml(t); }).join('');
    $('#uploadGo').disabled = !picked.some(function (p) { return !p.reason; });
  }

  /* 规则表单：按默认值渲染可编辑项；空值表示关闭阈值 */
  var RULE_FIELDS = {
    audio: [['duration_min', '时长下限(s)'], ['duration_max', '时长上限(s)'],
            ['max_silence', '最长静音(s)'], ['min_sample_rate', '采样率下限(Hz)'],
            ['min_channels', '声道数下限']],
    video: [['duration_min', '时长下限(s)'], ['duration_max', '时长上限(s)'],
            ['min_width', '最小宽度(px)'], ['min_height', '最小高度(px)'],
            ['min_fps', '帧率下限'], ['max_black', '最长黑屏(s)'], ['max_freeze', '最长冻结(s)']],
    image: [['min_width', '最小宽度(px)'], ['min_height', '最小高度(px)'],
            ['max_file_mb', '大小上限(MB)']]
  };
  var defaultRules = {};

  function rulesGroupHtml(type) {
    var fields = RULE_FIELDS[type] || [];
    var cells = fields.map(function (f) {
      var key = 'mv-rule-' + type + '-' + f[0];
      return '<div class="rule-field"><label for="' + key + '">' + f[1] + '</label>' +
             '<input id="' + key + '" data-type="' + type + '" data-key="' + f[0] + '" ' +
             'placeholder="留空=仅报告"></div>';
    }).join('');
    return '<details class="rules-group" open><summary>' + TYPE_LABELS[type] + '检测规则（可改）</summary>' +
           '<div class="rules-grid">' + cells +
           '<div class="rule-field"><label>非纯静音</label><input type="checkbox" data-type="' + type + '" data-key="require_sound" ' +
           (defaultRules[type] && defaultRules[type].require_sound ? 'checked' : '') + '></div>' +
           '<div class="rule-field"><label>画面内容检查</label><input type="checkbox" data-type="' + type + '" data-key="detect_blank" ' +
           (defaultRules[type] && defaultRules[type].detect_blank ? 'checked' : '') + '></div>' +
           '</div></details>';
  }

  function collectRules() {
    var out = {};
    document.querySelectorAll('#rulesBox [data-type]').forEach(function (el) {
      var type = el.dataset.type, key = el.dataset.key;
      out[type] = out[type] || {};
      if (el.type === 'checkbox') { out[type][key] = el.checked; return; }
      var v = el.value.trim();
      if (v === '') { out[type][key] = null; return; }
      var num = Number(v);
      out[type][key] = isNaN(num) ? null : num;
    });
    return out;
  }

  function doUpload() {
    var goBtn = $('#uploadGo');
    goBtn.disabled = true;
    var fd = new FormData();
    picked.forEach(function (p) { if (!p.reason) fd.append('files', p.file); });
    fd.append('rules', JSON.stringify(collectRules()));
    fd.append('start', '1');
    api('POST', '/media-validator/api/upload', fd).then(function (d) {
      if (!d.ok) { toast(d.msg || '上传失败', false); goBtn.disabled = false; return; }
      var rejN = (d.rejected || []).length, okN = (d.created || []).length;
      closeUpload();
      if (rejN) toast('已提交 ' + okN + ' 个文件，' + rejN + ' 个因格式不支持被拒绝', false);
      else toast('已上传并开始检测 ' + okN + ' 个文件');
      loadTasks();
      loadOverview();
    }).catch(function () { toast('上传失败（网络异常）', false); goBtn.disabled = false; });
  }

  /* ---------------- 检测触发 / 删除 ---------------- */
  function detectAll() {
    api('GET', '/media-validator/api/tasks').then(function (d) {
      if (!d.ok) return;
      var ids = (d.tasks || []).filter(function (t) { return t.status === 'PENDING'; })
                               .map(function (t) { return t.id; });
      if (!ids.length) { toast('没有「待检测」任务', false); return; }
      api('POST', '/media-validator/api/detect', { ids: ids }).then(function (r) {
        if (!r.ok) { toast(r.msg || '触发失败', false); return; }
        toast('已开始检测 ' + r.started.length + ' 个任务');
        loadTasks();
      });
    });
  }

  function detectOne(id) {
    api('POST', '/media-validator/api/task/' + id + '/detect', {}).then(function (d) {
      if (!d.ok) { toast(d.msg || '触发失败', false); return; }
      toast('已开始检测');
      $('#reportMask').classList.remove('show');
      loadTasks();
    });
  }

  function remove(id) {
    if (!confirm('删除该任务及其上传文件？不可恢复。')) return;
    api('DELETE', '/media-validator/api/task/' + id).then(function (d) {
      toast(d.ok ? '已删除' : (d.msg || '删除失败'), d.ok);
      if ($('#reportMask').classList.contains('show')) $('#reportMask').classList.remove('show');
      loadTasks();
      loadOverview();
    });
  }

  /* ---------------- 报告弹窗 ---------------- */
  var reportTaskId = null;

  function showReport(id) {
    api('GET', '/media-validator/api/task/' + id).then(function (d) {
      if (!d.ok) { toast(d.msg || '任务不存在', false); return; }
      reportTaskId = id;
      renderReport(d.task);
      $('#reportMask').classList.add('show');
    });
  }

  function renderReport(t) {
    $('#rpTitle').textContent = '检测报告 · ' + t.filename;
    var body = $('#reportBody');
    if (!t.report) {
      body.innerHTML = '<div class="empty"><div class="eico">⏳</div>' +
        (t.status === 'RUNNING' ? '检测进行中，请稍候…' : (t.error ? esc(t.error) : '尚无报告，点击「重新检测」开始')) + '</div>';
      return;
    }
    var r = t.report, info = r.info || {};
    var status = t.status;
    var vline = status === 'PASSED' ? '全部检测项通过' :
                status === 'FAILED' ? r.items.filter(function (i) { return i.passed === false; }).length + ' 个检测项未通过' :
                (t.error || '执行异常');

    var streamTxt = (info.streams || []).map(function (s) {
      var bits = [s.kind === 'audio' ? '音频轨' : '视频轨', s.codec];
      if (s.kind === 'video' && s.width) bits.push(s.width + 'x' + s.height);
      if (s.kind === 'audio' && s.sample_rate) bits.push(s.sample_rate + 'Hz/' + s.channels + 'ch');
      return bits.filter(Boolean).join(' · ');
    }).join('；') || '无';

    body.innerHTML =
      '<div class="verdict ' + esc(status) + '"><span class="vmark">' +
        (status === 'PASSED' ? '✓' : status === 'FAILED' ? '✕' : '!') + '</span>' +
        '<span class="vtxt"><b>' + esc(status) + '</b><span>' + esc(vline) + '</span></span></div>' +
      '<div class="info-grid">' +
        '<span class="k">类型</span><span class="v">' + (TYPE_LABELS[info.media_type] || '-') + '（.' + esc(info.ext) + '）</span>' +
        '<span class="k">大小</span><span class="v">' + fmtSize(info.size_bytes) + '</span>' +
        '<span class="k">封装</span><span class="v">' + esc(info.container || '-') + ' · 嗅探 ' + esc(info.sniff || '未识别') + '</span>' +
        '<span class="k">时长</span><span class="v">' + fmtDur(info.duration) + '</span>' +
        '<span class="k">流信息</span><span class="v full">' + esc(streamTxt) + '</span>' +
      '</div>' +
      '<div class="items-title">检测项（' + r.items.length + '）</div>' +
      r.items.map(itemHtml).join('');
  }

  function fmtDur(sec) {
    if (sec == null) return '-';
    var m = Math.floor(sec / 60), s = sec - m * 60;
    return m ? m + 'm' + s.toFixed(1) + 's' : s.toFixed(1) + 's';
  }

  function itemHtml(it) {
    var cls = it.passed === true ? 'pass' : it.passed === false ? 'fail' : 'skip';
    var mark = it.passed === true ? '✓' : it.passed === false ? '✕' : '－';
    return '<div class="item-row ' + cls + '">' +
      '<span class="imark">' + mark + '</span>' +
      '<span class="ibody"><span class="ilabel">' + esc(it.label) +
        '<span class="irule">规则：' + esc(it.rule) + '</span></span>' +
        '<div class="iactual">' + esc(it.actual) + '</div>' +
        (it.note ? '<div class="inote">' + esc(it.note) + '</div>' : '') +
      '</span></div>';
  }

  /* ---------------- 事件绑定 ---------------- */
  window.MV = { openUpload: openUpload, detectAll: detectAll, detectOne: detectOne,
                remove: remove, showReport: showReport, removePicked: removePicked };

  function removePicked(i) {
    picked.splice(i, 1);
    renderPicked();
  }

  $('#btnUpload').addEventListener('click', openUpload);
  $('#btnDetectAll').addEventListener('click', detectAll);
  $('#btnRefresh').addEventListener('click', function () { loadTasks(); loadOverview(); });
  $('#uploadClose').addEventListener('click', closeUpload);
  $('#uploadCancel').addEventListener('click', closeUpload);
  $('#uploadGo').addEventListener('click', doUpload);
  $('#reportClose').addEventListener('click', function () { $('#reportMask').classList.remove('show'); });
  $('#reportOk').addEventListener('click', function () { $('#reportMask').classList.remove('show'); });
  $('#rpRedetect').addEventListener('click', function () { if (reportTaskId) detectOne(reportTaskId); });

  // 点击遮罩空白处关闭
  [['#uploadMask', closeUpload], ['#reportMask', function () { $('#reportMask').classList.remove('show'); }]]
    .forEach(function (pair) {
      $(pair[0]).addEventListener('click', function (e) { if (e.target === $(pair[0])) pair[1](); });
    });
  // ESC 关闭
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    $('#reportMask').classList.remove('show');
    closeUpload();
  });

  var dz = $('#dropzone');
  dz.addEventListener('click', function () { $('#fileInput').click(); });
  $('#fileInput').addEventListener('change', function (e) { addFiles(e.target.files); });
  ['dragenter', 'dragover'].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('drag'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove('drag'); });
  });
  dz.addEventListener('drop', function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });

  /* ---------------- 启动 ---------------- */
  api('GET', '/media-validator/api/rules').then(function (d) {
    if (d.ok) defaultRules = d.rules || {};
  });
  loadOverview();
  loadTasks();
})();
