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

from flask import Flask, jsonify, request, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import device
import element_library
import case_generator
from tutorials import TUTORIALS, search_tutorials

app = Flask(__name__, static_folder='static', static_url_path='/static')

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


def _refresh_payload():
    """截图 + 元素树 完整载荷（按前端指定的设备；设备掉线自动回退第一台）
    fallback=True：请求的设备已掉线、响应来自回退设备——前端据此校正下拉，
    并与「过期响应」（用户已切到别的设备）区分开，过期响应直接丢弃防串台"""
    asked = _request_serial()
    serial = device.get_device(asked)
    if not serial:
        return None
    png = device.screenshot_png(serial)
    xml = device.dump_xml(serial)
    if not xml:
        return None
    try:
        data = device.xml_to_tree(xml)
    except Exception:
        return None
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
    }


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
    payload = _refresh_payload()
    if not payload:
        return jsonify({'ok': False, 'msg': '刷新失败：请检查设备连接，或设备屏幕是否为亮屏状态'})
    return jsonify({'ok': True, **payload})


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
    )
    # 命中重复元素时附带「已被哪些用例使用」，前端复用面板展示（默认直接复用，防元素库膨胀）
    if r.get('duplicate') and not r.get('ok'):
        r['duplicate']['used_in'] = case_generator.element_usage_in_cases(r['duplicate']['name'])
    return jsonify({'ok': r['ok'], 'msg': r.get('msg', ''), 'action': r.get('action', ''),
                    'duplicate': r.get('duplicate'),
                    'filename': data.get('filename') or element_library.DEFAULT_FILE,
                    'content': r.get('content', '')})


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
                                            '可改用「⬇ 下载用例包」再在平台「用例管理 → 上传用例包」入库'
                        % str(e)[:80]})
    payload, status = import_case_package(package, files,
                                          (data.get('uploader') or 'locator').strip()[:32])
    return jsonify(payload), status


@app.route('/api/build_case_package', methods=['POST'])
def api_build_case_package():
    """「保存测试用例包·下载 zip」：三个文件打包，供平台「用例管理 → 上传用例包」入库"""
    import io
    import zipfile
    data = request.get_json(silent=True) or {}
    package = (data.get('package') or 'case_package').strip()
    files = data.get('files') or []
    if not files:
        return jsonify({'ok': False, 'msg': '缺少文件内容'}), 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr('%s/%s' % (f.get('dir', ''), f.get('name', '')), f.get('content', ''))
    buf.seek(0)
    return send_file(buf, as_attachment=True, mimetype='application/zip',
                     attachment_filename='%s.zip' % re.sub(r'[^A-Za-z0-9_\-]', '_', package))


@app.route('/api/add_code', methods=['POST'])
def api_add_code():
    """「保存并添加到用例」：把一步操作代码追加到目标用例文件的指定方法体末尾。
    gen_page_method=True（功能③）时同步生成/更新该操作的页面方法（三件套联动）。"""
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
                    'page_file': r.get('page_file', ''),
                    'page_method': r.get('page_method', ''),
                    'page_content': r.get('page_content', '')})


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


if __name__ == '__main__':
    serial = device.get_device()
    if serial:
        print('已检测到设备: %s (%s)' % (serial, device.device_info(serial).get('model')))
    else:
        print('警告: 未检测到 Android 设备，界面将无法刷新截图（请连接手机后点"刷新"）')
    print('元素定位器已启动: http://127.0.0.1:%d/' % PORT)
    # 0.0.0.0：接受所有网卡进入，局域网同事可直接访问
    app.run(host='0.0.0.0', port=PORT, debug=False)