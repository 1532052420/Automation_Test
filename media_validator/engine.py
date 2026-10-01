# -*- coding: utf-8 -*-
"""媒体产物检测 · 检测引擎（独立模块，不依赖框架任何代码）

编排层：测量（vendor/rendercheck，ffprobe/ffmpeg 原语）→ 规则判定 → 结构化报告。
方案第 6 节的每个检测项产出一个 item：

    {'key': 'silence', 'label': '静音检测', 'passed': True|False|None,
     'rule': '非纯静音 · 最长静音 ≤ 10s', 'actual': '响度 -16.1 LUFS · 最长静音 0s', 'note': ...}

- passed=None = 未设阈值，仅报告实测值（不参与判定）；
- 总判定 passed = 所有 item 无 False；
- 文件损坏走 **FAIL**（有效的检测结果）；ffmpeg/ffprobe 缺失走 **ERROR**（基础设施故障），
  两者不得混淆——检测工具坏了不能伪装成「文件不合格」。

完整性 = 全量解码扫描（音频/视频/图片通用）；封装格式与扩展名不符在
「格式」项判 FAIL（改后缀伪装是常见的假产物手法）。
"""
import os
import shutil
import subprocess

from media_validator.vendor.rendercheck import _ffmpeg
from media_validator.vendor.rendercheck._ffmpeg import ToolUnavailable

DECODE_TIMEOUT = 600   # 与 vendor/rendercheck._ffmpeg._TIMEOUT 对齐

# 扩展名 → 封装格式名应包含的 token（与 ffprobe format_name 做包含比对）
_EXT_TOKENS = {
    'png': ('png',), 'jpg': ('jpeg', 'jpg'), 'jpeg': ('jpeg', 'jpg'), 'webp': ('webp',),
    'mp3': ('mp3',), 'wav': ('wav',),
    'm4a': ('m4a', 'mp4', 'aac', 'adts'),
    'mp4': ('mp4', 'mov', 'matroska'), 'mov': ('mov', 'mp4'), 'mkv': ('matroska', 'webm'),
}


class EngineError(Exception):
    """基础设施故障（ffmpeg/ffprobe 缺失等），任务置 ERROR 而非 FAIL"""


# ---------------------------------------------------------------- 工具与探针
def tools_available():
    return {'ffmpeg': bool(shutil.which('ffmpeg')), 'ffprobe': bool(shutil.which('ffprobe'))}


# 魔数嗅探名 → 标准扩展名（ftyp 品牌按家族归位）
_SNIFF_EXT = {'png': 'png', 'jpeg': 'jpg', 'webp': 'webp', 'wav': 'wav', 'mp3': 'mp3',
              'm4a': 'm4a', 'qt': 'mov'}


def sniff_ext(path):
    """文件头魔数 → 标准扩展名（png/jpg/webp/wav/mp3/m4a/mov/mkv/mp4），识别不了返回 None。

    供链接/路径来源在无扩展名时做类型识别。
    """
    s = _sniff_magic(path)
    if not s:
        return None
    if s in _SNIFF_EXT:
        return _SNIFF_EXT[s]
    if s == 'matroska':
        return 'mkv'
    return 'mp4'          # 其余 ftyp 品牌（isom/mp42/avc1…）一律按 mp4 家族


def _sniff_magic(path):
    """文件头魔数 → 嗅探格式名（识别不了的返回 None）"""
    try:
        with open(path, 'rb') as f:
            head = f.read(32)
    except OSError:
        return None
    if head.startswith(b'\x89PNG'):
        return 'png'
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    if head[:4] == b'RIFF' and head[8:12] == b'WAVE':
        return 'wav'
    if head[:3] == b'ID3' or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return 'mp3'
    if len(head) >= 8 and head[4:8] == b'ftyp':
        brand = head[8:12].decode('ascii', 'replace').lower().strip()
        return brand or 'mp4'
    if head.startswith(b'\x1a\x45\xdf\xa3'):
        return 'matroska'
    return None


def _decode_scan(path):
    """全量解码扫描：stderr 无 error 行 = 完整。返回 (ok: bool, detail: str)"""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise EngineError('ffmpeg 不可用，无法做完整性解码扫描')
    try:
        p = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', path, '-f', 'null', '-'],
                           capture_output=True, text=True, timeout=DECODE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, '解码超时（>%ds），文件可能异常庞大或损坏' % DECODE_TIMEOUT
    err = (p.stderr or '').strip()
    if p.returncode != 0 or err:
        return False, (err or 'ffmpeg 退出码 %d' % p.returncode).splitlines()[-1][:200]
    return True, '全量解码无错误'


def _probe_info(path):
    """ffprobe 探针 → info 字典；读不出 = 文件损坏，抛 ToolUnavailable"""
    streams = _ffmpeg.streams(path)
    try:
        duration = _ffmpeg.duration(path)
    except ToolUnavailable:
        duration = None
    return {
        'container': _ffmpeg.container(path),
        'duration': duration,
        'streams': [{
            'kind': s.kind, 'codec': s.codec,
            'width': s.width, 'height': s.height,
            'fps': s.fps, 'avg_fps': s.average_fps,
            'sample_rate': s.sample_rate, 'channels': s.channels,
            'duration': s.length,
        } for s in streams],
    }


def _video_stream(info):
    return next((s for s in info['streams'] if s['kind'] == 'video'), None) if info else None


def _audio_stream(info):
    return next((s for s in info['streams'] if s['kind'] == 'audio'), None) if info else None


# ---------------------------------------------------------------- 展示辅助
def _fmt_duration(sec):
    if sec is None:
        return '未知'
    if sec >= 60:
        return '%.1fs (%d:%05.2f)' % (sec, int(sec // 60), sec % 60)
    return '%.1fs' % sec


def _fmt_size(nbytes):
    if nbytes is None:
        return '未知'
    for unit, div in (('TB', 1 << 40), ('GB', 1 << 30), ('MB', 1 << 20), ('KB', 1 << 10)):
        if nbytes >= div:
            return '%.1f %s' % (nbytes / float(div), unit)
    return '%d B' % nbytes


def _fmt_range(rules, lo_key, hi_key, unit):
    lo, hi = rules.get(lo_key), rules.get(hi_key)
    if lo is not None and hi is not None:
        return '%g ~ %g%s' % (lo, hi, unit)
    if lo is not None:
        return '≥ %g%s' % (lo, unit)
    if hi is not None:
        return '≤ %g%s' % (hi, unit)
    return '仅报告'


def _fmt_min_wh(rules, unit):
    parts = []
    if rules.get('min_width') is not None:
        parts.append('宽 ≥ %g%s' % (rules['min_width'], unit))
    if rules.get('min_height') is not None:
        parts.append('高 ≥ %g%s' % (rules['min_height'], unit))
    return ' · '.join(parts)


def _item(key, label, passed, rule, actual, note=None):
    return {'key': key, 'label': label, 'passed': passed,
            'rule': rule, 'actual': actual, 'note': note}


def _stream_desc(s):
    if not s:
        return '无'
    parts = []
    if s.get('codec'):
        parts.append(s['codec'])
    if s.get('kind') == 'audio':
        if s.get('sample_rate'):
            parts.append('%g Hz' % s['sample_rate'])
        if s.get('channels'):
            parts.append('%g 声道' % s['channels'])
    elif s.get('kind') == 'video':
        if s.get('width') and s.get('height'):
            parts.append('%dx%d' % (s['width'], s['height']))
        _, fps_disp, _ = _fps_display(s)
        if fps_disp is not None:
            parts.append('%.3f fps' % fps_disp)
    return '、'.join(parts) or '未知'


_NOMINAL_CAP = 500
"""标称帧率（r_frame_rate）可信上限：录屏/部分封装常塞 1000000、90000 之类的
占位垃圾值，超过一律视为容器占位而非真实能力，展示与判定都不采用。"""


def _fps_display(v):
    """帧率展示与判定基准。

    实际帧率（avg_frame_rate = 总帧数/时长）为主；标称值只在「可信且与实际
    不一致」时作为变帧率注记。返回 (展示文本, 用于判定的帧率, 注记)。
    """
    nominal, avg = v.get('fps'), v.get('avg_fps')
    nominal_ok = bool(nominal and nominal <= _NOMINAL_CAP)
    if avg:
        txt = '%.3f fps' % avg
        note = None
        if nominal_ok and abs(avg - nominal) > max(0.01, nominal * 0.01):
            txt += '（标称 %g，变帧率）' % nominal
            note = '标称帧率与实际均值不一致，属于变帧率文件，剪辑软件里音画易漂移'
        return txt, avg, note
    if nominal_ok:
        return '%.3f fps（标称）' % nominal, nominal, '容器未提供实际均值帧率，仅标称值参考'
    return '未知', None, '容器未提供可用帧率（标称值为占位数据）'


# ---------------------------------------------------------------- 共用项：完整性 + 格式
def _items_integrity_format(path, info, ext, sniff):
    items = []
    if info is None:
        items.append(_item('integrity', '文件完整性', False, '可被正常解析',
                           'ffprobe 无法读取该文件', '0 字节、截断或非媒体内容'))
        items.append(_item('format', '格式', False, '与扩展名 .%s 一致' % ext,
                           '无法识别', '文件无法解析，无从核对封装格式'))
        return items

    ok, detail = _decode_scan(path)
    items.append(_item('integrity', '文件完整性', ok, '全量解码无错误',
                       '解码完整' if ok else detail,
                       None if ok else '存在损坏帧或截断，播放器可能在中途出错'))

    tokens = _EXT_TOKENS.get(ext)
    container = info['container'] or ''
    matched = bool(tokens) and any(t in container.lower() for t in tokens)
    items.append(_item('format', '格式', matched if tokens else None,
                       '与扩展名 .%s 一致' % ext,
                       '封装 %s · 嗅探 %s' % (container or '未知', sniff or '未识别'),
                       None if matched else '实际封装 %s 与扩展名 .%s 不符（嗅探 %s），常见于改后缀伪装'
                       % (container, ext, sniff)))
    return items


# ---------------------------------------------------------------- 时长（音视频共用）
def _item_duration(info, rules):
    dur = info['duration'] if info else None
    rule_txt = _fmt_range(rules, 'duration_min', 'duration_max', 's')
    if rules.get('duration_min') is None and rules.get('duration_max') is None:
        return _item('duration', '时长', None, rule_txt, _fmt_duration(dur))
    bad = []
    if rules.get('duration_min') is not None and (dur is None or dur < rules['duration_min']):
        bad.append('低于下限' if dur is not None else '无法获取时长')
    if rules.get('duration_max') is not None and dur is not None and dur > rules['duration_max']:
        bad.append('超出上限')
    return _item('duration', '时长', not bad, rule_txt, _fmt_duration(dur), '；'.join(bad) or None)


# ---------------------------------------------------------------- 各类型检测项
def _silence_rule(rules):
    parts = []
    if rules.get('require_sound'):
        parts.append('非纯静音')
    if rules.get('max_silence') is not None:
        parts.append('最长静音 ≤ %gs' % rules['max_silence'])
    return ' · '.join(parts) or '仅报告'


def _items_audio(path, info, rules):
    items, a = [], _audio_stream(info)
    on = rules.get('require_track')
    items.append(_item('audio_track', '音频轨', bool(a) if on else None,
                       '存在音频轨' if on else '仅报告',
                       _stream_desc(a) if a else '无音频轨',
                       None if a else '文件里没有任何音频轨，通常是合成/混流步骤静默失败'))
    if not a:
        # 无音频轨（含文件不可解析）时其余项无从测起：时长照常报告，静音项跳过不投票
        items.append(_item_duration(info, rules))
        items.append(_item('silence', '静音检测', None, _silence_rule(rules),
                           '无法测量', '没有音频轨，静音检测跳过'))
        return items
    if a:
        if rules.get('min_sample_rate') is not None:
            items.append(_item('sample_rate', '采样率',
                               a['sample_rate'] is not None and a['sample_rate'] >= rules['min_sample_rate'],
                               '≥ %g Hz' % rules['min_sample_rate'],
                               ('%g Hz' % a['sample_rate']) if a['sample_rate'] else '未知'))
        else:
            items.append(_item('sample_rate', '采样率', None, '仅报告',
                               ('%g Hz' % a['sample_rate']) if a['sample_rate'] else '未知'))
        if rules.get('min_channels') is not None:
            items.append(_item('channels', '声道',
                               a['channels'] is not None and a['channels'] >= rules['min_channels'],
                               '≥ %g 声道' % rules['min_channels'],
                               ('%g 声道' % a['channels']) if a['channels'] else '未知'))
        else:
            items.append(_item('channels', '声道', None, '仅报告',
                               ('%g 声道' % a['channels']) if a['channels'] else '未知'))
    items.append(_item_duration(info, rules))

    # 静音检测：一次解码同时读响度（loudnorm）与静音段（silencedetect）
    rule = _silence_rule(rules)
    try:
        m = _ffmpeg.measure(path, threshold_db=-40.0, min_seconds=0.5)
    except ToolUnavailable as e:
        items.append(_item('silence', '静音检测', False, rule, '测量失败', str(e)[:150]))
        return items
    longest = max([e - s for s, e in m.silences], default=0.0)
    actual = '响度 %s LUFS · 最长静音 %.1fs（%d 段）' % (
        '数字静音' if m.loudness == float('-inf') else '%.1f' % m.loudness,
        longest, len(m.silences))
    silent_fail = rules.get('require_sound') and m.loudness == float('-inf')
    gap_fail = rules.get('max_silence') is not None and longest > rules['max_silence']
    note = None
    if silent_fail:
        note = '整段音频全是零样本，等于没有内容（生成失败或混音被静音）'
    elif gap_fail:
        note = '最长静音 %.1fs 超过 %gs，疑似丢段/断流' % (longest, rules['max_silence'])
    items.append(_item('silence', '静音检测', not (silent_fail or gap_fail), rule, actual, note))
    return items


def _items_video(path, info, rules):
    items = []
    v, a = _video_stream(info), _audio_stream(info)
    for key, label, stream, need in (('video_track', '视频轨', v, 'require_video_track'),
                                     ('audio_track', '音频轨', a, 'require_audio_track')):
        on = rules.get(need)
        items.append(_item(key, label, bool(stream) if on else None,
                           '存在%s' % label if on else '仅报告',
                           _stream_desc(stream) if stream else '无%s' % label,
                           None if stream else '文件里没有%s' % label))
    items.append(_item_duration(info, rules))

    if v:
        res = '%dx%d' % (v['width'], v['height']) if v['width'] and v['height'] else '未知'
        if rules.get('min_width') is not None or rules.get('min_height') is not None:
            bad = []
            if rules.get('min_width') is not None and (v['width'] or 0) < rules['min_width']:
                bad.append('宽不足')
            if rules.get('min_height') is not None and (v['height'] or 0) < rules['min_height']:
                bad.append('高不足')
            items.append(_item('resolution', '分辨率', not bad,
                               _fmt_min_wh(rules, 'px'), res, '；'.join(bad) or None))
        else:
            items.append(_item('resolution', '分辨率', None, '仅报告', res))

        fps_txt, judge_fps, fps_note = _fps_display(v)
        if rules.get('min_fps') is not None:
            if judge_fps is None:
                passed, extra = None, '无法获取可用帧率，未判定'
            else:
                passed = judge_fps >= rules['min_fps']
                extra = '实际帧率低于 %g fps，观感卡顿' % rules['min_fps'] if passed is False else None
            if fps_note is None and extra:
                fps_note = extra
            items.append(_item('fps', '帧率', passed, '≥ %g fps' % rules['min_fps'], fps_txt, fps_note))
        else:
            items.append(_item('fps', '帧率', None, '仅报告', fps_txt, fps_note))

    # 黑屏 / 冻结帧：blackdetect + freezedetect 一次解码同时测
    rule_black = '最长黑屏 ≤ %gs' % rules['max_black'] if rules.get('max_black') is not None else '仅报告'
    rule_freeze = '最长冻结 ≤ %gs' % rules['max_freeze'] if rules.get('max_freeze') is not None else '仅报告'
    try:
        mv = _ffmpeg.measure_video(path, min_black=0.5, min_freeze=1.0)
    except ToolUnavailable as e:
        items.append(_item('black', '黑屏检测', False, rule_black, '测量失败', str(e)[:150]))
        items.append(_item('freeze', '冻结帧检测', False, rule_freeze, '测量失败', str(e)[:150]))
        return items

    long_black = max((d for _, d in mv.blacks), default=0.0)
    long_freeze = max((d for _, d in mv.freezes), default=0.0)
    black_fail = rules.get('max_black') is not None and long_black > rules['max_black']
    freeze_fail = rules.get('max_freeze') is not None and long_freeze > rules['max_freeze']
    items.append(_item('black', '黑屏检测', not black_fail, rule_black,
                       '最长 %.1fs（%d 段）' % (long_black, len(mv.blacks)),
                       '最长黑屏 %.1fs，疑似渲染中断输出纯黑' % long_black if black_fail else None))
    items.append(_item('freeze', '冻结帧检测', not freeze_fail, rule_freeze,
                       '最长 %.1fs（%d 段）' % (long_freeze, len(mv.freezes)),
                       '画面静止 %.1fs，疑似生成失败播放成幻灯片' % long_freeze if freeze_fail else None))
    return items


def _items_image(info, rules, size_bytes, path):
    items = []
    if info:
        v = _video_stream(info) or {}
        dims = '%dx%d' % (v['width'], v['height']) if v['width'] and v['height'] else '未知'
        if rules.get('min_width') is not None or rules.get('min_height') is not None:
            bad = []
            if rules.get('min_width') is not None and (v['width'] or 0) < rules['min_width']:
                bad.append('宽不足')
            if rules.get('min_height') is not None and (v['height'] or 0) < rules['min_height']:
                bad.append('高不足')
            items.append(_item('size', '尺寸', not bad, _fmt_min_wh(rules, 'px'), dims,
                               '；'.join(bad) or None))
        else:
            items.append(_item('size', '尺寸', None, '仅报告', dims))
    else:
        items.append(_item('size', '尺寸', False, '可解析尺寸', '未知', '文件无法解析'))

    cap_mb = rules.get('max_file_mb')
    mb = (size_bytes or 0) / (1024.0 * 1024.0)
    items.append(_item('file_size', '文件大小', cap_mb is None or mb <= cap_mb,
                       '≤ %gMB' % cap_mb if cap_mb is not None else '仅报告',
                       _fmt_size(size_bytes),
                       '超出 %gMB 上限' % cap_mb if (cap_mb is not None and mb > cap_mb) else None))

    if rules.get('detect_blank'):
        # signalstats 真解码首帧读亮度分布：纯色/空白画布 = 生成失败的典型形态
        try:
            pic = _ffmpeg.signalstats(path)
            spread = pic.high - pic.low
            blank = spread < 16.0
            items.append(_item('blank', '画面内容', not blank, '非空白/纯色图',
                               '亮度跨度 %d 级' % spread,
                               '近乎纯色/空白画布，是生成失败返回空图的典型形态' if blank else None))
        except ToolUnavailable as e:
            items.append(_item('blank', '画面内容', None, '非空白/纯色图', '无法测量', str(e)[:150]))
    return items


# ---------------------------------------------------------------- 入口
def detect(path, media_type, rules, size_bytes=None, ext=''):
    """执行检测，返回报告字典；工具缺失抛 EngineError。

    path: 上传文件绝对路径；media_type: audio|video|image
    rules: 已 sanitize 的规则快照；size_bytes/ext: 任务元信息回填
    """
    tools = tools_available()
    if not tools['ffmpeg'] or not tools['ffprobe']:
        raise EngineError('ffmpeg/ffprobe 未安装（%s），无法检测 %s 产物'
                          % ('、'.join(k for k, v in tools.items() if not v), media_type))

    sniff = _sniff_magic(path)
    probe_err = None
    try:
        info = _probe_info(path)
    except ToolUnavailable as e:
        info, probe_err = None, str(e)
    if size_bytes is None:
        try:
            size_bytes = os.path.getsize(path)
        except OSError:
            size_bytes = None

    head = _items_integrity_format(path, info, ext, sniff)
    if media_type == 'audio':
        items = head + _items_audio(path, info, rules)
    elif media_type == 'video':
        items = head + _items_video(path, info, rules)
    else:
        items = head + _items_image(info, rules, size_bytes, path)

    report = {
        'passed': all(i['passed'] is not False for i in items),
        'items': items,
        'info': {
            'media_type': media_type, 'ext': ext, 'sniff': sniff,
            'container': (info or {}).get('container'),
            'duration': (info or {}).get('duration'),
            'size_bytes': size_bytes,
            'streams': (info or {}).get('streams', []),
        },
    }
    if probe_err:
        report['probe_error'] = probe_err
    return report
