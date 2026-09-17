# -*- coding: utf-8 -*-
"""根据配置构建每次请求的 body（支持 userId 等字段随机化）。"""

from __future__ import annotations

import json
import secrets
from typing import Any


def _is_enabled(value: object) -> bool:
    """兼容 YAML 中 true / \"true\" / yes / 1 等写法。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return False


def random_digits(digits: int) -> str:
    """生成指定位数的纯数字字符串（首位不为 0，保证位数）。"""
    digits = max(1, int(digits))
    if digits == 1:
        return str(secrets.randbelow(10))
    first = str(secrets.randbelow(9) + 1)
    rest = "".join(str(secrets.randbelow(10)) for _ in range(digits - 1))
    return first + rest


def apply_dynamic_fields(body_raw: str, req_cfg: dict[str, Any]) -> str:
    """
    对 JSON 请求体应用动态字段替换。
    未开启或 body 非 JSON 时原样返回。
    """
    body_raw = (body_raw or "").strip()
    if not body_raw:
        return body_raw

    dynamic = req_cfg.get("dynamic_fields") or {}
    random_user = dynamic.get("random_user_id") or {}
    if not _is_enabled(random_user.get("enabled", False)):
        return body_raw

    try:
        payload = json.loads(body_raw)
    except json.JSONDecodeError:
        return body_raw

    if not isinstance(payload, dict):
        return body_raw

    field_name = str(random_user.get("field_name", "userId"))
    digit_count = int(random_user.get("digits", 16))
    as_string = bool(random_user.get("as_string", True))

    value = random_digits(digit_count)
    payload[field_name] = value if as_string else int(value)

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_request_body(req_cfg: dict[str, Any]) -> tuple[str, dict | None, str | None]:
    """
    返回 (body_raw, json_obj, data_str)：
    - json_obj 非空时以 JSON 发送
    - data_str 非空时以纯文本发送
    """
    body_raw = apply_dynamic_fields(req_cfg.get("body") or "", req_cfg)
    if not body_raw:
        return "", None, None

    headers = req_cfg.get("headers") or {}
    content_type = str(headers.get("Content-Type", "")).lower()
    if "json" in content_type:
        try:
            return body_raw, json.loads(body_raw), None
        except json.JSONDecodeError:
            return body_raw, None, body_raw
    return body_raw, None, body_raw
