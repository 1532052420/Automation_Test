# -*- coding: utf-8 -*-
"""录屏与报告相关配置：环境变量优先，缺省用默认值。

环境变量：
    RECORDING_ENABLED        是否启用自动录屏（默认 true）
    RECORDING_REQUIRED       录屏启动失败是否终止测试（默认 false，只告警继续跑）
    RECORDING_KEEP_ON_SUCCESS 成功后是否保留原始视频（默认 false，删除）
    RECORDING_BEFORE_SECONDS 失败前保留秒数（默认 5）
    RECORDING_AFTER_SECONDS  失败后继续录制秒数（默认 5）
    ADB_SERIAL               指定设备序列号（缺省按用例设备信息，无则自动发现第一台在线设备）
    VIDEO_EVIDENCE_ROOT      录屏产物根目录（缺省为框架根目录，由 conftest 注入）
"""
import configparser as ConfigParser
import os
import shutil
import subprocess
from pathlib import Path

# 录屏配置文件（平台「录屏配置」模块统一管理；直接跑 pytest 也读同一份）
# 优先级：代码默认值 < 本 conf 文件 < 环境变量（与平台「env 可覆盖」惯例一致）
RECORDING_CONF = Path(__file__).resolve().parents[2] / 'config' / 'recording.conf'

# PATH 找不到命令时再探测的常见安装位置（homebrew 等）
_FALLBACK_TOOL_DIRS = ('/opt/homebrew/bin', '/usr/local/bin')


def _conf_values():
    """读 config/recording.conf 的 [recording] 段；文件缺失/字段缺失返回空 dict。"""
    values = {}
    if not RECORDING_CONF.is_file():
        return values
    parser = ConfigParser.ConfigParser()
    try:
        parser.read(str(RECORDING_CONF), encoding='utf-8')
        for key in parser.options('recording') if parser.has_section('recording') else []:
            values[key.strip().lower()] = (parser.get('recording', key) or '').strip()
    except Exception:
        pass
    return values


def _resolve(name, cast, default, conf):
    """解析单项：默认值 < conf 文件 < 环境变量；解析失败回退默认值。
    conf 键不带 RECORDING_ 前缀（conf 里写 before_seconds，环境变量叫 RECORDING_BEFORE_SECONDS）。"""
    env = os.environ.get(name)
    raw = env if env is not None and env != '' else conf.get(name.lower().replace('recording_', ''), '')
    try:
        return cast(raw) if raw != '' else default
    except (TypeError, ValueError):
        return default


def _resolve_bool(name, default, conf):
    env = os.environ.get(name)
    raw = env if env is not None and env != '' else conf.get(name.lower().replace('recording_', ''), '')
    if raw == '':
        return default
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def find_tool(name):
    """定位外部命令：PATH 优先，再找常见安装位置(adb 另查 ANDROID_HOME)，找不到返回 None。"""
    path = shutil.which(name)
    if path:
        return path
    for d in _FALLBACK_TOOL_DIRS:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    if name == 'adb':
        android_home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
        if android_home:
            candidate = os.path.join(android_home, 'platform-tools', 'adb')
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def detect_first_device():
    """返回第一台在线设备的序列号，无设备/无 adb 返回 None。"""
    adb = find_tool('adb')
    if not adb:
        return None
    try:
        out = subprocess.run([adb, 'devices'], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == 'device':
            return parts[0]
    return None


class RecordingConfig:
    """一次运行共享的录屏配置。

    解析优先级：代码默认值 < config/recording.conf（平台「录屏配置」模块维护）
    < 环境变量（RECORDING_*，手工临时覆盖用）。
    """

    def __init__(self, adb_serial=None):
        conf = _conf_values()
        self.enabled = _resolve_bool('RECORDING_ENABLED', True, conf)
        self.required = _resolve_bool('RECORDING_REQUIRED', False, conf)
        self.keep_on_success = _resolve_bool('RECORDING_KEEP_ON_SUCCESS', False, conf)
        self.before_seconds = _resolve('RECORDING_BEFORE_SECONDS', int, 5, conf)
        self.after_seconds = _resolve('RECORDING_AFTER_SECONDS', int, 5, conf)
        # screenrecord 单段录制上限（Android 硬上限 180s，超长用例从此截断）与码率
        self.max_segment_seconds = max(3, min(180, _resolve('RECORDING_MAX_SEGMENT_SECONDS', int, 180, conf)))
        self.bit_rate = _resolve('RECORDING_BIT_RATE', int, 4000000, conf)
        # adb_serial 传入优先，其次 ADB_SERIAL 环境变量，最后自动发现
        self.adb_serial = adb_serial or os.environ.get('ADB_SERIAL') or detect_first_device()
        run_root = Path(os.environ.get('VIDEO_EVIDENCE_ROOT', os.getcwd()))
        # 产物统一放 output/ 下，随框架 .gitignore 的 *output* 规则被忽略
        self.tmp_dir = run_root / 'output' / 'video_evidence' / 'tmp'
        self.artifact_dir = run_root / 'output' / 'video_evidence' / 'artifacts'
        self.ffmpeg = find_tool('ffmpeg')
        self.ffprobe = find_tool('ffprobe')


def load_config(adb_serial=None):
    return RecordingConfig(adb_serial=adb_serial)
