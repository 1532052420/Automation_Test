/* 顶部全局导航 · 面包屑路径（唯一数据源）
   ------------------------------------------------------------------
   平台各页（app.js 的 renderSidebar）与元素定位器（element_locator/static/index.js）
   共用本文件。顶部不再是菜单链接，而是「当前路径」面包屑：
   首页 / APP自动化 / 项目管理 —— 只有「首页」可点击回首页，二级、三级为纯文本。
   三级路径由各页面在切换面板时调用 PlatformNav.setSub() 更新。

   样式见同目录 nav.css（自带 --nav-* 主题变量，两个页面都能直接引用）。 */
window.PlatformNav = (function () {
  'use strict';

  /* 路径 → 二级页面名（面包屑第二级文案；首页单独处理） */
  var PAGE_NAMES = {
    '/': '首页',
    '/run': 'APP自动化',
    '/api-test': '接口测试',
    '/locator': '元素定位器',
    '/perf': '性能压测',
    '/report': '测试报告'
  };

  /* 渲染品牌区 + 面包屑路径；footHtml 可选（平台传设备/Appium 状态与更新日志入口，
     定位器不传）。sub 可选：三级路径名（如「项目管理」），后续可用 setSub 动态更新。 */
  function render(el, active, footHtml, sub) {
    if (!el) return null;
    var page = PAGE_NAMES[active] || '';
    var crumbs = '<a class="crumb crumb-home" href="/" title="回到首页">首页</a>';
    if (active && active !== '/') {
      crumbs += '<span class="crumb-sep">/</span><span class="crumb cur">' + page + '</span>';
      if (sub) crumbs += '<span class="crumb-sep">/</span><span class="crumb sub"></span>';
    }
    el.innerHTML =
      '<a class="brand" href="/"><span class="logo">✓</span>自动化测试平台</a>' +
      '<nav class="crumbs">' + crumbs + '</nav>' + (footHtml || '');
    if (sub) setSub(el, sub);
    return el;
  }

  /* 更新三级路径（无则新增，传空则移除）；只改文本节点，不重建整条面包屑 */
  function setSub(el, sub) {
    if (!el) return;
    var nav = el.querySelector('nav.crumbs');
    if (!nav) return;
    var old = nav.querySelector('.crumb.sub');
    if (sub) {
      if (!old) {
        nav.insertAdjacentHTML('beforeend',
          '<span class="crumb-sep">/</span><span class="crumb sub"></span>');
        old = nav.querySelector('.crumb.sub');
      }
      old.textContent = sub;
    } else if (old) {
      var sep = old.previousElementSibling;
      if (sep && sep.classList.contains('crumb-sep')) sep.remove();
      old.remove();
    }
  }

  return { PAGE_NAMES: PAGE_NAMES, render: render, setSub: setSub };
})();
