/* 自动化测试平台 · 日间/夜间模式切换（所有页面通用）
   默认**日间**（Apple 官网即浅色为底）；夜间为 html.night 覆盖，见 style.css。
   选择存 localStorage['platform_theme']，刷新/重开保持。

   【首帧不闪】本脚本置于 <head>（样式表之前），并在脚本求值时就同步挂好 html 上的
   主题类，因此第一帧就是正确主题，不会出现"先白后黑"或"先黑后白"的闪烁。
   悬浮按钮的创建推迟到 DOMContentLoaded（那时 body 才存在）。

   【全局生效】元素定位器（/locator/）也加载本脚本，与平台共用同一个存储键，
   因此任一处切换，平台与定位器主题同步变化。两端 CSS 契约不同：
     · 平台   style.css —— 默认日间，html.night = 夜间
     · 定位器 style.css —— 默认日间，html.night = 夜间
   契约现已统一，故只驱动 night 一个类；day 类同时挂上，供历史选择器兼容。 */
(function () {
  const KEY = 'platform_theme';
  /* SF Symbols 风格：细线太阳 / 实心月牙 */
  const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">'
    + '<circle cx="12" cy="12" r="4.1"/>'
    + '<path d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.2 5.2l1.5 1.5M17.3 17.3l1.5 1.5M18.8 5.2l-1.5 1.5M6.7 17.3l-1.5 1.5"/></svg>';
  const ICON_MOON = '<svg viewBox="0 0 24 24" fill="currentColor">'
    + '<path d="M20.6 14.4A8.6 8.6 0 0 1 9.6 3.4 8.6 8.6 0 1 0 20.6 14.4Z"/></svg>';

  function apply(mode) {
    const root = document.documentElement;
    const isDay = mode !== 'night';
    root.classList.toggle('night', !isDay);
    root.classList.toggle('day', isDay);
    const fab = document.getElementById('theme-fab');
    if (fab) {
      fab.innerHTML = isDay ? ICON_MOON : ICON_SUN;
      fab.title = isDay ? '切换到夜间模式' : '切换到日间模式';
    }
  }

  function current() {
    try { if (localStorage.getItem(KEY) === 'night') return 'night'; } catch (e) { /* 忽略 */ }
    return 'day';
  }

  function toggle() {
    const m = current() === 'day' ? 'night' : 'day';
    try { localStorage.setItem(KEY, m); } catch (e) { /* 忽略 */ }
    apply(m);
  }

  // 立即生效（脚本在 <head>，先于样式表与首帧）
  apply(current());

  function init() {
    // 被平台 iframe 嵌入时不再注入按钮（避免父子各一个切换按钮）；
    // 主题标记仍照常同步，因此嵌入态一样跟随全局
    if (!document.documentElement.classList.contains('embedded')
        && !document.getElementById('theme-fab')) {
      const fab = document.createElement('button');
      fab.id = 'theme-fab';
      fab.className = 'theme-fab';
      fab.addEventListener('click', toggle);
      document.body.appendChild(fab);
    }
    apply(current());
    // 首屏按已存主题直接渲染（不动画）；首帧之后开启过渡，点击切换时颜色平滑渐变
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        document.documentElement.classList.add('theme-anim');
      });
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
