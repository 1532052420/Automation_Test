# -*- coding: utf-8 -*-
"""加载并校验压测 YAML 配置。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "load_test_config.yaml"

_VALID_MODES = frozenset({"staircase", "pulse"})
_VALID_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
)


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path or os.environ.get("LOAD_TEST_CONFIG", DEFAULT_CONFIG))
    if not path.is_file():
        raise FileNotFoundError(f"压测配置文件不存在: {path}")

    with path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    _apply_defaults(cfg)
    _validate(cfg)
    cfg["_config_path"] = str(path.resolve())
    return cfg


def _apply_defaults(cfg: dict[str, Any]) -> None:
    cfg.setdefault("mode", "staircase")
    cfg.setdefault("common", {})
    cfg.setdefault("request", {})
    cfg.setdefault("staircase", {})
    cfg.setdefault("pulse", {})
    cfg.setdefault("report", {})

    common = cfg["common"]
    common.setdefault("host", "http://127.0.0.1")
    common.setdefault("vu", 50)
    common.setdefault("loop_count", 0)
    common.setdefault("run_time", "5m")
    common.setdefault("spawn_rate", 10)
    common.setdefault("wait_time_min", 0)
    common.setdefault("wait_time_max", 0)

    req = cfg["request"]
    req.setdefault("path", "/")
    req.setdefault("method", "GET")
    req.setdefault("headers", {})
    req.setdefault("params", {})
    req.setdefault("body", "")
    req.setdefault("timeout", 30)
    req.setdefault("validate_status", True)
    req.setdefault("dynamic_fields", {})
    dynamic = req["dynamic_fields"]
    dynamic.setdefault("random_user_id", {})
    ruid = dynamic["random_user_id"]
    ruid.setdefault("enabled", False)
    ruid.setdefault("field_name", "userId")
    ruid.setdefault("digits", 16)
    ruid.setdefault("as_string", True)

    stair = cfg["staircase"]
    stair.setdefault("start_users", 10)
    stair.setdefault("step_users", 10)
    stair.setdefault("step_duration", 60)
    stair.setdefault("ramp_duration", "")
    stair.setdefault("spawn_rate", common["spawn_rate"])

    pulse = cfg["pulse"]
    pulse.setdefault("baseline_users", 20)
    pulse.setdefault("peak_users", 100)
    pulse.setdefault("peak_duration", 10)
    pulse.setdefault("pulse_interval", 60)
    pulse.setdefault("peak_spawn_rate", 50)
    pulse.setdefault("baseline_spawn_rate", common["spawn_rate"])

    report = cfg["report"]
    report.setdefault("output_path", "reports/load_test_report.html")
    report.setdefault("capture_response_body", False)
    report.setdefault("response_body_max_len", 500)
    report.setdefault("max_samples", 10000)


def _validate(cfg: dict[str, Any]) -> None:
    mode = str(cfg.get("mode", "")).lower()
    if mode not in _VALID_MODES:
        raise ValueError(f"mode 必须为 {_VALID_MODES}，当前: {mode!r}")
    cfg["mode"] = mode

    method = str(cfg["request"].get("method", "GET")).upper()
    if method not in _VALID_METHODS:
        raise ValueError(f"不支持的 HTTP 方法: {method}")
    cfg["request"]["method"] = method

    if cfg["common"]["vu"] < 1:
        raise ValueError("common.vu 必须 >= 1")

    if cfg["mode"] == "pulse":
        p = cfg["pulse"]
        if p["peak_users"] < p["baseline_users"]:
            raise ValueError("pulse.peak_users 应 >= pulse.baseline_users")
        if p["peak_duration"] > p["pulse_interval"]:
            raise ValueError("pulse.peak_duration 不应大于 pulse.pulse_interval")

    if cfg["mode"] == "staircase":
        stair = cfg["staircase"]
        step_users = int(stair.get("step_users", 0))
        step_duration = float(stair.get("step_duration", 0))
        spawn_rate = float(stair.get("spawn_rate", cfg["common"].get("spawn_rate", 1)))
        if step_users > 0 and step_duration > 0:
            min_rate = step_users / step_duration
            if spawn_rate < min_rate:
                import warnings

                warnings.warn(
                    f"staircase.spawn_rate({spawn_rate}) 偏低，建议 >= {min_rate:.1f} "
                    f"（每档 +{step_users} 人 / {step_duration}s），否则实际并发可能低于计划",
                    stacklevel=2,
                )
