/* 测试平台 · 日间/夜间模式切换（悬浮按钮，Mac/iPhone 简约风日/月图标，所有页面通用）
   默认夜间（黑色居多，即原深色主题）；日间模式白色居多（html.day 变量覆盖，见 style.css）
   选择存 localStorage['platform_theme']，刷新/重开保持
   按钮图标：日间显示月亮（点击切夜间），夜间显示太阳（点击切日间）；图标颜色随主题自适应

   【全局生效】元素定位器（/locator/）也加载本脚本，与平台共用同一个存储键，
   因此任一处切换，平台与定位器主题同步变化。
   两端 CSS 契约默认态相反，故同时驱动两个标记：
     · 平台   style.css —— html.day = 日间（默认夜间）
     · 定位器 style.css —— html.night = 夜间（默认日间） */
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
    const isDay = mode === 'day';
    // 同时驱动两端契约（默认态相反）：平台 .day 与定位器 .night 互为反向
    root.classList.toggle('day', isDay);
    root.classList.toggle('night', !isDay);
    const fab = document.getElementById('theme-fab');
    if (fab) {
      fab.innerHTML = isDay ? ICON_MOON : ICON_SUN;
      fab.title = isDay ? '切换到夜间模式（黑色）' : '切换到日间模式（白色）';
    }
  }

  function current() {
    try { if (localStorage.getItem(KEY) === 'day') return 'day'; } catch (e) { /* 忽略 */ }
    return 'night';
  }

  function toggle() {
    const m = current() === 'day' ? 'night' : 'day';
    try { localStorage.setItem(KEY, m); } catch (e) { /* 忽略 */ }
    apply(m);
  }

  function init() {
    // 被平台 iframe 嵌入时不再注入按钮（避免父子各一个切换按钮）；
    // 主题标记仍照常同步，因此嵌入态一样跟随全局
    if (!document.documentElement.classList.contains('embedded')) {
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
