# -*- coding: utf-8 -*-
"""媒体产物检测 · 引擎 + API 测试

自包含：测试夹具用标准库（wave/struct/zlib）合成健康与缺陷样本，视频样本用
本机 ffmpeg 合成（未装 ffmpeg 的机器自动跳过视频用例，其余照常）。
运行：cd <项目根> && .venv/bin/python -m pytest media_validator/tests -v
"""
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from media_validator import engine, rules as rules_mod, store          # noqa: E402
from media_validator.vendor.rendercheck._ffmpeg import ToolUnavailable  # noqa: E402

HAS_FFMPEG = bool(shutil.which('ffmpeg')) and bool(shutil.which('ffprobe'))

# ---------------------------------------------------------------- 夹具工厂
def make_wav(path, seconds=2.0, silent=False, rate=44100):
    """标准库合成 16bit 单声道 WAV：默认 440Hz 正弦（可听），silent=True 为全零样本"""
    import wave
    frames = int(rate * seconds)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        if silent:
            blob = b'\x00\x00' * frames
        else:
            blob = b''.join(struct.pack('<h', int(0.35 * 32767 * math.sin(2 * math.pi * 440 * i / rate)))
                            for i in range(frames))
        w.writeframes(blob)
    return path


def make_png(path, size=64, solid=False):
    """标准库合成 8bit RGB PNG：默认渐变（亮度跨度大），solid=True 为纯色（空白图）"""
    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    row = b''
    rows = []
    for y in range(size):
        if solid:
            px = [128] * (size * 3)                     # 纯色：三通道恒定
        else:
            px = [x * 4 % 256 if c == 0 else (y * 4 % 256 if c == 1 else 30)
                  for x in range(size) for c in (0, 1, 2)]
        rows.append(b'\x00' + bytes(px))
    raw = b''.join(rows)
    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', ihdr))
        f.write(chunk(b'IDAT', zlib.compress(raw)))
        f.write(chunk(b'IEND', b''))
    return path


def make_broken(path, ext='png'):
    """损坏样本：合法魔数 + 截断内容（头部能骗过嗅探，解码必炸）"""
    with open(path, 'wb') as f:
        if ext == 'png':
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 64)   # 有头无数据
        else:
            f.write(os.urandom(256))
    return path


def make_mp4(path, kind='ok', seconds=3.0):
    """ffmpeg 合成视频：ok=彩条+正弦音；black=纯黑无音；frozen=纯红静止无音"""
    if kind == 'ok':
        cmd = ['ffmpeg', '-y', '-nostdin',
               '-f', 'lavfi', '-i', 'testsrc2=duration=%g:size=320x240:rate=25' % seconds,
               '-f', 'lavfi', '-i', 'sine=frequency=440:duration=%g' % seconds,
               '-c:v', 'mpeg4', '-c:a', 'aac', '-shortest', path]
    else:
        color = 'black' if kind == 'black' else 'red'
        cmd = ['ffmpeg', '-y', '-nostdin',
               '-f', 'lavfi', '-i', 'color=%s:size=320x240:rate=25:duration=%g' % (color, seconds),
               '-c:v', 'mpeg4', '-an', path]
    subprocess.run(cmd, capture_output=True, timeout=120)
    return path


# ---------------------------------------------------------------- 共享夹具
@pytest.fixture(scope='session')
def wav_ok(tmp_path_factory):
    return make_wav(str(tmp_path_factory.mktemp('fx') / 'song_ok.wav'))


@pytest.fixture(scope='session')
def wav_silent(tmp_path_factory):
    return make_wav(str(tmp_path_factory.mktemp('fx') / 'song_silent.wav'), silent=True)


@pytest.fixture(scope='session')
def png_ok(tmp_path_factory):
    return make_png(str(tmp_path_factory.mktemp('fx') / 'img_ok.png'))


@pytest.fixture(scope='session')
def png_solid(tmp_path_factory):
    return make_png(str(tmp_path_factory.mktemp('fx') / 'img_solid.png'), solid=True)


@pytest.fixture(scope='session')
def png_broken(tmp_path_factory):
    return make_broken(str(tmp_path_factory.mktemp('fx') / 'img_broken.png'))


@pytest.fixture(scope='session')
def garbage_mp3(tmp_path_factory):
    return make_broken(str(tmp_path_factory.mktemp('fx') / 'track.mp3'), ext='mp3')


@pytest.fixture(scope='session')
def mp4_ok(tmp_path_factory):
    if not HAS_FFMPEG:
        pytest.skip('未安装 ffmpeg')
    return make_mp4(str(tmp_path_factory.mktemp('fx') / 'clip_ok.mp4'), kind='ok')


@pytest.fixture(scope='session')
def mp4_black(tmp_path_factory):
    if not HAS_FFMPEG:
        pytest.skip('未安装 ffmpeg')
    return make_mp4(str(tmp_path_factory.mktemp('fx') / 'clip_black.mp4'), kind='black', seconds=3.0)


@pytest.fixture(scope='session')
def mp4_frozen(tmp_path_factory):
    if not HAS_FFMPEG:
        pytest.skip('未安装 ffmpeg')
    return make_mp4(str(tmp_path_factory.mktemp('fx') / 'clip_frozen.mp4'), kind='frozen', seconds=4.0)


DEFAULT_AUDIO = rules_mod.sanitize('audio', {})
DEFAULT_VIDEO = rules_mod.sanitize('video', {})
DEFAULT_IMAGE = rules_mod.sanitize('image', {})


def item_map(report):
    return {i['key']: i for i in report['items']}


# ================================================================ 引擎层
@pytest.mark.skipif(not HAS_FFMPEG, reason='未安装 ffmpeg/ffprobe')
class TestEngineAudio:
    def test_healthy_wav_all_pass(self, wav_ok):
        """正常音频 → 全部检测项 PASS（AAA：Arrange 由夹具完成）"""
        report = engine.detect(wav_ok, 'audio', DEFAULT_AUDIO, ext='wav')
        assert report['passed'] is True
        im = item_map(report)
        assert im['integrity']['passed'] is True
        assert im['audio_track']['passed'] is True
        assert im['format']['passed'] is True          # 封装 wav 与扩展名一致
        assert im['silence']['passed'] is True          # 正弦波非纯静音

    def test_silent_wav_fails_silence(self, wav_silent):
        """全零样本音频 → 静音检测 FAIL，总判定 FAIL"""
        report = engine.detect(wav_silent, 'audio', DEFAULT_AUDIO, ext='wav')
        assert report['passed'] is False
        im = item_map(report)
        assert im['silence']['passed'] is False
        assert '静音' in (im['silence']['note'] or '') or '零样本' in (im['silence']['note'] or '')

    def test_silent_wav_passes_when_sound_rule_off(self, wav_silent):
        """关闭 require_sound 后同一文件 → 静音项不再一票否决（阈值可配）"""
        r2 = rules_mod.sanitize('audio', {'require_sound': False, 'max_silence': 3.0})
        report = engine.detect(wav_silent, 'audio', r2, ext='wav')
        assert report['passed'] is True

    def test_report_only_when_no_thresholds(self, wav_ok):
        """阈值全空 → 相关项 passed=None 仅报告，不影响总判定"""
        r0 = rules_mod.sanitize('audio', {'duration_min': None, 'duration_max': None,
                                          'min_sample_rate': None, 'min_channels': None,
                                          'max_silence': None, 'require_sound': False})
        report = engine.detect(wav_ok, 'audio', r0, ext='wav')
        im = item_map(report)
        assert im['duration']['passed'] is None
        assert im['sample_rate']['passed'] is None
        assert report['passed'] is True

    def test_garbage_mp3_fails_integrity(self, garbage_mp3):
        """随机字节伪装 .mp3 → 完整性/格式 FAIL（损坏文件产出 FAIL 报告而非 ERROR）"""
        report = engine.detect(garbage_mp3, 'audio', DEFAULT_AUDIO, ext='mp3')
        assert report['passed'] is False
        im = item_map(report)
        assert im['integrity']['passed'] is False
        assert im['format']['passed'] is False


@pytest.mark.skipif(not HAS_FFMPEG, reason='未安装 ffmpeg/ffprobe')
class TestEngineVideo:
    def test_healthy_mp4_all_pass(self, mp4_ok):
        report = engine.detect(mp4_ok, 'video', DEFAULT_VIDEO, ext='mp4')
        assert report['passed'] is True
        im = item_map(report)
        assert im['video_track']['passed'] is True
        assert im['audio_track']['passed'] is True
        assert im['resolution']['actual'] == '320x240'
        assert im['black']['passed'] is True
        assert im['freeze']['passed'] is True

    def test_black_video_fails_black(self, mp4_black):
        """纯黑视频 → 黑屏检测 FAIL（同时无音轨）"""
        r = rules_mod.sanitize('video', {'require_audio_track': False})
        report = engine.detect(mp4_black, 'video', r, ext='mp4')
        assert report['passed'] is False
        assert item_map(report)['black']['passed'] is False

    def test_frozen_video_fails_freeze(self, mp4_frozen):
        """纯红静止画面 → 冻结帧检测 FAIL"""
        r = rules_mod.sanitize('video', {'require_audio_track': False})
        report = engine.detect(mp4_frozen, 'video', r, ext='mp4')
        assert report['passed'] is False
        assert item_map(report)['freeze']['passed'] is False


@pytest.mark.skipif(not HAS_FFMPEG, reason='未安装 ffmpeg/ffprobe')
class TestEngineImage:
    def test_healthy_png_all_pass(self, png_ok):
        report = engine.detect(png_ok, 'image', DEFAULT_IMAGE, ext='png')
        assert report['passed'] is True
        im = item_map(report)
        assert im['integrity']['passed'] is True
        assert im['size']['actual'] == '64x64'
        assert im['blank']['passed'] is True

    def test_solid_png_fails_blank(self, png_solid):
        """纯色图 → 画面内容 FAIL（生成失败返回空图的典型形态）"""
        report = engine.detect(png_solid, 'image', DEFAULT_IMAGE, ext='png')
        assert report['passed'] is False
        assert item_map(report)['blank']['passed'] is False

    def test_broken_png_fails_integrity(self, png_broken):
        report = engine.detect(png_broken, 'image', DEFAULT_IMAGE, ext='png')
        assert report['passed'] is False
        im = item_map(report)
        assert im['integrity']['passed'] is False

    def test_oversize_image_fails_file_size(self, png_ok):
        r = rules_mod.sanitize('image', {'max_file_mb': 0.001})   # 1KB 阈值，64x64 PNG 必超
        report = engine.detect(png_ok, 'image', r, ext='png')
        assert item_map(report)['file_size']['passed'] is False


@pytest.mark.skipif(not HAS_FFMPEG, reason='未安装 ffmpeg/ffprobe')
class TestEngineGuards:
    def test_missing_tools_raise_engine_error(self, wav_ok, monkeypatch):
        """ffmpeg/ffprobe 缺失 → EngineError（ERROR 语义），绝不伪装成 FAIL/PASS"""
        monkeypatch.setattr(shutil, 'which', lambda name: None)
        with pytest.raises(engine.EngineError):
            engine.detect(wav_ok, 'audio', DEFAULT_AUDIO, ext='wav')

    def test_probe_fail_is_fail_not_error(self, garbage_mp3):
        """文件损坏走 FAIL（有效结果）；EngineError 仅留给基础设施故障"""
        report = engine.detect(garbage_mp3, 'audio', DEFAULT_AUDIO, ext='mp3')
        assert report.get('probe_error')            # 探针失败留痕
        assert report['passed'] is False


class TestRules:
    def test_sanitize_rejects_unknown_and_bad_types(self):
        out = rules_mod.sanitize('audio', {'duration_min': 'abc', 'hacker_key': 'x', 'require_sound': 'yes'})
        assert out['duration_min'] is None                # 'abc' 非法 → 回退默认（默认即 None）
        assert 'hacker_key' not in out
        assert out['require_sound'] is True               # 非布尔输入回退默认

    def test_sanitize_none_disables_threshold(self):
        out = rules_mod.sanitize('video', {'max_black': None})
        assert out['max_black'] is None

    def test_sanitize_clamps_below_floor(self):
        """非法负值/过小值钳到下限，而不是静默关闭（防假 PASS）"""
        out = rules_mod.sanitize('audio', {'max_silence': -5})
        assert out['max_silence'] == 0.5                  # _LIMITS 中 max_silence 下限
        out2 = rules_mod.sanitize('video', {'max_black': 0.1})
        assert out2['max_black'] == 0.5

    def test_media_type_of_whitelist(self):
        assert rules_mod.media_type_of('a.MP3') == 'audio'
        assert rules_mod.media_type_of('a.gif') is None
        assert rules_mod.media_type_of('noext') is None


class TestFpsDisplay:
    def test_garbage_nominal_not_shown(self):
        """录屏类文件的 r_frame_rate=1000000 占位值不进展示与判定，以实际均值为准"""
        txt, judge, note = engine._fps_display({'fps': 1000000.0, 'avg_fps': 71.642})
        assert txt == '71.642 fps'
        assert '1000000' not in txt and judge == 71.642 and note is None

    def test_vfr_note_when_nominal_plausible(self):
        txt, judge, note = engine._fps_display({'fps': 30.0, 'avg_fps': 24.5})
        assert '标称 30' in txt and judge == 24.5 and note and '变帧率' in note

    def test_cfr_no_note(self):
        txt, judge, note = engine._fps_display({'fps': 25.0, 'avg_fps': 25.0})
        assert txt == '25.000 fps' and judge == 25.0 and note is None

    def test_nominal_only(self):
        txt, judge, note = engine._fps_display({'fps': 25.0, 'avg_fps': None})
        assert '标称' in txt and judge == 25.0

    def test_all_garbage(self):
        txt, judge, note = engine._fps_display({'fps': 1000000.0, 'avg_fps': None})
        assert txt == '未知' and judge is None


# ================================================================ API 层
@pytest.fixture()
def client(tmp_path, monkeypatch):
    """独立 Flask app：只挂媒体检测蓝图，存储指到临时目录，互不污染"""
    monkeypatch.setattr(store, 'TASKS_FILE', str(tmp_path / 'tasks.json'))
    monkeypatch.setattr(store, 'UPLOADS_DIR', str(tmp_path / 'uploads'))
    os.makedirs(str(tmp_path / 'uploads'), exist_ok=True)

    from flask import Flask
    from media_validator.routes import bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(bp)
    return app.test_client()


@pytest.mark.skipif(not HAS_FFMPEG, reason='未安装 ffmpeg/ffprobe')
class TestApi:
    def test_upload_detect_report_lifecycle(self, client, wav_ok):
        """上传 → 待检测 → 检测 → PASS 报告 全链路"""
        with open(wav_ok, 'rb') as f:
            resp = client.post('/media-validator/api/upload',
                               data={'files': (f, 'demo_song.wav'), 'start': '0'},
                               content_type='multipart/form-data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True and len(data['created']) == 1
        task = data['created'][0]
        assert task['status'] == 'PENDING'
        assert task['media_type'] == 'audio'

        resp = client.post('/media-validator/api/detect', json={'ids': [task['id']]})
        assert resp.status_code == 200 and resp.get_json()['started'] == [task['id']]

        deadline = time.time() + 90
        final = None
        while time.time() < deadline:
            got = client.get('/media-validator/api/task/%s' % task['id']).get_json()['task']
            if got['status'] in ('PASSED', 'FAILED', 'ERROR'):   # 仅终态退出，PENDING/RUNNING 继续等
                final = got
                break
            time.sleep(0.5)
        assert final is not None, '检测 90s 未结束'
        assert final['status'] == 'PASSED'
        keys = {i['key'] for i in final['report']['items']}
        assert {'integrity', 'format', 'duration', 'audio_track', 'silence'} <= keys

    def test_upload_rejects_unsupported_ext(self, client):
        import io
        resp = client.post('/media-validator/api/upload',
                           data={'files': (io.BytesIO(b'x'), 'evil.gif')},
                           content_type='multipart/form-data')
        data = resp.get_json()
        assert data['ok'] is True and not data['created'] and len(data['rejected']) == 1

    def test_rules_endpoint(self, client):
        data = client.get('/media-validator/api/rules').get_json()
        assert set(data['rules']) == {'audio', 'video', 'image'}
        assert data['ext_types']['mp4'] == 'video'

    def test_overview_tools(self, client):
        data = client.get('/media-validator/api/overview').get_json()
        assert data['ok'] is True and 'tools' in data and 'stats' in data

    def test_sweep_rescues_stuck_running(self, client):
        """重启自愈：遗留 RUNNING 任务被启动扫描置 ERROR，且可重新检测"""
        from media_validator import routes
        store.upsert_task({'id': 'mvqa_ghost', 'filename': 'ghost.wav', 'ext': 'wav',
                           'stored_path': '/nonexistent', 'media_type': 'audio',
                           'size_bytes': 1, 'status': 'RUNNING', 'rules': {},
                           'report': None, 'error': None,
                           'created_at': 'x', 'finished_at': None})
        swept = routes.sweep_interrupted()
        assert 'mvqa_ghost' in swept
        t = store.get_task('mvqa_ghost')
        assert t['status'] == 'ERROR' and '中断' in t['error']
        store.delete_task('mvqa_ghost')

    def test_missing_task_404(self, client):
        assert client.get('/media-validator/api/task/nope').status_code == 404
        assert client.delete('/media-validator/api/task/nope').status_code == 404

    def test_delete_removes_task_and_file(self, client, wav_ok):
        with open(wav_ok, 'rb') as f:
            task = client.post('/media-validator/api/upload',
                               data={'files': (f, 'todelete.wav')},
                               content_type='multipart/form-data').get_json()['created'][0]
        assert os.path.isfile(task['stored_path'])
        assert client.delete('/media-validator/api/task/%s' % task['id']).status_code == 200
        assert client.get('/media-validator/api/task/%s' % task['id']).status_code == 404
        assert not os.path.isfile(task['stored_path'])   # 上传文件一并清理

    def test_upload_size_cap_rejects(self, client, wav_ok, monkeypatch):
        """请求级 413 预检：Content-Length 超上限的请求在读入前就被拒"""
        monkeypatch.setattr(store, 'MAX_UPLOAD_BYTES', 1024)
        with open(wav_ok, 'rb') as f:                      # 176KB > (1024+64KB) 预检线
            resp = client.post('/media-validator/api/upload',
                               data={'files': (f, 'big.wav')},
                               content_type='multipart/form-data')
        assert resp.status_code == 413                     # 请求级预检直接 413

    def test_upload_size_cap_stream_rejects(self, client, monkeypatch):
        """流式落盘上限：预检之下、单文件超限时拒收并给原因"""
        monkeypatch.setattr(store, 'MAX_UPLOAD_BYTES', 1024)
        small_but_over = io.BytesIO(b'x' * 2048)           # 2KB：过 413 预检，超 1KB 落盘上限
        resp = client.post('/media-validator/api/upload',
                           data={'files': (small_but_over, 'big.wav')},
                           content_type='multipart/form-data')
        data = resp.get_json()
        assert not data['created'] and len(data['rejected']) == 1
        assert '上限' in data['rejected'][0]['reason']

    def test_save_upload_cap_raises(self, tmp_path, monkeypatch):
        """store 层：超上限抛 ValueError 并不留残文件"""
        monkeypatch.setattr(store, 'UPLOADS_DIR', str(tmp_path))
        monkeypatch.setattr(store, 'MAX_UPLOAD_BYTES', 1024)

        class _Fake:
            def __init__(self, data):
                self.stream = io.BytesIO(data)

        with pytest.raises(ValueError):
            store.save_upload(_Fake(b'x' * 2048), 'big.wav', 'testid')
        assert not list(tmp_path.iterdir())                # 超限文件已删除，无残留

    def test_detect_one_accepts_wrapper_and_flat_rules(self, client, wav_ok):
        """单任务检测接口两种规则形态都收：{audio:{...}} 包装式与扁平式"""
        with open(wav_ok, 'rb') as f:
            task = client.post('/media-validator/api/upload',
                               data={'files': (f, 'rules.wav')},
                               content_type='multipart/form-data').get_json()['created'][0]
        tid = task['id']

        def wait_terminal():
            deadline = time.time() + 60
            while time.time() < deadline:
                t = client.get('/media-validator/api/task/%s' % tid).get_json()['task']
                if t['status'] in ('PASSED', 'FAILED', 'ERROR'):
                    return t
                time.sleep(0.3)
            raise AssertionError('检测 60s 未终态')

        # 包装式（与批量接口一致）
        r1 = client.post('/media-validator/api/task/%s/detect' % tid,
                         json={'rules': {'audio': {'max_silence': 0.5}}}).get_json()
        t1 = wait_terminal()
        assert r1['ok'] is True and t1['rules']['max_silence'] == 0.5
        # 扁平式（等上一次检测终态后再发，否则命中防重入 409）
        r2 = client.post('/media-validator/api/task/%s/detect' % tid,
                         json={'rules': {'max_silence': 20}}).get_json()
        t2 = wait_terminal()
        assert r2['ok'] is True and t2['rules']['max_silence'] == 20.0


@pytest.mark.skipif(not HAS_FFMPEG, reason='未安装 ffmpeg/ffprobe')
def test_uncaught_engine_exception_becomes_error(client, wav_ok, monkeypatch):
    """引擎意外异常 → 任务 ERROR（兜底），不无声死亡"""
    with open(wav_ok, 'rb') as f:
        task = client.post('/media-validator/api/upload',
                           data={'files': (f, 'boom.wav')},
                           content_type='multipart/form-data').get_json()['created'][0]
    from media_validator import routes
    def boom(*a, **k):
        raise RuntimeError('模拟引擎崩溃')
    monkeypatch.setattr(routes.engine, 'detect', boom)
    client.post('/media-validator/api/task/%s/detect' % task['id'], json={})
    deadline = time.time() + 20
    got = None
    while time.time() < deadline:
        got = client.get('/media-validator/api/task/%s' % task['id']).get_json()['task']
        if got['status'] in ('PASSED', 'FAILED', 'ERROR'):
            break
        time.sleep(0.3)
    assert got['status'] == 'ERROR'
    assert '模拟引擎崩溃' in got['error']


# ================================================================ 链接 / 路径来源
import http.server                                                        # noqa: E402
from functools import partial                                             # noqa: E402


@pytest.fixture(scope='module')
def media_server(tmp_path_factory):
    """本地 HTTP 服务：提供真 URL 的媒体文件（good.wav / 无扩展名 PNG / 大文件）"""
    root = tmp_path_factory.mktemp('srv')
    make_wav(str(root / 'good.wav'))
    make_png(str(root / 'rawimage'))                  # 无扩展名 → 服务端按魔数识别
    with open(str(root / 'good.wav'), 'rb') as f:
        big = f.read() * 2
    (root / 'big.wav').write_bytes(big)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {'base': 'http://127.0.0.1:%d' % srv.server_address[1], 'root': str(root)}
    srv.shutdown()


def _poll_terminal(client, tid, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = client.get('/media-validator/api/task/%s' % tid).get_json()['task']
        if t['status'] in ('PASSED', 'FAILED', 'ERROR'):
            return t
        time.sleep(0.3)
    raise AssertionError('检测 %ds 未终态' % timeout)


@pytest.mark.skipif(not HAS_FFMPEG, reason='未安装 ffmpeg/ffprobe')
class TestSources:
    def _upload_sources(self, client, sources, **extra):
        data = {'sources': json.dumps(sources), 'start': '1'}
        data.update(extra)
        return client.post('/media-validator/api/upload', data=data,
                           content_type='multipart/form-data').get_json()

    def test_url_upload_detect_pass(self, client, media_server):
        """http 链接 → 下载 → 建任务 → 检测 PASS，来源记录为链接"""
        d = self._upload_sources(client, [media_server['base'] + '/good.wav'])
        assert d['ok'] and len(d['created']) == 1
        t = d['created'][0]
        assert t['media_type'] == 'audio' and t['origin']['kind'] == 'url'
        final = _poll_terminal(client, t['id'])
        assert final['status'] == 'PASSED'

    def test_url_without_ext_sniffed(self, client, media_server):
        """无扩展名 URL → 魔数识别为 png → 建任务并检测 PASS"""
        d = self._upload_sources(client, [media_server['base'] + '/rawimage'])
        assert len(d['created']) == 1 and d['rejected'] == []
        t = d['created'][0]
        assert t['media_type'] == 'image' and t['ext'] == 'png'
        assert t['filename'].endswith('.png')
        final = _poll_terminal(client, t['id'])
        assert final['status'] == 'PASSED'

    def test_url_404_rejected(self, client, media_server):
        d = self._upload_sources(client, [media_server['base'] + '/nope.wav'])
        assert not d['created'] and '下载失败' in d['rejected'][0]['reason']

    def test_url_bad_scheme_rejected(self, client):
        d = self._upload_sources(client, ['ftp://example.com/a.mp3'])
        assert not d['created'] and '协议' in d['rejected'][0]['reason']

    def test_url_oversize_rejected(self, client, media_server, monkeypatch):
        monkeypatch.setattr(store, 'MAX_UPLOAD_BYTES', 1024)
        d = self._upload_sources(client, [media_server['base'] + '/good.wav'])
        assert not d['created'] and '上限' in d['rejected'][0]['reason']

    def test_absolute_path_upload(self, client, wav_ok):
        d = self._upload_sources(client, [wav_ok])
        assert len(d['created']) == 1 and d['created'][0]['origin']['kind'] == 'path'
        final = _poll_terminal(client, d['created'][0]['id'])
        assert final['status'] == 'PASSED'
        assert os.path.isfile(final['stored_path'])          # 副本在 uploads
        assert os.path.isfile(wav_ok)                        # 原文件不受删除影响

    def test_relative_path_upload(self, client, tmp_path, monkeypatch):
        """相对路径基于进程 CWD 解析（平台进程 = 项目根）"""
        make_wav(str(tmp_path / 'rel_ok.wav'))
        monkeypatch.chdir(str(tmp_path))
        d = self._upload_sources(client, ['rel_ok.wav'])
        assert len(d['created']) == 1
        final = _poll_terminal(client, d['created'][0]['id'])
        assert final['status'] == 'PASSED'

    def test_tilde_path_upload(self, client, tmp_path, monkeypatch):
        make_wav(str(tmp_path / 'home_ok.wav'))
        monkeypatch.setenv('HOME', str(tmp_path))
        d = self._upload_sources(client, ['~/home_ok.wav'])
        assert len(d['created']) == 1

    def test_path_missing_rejected(self, client):
        d = self._upload_sources(client, ['/no/such/file.mp4', 'no/such/rel.wav'])
        assert not d['created'] and len(d['rejected']) == 2

    def test_path_is_dir_rejected(self, client, tmp_path):
        d = self._upload_sources(client, [str(tmp_path)])
        assert not d['created'] and '不是文件' in d['rejected'][0]['reason']

    def test_path_unknown_type_rejected(self, client, tmp_path):
        p = tmp_path / 'mystery.bin'
        p.write_bytes(b'\x00\x01\x02\x03' * 16)
        d = self._upload_sources(client, [str(p)])
        assert not d['created'] and '无法识别' in d['rejected'][0]['reason']

    def test_mixed_sources_and_files(self, client, wav_ok, media_server):
        """文件 + 链接 + 路径混提：同一请求建 3 个任务"""
        with open(wav_ok, 'rb') as f:
            resp = client.post('/media-validator/api/upload',
                               data={'files': (f, 'mix.wav'),
                                     'sources': json.dumps([media_server['base'] + '/good.wav', wav_ok]),
                                     'start': '0'},
                               content_type='multipart/form-data').get_json()
        assert len(resp['created']) == 3 and resp['rejected'] == []
        kinds = {t['origin']['kind'] for t in resp['created']}
        assert kinds == {'file', 'url', 'path'}
        for t in resp['created']:
            client.delete('/media-validator/api/task/%s' % t['id'])

    def test_sources_only_bad_json_400(self, client):
        resp = client.post('/media-validator/api/upload',
                           data={'sources': '{not-json'},
                           content_type='multipart/form-data')
        assert resp.status_code == 400
