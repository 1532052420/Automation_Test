# -*- coding: utf-8 -*-
"""
压测过程指标采集
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestSample:
    """单条请求样本，对应 JMeter View Results Tree 一行。"""

    timestamp: float
    name: str
    method: str
    url: str
    status_code: int | None
    response_time_ms: float
    success: bool
    error_message: str
    request_headers: str
    request_body: str
    response_body: str
    response_length: int


@dataclass
class AggregateMetrics:
    total_requests: int = 0
    success_count: int = 0
    fail_count: int = 0
    total_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    response_times_ms: list[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.fail_count / self.total_requests * 100.0

    @property
    def avg_response_time_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time_ms / self.total_requests

    def percentile(self, p: float) -> float:
        if not self.response_times_ms:
            return 0.0
        sorted_rt = sorted(self.response_times_ms)
        idx = int(len(sorted_rt) * p / 100.0) - 1
        idx = max(0, min(idx, len(sorted_rt) - 1))
        return sorted_rt[idx]

    @property
    def tps(self) -> float:
        if self.duration_sec <= 0:
            return 0.0
        return self.total_requests / self.duration_sec

    duration_sec: float = 0.0


class MetricsCollector:
    """线程安全的全局指标与样本收集器。"""

    def __init__(self, config: dict[str, Any]) -> None:
        self._lock = threading.Lock()
        self._report_cfg = config.get("report", {})
        self._max_samples = int(self._report_cfg.get("max_samples", 8000))
        self._capture_body = bool(self._report_cfg.get("capture_response_body", False))
        self._body_max_len = int(self._report_cfg.get("response_body_max_len", 500))

        self._samples: deque[RequestSample] = deque(maxlen=self._max_samples)
        self._aggregate = AggregateMetrics()
        self._rt_cap = 100_000
        self._start_time: float | None = None
        self._end_time: float | None = None
        self._time_series: list[dict[str, Any]] = []
        self._bucket_sec = 1.0
        self._bucket_counts: dict[int, dict[str, int | float]] = {}

        self.mode = config.get("mode", "")
        self.config_snapshot = {
            "mode": config.get("mode"),
            "host": config.get("common", {}).get("host"),
            "vu": config.get("common", {}).get("vu"),
            "run_time": config.get("common", {}).get("run_time"),
        }

    def mark_start(self) -> None:
        with self._lock:
            self._start_time = time.time()

    def mark_end(self) -> None:
        with self._lock:
            self._end_time = time.time()
            if self._start_time and self._end_time:
                self._aggregate.duration_sec = self._end_time - self._start_time

    def record(
        self,
        *,
        name: str,
        method: str,
        url: str,
        status_code: int | None,
        response_time_ms: float,
        success: bool,
        error_message: str = "",
        request_headers: dict | None = None,
        request_body: str = "",
        response_body: str = "",
        response_length: int = 0,
    ) -> None:
        ts = time.time()
        headers_str = str(request_headers or {})
        body_snippet = ""
        if self._capture_body and response_body:
            body_snippet = response_body[: self._body_max_len]

        sample = RequestSample(
            timestamp=ts,
            name=name,
            method=method,
            url=url,
            status_code=status_code,
            response_time_ms=response_time_ms,
            success=success,
            error_message=error_message or "",
            request_headers=headers_str,
            request_body=(request_body or "")[: self._body_max_len],
            response_body=body_snippet,
            response_length=response_length,
        )

        with self._lock:
            self._samples.append(sample)
            self._aggregate.total_requests += 1
            if success:
                self._aggregate.success_count += 1
            else:
                self._aggregate.fail_count += 1
            self._aggregate.total_response_time_ms += response_time_ms
            if len(self._aggregate.response_times_ms) < self._rt_cap:
                self._aggregate.response_times_ms.append(response_time_ms)

            if self._aggregate.min_response_time_ms == 0 or response_time_ms < self._aggregate.min_response_time_ms:
                self._aggregate.min_response_time_ms = response_time_ms
            if response_time_ms > self._aggregate.max_response_time_ms:
                self._aggregate.max_response_time_ms = response_time_ms

            if self._start_time:
                bucket = int((ts - self._start_time) // self._bucket_sec)
                b = self._bucket_counts.setdefault(
                    bucket, {"ok": 0, "fail": 0, "total_ms": 0.0, "count": 0}
                )
                b["count"] = int(b["count"]) + 1
                b["total_ms"] = float(b["total_ms"]) + response_time_ms
                if success:
                    b["ok"] = int(b["ok"]) + 1
                else:
                    b["fail"] = int(b["fail"]) + 1

    def build_time_series(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._start_time:
                return []
            series = []
            for bucket in sorted(self._bucket_counts.keys()):
                b = self._bucket_counts[bucket]
                count = int(b["count"])
                tps = count / self._bucket_sec
                avg_ms = float(b["total_ms"]) / count if count else 0
                fail = int(b["fail"])
                err_rate = (fail / count * 100.0) if count else 0.0
                series.append(
                    {
                        "second": bucket,
                        "tps": round(tps, 2),
                        "avg_ms": round(avg_ms, 2),
                        "error_rate": round(err_rate, 2),
                    }
                )
            return series

    def get_samples(self) -> list[RequestSample]:
        with self._lock:
            return list(self._samples)

    def get_aggregate(self) -> AggregateMetrics:
        with self._lock:
            return self._aggregate
