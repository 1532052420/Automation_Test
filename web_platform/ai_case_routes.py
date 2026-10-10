# -*- coding: utf-8 -*-
"""AI 用例生成（Maestro MCP + LangGraph 方案 · V1.1）

P1 已实现（本次）：
  - 首页卡片入口 /ai-case + 工作台页
  - 任务创建 + 需求解析（模型适配层优先、规则兜底）+ 状态机 + SSE 事件流
  - 澄清问题确认、任务取消、任务列表（草稿即任务记录，重开页面可恢复）
后续阶段（见 docs/ai_case_implementation.md 排期）：
  P2 接 Maestro MCP 真机探索与设备锁；P3 case_spec + 元素库映射；
  P4 Appium 试运行 + 三件套 ZIP 入库。

存储：复用平台 YamlStore（config/ai_case/ai_case_jobs.yaml），任务即草稿，刷新可恢复。
状态机（方案 3.3，P1 只走到「待探索」，其余节点由后续阶段推进）：
  需求解析中 → 待补充信息 / 待探索 →（后续：探索中 → 待确认入口 → … → 已生成用例包）
  任何阶段可 → 已取消
"""
import json
import os
import re
import time

from flask import Blueprint, Response, jsonify, render_template, request, send_file, stream_with_context

from web_platform.ai_case_analyzer import analyze_requirement, post_chat
from web_platform.ai_case_device import (
    EVIDENCE_DIR, LOCK_TTL, acquire_lock, adb_devices, adb_hierarchy, adb_screenshot,
    get_lock, get_settings, release_lock, save_evidence, update_settings,
)
from web_platform.ai_case_maestro import friendly_error, get_maestro, maestro_available
from web_platform.ai_case_prompts import DEFAULTS as PROMPT_DEFAULTS
from web_platform.ai_case_skills_default import DEFAULT_SKILLS
from web_platform.yaml_store import YamlStore

bp = Blueprint('ai_case', __name__)

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'config', 'ai_case')
APP_TESTING_DATA_DIR = os.path.join(BASE_DIR, 'config', 'app_testing')

# P1 终态只有「已取消」；后续阶段追加 已生成用例包 / 失败待处理
TERMINAL_STATUSES = ('已取消',)

ENTRY_MODES = ('ai_explore', 'current_page', 'manual')
ENTRY_MODE_LABELS = {
    'ai_explore': 'AI 探索入口',
    'current_page': '从当前页面开始',
    'manual': '我手动打开页面后设为入口',
}
# P1 状态全集（页面状态条展示用；打 * 的节点 P2+ 才会到达）
FLOW_STATUSES = ['需求解析中', '待补充信息', '待探索', '*探索中', '*待确认入口', '*生成步骤',
                 '*待定位', '*待验证', '*验证通过', '*已生成用例包']

_jobs_store = YamlStore('ai_case_jobs', data_dir=DATA_DIR)
_projects_store = YamlStore('projects', data_dir=APP_TESTING_DATA_DIR)
# P2.5 配置中心：模型 / 提示词 / Skill / AI 项目（项目+包名绑定）
_model_store = YamlStore('ai_case_model', data_dir=DATA_DIR)
_prompts_store = YamlStore('ai_case_prompts', data_dir=DATA_DIR)
_skills_store = YamlStore('ai_case_skills', data_dir=DATA_DIR)
_ai_projects_store = YamlStore('ai_case_projects', data_dir=DATA_DIR)
# Skill 本质是给模型读的 Markdown 文件（名称/触发时机/正文/启用）——文件库存储
_skill_files_store = YamlStore('ai_case_skill_files', data_dir=DATA_DIR)

MODEL_DEFAULTS = {'enabled': False, 'base_url': '', 'api_key': '', 'model': '', 'timeout': 20}
SKILLS_DEFAULTS = {
    'parser_mode': 'model',        # model=模型优先（失败回落规则）；rule=仅规则
    'explore_enabled': True,       # 真机探索技能（Maestro MCP）
    'element_search_enabled': True,  # 元素库检索技能（Platform MCP，P3 生效）
    'capture_link_enabled': True,  # 缺元素跳转定位器采集联动
    'dry_run_enabled': True,       # 试运行技能（Appium，P4 生效）
    'high_risk_policy': 'manual_confirm',  # 方案 8.6 铁律：只允许人工确认，不开放修改
    'default_project_id': None,    # 默认项目（携带 App 包名）
    'default_device': '',          # 默认设备 udid
}


def _single(store, defaults):
    items = store.list()
    if items:
        merged = dict(defaults)
        merged.update({k: v for k, v in items[0].items() if k in defaults or
                       k in ('name', 'app_package', 'note', 'customized')})
        return merged, items[0]
    return dict(defaults), None


def _get_model_cfg():
    cfg, _row = _single(_model_store, MODEL_DEFAULTS)
    return cfg


def _mask_key(key):
    if not key:
        return ''
    return '已设置（****' + key[-4:] + '）' if len(key) > 4 else '已设置'


def _get_prompts():
    merged = dict(PROMPT_DEFAULTS)
    row = _prompts_store.list()
    if row:
        merged.update({k: v for k, v in row[0].items() if k in PROMPT_DEFAULTS and v})
        merged['customized'] = True
    else:
        merged['customized'] = False
    return merged


def _get_skills():
    """执行视图：解析/设备等设置 + 技能启停（启停源自 Skill 文件库）"""
    cfg, _row = _single(_skills_store, SKILLS_DEFAULTS)
    files = {f['key']: f for f in _get_skill_files()}
    cfg['explore_enabled'] = files.get('explore', {}).get('enabled', True)
    cfg['element_search_enabled'] = files.get('mapping', {}).get('enabled', True)
    cfg['dry_run_enabled'] = files.get('dryrun', {}).get('enabled', True)
    limits = get_settings()
    cfg['max_steps'] = limits.get('max_steps')
    cfg['max_minutes'] = limits.get('max_minutes')
    return cfg


def _save_skills(patch):
    item = _skills_store.list()
    item = item[0] if item else _skills_store.create(dict(SKILLS_DEFAULTS))
    changed_limits = {}
    for k, v in (patch or {}).items():
        if k in ('max_steps', 'max_minutes'):
            changed_limits[k] = v
            continue
        if k == 'high_risk_policy':
            continue            # 方案 8.6 铁律：高风险策略锁定为人工确认，接口层也不可改
        if k == 'parser_mode':
            if v not in ('model', 'rule'):
                return None, 'parser_mode 只能是 model 或 rule'
            item[k] = v
        elif k == 'default_project_id':
            item[k] = int(v) if v not in (None, '', 'null') else None
        elif k in ('explore_enabled', 'element_search_enabled', 'dry_run_enabled'):
            # 旧开关键 → 映射到对应 Skill 文件的启停
            key = {'explore_enabled': 'explore',
                   'element_search_enabled': 'mapping',
                   'dry_run_enabled': 'dryrun'}[k]
            _save_skill_file(key, {'enabled': bool(v)})
        elif k in SKILLS_DEFAULTS:
            item[k] = v
    _skills_store.update(item['id'], item)
    if changed_limits:
        _, err = update_settings(changed_limits)
        if err:
            return None, err
    return _get_skills(), None


# ---------------- Skill 文件库（skill = 给模型读的 Markdown 文件） ----------------

def _get_skill_files():
    """默认技能 + 存储覆盖（按 key 合并）；返回列表保持内置顺序"""
    overrides = {o['key']: o for o in _skill_files_store.list()}
    out = []
    for d in DEFAULT_SKILLS:
        f = {'key': d['key'], 'name': d['name'], 'when': d['when'],
             'content': d['content'], 'enabled': d['enabled'], 'customized': False}
        o = overrides.get(d['key'])
        if o:
            f.update({k: v for k, v in o.items() if k in f and v is not None})
            f['customized'] = True
        out.append(f)
    return out


def _save_skill_file(key, patch):
    if key not in {d['key'] for d in DEFAULT_SKILLS}:
        return None, '未知技能: %s' % key
    row = None
    for o in _skill_files_store.list():
        if o['key'] == key:
            row = o
            break
    if row is None:
        base = next(d for d in DEFAULT_SKILLS if d['key'] == key)
        row = _skill_files_store.create({'key': key, 'name': base['name'], 'when': base['when'],
                                         'content': base['content'], 'enabled': base['enabled']})
    for k in ('name', 'when', 'content'):
        if k in (patch or {}):
            v = str(patch[k] or '').strip()
            if not v:
                return None, '%s 不能为空（可恢复默认）' % k
            if len(v) > 50000:
                return None, '%s 超长（>50000 字符）' % k
            row[k] = v
    if 'enabled' in (patch or {}):
        row['enabled'] = bool(patch['enabled'])
    _skill_files_store.update(row['id'], row)
    return row, None


def _ok(**payload):
    return jsonify(dict({'ok': True}, **payload))


def _bad(msg, code=400):
    return jsonify({'ok': False, 'msg': msg}), code


def _now():
    return int(time.time())


def _add_event(job, etype, msg):
    evs = job.setdefault('events', [])
    evs.append({'t': _now(), 'type': etype, 'msg': msg})
    if len(evs) > 200:
        del evs[:-200]


def _unanswered(job):
    return [c for c in job.get('clarifications') or [] if not c.get('answer')]


def _job_public(job, full=True):
    if not job:
        return None
    out = {
        'id': job['id'],
        'status': job.get('status'),
        'requirement': job.get('requirement'),
        'app_package': job.get('app_package'),
        'project_name': job.get('project_name'),
        'device': job.get('device'),
        'entry_mode': job.get('entry_mode'),
        'entry_mode_label': ENTRY_MODE_LABELS.get(job.get('entry_mode'), '-'),
        'created_at': job.get('created_at'),
        'updated_at': job.get('updated_at'),
    }
    if full:
        out.update({
            'analysis': job.get('analysis'),
            'clarifications': job.get('clarifications') or [],
            'events': (job.get('events') or [])[-60:],
            'flow_statuses': FLOW_STATUSES,
        })
    return out


def _list_adb_devices():
    devs, note = adb_devices()
    online = [d for d in devs if d['state'] == 'device']
    note = None if online else '当前无在线设备（adb devices 为空）；真机探索需先连接设备'
    return online, note


# ---------------- 页面 ----------------

@bp.route('/ai-case')
def ai_case_page():
    return render_template('ai_case.html')


# ---------------- API ----------------

@bp.route('/api/ai-case/config')
def api_config():
    projects = [{'id': p['id'], 'name': p.get('name') or ('项目%d' % p['id'])}
                for p in _projects_store.list()]
    devices, device_note = _list_adb_devices()
    for d in devices:
        d['lock'] = get_lock(d['udid'])
    ai_projects = [{'id': p['id'], 'name': p.get('name'), 'app_package': p.get('app_package')}
                   for p in _ai_projects_store.list()]
    skills = _get_skills()
    model = _get_model_cfg()
    model['api_key'] = _mask_key(model.get('api_key'))
    return _ok(projects=projects, devices=devices, device_note=device_note,
               ai_projects=ai_projects, model=model, prompts=_get_prompts(),
               skills=skills, skill_files=_get_skill_files(), maestro=maestro_available(),
               model_configured=bool(
                   os.environ.get('AI_CASE_MODEL_URL') or
                   (model.get('enabled') and model.get('base_url'))),
               lock_ttl_min=LOCK_TTL // 60,
               entry_modes=[{'value': k, 'label': v} for k, v in ENTRY_MODE_LABELS.items()])


@bp.route('/api/ai-case/jobs', methods=['POST'])
def api_create_job():
    d = request.get_json(force=True, silent=True) or {}
    requirement = (d.get('requirement') or '').strip()
    entry_mode = d.get('entry_mode') or 'ai_explore'
    if len(requirement) < 5:
        return _bad('需求描述太短：请描述测试场景与断言（至少 5 个字）')
    if entry_mode not in ENTRY_MODES:
        return _bad('入口模式不合法')

    # 包名 / 设备 / 项目：显式参数优先，否则取「配置项」里的默认项目与默认设备
    skills = _get_skills()
    app_package = (d.get('app_package') or '').strip()
    device = (d.get('device') or '').strip()
    project_id = d.get('project_id') or skills.get('default_project_id')
    project_name = None
    if project_id:
        try:
            p = _ai_projects_store.get(int(project_id))
        except (TypeError, ValueError):
            p = None
        if p:
            project_name = p.get('name')
            if not app_package:
                app_package = (p.get('app_package') or '').strip()
    if not device:
        device = skills.get('default_device') or ''
    if not app_package:
        return _bad('App 包名未配置：请在「配置项 → 项目与设备」绑定默认项目（含包名），'
                    '或显式传入 app_package')

    job = _jobs_store.create({
        'requirement': requirement,
        'project_id': project_id, 'project_name': project_name,
        'app_package': app_package,
        'device': device,
        'entry_mode': entry_mode,
        'status': '需求解析中',
        'analysis': None, 'clarifications': [], 'events': [],
    })
    _add_event(job, 'stage', '任务创建（ #%d ），开始解析需求' % job['id'])

    # Skill 决定解析技能：模型优先 / 仅规则；提示词取配置面板当前值；
    # 「需求解析技能」文件正文（若启用）拼进 system——skill 即模型加载的指令文件
    force_rule = skills.get('parser_mode') == 'rule'
    model_cfg = _get_model_cfg() if not force_rule else None
    prompts = _get_prompts()
    parse_skill = next((f for f in _get_skill_files() if f['key'] == 'parse'), None)
    if parse_skill and parse_skill.get('enabled'):
        prompts = dict(prompts)
        prompts['parse_system'] = (prompts['parse_system'] +
                                   '\n\n# 启用技能：' + parse_skill['name'] +
                                   '\n' + parse_skill['content'])
        _add_event(job, 'stage', '已加载技能文件「%s」%s' % (
            parse_skill['name'], '（自定义版）' if parse_skill.get('customized') else '（默认版）'))
    analysis = analyze_requirement(requirement, entry_mode, model_cfg=model_cfg,
                                   prompts=prompts, force_rule=force_rule)
    job['analysis'] = analysis
    job['clarifications'] = analysis.get('clarifications') or []
    _add_event(job, 'stage', '需求解析完成（%s）：步骤 %d · 断言 %d · 澄清 %d · 风险 %d' % (
        analysis.get('analyzer'), len(analysis.get('steps') or []),
        len(analysis.get('assertions') or []), len(job['clarifications']),
        len(analysis.get('risks') or [])))
    if _unanswered(job):
        job['status'] = '待补充信息'
        _add_event(job, 'clarification', '存在待澄清问题，等待人工确认（AI 不擅自编造缺失信息）')
    else:
        job['status'] = '待探索'
        _add_event(job, 'stage', '信息齐备，进入「待探索」（P2 接入 Maestro MCP 真机探索）')
    job = _jobs_store.update(job['id'], job)
    return _ok(job=_job_public(job))


@bp.route('/api/ai-case/jobs')
def api_list_jobs():
    limit = request.args.get('limit', type=int) or 0
    items = sorted(_jobs_store.list(), key=lambda j: -j['id'])
    if limit > 0:
        items = items[:limit]
    return _ok(results=[_job_public(j, full=False) for j in items])


@bp.route('/api/ai-case/jobs/<int:jid>')
def api_get_job(jid):
    job = _jobs_store.get(jid)
    if not job:
        return _bad('任务不存在', 404)
    return _ok(job=_job_public(job))


@bp.route('/api/ai-case/jobs/<int:jid>/clarifications', methods=['POST'])
def api_answer_clarifications(jid):
    job = _jobs_store.get(jid)
    if not job:
        return _bad('任务不存在', 404)
    if job.get('status') in TERMINAL_STATUSES:
        return _bad('任务已结束（%s）' % job['status'])
    d = request.get_json(force=True, silent=True) or {}
    answers = d.get('answers') or {}
    if not isinstance(answers, dict) or not answers:
        return _bad('answers 不能为空（{qid: 选项文本}）')
    answered = 0
    for c in job.get('clarifications') or []:
        if c['qid'] in answers and not c.get('answer'):
            c['answer'] = str(answers[c['qid']])[:200]
            c['answered_at'] = _now()
            answered += 1
            _add_event(job, 'human', '人工确认[%s]：%s' % (c['qid'], c['answer']))
    if not answered:
        return _bad('没有匹配到待澄清问题（或均已回答）')
    job['status'] = '待探索' if not _unanswered(job) else job['status']
    if job['status'] == '待探索':
        _add_event(job, 'stage', '信息齐备，进入「待探索」（P2 接入 Maestro MCP 真机探索）')
    job = _jobs_store.update(jid, job)
    return _ok(job=_job_public(job))


@bp.route('/api/ai-case/jobs/<int:jid>/cancel', methods=['POST'])
def api_cancel_job(jid):
    job = _jobs_store.get(jid)
    if not job:
        return _bad('任务不存在', 404)
    if job.get('status') in TERMINAL_STATUSES:
        return _bad('任务已结束（%s）' % job['status'])
    job['status'] = '已取消'
    _add_event(job, 'stage', '任务已取消（已生成内容保留，可重开查看）')
    job = _jobs_store.update(jid, job)
    _release_locks_for_job(jid)
    return _ok(job=_job_public(job))


def _release_locks_for_job(jid):
    """任务取消时释放其持有的设备锁（方案 7：失败也要交还设备）"""
    lock_dir = os.path.join(DATA_DIR, 'locks')
    if not os.path.isdir(lock_dir):
        return
    for fn in os.listdir(lock_dir):
        p = os.path.join(lock_dir, fn)
        try:
            with open(p, 'r', encoding='utf-8') as f:
                info = json.load(f)
            if info.get('job_id') == jid:
                os.remove(p)
        except Exception:
            continue


# ---------------- P2：设备观察 / 独占锁 / 设置 ----------------

def _udid_ok(udid):
    return bool(re.match(r'^[A-Za-z0-9_.:-]{1,64}$', udid or ''))


@bp.route('/api/ai-case/devices')
def api_devices():
    devs, note = _list_adb_devices()
    for d in devs:
        d['lock'] = get_lock(d['udid'])
    return _ok(devices=devs, device_note=note, maestro=maestro_available(),
               settings=get_settings())


@bp.route('/api/ai-case/observe/screenshot', methods=['POST'])
def api_observe_screenshot():
    udid = (request.get_json(force=True, silent=True) or {}).get('udid')
    if not _udid_ok(udid):
        return _bad('缺少或非法的 udid')
    source, note, png = 'maestro', None, None
    try:
        png = get_maestro().screenshot(udid)
    except Exception as e:
        note = friendly_error(e)
    if png is None:
        try:
            png = adb_screenshot(udid)
            source = 'adb-fallback'
        except Exception as e2:
            return _bad('截图失败：Maestro（%s）；adb 兜底（%s）' % (note or '不可用', e2))
    fn = save_evidence(udid, png)
    return _ok(image_url='/api/ai-case/evidence/%s/%s' % (udid, fn),
               source=source, ts=int(time.time()), note=note)


@bp.route('/api/ai-case/evidence/<udid>/<fname>')
def api_evidence(udid, fname):
    if not _udid_ok(udid) or not re.match(r'^[0-9A-Za-z_]+\.png$', fname):
        return _bad('非法路径'), 404
    path = os.path.join(EVIDENCE_DIR, udid, fname)
    if not os.path.exists(path):
        return _bad('截图不存在', 404)
    resp = send_file(path, mimetype='image/png')   # Flask 1.x 无 max_age 参数
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@bp.route('/api/ai-case/observe/hierarchy', methods=['POST'])
def api_observe_hierarchy():
    udid = (request.get_json(force=True, silent=True) or {}).get('udid')
    if not _udid_ok(udid):
        return _bad('缺少或非法的 udid')
    source, note, result = 'maestro', None, None
    try:
        result = get_maestro().hierarchy(udid)
    except Exception as e:
        note = friendly_error(e)
    if result is None:
        try:
            result = adb_hierarchy(udid)
            source = 'adb-fallback'
        except Exception as e2:
            return _bad('层级读取失败：Maestro（%s）；adb 兜底（%s）' % (note or '不可用', e2))
    if isinstance(result, list):
        clickable = [x for x in result if x.get('clickable')]
        texts = [x['text'] for x in result if x.get('text')]
        return _ok(source=source, note=note, elements=result,
                   summary={'nodes': len(result), 'clickable': len(clickable),
                            'texts': texts[:10]})
    # Maestro 原生层级结构未知形状：原样截断返回，前端显示节点计数
    dumped = json.dumps(result, ensure_ascii=False)
    return _ok(source=source, note=note, raw=dumped[:4000], summary={'nodes': dumped.count('{')})


@bp.route('/api/ai-case/devices/<udid>/lock', methods=['POST', 'DELETE'])
def api_device_lock(udid):
    if not _udid_ok(udid):
        return _bad('非法 udid')
    if request.method == 'DELETE':
        info = get_lock(udid)
        release_lock(udid)
        return _ok(released=bool(info), lock=None)
    body = request.get_json(force=True, silent=True) or {}
    try:
        jid = int(body['job_id']) if body.get('job_id') else None
    except (TypeError, ValueError):
        return _bad('job_id 不合法')
    info, err = acquire_lock(udid, job_id=jid, user=body.get('user') or 'web')
    if err:
        return _bad(err, 409)
    return _ok(lock=info)


@bp.route('/api/ai-case/settings', methods=['POST'])
def api_update_settings():
    d = request.get_json(force=True, silent=True) or {}
    s, err = update_settings(d)
    if err:
        return _bad(err)
    return _ok(settings=s)


# ---------------- P2.5：配置中心（模型 / 提示词 / Skill / AI 项目） ----------------

@bp.route('/api/ai-case/model-config', methods=['GET', 'PUT'])
def api_model_config():
    if request.method == 'GET':
        cfg = _get_model_cfg()
        cfg['api_key'] = _mask_key(cfg.get('api_key'))
        return _ok(model=cfg)
    d = request.get_json(force=True, silent=True) or {}
    cfg = _get_model_cfg()
    if 'enabled' in d:
        cfg['enabled'] = bool(d['enabled'])
    if 'base_url' in d:
        cfg['base_url'] = str(d['base_url'] or '').strip()
    if 'model' in d:
        cfg['model'] = str(d['model'] or '').strip()
    if 'timeout' in d:
        try:
            t = int(d['timeout'])
            if not 1 <= t <= 300:
                return _bad('timeout 必须是 1~300 秒')
            cfg['timeout'] = t
        except (TypeError, ValueError):
            return _bad('timeout 必须是整数秒')
    if 'api_key' in d:
        v = str(d['api_key'] or '').strip()
        if v == '__CLEAR__':
            cfg['api_key'] = ''
        elif v:                       # 空串=保持现有密钥不变（回显是脱敏值）
            cfg['api_key'] = v
    row = _model_store.list()
    row = row[0] if row else _model_store.create(dict(MODEL_DEFAULTS))
    _model_store.update(row['id'], cfg)
    cfg = _get_model_cfg()
    cfg['api_key'] = _mask_key(cfg.get('api_key'))
    return _ok(model=cfg)


@bp.route('/api/ai-case/model/test', methods=['POST'])
def api_model_test():
    """连通性测试：用已存配置或请求体覆盖配置，发一条最小对话"""
    d = request.get_json(force=True, silent=True) or {}
    cfg = _get_model_cfg()
    for k in ('base_url', 'model'):
        if d.get(k):
            cfg[k] = str(d[k]).strip()
    if d.get('api_key'):
        cfg['api_key'] = str(d['api_key']).strip()
    if d.get('timeout'):
        cfg['timeout'] = d['timeout']
    if not cfg.get('base_url'):
        return _bad('Base URL 未配置')
    try:
        reply, latency = post_chat(cfg, PROMPT_DEFAULTS['test_system'],
                                   PROMPT_DEFAULTS['test_user'])
        return _ok(latency_ms=latency, reply=(reply or '')[:120],
                   model=cfg.get('model'))
    except Exception as e:
        return _bad('模型调用失败：%s' % str(e)[:180], 502)


@bp.route('/api/ai-case/prompts', methods=['GET', 'PUT'])
def api_prompts():
    if request.method == 'GET':
        return _ok(prompts=_get_prompts())
    d = request.get_json(force=True, silent=True) or {}
    item = _prompts_store.list()
    item = item[0] if item else _prompts_store.create({})
    for k in ('parse_system', 'parse_user_template'):
        if k in d:
            v = str(d[k] or '').strip()
            if not v:
                return _bad('%s 不能为空（可点「恢复默认」）' % k)
            if len(v) > 20000:
                return _bad('%s 超长（>20000 字符）' % k)
            item[k] = v
    _prompts_store.update(item['id'], item)
    return _ok(prompts=_get_prompts())


@bp.route('/api/ai-case/prompts/reset', methods=['POST'])
def api_prompts_reset():
    row = _prompts_store.list()
    if row:
        _prompts_store.delete(row[0]['id'])
    return _ok(prompts=_get_prompts())


@bp.route('/api/ai-case/skill-files', methods=['GET'])
def api_skill_files():
    return _ok(results=_get_skill_files())


@bp.route('/api/ai-case/skill-files/<key>', methods=['PUT'])
def api_skill_file_put(key):
    row, err = _save_skill_file(key, request.get_json(force=True, silent=True) or {})
    if err:
        return _bad(err)
    files = {f['key']: f for f in _get_skill_files()}
    return _ok(skill=files.get(key))


@bp.route('/api/ai-case/skill-files/<key>/reset', methods=['POST'])
def api_skill_file_reset(key):
    if key not in {d['key'] for d in DEFAULT_SKILLS}:
        return _bad('未知技能', 404)
    for o in _skill_files_store.list():
        if o['key'] == key:
            _skill_files_store.delete(o['id'])
    files = {f['key']: f for f in _get_skill_files()}
    return _ok(skill=files.get(key))


@bp.route('/api/ai-case/skills', methods=['GET', 'PUT'])
def api_skills():
    if request.method == 'GET':
        return _ok(skills=_get_skills())
    s, err = _save_skills(request.get_json(force=True, silent=True) or {})
    if err:
        return _bad(err)
    return _ok(skills=s)


@bp.route('/api/ai-case/ai-projects', methods=['GET', 'POST'])
def api_ai_projects():
    if request.method == 'GET':
        return _ok(results=[{'id': p['id'], 'name': p.get('name'),
                             'app_package': p.get('app_package'), 'note': p.get('note')}
                            for p in _ai_projects_store.list()])
    d = request.get_json(force=True, silent=True) or {}
    name = (d.get('name') or '').strip()
    pkg = (d.get('app_package') or '').strip()
    if not name:
        return _bad('项目名称不能为空')
    if not re.match(r'^[A-Za-z][A-Za-z0-9_.]{3,100}$', pkg):
        return _bad('App 包名不合法（示例：com.example.app）')
    if any(x['name'] == name for x in _ai_projects_store.list()):
        return _bad('项目名称已存在: %s' % name)
    row = _ai_projects_store.create({'name': name[:60], 'app_package': pkg,
                                     'note': (d.get('note') or '').strip()[:200]})
    return _ok(project={'id': row['id'], 'name': name, 'app_package': pkg})


@bp.route('/api/ai-case/ai-projects/<int:pid>', methods=['PUT', 'DELETE'])
def api_ai_project_detail(pid):
    p = _ai_projects_store.get(pid)
    if not p:
        return _bad('项目不存在', 404)
    if request.method == 'DELETE':
        _ai_projects_store.delete(pid)
        skills = _get_skills()
        if skills.get('default_project_id') == pid:   # 默认项目被删则解绑
            _save_skills({'default_project_id': None})
        return _ok(msg='已删除')
    d = request.get_json(force=True, silent=True) or {}
    patch = {}
    if 'name' in d:
        name = (d['name'] or '').strip()
        if not name:
            return _bad('项目名称不能为空')
        patch['name'] = name[:60]
    if 'app_package' in d:
        pkg = (d['app_package'] or '').strip()
        if not re.match(r'^[A-Za-z][A-Za-z0-9_.]{3,100}$', pkg):
            return _bad('App 包名不合法（示例：com.example.app）')
        patch['app_package'] = pkg
    _ai_projects_store.update(pid, patch)
    return _ok(project=_ai_projects_store.get(pid))


@bp.route('/api/ai-case/jobs/<int:jid>/events')
def api_job_events(jid):
    """SSE：连接即推 snapshot，之后每次任务变化推 update；终态后自动收流"""
    def gen():
        last = None
        deadline = time.time() + 600
        yield 'retry: 3000\n\n'
        while time.time() < deadline:
            job = _jobs_store.get(jid)
            if not job:
                break
            data = json.dumps(_job_public(job), ensure_ascii=False)
            if data != last:
                last = data
                yield 'event: update\ndata: %s\n\n' % data
                if job.get('status') in TERMINAL_STATUSES:
                    break
            else:
                yield ': ping\n\n'
            time.sleep(1.2)
    return Response(stream_with_context(gen()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
