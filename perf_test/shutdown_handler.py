# -*- coding: utf-8 -*-
"""Ctrl+C 快速停止：先停压测，再退出；再次 Ctrl+C 强制退出。"""

from __future__ import annotations

import os
import signal
import threading
from typing import Callable

import gevent

_installed = False
_lock = threading.Lock()
_interrupt_count = 0


def reset_shutdown_state() -> None:
    """新一次压测启动前重置（避免同进程或异常退出后状态残留）。"""
    global _installed, _interrupt_count
    _installed = False
    with _lock:
        _interrupt_count = 0


def _stop_runner(runner) -> None:
    shape = getattr(runner, "shape_greenlet", None)
    if shape is not None and not shape.dead:
        try:
            shape.kill(block=False)
        except Exception:
            pass
    spawning = getattr(runner, "spawning_greenlet", None)
    if spawning is not None and not spawning.dead:
        try:
            spawning.kill(block=False)
        except Exception:
            pass
    try:
        runner.quit()
    except Exception:
        try:
            runner.stop()
        except Exception:
            pass


def install_interrupt_handler(
    environment,
    *,
    on_interrupt: Callable[[], None] | None = None,
) -> None:
    global _installed
    if _installed:
        return
    _installed = True

    def handle_sigint(*_args) -> None:
        global _interrupt_count
        with _lock:
            _interrupt_count += 1
            count = _interrupt_count

        if count >= 2:
            print("\n[中断] 再次 Ctrl+C，强制退出", flush=True)
            os._exit(130)

        print("\n[中断] 正在停止压测（再次 Ctrl+C 可立即强制退出）…", flush=True)

        if on_interrupt:
            try:
                on_interrupt()
            except Exception:
                pass

        environment.process_exit_code = 130

        # 必须先停掉虚拟用户，再生成报告（报告在 test_stop / quitting 里生成）
        runner = getattr(environment, "runner", None)
        if runner is not None:
            _stop_runner(runner)

    try:
        gevent.signal_handler(signal.SIGINT, handle_sigint)
    except Exception:
        signal.signal(signal.SIGINT, lambda _s, _f: handle_sigint())
