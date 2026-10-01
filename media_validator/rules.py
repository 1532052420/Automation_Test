# -*- coding: utf-8 -*-
"""媒体产物检测 · 检测规则（独立模块，不依赖框架任何代码）

方案第 6 节的检测项在此落成「可编辑阈值」：每类媒体一套默认规则，用户检测前可改，
规则快照随任务存档，报告里逐项展示「规则 → 实测」。

键值约定：
- 值为 None = 该项不设阈值（只报告实测值，不判定）；
- 布尔开关默认开启的是方案列为检测项、且「缺失即缺陷」的项（轨道/完整性）；
- engine.py 保证规则不合法时回退默认值，不会因坏输入崩溃。
"""
import numbers

# 每类媒体的默认规则（API /api/rules 原样下发，前端据此渲染表单）
DEFAULT_RULES = {
    'audio': {
        'integrity': True,        # 文件完整性（全量解码扫描）
        'require_track': True,    # 必须存在音频轨
        'duration_min': None,     # 时长下限（秒）
        'duration_max': None,     # 时长上限（秒）
        'require_sound': True,    # 不得是纯静音（数字零样本）
        'max_silence': 10.0,      # 最长静音段上限（秒）
        'min_sample_rate': None,  # 采样率下限（Hz）
        'min_channels': None,     # 声道数下限
    },
    'video': {
        'integrity': True,          # 文件完整性（全量解码扫描）
        'require_video_track': True,
        'require_audio_track': True,
        'duration_min': None,
        'duration_max': None,
        'min_width': None,          # 分辨率下限（宽）
        'min_height': None,         # 分辨率下限（高）
        'min_fps': 12.0,            # 帧率下限（fps，报告实测）
        'max_black': 1.0,           # 最长黑屏段上限（秒）
        'max_freeze': 3.0,          # 最长冻结帧段上限（秒）
    },
    'image': {
        'integrity': True,          # 文件完整性（解码校验）
        'min_width': None,
        'min_height': None,
        'max_file_mb': 100.0,       # 文件大小上限（MB）
        'detect_blank': True,       # 空白/纯色图判定（AI 生图最常见的"无报错空图"缺陷）
    },
}

# 方案第 5 节：支持的格式白名单（扩展名 → 媒体类型）
EXT_TYPES = {
    'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'webp': 'image',
    'mp3': 'audio', 'wav': 'audio', 'm4a': 'audio',
    'mp4': 'video', 'mov': 'video', 'mkv': 'video',
}

TYPE_LABELS = {'audio': '音频', 'video': '视频', 'image': '图片'}

# 规则键 →（类型，下限钳制）：sanitize 用，超出即回退默认值
_LIMITS = {
    'duration_min': (float, 0.0), 'duration_max': (float, 0.0),
    'max_silence': (float, 0.5), 'min_sample_rate': (float, 0.0),
    'min_channels': (float, 0.0), 'min_fps': (float, 0.0),
    'min_width': (float, 0.0), 'min_height': (float, 0.0),
    'max_black': (float, 0.5), 'max_freeze': (float, 1.0),
    'max_file_mb': (float, 0.0005),
}


def media_type_of(filename):
    """扩展名 → 媒体类型（audio/video/image），白名单外返回 None"""
    ext = (filename or '').rsplit('.', 1)
    if len(ext) != 2:
        return None
    return EXT_TYPES.get(ext[1].lower())


def sanitize(media_type, raw):
    """把外部传入的规则清洗成本类型合法快照：只收已知键，类型/下限不对回退默认值"""
    base = DEFAULT_RULES.get(media_type) or {}
    if not isinstance(raw, dict):
        return dict(base)
    out = dict(base)
    for key, default in base.items():
        if key not in raw or key in ('integrity',):
            continue
        val = raw[key]
        if isinstance(default, bool):
            out[key] = bool(val) if isinstance(val, bool) else default
        elif key in _LIMITS:
            kind, floor = _LIMITS[key]
            num = val if isinstance(val, numbers.Number) and not isinstance(val, bool) else None
            if num is None:
                out[key] = None       # 显式 null = 关闭该阈值
            else:
                try:
                    num = kind(float(num))
                except (TypeError, ValueError):
                    out[key] = default
                else:
                    out[key] = None if num < floor else num
    return out
