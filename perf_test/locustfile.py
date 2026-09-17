# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import random
import sys
import threading
from pathlib import Path

# 保证同目录模块可导入
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from locust import HttpUser, events, task
from locust.env import Environment

from config_loader import load_config
import load_shapes as load_shapes_mod
from load_shapes import format_staircase_plan, resolve_shape_class
from metrics_collector import MetricsCollector
from report_generator import generate_html_report
from request_body_builder import build_request_body
from shutdown_handler import install_interrupt_handler, reset_shutdown_state

# 全局：启动时注入
_CONFIG: dict | None = None
_COLLECTOR: MetricsCollector | None = None
_REPORT_LOCK = threading.Lock()
_REPORT_WRITTEN = False
_USER_INTERRUPTED = False


def _get_config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        path = os.environ.get("LOAD_TEST_CONFIG")
        _CONFIG = load_config(path)
    return _CONFIG


def _get_collector() -> MetricsCollector:
    global _COLLECTOR
    if _COLLECTOR is None:
        _COLLECTOR = MetricsCollector(_get_config())
    return _COLLECTOR


@events.init_command_line_parser.add_listener
def _add_cli(parser) -> None:
    parser.add_argument(
        "--test-config",
        type=str,
        default="",
        help="压测 YAML 配置文件路径（勿用 --config，会与 Locust 内置 locust.conf 冲突）",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["staircase", "pulse"],
        default="",
        help="压测模式：staircase=阶梯加压，pulse=脉冲峰值（覆盖配置文件）",
    )


@events.init.add_listener
def _on_init(environment: Environment, **kwargs) -> None:
    global _CONFIG, _COLLECTOR, _REPORT_WRITTEN, _USER_INTERRUPTED
    reset_shutdown_state()
    _REPORT_WRITTEN = False
    _USER_INTERRUPTED = False

    opts = environment.parsed_options
    config_path = getattr(opts, "test_config", None) or os.environ.get("LOAD_TEST_CONFIG")
    if config_path:
        os.environ["LOAD_TEST_CONFIG"] = config_path

    _CONFIG = load_config(config_path or None)
    mode_override = getattr(opts, "mode", None) or ""
    if mode_override:
        _CONFIG["mode"] = mode_override

    run_time_cli = getattr(opts, "run_time", None) or ""
    if run_time_cli:
        _CONFIG["common"]["run_time"] = run_time_cli

    _COLLECTOR = MetricsCollector(_CONFIG)
    _COLLECTOR.mark_start()

    load_shapes_mod.ACTIVE_CONFIG = _CONFIG
    environment.shape_class = resolve_shape_class(_CONFIG["mode"])()

    common = _CONFIG["common"]
    environment.host = common["host"].rstrip("/")

    from urllib.parse import urlencode

    req = _CONFIG.get("request", {})
    base = f"{environment.host}{req.get('path', '/')}"
    query = urlencode(req.get("params") or {})
    print(f"目标 URL: {base}{'?' + query if query else ''}")
    print(f"请求方法: {req.get('method', 'GET')}")

    if _CONFIG["mode"] == "staircase":
        print(format_staircase_plan(_CONFIG))
        print("-" * 60)

    def _on_user_interrupt() -> None:
        global _USER_INTERRUPTED
        _USER_INTERRUPTED = True

    install_interrupt_handler(environment, on_interrupt=_on_user_interrupt)


def _wait_time_from_config(w_min: float, w_max: float):
    """生成无参 wait_time 函数，兼容 Locust task.py 的 user.wait_time() 调用。"""
    if w_min <= 0 and w_max <= 0:
        return lambda: 0.0
    lo, hi = min(w_min, w_max), max(w_min, w_max)
    return lambda: lo + random.random() * (hi - lo)


class LoadTestHttpUser(HttpUser):
    """可配置 HTTP 虚拟用户。"""

    abstract = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._loop_count = 0

    def on_start(self) -> None:
        cfg = _get_config()
        w_min = float(cfg["common"].get("wait_time_min", 0))
        w_max = float(cfg["common"].get("wait_time_max", 0))
        self.wait_time = _wait_time_from_config(w_min, w_max)

    @task
    def configured_request(self) -> None:
        cfg = _get_config()
        common = cfg["common"]
        req_cfg = cfg["request"]
        max_loops = int(common.get("loop_count", 0))

        if max_loops > 0 and self._loop_count >= max_loops:
            self.stop(True)
            return

        method = req_cfg["method"]
        path = req_cfg["path"]
        headers = dict(req_cfg.get("headers") or {})
        params = dict(req_cfg.get("params") or {})
        timeout = float(req_cfg.get("timeout", 30))
        validate = bool(req_cfg.get("validate_status", True))
        name = f"{method} {path}"

        body_raw, body_json, body_data = build_request_body(req_cfg)

        kwargs: dict = {
            "headers": headers,
            "timeout": timeout,
            "name": name,
            "catch_response": True,
        }
        if params:
            kwargs["params"] = params
        if method in ("POST", "PUT", "PATCH") and body_raw:
            if body_json is not None:
                kwargs["json"] = body_json
            elif body_data is not None:
                kwargs["data"] = body_data

        start = __import__("time").perf_counter()
        error_msg = ""
        success = True
        status_code = None
        resp_text = ""
        resp_len = 0

        try:
            client_method = getattr(self.client, method.lower(), None)
            if client_method is None:
                raise ValueError(f"不支持的 HTTP 方法: {method}")
            with client_method(path, **kwargs) as response:
                status_code = response.status_code
                resp_len = len(response.content or b"")
                body_max = int(
                    cfg.get("report", {}).get("response_body_max_len", 500)
                )
                resp_text = (response.text or "")[:body_max]

                if validate and not (200 <= status_code < 300):
                    success = False
                    error_msg = f"HTTP {status_code}"
                    response.failure(error_msg)
                else:
                    response.success()
        except Exception as exc:
            success = False
            error_msg = str(exc)[:500]

        elapsed_ms = (__import__("time").perf_counter() - start) * 1000.0
        url = f"{self.host}{path}"

        _get_collector().record(
            name=name,
            method=method,
            url=url,
            status_code=status_code,
            response_time_ms=elapsed_ms,
            success=success,
            error_message=error_msg,
            request_headers=headers,
            request_body=body_raw,
            response_body=resp_text,
            response_length=resp_len,
        )

        self._loop_count += 1
        if max_loops > 0 and self._loop_count >= max_loops:
            self.stop(True)


# Locust 需要具体 User 类（非 abstract）
class HttpLoadUser(LoadTestHttpUser):
    pass


def _finalize_report(*, interrupted: bool = False) -> None:
    """正常结束 / Ctrl+C / 异常退出时生成报告（仅执行一次）。"""
    global _REPORT_WRITTEN, _USER_INTERRUPTED
    interrupted = interrupted or _USER_INTERRUPTED
    with _REPORT_LOCK:
        if _REPORT_WRITTEN:
            return
        if _COLLECTOR is None or _CONFIG is None:
            return

        _COLLECTOR.mark_end()
        agg = _COLLECTOR.get_aggregate()
        if agg.total_requests == 0:
            print("\n[压测报告] 尚无请求数据，未生成 HTML（请确认压测已发出至少 1 次请求）\n")
            _REPORT_WRITTEN = True
            return

        cfg = dict(_CONFIG)
        cfg["_interrupted"] = interrupted
        report_path = cfg.get("report", {}).get("output_path", "reports/load_test_report.html")
        try:
            out = generate_html_report(_COLLECTOR, cfg, report_path)
            reason = "手动中断 (Ctrl+C)" if interrupted else "正常结束"
            print(f"\n[压测报告] HTML 已生成 ({reason}): {out}\n")
        except Exception as exc:
            print(f"\n[压测报告] 生成失败: {exc}\n")
        _REPORT_WRITTEN = True


@events.test_stop.add_listener
def _on_test_stop(environment: Environment, **kwargs) -> None:
    _finalize_report(interrupted=False)


@events.quitting.add_listener
def _on_quitting(environment: Environment, **kwargs) -> None:
    """Ctrl+C 或进程退出时触发（若 test_stop 已生成报告则跳过）。"""
    _finalize_report(interrupted=True)


