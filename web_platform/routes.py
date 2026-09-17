# -*- coding: utf-8 -*-
"""Web 执行平台 · 页面与 API 路由"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

from flask import Blueprint, jsonify, render_template, request, send_file

from web_platform import report_data
from web_platform import runner
from web_platform.changelog import APP_VERSION, CHANGELOG
from web_platform.runtime_config import (
    BASE_DIR,
    WebPlatformConfig,
    adb_devices,
    check_appium,
    find_free_port,
    list_devices_conf_files,
    parse_devices_info,
    scan_case_tree,
)

bp = Blueprint('platform', __name__)

PLATFORM_CFG = WebPlatformConfig()

# 已启动的报告静态服务：run_id -> {'port': int, 'proc': Popen}（复用，避免重复起服务/进程泄漏）
_report_services = {}


@atexit.register
def _cleanup_report_services():
    """平台退出时终止全部报告静态服务，避免孤儿进程占用端口"""
    for svc in _report_services.values():
        try:
            svc['proc'].terminate()
        except Exception:
            pass


# 用例节点白名单：文件路径/类/方法（pytest nodeid），杜绝 API 直调注入任意 pytest 参数
_NODE_RE = re.compile(r'^[A-Za-z0-9_\./:\u4e00-\u9fff-]+$')

# ---------------------------------------------------------------- 页面
@bp.route('/')
def page_index():
    return render_template('index.html')


@bp.route('/run')
def page_run():
    return render_template('run.html')


@bp.route('/runs/<run_id>')
def page_run_detail(run_id):
    return render_template('run_detail.html', run_id=run_id)


@bp.route('/report')
def page_report():
    return render_template('report.html')


@bp.route('/perf')
def page_perf():
    """⚡ 性能压测（HTTP 接口压测，独立模块）"""
    return render_template('perf.html')


# ---------------------------------------------------------------- API
@bp.route('/api/status')
def api_status():
    confs = list_devices_conf_files()
    adb = adb_devices()
    online = [d for d in adb['devices'] if d['state'] == 'device']
    appium_ok, appium_msg = check_appium('127.0.0.1', '4726')
    running = runner.manager.running_task()
    return jsonify({
        'ok': True,
        'service': 'app-ui-platform',
        'version': APP_VERSION,
        'confs': confs,
        'device_online': len(online),
        'devices': adb['devices'],
        'appium': {'ok': appium_ok, 'msg': appium_msg},
        'running': running,
        'port': PLATFORM_CFG.port,
    })


@bp.route('/api/changelog')
def api_changelog():
    """更新日志：版本号 + 更新时间（秒级）+ 变更明细（供左下角「更新日志」入口展示）"""
    return jsonify({'ok': True, 'version': APP_VERSION, 'entries': CHANGELOG})


@bp.route('/api/recording/config', methods=['GET', 'POST'])
def api_recording_config():
    """录屏配置：GET 读当前生效值（默认值 < conf < 环境变量），POST 校验并落盘 conf。"""
    from web_platform import recording_config
    if request.method == 'GET':
        return jsonify({'ok': True, 'config': recording_config.load_recording_config()})
    ok, msg, _effective = recording_config.save_recording_config(request.get_json(silent=True) or {})
    return jsonify({'ok': ok, 'msg': msg}), (200 if ok else 400)


# ---------------------------------------------------------------- 性能压测（HTTP 接口压测）
@bp.route('/api/perf/config', methods=['GET', 'POST'])
def api_perf_config():
    """压测配置：GET 返回表单结构 + 当前值；POST 校验后整体落盘 YAML（非法值不落盘）"""
    from web_platform import perf_config, perf_runner
    if request.method == 'GET':
        return jsonify({'ok': True, 'schema': perf_config.SCHEMA,
                        'values': perf_config.read_config(),
                        'venv_ready': perf_runner.venv_ready()})
    ok, msg = perf_config.write_config(request.get_json(silent=True) or {})
    return jsonify({'ok': ok, 'msg': msg}), (200 if ok else 400)


@bp.route('/api/perf/run', methods=['POST'])
def api_perf_start():
    """启动压测（默认用当前已保存配置；body 带 values 则先保存再跑）"""
    from web_platform import perf_runner
    data = request.get_json(silent=True) or {}
    ok, msg, run_id = perf_runner.start_run(data.get('values'))
    return jsonify({'ok': ok, 'msg': msg, 'run_id': run_id}), (200 if ok else 400)


@bp.route('/api/perf/stop', methods=['POST'])
def api_perf_stop():
    from web_platform import perf_runner
    data = request.get_json(silent=True) or {}
    ok, msg = perf_runner.stop_run((data.get('run_id') or '').strip())
    return jsonify({'ok': ok, 'msg': msg}), (200 if ok else 400)


@bp.route('/api/perf/runs')
def api_perf_runs():
    from web_platform import perf_runner
    return jsonify({'ok': True, 'runs': perf_runner.list_runs()})


@bp.route('/api/perf/run/<run_id>')
def api_perf_run(run_id):
    from web_platform import perf_runner
    t = perf_runner.get_run(run_id)
    return jsonify({'ok': bool(t), 'run': t}) if t else (jsonify({'ok': False, 'msg': '任务不存在'}), 404)


@bp.route('/api/perf/run/<run_id>/log')
def api_perf_log(run_id):
    from web_platform import perf_runner
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0
    lines, total = perf_runner.read_log(run_id, offset)
    return jsonify({'ok': True, 'lines': lines, 'offset': offset + len(lines), 'total': total})


@bp.route('/perf/report/<run_id>')
def page_perf_report(run_id):
    """在线查看压测报告（HTML 由压测引擎生成，收进 run 目录）"""
    from web_platform import perf_runner
    t = perf_runner.get_run(run_id)
    if not t or not t.get('report'):
        return '报告未生成（压测结束或失败时可能没有报告）', 404
    return send_file(os.path.join(BASE_DIR, t['report']))


@bp.route('/api/devices')
def api_devices():
    adb = adb_devices()
    running = runner.manager.running_task()
    used_udids = set()
    if running:
        used_udids.add(running['udid'])
    for d in adb['devices']:
        d['occupied'] = d['udid'] in used_udids and d['state'] == 'device'
    return jsonify({'ok': adb['ok'], 'msg': adb['msg'], 'devices': adb['devices']})


@bp.route('/api/cases')
def api_cases():
    return jsonify({'ok': True, 'tree': scan_case_tree()})


@bp.route('/api/confs')
def api_confs():
    confs = []
    for f in list_devices_conf_files():
        devices = parse_devices_info(f)
        confs.append({
            'file': f,
            'devices': [{
                'device_desc': d['device_desc'],
                'udid': (d.get('capabilities') or [{}])[0].get('udid', ''),
                'app_package': (d.get('capabilities') or [{}])[0].get('appPackage', ''),
                'server': '%s:%s' % (d['server_ip'], d['server_port']),
            } for d in devices],
        })
    return jsonify({'ok': True, 'confs': confs})


@bp.route('/api/exec_defaults')
def api_exec_defaults():
    """执行配置默认值：当前第一台在线设备(udid/型号) + 所选 conf 的默认 appPackage/appActivity。
    可选参数 ?conf=<文件> 指定默认值来源，缺省取第一个 conf。"""
    confs = list_devices_conf_files()
    conf_file = request.args.get('conf') or (confs[0] if confs else '')
    defaults = {'conf_file': conf_file, 'udid': '', 'model': '', 'app_package': '',
                'app_activity': '', 'server': '', 'appium_ok': False, 'occupied': False,
                'device_online': False, 'udid_from_conf': False}
    adb = adb_devices()
    online = [d for d in adb['devices'] if d['state'] == 'device']
    defaults['device_online'] = bool(online)
    if online:
        defaults['udid'] = online[0]['udid']
        defaults['model'] = online[0]['model']
    devices = parse_devices_info(conf_file) if conf_file else []
    if devices:
        d = devices[0]
        caps = (d.get('capabilities') or [{}])[0]
        defaults['app_package'] = caps.get('appPackage', '')
        defaults['app_activity'] = caps.get('appActivity', '')
        defaults['server'] = '%s:%s' % (d['server_ip'], d['server_port'])
        if not defaults['udid']:
            # 无在线设备时用 conf 里的 udid 预填输入框（仅作为默认值，不代表在线）
            defaults['udid'] = caps.get('udid', '')
            defaults['udid_from_conf'] = bool(defaults['udid'])
        defaults['appium_ok'], _ = check_appium(d['server_ip'], d['server_port'])
    running = runner.manager.running_task()
    defaults['occupied'] = bool(running)
    return jsonify({'ok': True, 'defaults': defaults, 'confs': confs})


@bp.route('/api/run', methods=['POST'])
def api_start_run():
    data = request.get_json(force=True, silent=True) or {}
    conf_file = (data.get('conf_file') or '').strip()
    case_nodes = data.get('case_nodes') or []
    case_nodes = [c for c in case_nodes if c and str(c).strip()]
    bad_nodes = [str(c) for c in case_nodes
                 if str(c).startswith('-') or '..' in str(c) or not _NODE_RE.match(str(c))]
    if bad_nodes:
        return jsonify({'ok': False, 'msg': '用例节点不合法: %s' % bad_nodes[0]}), 400
    overrides = data.get('overrides') or {}
    ok, result = runner.manager.start_run(conf_file, case_nodes, overrides)
    if not ok:
        return jsonify({'ok': False, 'msg': result}), 409 if '正在运行' in result else 400
    return jsonify({'ok': True, 'run_id': result})


@bp.route('/api/run/<run_id>')
def api_run_detail(run_id):
    task = runner.manager.get_task(run_id)
    if not task:
        return jsonify({'ok': False, 'msg': '任务不存在'}), 404
    return jsonify({'ok': True, 'task': task})


@bp.route('/api/run/<run_id>/log')
def api_run_log(run_id):
    offset = request.args.get('offset', 0, type=int)
    return jsonify(runner.manager.get_log(run_id, offset))


@bp.route('/api/run/<run_id>/cases')
def api_run_cases(run_id):
    """自建「用例执行记录」：解析 allure-results，返回用例+step+断言截图（不依赖 allure 命令行）"""
    return jsonify({'ok': True, 'cases': report_data.list_run_cases(run_id)})


@bp.route('/api/runs/<run_id>/res/<path:source>')
def api_run_attachment(run_id, source):
    """alure-results 附件（断言截图）服务；source 严格限制在结果目录内，防路径穿越"""
    p = report_data.resolve_attachment_path(run_id, source)
    if not p:
        return jsonify({'ok': False, 'msg': '附件不存在'}), 404
    return send_file(p)


@bp.route('/api/run/<run_id>/stop', methods=['POST'])
def api_stop_run(run_id):
    ok, msg = runner.manager.stop_run(run_id)
    return jsonify({'ok': ok, 'msg': msg}), 200 if ok else 400


@bp.route('/api/run/<run_id>/report', methods=['POST'])
def api_generate_report(run_id):
    """generate Allure 报告到 run/report/（不启动服务）"""
    ok, msg = runner.manager.generate_report(run_id)
    if not ok:
        return jsonify({'ok': False, 'msg': msg}), 400
    return jsonify({'ok': True, 'report_dir': msg})


@bp.route('/api/run/<run_id>/report/open', methods=['POST'])
def api_open_report(run_id):
    """确保报告生成后起本地静态服务，**等服务就绪**再返回地址（前端拿到即可直接打开）。

    用 python -m http.server 替代 allure open：allure open 会自己拉起系统默认浏览器
    （浏览器里就出现"打开两个网页"），且起服务慢；allure 报告本身是纯静态站点，http.server 等价。
    同一 run 的服务复用（_report_services），重复点击不重复起进程。"""
    task = runner.manager.get_task(run_id)
    if not task:
        return jsonify({'ok': False, 'msg': '任务不存在'}), 404
    report_dir = os.path.join(runner.RUNS_DIR, run_id, 'report')
    index_html = os.path.join(report_dir, 'index.html')
    # 未生成过则先生成
    if not os.path.isfile(index_html):
        ok, msg = runner.manager.generate_report(run_id)
        if not ok:
            return jsonify({'ok': False, 'msg': msg}), 400

    # 服务已在跑则直接复用
    svc = _report_services.get(run_id)
    if svc and svc['proc'].poll() is None:
        return jsonify({'ok': True, 'url': 'http://127.0.0.1:%d/' % svc['port'], 'reused': True})
    if svc:
        _report_services.pop(run_id, None)

    # 清理同 run 遗留的旧服务进程（平台重启后注册表为空，但进程可能还在）
    subprocess.run(['pkill', '-f', 'http.server.*runs/%s/report' % run_id],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    port = find_free_port(PLATFORM_CFG.report_start_port)
    try:
        proc = subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(port), '--directory', report_dir],
            cwd=report_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
    except Exception as e:
        return jsonify({'ok': False, 'msg': '启动报告服务失败: %s' % e}), 500

    # 轮询等服务真正可访问（最多 ~8 秒），就绪才返回，前端打开即有内容
    url = 'http://127.0.0.1:%d/' % port
    deadline = time.time() + 8
    last_err = ''
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    _report_services[run_id] = {'port': port, 'proc': proc}
                    return jsonify({'ok': True, 'url': url})
        except Exception as e:
            last_err = str(e)
        time.sleep(0.3)
    proc.terminate()
    return jsonify({'ok': False, 'msg': '报告服务启动超时: %s' % last_err}), 500


@bp.route('/api/runs')
def api_runs():
    return jsonify({'ok': True, 'runs': runner.manager.list_tasks()})


@bp.route('/api/runs/<run_id>', methods=['DELETE'])
def api_delete_run(run_id):
    ok, msg = runner.manager.delete_run(run_id)
    return jsonify({'ok': ok, 'msg': msg}), 200 if ok else 400


@bp.route('/api/runs/clear', methods=['POST'])
def api_clear_runs():
    ok, msg = runner.manager.clear_runs()
    return jsonify({'ok': ok, 'msg': msg})