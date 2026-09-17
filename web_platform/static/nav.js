/* 顶部全局导航 · 结构单一数据源
   ------------------------------------------------------------------
   平台各页（app.js 的 renderSidebar）与元素定位器（element_locator/static/index.js）
   共用同一份导航项与渲染逻辑：加页面只改这里的 ITEMS 一处，两端同时生效。

   样式见同目录 nav.css（自带 --nav-* 主题变量，两个页面都能直接引用）。 */
window.PlatformNav = (function () {
  'use strict';

  /* [路径, 名称] —— 顺序即导航显示顺序 */
  var ITEMS = [
    ['/', '首页'],
    ['/run', 'AppUI 自动化'],
    ['/api-test', '接口测试'],
    ['/report', '测试报告'],
    ['/locator', '元素定位器'],
    ['/perf', '性能压测']
  ];

  /* 渲染品牌区 + 导航链接；footHtml 可选（平台传设备/Appium 状态与更新日志入口，
     定位器不传）。返回容器，便于调用方继续挂自己的元素。 */
  function render(el, active, footHtml) {
    if (!el) return null;
    var links = ITEMS.map(function (it) {
      return '<a href="' + it[0] + '"' + (it[0] === active ? ' class="on"' : '') + '>' + it[1] + '</a>';
    }).join('');
    el.innerHTML =
      '<a class="brand" href="/"><span class="logo">✓</span>自动化测试平台</a>' +
      '<nav>' + links + '</nav>' + (footHtml || '');
    return el;
  }

  return { ITEMS: ITEMS, render: render };
})();
