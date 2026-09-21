# -*- coding: utf-8 -*-
"""APP UI 用例级自动录屏 + 失败证据自动挂载 allure（业务用例零侵入）。

- 每条用例 setup 执行前自动启动录屏（按设备能力选 adb screenrecord / screencap 抽帧兜底），
  setup_class(启动App等)与用例主体全程在录屏内
- 用例通过：停止并清理临时录屏，报告里只有断言截图（assert_true_with_shot 挂载，现状不变）
- 用例失败：记录失败时刻 T，先抓失败瞬间截图，再继续录 after 秒收尾，
  裁剪 [T-before, T+after] 证据视频，连同失败截图、失败原因、录屏过程日志
  （含 screencap 兜底后端的抽帧索引）一并挂入 allure
- 附件必须挂载在 pytest_runtest_makereport 的 post-yield：allure 2.7.0 的测试上下文
  到 pytest_runtest_logfinish 才关闭，该时机有效；yield fixture teardown 里挂载不会落入结果
- 失败重跑(--reruns)时每次失败尝试各自生成证据，落在各自尝试的 allure 结果里
- 录屏/裁剪/截图任何异常只记日志，绝不覆盖用例真实结果
- 单条用例可用 @pytest.mark.no_recording 关闭录屏；开关与秒数见 common/video_evidence/config.py
"""
import json
import logging
import os
import time
from pathlib import Path

import pytest

# 产物根目录需在导入录屏模块前就绪（config 模块会读取该环境变量）
_REPO_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('VIDEO_EVIDENCE_ROOT', str(_REPO_ROOT))

from common.video_evidence.attach import attach_screenshot, attach_text, attach_video
from common.video_evidence.config import load_config
from common.video_evidence.device import RecorderError, capture_screenshot, create_recorder

logger = logging.getLogger('video_evidence')

# 进程级缓存：设备序列号/配置只解析一次（多设备并行时每个 pytest 进程独享一台设备）
_RESOLVED = {}

# 失败/报错用例集合：teardown 后对被测 App force-stop，保证下一条用例冷启动（平台 v6.85）
_FAILED_NODEIDS = set()


def pytest_runtest_teardown(item, nextitem):
    """失败冷启动兜底：设计上用例间冷启动靠 teardown_class close_app + 下一条 start_activity
    重新拉起；但旧用例可能缺 teardown_class，或失败把 App 卡死导致 close_app 无效——
    此处对失败/报错用例结束后 adb force-stop 被测 App，下一条 setup_class 即冷启动，
    一条用例失败不阻碍后面的用例。成功用例不做额外动作（保持现有热启动行为）。"""
    if item.nodeid not in _FAILED_NODEIDS:
        return
    caps = _read_current_capabilities()
    udid = os.environ.get('ADB_SERIAL') or caps.get('udid')
    pkg = caps.get('appPackage') or ''
    if not (udid and pkg):
        logger.warning('[冷启动兜底] 缺 udid/appPackage（%s/%s），跳过 force-stop', udid, pkg)
        return
    import subprocess
    try:
        subprocess.run(['adb', '-s', udid, 'shell', 'am', 'force-stop', pkg],
                       timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info('[冷启动兜底] 上条用例失败，已 force-stop %s，下一条将冷启动', pkg)
    except Exception as e:
        logger.warning('[冷启动兜底] force-stop 失败: %s', e)


def _read_current_capabilities():
    """读取 run_app_ui_test 为当前进程落盘的 desired_capabilities（含 udid），读取失败返回空 dict。"""
    path = os.path.join('config', 'app_ui_tmp',
                        '%s_current_desired_capabilities' % os.getppid())
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _get_cfg():
    """加载录屏配置：设备序列号按 ADB_SERIAL 环境变量 > 用例设备信息 udid > 自动发现。"""
    if 'cfg' not in _RESOLVED:
        udid = _read_current_capabilities().get('udid')
        cfg = load_config(adb_serial=os.environ.get('ADB_SERIAL') or udid)
        _RESOLVED['cfg'] = cfg
        _RESOLVED['ready'] = bool(cfg.enabled) and bool(cfg.adb_serial) and bool(cfg.ffmpeg)
        if cfg.enabled and not cfg.adb_serial:
            logger.warning('未解析到 adb 设备序列号，本进程录屏功能关闭')
        elif cfg.enabled and not cfg.ffmpeg:
            logger.warning('未找到 ffmpeg 命令，本进程录屏功能关闭')
    return _RESOLVED['cfg']


def _node_name(item, cfg):
    safe = item.nodeid.replace('/', '__').replace('::', '__').replace(':', '_')
    # 多设备并行时同名用例会同时跑在多个进程，附加 serial+pid 隔离各自的临时目录
    return '%s__%s__%s' % (safe, cfg.adb_serial, os.getpid())


def _start_recording(item):
    """在 setup 执行前启动录屏。失败只告警，绝不阻塞用例。"""
    cfg = _get_cfg()
    item._ve_cfg = cfg
    item._ve_recorder = None
    if not cfg.enabled:
        return
    if not _RESOLVED.get('ready'):
        return
    if item.get_closest_marker('no_recording'):
        logger.info('用例标记 no_recording，跳过录屏: %s' % item.nodeid)
        return
    try:
        rec = create_recorder(cfg, _node_name(item, cfg))
        rec.start()
        item._ve_recorder = rec
        logger.info('录屏已开始 device=%s backend=%s usecase=%s'
                    % (cfg.adb_serial, type(rec).__name__, item.nodeid))
    except RecorderError as exc:
        if cfg.required:
            raise
        logger.warning('录屏启动失败(已忽略，不影响用例): %s' % exc)


def _finish_recording(item, keep=False):
    """收尾录屏（成功/跳过场景），幂等。"""
    rec = getattr(item, '_ve_recorder', None)
    if rec is None:
        return
    try:
        rec.discard(keep=keep)
        logger.info('用例无失败，临时录屏已清理')
    except Exception as exc:
        logger.warning('录屏收尾异常(已忽略): %s' % exc)
    finally:
        item._ve_recorder = None


def _build_failure_evidence(item, rep):
    """失败证据四件套：失败截图 + [T-5s,T+5s]证据视频 + 失败原因 + 录屏过程日志(含抽帧索引)。"""
    rec = getattr(item, '_ve_recorder', None)
    if rec is None:
        return
    cfg = item._ve_cfg
    try:
        t_fail = time.time()
        logger.warning('「%s」执行失败(阶段=%s)，生成录屏证据：失败前%ds~后%ds'
                       % (item.nodeid, rep.when, cfg.before_seconds, cfg.after_seconds))
        node = _node_name(item, cfg)

        # 1. 失败瞬间截图：先于延迟收尾抓取，屏幕现场最及时
        shot = None
        try:
            shot = capture_screenshot(cfg.adb_serial, str(cfg.artifact_dir), '%s_failure' % node)
        except Exception as exc:
            rec.recording_log.write('失败截图失败(已忽略): %s' % exc)

        # 2. 关键点：失败后不立即停止，继续录 after 秒再收尾
        try:
            rec.stop(wait_seconds=cfg.after_seconds)
        except Exception as exc:
            rec.recording_log.write('停止录制失败(已忽略): %s' % exc)

        # 3. 裁剪 [T-before, T+after] 证据视频；裁剪失败时由 recorder 用原始视频兜底
        video_path = os.path.join(str(cfg.artifact_dir), '%s_failure.mp4' % node)
        try:
            produced = rec.build_video(t_fail, video_path, cfg.before_seconds, cfg.after_seconds)
            if produced == str(video_path):
                attach_video(video_path)
                logger.info('失败证据视频已挂载 allure: %s' % produced)
            else:
                attach_video(produced, name='failure_video_raw')
                attach_text('证据视频裁剪失败，已用完整原始录屏兜底', name='video_process_error')
                logger.warning('裁剪失败，原始录屏已兜底挂载: %s' % produced)
        except Exception as exc:
            logger.error('失败视频生成异常(已忽略，不影响用例结果): %s' % exc)
            attach_text('失败视频生成失败: %s' % exc, name='video_error')

        # 4. 失败截图 / 失败原因 / 录屏过程日志（含抽帧索引）
        if shot and os.path.exists(shot):
            attach_screenshot(shot)
        attach_text(rep.longrepr, name='failure_reason')
        recording_log_content = rec.recording_log.read()
        if recording_log_content:
            attach_text(recording_log_content, name='recording_log')
    except Exception as exc:
        logger.error('录屏证据处理异常(已忽略，不影响用例结果): %s' % exc)
    finally:
        item._ve_recorder = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    """setup 执行前启动录屏，把 setup_class(启动App等)也录进去。"""
    _start_recording(item)
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()

    if rep.failed:
        _FAILED_NODEIDS.add(item.nodeid)   # 失败/报错记录：teardown 后触发冷启动兜底

    if rep.when == 'setup':
        if rep.failed:
            # setup 失败同样生成证据（录屏自 setup 前已开始，覆盖 setup_class 现场）
            _build_failure_evidence(item, rep)
        elif rep.skipped:
            _finish_recording(item)
    elif rep.when == 'call':
        if rep.failed:
            _build_failure_evidence(item, rep)
        else:
            _finish_recording(item, keep=item._ve_cfg.keep_on_success)
    elif rep.when == 'teardown':
        # 兜底：call 阶段未执行（setup 失败被跳过等）时录屏进程可能仍在跑，防止泄漏
        if getattr(item, '_ve_recorder', None) is not None:
            logger.info('call 阶段未产生结果，清理孤儿录屏')
            _finish_recording(item)
