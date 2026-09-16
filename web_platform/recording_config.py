# -*- coding: utf-8 -*-
"""Web 执行平台 · 录屏配置模块

统一管理所有录屏相关可配置项，落盘 config/recording.conf（INI）。
pytest 侧（common/video_evidence/config.py）读同一份文件生效：
    默认值 < config/recording.conf < 环境变量 RECORDING_*（手工临时覆盖）

可配置项（[recording] 段）：
    enabled               总开关：是否自动录屏（默认 true）
    required              录屏启动失败是否终止用例（默认 false，只告警继续跑）
    keep_on_success       用例成功后是否保留原始录屏（默认 false，删除）
    before_seconds        失败证据保留失败前秒数（默认 5，范围 0~60）
    after_seconds         失败后继续录制秒数（默认 5，范围 0~60）
    max_segment_seconds   单段录制时长上限（默认 180，Android 硬上限 180，范围 3~180）
    bit_rate              录制码率 bps（默认 4000000，范围 1000000~20000000）

录屏时机（setup 执行前启动，覆盖启动 App 现场）为框架 hook 固定行为，不作配置。
"""
import configparser as ConfigParser
import os

from web_platform.runtime_config import BASE_DIR

CONF_PATH = os.path.join(BASE_DIR, 'config', 'recording.conf')

# 字段定义：key -> (类型, 默认值, 最小值, 最大值, 说明)
FIELD_DEFS = {
    'enabled':             ('bool', True,  None, None, '总开关：执行用例时自动录屏'),
    'required':            ('bool', False, None, None, '录屏启动失败是否终止用例（false=只告警继续跑）'),
    'keep_on_success':     ('bool', False, None, None, '用例成功后保留原始录屏文件'),
    'before_seconds':      ('int',  5,     0,    60,   '失败证据保留失败前多少秒'),
    'after_seconds':       ('int',  5,     0,    60,   '失败后继续录制多少秒再收尾'),
    'max_segment_seconds': ('int',  180,   3,    180,  '单段录制时长上限（Android screenrecord 硬上限 180s）'),
    'bit_rate':            ('int',  4000000, 1000000, 20000000, '录制码率（bps）'),
}

_CONF_TEMPLATE = """# 录屏配置（平台「录屏配置」模块维护；common/video_evidence 执行时读取）
# 优先级：代码默认值 < 本文件 < 环境变量 RECORDING_*（手工临时覆盖）
# 录屏时机固定为每条用例 setup 执行前启动（覆盖启动 App 现场），不做配置。
[recording]
"""


def _coerce(raw, ftype):
    if ftype == 'bool':
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
    return int(str(raw).strip())


def load_recording_config():
    """读当前生效配置（默认值 < conf 文件 < 环境变量），返回 dict（值已转类型）。"""
    parser = ConfigParser.ConfigParser()
    conf = {}
    try:
        parser.read(CONF_PATH, encoding='utf-8')
        if parser.has_section('recording'):
            conf = {k.strip().lower(): (parser.get('recording', k) or '').strip()
                    for k in parser.options('recording')}
    except Exception:
        conf = {}
    result = {}
    for key, (ftype, default, lo, hi, _desc) in FIELD_DEFS.items():
        env = os.environ.get('RECORDING_' + key.upper())
        raw = env if env is not None and env != '' else conf.get(key, '')
        try:
            val = _coerce(raw, ftype) if raw != '' else default
        except (TypeError, ValueError):
            val = default
        if ftype == 'int' and lo is not None:
            val = max(lo, min(hi, val))
        result[key] = val
    return result


def save_recording_config(data):
    """校验并写入 config/recording.conf。

    返回 (ok, msg, effective_dict)。非法值报错不落盘（不部分写入）。
    """
    if not isinstance(data, dict):
        return False, '请求体须为 JSON 对象', None
    cleaned = {}
    for key, (ftype, default, lo, hi, _desc) in FIELD_DEFS.items():
        if key not in data or data[key] in ('', None):
            cleaned[key] = default          # 缺省字段用默认值
            continue
        try:
            val = _coerce(data[key], ftype)
        except (TypeError, ValueError):
            return False, '%s: 值 %r 不是合法%s' % (key, data[key], '布尔' if ftype == 'bool' else '整数'), None
        if ftype == 'int' and lo is not None and not (lo <= val <= hi):
            return False, '%s: 超出允许范围 %d~%d' % (key, lo, hi), None
        cleaned[key] = val
    lines = [_CONF_TEMPLATE]
    for key, (ftype, _d, _lo, _hi, desc) in FIELD_DEFS.items():
        val = cleaned[key]
        if ftype == 'bool':
            val = 'true' if val else 'false'
        lines.append('# %s\n%s = %s\n' % (desc, key, val))
    try:
        with open(CONF_PATH, 'w', encoding='utf-8') as f:
            f.write(''.join(lines))
    except OSError as e:
        return False, '写入配置文件失败: %s' % e, None
    return True, '录屏配置已保存，下次执行用例时生效', cleaned


def read_conf_file_raw():
    """读 conf 文件原始内容（无文件返回 ''），供测试还原。"""
    try:
        with open(CONF_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''
