# -*- coding: utf-8 -*-
"""Allure 报告后处理：截图/视频附件缩略图化 + 点击放大

Allure 2.46 生成的报告里，图片/视频附件按原始尺寸渲染——手机截图（1220×2688）
和录屏在报告里占满整屏，翻报告很痛苦。本模块在 `allure generate` 之后对报告
目录做后处理：

- 注入 allure_thumb.css：附件图片/视频缩略图化（max 220×160），光标 zoom-in
- 注入 allure_thumb.js：事件委托，点击附件弹出浮层看原尺寸（图片原分辨率 /
  视频带控制条自动播放），点遮罩或 Esc 关闭
- index.html 注入引用（幂等：已有标记则跳过）

证据文件本身不压缩、不上传——缩小只是展示层。
"""
import os
import re

_THUMB_CSS = """/* Allure 附件缩略图（平台注入） */
#content img[src*="attachments/"], #content video[src*="attachments/"] {
  max-width: 220px !important; max-height: 160px !important;
  width: auto !important; height: auto !important;
  cursor: zoom-in; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.25);
}
#content video[src*="attachments/"] { background: #000; }
/* 点击放大浮层 */
#thumb-lightbox { position: fixed; inset: 0; z-index: 99999; display: none;
  align-items: center; justify-content: center; background: rgba(0,0,0,.82); cursor: zoom-out; }
#thumb-lightbox.on { display: flex; }
#thumb-lightbox img, #thumb-lightbox video {
  max-width: 94vw; max-height: 94vh; width: auto; height: auto;
  border-radius: 8px; box-shadow: 0 8px 40px rgba(0,0,0,.6); background: #000; }
#thumb-lightbox .thumb-close { position: fixed; top: 18px; right: 26px; color: #fff;
  font-size: 34px; line-height: 1; opacity: .8; font-family: sans-serif; }
"""

_THUMB_JS = """/* Allure 附件点击放大（平台注入）：截图/视频缩略图 → 浮层看原尺寸 */
(function () {
  'use strict';
  var lb = null, lbMedia = null;
  function ensureLightbox() {
    if (lb) return;
    lb = document.createElement('div');
    lb.id = 'thumb-lightbox';
    lb.innerHTML = '<span class="thumb-close">×</span>';
    lbMedia = document.createElement('div');
    lb.appendChild(lbMedia);
    lb.addEventListener('click', closeLb);
    document.body.appendChild(lb);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && lb.classList.contains('on')) closeLb();
    });
  }
  function closeLb() {
    lb.classList.remove('on');
    lbMedia.innerHTML = '';   // 停掉浮层里的视频播放
  }
  function openLb(src, isVideo) {
    ensureLightbox();
    lbMedia.innerHTML = '';
    var el;
    if (isVideo) {
      el = document.createElement('video');
      el.controls = true; el.autoplay = true; el.src = src;
    } else {
      el = document.createElement('img');
      el.src = src;
    }
    lbMedia.appendChild(el);
    lb.classList.add('on');
  }
  // 事件委托：SPA 动态渲染的附件无需逐个绑事件
  document.addEventListener('click', function (e) {
    if (lb && lb.contains(e.target)) return;   // 浮层内部点击交给 closeLb
    var t = e.target;
    if (!t || (t.tagName !== 'IMG' && t.tagName !== 'VIDEO')) return;
    var src = t.currentSrc || t.src || '';
    if (src.indexOf('attachments/') < 0) return;
    e.preventDefault();
    if (t.tagName === 'VIDEO' && t.pause) t.pause();
    openLb(src, t.tagName === 'VIDEO');
  }, true);
})();
"""


def apply(report_dir):
    """对生成的 Allure 报告目录注入缩略图样式与点击放大脚本（幂等）。返回 (ok, msg)"""
    try:
        index_path = os.path.join(report_dir, 'index.html')
        if not os.path.isfile(index_path):
            return False, '报告 index.html 不存在'
        with open(index_path, 'r', encoding='utf-8') as f:
            html = f.read()
        if 'allure_thumb.js' in html:
            return True, '已注入过，跳过'

        with open(os.path.join(report_dir, 'allure_thumb.css'), 'w', encoding='utf-8') as f:
            f.write(_THUMB_CSS)
        with open(os.path.join(report_dir, 'allure_thumb.js'), 'w', encoding='utf-8') as f:
            f.write(_THUMB_JS)

        inject = ('<link rel="stylesheet" href="allure_thumb.css">\n'
                  '<script src="allure_thumb.js"></script>\n')
        # 优先挂在核心脚本标记之后；找不到就挂 </body> 前
        marker = re.search(r'<script src="assets/index-[^"]+\.js"></script>', html)
        if marker:
            html = html[:marker.end()] + '\n' + inject + html[marker.end():]
        else:
            html = html.replace('</body>', inject + '</body>', 1)
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return True, '缩略图注入完成'
    except Exception as e:
        return False, '注入失败: %s' % e
