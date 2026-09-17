# -*- coding: utf-8 -*-
"""性能压测配置（HTTP 接口压测，Locust + 阶梯/脉冲双模式）

单一数据源：perf_test/config/load_test_config.yaml（压测引擎原生读取的 YAML）。
本模块负责「读 → 校验 → 写」，供平台 ⚡ 性能压测 页面可视化编辑：
- 读取：YAML → 扁平 {section.key: value}，前端按 SCHEMA 渲染表单
- 保存：校验通过后**按模板重写** YAML（保留分组注释，值由表单回填）
- 校验：类型/范围/枚举；非法值返回 (False, msg)，且**整体不落盘**

依赖隔离：压测在 perf_test/.venv（Python 3.13 + locust 2.x）里运行，
与平台 venv（Python 3.8 + flask 1.1.2）完全隔离，升级互不影响。
"""
import os
import re

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERF_DIR = os.path.join(BASE_DIR, 'perf_test')
CONFIG_PATH = os.path.join(PERF_DIR, 'config', 'load_test_config.yaml')
VENV_PYTHON = os.path.join(PERF_DIR, '.venv', 'bin', 'python')
RUNNER = os.path.join(PERF_DIR, 'run_load_test.py')

MODES = ('staircase', 'pulse')
METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')

# 表单结构：分组 → 字段。type: str/int/float/bool/select/dict/text
# 分组标注（只影响界面展示，不影响 YAML 落盘——字段集与引擎契约保持不变）：
#   show_if: 'staircase'|'pulse' —— 仅当压测模式匹配时显示该字段（加压策略按模式二选一）
#   advanced: True —— 整组归入「高级参数」折叠区（默认收起，保持默认即可跑通）
# 精简原则：核心必填（压什么/压多大/压多久）+ 当前模式的加压策略 + 请求细节常驻，
#           思考时间、循环次数、动态参数、报告参数等低频项全部收进折叠区。
SCHEMA = [
    {'group': '核心配置', 'icon': '🎯', 'desc': '必填：压哪个接口、压多大并发、压多久',
     'fields': [
         {'section': None, 'key': 'mode', 'label': '压测模式', 'type': 'select', 'options': list(MODES),
          'help': 'staircase 阶梯递增=平缓爬坡（业务逐步放量）；pulse 瞬时脉冲=短尖峰+基准并发（秒杀洪峰）'},
         {'section': 'common', 'key': 'host', 'label': '被测服务地址', 'type': 'str',
          'help': '协议+域名+端口，如 http://127.0.0.1:8000（结尾斜杠自动去掉）'},
         {'section': 'request', 'key': 'path', 'label': '接口路径', 'type': 'str',
          'help': '相对 host，如 /api/login；支持 {变量} 占位'},
         {'section': 'request', 'key': 'method', 'label': '请求方法', 'type': 'select', 'options': list(METHODS)},
         {'section': 'common', 'key': 'vu', 'label': '并发用户上限', 'type': 'int', 'min': 1, 'max': 100000,
          'help': '阶梯模式=最终目标并发；脉冲模式=峰值参考'},
         {'section': 'common', 'key': 'run_time', 'label': '压测总时长', 'type': 'str',
          'help': '如 30s / 5m / 1h；阶梯模式须 ≥ 爬坡时长'},
     ]},
    {'group': '阶梯递增参数', 'icon': '📶', 'desc': 'mode=staircase 时生效：从起始并发逐级爬到目标并发',
     'fields': [
         {'section': 'staircase', 'key': 'start_users', 'label': '起始并发', 'type': 'int', 'min': 0, 'max': 100000, 'show_if': 'staircase'},
         {'section': 'staircase', 'key': 'step_users', 'label': '每级增加并发', 'type': 'int', 'min': 0, 'max': 100000, 'show_if': 'staircase'},
         {'section': 'staircase', 'key': 'step_duration', 'label': '每级持续(秒)', 'type': 'int', 'min': 1, 'max': 3600, 'show_if': 'staircase'},
         {'section': 'staircase', 'key': 'ramp_duration', 'label': '爬坡总时长', 'type': 'str', 'show_if': 'staircase',
          'help': '如 5m；到期后保持末档并发到总时长结束'},
         {'section': 'staircase', 'key': 'spawn_rate', 'label': '升档孵化速率(人/秒)', 'type': 'float', 'min': 0.1, 'max': 100000, 'show_if': 'staircase',
          'help': '建议 ≥ 每级增加并发 / 每级持续秒数，否则实际并发跟不上计划'},
     ]},
    {'group': '脉冲峰值参数', 'icon': '⚡', 'desc': 'mode=pulse 时生效：基准并发上周期性打瞬时尖峰',
     'fields': [
         {'section': 'pulse', 'key': 'baseline_users', 'label': '基准并发', 'type': 'int', 'min': 0, 'max': 100000, 'show_if': 'pulse'},
         {'section': 'pulse', 'key': 'peak_users', 'label': '尖峰并发', 'type': 'int', 'min': 0, 'max': 100000, 'show_if': 'pulse'},
         {'section': 'pulse', 'key': 'peak_duration', 'label': '尖峰持续(秒)', 'type': 'int', 'min': 1, 'max': 3600, 'show_if': 'pulse'},
         {'section': 'pulse', 'key': 'pulse_interval', 'label': '脉冲周期(秒)', 'type': 'int', 'min': 1, 'max': 36000, 'show_if': 'pulse',
          'help': '上一尖峰开始到下一尖峰开始的间隔；尖峰持续不应大于周期'},
         {'section': 'pulse', 'key': 'peak_spawn_rate', 'label': '尖峰孵化速率(人/秒)', 'type': 'float', 'min': 0.1, 'max': 100000, 'show_if': 'pulse'},
         {'section': 'pulse', 'key': 'baseline_spawn_rate', 'label': '基准孵化速率(人/秒)', 'type': 'float', 'min': 0.1, 'max': 100000, 'show_if': 'pulse'},
     ]},
    {'group': '请求细节', 'icon': '🌐', 'desc': '请求头、URL 参数、请求体与校验规则',
     'fields': [
         {'section': 'request', 'key': 'headers', 'label': '请求头', 'type': 'dict',
          'help': '每行一条：Header名: 值（鉴权、Content-Type 等）'},
         {'section': 'request', 'key': 'params', 'label': 'URL 参数', 'type': 'dict',
          'help': '每行一条：参数名: 值'},
         {'section': 'request', 'key': 'body', 'label': '请求体', 'type': 'text',
          'help': 'POST/PUT 使用；留空表示不带 body'},
         {'section': 'request', 'key': 'timeout', 'label': '请求超时(秒)', 'type': 'int', 'min': 1, 'max': 600},
         {'section': 'request', 'key': 'validate_status', 'label': '校验状态码(2xx 才计成功)', 'type': 'bool'},
     ]},
    {'group': '高级参数', 'icon': '🔧', 'desc': '低频项：保持默认即可跑通；调整前请先理解各项含义', 'advanced': True,
     'fields': [
         {'section': 'common', 'key': 'loop_count', 'label': '单用户循环次数', 'type': 'int', 'min': 0, 'max': 1000000,
          'help': '0 = 不限，持续跑到总时长结束'},
         {'section': 'common', 'key': 'wait_time_min', 'label': '思考时间下限(秒)', 'type': 'float', 'min': 0, 'max': 60,
          'help': '每次请求后的随机等待；建议 0.1~0.5 减轻压测机压力'},
         {'section': 'common', 'key': 'wait_time_max', 'label': '思考时间上限(秒)', 'type': 'float', 'min': 0, 'max': 60,
          'help': '须 ≥ 下限'},
         {'section': 'common', 'key': 'spawn_rate', 'label': '基础孵化速率(人/秒)', 'type': 'float', 'min': 0.1, 'max': 100000,
          'help': '加压策略未单独设速率时的兜底值'},
         {'section': 'request.dynamic_fields.random_user_id', 'key': 'enabled', 'label': '动态参数·启用随机替换', 'type': 'bool',
          'help': '每次请求自动替换随机值（如随机 userId），避免缓存/去重干扰压测'},
         {'section': 'request.dynamic_fields.random_user_id', 'key': 'field_name', 'label': '动态参数·替换字段', 'type': 'str',
          'help': '被替换的字段名，如 userId'},
         {'section': 'request.dynamic_fields.random_user_id', 'key': 'digits', 'label': '动态参数·随机数字位数', 'type': 'int', 'min': 1, 'max': 32},
         {'section': 'request.dynamic_fields.random_user_id', 'key': 'as_string', 'label': '动态参数·以字符串形式替换', 'type': 'bool'},
         {'section': 'report', 'key': 'output_path', 'label': '报告输出路径', 'type': 'str',
          'help': '相对 perf_test 目录，如 reports/load_test_report.html'},
         {'section': 'report', 'key': 'capture_response_body', 'label': '记录响应体样本', 'type': 'bool',
          'help': '报告中可查看「结果树」明细；关掉可省内存'},
         {'section': 'report', 'key': 'response_body_max_len', 'label': '响应体截断长度', 'type': 'int', 'min': 0, 'max': 100000},
         {'section': 'report', 'key': 'max_samples', 'label': '最大样本数', 'type': 'int', 'min': 1, 'max': 1000000,
          'help': '超过后停止记录明细（防大并发撑爆内存）'},
     ]},
]

_DURATION_RE = re.compile(r'^\d+(\.\d+)?(s|m|h)?$')


def _flat_key(section, key):
    return key if not section else '%s.%s' % (section, key)


def read_config():
    """读取当前生效配置：返回扁平 {section.key: value}（缺项用引擎默认值补齐）"""
    cfg = {}
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:      # 配置被手工改坏时不阻断页面：回退默认值，由保存时整体重写修复
            print('警告: 压测配置解析失败，已回退默认值（可在页面重新保存修复）: %s' % e)
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    values = {'mode': cfg.get('mode', 'staircase')}
    for group in SCHEMA:
        for f in group['fields']:
            if not f['section']:
                continue
            node = cfg
            for part in f['section'].split('.'):
                node = (node or {}).get(part, {}) if isinstance(node, dict) else {}
            v = node.get(f['key']) if isinstance(node, dict) else None
            if f['type'] == 'dict':
                values[_flat_key(f['section'], f['key'])] = v if isinstance(v, dict) else {}
            elif f['type'] == 'bool':
                values[_flat_key(f['section'], f['key'])] = bool(v) if v is not None else False
            else:
                values[_flat_key(f['section'], f['key'])] = v
    # 引擎默认值（无配置文件时给一份能直接跑的最小配置）
    if values.get('common.host') in (None, ''):
        values['common.host'] = 'http://127.0.0.1'
    if not values.get('common.run_time'):
        values['common.run_time'] = '1m'
    if values.get('request.method') not in METHODS:
        values['request.method'] = 'GET'          # 原工具配置里 method 为空，按 GET 兜底
    if not values.get('request.path'):
        values['request.path'] = '/'
    if not values.get('request.dynamic_fields.random_user_id.digits'):
        values['request.dynamic_fields.random_user_id.digits'] = 16
    if not values.get('request.dynamic_fields.random_user_id.field_name'):
        values['request.dynamic_fields.random_user_id.field_name'] = 'userId'
    if values.get('staircase.spawn_rate') is None:
        values['staircase.spawn_rate'] = 10
    if values.get('pulse.baseline_spawn_rate') is None:
        values['pulse.baseline_spawn_rate'] = 10
    if values.get('pulse.peak_spawn_rate') is None:
        values['pulse.peak_spawn_rate'] = 10
    return values


def validate(values):
    """校验扁平配置；返回 (ok, msg, 归一化后的值)"""
    norm = {}
    for group in SCHEMA:
        for f in group['fields']:
            fk = _flat_key(f['section'], f['key'])
            raw = values.get(fk)
            t = f['type']
            if t == 'dict':
                if isinstance(raw, str):
                    d = {}
                    for line in raw.splitlines():
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if ':' not in line:
                            return False, '%s 每行须为「名: 值」格式：%s' % (f['label'], line), None
                        k, v = line.split(':', 1)
                        d[k.strip()] = v.strip()
                    raw = d
                norm[fk] = raw if isinstance(raw, dict) else {}
                continue
            if t == 'bool':
                norm[fk] = bool(raw) if not isinstance(raw, str) else raw.strip().lower() in ('1', 'true', 'yes', 'on')
                continue
            if t == 'select':
                if raw not in f['options']:
                    return False, '%s 取值不合法：%s' % (f['label'], raw), None
                norm[fk] = raw
                continue
            if t in ('int', 'float'):
                try:
                    num = int(raw) if t == 'int' else float(raw)
                except (TypeError, ValueError):
                    return False, '%s 不是合法数字：%s' % (f['label'], raw), None
                if 'min' in f and num < f['min']:
                    return False, '%s 不能小于 %s' % (f['label'], f['min']), None
                if 'max' in f and num > f['max']:
                    return False, '%s 不能大于 %s' % (f['label'], f['max']), None
                norm[fk] = num
                continue
            # str / text
            norm[fk] = '' if raw is None else str(raw).strip() if t == 'str' else str(raw)
    if norm.get('common.wait_time_max', 0) < norm.get('common.wait_time_min', 0):
        return False, '思考时间上限不能小于下限', None
    rt = str(norm.get('common.run_time') or '')
    if rt and not _DURATION_RE.match(rt):
        return False, '总时长格式不合法（如 30s / 5m / 1h）：%s' % rt, None
    rd = str(norm.get('staircase.ramp_duration') or '')
    if rd and not _DURATION_RE.match(rd):
        return False, '爬坡时长格式不合法（如 5m）：%s' % rd, None
    host = str(norm.get('common.host') or '').strip()
    if not host:
        return False, '被测服务地址不能为空', None
    norm['common.host'] = host.rstrip('/')
    return True, '', norm


def _yaml_quote(v):
    s = str(v)
    if s == '' or re.search(r'[:#{}&*!|>%@`"\'\[\],]', s) or s.lower() in ('yes', 'no', 'true', 'false', 'null'):
        return '"%s"' % s.replace('\\', '\\\\').replace('"', '\\"')
    return s


def write_config(values):
    """校验并写入 YAML（保留分组注释）。返回 (ok, msg)"""
    ok, msg, norm = validate(values)
    if not ok:
        return False, msg
    ok, msg = _write_yaml(norm)
    return ok, msg


def _write_yaml(norm):
    def g(fk):
        return norm.get(fk)
    lines = [
        '# =============================================================================',
        '# HTTP 接口性能压测配置（由平台「⚡ 性能压测」页面维护，手工编辑请保持语法）',
        '# 模式：staircase 阶梯递增加压 / pulse 瞬时脉冲峰值',
        '# 依赖：perf_test/.venv（Python 3.13 + locust 2.x），与平台主环境隔离',
        '# =============================================================================',
        '',
        'mode: %s' % g('mode'),
        '',
        '# ------------------------------------------------------------------ 通用参数',
        'common:',
        '  host: %s' % _yaml_quote(g('common.host')),
        '  vu: %s' % g('common.vu'),
        '  run_time: %s' % _yaml_quote(g('common.run_time')),
        '  spawn_rate: %s' % g('common.spawn_rate'),
        '  loop_count: %s' % g('common.loop_count'),
        '  wait_time_min: %s' % g('common.wait_time_min'),
        '  wait_time_max: %s' % g('common.wait_time_max'),
        '',
        '# ------------------------------------------------------------------ 请求定义',
        'request:',
        '  path: %s' % _yaml_quote(g('request.path')),
        '  method: %s' % g('request.method'),
        '  timeout: %s' % g('request.timeout'),
        '  validate_status: %s' % ('true' if g('request.validate_status') else 'false'),
        '  headers:',
    ]
    headers = g('request.headers') or {}
    for k, v in headers.items():
        lines.append('    %s: %s' % (k, _yaml_quote(v)))
    lines.append('  params:')
    for k, v in (g('request.params') or {}).items():
        lines.append('    %s: %s' % (k, _yaml_quote(v)))
    body = g('request.body') or ''
    lines.append('  body: %s' % _yaml_quote(body))
    lines += [
        '  dynamic_fields:',
        '    random_user_id:',
        '      enabled: %s' % ('true' if g('request.dynamic_fields.random_user_id.enabled') else 'false'),
        '      field_name: %s' % _yaml_quote(g('request.dynamic_fields.random_user_id.field_name')),
        '      digits: %s' % g('request.dynamic_fields.random_user_id.digits'),
        '      as_string: %s' % ('true' if g('request.dynamic_fields.random_user_id.as_string') else 'false'),
        '',
        '# ------------------------------------------------------- 阶梯递增加压（staircase）',
        'staircase:',
        '  start_users: %s' % g('staircase.start_users'),
        '  step_users: %s' % g('staircase.step_users'),
        '  step_duration: %s' % g('staircase.step_duration'),
        '  ramp_duration: %s' % _yaml_quote(g('staircase.ramp_duration')),
        '  spawn_rate: %s' % g('staircase.spawn_rate'),
        '',
        '# ------------------------------------------------------- 瞬时脉冲峰值（pulse）',
        'pulse:',
        '  baseline_users: %s' % g('pulse.baseline_users'),
        '  peak_users: %s' % g('pulse.peak_users'),
        '  peak_duration: %s' % g('pulse.peak_duration'),
        '  pulse_interval: %s' % g('pulse.pulse_interval'),
        '  peak_spawn_rate: %s' % g('pulse.peak_spawn_rate'),
        '  baseline_spawn_rate: %s' % g('pulse.baseline_spawn_rate'),
        '',
        '# ------------------------------------------------------------------ 报告',
        'report:',
        '  output_path: %s' % _yaml_quote(g('report.output_path')),
        '  capture_response_body: %s' % ('true' if g('report.capture_response_body') else 'false'),
        '  response_body_max_len: %s' % g('report.response_body_max_len'),
        '  max_samples: %s' % g('report.max_samples'),
        '',
    ]
    try:
        yaml.safe_load('\n'.join(lines))   # 写前自检：语法必须可解析
    except Exception as e:
        return False, '生成内容非法，未落盘：%s' % e
    if not os.path.isdir(os.path.dirname(CONFIG_PATH)):
        os.makedirs(os.path.dirname(CONFIG_PATH))
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return True, '压测配置已保存（下次压测生效）'
