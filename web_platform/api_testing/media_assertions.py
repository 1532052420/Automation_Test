# -*- coding: utf-8 -*-
"""接口测试 · 音视频断言（依据《音频/视频文件内容检测技术方案》）

对外只有一个断言：「音视频检测」= media_check，检测项全部可选（留空即不检查）：
- 格式（编码，如 h264 / aac）
- 时长（范围，秒）
- 有无声音（静音阈值 dB，用 ffmpeg volumedetect；有音轨 ≠ 有声音）
- 分辨率（仅视频，音频自动跳过）
- 码率（范围 kbps，可选）

实现上是一个公共方法 check_media(path, options)：探测一次文件，按 options 里填了哪些项
逐项校验；evaluate() 只是断言字段 → options 的薄适配层（含旧断言类型兼容）。

方案里的 L4（指纹/PESQ）与 silencedetect/astats 按方案自身建议暂不引入。

工程约定（方案第六节）：
- 独立工具函数封装，不在断言里散落命令行；
- 阈值可配（跟随断言字段），不硬编码；
- 子进程 timeout=60s；失败时错误信息带上 ffprobe/ffmpeg 原始输出尾部，便于定位。
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

FFPROBE = shutil.which('ffprobe')
FFMPEG = shutil.which('ffmpeg')
MEDIA_TIMEOUT = 60          # 方案 6.3：长音频分析上限

# 静音时 ffmpeg 输出 "-inf dB"，数值化成一个必低于任何阈值的哨兵值
_NEG_INF = -999.0

# 默认静音阈值（方案推荐：max_volume 低于 -40dB 判定为静音）
DEFAULT_SOUND_THRESHOLD = -40.0

# 响应 Content-Type → 临时文件后缀（ffprobe 按内容探测，后缀仅辅助）
_EXT_BY_MIME = {
    'audio/mpeg': '.mp3', 'audio/mp3': '.mp3', 'audio/mp4': '.m4a',
    'audio/aac': '.aac', 'audio/wav': '.wav', 'audio/x-wav': '.wav',
    'audio/flac': '.flac', 'audio/ogg': '.ogg',
    'video/mp4': '.mp4', 'video/quicktime': '.mov', 'video/webm': '.webm',
}

# 分辨率写法兼容：1280x720 / 1280*720 / 1280×720 / 1280 720
_RES_SEP = re.compile(r'\s*[x*×,\s]\s*')


def _run(cmd):
    """跑探测命令，返回 (stdout, stderr, returncode)；命令不存在/超时抛 RuntimeError"""
    exe = cmd[0]
    if not shutil.which(exe):
        raise RuntimeError('%s 不可用（未安装 ffmpeg/ffprobe，无法做音视频断言）' % exe)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=MEDIA_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError('%s 分析超时（>%ds）' % (exe, MEDIA_TIMEOUT))
    return p.stdout, p.stderr, p.returncode


def materialize_response(resp):
    """把响应体落成临时文件供 ffprobe/ffmpeg 分析，返回文件路径（调用方负责删除）"""
    ctype = (resp.headers.get('content-type') or '').split(';')[0].strip().lower()
    suffix = _EXT_BY_MIME.get(ctype)
    if not suffix:
        # 从 URL 路径取扩展名兜底（如 /mock/media.wav）
        path = getattr(resp, 'url', '') or ''
        base = path.split('?')[0].rsplit('.', 1)
        suffix = '.' + base[1].lower()[:5] if len(base) == 2 and base[1].isalnum() else '.bin'
    fd, tmp = tempfile.mkstemp(suffix=suffix, prefix='avassert_')
    with os.fdopen(fd, 'wb') as f:
        f.write(resp.content or b'')
    return tmp


def _num(val):
    """字符串数字 → float，失败返回 None（ffprobe 的 bit_rate/duration 有时是 'N/A'）"""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def probe_media(path):
    """ffprobe 探测文件属性。

    返回 {'streams': [...], 'duration': float|None, 'format_bit_rate': int|None}
    每条流字段：codec_type/codec_name/sample_rate/channels/duration/bit_rate/width/height
    """
    out, err, code = _run([
        FFPROBE, '-v', 'error',
        '-show_entries',
        'stream=codec_type,codec_name,sample_rate,channels,duration,bit_rate,width,height',
        '-show_entries', 'format=duration,bit_rate',
        '-of', 'json', path,
    ])
    if code != 0:
        raise RuntimeError('ffprobe 解析失败: %s' % (err or '无输出').strip()[-300:])
    try:
        d = json.loads(out)
    except ValueError:
        raise RuntimeError('ffprobe 输出不是 JSON: %s' % out[-200:])
    streams = d.get('streams') or []
    fmt = d.get('format') or {}
    duration = None
    for src in ([s.get('duration') for s in streams] + [fmt.get('duration')]):
        v = _num(src)
        if v is not None and v > 0:
            duration = v
            break
    return {'streams': streams, 'duration': duration,
            'format_bit_rate': _num(fmt.get('bit_rate'))}


def parse_range(text):
    """解析「下限-上限」范围输入（如 '0.5-30'、'200-2000'、'1280-'、'-720'、'1.5'）

    返回 (min, max)，无法解析返回 (None, None)；单个值视为下限 = 上限。
    """
    s = str(text or '').strip()
    if not s:
        return None, None
    m = re.match(r'^(\d+(?:\.\d+)?)?\s*-\s*(\d+(?:\.\d+)?)?$', s)
    if m and (m.group(1) or m.group(2)):
        return (_num(m.group(1)), _num(m.group(2)))
    v = _num(s)
    return (v, v) if v is not None else (None, None)


def parse_resolution(text):
    """解析分辨率输入（1280x720 / 1280*720 / 1280×720 / 1280 720）→ (w, h) 或 None"""
    parts = [p for p in _RES_SEP.split(str(text or '').strip()) if p]
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return int(parts[0]), int(parts[1])
    return None


def detect_volume(path):
    """volumedetect：返回 {'max_volume': float, 'mean_volume': float}（单位 dBFS）"""
    _, err, _ = _run([FFMPEG, '-i', path, '-af', 'volumedetect', '-f', 'null', '-'])
    vol = {}
    for key in ('max_volume', 'mean_volume'):
        val = _NEG_INF
        for line in err.splitlines():
            if key in line and 'dB' in line:
                num = line.split(key + ':')[1].strip().split(' ')[0]
                val = _NEG_INF if 'inf' in num else (_num(num) if _num(num) is not None else _NEG_INF)
                break
        vol[key] = val
    if vol['max_volume'] == _NEG_INF and vol['mean_volume'] == _NEG_INF and 'mean_volume' not in err:
        raise RuntimeError('无法解析音量信息，ffmpeg 原始输出尾部: %s' % err.strip()[-300:])
    return vol


def _first_stream(streams, kind):
    for s in streams:
        if s.get('codec_type') == kind:
            return s
    return None


def _stream_actual(target, info):
    """报告里的 actual：把这条轨的关键属性摊平成能直接看懂的字段"""
    w, h = target.get('width'), target.get('height')
    br = _num(target.get('bit_rate'))
    return {
        'codec_type': target.get('codec_type'),
        'codec_name': target.get('codec_name'),
        'duration': info['duration'],
        'resolution': ('%sx%s' % (w, h)) if (w and h) else None,
        'bit_rate_kbps': round(br / 1000.0, 1) if br else None,
        'sample_rate': _num(target.get('sample_rate')),
        'channels': _num(target.get('channels')),
    }


# ---------------- 公共检测方法 ----------------
def check_media(path, options=None):
    """音视频检测的公共方法：探测一次，按 options 里填了哪些项逐项校验。

    options（全部可选，留空即不检查该项）：
        media_type   'audio'（默认）| 'video' —— 检测哪条轨；分辨率仅视频有意义，音频自动跳过
        codec        期望编码，如 h264 / aac
        duration_min / duration_max   时长范围（秒）
        resolution   期望分辨率，如 1280x720（仅视频）
        bitrate_min / bitrate_max     码率范围（kbps）
        sample_rate / channels        采样率(Hz) / 声道数（可选，同样支持区间）
        sound        静音阈值 dB —— 填了才检测「有无声音」（默认阈值 -40）
        mean_min     平均音量下限 dB（可选辅助）

    返回 (passed: bool, actual: dict, error: str|None)；只有目标轨存在、且所有填了的项都通过才算过。
    """
    o = dict(options or {})
    media_type = str(o.get('media_type') or 'audio').lower()
    kind = 'video' if media_type == 'video' else 'audio'
    label = '视频' if kind == 'video' else '音频'

    try:
        info = probe_media(path)
    except RuntimeError as e:
        return False, None, str(e)
    streams = info['streams']
    if not streams:
        return False, {'streams': []}, '文件里没有任何音视频轨（可能是 0 字节或非音视频文件）'
    target = _first_stream(streams, kind)
    if target is None:
        kinds = [s.get('codec_type') for s in streams]
        return False, {'streams': kinds}, ('文件里没有%s轨（实际只有: %s）'
                                           % (label, '、'.join(kinds) or '无'))

    actual = _stream_actual(target, info)
    errors = []

    # ① 格式（编码）
    want_codec = str(o.get('codec') or '').strip()
    if want_codec and target.get('codec_name') != want_codec:
        errors.append('格式是 %s，期望 %s' % (target.get('codec_name') or '未知', want_codec))

    # ② 时长（范围）
    for field, side, ok in (('duration_min', '下限', lambda d, v: d >= v),
                            ('duration_max', '上限', lambda d, v: d <= v)):
        if o.get(field) in (None, ''):
            continue
        limit = _num(o.get(field))
        if limit is None:
            errors.append('时长%s不是数字: %r' % (side, o.get(field)))
        elif info['duration'] is None:
            errors.append('无法获取时长')
        elif not ok(info['duration'], limit):
            errors.append('时长 %ss 不满足%s %ss' % (info['duration'], side, limit))

    # ③ 分辨率（仅视频；音频跳过）
    want_res = str(o.get('resolution') or '').strip()
    if want_res and kind == 'video':
        parsed = parse_resolution(want_res)
        if parsed is None:
            errors.append('分辨率格式应为「宽x高」，如 1280x720，当前填的是 %r' % want_res)
        elif not (target.get('width') and target.get('height')):
            errors.append('这条视频轨没有分辨率信息')
        elif (target['width'], target['height']) != parsed:
            errors.append('分辨率是 %sx%s，期望 %dx%d'
                          % (target['width'], target['height'], parsed[0], parsed[1]))

    # ④ 码率（范围，kbps）
    br_kbps = actual['bit_rate_kbps']
    if br_kbps is None and info.get('format_bit_rate'):
        br_kbps = round(info['format_bit_rate'] / 1000.0, 1)
    for field, side, ok in (('bitrate_min', '下限', lambda b, v: b >= v),
                            ('bitrate_max', '上限', lambda b, v: b <= v)):
        if o.get(field) in (None, ''):
            continue
        limit = _num(o.get(field))
        if limit is None:
            errors.append('码率%s不是数字: %r' % (side, o.get(field)))
        elif br_kbps is None:
            errors.append('无法获取码率信息')
        elif not ok(br_kbps, limit):
            errors.append('码率 %skbps 不满足%s %skbps' % (br_kbps, side, limit))

    # ⑤ 采样率 / 声道数（可选，兼容既有数据）
    for field, cname, label2, unit in (('sample_rate', 'sample_rate', '采样率', 'Hz'),
                                       ('channels', 'channels', '声道数', '')):
        want = str(o.get(field) or '').strip()
        if not want:
            continue
        lo, hi = parse_range(want)
        if lo is None and hi is None:
            errors.append('%s不是数字: %r' % (label2, want))
        elif actual[cname] is None:
            errors.append('这条%s轨没有%s信息' % (label, label2))
        else:
            got = int(actual[cname])
            if (lo is not None and got < lo) or (hi is not None and got > hi):
                errors.append('%s是 %d%s，期望 %s' % (label2, got, unit, want))

    # ⑥ 有无声音（填了阈值才检测；有音轨 ≠ 有声音）
    if o.get('sound') not in (None, ''):
        threshold = _num(o.get('sound'))
        if threshold is None:
            errors.append('静音阈值不是数字: %r' % o.get('sound'))
        elif _first_stream(streams, 'audio') is None:
            errors.append('文件里没有音频轨，无法检测有无声音')
        else:
            try:
                vol = detect_volume(path)
                actual['max_volume'] = vol['max_volume']
                actual['mean_volume'] = vol['mean_volume']
                actual['sound_threshold'] = threshold
                if vol['max_volume'] <= threshold:
                    errors.append('检测到静音：最大音量 %sdB 未高于阈值 %sdB'
                                  % (vol['max_volume'], threshold))
                mean_min = _num(o.get('mean_min'))
                if mean_min is not None and vol['mean_volume'] <= mean_min:
                    errors.append('平均音量 %sdB 低于下限 %sdB —— 整体声音过小'
                                  % (vol['mean_volume'], mean_min))
            except RuntimeError as e:
                errors.append(str(e))

    return (not errors), actual, '；'.join(errors) or None


# ---------------- 断言入口（字段 → options 的薄适配） ----------------
def evaluate(a_type, assertion, path):
    """执行单条音视频断言，返回 (passed: bool, actual, error: str|None)

    统一走公共方法 check_media；旧断言类型（media_video / media_audio / media_volume /
    media_stream）按各自字段映射进去，保证历史数据继续可执行。
    """
    a = assertion or {}

    if a_type == 'media_check':
        opts = {k: a.get(k) for k in ('media_type', 'codec', 'duration_min', 'duration_max',
                                      'resolution', 'bitrate_min', 'bitrate_max',
                                      'sample_rate', 'channels')}
        opts['media_type'] = opts.get('media_type') or 'audio'
        if a.get('sound_threshold') not in (None, ''):
            opts['sound'] = a.get('sound_threshold')
        if a.get('mean_volume_min') not in (None, ''):
            opts['mean_min'] = a.get('mean_volume_min')
        return check_media(path, opts)

    if a_type == 'media_volume':                       # 旧：只检测有无声音
        return check_media(path, {'media_type': 'audio',
                                  'sound': a.get('expected') or DEFAULT_SOUND_THRESHOLD,
                                  'mean_min': a.get('mean_volume_min')})

    if a_type == 'media_video':                        # 旧：视频属性
        return check_media(path, {
            'media_type': 'video', 'codec': a.get('codec'), 'resolution': a.get('resolution'),
            'duration_min': a.get('duration_min'), 'duration_max': a.get('duration_max'),
            'bitrate_min': a.get('bitrate_min'), 'bitrate_max': a.get('bitrate_max')})

    if a_type == 'media_audio':                        # 旧：音频属性
        return check_media(path, {
            'media_type': 'audio', 'codec': a.get('codec'),
            'sample_rate': a.get('sample_rate'), 'channels': a.get('channels'),
            'duration_min': a.get('duration_min'), 'duration_max': a.get('duration_max')})

    if a_type == 'media_stream':                       # 旧：按 media_type 归位
        mt = str(a.get('media_type') or 'video').lower()
        return check_media(path, {
            'media_type': 'audio' if mt == 'audio' else 'video',
            'codec': a.get('codec'), 'resolution': a.get('resolution'),
            'duration_min': a.get('duration_min'), 'duration_max': a.get('duration_max'),
            'bitrate_min': a.get('bitrate_min'), 'bitrate_max': a.get('bitrate_max')})

    return False, None, '未知音视频断言类型: %s' % a_type
