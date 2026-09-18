# -*- coding: utf-8 -*-
"""接口测试 · 音视频断言测试（v6.19：合并成一个断言 + 公共方法）

对外只有一个断言 media_check「音视频检测」，检测项全部可选：
- 格式（编码，如 h264 / aac）
- 时长（范围，秒）
- 有无声音（静音阈值 dB）
- 分辨率（仅视频，音频自动跳过）
- 码率（范围 kbps，可选）

核心是公共方法 media.check_media(path, options)：填哪项查哪项，留空即跳过。
evaluate() 是断言字段 → options 的薄适配层，同时兼容旧断言类型。

测试资产由 ffmpeg 现场生成（正弦音 / 静音 / 带音轨视频 / 纯视频），环境无 ffmpeg 时整体跳过。
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest web_platform/tests/test_media_assertions.py -q
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from web_platform.api_testing import media_assertions as media      # noqa: E402
from web_platform.api_testing.executor import execute_assertions    # noqa: E402

pytestmark = pytest.mark.skipif(not (media.FFPROBE and media.FFMPEG),
                                reason='环境无 ffmpeg/ffprobe，音视频断言不可测')


def _ffmpeg(out_path, *filters):
    subprocess.run(['ffmpeg', '-y', '-v', 'error'] + list(filters) + [out_path],
                   check=True, capture_output=True)


@pytest.fixture(scope='module')
def assets(tmp_path_factory):
    """生成测试资产：正弦音 / 静音 / 带音轨视频 / 纯视频（无音轨）"""
    d = tmp_path_factory.mktemp('media')
    tone = str(d / 'tone.wav')
    silence = str(d / 'silence.wav')
    video_av = str(d / 'video_av.mp4')      # 视频 + 440Hz 音轨
    video_only = str(d / 'video_only.mp4')  # 纯视频，无音轨
    _ffmpeg(tone, '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-ar', '8000', '-ac', '1')
    _ffmpeg(silence, '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono', '-t', '1')
    _ffmpeg(video_av, '-f', 'lavfi', '-i', 'testsrc=duration=1:size=128x64:rate=10',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest')
    _ffmpeg(video_only, '-f', 'lavfi', '-i', 'testsrc=duration=1:size=128x64:rate=10',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p')
    return {'tone': tone, 'silence': silence, 'video_av': video_av, 'video_only': video_only}


def _check(**kw):
    """音视频断言行（统一 media_check）：字段 → 期望值，用 evaluate 走完整适配层"""
    a = {'name': '音视频检测', 'type': 'media_check'}
    a.update(kw)
    return a


# ---------------- 公共方法 check_media：填哪项查哪项 ----------------
def test_only_format_and_duration(assets):
    """TC_MEDIA_001 正向（用户主场景）：只填格式+时长，其余留空 → 只校验这两项且通过"""
    passed, actual, err = media.check_media(assets['tone'], {
        'media_type': 'audio', 'codec': 'pcm_s16le',
        'duration_min': '0.5', 'duration_max': '2'})
    assert passed, err
    assert actual['codec_name'] == 'pcm_s16le'
    assert 0.5 <= actual['duration'] <= 2


def test_all_fields_blank_only_requires_stream(assets):
    """TC_MEDIA_002 边界：一项都不填 → 只要求目标轨存在，通过（留空=不检查）"""
    passed, actual, err = media.check_media(assets['tone'], {'media_type': 'audio'})
    assert passed, err
    assert actual['codec_type'] == 'audio'


def test_no_options_at_all(assets):
    """TC_MEDIA_003 边界：options 缺省（None）也按音频轨存在判定"""
    passed, _, err = media.check_media(assets['tone'])
    assert passed, err


def test_codec_mismatch(assets):
    """TC_MEDIA_004 异常：编码不符 → 报「格式是 X，期望 Y」"""
    passed, _, err = media.check_media(assets['tone'],
                                       {'media_type': 'audio', 'codec': 'aac'})
    assert not passed and '格式是 pcm_s16le' in err and '期望 aac' in err


def test_duration_range_out(assets):
    """TC_MEDIA_005 边界：时长下限超标 / 上限超标均失败"""
    passed, _, err = media.check_media(assets['tone'],
                                       {'media_type': 'audio', 'duration_min': '5'})
    assert not passed and '不满足下限' in err
    passed, _, err = media.check_media(assets['tone'],
                                       {'media_type': 'audio', 'duration_max': '0.2'})
    assert not passed and '不满足上限' in err


# ---------------- 分辨率：只有视频查，音频自动跳过 ----------------
def test_video_resolution_hit(assets):
    """TC_MEDIA_006 正向：视频分辨率命中"""
    passed, actual, err = media.check_media(assets['video_av'],
                                            {'media_type': 'video', 'resolution': '128x64'})
    assert passed, err
    assert actual['resolution'] == '128x64'


def test_video_resolution_mismatch(assets):
    """TC_MEDIA_007 异常：视频分辨率不符 → 报实际值与期望值"""
    passed, _, err = media.check_media(assets['video_av'],
                                       {'media_type': 'video', 'resolution': '1280x720'})
    assert not passed and '分辨率是 128x64' in err and '期望 1280x720' in err


def test_video_resolution_bad_format(assets):
    """TC_MEDIA_008 异常（边界）：分辨率写法非法 → 明确提示格式"""
    passed, _, err = media.check_media(assets['video_av'],
                                       {'media_type': 'video', 'resolution': '高清'})
    assert not passed and '分辨率格式' in err


def test_audio_skips_resolution(assets):
    """TC_MEDIA_009 正向（用户诉求）：音频断言填了分辨率也跳过，不影响通过"""
    passed, actual, err = media.check_media(assets['tone'], {
        'media_type': 'audio', 'codec': 'pcm_s16le', 'resolution': '1280x720'})
    assert passed, err
    assert actual['resolution'] is None          # 音频轨本来就没有分辨率


def test_audio_skips_resolution_via_evaluate(assets):
    """TC_MEDIA_010 正向：evaluate 层同样对音频跳过分辨率（哪怕表单填了）"""
    passed, _, err = media.evaluate('media_check',
                                    _check(media_type='audio', resolution='1280x720'),
                                    assets['tone'])
    assert passed, err


# ---------------- 有无声音（静音阈值 dB） ----------------
def test_sound_tone_has_sound(assets):
    """TC_MEDIA_011 正向：正弦音最大音量高于阈值 → 有声音"""
    passed, actual, err = media.check_media(assets['tone'],
                                            {'media_type': 'audio', 'sound': '-40'})
    assert passed, err
    assert actual['max_volume'] > -40 and actual['sound_threshold'] == -40


def test_sound_silence_detected(assets):
    """TC_MEDIA_012 异常：静音文件 → 判定为静音"""
    passed, actual, err = media.check_media(assets['silence'],
                                            {'media_type': 'audio', 'sound': '-40'})
    assert not passed and '检测到静音' in err
    assert actual['max_volume'] <= -40


def test_sound_no_audio_stream(assets):
    """TC_MEDIA_013 异常（前置检查）：纯视频无音轨 → 无法检测有无声音"""
    passed, _, err = media.check_media(assets['video_only'],
                                       {'media_type': 'audio', 'sound': '-40'})
    assert not passed and '没有音频轨' in err


def test_sound_bad_threshold(assets):
    """TC_MEDIA_014 边界：阈值非数字 → 失败并明确报错"""
    passed, _, err = media.check_media(assets['tone'],
                                       {'media_type': 'audio', 'sound': 'abc'})
    assert not passed and '阈值不是数字' in err


def test_sound_on_video_with_audio_track(assets):
    """TC_MEDIA_015 正向（容器无关）：带音轨视频选「视频」也能查有无声音"""
    passed, _, err = media.check_media(assets['video_av'],
                                       {'media_type': 'video', 'sound': '-40'})
    assert passed, err


def test_sound_plus_resolution_combined(assets):
    """TC_MEDIA_016 正向：一次断言同时查分辨率与有无声音"""
    passed, actual, err = media.check_media(assets['video_av'], {
        'media_type': 'video', 'resolution': '128x64', 'sound': '-40'})
    assert passed, err
    assert actual['resolution'] == '128x64' and actual['max_volume'] > -40


# ---------------- 码率 ----------------
def test_bitrate_range(assets):
    """TC_MEDIA_017 正向/异常：码率范围命中；超上限时报实际码率"""
    passed, actual, err = media.check_media(assets['video_av'],
                                            {'media_type': 'video', 'bitrate_min': '1'})
    assert passed, err
    assert actual['bit_rate_kbps'] and actual['bit_rate_kbps'] > 1
    passed, _, err = media.check_media(assets['video_av'],
                                       {'media_type': 'video', 'bitrate_max': '1'})
    assert not passed and '不满足上限' in err


# ---------------- 可选：采样率 / 声道（兼容既有数据） ----------------
def test_sample_rate_and_channels(assets):
    """TC_MEDIA_018 正向/异常：采样率与声道数（支持区间）"""
    passed, actual, err = media.check_media(assets['tone'], {
        'media_type': 'audio', 'sample_rate': '8000-48000', 'channels': '1'})
    assert passed, err
    assert int(actual['sample_rate']) == 8000 and int(actual['channels']) == 1
    passed, _, err = media.check_media(assets['tone'],
                                       {'media_type': 'audio', 'sample_rate': '44100'})
    assert not passed and '采样率是 8000Hz' in err
    passed, _, err = media.check_media(assets['tone'],
                                       {'media_type': 'audio', 'channels': '2'})
    assert not passed and '声道数是 1' in err


# ---------------- 目标轨缺失 / 空文件 ----------------
def test_audio_file_checked_as_video(assets):
    """TC_MEDIA_019 异常：音频文件做视频检测 → 报没有视频轨及实际轨类型"""
    passed, actual, err = media.check_media(assets['tone'], {'media_type': 'video'})
    assert not passed and '文件里没有视频轨' in err
    assert actual['streams'] == ['audio']


def test_audio_of_video_container(assets):
    """TC_MEDIA_020 正向（容器无关）：带音轨视频的音频检测同样可用"""
    passed, actual, err = media.check_media(assets['video_av'],
                                            {'media_type': 'audio', 'codec': 'aac'})
    assert passed, err
    assert actual['codec_name'] == 'aac'


def test_empty_file(tmp_path):
    """TC_MEDIA_021 异常：0 字节文件 → 失败且错误信息可定位"""
    empty = str(tmp_path / 'empty.wav')
    open(empty, 'wb').close()
    passed, _, err = media.check_media(empty, {'media_type': 'audio'})
    assert not passed and err


# ---------------- evaluate 适配层 + 旧类型兼容 ----------------
def test_evaluate_media_check_adapter(assets):
    """TC_MEDIA_022 正向：evaluate('media_check', 字段) 正确透传到公共方法"""
    passed, actual, err = media.evaluate('media_check', _check(
        media_type='video', codec='h264', resolution='128x64',
        duration_min='0.5', duration_max='2', bitrate_min='1'), assets['video_av'])
    assert passed, err
    assert actual['codec_name'] == 'h264' and actual['resolution'] == '128x64'


def test_evaluate_media_check_sound_threshold_field(assets):
    """TC_MEDIA_023 正向：sound_threshold 字段（表单字段名）→ 公共方法的 sound"""
    passed, _, err = media.evaluate('media_check',
                                    _check(media_type='audio', sound_threshold='-40'),
                                    assets['tone'])
    assert passed, err
    passed, _, err = media.evaluate('media_check',
                                    _check(media_type='audio', sound_threshold='-40'),
                                    assets['silence'])
    assert not passed and '检测到静音' in err


def test_legacy_media_volume(assets):
    """TC_MEDIA_024 正向（旧数据）：media_volume 折算成音频有无声音检测"""
    passed, actual, err = media.evaluate('media_volume',
                                         {'name': 'v', 'type': 'media_volume', 'expected': -40},
                                         assets['tone'])
    assert passed, err
    assert actual['max_volume'] > -40


def test_legacy_media_video(assets):
    """TC_MEDIA_025 正向（旧数据）：media_video 折算成视频检测"""
    passed, _, err = media.evaluate('media_video',
                                    {'name': 'v', 'type': 'media_video',
                                     'codec': 'h264', 'resolution': '128x64'},
                                    assets['video_av'])
    assert passed, err


def test_legacy_media_audio(assets):
    """TC_MEDIA_026 正向（旧数据）：media_audio 折算成音频检测"""
    passed, _, err = media.evaluate('media_audio',
                                    {'name': 'a', 'type': 'media_audio',
                                     'codec': 'pcm_s16le', 'sample_rate': '8000'},
                                    assets['tone'])
    assert passed, err


def test_legacy_media_stream(assets):
    """TC_MEDIA_027 正向（旧数据兼容）：media_stream 按 media_type 归到视频/音频检测"""
    passed, _, err = media.evaluate('media_stream', {
        'name': 'stream', 'type': 'media_stream', 'media_type': 'audio',
        'codec': 'pcm_s16le', 'duration_min': '0.5'}, assets['tone'])
    assert passed, err
    passed, actual, err = media.evaluate('media_stream', {
        'name': 'stream', 'type': 'media_stream', 'media_type': 'video',
        'resolution': '128x64'}, assets['video_av'])
    assert passed, err
    assert actual['resolution'] == '128x64'


# ---------------- 解析工具 ----------------
def test_parse_range_and_resolution():
    """TC_MEDIA_028 边界：范围与分辨率输入解析（含单值、半开、非法）"""
    assert media.parse_range('0.5-30') == (0.5, 30.0)
    assert media.parse_range('200-') == (200.0, None)
    assert media.parse_range('-720') == (None, 720.0)
    assert media.parse_range('5') == (5.0, 5.0)
    assert media.parse_range('abc') == (None, None)
    assert media.parse_resolution('1280x720') == (1280, 720)
    assert media.parse_resolution('1280*720') == (1280, 720)
    assert media.parse_resolution('1280×720') == (1280, 720)
    assert media.parse_resolution('高清') is None


# ---------------- 与执行器 / 响应体的集成 ----------------
def _fake_response(content, ctype='audio/wav', url='http://127.0.0.1:8080/api-testing/mock/media.wav'):
    import requests
    r = requests.Response()
    r.status_code = 200
    r._content = content
    r.headers['content-type'] = ctype
    r.url = url
    return r


def test_materialize_suffix(assets):
    """TC_MEDIA_029 边界：临时文件后缀取自 Content-Type，缺失时从 URL 兜底"""
    with open(assets['tone'], 'rb') as f:
        content = f.read()
    p1 = media.materialize_response(_fake_response(content, 'audio/wav'))
    p2 = media.materialize_response(_fake_response(content, 'application/octet-stream',
                                                   'http://x/api-testing/mock/media.wav'))
    try:
        assert p1.endswith('.wav') and p2.endswith('.wav')
        assert os.path.getsize(p1) == len(content)
    finally:
        os.unlink(p1)
        os.unlink(p2)


def test_executor_media_check_integration(assets):
    """TC_MEDIA_030 正向（执行器集成）：一条 media_check 覆盖格式/时长/分辨率/有无声音/码率"""
    with open(assets['video_av'], 'rb') as f:
        resp = _fake_response(f.read(), 'video/mp4')
    results = execute_assertions(resp, [
        _check(media_type='video', codec='h264', resolution='128x64',
               duration_min='0.5', duration_max='3', bitrate_min='1', sound_threshold='-40'),
        {'name': '状态码', 'type': 'status_code', 'expected': 200},
    ])
    assert all(r['passed'] for r in results), [r.get('error') for r in results]
    assert results[0]['actual']['resolution'] == '128x64'
    assert results[0]['actual']['max_volume'] > -40


def test_executor_media_fail_keeps_error(assets):
    """TC_MEDIA_031 异常（执行器集成）：静音断言失败时 error 带判定信息，普通断言不受影响"""
    with open(assets['silence'], 'rb') as f:
        resp = _fake_response(f.read())
    results = execute_assertions(resp, [
        _check(media_type='audio', sound_threshold='-40'),
        {'name': '状态码', 'type': 'status_code', 'expected': 200},
    ])
    assert not results[0]['passed'] and '检测到静音' in results[0]['error']
    assert results[1]['passed']


def test_executor_legacy_types_still_run(assets):
    """TC_MEDIA_032 正向（兼容）：旧断言类型经执行器仍可执行"""
    with open(assets['video_av'], 'rb') as f:
        resp = _fake_response(f.read(), 'video/mp4')
    results = execute_assertions(resp, [
        {'name': 'v', 'type': 'media_video', 'codec': 'h264', 'resolution': '128x64'},
        {'name': 'a', 'type': 'media_audio', 'codec': 'aac'},
        {'name': 's', 'type': 'media_volume', 'expected': -40},
    ])
    assert all(r['passed'] for r in results), [r.get('error') for r in results]
