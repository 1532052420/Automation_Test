# -*- coding: utf-8 -*-
"""给 @appium/base-driver 打补丁：修复 proxyRouteIsAvoided 的 URL 规范化缺陷。

问题（Appium 3.7.0 / @appium/base-driver 10.8.0 实测）：
  protocol.js 把 `req.originalUrl`（完整 URL，含 http://host:port 前缀）传给
  basedriver/core.js 的 proxyRouteIsAvoided；而该方法只按 `this.basePath`
  剥前缀。结果 URL 开头的 `http://host:port` 剥不掉，与 driver 的 NO_PROXY
  白名单（全部是 ^/session/... 形式）永不匹配 —— 判定恒为 false，所有命令
  被误代理给设备端 uiautomator2 server（它只实现了 find/ source 等少数路由，
  start_activity / window_rect / app_state 等一律 404 "unknown command"）。
  附带问题：`this.basePath` 在部分版本组合下无人赋值（实际值挂在
  `this.serverPath`），一并兜底。

补丁：判定前先把 URL 规范化为 path（new URL(url).pathname），并对
basePath 缺失回退 serverPath。幂等：已打补丁则跳过；原文件自动备份。

用法：python deploy/patch_appium_base_driver.py [--revert]
"""
import glob
import os
import shutil
import sys
import time

MARK = '__avoidUrl'
OLD_SNIPPET = "const normalizedUrl = url.replace(new RegExp(`^${support_1.util.escapeRegExp(this.basePath)}`), '');"
NEW_SNIPPET = (
    "let __avoidUrl = url;\n"
    "            try { __avoidUrl = new URL(url).pathname; } catch { /* patched: url 可能是完整 URL */ }\n"
    "            const normalizedUrl = __avoidUrl.replace(new RegExp(`^${support_1.util.escapeRegExp(this.basePath ?? this.serverPath ?? '')}`), '');"
)

HOME = os.path.expanduser('~')


def candidate_files():
    """base-driver 可能的安装位置（appium 主程序目录优先）。"""
    pats = [
        os.path.join(HOME, 'appium2', 'node_modules', '@appium', 'base-driver',
                     'build', 'lib', 'basedriver', 'core.js'),
        os.path.join(HOME, '.appium', 'node_modules', '@appium', 'base-driver',
                     'build', 'lib', 'basedriver', 'core.js'),
        os.path.join(HOME, 'node_modules', '@appium', 'base-driver',
                     'build', 'lib', 'basedriver', 'core.js'),
    ]
    out = [p for p in pats if os.path.isfile(p)]
    if not out:  # 兜底：全局搜一次
        out = glob.glob(os.path.join(HOME, '*', 'node_modules', '@appium', 'base-driver',
                                     'build', 'lib', 'basedriver', 'core.js'))
    return out


def main():
    revert = '--revert' in sys.argv
    files = candidate_files()
    if not files:
        print('未找到 @appium/base-driver（跳过，Appium 可能未安装）')
        return 0
    rc = 0
    for path in files:
        with open(path, encoding='utf-8') as f:
            s = f.read()
        if revert:
            bak = sorted(glob.glob(path + '.orig-*'))
            if bak:
                shutil.copyfile(bak[-1], path)
                print('已还原: %s（用备份 %s）' % (path, os.path.basename(bak[-1])))
            else:
                print('无备份可还原: %s' % path)
                rc = 1
            continue
        if MARK in s:
            print('已是补丁版（跳过）: %s' % path)
            continue
        if OLD_SNIPPET not in s:
            print('!! 未匹配到目标代码（Appium 版本可能已更新，人工确认）: %s' % path)
            rc = 1
            continue
        bak = '%s.orig-%s' % (path, time.strftime('%Y%m%d_%H%M%S'))
        shutil.copyfile(path, bak)
        s2 = s.replace(OLD_SNIPPET, NEW_SNIPPET)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(s2)
        print('补丁完成: %s（备份 %s）' % (path, os.path.basename(bak)))
    if not revert:
        print('说明：该补丁修复的是 Appium 3.7.0 / base-driver 10.8.0 的上游缺陷，'
              '升级 Appium 后需重跑本脚本。还原：--revert')
    return rc


if __name__ == '__main__':
    sys.exit(main())
