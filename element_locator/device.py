# -*- coding: utf-8 -*-
"""
GUI 元素定位器 · 设备层
通过 adb 获取：设备信息 / 实时截图 / 页面元素树
不依赖 Appium session，连接和刷新都轻量可靠。
"""
import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ADB = os.path.expanduser('~/Library/Android/sdk/platform-tools/adb')

last_error = ''   # 最近一次截图/dump 的失败原因（刷新接口透出给前端，不再笼统报错）

# 有意义的节点属性（用于展示和定位）
ATTR_KEYS = ['index', 'text', 'resource-id', 'class', 'package', 'content-desc',
             'checkable', 'checked', 'clickable', 'focusable', 'focused', 'scrollable',
             'long-clickable', 'password', 'selected', 'bounds', 'enabled']

# 属性值 "true/false" 转布尔，便于前端判断
_BOOL_KEYS = {'checkable', 'checked', 'clickable', 'focusable', 'focused',
              'scrollable', 'long-clickable', 'password', 'selected', 'enabled'}


def _run(cmd, timeout=30):
    """执行 adb 命令，返回 stdout 文本（容错）"""
    try:
        p = subprocess.run([ADB] + cmd, capture_output=True, timeout=timeout)
        return p.stdout.decode('utf-8', errors='ignore')
    except Exception:
        return ''


def _online_serials():
    """全部 device 状态的设备序列号（按 adb devices 输出顺序）"""
    out = _run(['devices'])
    serials = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == 'device':
            serials.append(parts[0])
    return serials


def get_device(preferred=None):
    """返回在线设备序列号：preferred 仍在线则优先返回它，
    否则回退第一台（单设备场景与旧行为一致）；无设备返回 None"""
    serials = _online_serials()
    if preferred and preferred in serials:
        return preferred
    return serials[0] if serials else None


def list_devices():
    """全部在线设备（含型号/系统版本），供前端设备切换下拉"""
    return [device_info(s) for s in _online_serials()]


def device_info(serial):
    """设备型号/系统版本"""
    model = _run(['-s', serial, 'shell', 'getprop', 'ro.product.model']).strip()
    version = _run(['-s', serial, 'shell', 'getprop', 'ro.build.version.release']).strip()
    return {'serial': serial, 'model': model or 'unknown', 'platformVersion': version or 'unknown'}


def screenshot_png(serial):
    """返回设备截图 PNG bytes；失败自动重试 3 次（间隔 0.5s，USB 闪断自愈），原因记入 last_error"""
    global last_error
    for _ in range(3):
        try:
            p = subprocess.run([ADB, '-s', serial, 'exec-out', 'screencap', '-p'],
                               capture_output=True, timeout=30)
            if p.returncode == 0 and p.stdout[:4] == b'\x89PNG':
                return p.stdout
            last_error = '截图失败（adb 退出码 %s）' % p.returncode
        except Exception as e:
            last_error = '截图异常: %s' % str(e)[:60]
        time.sleep(0.5)
    last_error += '（已重试 3 次）'
    return None


def restart_adb(wait_seconds=10):
    """adb 级恢复：重启 adb server 并等设备重新上线（USB 闪断/offline 等连接类故障，
    设备层重试救不回来时由刷新接口升级调用）。返回是否重新看到在线设备。"""
    subprocess.run([ADB, 'kill-server'], capture_output=True, timeout=10)
    subprocess.run([ADB, 'start-server'], capture_output=True, timeout=10)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _online_serials():
            return True
        time.sleep(1)
    return False


def tap(serial, x, y):
    """在设备真实点击坐标 (x, y)，用于验证定位是否准确（双击执行器）"""
    try:
        p = subprocess.run([ADB, '-s', serial, 'shell', 'input', 'tap', str(int(x)), str(int(y))],
                           capture_output=True, timeout=15)
        return p.returncode == 0
    except Exception:
        return False


def _release_ui_idle(serial):
    """uiautomator dump 失败（could not get idle state）常见原因：输入框自动聚焦 +
    软键盘/光标持续动画，界面永远"不空闲"。这里做副作用最小的解锁：
    1) 键盘可见时才按返回键收起（BACK 在键盘显示时只收键盘，不退出页面）；
    2) 点击屏幕上"几乎不可能有业务控件"的位置把输入焦点移走。
    ⚠️ 实测踩坑：不要 tap 页面中部（如 68% 高度）——登录页该处是"服务协议"链接，
    tap 会打开协议页导致拿到的树不是当前表单页。tap 左右边缘中心是安全的：
    tap 不是 swipe，不会触发侧滑返回；边缘 1px 内无业务控件，仅让 EditText 失焦。
    解锁后界面趋于稳定，重试 dump 即可拿到当前页元素树。
    """
    out = _run(['-s', serial, 'shell', 'dumpsys', 'input_method'], timeout=10)
    if 'mInputShown=true' in out:
        _run(['-s', serial, 'shell', 'input', 'keyevent', '4'], timeout=10)
        time.sleep(1.5)
    m = re.search(r'(\d+)x(\d+)', _run(['-s', serial, 'shell', 'wm', 'size'], timeout=10) or '')
    w, h = (int(m.group(1)), int(m.group(2))) if m else (720, 1600)
    for x, y in [(2, h // 2), (w - 2, h // 2)]:
        _run(['-s', serial, 'shell', 'input', 'tap', str(x), str(y)], timeout=10)
        time.sleep(1.5)


def _u2_server_running(serial):
    """设备上 uiautomator2 server 是否在运行（pidof，毫秒级）。
    在跑即独占设备的 UiAutomation 通道，系统 uiautomator dump 会一直卡到超时——
    真机执行用例后 server 常驻设备，正是「刷新十几秒才失败」的来源；
    先按进程探测再选通道，被占用时直接走 u2 秒级出树。"""
    out = _run(['-s', serial, 'shell', 'pidof', 'io.appium.uiautomator2.server'], timeout=5)
    return bool(out and out.strip())


def _system_dump(serial):
    """系统 uiautomator dump 单次：删旧文件 → dump → cat（只认本次生成的树，绝不吃旧树）"""
    _run(['-s', serial, 'shell', 'rm', '-f', '/sdcard/ui_dump.xml'], timeout=8)
    _run(['-s', serial, 'shell', 'uiautomator', 'dump', '/sdcard/ui_dump.xml'], timeout=8)
    xml = _run(['-s', serial, 'shell', 'cat', '/sdcard/ui_dump.xml'], timeout=8)
    return xml if xml and '<hierarchy' in xml else None


def _kill_u2_server(serial):
    """强杀设备上的 uiautomator2 server。僵尸态：进程在但 UiAutomation 已断连
    （建会话报 UiAutomation not connected），却占着通道让系统 dump 也拿不到
    idle——跑完真机用例后刷新失败多源于此；杀掉后系统 dump 立即恢复。"""
    for pkg in ('io.appium.uiautomator2.server.test', 'io.appium.uiautomator2.server'):
        _run(['-s', serial, 'shell', 'am', 'force-stop', pkg], timeout=8)
    _U2_STATES[serial] = {'ok': False, 'session': None}
    time.sleep(1)


def dump_xml(serial):
    """uiautomator dump 返回页面 XML 文本；连续失败返回 None

    注意：uiautomator dump 偶发失败（华为 ROM 实测出现 SIGKILL/137，或输入框聚焦+
    软键盘导致 could not get idle state），失败时不会更新 /sdcard/ui_dump.xml ——
    若不校验直接 cat，会拿到上一次（甚至更早）的旧元素树，造成"页面切换了、树还是
    旧的"假象。因此：先删旧文件 → dump → cat 到有效 XML 才算本次成功；失败先解锁
    界面再重试，最多 3 次。

    持续动画页面（如登录页顶部轮播/跑马灯）会让 uiautomator 永远等不到 idle ——
    这是华为 ROM 系统级限制，解锁动作无效。此时降级走 Appium uiautomator2 server，
    用 waitForIdleTimeout=0 跳过 idle 等待直接抓 accessibility 树。

    通道选择：u2 server 在设备上运行时（刚跑完真机用例会常驻），系统 dump 必然
    卡死到超时——此时直接走 u2，秒级出树；系统 dump 的单次超时也从 30s 收紧到 8s
    （正常 2~3s 就该完成），避免被占用场景下 3 次重试拖到几十秒才降级。"""
    u2_running = _u2_state(serial)['ok'] or _u2_server_running(serial)
    if u2_running:
        u2 = _dump_via_u2(serial)
        if u2:
            return u2
    for _ in range(3):
        xml = _system_dump(serial)
        if xml:
            return xml
        _release_ui_idle(serial)
    xml = _dump_via_u2(serial)
    if xml:
        return xml
    # 双通道全败 + u2 进程仍在 = 僵尸 server（占通道但自身失联）→ 强杀后重试
    if _u2_server_running(serial):
        _kill_u2_server(serial)
        for _ in range(3):
            xml = _system_dump(serial)
            if xml:
                return xml
            _release_ui_idle(serial)
        xml = _dump_via_u2(serial)   # 通道已清空：冷启动全新 u2 server 兜底
        if xml:
            return xml
    global last_error
    last_error = ('界面 dump 失败：系统 uiautomator 与 u2 通道均未成功'
                  '（已各重试 3 次并清理设备上的 u2 server）')
    return None


# ---------------------------------------------------------------
# uiautomator2 降级通道（多设备：状态与主机端口均按 serial 隔离）
# 系统 uiautomator dump 要求窗口 idle；持续动画页面（轮播/跑马灯）永远等不到 idle，
# 华为 ROM 上必失败。设备上预装的 Appium uiautomator2 server 可用 waitForIdleTimeout=0
# 跳过 idle 等待直接抓 accessibility 树 —— 两种通道互相补充。
# 注意：u2 server 进程会长时间占用设备的 UiAutomation 通道，启动后系统 uiautomator
# dump 不再可用（返回 FATAL），此后统一走 u2。这是有意为之的取舍。
# 多设备注意：adb forward 的主机端口必须每台不同（都用 6790 的话，
# 第二台 forward 会悄悄把 6790 改指向新设备，旧 session 全部串台）。
# ---------------------------------------------------------------
_U2_STATES = {}          # serial -> {'ok':bool, 'session':str|None}
_U2_PORT_BASE = 6790     # 每台设备的主机端口 = 6790 + 在线序号


def _u2_host_port(serial):
    """该设备专用的主机端口：按其在在线设备列表中的序号分配，保证多设备互不串台"""
    serials = _online_serials()
    try:
        idx = serials.index(serial)
    except ValueError:
        idx = 0
    return _U2_PORT_BASE + idx


def _u2_state(serial):
    """取该设备的 u2 状态（惰性初始化）"""
    return _U2_STATES.setdefault(serial, {'ok': False, 'session': None})


# u2 server 就在本机 127.0.0.1，绝不能走系统代理：环境配了 http_proxy 时，
# urlopen 默认把 127.0.0.1:6790 的请求发给代理，代理转发失败还会返回它自己的
# 错误文本（如 "upstream connect failed"）——非空 body 会被误判为"server 已就绪"。
# 直连 opener（ProxyHandler({})）彻底绕开代理；实测代理环境下必须如此。
_U2_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _u2_http(serial, method, path, data=None, timeout=20):
    """发请求到指定设备的 uiautomator2 server（经该设备专属主机端口），返回响应文本；失败返回 ''
    注意：u2 server 对未实现的路由返回 404 + JSON body（如 /status），
    HTTPError 也要读出 body —— 有 body 即证明端口已通，不能当失败。
    """
    try:
        body = json.dumps(data).encode('utf-8') if data is not None else None
        req = urllib.request.Request('http://127.0.0.1:%d%s' % (_u2_host_port(serial), path),
                                     data=body, method=method)
        req.add_header('Content-Type', 'application/json')
        try:
            with _U2_OPENER.open(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except urllib.error.HTTPError as e:
            # 404 等错误也带 body（JSON），说明服务在跑
            return e.read().decode('utf-8', errors='ignore')
    except Exception:
        return ''


def _u2_start_server(serial):
    """确保设备上 uiautomator2 server 运行并建立 forward（主机端口用该设备专属端口，
    设备端端口恒为 6790）。先查进程：server 已在跑则只补 forward——
    重复 am instrument 会与现存实例冲突，导致该通道明明可用却启动"失败"。"""
    host_port = _u2_host_port(serial)
    running = bool(_run(['-s', serial, 'shell', 'pidof', 'io.appium.uiautomator2.server'],
                        timeout=5).strip())
    if not running:
        _run(['-s', serial, 'shell',
              'nohup am instrument -w -e debug false -e principalServerPort 6790 '
              'io.appium.uiautomator2.server.test/androidx.test.runner.AndroidJUnitRunner '
              '>/dev/null 2>&1 &'], timeout=10)
    _run(['-s', serial, 'forward', 'tcp:%d' % host_port, 'tcp:6790'], timeout=10)
    for _ in range(15):
        if _u2_http(serial, 'GET', '/status'):
            return True
        time.sleep(1)
    return False


def _u2_ensure(serial):
    """确保该设备的 u2 server + session 就绪，返回 True；无法就绪返回 False"""
    st = _u2_state(serial)
    if st['ok'] and st['session']:
        return True
    # 先确认 server 端口通（可能之前已启动）；不通则冷启动
    if not _u2_http(serial, 'GET', '/status'):
        if not _u2_start_server(serial):
            return False
    # 建 session：waitForIdleTimeout=0 跳过 idle 等待（抓树不要求窗口空闲）；udid 明确指向本设备
    resp = _u2_http(serial, 'POST', '/wd/hub/session', {
        'capabilities': {'alwaysMatch': {
            'appium:automationName': 'UiAutomator2',
            'appium:deviceName': 'android',
            'appium:udid': serial,
            'appium:waitForIdleTimeout': 0,
        }},
    }, timeout=30)
    try:
        data = json.loads(resp)
        # W3C 格式（u2 server 10.x 实测）：顶层 sessionId 是 "None"，真实 id 在 value.sessionId；
        # 取错字段会把字符串 "None" 当 session 用，所有取树请求都报 invalid session id
        sid = data.get('sessionId')
        if not sid or sid == 'None':
            sid = (data.get('value') or {}).get('sessionId')
        st['session'] = sid
        st['ok'] = bool(sid)
        return bool(sid)
    except Exception:
        return False


def _u2_session_alive(serial):
    """该设备 u2 session 是否还有效（探测：请求不存在的 session 返回 404，存在的返回 200）"""
    sid = _u2_state(serial).get('session')
    if not sid:
        return False
    try:
        req = urllib.request.Request(
            'http://127.0.0.1:%d/wd/hub/session/%s' % (_u2_host_port(serial), sid))
        try:
            with _U2_OPENER.open(req, timeout=10):
                return True
        except urllib.error.HTTPError as e:
            return e.code == 200
    except Exception:
        return False


def _dump_via_u2(serial):
    """uiautomator2 通道抓当前页元素树 XML；失败返回 None
    /source 返回 JSON：{"sessionId":..., "value":"<xml>"} —— 需取 value 字段"""
    if not _u2_ensure(serial):
        return None
    st = _u2_state(serial)
    if not _u2_session_alive(serial):
        st['session'] = None
        st['ok'] = False
        if not _u2_ensure(serial):
            return None
    sid = st['session']
    resp = _u2_http(serial, 'GET', '/wd/hub/session/%s/source' % sid, timeout=30)
    try:
        xml = json.loads(resp).get('value') or ''
    except Exception:
        return None
    if isinstance(xml, str) and '<hierarchy' in xml:
        return xml
    return None


def parse_bounds(bounds_str):
    """解析 '[x1,y1][x2,y2]' -> (x1, y1, x2, y2)"""
    m = re.findall(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str or '')
    if m:
        x1, y1, x2, y2 = map(int, m[0])
        return x1, y1, x2, y2
    return None


def _node_dict(elem):
    """XML 节点 -> 展示用 dict（保留完整属性 + bounds 数字）"""
    attrs = {}
    for k, v in elem.attrib.items():
        if k in _BOOL_KEYS:
            attrs[k] = (v == 'true')
        else:
            attrs[k] = v
    b = parse_bounds(attrs.get('bounds', ''))
    attrs['_bounds'] = b  # (x1,y1,x2,y2)
    attrs['_center'] = None
    if b:
        attrs['_center'] = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
    return attrs


def xml_to_tree(xml_text):
    """XML -> {width,height,nodes:[树]}，返回所有节点扁平列表(用于命中)"""
    root = ET.fromstring(xml_text)
    width = int(root.attrib.get('width', 0) or 0)
    height = int(root.attrib.get('height', 0) or 0)
    all_nodes = []

    def walk(elem, parent=None):
        node = _node_dict(elem)
        node['_parent'] = parent
        node['children'] = []
        all_nodes.append(node)
        for child in list(elem):
            cnode = walk(child, node)
            node['children'].append(cnode)
        return node

    tree = walk(root)
    # 部分 ROM(如华为)根节点不带 width/height，用最大元素 bounds 推导屏幕尺寸
    if not width or not height:
        for n in all_nodes:
            b = n.get('_bounds')
            if b:
                width = max(width, b[2])
                height = max(height, b[3])
    # 去掉树里 _parent 的引用（会形成环，无法 json 序列化），保留扁平列表的 parent 引用用于命中
    def clean(n):
        n.pop('_parent', None)
        n['children'] = [clean(c) for c in n['children']]
        return n
    clean(tree)
    for n in all_nodes:
        n.pop('_parent', None)
    return {'width': width, 'height': height, 'tree': tree, 'all': all_nodes}


def hit_element(all_nodes, x, y):
    """命中坐标 (x,y) 的元素：包含该点且面积最小的节点（越靠内层越小）"""
    best = None
    best_area = None
    for n in all_nodes:
        b = n.get('_bounds')
        if not b:
            continue
        x1, y1, x2, y2 = b
        if x1 <= x <= x2 and y1 <= y <= y2:
            area = (x2 - x1) * (y2 - y1)
            # 跳过 0 面积（无意义）
            if area <= 0:
                continue
            if best is None or area < best_area:
                best = n
                best_area = area
    return best


def escape_xpath(v):
    """xpath 字符串转义：双引号包起来，值里含双引号用 concat 处理"""
    v = v or ''
    if '"' not in v:
        return '"%s"' % v
    return 'concat(%s)' % ','.join('"%s"' % part for part in v.split('"'))


def gen_locators(node, all_nodes):
    """
    按官方文档提纯的定位写法，返回候选列表：
    [{kind, locator_type, value, desc}]
    locator_type 对应框架 Locator_Type 的常量名（ID/XPATH/ACCESSIBILITY_ID/ANDROID_UIAUTOMATOR）
    对页面里重复的 resource-id/text，额外给出带下标的写法（UiSelector.instance / XPath []）
    """
    cands = []
    rid = (node.get('resource-id') or '').strip()
    text = (node.get('text') or '').strip()
    desc = (node.get('content-desc') or '').strip()

    def unique(key, val):
        cnt = 0
        for n in all_nodes:
            if n.get(key) == val:
                cnt += 1
                if cnt > 1:
                    return False
        return cnt == 1

    def same_rid_count():
        return sum(1 for n in all_nodes if (n.get('resource-id') or '').strip() == rid)

    def rid_index():
        # 当前节点在所有同 resource-id 元素中的序号（按文档顺序，1 开始）
        i = 0
        for n in all_nodes:
            if (n.get('resource-id') or '').strip() == rid:
                i += 1
                if n is node:
                    return i
        return 1

    if rid and unique('resource-id', rid):
        cands.append({'kind': 'ID', 'locator_type': 'ID', 'value': rid,
                      'desc': 'resource-id 唯一，最稳'})

    if text and unique('text', text):
        cands.append({'kind': 'XPATH', 'locator_type': 'XPATH',
                      'value': '//*[@text=%s]' % escape_xpath(text),
                      'desc': 'text 唯一'})

    if desc and unique('content-desc', desc):
        cands.append({'kind': 'ACCESSIBILITY_ID', 'locator_type': 'ACCESSIBILITY_ID', 'value': desc,
                      'desc': 'content-desc 唯一（无障碍标签）'})

    # XPath：带 text 或 resource-id 的组合（不要求唯一，用户可自行确认）
    if text:
        cands.append({'kind': 'XPATH', 'locator_type': 'XPATH',
                      'value': '//*[@text=%s]' % escape_xpath(text),
                      'desc': 'text 定位（页面可能存在多个同名）'})
    if rid:
        dup = same_rid_count()
        cands.append({'kind': 'XPATH', 'locator_type': 'XPATH',
                      'value': '//*[@resource-id=%s]' % escape_xpath(rid),
                      'desc': 'resource-id 定位（页面%s共 %d 个同名）' % ('仅有 1 个' if dup == 1 else '共有', dup)})

    # 重复元素：给出带下标/instance 的写法（解决"页面多个一模一样"的定位偏差）
    if rid and same_rid_count() > 1:
        k = rid_index()
        cands.append({'kind': 'XPATH-下标', 'locator_type': 'XPATH',
                      'value': '(//*[@resource-id=%s])[%d]' % (escape_xpath(rid), k),
                      'desc': '同 id 共 %d 个，取第 %d 个（XPath 下标从 1 开始）' % (same_rid_count(), k)})
        cands.append({'kind': 'UIAT-instance', 'locator_type': 'ANDROID_UIAUTOMATOR',
                      'value': 'new UiSelector().resourceId("%s").instance(%d)' % (rid, k - 1),
                      'desc': 'instance 从 0 开始，与 getElements()[i] 下标一致'})

    # UIAutomator（UiAutomator2 专用）
    if rid:
        cands.append({'kind': 'UIAUTOMATOR', 'locator_type': 'ANDROID_UIAUTOMATOR',
                      'value': 'new UiSelector().resourceId("%s")' % rid,
                      'desc': 'UiAutomator2 UiSelector 写法'})
    elif text:
        cands.append({'kind': 'UIAUTOMATOR', 'locator_type': 'ANDROID_UIAUTOMATOR',
                      'value': 'new UiSelector().text("%s")' % text,
                      'desc': 'UiAutomator2 UiSelector 写法'})

    # 兜底：class + text / 纯 xpath
    cls = (node.get('class') or '').strip()
    if cls and text:
        short = cls.split('.')[-1]
        cands.append({'kind': 'XPATH', 'locator_type': 'XPATH',
                      'value': '//%s[@text=%s]' % (short, escape_xpath(text)),
                      'desc': 'class + text 组合（更精确）'})
    if not cands:
        cands.append({'kind': 'XPATH', 'locator_type': 'XPATH',
                      'value': '//*[@class=%s]' % escape_xpath(cls),
                      'desc': '仅 class 兜底（不推荐，页面常多个同类）'})
    return cands


def serialize_node(node):
    """节点转前端展示 dict（去掉 _ 内部字段）"""
    d = {k: v for k, v in node.items() if not k.startswith('_')}
    d['children'] = [serialize_node(c) for c in node.get('children', [])]
    return d


if __name__ == '__main__':
    # 简单自测
    serial = get_device()
    print('device:', serial)
    if serial:
        info = device_info(serial)
        print(info)
        png = screenshot_png(serial)
        print('screenshot bytes:', len(png) if png else None)
        xml = dump_xml(serial)
        if xml:
            data = xml_to_tree(xml)
            print('screen:', data['width'], 'x', data['height'], ' nodes:', len(data['all']))
            hit = hit_element(data['all'], 360, 1000)
            if hit:
                print('hit text:', hit.get('text'), 'rid:', hit.get('resource-id'))
                print('locators:', gen_locators(hit, data['all']))


# 前端定位方式（Locator_Type 键）→ uiautomator2 server 的 W3C 定位策略
_LOCATE_STRATEGIES = {
    'ID': 'id',
    'XPATH': 'xpath',
    'ACCESSIBILITY_ID': 'accessibility id',
    'ANDROID_UIAUTOMATOR': '-android uiautomator',
    'CLASS_NAME': 'class name',
    'NAME': 'name',
}


def locate_check(serial, locator_type, locator_value):
    """「定位器体检」：按定位方式在当前页面实查元素。
    返回 {ok, found, count, bounds, msg}；bounds 为首元素 [x1,y1,x2,y2]。
    复用 u2 通道（与抓树同一条 session）；session 失效自动重建重试一次。"""
    strategy = _LOCATE_STRATEGIES.get(str(locator_type or '').upper())
    if not strategy:
        return {'ok': False, 'msg': '不支持的定位方式: %s' % locator_type}
    if not locator_value:
        return {'ok': False, 'msg': '定位值为空'}
    for _attempt in (1, 2):
        if not _u2_ensure(serial):
            return {'ok': False, 'msg': 'u2 通道未就绪（设备离线或 server 启动失败）'}
        sid = _u2_state(serial).get('session')
        resp = _u2_http(serial, 'POST', '/wd/hub/session/%s/elements' % sid,
                        # 设备端 uiautomator2 server 的 FindElementModel 要求 strategy/selector 字段
                        {'strategy': strategy, 'selector': locator_value}, timeout=15)
        if not resp:
            # session 可能已失效：置空重建后重试一次
            st = _u2_state(serial)
            st['session'] = None
            st['ok'] = False
            continue
        try:
            val = json.loads(resp).get('value')
        except Exception:
            return {'ok': False, 'msg': '设备端响应异常'}
        if isinstance(val, dict) and val.get('error'):
            err = str(val.get('error') or '')
            if 'no such element' in err.lower():
                return {'ok': True, 'found': False, 'count': 0, 'bounds': None, 'msg': '当前页面未命中'}
            # 其他错误（invalid selector / session 失效等）如实上报，不能伪装成"未命中"
            return {'ok': False, 'msg': '设备端查找出错: %s' % (err or val)[:120]}
        if not isinstance(val, list):
            return {'ok': False, 'msg': '设备端响应格式异常'}
        count = len(val)
        if not count:
            return {'ok': True, 'found': False, 'count': 0, 'bounds': None, 'msg': '当前页面未命中'}
        bounds = None
        first = val[0]
        eid = first.get(next((k for k in first if 'element' in k.lower()), ''), '')
        if eid:
            rect = _u2_http(serial, 'GET', '/wd/hub/session/%s/element/%s/rect' % (sid, eid),
                            None, timeout=10)
            try:
                r = json.loads(rect)['value']
                bounds = [int(r['x']), int(r['y']),
                          int(r['x']) + int(r['width']), int(r['y']) + int(r['height'])]
            except Exception:
                bounds = None
        return {'ok': True, 'found': True, 'count': count, 'bounds': bounds,
                'msg': '命中 %d 处' % count}
    return {'ok': False, 'msg': 'u2 通道异常（session 重建后仍失败）'}
