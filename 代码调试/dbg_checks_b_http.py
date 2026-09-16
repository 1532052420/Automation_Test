# -*- coding: utf-8 -*-
"""代码调试 · HTTP 客户端与平台接口检查项"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dbg_kit import check, Skip, assert_true, tmp_workdir, platform_status, http_get_json

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, status=200, extra_headers=None):
        import ujson
        body = ujson.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/get':
            self._json({'ok': True, 'method': 'GET', 'params': {k: v[0] for k, v in parse_qs(u.query).items()},
                        'x_debug': self.headers.get('X-Debug', ''), 'cookie': self.headers.get('Cookie', '')})
        elif u.path == '/cookie':
            self._json({'ok': True}, extra_headers={'Set-Cookie': 'session=debug123; Path=/'})
        elif u.path == '/file':
            body = b'debug-file-content'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == '/echo':
            self._json({'echo': u.query})
        else:
            self._json({'ok': False, 'msg': 'not found'}, status=404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode('utf-8', 'replace') if length else ''
        if urlparse(self.path).path == '/form':
            self._json({'ok': True, 'form': {k: v[0] for k, v in parse_qs(raw).items()}})
        else:
            self._json({'ok': False}, status=404)


@check('common.httpclient.doRequest', 'common/httpclient/doRequest.py',
       'HTTP 客户端全方法：GET/POST(form)/文件下载/头与 Cookie 管理/换址（本地临时服务，不依赖外网）')
def _():
    from common.httpclient.doRequest import DoRequest
    server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = 'http://127.0.0.1:%d' % port
        client = DoRequest(base)
        # GET + params
        r = client.get('/get', {'a': '1'})
        assert_true(r.status_code == 200, 'GET 状态码 %s' % r.status_code)
        import ujson
        data = ujson.loads(r.body)
        assert_true(data['params'].get('a') == '1', 'GET 参数透传异常: %r' % data)
        # POST form
        r2 = client.post_with_form('/form', {'x': 'y'})
        assert_true(r2.status_code == 200 and ujson.loads(r2.body)['form'].get('x') == 'y', 'POST form 异常')
        # headers 管理 + 服务端可见性
        client.setHeaders({'X-Debug': 'debug-ok'})
        assert_true(client.getHeaders().get('X-Debug') == 'debug-ok', 'setHeaders/getHeaders 不一致')
        r3 = client.get('/get')
        assert_true(ujson.loads(r3.body)['x_debug'] == 'debug-ok', '自定义头未到达服务端')
        client.updateHeaders({'X-Debug': 'v2'})
        assert_true(client.getHeaders()['X-Debug'] == 'v2', 'updateHeaders 未覆盖')
        client.removeHeader('X-Debug')
        assert_true('X-Debug' not in client.getHeaders(), 'removeHeader 未删除')
        # cookies：服务端 Set-Cookie → 客户端回收
        r4 = client.get('/cookie')
        cookies = ujson.loads(r4.cookies or '{}') if r4.cookies and r4.cookies.strip().startswith('{') else r4.cookies
        assert_true('session' in str(cookies) or client.getCookies().get('session') == 'debug123',
                    'Set-Cookie 未被回收: %r / %r' % (cookies, client.getCookies()))
        # 文件下载
        with tmp_workdir() as d:
            target = os.path.join(d, 'dl.bin')
            r5 = client.getFile('/file', target)
            assert_true(r5.status_code == 200 and open(target, 'rb').read() == b'debug-file-content', 'getFile 下载异常')
        # changeUrl + setTimeout + closeSession
        client.setTimeout(5)
        client.changeUrl(base)
        assert_true(client.get('/echo?q=1').status_code == 200, 'changeUrl 后请求失败')
        client.closeSession()
    finally:
        server.shutdown()
        server.server_close()
    return 'GET/POST(表单)/下载/请求头/回收Cookie/换址 全部通过'


@check('platform.locator', '平台接口 · 元素定位器(平台 /locator)', '元素定位器子应用健康检查 /locator/api/status')
def _():
    try:
        _, data = http_get_json('http://127.0.0.1:8080/locator/api/status', timeout=3)
    except Exception:
        raise Skip('执行平台未启动（run.sh platform 可启动；定位器已并入平台 /locator 子路径），接口探测跳过')
    assert_true('version' in (data or {}), '状态接口返回缺 version 字段: %r' % data)
    return '定位器子应用在线 version=%s' % (data or {}).get('version')


@check('platform.web', '平台接口 · 执行平台(:8080)', 'Web 执行平台健康检查 /api/status')
def _():
    up, data = platform_status(8080)
    if not up:
        raise Skip('执行平台未启动（run.sh platform 可启动），接口探测跳过')
    assert_true((data or {}).get('service') == 'app-ui-platform', '状态接口返回异常: %r' % data)
    return '服务在线，设备在线数=%s' % (data or {}).get('device_online')


@check('env.appium', '平台接口 · Appium(:4726)', 'Appium 服务状态探测（APP 用例执行前置）')
def _():
    from dbg_kit import appium_ok, adb_device_serials
    up = appium_ok()
    serials = adb_device_serials()
    if not up and not serials:
        raise Skip('Appium 未启动且无在线设备（run.sh start-appium + 连接手机后可用）')
    assert_true(up, 'Appium 未启动，但有 %d 台设备在线' % len(serials))
    if not serials:
        raise Skip('Appium 在线但无在线设备（连上手机后可用）；Appium 服务本身正常')
    return 'Appium 在线，设备: %s' % ', '.join(serials)
