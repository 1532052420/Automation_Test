# -*- coding: utf-8 -*-
"""escrcpy 投屏控制台 · 独立项目启动器

escrcpy（https://github.com/viarotel-org/escrcpy）是 Electron 桌面应用：
scrcpy 的图形化封装（实时镜像/控制/录屏/截图/群控/AI 助手）。
它不是 web 服务——本模块只负责：检测安装状态、清 quarantine、一键拉起桌面 App。

目录约定：escrcpy.app 解压在本目录（escrcpy/Escrcpy.app）；
平台通过 web_platform/routes.py 的 /api/escrcpy/* 接口调用这里（惰性导入，缺目录不影响远端）。
"""
import glob
import os
import subprocess
import time

BASE = os.path.dirname(os.path.abspath(__file__))
OPEN = '/usr/bin/open'
XATTR = '/usr/bin/xattr'


def app_path():
    """定位 Escrcpy.app（本目录优先，兼容大小写变体）"""
    candidates = sorted(glob.glob(os.path.join(BASE, '*.app')))
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


def is_running():
    out = subprocess.run(['pgrep', '-f', r'Escrcpy\.app/Contents/MacOS'],
                         capture_output=True, text=True, timeout=8).stdout
    return bool(out.strip())


def status():
    app = app_path()
    return {
        'installed': bool(app),
        'app_path': app,
        'running': is_running(),
    }


def launch():
    """拉起桌面 App。首次运行清 quarantine（浏览器下载会带标记，否则 macOS 拒绝启动）。"""
    app = app_path()
    if not app:
        return False, 'escrcpy 尚未部署：escrcpy/ 目录下没有 Escrcpy.app（见 README.md 下载解压步骤）'
    if os.path.exists(XATTR):
        subprocess.run([XATTR, '-cr', app], capture_output=True, timeout=30)
    subprocess.run([OPEN, app], capture_output=True, timeout=30)
    # 等进程真正起来（最多 8 秒）
    deadline = time.time() + 8
    while time.time() < deadline:
        if is_running():
            return True, app
        time.sleep(0.5)
    return False, 'escrcpy 已发出启动命令，但未检测到进程（首次启动可能需要在系统设置里允许）'
