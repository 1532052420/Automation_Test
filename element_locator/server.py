# -*- coding: utf-8 -*-
"""
App 元素定位器 · Flask 应用（element_locator）
已并入 Web 执行平台，由 web_platform/app.py 以 DispatcherMiddleware 挂在 /locator 子路径，
随平台一起启动/停止；不再有独立的 8001 服务。
访问：cd ~/Desktop/AutomationTest && ./run.sh platform  →  http://127.0.0.1:8080/locator/
技术方案与配置方法见同目录 技术实现方案.md
"""
import ast
import base64
import os
import re
import sys
import time

from flask import Flask, jsonify, request, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collect
import device
import element_library
import case_generator
import popup_rules
from tutorials import TUTORIALS, search_tutorials

app = Flask(__name__, static_folder='static', static_url_path='/static')

# 三件套/元素库文件写入互斥锁：append_code_to_method 等是「读→改→写」非原子，
# 并发保存（同名确认框并发放行/快速连点）会互相覆盖丢步骤——所有落盘接口串行过锁
import threading
_save_lock = threading.Lock()

# 元素定位器版本号：与平台统一，唯一数据源为 web_platform/changelog.py（APP_VERSION）。
# 左上角会显示，用来确认本地是否已更新。改版本号请改 changelog.py，勿在这里硬编码。
try:
    from web_platform.changelog import APP_VERSION as _PLATFORM_VERSION
    APP_VERSION = 'v' + _PLATFORM_VERSION
except ImportError:  # 独立运行定位器且项目根不在 sys.path 时的兜底
    APP_VERSION = 'v3.3'
    print('警告: 未能读取 web_platform.changelog 的版本号，使用内置兜底值 %s' % APP_VERSION)

# 开发工具要能"改完即刷"，静态文件禁用浏览器强缓存（Flask 默认 max-age=12h）
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


@app.after_request
def _no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp

PORT = int(os.environ.get('LOCATOR_PORT', '8001'))


def _serialize(node, with_children=True):
    """节点 dict -> JSON 可序列化结构（_bounds/_center 转成普通字段）。
    with_children=False 用于 all 扁平列表：只保留节点自身，避免把整棵子树重复序列化（O(n²) 冗余）。"""
    d = {}
    for k, v in node.items():
        if k == '_bounds':
            d['bounds_num'] = list(v) if v else None
        elif k == '_center':
            d['center'] = list(v) if v else None
        elif k == 'children':
            if with_children:
                d['children'] = [_serialize(c) for c in v]
        elif k.startswith('_'):
            continue
        else:
            d[k] = v
    d.setdefault('children', [])
    return d


def _request_serial():
    """前端指定的设备序列号（JSON body 或 query 的 serial），缺省回退第一台在线设备"""
    data = request.get_json(silent=True) or {}
    serial = (data.get('serial') or request.args.get('serial') or '').strip()
    return serial or None


def _refresh_once():
    """截图 + 元素树 完整载荷（按前端指定的设备；设备掉线自动回退第一台）。
    返回 (payload, reason)：失败时 reason 带真实原因（哪一步、做过什么）。
    fallback=True：请求的设备已掉线、响应来自回退设备——前端据此校正下拉，
    并与「过期响应」（用户已切到别的设备）区分开，过期响应直接丢弃防串台"""
    asked = _request_serial()
    serial = device.get_device(asked)
    if not serial:
        return None, '未检测到在线设备（USB 断开、未授权或 adb 掉线）'
    # 截图与取树相互独立：并行执行（原串行两段耗时相加，实测白等约 1s）
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_png = ex.submit(device.screenshot_png, serial)
        xml = ex.submit(device.dump_xml, serial).result()
        png = f_png.result()
    if not xml:
        return None, device.last_error or '界面 dump 失败'
    try:
        data = device.xml_to_tree(xml)
    except Exception as e:
        return None, '元素树解析失败: %s' % str(e)[:80]
    # 为每个节点生成定位候选（ID/XPath/UIAutomator 等）
    for n in data['all']:
        n['locators'] = device.gen_locators(n, data['all'])
    return {
        'serial': serial,
        'fallback': bool(asked and serial != asked),
        'device': device.device_info(serial),
        'screenshot': 'data:image/png;base64,' + base64.b64encode(png).decode() if png else '',
        'width': data['width'],
        'height': data['height'],
        'tree': _serialize(data['tree']),
        'all': [_serialize(n, with_children=False) for n in data['all']],
    }, ''


def _platform_running():
    """平台是否正在执行测试——重启 adb 会打断执行链路，运行中不做 adb 级恢复"""
    try:
        from web_platform import runner
        return bool(runner.manager.running_task())
    except Exception:
        return False


@app.route('/')
def index():
    return send_file(os.path.join(app.static_folder, 'index.html'))


@app.route('/api/devices')
def api_devices():
    """全部在线设备（多设备切换下拉数据源）"""
    return jsonify({'ok': True, 'devices': device.list_devices()})


@app.route('/api/status')
def api_status():
    serial = device.get_device(_request_serial())
    if not serial:
        return jsonify({'ok': False, 'version': APP_VERSION,
                        'msg': '未检测到已授权的 Android 设备，请连接手机并允许 USB 调试'})
    return jsonify({'ok': True, 'version': APP_VERSION, 'serial': serial,
                    'device': device.device_info(serial)})


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """刷新 = 截图 + 元素树。
    fast=true（⚡ 刷新按钮）：只做一次 dump，失败立即报错——最快路径，不做任何自愈；
    fast=false（♻ 重启按钮）：完整自愈链——设备层各自重试 3 次 → 这里升级重启 adb server
    再试一轮（USB 闪断/offline 类故障的最终自愈手段；平台有测试在跑时不重启，防打断执行链路）
    → 仍失败才报错，且带真实原因。"""
    data = request.get_json(silent=True) or {}
    fast = bool(data.get('fast'))
    payload, reason = _refresh_once()
    if payload:
        return jsonify({'ok': True, **payload})
    if fast:
        return jsonify({'ok': False, 'msg': reason + '（快速刷新失败；可点「♻ 重启」走完整自愈后重试）'})
    if not _platform_running():
        if device.restart_adb():
            payload, reason2 = _refresh_once()
            if payload:
                return jsonify({'ok': True, **payload})
            reason = reason2 + '（已自动重启 adb 并重试仍失败）'
        else:
            reason += '（已自动重启 adb，设备未重新上线——请重新插拔 USB 线）'
    return jsonify({'ok': False, 'msg': '刷新失败：%s' % reason})


@app.route('/api/library')
def api_library():
    files = element_library.list_element_files()
    default = element_library.DEFAULT_FILE
    content = ''
    path = os.path.join(element_library.ELEMENTS_DIR, default)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    return jsonify({'ok': True, 'files': files, 'default': default, 'content': content})


@app.route('/api/add_element', methods=['POST'])
def api_add_element():
    with _save_lock:
        return _add_element_locked()

def _add_element_locked():
    data = request.get_json(silent=True) or {}
    # check_dup：默认 True 先做重复检测（库中已有相同定位 → 返回 duplicate 不落盘，前端决定用已有/新建）
    check_dup = data.get('check_dup', True)
    # wait_seconds：显式等待超时秒数；空/非法 = 沿用框架默认 30
    try:
        wait_seconds = int(data.get('wait_seconds'))
        if not 1 <= wait_seconds <= 600:
            wait_seconds = None
    except (TypeError, ValueError):
        wait_seconds = None
    r = element_library.add_element(
        data.get('filename') or element_library.DEFAULT_FILE,
        data.get('name', '').strip(),
        data.get('locator_type', '').strip(),
        data.get('value', '').strip(),
        data.get('wait_type', 'VISIBILITY_OF').strip() or 'VISIBILITY_OF',
        wait_seconds=wait_seconds,
        comment=(data.get('comment') or '').strip(),
        check_dup=bool(check_dup),
        cn_name=(data.get('cn_name') or '').strip() or None,
    )
    # 命中重复元素时附带「已被哪些用例使用」，前端复用面板展示（默认直接复用，防元素库膨胀）
    if r.get('duplicate') and not r.get('ok'):
        r['duplicate']['used_in'] = case_generator.element_usage_in_cases(r['duplicate']['name'])
    return jsonify({'ok': r['ok'], 'msg': r.get('msg', ''), 'action': r.get('action', ''),
                    'duplicate': r.get('duplicate'),
                    'filename': data.get('filename') or element_library.DEFAULT_FILE,
                    'content': r.get('content', '')})


@app.route('/api/collect_all', methods=['POST'])
def api_collect_all():
    """采集全部元素（方案第一阶段）：当前页面 hierarchy → 过滤 → 去重 → 命名 → 定位候选。
    原始 hierarchy 存档到 element_collect/<时间戳>/hierarchy.xml（原则：过滤的是入库数据，不是原始数据）。"""
    asked = _request_serial()
    serial = device.get_device(asked)
    if not serial:
        return jsonify({'ok': False, 'msg': '未检测到在线设备（USB 断开、未授权或 adb 掉线）'})
    xml = device.dump_xml(serial)
    if not xml:
        return jsonify({'ok': False, 'msg': '界面 dump 失败：' + (device.last_error or '未知原因')})
    try:
        result = collect.collect_from_xml(xml)
    except Exception as e:
        return jsonify({'ok': False, 'msg': '元素树解析失败: %s' % str(e)[:80]})
    try:
        root_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'element_collect')
        stamp = __import__('time').strftime('%Y%m%d_%H%M%S')
        page_dir = os.path.join(root_dir, stamp)
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, 'hierarchy.xml'), 'w', encoding='utf-8') as f:
            f.write(xml)
        result['archive'] = 'element_collect/%s/hierarchy.xml' % stamp
    except Exception as e:
        result['archive'] = ''            # 存档失败不阻塞采集，只透出
        result['archive_err'] = str(e)[:80]
    result['ok'] = True
    result['serial'] = serial
    return jsonify(result)


@app.route('/api/collect_save', methods=['POST'])
def api_collect_save():
    """采集结果批量入库：复用现有元素库文件（不建新体系），一次读、分类、一次写回。"""
    data = request.get_json(silent=True) or {}
    items = data.get('items') or []
    r = element_library.add_elements_batch(data.get('filename') or '', items)
    return jsonify(r)


@app.route('/api/cases')
def api_cases():
    """列出现有用例文件（新建/追加下拉用）；case_info 含每个文件的方法列表（目标用例两级联动）"""
    return jsonify({'ok': True, 'cases': case_generator.list_case_files(),
                    'case_info': case_generator.case_files_info()})


@app.route('/api/save_case_package', methods=['POST'])
def api_save_case_package():
    """「保存测试用例包·保存到框架」：三个文件内容入库。
    定位器现以 /locator 子应用挂在测试平台同一进程内，因此直接调用用例管理的入库实现
    （import_case_package），享受与之完全一致的语法校验、覆盖备份与上传人登记——
    不再需要一个从来不存在的 8090 端点。"""
    data = request.get_json(silent=True) or {}
    package = (data.get('package') or '').strip()
    files = data.get('files') or []
    if not package or not isinstance(files, list) or not files:
        return jsonify({'ok': False, 'msg': '缺少包名或文件内容'})
    if not all(isinstance(f, dict) and f.get('name') and f.get('content') is not None for f in files):
        return jsonify({'ok': False, 'msg': '文件结构不合法'})
    try:
        from web_platform.admin_routes import import_case_package
    except ImportError as e:
        return jsonify({'ok': False, 'msg': '「保存到框架」需与测试平台运行在同一进程（%s）；'
                                            '可改用「⬇ 下载用例包」再在平台「APP自动化 → 用例上传」入库'
                        % str(e)[:80]})
    payload, status = import_case_package(package, files,
                                          (data.get('uploader') or 'locator').strip()[:32])
    return jsonify(payload), status


@app.route('/api/add_code', methods=['POST'])
def api_add_code():
    """「保存并添加到用例」：把一步操作代码追加到目标用例文件的指定方法体末尾。
    gen_page_method=True（功能③）时同步生成/更新该操作的页面方法（三件套联动）。"""
    with _save_lock:
        return _add_code_locked()

def _add_code_locked():
    data = request.get_json(silent=True) or {}
    step = data.get('step') or {}
    if not isinstance(step, dict) or not step.get('type'):
        return jsonify({'ok': False, 'msg': '缺少操作步骤'})
    try:
        insert_after = int(data.get('insert_after_step') or 0)
    except (TypeError, ValueError):
        insert_after = 0
    r = case_generator.append_code_to_method(
        data.get('case_file', '').strip(),
        data.get('method_name', '').strip(),
        step,
        gen_page_method=bool(data.get('gen_page_method')),
        insert_after_step=insert_after,
    )
    return jsonify({'ok': r['ok'], 'msg': r.get('msg', ''),
                    'action': r.get('action', ''),
                    'line': r.get('line', ''),
                    'case_file': data.get('case_file', '').strip(),
                    'method_name': data.get('method_name', '').strip(),
                    'content': r.get('content', ''),
                    'case_before': r.get('case_before', ''),
                    'page_before': r.get('page_before', ''),
                    'page_file': r.get('page_file', ''),
                    'page_method': r.get('page_method', ''),
                    'page_content': r.get('page_content', '')})


@app.route('/api/locate_check', methods=['POST'])
def api_locate_check():
    """「定位器体检」：按定位方式在当前页面实查元素。
    POST {locator_type, locator_value, serial?} → {ok, found, count, bounds, msg}"""
    data = request.get_json(silent=True) or {}
    serial = device.get_device(_request_serial())
    if not serial:
        return jsonify({'ok': False, 'msg': '未检测到设备'})
    r = device.locate_check(serial, data.get('locator_type'), (data.get('locator_value') or '').strip())
    r['serial'] = serial
    return jsonify(r)


# ---------------------------------------------------------------- ④断言栏 · 视觉基线采集
@app.route('/api/element/baseline', methods=['POST'])
def api_element_baseline():
    """视觉断言基线采集：当前屏幕截图按元素 bounds 裁剪 → 落盘 baselines/<元素文件>/<元素名>.png。
    入参 {locator_type, locator_value, element_file, element_name}；
    元素不在当前屏幕时明确报错（不猜不兜底）。返回缩略图 dataURL 供弹窗预览。"""
    import io
    import re as _re
    data = request.get_json(silent=True) or {}
    element_file = (data.get('element_file') or '').strip()
    element_name = (data.get('element_name') or '').strip()
    # 与元素库同名规则：允许中文（is_valid_element_name / add_elements_batch 同款正则）；
    # 无点无斜杠，路径穿越天然被拦
    if not _re.match(r'^[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*\.py$', element_file):
        return jsonify({'ok': False, 'msg': '元素文件名不合法（%s）' % (element_file or '空')})
    if not element_library.is_valid_element_name(element_name):
        return jsonify({'ok': False, 'msg': '元素名不合法（%s）' % (element_name or '空')})
    serial = device.get_device(_request_serial())
    if not serial:
        return jsonify({'ok': False, 'msg': '未检测到在线设备——基线采集需要元素真实在屏'})
    png = device.screenshot_png(serial)
    if not png:
        return jsonify({'ok': False, 'msg': '屏幕截图失败：' + (device.last_error or '未知原因')})
    xml = device.dump_xml(serial)
    if not xml:
        return jsonify({'ok': False, 'msg': '界面 dump 失败：' + (device.last_error or '未知原因')})
    try:
        tree = device.xml_to_tree(xml)
    except Exception as e:
        return jsonify({'ok': False, 'msg': '元素树解析失败: %s' % str(e)[:80]})

    lt = (data.get('locator_type') or '').upper()
    lv = (data.get('locator_value') or '').strip()
    hit = None

    def _walk(n):
        nonlocal hit
        if hit is not None:
            return
        rid = n.get('resource-id') or ''
        if lt == 'ID' and rid == lv:
            hit = n
        elif lt == 'XPATH' and lv:
            m = _re.search(r"@text='([^']*)'", lv)
            if m and (n.get('text') or '') == m.group(1):
                hit = n
            else:
                m2 = _re.search(r"@resource-id='([^']*)'", lv)
                if m2 and rid == m2.group(1):
                    hit = n
        for c in n.get('children') or []:
            _walk(c)

    for n in tree.get('all') or []:
        _walk(n)
        if hit is not None:
            break
    # xml_to_tree 原始节点的坐标在 _bounds（元组）/ bounds（字符串），无 bounds_num
    bounds = None
    if hit:
        b = hit.get('_bounds')
        if isinstance(b, (list, tuple)) and len(b) == 4:
            bounds = [int(x) for x in b]
        else:
            m2 = _re.findall(r'-?\d+', hit.get('bounds') or '')
            if len(m2) == 4:
                bounds = [int(x) for x in m2]
    if not bounds or len(bounds) != 4:
        return jsonify({'ok': False, 'msg': '元素不在当前屏幕上（未在元素树命中该定位）——请先让元素出现在屏幕再采集基线'})

    from PIL import Image
    img = Image.open(io.BytesIO(png))
    x1, y1, x2, y2 = [int(v) for v in bounds]
    x2 = min(x2, img.size[0])
    y2 = min(y2, img.size[1])
    if x2 - x1 < 2 or y2 - y1 < 2:
        return jsonify({'ok': False, 'msg': '元素区域为空（bounds=%s）' % bounds})
    crop = img.crop((x1, y1, x2, y2))
    base_dir = os.path.join(element_library.ELEMENTS_DIR, 'baselines', os.path.splitext(element_file)[0])
    os.makedirs(base_dir, exist_ok=True)
    out = os.path.join(base_dir, '%s.png' % element_name)
    crop.save(out)
    thumb = crop.copy()
    thumb.thumbnail((180, 180))
    buf = io.BytesIO()
    thumb.save(buf, format='PNG')
    import base64 as _b64
    return jsonify({'ok': True, 'path': out.replace(os.sep, '/'), 'size': list(crop.size),
                    'thumbnail': 'data:image/png;base64,' + _b64.b64encode(buf.getvalue()).decode()})


# ---------------------------------------------------------------- 随机弹窗规则库
@app.route('/api/popup_rules')
def api_popup_rules():
    """随机弹窗规则列表（popupElements.py 的关闭按钮 + 锚点/冷却/活动页约束）"""
    return jsonify({'ok': True, 'rules': popup_rules.parse_rules()})


@app.route('/api/add_popup_rule', methods=['POST'])
def api_add_popup_rule():
    """登记/更新一条弹窗规则。POST {name, locator_type, locator_value, anchor_type?,
    anchor_value?, cooldown?, activity?, comment?}；成功后前端可再调 /api/locate_check 实查。"""
    data = request.get_json(silent=True) or {}
    r = popup_rules.add_rule(
        (data.get('name') or '').strip(),
        (data.get('locator_type') or '').strip(),
        (data.get('locator_value') or '').strip(),
        anchor_type=(data.get('anchor_type') or '').strip() or None,
        anchor_value=(data.get('anchor_value') or '').strip() or None,
        cooldown=data.get('cooldown'),
        activity=(data.get('activity') or '').strip() or None,
        comment=(data.get('comment') or '').strip() or None,
    )
    return jsonify(r)


@app.route('/api/delete_popup_rule', methods=['POST'])
def api_delete_popup_rule():
    """删除一条弹窗规则（元素行 + RULE_OPTIONS 约束一起移除）"""
    data = request.get_json(silent=True) or {}
    return jsonify(popup_rules.delete_rule((data.get('name') or '').strip()))


@app.route('/api/pages')
def api_pages():
    """列出页面文件 + 各元素文件已定义的元素名（用例步骤下拉用）"""
    return jsonify({
        'ok': True,
        'pages': case_generator.list_page_files(),
        'elements': {f: element_library.list_element_names(f)
                     for f in element_library.list_element_files()},
    })


@app.route('/api/tap', methods=['POST'])
def api_tap():
    """设备真实点击（验证定位）：POST {x, y, serial?} 设备坐标（serial 缺省回退第一台）"""
    serial = device.get_device(_request_serial())
    if not serial:
        return jsonify({'ok': False, 'msg': '未检测到设备'})
    data = request.get_json(silent=True) or {}
    x, y = data.get('x'), data.get('y')
    if x is None or y is None:
        return jsonify({'ok': False, 'msg': '缺少坐标 x/y'})
    ok = device.tap(serial, x, y)
    return jsonify({'ok': ok, 'serial': serial,
                    'msg': '已点击设备 (%d, %d)' % (x, y) if ok else '点击失败'})


@app.route('/api/tutorials')
def api_tutorials():
    q = request.args.get('q', '').strip()
    return jsonify({'ok': True, 'tutorials': search_tutorials(q)})


# 顶部快速打开支持的三类文件：kind -> (目录, 标题后缀)
_OPEN_KINDS = {
    'case': (lambda: case_generator.CASES_DIR, '用例'),
    'element': (lambda: element_library.ELEMENTS_DIR, '元素库'),
    'page': (lambda: case_generator.PAGES_DIR, '页面操作'),
}
_NAME_PAT = re.compile(r'^[A-Za-z0-9_\-]+\.py$')


def _resolve_open_file(kind, filename):
    """按 kind 校验文件名并拼接目录（白名单防任意路径读写），返回 (full_path, title) 或 (None, 错误)"""
    entry = _OPEN_KINDS.get(kind)
    if not entry:
        return None, '文件类型不合法（case / element / page）'
    if not _NAME_PAT.match(filename or ''):
        return None, '文件名不合法'
    full = os.path.join(entry[0](), filename)
    return full, '%s（%s）' % (filename, entry[1])


@app.route('/api/file_content')
def api_file_content():
    """顶部快速打开·查看文件内容：?case= / ?element= / ?page= + 文件名。
    目录由服务端拼接，文件名做白名单校验，防任意路径读取。"""
    kind = next((k for k in ('case', 'element', 'page') if (request.args.get(k) or '').strip()), None)
    if not kind:
        return jsonify({'ok': False, 'msg': '请用 case / element / page 参数指定一个文件'})
    full, msg = _resolve_open_file(kind, (request.args.get(kind) or '').strip())
    if not full:
        return jsonify({'ok': False, 'msg': msg})
    if not os.path.isfile(full):
        return jsonify({'ok': False, 'msg': '文件不存在: %s' % os.path.basename(full)})
    try:
        with open(full, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return jsonify({'ok': False, 'msg': '读取失败: %s' % e})
    return jsonify({'ok': True, 'kind': kind, 'filename': os.path.basename(full),
                    'title': msg, 'content': content})


@app.route('/api/save_file', methods=['POST'])
def api_save_file():
    """顶部快速打开·保存修改：{kind: case|element|page, filename, content}。
    只允许覆盖已存在的白名单文件（先打开才能改）；保存前做 Python 语法校验（ast），
    语法错误拒绝落盘并返回行号，避免把打错的文件写坏跑不起来。"""
    data = request.get_json(silent=True) or {}
    kind = (data.get('kind') or '').strip()
    filename = (data.get('filename') or '').strip()
    content = data.get('content')
    if content is None or not isinstance(content, str):
        return jsonify({'ok': False, 'msg': '缺少文件内容'})
    full, msg = _resolve_open_file(kind, filename)
    if not full:
        return jsonify({'ok': False, 'msg': msg})
    if not os.path.isfile(full):
        return jsonify({'ok': False, 'msg': '文件不存在: %s（只支持修改已打开的文件）' % filename})
    try:
        ast.parse(content)
    except SyntaxError as e:
        return jsonify({'ok': False,
                        'msg': 'Python 语法错误（第 %s 行: %s），已取消保存' % (e.lineno, e.msg)})
    try:
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        return jsonify({'ok': False, 'msg': '写入失败: %s' % e})
    return jsonify({'ok': True, 'msg': '%s 已保存' % msg, 'content': content})


# ---------------------------------------------------------------- 视觉断言资产（三范围 + 忽略区域 + Layout + 业务类型）
import visual_assets as va


@app.route('/api/visual_asset/preview', methods=['POST'])
def api_visual_preview():
    """预览：按范围实时截图裁剪（不落盘），返回 dataURL 供确认"""
    d = request.get_json(silent=True) or {}
    img, box, err = va.capture(d.get('scope'), d.get('locator_type'),
                               d.get('locator_value'), d.get('region'))
    if err:
        return jsonify({'ok': False, 'msg': err})
    import io
    import base64
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return jsonify({'ok': True, 'box': box, 'size': list(img.size),
                    'thumb': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()})


@app.route('/api/visual_asset/save', methods=['POST'])
def api_visual_save():
    """保存资产：采集基线 + config.yaml（重名覆盖，旧基线留 baseline.prev.png）"""
    d = request.get_json(silent=True) or {}
    ok, r = va.save(d.get('name'), d)
    if not ok:
        return jsonify({'ok': False, 'msg': r})
    return jsonify({'ok': True, 'asset': r})


@app.route('/api/visual_asset/list')
def api_visual_list():
    return jsonify({'ok': True, 'assets': va.list_assets()})


@app.route('/api/visual_asset/<name>', methods=['DELETE'])
def api_visual_delete(name):
    ok, msg = va.delete(name)
    return jsonify({'ok': ok, 'msg': msg})


@app.route('/api/visual_asset/<name>/baseline.png')
def api_visual_baseline(name):
    p = va.baseline_path(name)
    if not p:
        return jsonify({'ok': False, 'msg': '基线图不存在'}), 404
    return send_file(p)


# ---------- 调试：临时用例真跑（v6.14.107） ----------
# 思路：把「选中元素 + 操作类型 + 勾选断言」临时生成一条单步用例，交平台现有 runner 真跑一次，
# 结果 JSON 回读展示、用例文件跑完即删（临时数据，不入元素库/不入用例/不提交 git）。
# 不新建任何会话管理：Appium 会话由用例运行时（Client 单例）自建自清，与用例执行完全同源；
# 与平台执行用例的互斥由 runner.start_run 内置（有任务在跑直接拒绝）。

_DEBUG_CONF = 'config/demoProject/app_ui_android_devices_info_demoProject.conf'
_DEBUG_CONF_OUT = 'config/app_ui_tmp/devices_info_debug.conf'   # 调试专用（gitignore 目录）
_DEBUG_CASE_DIR = 'cases/app_ui/android/demoProject'
_DEBUG_TIMEOUT_MIN = 10
# 调试支持的操作类型 → 执行描述（v1；custom/组合弹窗处理等生成型类型暂不支持）
_DEBUG_OP_NAMES = {
    'click': '点击', 'input': '输入', 'long_press': '长按', 'tap': '坐标点击',
    'screenshot': '截图', 'sleep': '固定等待', 'wait_element': '轮询等待出现',
    'if_click': '出现才点击', 'assert_visible': '断言存在', 'hide_keyboard': '收起键盘',
}
_DEBUG_NEED_ELEMENT = {'click', 'input', 'long_press', 'wait_element', 'if_click',
                       'assert_visible'}
_DEBUG_ASSERT_NAMES = {
    'exists': '断言元素是否可见', 'text': '断言文本是否正确', 'toast': '断言Toast是否出现',
    'text_page': '断言页面文本出现', 'gone': '断言元素是否消失', 'visual': '视觉资产比对',
}


def _debug_case_source(token, lt, lv, wait_type, wait_sec, op_type, param, asserts):
    """生成临时调试用例源码。probe/操作/断言全部内联（不依赖页面与元素文件），
    操作与断言调用与 case_generator.page_method_code 完全同一批运行时方法（保真）。"""
    lines = [
        "# -*- coding: utf-8 -*-",
        "# 临时调试用例（定位器自动生成，跑完即删，勿提交）：token=%s" % token,
        "import time",
        "import ujson",
        "import allure",
        "from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client",
        "from page_objects.createElement import CreateElement",
        "from page_objects.app_ui.locator_type import Locator_Type",
        "from page_objects.app_ui.wait_type import Wait_Type as Wait_By",
        "",
        "RESULT_FILE = 'output/%s.json'" % token,
        "",
        "@allure.parent_suite('快歌APP自动化')",
        "@allure.suite('定位器调试')",
        "class TestDebugTmp:",
        "",
        "    def setup_class(self):",
        "        client = APP_UI_Android_demoProject_Client(is_need_kill_app=False)",
        "        self.op = client.appOperator",
        "",
        "    def test_debug(self):",
        "        results = {'op': None, 'asserts': [], 'finished_at': ''}",
        "        op = self.op",
    ]
    # 操作段（probe 复用「元素等待方式/等待秒数」，与保存用例的元素行为一致）
    need_el = op_type in _DEBUG_NEED_ELEMENT
    if need_el:
        lines += [
            "        el = CreateElement.create(Locator_Type.%s, %r, None," % (lt, lv),
            "                                  Wait_By.%s, wait_seconds=%s)" % (wait_type, wait_sec),
        ]
    if op_type == 'click':
        body = ["op.click(op.getElement(el))"]
    elif op_type == 'input':
        body = ["op.sendText(op.getElement(el), %r)" % (param or '')]
    elif op_type == 'long_press':
        body = ["op.touch_long_press(op.getElement(el), duration_sconds=2)"]
    elif op_type == 'tap':
        x, y = [int(v) for v in str(param).split(',')]
        body = ["op.tap(%d, %d)" % (x, y)]
    elif op_type == 'sleep':
        body = ["time.sleep(%d)" % int(float(param or 2))]
    elif op_type == 'screenshot':
        body = ["time.sleep(1)", "op.get_screenshot('定位器调试截图')"]
    elif op_type == 'wait_element':
        body = ["op.getElement(el)"]
    elif op_type == 'if_click':
        body = [
            "try:",
            "    op.click(op.getElement(el))",
            "except Exception:",
            "    pass",
        ]
    elif op_type == 'assert_visible':
        body = ["op.getElement(el)"]
    elif op_type == 'hide_keyboard':
        body = [
            "try:",
            "    if op.is_keyboard_shown():",
            "        op.hide_keyboard()",
            "except Exception:",
            "    op.press_keycode(4)",
            "time.sleep(1)",
        ]
    elif op_type:
        body = None
    else:
        body = ["pass  # 仅断言调试：无操作"]
    if body is None:
        return None, '操作类型 %s 暂不支持调试' % op_type
    lines.append("        try:")
    for b in body:
        lines.append("            " + b)
    lines += [
        "            results['op'] = {'desc': %r, 'ok': True, 'error': ''}" % _DEBUG_OP_NAMES.get(op_type, op_type),
        "        except Exception as e:",
        "            results['op'] = {'desc': %r, 'ok': False, 'error': str(e)[:200]}" % _DEBUG_OP_NAMES.get(op_type, op_type),
        "        time.sleep(1)  # 操作后留 1s 等页面稳定，再执行断言",
    ]
    # 断言段（多选，逐条收集不中断——与用例运行时同一批 assert_*_or_record 方法）
    lines.append("        results['asserts'] = []")
    if any((a.get('type') or '') in ('exists', 'text', 'gone') for a in asserts) and not need_el:
        # 操作段没用元素探针（坐标点击/等待/仅断言调试等），断言需要时在此补建
        lines += [
            "        el = CreateElement.create(Locator_Type.%s, %r, None," % (lt, lv),
            "                                  Wait_By.%s, wait_seconds=%s)" % (wait_type, wait_sec),
        ]
    for i, a in enumerate(asserts, 1):
        kind = (a.get('type') or '').strip()
        desc = '调试·断言%d·%s' % (i, _DEBUG_ASSERT_NAMES.get(kind, kind))
        lines.append("        _f = []")
        if kind == 'exists':
            try:
                w = int(a.get('wait') or 3)
            except (TypeError, ValueError):
                w = 3
            lines.append("        op.assert_exists_or_record(_f, %r, el, wait_seconds=%d)" % (desc, w))
        elif kind == 'text':
            try:
                w = int(a.get('wait') or 3)
            except (TypeError, ValueError):
                w = 3
            lines.append("        op.assert_text_or_record(_f, %r, el, expected=%r)" % (desc, a.get('text') or ''))
            # 语义提示：元素级文本断言读的是选中元素自身的 text——文本常在子节点上（容器 text 为空）。
            # 失败时页面级检索一次：期望文本若在页面其他节点上，给出可操作的修正建议
            _hint_tpl = ('提示：页面级检索到 %d 个含「' + (a.get('text') or '')
                         + '」的节点——文本在别的节点上：请重新选中该文本节点本身再断言，或改用「断言页面文本出现」')
            lines += [
                "        if _f:",
                "            try:",
                "                _hits = op.getElements(CreateElement.create(",
                "                    Locator_Type.XPATH, \"//*[contains(@text,%r)]\", None," % (a.get('text') or ''),
                "                    Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=3))",
                "                if _hits:",
                "                    _f.append(%r %% len(_hits))" % _hint_tpl,
                "                else:",
                "                    _f.append('提示：页面级检索也未发现该文本——页面可能仍在启动/加载中，或文本尚未出现')",
                "            except Exception as _he:",
                "                _f.append('提示：页面级检索异常: ' + str(_he)[:80])",
            ]
        elif kind == 'toast':
            lines.append("        op.assert_toast_or_record(_f, %r, %r, wait_seconds=5)" % (desc, a.get('toast') or ''))
        elif kind == 'text_page':
            lines.append("        op.assert_page_text_or_record(_f, %r, %r, wait_seconds=5)" % (desc, a.get('text') or ''))
        elif kind == 'gone':
            try:
                w = int(a.get('wait') or 2)
            except (TypeError, ValueError):
                w = 2
            lines.append("        op.assert_gone_or_record(_f, %r, el, wait_seconds=%d)" % (desc, w))
        elif kind == 'visual':
            asset = (a.get('asset') or '').strip()
            try:
                th = float(a.get('threshold') or 0.95)
            except (TypeError, ValueError):
                th = 0.95
            if asset:
                lines.append("        op.assert_visual_asset_record(_f, %r, %r, threshold=%.2f)" % (desc, asset, th))
            else:
                lines.append("        _f.append('未选择视觉资产（请先在视觉断言里采集资产）')")
        else:
            lines.append("        _f.append('未知断言类型 %s')" % kind)
        lines.append("        results['asserts'].append({'kind': %r, 'name': %r, 'ok': not _f, 'detail': '; '.join(_f)[:400]})"
                     % (kind, _DEBUG_ASSERT_NAMES.get(kind, kind)))
    lines += [
        "        results['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')",
        "        with open(RESULT_FILE, 'w', encoding='utf-8') as f:",
        "            ujson.dump(results, f, ensure_ascii=False)",
    ]
    return '\n'.join(lines) + '\n', ''


def _debug_cleanup_cases(older_than_sec=7200, token_prefix=None):
    """清理临时调试用例（跑完即删 + 孤儿兜底：默认删 2h 前的残留，_pyc 一并清）"""
    import glob
    d = os.path.join(os.getcwd(), _DEBUG_CASE_DIR)
    now = time.time()
    removed = 0
    for p in glob.glob(os.path.join(d, 'test_zdebug_*.py')):
        if token_prefix and token_prefix not in p:
            continue
        try:
            if older_than_sec is None or now - os.path.getmtime(p) >= older_than_sec:
                os.remove(p)
                removed += 1
        except OSError:
            pass
    for p in glob.glob(os.path.join(d, '__pycache__', 'test_zdebug_*.pyc')):
        try:
            os.remove(p)
        except OSError:
            pass
    return removed


@app.route('/api/debug_run', methods=['POST'])
def api_debug_run():
    """调试：临时生成单步用例（操作+勾选断言）→ 现有 runner 真机执行 → 前端轮询取临时结果"""
    data = request.get_json(silent=True) or {}
    serial = _request_serial()
    if not serial:
        return jsonify({'ok': False, 'msg': '未检测到在线设备'})
    lt = (data.get('locator_type') or '').strip()
    lv = (data.get('locator_value') or '').strip()
    wait_type = (data.get('wait_type') or 'PRESENCE_OF_ELEMENT_LOCATED').strip()
    wait_sec = (data.get('wait_sec') or 6)
    op_type = (data.get('op_type') or '').strip()
    param = (data.get('param') or '').strip()
    asserts = [a for a in (data.get('asserts') or []) if (a.get('type') or '').strip()]
    if op_type and op_type not in _DEBUG_OP_NAMES:
        return jsonify({'ok': False, 'msg': '操作类型 %s 暂不支持调试（v1 支持：点击/输入/长按/坐标点击/截图/等待/出现才点击/收起键盘）' % op_type})
    need_el = (op_type in _DEBUG_NEED_ELEMENT) or any(
        (a.get('type') or '') in ('exists', 'text', 'gone') for a in asserts)
    if need_el and (not lt or not lv):
        return jsonify({'ok': False, 'msg': '该操作/断言需要元素定位值（定位方式+定位值）'})
    if not op_type and not asserts:
        return jsonify({'ok': False, 'msg': '请先选操作类型或勾选断言'})
    if need_el:
        from page_objects.app_ui.locator_type import Locator_Type as _LT
        if not hasattr(_LT, lt):
            return jsonify({'ok': False, 'msg': '未知定位方式 %s' % lt})
    try:
        wait_sec = max(1, min(600, int(wait_sec)))
    except (TypeError, ValueError):
        wait_sec = 6
    if op_type == 'tap':
        try:
            xs, ys = str(param).split(',')
            int(xs), int(ys)
        except (ValueError, TypeError):
            return jsonify({'ok': False, 'msg': '坐标点击参数格式应为 x,y（如 360,800）'})
    if op_type == 'sleep':
        try:
            int(float(param or 2))
        except (ValueError, TypeError):
            return jsonify({'ok': False, 'msg': '固定等待参数应为秒数（数字）'})
    from web_platform import runner
    if runner.manager.running_task():
        return jsonify({'ok': False, 'msg': '平台正在执行用例——调试与执行互斥，请等用例跑完再调试'})
    # 孤儿兜底：清 2h 前的临时用例残留
    _debug_cleanup_cases(older_than_sec=7200)
    # 调试专用 conf：保留 appPackages/appActivitys（pojo 需要它构建 caps），但注入
    # dontStopAppOnReset=true + 复用 noReset=true —— uiautomator2 驱动此时跳过启动、
    # 不执行 am start -S 强杀，会话附着到前台：调试的就是用户正在看的页面
    try:
        conf_text = open(_DEBUG_CONF, encoding='utf-8').read()
        if re.search(r'(?m)^dontStopAppOnResets\s*=', conf_text):
            conf_text = re.sub(r'(?m)^dontStopAppOnResets\s*=.*$', 'dontStopAppOnResets = True ||', conf_text)
        else:
            conf_text += '\n# 定位器调试：会话附着前台不重启 App（自动生成）\ndontStopAppOnResets = True ||\n'
        os.makedirs(os.path.dirname(os.path.join(os.getcwd(), _DEBUG_CONF_OUT)), exist_ok=True)
        with open(os.path.join(os.getcwd(), _DEBUG_CONF_OUT), 'w', encoding='utf-8') as f:
            f.write(conf_text)
    except OSError as e:
        return jsonify({'ok': False, 'msg': '生成调试 conf 失败: %s' % e})
    token = 'debug_' + time.strftime('%Y%m%d%H%M%S')
    case_name = 'test_zdebug_%s.py' % token
    case_abs = os.path.join(os.getcwd(), _DEBUG_CASE_DIR, case_name)
    src, err = _debug_case_source(token, lt, lv, wait_type, wait_sec, op_type, param, asserts)
    if err:
        return jsonify({'ok': False, 'msg': err})
    try:
        compile(src, case_name, 'exec')   # 生成即语法校验，坏代码不落盘
    except SyntaxError as e:
        return jsonify({'ok': False, 'msg': '临时用例生成语法错误: %s' % e})
    with open(case_abs, 'w', encoding='utf-8') as f:
        f.write(src)
    node = '%s/%s::TestDebugTmp::test_debug' % (_DEBUG_CASE_DIR, case_name)
    ok, run_id_or_err = runner.manager.start_run(
        _DEBUG_CONF_OUT, [node], overrides={'udid': serial},
        owner='定位器调试', timeout_minutes=_DEBUG_TIMEOUT_MIN,
        setup_reset=False,   # 调试绝不前置清数据（会毁掉用户当前页面状态）
        teardown_reset=False)
    if not ok:
        try:
            os.remove(case_abs)
        except OSError:
            pass
        return jsonify({'ok': False, 'msg': run_id_or_err})
    return jsonify({'ok': True, 'token': token, 'run_id': run_id_or_err})


@app.route('/api/debug_result')
def api_debug_result():
    """轮询调试结果：执行中返回 state=running；结束后回读临时结果 JSON 并删除临时用例"""
    token = (request.args.get('token') or '').strip()
    run_id = (request.args.get('run_id') or '').strip()
    if not re.match(r'^debug_\d{14}$', token) or not re.match(r'^[0-9_]+$', run_id):
        return jsonify({'ok': False, 'msg': '参数不合法'}), 400
    from web_platform import runner
    task = runner.manager.get_task(run_id)
    if task and task.get('status') in ('PENDING', 'RUNNING'):
        return jsonify({'ok': True, 'state': 'running', 'status': task['status']})
    results = None
    rf = os.path.join(os.getcwd(), 'output', '%s.json' % token)
    try:
        import ujson
        with open(rf, 'r', encoding='utf-8') as f:
            results = ujson.load(f)
    except Exception:
        results = None
    removed = _debug_cleanup_cases(older_than_sec=None, token_prefix=token)
    case_abs = os.path.join(os.getcwd(), _DEBUG_CASE_DIR, 'test_zdebug_%s.py' % token)
    status = task.get('status') if task else 'UNKNOWN'
    return jsonify({'ok': True, 'state': 'finished', 'run_id': run_id, 'task_status': status,
                    'results': results, 'case_cleaned': not os.path.isfile(case_abs)})


if __name__ == '__main__':
    serial = device.get_device()
    if serial:
        print('已检测到设备: %s (%s)' % (serial, device.device_info(serial).get('model')))
    else:
        print('警告: 未检测到 Android 设备，界面将无法刷新截图（请连接手机后点"刷新"）')
    print('元素定位器已启动: http://127.0.0.1:%d/' % PORT)
    # 0.0.0.0：接受所有网卡进入，局域网同事可直接访问
    app.run(host='0.0.0.0', port=PORT, debug=False)