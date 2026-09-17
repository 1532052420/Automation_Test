# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import sys


def check_stale_load_test_processes() -> list[int]:
    """返回可能残留的压测 python 进程 PID（不含当前进程）。"""
    current_pid = os.getpid()
    stale: list[int] = []

    if sys.platform != "win32":
        return stale

    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -match 'http_load_test' -and "
            "$_.CommandLine -match 'locustfile\\.py' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
        )
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line.isdigit():
                continue
            pid = int(line)
            if pid != current_pid:
                stale.append(pid)
    except Exception:
        pass

    return stale


def warn_stale_processes() -> bool:
    stale = check_stale_load_test_processes()
    if not stale:
        return False
    print(
        "\n[警告] 检测到上次可能未完全退出的压测进程，"
        f"PID: {', '.join(str(p) for p in stale)}",
        flush=True,
    )
    print(
        "  若再次运行并发异常偏高，请在任务管理器结束上述 python.exe，"
        "或执行: taskkill /PID <pid> /F\n",
        flush=True,
    )
    return True
