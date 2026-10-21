# -*- coding: utf-8 -*-
"""Trace 失败诊断 · 录制器（独立 CLI，与平台零耦合）

调试直跑（不经平台）：
    trace_lab/.venv/bin/python trace_lab/record.py <url> <out.zip> [--headed]

产出 Playwright trace.zip（操作步骤 + 截图 + DOM 快照 + 网络请求合一），
另有同名 .png 整页截图作快速留档。回放方式二选一：
    1) 平台首页「Trace 失败诊断」卡片 → Trace 诊断页 → 回放
    2) trace_lab/.venv/bin/python -m playwright show-trace <out.zip>

录制步骤刻意保持最小样板：现阶段验证链路用，接入用例框架后
由框架在各步骤埋点（tracing.start/stop + 每步前后快照）替换。
"""
import os
import sys
import time


def log(msg):
    print('[%s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def record(url, out_zip, headless=True):
    """录制一次浏览会话 trace。步骤全部容错：单步失败不中断，
    失败本身就是 trace 要捕获的东西（viewer 里能看到失败现场）。"""
    from playwright.sync_api import sync_playwright

    out_png = os.path.splitext(out_zip)[0] + '.png'
    with sync_playwright() as p:
        log('启动 Chromium（headless=%s）' % headless)
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        log('trace 开始录制（截图 + DOM 快照 + 网络）')
        page = context.new_page()
        steps = [
            ('打开页面 %s' % url,
             lambda: page.goto(url, wait_until='domcontentloaded', timeout=30000)),
            ('等待网络空闲',
             lambda: page.wait_for_load_state('networkidle', timeout=15000)),
            ('读取标题',
             lambda: log('页面标题：%s' % page.title())),
            ('整页截图 %s' % os.path.basename(out_png),
             lambda: page.screenshot(path=out_png, full_page=True)),
            ('刷新一次（生成网络回放样本）',
             lambda: page.reload(wait_until='domcontentloaded')),
            ('再次等待网络空闲',
             lambda: page.wait_for_load_state('networkidle', timeout=15000)),
        ]
        for name, act in steps:
            t0 = time.time()
            try:
                act()
                log('%s ✓（%.1fs）' % (name, time.time() - t0))
            except Exception as exc:
                log('%s ✗（%.1fs）：%s' % (name, time.time() - t0, str(exc)[:200]))
        context.tracing.stop(path=out_zip)
        log('trace 已保存：%s' % out_zip)
        browser.close()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 2:
        print('用法：trace_lab/.venv/bin/python trace_lab/record.py <url> <out.zip> [--headed]')
        sys.exit(2)
    record(args[0], args[1], headless='--headed' not in sys.argv)


if __name__ == '__main__':
    main()
