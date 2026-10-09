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

from web_platform.ai_case_analyzer import analyze_requirement
from web_platform.ai_case_device import (
    EVIDENCE_DIR, LOCK_TTL, acquire_lock, adb_devices, adb_hierarchy, adb_screenshot,
    get_lock, get_settings, release_lock, save_evidence, update_settings,
)
from web_platform.ai_case_maestro import friendly_error, get_maestro, maestro_available
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
    return _ok(projects=projects, devices=devices, device_note=device_note,
               model_configured=bool(os.environ.get('AI_CASE_MODEL_URL')),
               maestro=maestro_available(),
               settings=get_settings(),
               lock_ttl_min=LOCK_TTL // 60,
               entry_modes=[{'value': k, 'label': v} for k, v in ENTRY_MODE_LABELS.items()])


@bp.route('/api/ai-case/jobs', methods=['POST'])
def api_create_job():
    d = request.get_json(force=True, silent=True) or {}
    requirement = (d.get('requirement') or '').strip()
    entry_mode = d.get('entry_mode') or 'ai_explore'
    app_package = (d.get('app_package') or '').strip()
    if len(requirement) < 5:
        return _bad('需求描述太短：请描述测试场景与断言（至少 5 个字）')
    if entry_mode not in ENTRY_MODES:
        return _bad('入口模式不合法')
    if not app_package:
        return _bad('App 包名不能为空（从项目配置读取或手动填写，AI 不猜测包名）')

    project_name = None
    pid = d.get('project_id')
    if pid:
        p = _projects_store.get(int(pid))
        if p:
            project_name = p.get('name')

    job = _jobs_store.create({
        'requirement': requirement,
        'project_id': pid, 'project_name': project_name,
        'app_package': app_package,
        'device': (d.get('device') or '').strip(),
        'entry_mode': entry_mode,
        'status': '需求解析中',
        'analysis': None, 'clarifications': [], 'events': [],
    })
    _add_event(job, 'stage', '任务创建（ #%d ），开始解析需求' % job['id'])

    analysis = analyze_requirement(requirement, entry_mode)
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
    return send_file(path, mimetype='image/png', max_age=0)


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
