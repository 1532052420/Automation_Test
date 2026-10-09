# -*- coding: utf-8 -*-
"""官方 `maestro mcp` 最小 stdio 客户端（P2 设备探索通道）

只实现本平台需要的 MCP 能力：initialize / tools/list / tools/call（方案 2.4：
直接复用官方 Maestro MCP，不自研协议栈）。帧格式为换行分隔 JSON-RPC 2.0
（已用真机探针验证，Maestro 2.10.0 / server 1.0.0）。

线程模型：全局单例 + 串行锁（P2 观察频率低，串行足够）；读线程按 id 分发响应；
每个调用带超时，绝不无限等待（方案 8.4）。
"""
import atexit
import base64
import json
import os
import queue
import shutil
import subprocess
import threading

INIT_PARAMS = {
    'protocolVersion': '2024-11-05',
    'capabilities': {},
    'clientInfo': {'name': 'automation-test-platform', 'version': '1.0'},
}


class MaestroError(Exception):
    pass


class _MaestroMCP(object):
    """单进程长连接。进程死亡时下次调用自动重启并重新握手。"""

    def __init__(self):
        self._proc = None
        # 可重入锁：_rpc 持锁期间 _ensure 会再走 _rpc(initialize)，必须 RLock
        self._lock = threading.RLock()
        self._rid = 0
        self._waiters = {}

    # ---------------- 进程与握手 ----------------

    def _ensure(self):
        if self._proc is not None and self._proc.poll() is None:
            return
        exe = shutil.which('maestro') or os.path.expanduser('~/.maestro/bin/maestro')
        if not os.path.exists(exe):
            raise MaestroError('maestro CLI 未安装（本机应已装 2.10.0，检查 PATH）')
        self._proc = subprocess.Popen(
            [exe, 'mcp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        t = threading.Thread(target=self._read_loop)
        t.daemon = True
        t.start()
        self._rpc('initialize', INIT_PARAMS, timeout=30)
        self._notify('notifications/initialized')

    def _read_loop(self):
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            waiter = self._waiters.get(msg.get('id'))
            if waiter is not None:
                waiter.put(msg)

    def _notify(self, method):
        try:
            self._proc.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': method}) + '\n')
            self._proc.stdin.flush()
        except Exception:
            raise MaestroError('maestro mcp 进程通信失败')

    def _rpc(self, method, params=None, timeout=60):
        with self._lock:
            self._ensure()
            self._rid += 1
            rid = self._rid
            self._waiters[rid] = queue.Queue()
            try:
                self._proc.stdin.write(json.dumps(
                    {'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params or {}}) + '\n')
                self._proc.stdin.flush()
                try:
                    msg = self._waiters[rid].get(timeout=timeout)
                except queue.Empty:
                    raise MaestroError('%s 超时（%.0fs）——首次对真机调用需安装设备驱动，可稍后重试' % (method, timeout))
                if 'error' in msg:
                    err = msg['error']
                    raise MaestroError(str(err.get('message') if isinstance(err, dict) else err))
                return msg.get('result')
            finally:
                self._waiters.pop(rid, None)

    # ---------------- 工具调用 ----------------

    def _call_tool(self, name, args=None, timeout=90):
        res = self._rpc('tools/call', {'name': name, 'arguments': args or {}}, timeout=timeout) or {}
        texts, images = [], []
        for c in res.get('content') or []:
            if c.get('type') == 'image':
                images.append(c)
            elif c.get('type') == 'text':
                t = c.get('text', '')
                if t.startswith('Important: Maestro Viewer'):
                    continue    # Viewer 推广语不是工具结果，混进报错会污染提示
                texts.append(t)
        if res.get('isError'):
            raise MaestroError(' / '.join(texts)[:300] or 'maestro 工具执行失败')
        return texts, images

    @staticmethod
    def _last_json(texts):
        """list_devices/inspect_screen 的结果 JSON 在最后一段 text（首段是 Viewer 提示）"""
        for t in reversed(texts):
            try:
                data = json.loads(t)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
        return None

    def list_devices(self):
        texts, _ = self._call_tool('list_devices', timeout=30)
        data = self._last_json(texts)
        return (data or {}).get('devices') or []

    def screenshot(self, udid):
        _, images = self._call_tool('take_screenshot', {'device_id': udid}, timeout=120)
        if not images:
            raise MaestroError('take_screenshot 未返回图像')
        return base64.b64decode(images[0]['data'])

    def hierarchy(self, udid):
        texts, _ = self._call_tool('inspect_screen', {'device_id': udid}, timeout=120)
        data = self._last_json(texts)
        if data is None:
            raise MaestroError('inspect_screen 未返回层级 JSON')
        return data

    def run_flow(self, udid, yaml_text, timeout=180):
        """受控探索阶段执行临时 Maestro flow（P2 仅观察不调用；P3+ 探索引擎使用）"""
        texts, _ = self._call_tool('run', {'device_id': udid, 'yaml': yaml_text}, timeout=timeout)
        return '\n'.join(texts)[:2000]

    def stop(self):
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None


_maestro = None


def get_maestro():
    global _maestro
    if _maestro is None:
        _maestro = _MaestroMCP()
        atexit.register(_maestro.stop)
    return _maestro


def maestro_available():
    return bool(shutil.which('maestro') or os.path.exists(os.path.expanduser('~/.maestro/bin/maestro')))


def friendly_error(e):
    """MCP/设备错误 → 面向测试人员的中文提示"""
    s = str(e)
    if 'not connected' in s or 'not found' in s:
        return '设备未连接：检查 USB / 无线调试，`adb devices` 应显示 device 状态'
    if '超时' in s:
        return 'Maestro 调用超时：首次对真机调用需安装设备驱动（手机上确认弹窗），请重试'
    return 'Maestro: ' + s[:160]
