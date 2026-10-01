"""rendercheck -- assertions for AI-generated media.（供应商化裁剪版）

上游：https://github.com/rogermsc/rendercheck（MIT License，见同目录 LICENSE）。
本目录为 vendored 静态副本，仅保留**确定性检测核心**（无网络、无密钥、无第三方依赖）：
_core / _ffmpeg / media / captions / text / lipsync。

相对上游的改动（详见 ../VENDOR.md）：
- 删除 cli.py / mcp.py / demo.py / vision.py（AI 网络层）/ config.py / presets.py
  及全部发布身份文件；__init__ 只导出确定性 API；
- _ffmpeg.py 两处 zip(..., strict=False) 去掉 strict 参数（语义等价），
  兼容本平台运行时 Python 3.8。
"""

from ._core import SilentFail, Skipped, collect_skips
from .media import (
    assert_audio_format,
    assert_captions_aligned,
    assert_duration,
    assert_format,
    assert_has_sound,
    assert_lip_sync,
    assert_loudness,
    assert_loudness_range,
    assert_no_black_frames,
    assert_no_clipping,
    assert_no_dead_air,
    assert_no_truncation,
    assert_not_blank,
    assert_not_frozen,
    assert_pace,
    assert_streams_aligned,
)

__version__ = "0.4.1"

__all__ = [
    "SilentFail",
    "Skipped",
    "assert_audio_format",
    "assert_captions_aligned",
    "assert_duration",
    "assert_format",
    "assert_has_sound",
    "assert_lip_sync",
    "assert_loudness",
    "assert_loudness_range",
    "assert_no_black_frames",
    "assert_no_clipping",
    "assert_no_dead_air",
    "assert_no_truncation",
    "assert_not_blank",
    "assert_not_frozen",
    "assert_pace",
    "assert_streams_aligned",
    "collect_skips",
]
