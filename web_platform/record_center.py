# -*- coding: utf-8 -*-
"""录制调试中心（平台侧）· 复用 GitHub 官方项目，自研仅启动器与落盘

- Web 录制  = Playwright 官方 codegen（microsoft/playwright）：真实浏览器窗口里
  操作，代码实时写入产物文件（`playwright codegen --target python -o <file> <url>`）
- App 录制  = Maestro Studio（mobile-dev-inc/maestro）：真机界面里操作生成流程，
  Studio 界面 http://127.0.0.1:9999（`maestro studio`）
- 调试运行  = trace_lab/debug_web.py 把任意录制产物（网页 .py）自动带 trace 执行，
  跑完在 Playwright trace viewer 里回放；App 流程用 `maestro test` 直接跑真机
- 项目配置  = trace_lab/record_project.yaml（入口地址/浏览器/视口/保存目录），
  页面可编辑，两端各自的产物落配置指定的保存目录

上游工具原封不动，本模块只负责：拉起/停止进程、产物文件管理、配置持久化。
"""
import glob
import os
import re
import shutil
import subprocess
import threading
import time

import yaml
from flask import Blueprint, jsonify, request, send_file

from web_platform.runtime_config import BASE_DIR, adb_devices

bp = Blueprint('record_center', __name__)

TRACE_VENV_PY = os.path.join(BASE_DIR, 'trace_lab', '.venv', 'bin', 'python')
DEBUG_RUNNER = os.path.join(BASE_DIR, 'trace_lab', 'debug_web.py')
CONFIG_PATH = os.path.join(BASE_DIR, 'trace_lab', 'record_project.yaml')
MAESTRO = shutil.which('maestro') or os.path.expanduser('~/.maestro/bin/maestro')

DEFAULT_CFG = {
    'web': {
        'base_url': 'https://www.baidu.com',
        'browser': 'chromium',
        'viewport': '1280,720',
        'save_dir': 'recordings/web',
    },
    'app': {
        'save_dir': 'recordings/app',
    },
}

_LOCK = threading.RLock()
_procs = {'web': None, 'app': None, 'debug': None}
_debug = {'kind': '', 'run_id': '', 'running': False, 'log_path': '', 'exit': None}

_REL_RE = re.compile(r'^(web|app)/[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff_\-.]*\.(py|yaml|yml)$')


# ---------------------------------------------------------------- 配置
def _cfg():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            saved = yaml.safe_load(f) or {}
    except Exception:
        saved = {}
    cfg = {'web': dict(DEFAULT_CFG['web']), 'app': dict(DEFAULT_CFG['app'])}
    for sec in ('web', 'app'):
        cfg[sec].update({k: v for k, v in (saved.get(sec) or {}).items() if v})
    return cfg


def _save_dir(section):
    d = os.path.join(BASE_DIR, _cfg()[section]['save_dir'])
    os.makedirs(d, exist_ok=True)
    return d


def _abs(rel):
    """web/xxx.py → 绝对路径（白名单校验，防穿越）。非法返回 None。"""
    rel = str(rel or '').replace('\\', '/')
    if not _REL_RE.match(rel):
        return None
    path = os.path.join(BASE_DIR, _cfg()[rel.split('/')[0]]['save_dir'], os.path.basename(rel))
    return path if os.path.isfile(path) else None


# ---------------------------------------------------------------- 进程管理
def _stop(section):
    proc = _procs.get(section)
    if not proc or proc.poll() is not None:
        _procs[section] = None
        return True, '未在运行'
    try:
        import signal
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    _procs[section] = None
    return True, '已停止'


def _env_clean():
    return {k: v for k, v in os.environ.items()
            if k not in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                         'ALL_PROXY', 'all_proxy', 'PYTHONPATH')}


# ---------------------------------------------------------------- 路由：配置
@bp.route('/api/record/config', methods=['GET'])
def api_config_get():
    env = {
        'pw_ready': os.path.isfile(TRACE_VENV_PY),
        'maestro': '',
        'devices': [],
    }
    try:
        r = subprocess.run([MAESTRO, '--version'], capture_output=True, text=True, timeout=15)
        env['maestro'] = (r.stdout or '').strip().splitlines()[-1] if r.stdout else ''
    except Exception:
        env['maestro'] = ''
    try:
        env['devices'] = adb_devices().get('devices') or []
    except Exception:
        pass
    return jsonify({'ok': True, 'config': _cfg(), 'env': env})


@bp.route('/api/record/config', methods=['POST'])
def api_config_save():
    body = request.json or {}
    cfg = _cfg()
    for sec in ('web', 'app'):
        for k, v in (body.get(sec) or {}).items():
            if k in cfg[sec]:
                cfg[sec][k] = str(v).strip()
    if cfg['web']['browser'] not in ('chromium', 'firefox', 'webkit'):
        return jsonify({'ok': False, 'msg': '浏览器仅支持 chromium / firefox / webkit'})
    for sec in ('web', 'app'):
        d = cfg[sec]['save_dir']
        if not d or d.startswith('/') or '..' in d:
            return jsonify({'ok': False, 'msg': '保存目录需为项目内相对路径（如 recordings/web）'})
        os.makedirs(os.path.join(BASE_DIR, d), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write('# 录制调试中心 · 项目配置（页面可编辑；base_url/浏览器/视口/保存目录）\n')
        f.write(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    return jsonify({'ok': True, 'msg': '配置已保存', 'config': cfg})


# ---------------------------------------------------------------- 路由：录制
@bp.route('/api/record/status')
def api_status():
    with _LOCK:
        web, app_, debug = _procs['web'], _procs['app'], _procs['debug']
        return jsonify({
            'ok': True,
            'web': {'running': bool(web and web.poll() is None)},
            'app': {'running': bool(app_ and app_.poll() is None),
                    'studio_url': 'http://127.0.0.1:9999'},
            'debug': {'running': bool(debug and debug.poll() is None),
                      'kind': _debug['kind'], 'run_id': _debug['run_id']},
        })


@bp.route('/api/record/web/start', methods=['POST'])
def api_web_start():
    with _LOCK:
        old = _procs.get('web')
        if old and old.poll() is None:
            return jsonify({'ok': False, 'msg': '网页录制已在进行中，请先停止'})
        if not os.path.isfile(TRACE_VENV_PY):
            return jsonify({'ok': False, 'msg': '录制环境未就绪：python3 -m venv trace_lab/.venv '
                                                '&& trace_lab/.venv/bin/pip install -r trace_lab/requirements-trace.txt'})
        cfg = _cfg()['web']
        url = (request.json or {}).get('url') or cfg['base_url']
        if url and not url.startswith('http'):
            return jsonify({'ok': False, 'msg': '入口地址需以 http:// 或 https:// 开头'})
        save_dir = _save_dir('web')
        out_file = os.path.join(save_dir, 'web_%s.py' % time.strftime('%Y%m%d_%H%M%S'))
        cmd = [TRACE_VENV_PY, '-m', 'playwright', 'codegen', '--target', 'python',
               '-b', cfg['browser'], '-o', out_file]
        if cfg.get('viewport'):
            cmd += ['--viewport-size', cfg['viewport']]
        if url:
            cmd.append(url)
        log = open(os.path.join(BASE_DIR, 'trace_lab', 'codegen.log'), 'a', encoding='utf-8')
        try:
            proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=_env_clean(),
                                    start_new_session=True)
        except Exception as e:
            return jsonify({'ok': False, 'msg': '启动录制失败：%s' % e})
        _procs['web'] = proc
        return jsonify({'ok': True, 'msg': '网页录制已开始：%s 窗口已打开，操作会被实时记录到 %s'
                        % (cfg['browser'], os.path.relpath(out_file, BASE_DIR)),
                        'file': os.path.relpath(out_file, BASE_DIR)})


@bp.route('/api/record/web/stop', methods=['POST'])
def api_web_stop():
    ok, msg = _stop('web')
    return jsonify({'ok': ok, 'msg': msg or '网页录制已停止，产物见录制产物列表'})


@bp.route('/api/record/app/start', methods=['POST'])
def api_app_start():
    with _LOCK:
        old = _procs.get('app')
        if old and old.poll() is None:
            return jsonify({'ok': False, 'msg': 'Maestro Studio 已在运行'})
        if not os.path.isfile(MAESTRO):
            return jsonify({'ok': False, 'msg': 'maestro 未安装（预期 ~/.maestro/bin/maestro）'})
        log = open(os.path.join(BASE_DIR, 'trace_lab', 'studio.log'), 'a', encoding='utf-8')
        try:
            proc = subprocess.Popen([MAESTRO, 'studio'], cwd=BASE_DIR,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=_env_clean(),
                                    start_new_session=True)
        except Exception as e:
            return jsonify({'ok': False, 'msg': '启动 Maestro Studio 失败：%s' % e})
        _procs['app'] = proc
        time.sleep(2)
        running = proc.poll() is None
        return jsonify({'ok': running,
                        'msg': ('Maestro Studio 已启动：在打开的 http://127.0.0.1:9999 界面里操作真机生成流程，'
                                '导出 YAML 保存到 recordings/app/ 即出现在录制产物列表')
                        if running else 'Maestro Studio 启动即退出（多半是设备不在线，请先连接设备）',
                        'studio_url': 'http://127.0.0.1:9999'})


@bp.route('/api/record/app/stop', methods=['POST'])
def api_app_stop():
    ok, msg = _stop('app')
    return jsonify({'ok': ok, 'msg': 'Maestro Studio 已停止'} if ok else {'ok': ok, 'msg': msg})


# ---------------------------------------------------------------- 路由：产物
@bp.route('/api/record/files')
def api_files():
    out = []
    for sec in ('web', 'app'):
        save_dir = os.path.join(BASE_DIR, _cfg()[sec]['save_dir'])
        for p in sorted(glob.glob(os.path.join(save_dir, '*.py')) +
                        glob.glob(os.path.join(save_dir, '*.yaml')) +
                        glob.glob(os.path.join(save_dir, '*.yml')),
                        key=os.path.getmtime, reverse=True):
            out.append({
                'rel': '%s/%s' % (sec, os.path.basename(p)),
                'kind': sec,
                'size': os.path.getsize(p),
                'mtime': int(os.path.getmtime(p)),
            })
    return jsonify({'ok': True, 'files': out[:100]})


@bp.route('/api/record/source')
def api_source():
    path = _abs(request.args.get('rel'))
    if not path:
        return jsonify({'ok': False, 'msg': '文件不存在'}), 404
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return jsonify({'ok': True, 'content': f.read()})


@bp.route('/api/record/delete', methods=['POST'])
def api_delete():
    path = _abs((request.json or {}).get('rel'))
    if not path:
        return jsonify({'ok': False, 'msg': '文件不存在'}), 404
    os.remove(path)
    return jsonify({'ok': True, 'msg': '已删除'})


# ---------------------------------------------------------------- 路由：调试运行
@bp.route('/api/record/web/debug', methods=['POST'])
def api_web_debug():
    """带 trace 调试运行网页录制产物：trace.zip 落 output/trace_runs/<run_id>/，
    跑完在官方 viewer 回放（复用 /trace-lab/viewer/<run_id>）。"""
    rel = str((request.json or {}).get('rel') or '')
    if not rel.endswith('.py'):
        return jsonify({'ok': False, 'msg': '调试运行只接受 .py 脚本（步骤稿 .steps.yaml 请先「生成脚本」）'})
    path = _abs(rel)
    if not path:
        return jsonify({'ok': False, 'msg': '文件不存在'})
    with _LOCK:
        dbg = _procs.get('debug')
        if dbg and dbg.poll() is None:
            return jsonify({'ok': False, 'msg': '已有调试运行在进行中'})
        if not os.path.isfile(TRACE_VENV_PY):
            return jsonify({'ok': False, 'msg': '调试环境未就绪（trace_lab/.venv）'})
        from web_platform.trace_lab import _next_run_id
        run_id = _next_run_id()
        run_dir = os.path.join(BASE_DIR, 'output', 'trace_runs', run_id)
        os.makedirs(run_dir, exist_ok=True)
        log_path = os.path.join(run_dir, 'run.log')
        log = open(log_path, 'w', encoding='utf-8')
        try:
            proc = subprocess.Popen([TRACE_VENV_PY, DEBUG_RUNNER, path,
                                     os.path.join(run_dir, 'trace.zip')],
                                    cwd=BASE_DIR, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=_env_clean(),
                                    start_new_session=True)
        except Exception as e:
            return jsonify({'ok': False, 'msg': '启动调试运行失败：%s' % e})
        _procs['debug'] = proc
        _debug.update(kind='web', run_id=run_id, running=True, log_path=log_path, exit=None)
        threading.Thread(target=_wait_debug, args=(proc, log), daemon=True).start()
        return jsonify({'ok': True, 'msg': '调试运行已启动（%s），结束后可打开 trace 回放' % run_id,
                        'run_id': run_id})


@bp.route('/api/record/app/debug', methods=['POST'])
def api_app_debug():
    """maestro test 真机调试运行 App 流程产物。"""
    rel = str((request.json or {}).get('rel') or '')
    if not rel.endswith(('.yaml', '.yml')):
        return jsonify({'ok': False, 'msg': 'App 调试只接受 .yaml 流程（Maestro 官方格式即步骤规范）'})
    path = _abs(rel)
    if not path:
        return jsonify({'ok': False, 'msg': '文件不存在'})
    with _LOCK:
        dbg = _procs.get('debug')
        if dbg and dbg.poll() is None:
            return jsonify({'ok': False, 'msg': '已有调试运行在进行中'})
        if not os.path.isfile(MAESTRO):
            return jsonify({'ok': False, 'msg': 'maestro 未安装'})
        from web_platform.trace_lab import _next_run_id
        run_id = _next_run_id()
        run_dir = os.path.join(BASE_DIR, 'output', 'trace_runs', run_id)
        os.makedirs(run_dir, exist_ok=True)
        log_path = os.path.join(run_dir, 'run.log')
        log = open(log_path, 'w', encoding='utf-8')
        try:
            proc = subprocess.Popen([MAESTRO, 'test', path], cwd=BASE_DIR,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=_env_clean(),
                                    start_new_session=True)
        except Exception as e:
            return jsonify({'ok': False, 'msg': '启动调试运行失败：%s' % e})
        _procs['debug'] = proc
        _debug.update(kind='app', run_id=run_id, running=True, log_path=log_path, exit=None)
        threading.Thread(target=_wait_debug, args=(proc, log), daemon=True).start()
        return jsonify({'ok': True, 'msg': 'App 流程调试已启动（%s，需设备在线）' % run_id,
                        'run_id': run_id})


def _wait_debug(proc, log_f):
    code = proc.wait()
    try:
        log_f.close()
    except Exception:
        pass
    with _LOCK:
        _debug['running'] = False
        _debug['exit'] = code
    has_zip = os.path.isfile(os.path.join(BASE_DIR, 'output', 'trace_runs',
                                          _debug['run_id'], 'trace.zip'))
    if _debug['kind'] == 'web' and not has_zip:
        pass  # 留给前端从状态接口读取 exit 与提示


@bp.route('/api/record/debug/status')
def api_debug_status():
    with _LOCK:
        d = dict(_debug)
        proc = _procs.get('debug')
        d['running'] = bool(proc and proc.poll() is None)
        d['has_zip'] = os.path.isfile(os.path.join(
            BASE_DIR, 'output', 'trace_runs', d['run_id'] or '_', 'trace.zip'))
        return jsonify({'ok': True, **d})


@bp.route('/api/record/debug/log')
def api_debug_log():
    offset = request.args.get('offset', 0, type=int)
    path = _debug.get('log_path') or ''
    if not path or not os.path.isfile(path):
        return jsonify({'ok': True, 'lines': [], 'offset': 0})
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    return jsonify({'ok': True, 'lines': lines[offset:], 'offset': len(lines)})


@bp.route('/api/record/log/<name>')
def api_tool_log(name):
    """codegen / studio 启动日志尾部（排障用）。"""
    if name not in ('codegen', 'studio'):
        return jsonify({'ok': False, 'msg': '非法日志名'}), 404
    path = os.path.join(BASE_DIR, 'trace_lab', '%s.log' % name)
    if not os.path.isfile(path):
        return jsonify({'ok': True, 'lines': []})
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return jsonify({'ok': True, 'lines': f.read().splitlines()[-50:]})


# ---------------------------------------------------------------- 步骤生成（写好步骤 → Playwright 脚本）
# 规范：YAML 步骤稿是源头（<名字>.steps.yaml），脚本是生成物（同名 .py，可反复重新生成/调试运行）。
# 动作集贴合 Playwright 官方 API；选择器直接用 Playwright 选择器语法（#id / text=xx / role=..）。

STEPS_TEMPLATE = '''name: 示例流程
base_url: http://127.0.0.1:8080        # 可选：相对地址前缀；步骤里写完整 URL 则忽略
viewport: "1280,720"                   # 可选
steps:
  - goto: /e2e-page                    # 打开页面（相对 base_url 或完整 URL）
  - fill: {selector: "#kw", text: "自动化测试"}   # 输入
  - click: "#su"                       # 点击（简写）；完整写法 {selector: "#su", desc: 点搜索}
  - press: Enter                       # 按键
  - wait: 1                            # 等待秒数
  - wait_for: "#result"                # 等元素出现
  - screenshot: 结果.png               # 截图（存 output/record_shots/）
  - assert_visible: "#result"          # 断言元素可见
  - assert_text: {selector: "body", contains: "ok"}   # 断言文本包含
'''

_WEB_VERBS = ('goto', 'fill', 'click', 'press', 'wait', 'wait_for', 'hover',
              'select', 'check', 'uncheck', 'screenshot', 'slide',
              'assert_visible', 'assert_text', 'assert_title')


def _py(s):
    """Python 字符串字面量（json 兼容）。"""
    import json as _json
    return _json.dumps(str(s), ensure_ascii=False)


def _sel(arg, errors, idx, verb):
    """从步骤参数提取选择器：简写字符串或 {selector: ...}。"""
    if isinstance(arg, str):
        return arg
    if isinstance(arg, dict) and arg.get('selector'):
        return str(arg['selector'])
    errors.append('第 %d 步「%s」缺少 selector（写法：- %s: "#id" 或 - %s: {selector: "#id", ...}）'
                  % (idx, verb, verb, verb))
    return None


def _gen_step(verb, arg, idx, errors, base_url):
    """单个步骤 → 一行（或数行）缩进 4 的脚本体。不支持返回 None。"""
    err0 = len(errors)
    line = None
    if verb == 'goto':
        if not isinstance(arg, str) or not arg:
            errors.append('第 %d 步 goto 需要地址：- goto: "/path" 或完整 URL' % idx)
            return None
        url = arg if arg.startswith('http') else base_url + arg
        line = 'page.goto(%s)' % _py(url)
    elif verb == 'fill':
        sel = _sel(arg, errors, idx, verb)
        if sel is not None:
            text = arg.get('text', '') if isinstance(arg, dict) else ''
            if not text:
                errors.append('第 %d 步 fill 缺少 text：{selector: "#id", text: "内容"}' % idx)
                return None
            line = 'page.fill(%s, %s)' % (_py(sel), _py(text))
    elif verb in ('click', 'hover', 'check', 'uncheck', 'wait_for', 'assert_visible'):
        sel = _sel(arg, errors, idx, verb)
        if sel is not None:
            if verb == 'wait_for':
                line = 'page.wait_for_selector(%s)' % _py(sel)
            elif verb == 'assert_visible':
                line = 'expect(page.locator(%s)).to_be_visible()' % _py(sel)
            else:
                line = 'page.%s(%s)' % (verb, _py(sel))
    elif verb == 'press':
        if not isinstance(arg, str) or not arg:
            errors.append('第 %d 步 press 需要键名：- press: Enter' % idx)
            return None
        line = 'page.keyboard.press(%s)' % _py(arg)
    elif verb == 'wait':
        try:
            ms = int(float(arg) * 1000)
        except (TypeError, ValueError):
            errors.append('第 %d 步 wait 需要秒数：- wait: 2' % idx)
            return None
        line = 'page.wait_for_timeout(%d)' % ms
    elif verb == 'screenshot':
        name = str(arg or ('shot_%d.png' % idx))
        line = 'page.screenshot(path=os.path.join(shot_dir, %s), full_page=True)' % _py(name)
    elif verb in ('slide', 'drag'):
        # 滑块/拖拽（codegen 录不到连续手势，用本动作补）：按住滑块 → 分步移动 → 松手
        if not isinstance(arg, dict):
            arg = {'selector': arg}
        sel = _sel(arg, errors, idx, verb)
        if sel is None:
            return None
        hold = arg.get('hold')
        try:
            hold_ms = int(float(hold) * 1000) if hold else 0
        except (TypeError, ValueError):
            errors.append('第 %d 步 slide 的 hold 需为秒数（如 0.3）' % idx)
            return None
        try:
            move_steps = int(arg.get('steps') or 25)
        except (TypeError, ValueError):
            errors.append('第 %d 步 slide 的 steps 需为整数（分几步移动，模拟人手）' % idx)
            return None
        s, t, k = '_s%d' % idx, '_t%d' % idx, '_k%d' % idx
        lines = [
            '%s = page.locator(%s).bounding_box()' % (s, _py(sel)),
            '_sx, _sy = %s["x"] + %s["width"] / 2, %s["y"] + %s["height"] / 2' % (s, s, s, s),
            'page.mouse.move(_sx, _sy)',
            'page.mouse.down()',
        ]
        if arg.get('to'):   # 拖到某个元素中心（按水平对齐滑块原 y）
            tsel = str(arg['to'])
            lines.append('%s = page.locator(%s).bounding_box()' % (t, _py(tsel)))
            lines.append('page.mouse.move(%s["x"] + %s["width"] / 2, _sy, steps=%d)'
                         % (t, t, move_steps))
        elif arg.get('track'):   # 沿轨道拖到底：距离 = 轨道宽 - 滑块宽
            ksel = str(arg['track'])
            lines.append('%s = page.locator(%s).bounding_box()' % (k, _py(ksel)))
            lines.append('page.mouse.move(_sx + (%s["width"] - %s["width"]), _sy, steps=%d)'
                         % (k, s, move_steps))
        elif arg.get('distance') is not None:   # 固定像素（负数反向）
            try:
                dx = int(arg['distance'])
            except (TypeError, ValueError):
                errors.append('第 %d 步 slide 的 distance 需为像素整数（如 300）' % idx)
                return None
            lines.append('page.mouse.move(_sx + %d, _sy, steps=%d)' % (dx, move_steps))
        else:
            errors.append('第 %d 步 slide 需要目标之一：distance: 像素 / to: 目标元素 / track: 轨道元素' % idx)
            return None
        if hold_ms:
            lines.append('page.wait_for_timeout(%d)' % hold_ms)
        lines.append('page.mouse.up()')
        return lines
    elif verb == 'select':
        sel = _sel(arg, errors, idx, verb)
        if sel is not None and isinstance(arg, dict):
            if arg.get('value'):
                line = 'page.select_option(%s, value=%s)' % (_py(sel), _py(arg['value']))
            elif arg.get('label'):
                line = 'page.select_option(%s, label=%s)' % (_py(sel), _py(arg['label']))
            elif arg.get('index') is not None:
                line = 'page.select_option(%s, index=%s)' % (_py(sel), int(arg['index']))
            else:
                errors.append('第 %d 步 select 需要 value/label/index 之一' % idx)
    elif verb == 'assert_text':
        sel = _sel(arg, errors, idx, verb)
        if sel is not None and isinstance(arg, dict):
            if arg.get('contains'):
                line = 'expect(page.locator(%s)).to_contain_text(%s)' % (_py(sel), _py(arg['contains']))
            elif arg.get('text'):
                line = 'expect(page.locator(%s)).to_have_text(%s)' % (_py(sel), _py(arg['text']))
            else:
                errors.append('第 %d 步 assert_text 需要 contains 或 text' % idx)
    elif verb == 'assert_title':
        if isinstance(arg, str):
            arg = {'contains': arg}
        if isinstance(arg, dict) and (arg.get('contains') or arg.get('text')):
            key = 'contains' if arg.get('contains') else 'text'
            line = ('assert %s in page.title(), %s'
                    % (_py(arg[key]), _py('标题断言失败：期望包含「%s」' % arg[key])))
        else:
            errors.append('第 %d 步 assert_title 需要 contains 或 text' % idx)
    if line is None and len(errors) == err0:
        errors.append('第 %d 步不支持的动作「%s」（支持：%s）' % (idx, verb, '/'.join(_WEB_VERBS)))
    return line


def gen_steps_script(yaml_text):
    """步骤 YAML → Playwright 脚本文本。返回 (script 或 None, errors 列表)。"""
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as e:
        return None, ['YAML 解析失败：%s' % str(e).splitlines()[0]]
    if not isinstance(data, dict):
        return None, ['顶层必须是键值结构（name / base_url / viewport / steps）']
    steps = data.get('steps')
    if not isinstance(steps, list) or not steps:
        return None, ['缺少 steps 列表，或列表为空（至少写一个步骤）']
    errors = []
    body = []
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict) or not st:
            errors.append('第 %d 步格式不对：每行应是「- 动作: 参数」' % i)
            continue
        verb = list(st.keys())[0]
        if verb == 'desc':
            continue
        arg = st[verb]
        desc = st.get('desc') or (arg.get('desc') if isinstance(arg, dict) else None)
        base_url = str(data.get('base_url') or '').rstrip('/')
        line = _gen_step(verb, arg, i, errors, base_url)
        if line is None:
            continue
        if desc:
            body.append('    # 步骤%d · %s' % (i, desc))
        if isinstance(line, list):
            body.extend('    ' + l for l in line)
        else:
            body.append('    ' + line)
    if errors:
        return None, errors
    base_url = str(data.get('base_url') or '').rstrip('/')
    viewport = str(data.get('viewport') or '').strip()
    name = str(data.get('name') or '录制备用').strip()
    if viewport:
        try:
            w, h = [int(v.strip()) for v in viewport.split(',', 1)]
        except ValueError:
            return None, ['viewport 需为「宽,高」数字（如 1280,720）']
        ctx_line = ('    context = browser.new_context('
                    'viewport={"width": %d, "height": %d})' % (w, h))
    else:
        ctx_line = '    context = browser.new_context()'
    script = (
        '# 由「录制调试中心 · 步骤生成」按步骤稿自动生成；改步骤请改同名 .steps.yaml 后重新生成\n'
        'import os\n'
        'import re\n\n'
        'from playwright.sync_api import Playwright, expect, sync_playwright\n\n\n'
        'def run(playwright: Playwright) -> None:  # %s\n'
        '    browser = playwright.chromium.launch(headless=False)\n'
        '%s\n'
        '    page = context.new_page()\n'
        '    shot_dir = os.environ.get("AT_DEBUG_SHOT_DIR") or "output/record_shots"\n'
        '    os.makedirs(shot_dir, exist_ok=True)\n'
        '%s\n'
        '    browser.close()\n\n\n'
        'with sync_playwright() as playwright:\n'
        '    run(playwright)\n' % (_py(name), ctx_line, '\n'.join(body) if body else '    pass'))
    return script, []


def _steps_rel(name):
    base = re.sub(r'[^\w\u4e00-\u9fff-]+', '_', str(name or '').strip()) or 'steps'
    return 'web/%s' % base, base


@bp.route('/api/record/gen/template', methods=['GET'])
def api_gen_template():
    return jsonify({'ok': True, 'template': STEPS_TEMPLATE})


@bp.route('/api/record/gen', methods=['POST'])
def api_gen():
    """步骤稿文本 → 校验 → 落 .steps.yaml + 生成同名 .py。"""
    body = request.json or {}
    yaml_text = str(body.get('yaml') or '')
    script, errors = gen_steps_script(yaml_text)
    if errors:
        return jsonify({'ok': False, 'msg': '；'.join(errors[:6]), 'errors': errors})
    data = yaml.safe_load(yaml_text) or {}
    rel, base = _steps_rel(data.get('name'))
    save_dir = _save_dir('web')
    with open(os.path.join(save_dir, base + '.steps.yaml'), 'w', encoding='utf-8') as f:
        f.write(yaml_text)
    with open(os.path.join(save_dir, base + '.py'), 'w', encoding='utf-8') as f:
        f.write(script)
    return jsonify({'ok': True,
                    'msg': '已生成脚本 %s.py（步骤稿 %s.steps.yaml 可随时改后重新生成）' % (rel, rel),
                    'rel': rel + '.py'})


@bp.route('/api/record/gen/from_file', methods=['POST'])
def api_gen_from_file():
    """对已有 .steps.yaml 重新生成脚本（改步骤后再生成）。"""
    rel = str((request.json or {}).get('rel') or '')
    if not rel.endswith('.steps.yaml'):
        return jsonify({'ok': False, 'msg': '只支持对 .steps.yaml 步骤稿重新生成'})
    path = _abs(rel)
    if not path:
        return jsonify({'ok': False, 'msg': '步骤稿不存在'})
    with open(path, 'r', encoding='utf-8') as f:
        script, errors = gen_steps_script(f.read())
    if errors:
        return jsonify({'ok': False, 'msg': '；'.join(errors[:6]), 'errors': errors})
    py_rel = rel[:-len('.steps.yaml')] + '.py'
    with open(os.path.join(BASE_DIR, _cfg()['web']['save_dir'], os.path.basename(py_rel)),
              'w', encoding='utf-8') as f:
        f.write(script)
    return jsonify({'ok': True, 'msg': '已重新生成 %s（可调试运行）' % py_rel, 'rel': py_rel})
