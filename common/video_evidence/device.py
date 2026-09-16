# -*- coding: utf-8 -*-
"""ADB 录屏生命周期、失败截图、文件拉取与证据视频裁剪。

提供两种录屏后端，接口一致，按设备能力自动选择：
- AdbScreenrecordRecorder: 设备端有 screenrecord 二进制（标准 Android 设备，首选，
  帧率足，单次上限 180s）
- FrameLoopRecorder: 设备无 screenrecord（如部分 HarmonyOS/华为设备），
  用 screencap 抽帧循环兜底，约 5fps；帧号+抓取时刻索引写入 frames.tsv（抽帧日志）

每个用例的录屏全过程（启动/停止/拉取/抽帧/裁剪）记录在 work_dir/recording.log，
失败时由 conftest 整体挂入 allure 附件 recording_log。
"""
import datetime
import os
import shutil
import subprocess
import threading
import time
import uuid

from common.video_evidence.config import find_tool
from common.video_evidence.video import crop_failure_video, probe_duration


class RecorderError(Exception):
    pass


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _time_tag(ts=None):
    dt = datetime.datetime.fromtimestamp(ts) if ts else datetime.datetime.now()
    return dt.strftime('%H:%M:%S.%f')[:-3]


class RecordingLog(object):
    """录屏过程日志：记录后端、起止时刻、抽帧索引、拉取/裁剪过程，失败时整体挂入 allure。"""

    def __init__(self, path):
        self.path = str(path)
        _ensure_dir(os.path.dirname(self.path))

    def write(self, msg):
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write('[%s] %s\n' % (_time_tag(), msg))
        except OSError:
            pass

    def read(self, max_chars=60000):
        try:
            with open(self.path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except OSError:
            return ''
        if len(content) > max_chars:
            content = content[:max_chars] + '\n...(日志过长已截断)'
        return content


class AdbScreenrecordRecorder:
    """基于 `adb shell screenrecord` 的录屏器（首选后端）。"""

    def __init__(self, serial, tmp_dir, node_name, time_limit=180, bit_rate=4000000):
        self.serial = serial
        self.node_name = node_name
        self.time_limit = max(3, min(180, int(time_limit)))
        self.bit_rate = int(bit_rate)
        self._adb = find_tool('adb')
        if not self._adb:
            raise RecorderError('未找到 adb 命令')
        self.remote_path = '/sdcard/evidence_%s.mp4' % uuid.uuid4().hex
        self.work_dir = os.path.join(str(tmp_dir), node_name)
        _ensure_dir(self.work_dir)
        self.recording_log = RecordingLog(os.path.join(self.work_dir, 'recording.log'))
        self.started_at = None
        self._proc = None
        self._log_f = None

    def start(self):
        self.recording_log.write('后端=adb screenrecord 设备=%s 开始录制(单次上限%ds) '
                                 'bit_rate=%d 远端文件=%s'
                                 % (self.serial, self.time_limit, self.bit_rate, self.remote_path))
        cmd = [self._adb, '-s', self.serial, 'shell', 'screenrecord',
               '--bit-rate', str(self.bit_rate), '--time-limit', str(self.time_limit),
               self.remote_path]
        self._log_f = open(os.path.join(self.work_dir, 'screenrecord.log'), 'ab')
        self._proc = subprocess.Popen(
            cmd, stdout=self._log_f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        self.started_at = time.time()
        time.sleep(0.8)  # 给 screenrecord 启动与首帧时间
        if self._proc.poll() is not None:
            raise RecorderError('screenrecord 启动后立即退出 rc=%s' % self._proc.returncode)
        self.recording_log.write('录制启动成功')

    def stop(self, wait_seconds=0):
        """wait_seconds > 0 时先继续录制（失败后延迟收尾的关键点），再正常停止。"""
        if self._proc is None:
            return
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        # 给设备端 screenrecord 发 SIGINT(2)，触发其写全 moov atom 后正常退出
        r = subprocess.run([self._adb, '-s', self.serial, 'shell', 'pkill', '-2', 'screenrecord'],
                           capture_output=True, text=True, timeout=10)
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)
        time.sleep(0.5)  # 等设备端文件落盘
        if self._log_f is not None:
            self._log_f.close()
            self._log_f = None
        self.recording_log.write('录制已停止(pkill rc=%s) 总时长≈%.1fs'
                                 % (r.returncode, time.time() - (self.started_at or time.time())))

    def _pull(self):
        local = os.path.join(self.work_dir, '%s_raw.mp4' % self.node_name)
        r = subprocess.run([self._adb, '-s', self.serial, 'pull', self.remote_path, local],
                           capture_output=True, text=True, timeout=60)
        if not os.path.exists(local) or os.path.getsize(local) == 0:
            raise RecorderError('拉取视频失败: %s' % (r.stderr or r.stdout).strip()[:200])
        # 拉取成功后清理设备端残留
        subprocess.run([self._adb, '-s', self.serial, 'shell', 'rm', '-f', self.remote_path],
                       capture_output=True, timeout=10)
        self.recording_log.write('原始视频已拉取: %s (%.2fs, %d字节)'
                                 % (local, probe_duration(local) or -1, os.path.getsize(local)))
        return local

    def build_video(self, t_fail, out_path, before, after):
        """产出 [t_fail-before, t_fail+after] 的失败证据视频；裁剪失败返回原始视频兜底。"""
        raw = self._pull()
        try:
            offset = max(0.0, t_fail - self.started_at)
            self.recording_log.write('裁剪失败证据: 失败偏移=%.2fs 窗口=[T-%ss, T+%ss]'
                                     % (offset, before, after))
            crop_failure_video(raw, out_path, offset, before=before, after=after)
            self.recording_log.write('证据视频已生成: %s (%.2fs)'
                                     % (out_path, probe_duration(out_path) or -1))
            os.remove(raw)
            return str(out_path)
        except Exception as exc:
            self.recording_log.write('裁剪失败(用原始视频兜底): %s' % exc)
            return raw

    def discard(self, keep=False):
        self.stop(wait_seconds=0)
        if keep:
            self._pull()
            self.recording_log.write('用例成功，按配置保留原始视频')
            return
        subprocess.run([self._adb, '-s', self.serial, 'shell', 'rm', '-f', self.remote_path],
                       capture_output=True, timeout=10)
        self.recording_log.write('用例成功，临时录屏已清理')
        shutil.rmtree(self.work_dir, ignore_errors=True)


class FrameLoopRecorder:
    """screencap 抽帧循环兜底录屏：适配无 screenrecord 的设备（如 HarmonyOS/华为）。

    按约 5fps 用 adb exec-out screencap 抓帧存本机并记录墙钟索引(frames.tsv)；
    失败时按 [t_fail-before, t_fail+after] 时间窗选帧重编码成 mp4。
    帧率低于 screenrecord，仅作为设备能力不足时的兜底。
    """
    FPS = 5

    def __init__(self, serial, tmp_dir, node_name):
        self.serial = serial
        self.node_name = node_name
        self._adb = find_tool('adb')
        if not self._adb:
            raise RecorderError('未找到 adb 命令')
        self._ffmpeg = find_tool('ffmpeg')
        if not self._ffmpeg:
            raise RecorderError('未找到 ffmpeg 命令')
        self.work_dir = os.path.join(str(tmp_dir), node_name)
        self.frame_dir = os.path.join(self.work_dir, 'frames')
        _ensure_dir(self.frame_dir)
        self.index_path = os.path.join(self.work_dir, 'frames.tsv')
        self.recording_log = RecordingLog(os.path.join(self.work_dir, 'recording.log'))
        self.started_at = None
        self._stop_flag = False
        self._thread = None

    def start(self):
        self.recording_log.write('后端=screencap抽帧循环(约%dfps) 设备=%s 开始抓帧'
                                 % (self.FPS, self.serial))
        self.started_at = time.time()
        self._stop_flag = False
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        time.sleep(0.6)

    def _capture_loop(self):
        interval = 1.0 / self.FPS
        idx = 0
        with open(self.index_path, 'w') as idx_f:
            while not self._stop_flag:
                t0 = time.time()
                try:
                    png = subprocess.run(
                        [self._adb, '-s', self.serial, 'exec-out', 'screencap', '-p'],
                        capture_output=True, timeout=15).stdout
                except Exception:
                    png = b''
                if png:
                    with open(os.path.join(self.frame_dir, 'frame_%05d.png' % idx), 'wb') as fh:
                        fh.write(png)
                    idx_f.write('%d\t%.3f\n' % (idx, time.time()))
                    idx_f.flush()
                    idx += 1
                time.sleep(max(0.0, interval - (time.time() - t0)))

    def stop(self, wait_seconds=0):
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        self._stop_flag = True
        if self._thread:
            self._thread.join(timeout=20)
        self.recording_log.write('抓帧已停止 总时长≈%.1fs' % (time.time() - (self.started_at or time.time())))

    def build_video(self, t_fail, out_path, before, after):
        """按失败时间窗选帧重编码成证据视频；帧号+抓取时刻作为抽帧日志写入 recording.log。"""
        low, high = t_fail - before, t_fail + after
        chosen, total = [], 0
        with open(self.index_path) as f:
            for line in f:
                parts = line.split()
                if len(parts) != 2:
                    continue
                total += 1
                if low <= float(parts[1]) <= high:
                    chosen.append(int(parts[0]))
        self.recording_log.write('抽帧时间窗=[%.2f, %.2f] 总帧数=%d 窗口内选中=%d'
                                 % (low, high, total, len(chosen)))
        # 抽帧日志：逐帧列出 帧号 + 抓取时刻（截断保护，完整索引在 frames.tsv）
        with open(self.index_path) as f:
            lines = f.readlines()
        log_lines = ['帧号\t抓取时刻']
        for line in lines:
            parts = line.split()
            if len(parts) == 2:
                log_lines.append('frame_%05d\t%s' % (int(parts[0]), _time_tag(float(parts[1]))))
        self.recording_log.write('--- 抽帧索引(frames.tsv) 共%d帧 ---\n%s'
                                 % (len(log_lines) - 1, '\n'.join(log_lines[:500])))
        if not chosen:
            raise RecorderError('失败时间窗内无可用帧')
        sel_dir = os.path.join(self.work_dir, 'selected')
        shutil.rmtree(sel_dir, ignore_errors=True)
        _ensure_dir(sel_dir)
        for n, idx in enumerate(chosen):
            shutil.copyfile(os.path.join(self.frame_dir, 'frame_%05d.png' % idx),
                            os.path.join(sel_dir, 'frame_%05d.png' % n))
        subprocess.run(
            [self._ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
             '-framerate', str(self.FPS), '-i', os.path.join(sel_dir, 'frame_%05d.png'),
             '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
             str(out_path)],
            capture_output=True, text=True, timeout=120)
        if not os.path.exists(str(out_path)) or os.path.getsize(str(out_path)) == 0:
            raise RecorderError('ffmpeg 帧合成失败')
        self.recording_log.write('抽帧合成完成: %s (%.2fs)'
                                 % (out_path, probe_duration(out_path) or -1))
        return str(out_path)

    def discard(self, keep=False):
        self.stop(wait_seconds=0)
        if keep:
            self.recording_log.write('用例成功，按配置保留抓帧目录: %s' % self.frame_dir)
            return
        self.recording_log.write('用例成功，抓帧临时文件已清理')
        shutil.rmtree(self.work_dir, ignore_errors=True)


_backend_cache = {}


def probe_screenrecord(serial):
    """探测设备端是否有 screenrecord 二进制（结果按设备缓存）。"""
    if serial not in _backend_cache:
        adb = find_tool('adb')
        if not adb:
            _backend_cache[serial] = False
        else:
            r = subprocess.run([adb, '-s', serial, 'shell', 'command -v screenrecord'],
                               capture_output=True, text=True, timeout=10)
            _backend_cache[serial] = bool(r.stdout.strip())
    return _backend_cache[serial]


def create_recorder(cfg, node_name):
    """按设备能力自动选择录屏后端。"""
    serial = cfg.adb_serial
    if not serial:
        raise RecorderError('未检测到可用设备（连接设备或设置 ADB_SERIAL）')
    if not cfg.ffmpeg:
        raise RecorderError('未找到 ffmpeg，无法处理失败证据视频')
    if probe_screenrecord(serial):
        return AdbScreenrecordRecorder(serial, cfg.tmp_dir, node_name,
                                       time_limit=getattr(cfg, 'max_segment_seconds', 180),
                                       bit_rate=getattr(cfg, 'bit_rate', 4000000))
    return FrameLoopRecorder(serial, cfg.tmp_dir, node_name)


def capture_screenshot(serial, artifact_dir, name):
    """用 adb exec-out screencap 截当前屏幕到本地 PNG，返回本地路径。"""
    adb = find_tool('adb')
    if not adb:
        raise RecorderError('未找到 adb 命令')
    local = os.path.join(str(artifact_dir), '%s.png' % name)
    _ensure_dir(str(artifact_dir))
    with open(local, 'wb') as f:
        subprocess.run([adb, '-s', serial, 'exec-out', 'screencap', '-p'],
                       stdout=f, stderr=subprocess.DEVNULL, timeout=15)
    if not os.path.exists(local) or os.path.getsize(local) == 0:
        if os.path.exists(local):
            os.remove(local)
        raise RecorderError('screencap 截图为空')
    return local
