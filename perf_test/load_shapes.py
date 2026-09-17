# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

from locust import LoadTestShape

logger = logging.getLogger(__name__)

# 由 locustfile 在 events.init 中注入
ACTIVE_CONFIG: dict[str, Any] | None = None


def _parse_run_time_seconds(run_time: str | int | float) -> float:
    """将 30s / 5m / 1h30m 或 Locust CLI 传入的秒数(int) 转为秒。"""
    if isinstance(run_time, (int, float)):
        return float(run_time)
    run_time = (run_time or "0s").strip().lower()
    if run_time.isdigit():
        return float(run_time)

    total = 0.0
    num = ""
    for ch in run_time:
        if ch.isdigit() or ch == ".":
            num += ch
        elif ch in ("h", "m", "s") and num:
            val = float(num)
            if ch == "h":
                total += val * 3600
            elif ch == "m":
                total += val * 60
            else:
                total += val
            num = ""
    if num:
        total += float(num)
    return total if total > 0 else 0.0


def _cfg() -> dict[str, Any]:
    if ACTIVE_CONFIG is None:
        raise RuntimeError("压测配置未初始化，请检查 events.init 是否正常执行")
    return ACTIVE_CONFIG


def _effective_run_time(run_time: float, ramp_duration: float) -> float:
    if ramp_duration > 0 and run_time >= ramp_duration:
        return max(0.0, ramp_duration - 0.001)
    return run_time


def _users_for_step(
    step_index: int, start_users: int, step_users: int, max_users: int
) -> int:
    count = start_users + step_index * step_users
    return int(min(max(count, 1), max_users))


def format_staircase_plan(config: dict[str, Any], max_rows: int = 12) -> str:
    """生成阶梯计划说明，便于启动前核对。"""
    common = config["common"]
    stair = config["staircase"]
    start = int(stair["start_users"])
    step_users = int(stair["step_users"])
    step_duration = float(stair["step_duration"])
    max_users = int(common["vu"])
    ramp_duration = _parse_run_time_seconds(stair.get("ramp_duration") or 0)
    run_time = _parse_run_time_seconds(common["run_time"])

    lines = [
        "阶梯加压计划（按配置推算）:",
        f"  起始={start}, 每档+{step_users}, 每档{step_duration}s, 上限 vu={max_users}",
    ]
    if ramp_duration > 0:
        lines.append(f"  爬坡时长={ramp_duration}s, 之后稳态保持至 run_time={run_time}s")

    step_index = 0
    t = 0.0
    shown = 0
    while t <= run_time and shown < max_rows:
        eff = _effective_run_time(t, ramp_duration)
        step_index = int(eff // step_duration) if step_duration > 0 else 0
        users = _users_for_step(step_index, start, step_users, max_users)
        lines.append(f"  T+{int(t):>4}s -> 目标并发 {users}")
        t += step_duration
        shown += 1

    if t <= run_time:
        hold_users = _users_for_step(
            int(_effective_run_time(ramp_duration or run_time, ramp_duration) // step_duration)
            if step_duration > 0
            else 0,
            start,
            step_users,
            max_users,
        )
        lines.append(f"  ... 稳态阶段保持约 {hold_users} 并发")
    return "\n".join(lines)


class StaircaseLoadShape(LoadTestShape):
    """按时间阶梯递增并发；以时间为档位依据，孵化速率在档位切换时更新。"""

    def __init__(self) -> None:
        super().__init__()
        config = _cfg()
        common = config["common"]
        stair = config["staircase"]
        self.time_limit = _parse_run_time_seconds(common["run_time"])
        self.max_users = int(common["vu"])
        self.start_users = int(stair["start_users"])
        self.step_users = int(stair["step_users"])
        self.step_duration = float(stair["step_duration"])
        self.spawn_rate = float(stair.get("spawn_rate", common["spawn_rate"]))
        ramp_raw = stair.get("ramp_duration") or ""
        self.ramp_duration = (
            _parse_run_time_seconds(ramp_raw) if ramp_raw else 0.0
        )
        self._last_logged_target = -1
        self._cached_spawn_rate = self.spawn_rate

    def _step_index_by_time(self, run_time: float) -> int:
        effective_time = _effective_run_time(run_time, self.ramp_duration)
        if self.step_duration <= 0:
            return 0
        return int(effective_time // self.step_duration)

    def _calc_spawn_rate(self, user_count: int, actual_users: int, step_index: int, run_time: float) -> float:
        """按与目标的差距估算孵化速率；仅在档位变化时更新，避免 Locust 每秒重启孵化。"""
        delta = max(0, user_count - actual_users)
        if delta <= 0:
            return self.spawn_rate

        effective_time = _effective_run_time(run_time, self.ramp_duration)
        time_in_step = effective_time - step_index * self.step_duration
        if time_in_step >= self.step_duration:
            # 实际人数落后时间计划：尽快追平，但保持本档位内 spawn_rate 稳定
            remaining = 1.0
        else:
            remaining = max(self.step_duration - time_in_step, 1.0)
        required = delta / remaining
        return max(self.spawn_rate, required, 1.0)

    def tick(self) -> tuple[int, float] | None:
        run_time = self.get_run_time()
        if self.time_limit and run_time >= self.time_limit:
            return None

        if self.step_duration <= 0:
            user_count = self.max_users
            return int(user_count), self.spawn_rate

        step_index = self._step_index_by_time(run_time)
        user_count = _users_for_step(
            step_index, self.start_users, self.step_users, self.max_users
        )
        actual_users = self.runner.user_count if self.runner is not None else 0

        # Locust shape_worker 仅在 tick 返回值变化时调用 start()；若 spawn_rate 每秒变化
        # 会反复 kill 孵化协程导致并发卡住。因此仅在目标档位变化时重算 spawn_rate。
        if user_count != self._last_logged_target:
            self._cached_spawn_rate = self._calc_spawn_rate(
                user_count, actual_users, step_index, run_time
            )
            logger.info(
                "阶梯目标: %d 并发 (档位=%d, 已运行=%.0fs, 当前实际=%d, spawn_rate=%.1f)",
                user_count,
                step_index,
                run_time,
                actual_users,
                self._cached_spawn_rate,
            )
            if actual_users < user_count - self.step_users:
                logger.warning(
                    "并发滞后: 目标=%d 实际=%d 差距=%d，将按 spawn_rate=%.1f 追赶"
                    "（若长期无改善请检查 CPU/网络或分布式加压）",
                    user_count,
                    actual_users,
                    user_count - actual_users,
                    self._cached_spawn_rate,
                )
            self._last_logged_target = user_count

        return int(user_count), float(self._cached_spawn_rate)


class PulseLoadShape(LoadTestShape):
    """短周期尖峰 + 基准并发，模拟秒杀洪峰。"""

    def __init__(self) -> None:
        super().__init__()
        config = _cfg()
        common = config["common"]
        pulse = config["pulse"]
        self.time_limit = _parse_run_time_seconds(common["run_time"])
        self.baseline_users = int(pulse["baseline_users"])
        self.peak_users = int(pulse["peak_users"])
        self.peak_duration = float(pulse["peak_duration"])
        self.pulse_interval = float(pulse["pulse_interval"])
        self.peak_spawn_rate = float(pulse["peak_spawn_rate"])
        self.baseline_spawn_rate = float(pulse["baseline_spawn_rate"])

    def tick(self) -> tuple[int, float] | None:
        run_time = self.get_run_time()
        if self.time_limit and run_time >= self.time_limit:
            return None

        if self.pulse_interval <= 0:
            return self.peak_users, self.peak_spawn_rate

        pos_in_cycle = run_time % self.pulse_interval
        if pos_in_cycle < self.peak_duration:
            return self.peak_users, self.peak_spawn_rate
        return self.baseline_users, self.baseline_spawn_rate


def resolve_shape_class(mode: str) -> type[LoadTestShape]:
    if mode == "staircase":
        return StaircaseLoadShape
    return PulseLoadShape
