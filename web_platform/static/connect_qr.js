/* 扫码连接弹窗 · 共享模块（平台各页 + 元素定位器共用）
   ------------------------------------------------------------------
   window.PlatformQR.open() → 弹出「扫码连接设备」二维码模态。
   数据源：/api/connect/info（连接配置持久化 config/connect_settings.json）
           /api/connect/qrcode（PNG，本地生成）
   三种模式：adbwifi（Android 11+ 无线调试配对串）/ url（平台地址）/ custom（自定义文本）。
   样式自注入（.pqr-* 前缀，与平台 style.css 的 .qrmodal 段视觉一致，改动需两处同步）；
   夜间主题走两端共用的 html.night 契约。 */
window.PlatformQR = (function () {
  'use strict';

  var MODE_NAMES = { adbwifi: 'ADB 无线调试配对', url: '平台地址', custom: '自定义文本' };
  var MODE_STEPS = {
    adbwifi: ['✓ 用手机相机/微信扫本码（此码是平台连接页地址）',
              '手机打开页面后自动显示手机 IP 并匹配已登记设备',
              '手机「设置 → 开发者选项 → 无线调试」→「使用配对码配对设备」，把显示的端口和 6 位码填进页面',
              '点「配对并连接」即完成——下次免 USB 直接在线'],
    url:     ['✓ 此码可用任意扫码工具（相机 / 微信 / 浏览器）',
              '扫后在手机上打开自动化测试平台',
              '按页面提示完成设备接入与用例执行'],
    custom:  ['用手机扫描二维码读取内容',
              '按自定义内容的指引完成连接'],
  };

  var STYLE = [
    '.pqr-mask { position: fixed; inset: 0; z-index: 998; display: none; align-items: center;',
    '  justify-content: center; background: rgba(0,0,0,.32);',
    '  -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); }',
    '.pqr-mask.show { display: flex; }',
    '.pqr-modal { background: #fff; color: #1d1d1f; border-radius: 20px; padding: 26px 28px 22px;',
    '  width: min(600px, 92vw); max-width: 92vw; border: 1px solid rgba(0,0,0,.07);',
    '  box-shadow: 0 30px 80px rgba(0,0,0,.25); animation: pqr-pop .2s cubic-bezier(.22,.9,.3,1.15); }',
    '@keyframes pqr-pop { from { transform: scale(.94); opacity: 0; } to { transform: scale(1); opacity: 1; } }',
    '.pqr-modal h4 { font-size: 17px; font-weight: 600; margin-bottom: 12px; }',
    '.pqr-wrap { display: flex; gap: 18px; align-items: flex-start; }',
    '.pqr-wrap img { width: 176px; height: 176px; padding: 8px; flex: none; display: block;',
    '  background: #fff; border: 1px solid rgba(0,0,0,.07); border-radius: 12px; }',
    '.pqr-side { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 8px; }',
    '.pqr-pill { align-self: flex-start; padding: 3px 12px; border-radius: 980px; font-size: 12.5px;',
    '  font-weight: 500; background: rgba(52,199,89,.13); color: #1d7a3a; }',
    '.pqr-payload { display: block; width: 100%; font: 11.5px/1.6 ui-monospace, "SF Mono", Menlo, Consolas, monospace;',
    '  background: #fbfbfd; border: 1px solid rgba(0,0,0,.07); border-radius: 8px; padding: 8px 10px;',
    '  color: #3a3a3c; word-break: break-all; max-height: 84px; overflow: auto; }',
    '.pqr-steps { margin: 2px 0 0; padding-left: 20px; font-size: 12.5px; color: #6e6e73; line-height: 1.9; }',
    '.pqr-tip { font-size: 12.5px; margin: 14px 0 0; color: #6e6e73; }',
    '.pqr-mops { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }',
    '.pqr-mops button, .pqr-mops a { font: inherit; font-size: 13.5px; font-weight: 500; padding: 7px 18px;',
    '  border-radius: 980px; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center;',
    '  transition: background .18s ease, color .18s ease; }',
    '.pqr-mops .ghost { background: transparent; color: #1d1d1f; border: 1px solid #d2d2d7; }',
    '.pqr-mops .ghost:hover { background: #f0f0f2; }',
    '.pqr-mops .primary { background: #0071e3; color: #fff; border: 0; }',
    '.pqr-mops .primary:hover { background: #0077ed; }',
    'html.night .pqr-modal { background: #1d1d1f; color: #f5f5f7; border-color: rgba(255,255,255,.08); }',
    'html.night .pqr-payload { background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.08); color: #e8e8ed; }',
    'html.night .pqr-steps, html.night .pqr-tip { color: #a1a1a6; }',
    'html.night .pqr-mops .ghost { color: #f5f5f7; border-color: rgba(255,255,255,.2); }',
    'html.night .pqr-mops .ghost:hover { background: rgba(255,255,255,.08); }',
    '@media (max-width: 560px) { .pqr-wrap { flex-direction: column; } .pqr-wrap img { width: 100%; height: auto; } }',
  ].join('\n');

  function ensureStyle() {
    if (document.getElementById('pqr-style')) return;
    var st = document.createElement('style');
    st.id = 'pqr-style';
    st.textContent = STYLE;
    document.head.appendChild(st);
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function stepsHtml(mode) {
    return (MODE_STEPS[mode] || []).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('');
  }

  function fill(d) {
    var mode = (d.config && d.config.mode) || 'adbwifi';
    document.querySelector('#pqrMode').textContent = MODE_NAMES[mode] || mode;
    document.querySelector('#pqrPayload').textContent = d.payload || '';
    document.querySelector('#pqrSteps').innerHTML = stepsHtml(mode);
    document.querySelector('#pqrImg').src = '/api/connect/qrcode?ts=' + Date.now();
    document.querySelector('#pqrTip').innerHTML =
      '主机 IP：<b>' + esc(d.detected_host || '-') + '</b>' +
      ' · SoloPi 组网：主设备「一机多控」扫码添加从机；APK 一键安装见平台「设备连接 → 设备管理」';
  }

  function open() {
    ensureStyle();
    fetch('/api/connect/info', { headers: { 'Content-Type': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) throw new Error(d.msg || '加载失败');
        var mask = document.getElementById('pqrMask');
        if (!mask) {
          mask = document.createElement('div');
          mask.className = 'pqr-mask';
          mask.id = 'pqrMask';
          mask.innerHTML =
            '<div class="modal pqr-modal"><h4>扫码连接设备</h4>' +
            '<div class="qr-wrap"><img id="pqrImg" alt="连接二维码">' +
            '<div class="qr-side"><span class="pill pqr-pill" id="pqrMode">—</span>' +
            '<code class="qr-payload pqr-payload" id="pqrPayload" title="二维码内容">—</code>' +
            '<ol class="qr-steps pqr-steps" id="pqrSteps"></ol></div></div>' +
            '<p class="pqr-tip" id="pqrTip"></p>' +
            '<div class="pqr-mops"><button type="button" class="ghost" id="pqrRefresh">刷新二维码</button>' +
            '<a class="ghost" href="/connect">连接配置</a>' +
            '<button type="button" class="primary" id="pqrClose">关闭</button></div></div>';
          document.body.appendChild(mask);
          mask.addEventListener('click', function (e) {
            if (e.target === mask) mask.classList.remove('show');
          });
          document.querySelector('#pqrClose').addEventListener('click', function () {
            mask.classList.remove('show');
          });
          document.querySelector('#pqrRefresh').addEventListener('click', function () {
            document.querySelector('#pqrImg').src = '/api/connect/qrcode?ts=' + Date.now();
          });
        }
        fill(d);
        mask.classList.add('show');
      })
      .catch(function (e) {
        alert('扫码连接加载失败：' + (e.message || e));
      });
  }

  return { open: open, MODE_NAMES: MODE_NAMES, MODE_STEPS: MODE_STEPS };
})();
