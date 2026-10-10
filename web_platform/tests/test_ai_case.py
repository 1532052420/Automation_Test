# -*- coding: utf-8 -*-
"""AI 用例生成（P1 需求解析 + P2 设备观察）· 单元/集成测试

覆盖 AAA 与全路径：正向 → 边界 → 异常 → 特殊场景。存储/锁/证据目录全部指向临时目录，
Maestro 与 adb 打桩，不碰真实数据与真机。
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest web_platform/tests/test_ai_case.py -q
"""
import base64
import json
import json as _json   # 别名：_fake_post 的形参 json 会遮蔽模块名
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from web_platform import ai_case_analyzer as AZ          # noqa: E402
from web_platform import ai_case_device as DEV           # noqa: E402
from web_platform import ai_case_routes as RT            # noqa: E402
from web_platform.ai_case_maestro import MaestroError    # noqa: E402
from web_platform.yaml_store import YamlStore            # noqa: E402

REQ_FULL = ('验证「发布歌曲」主流程：从「我的」进入「创作中心」，点击「发布歌曲」，'
            '输入歌名《测试之歌A1》，选择分类「流行」，点击发布。'
            '断言：出现「发布成功」提示；列表新增该歌曲。')

PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


class _FakeMaestro(object):
    """可编程桩：默认成功，用例可注入异常"""

    def __init__(self):
        self.err = None
        self.hier = {'nodes': []}

    def screenshot(self, udid):
        if self.err:
            raise self.err
        return PNG_1PX

    def hierarchy(self, udid):
        if self.err:
            raise self.err
        return self.hier


@pytest.fixture()
def fm(monkeypatch):
    fake = _FakeMaestro()
    monkeypatch.setattr(RT, 'get_maestro', lambda: fake)
    return fake


@pytest.fixture()
def client(tmp_path, monkeypatch, fm):
    """Flask 测试客户端：任务/配置中心/锁/证据目录全部指向临时目录"""
    d = str(tmp_path / 'ai_case')
    os.makedirs(d, exist_ok=True)
    RT._jobs_store = YamlStore('ai_case_jobs', data_dir=d)
    RT._projects_store = YamlStore('projects', data_dir=os.path.join(d, 'app_testing'))
    RT._model_store = YamlStore('ai_case_model', data_dir=d)
    RT._prompts_store = YamlStore('ai_case_prompts', data_dir=d)
    RT._skills_store = YamlStore('ai_case_skills', data_dir=d)
    RT._ai_projects_store = YamlStore('ai_case_projects', data_dir=d)
    monkeypatch.setattr(DEV._settings_store, 'path', os.path.join(d, 'ai_case_settings.yaml'))
    if not os.path.exists(DEV._settings_store.path):
        DEV._settings_store._write({'meta': {'next_id': 1}, 'items': []})
    monkeypatch.setattr(DEV, 'LOCK_DIR', os.path.join(d, 'locks'))
    monkeypatch.setattr(DEV, 'EVIDENCE_DIR', os.path.join(d, 'evidence'))
    monkeypatch.setattr(RT, 'EVIDENCE_DIR', os.path.join(d, 'evidence'))   # routes 按值导入，需同补
    monkeypatch.setattr(DEV, 'ADB', '/nonexistent/adb')   # adb 兜底必须走不通，强制走桩分支
    monkeypatch.setattr(RT, 'DATA_DIR', d)

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(RT.bp)
    app.config['TESTING'] = True
    return app.test_client()


def _mk_job(client, req=REQ_FULL, entry='ai_explore', pkg='com.demo.app', **kw):
    body = {'requirement': req, 'app_package': pkg, 'device': '', 'entry_mode': entry}
    body.update(kw)
    r = client.post('/api/ai-case/jobs', json=body).get_json()
    assert r['ok'], r
    return r['job']


# ============================================================
# 单元层：需求解析器（方案第一步）
# ============================================================

class TestAnalyzer(object):
    def test_parse_001_完整需求正向(self):
        # Act
        r = AZ.analyze_requirement(REQ_FULL, 'ai_explore')
        # Assert：6 步 / 2 断言 / 入口 / 风险
        assert [(s['action'], s['target']) for s in r['steps']] == [
            ('launch', 'App'), ('click', '创作中心'), ('click', '发布歌曲'),
            ('input', '歌名'), ('select', '流行'), ('click', '发布')]
        assert r['entry_path'] == ['我的', '创作中心']
        assert [(a['type'], a['target']) for a in r['assertions']] == [
            ('text_contains', '发布成功'), ('list_added', '列表新增该歌曲')]
        assert r['risks'] and r['analyzer'] == 'rule-fallback'

    def test_parse_002_无入口生成澄清_manual模式不生成入口澄清(self):
        # Arrange：需求不含「从X进入Y」
        req = '点击「登录」，输入「13800138000」。'
        # Act
        with_entry = AZ.analyze_requirement(req, 'ai_explore')
        manual = AZ.analyze_requirement(req, 'manual')
        # Assert
        qids = [c['qid'] for c in with_entry['clarifications']]
        assert 'entry' in qids
        assert 'entry' not in [c['qid'] for c in manual['clarifications']]

    def test_parse_003_有前置不生成前置澄清(self):
        r = AZ.analyze_requirement('前置：已登录会员账号。点击「搜索框」。', 'manual')
        assert r['preconditions'] == ['前置：已登录会员账号']
        assert 'precond' not in [c['qid'] for c in r['clarifications']]

    def test_parse_004_断言类型全族(self):
        r = AZ.analyze_requirement(
            '点击「删除」。断言：「测试之歌A1」不再出现；断言：视觉断言页面正常；'
            '断言：出现「删除成功」', 'manual')
        types = [a['type'] for a in r['assertions']]
        assert types == ['text_gone', 'visual', 'text_contains']

    def test_parse_005_边界_空需求不崩溃(self):
        for text in ('', '。。。；；', '断言：', '！'):
            r = AZ.analyze_requirement(text, 'ai_explore')   # Act
            assert isinstance(r.get('steps'), list)          # Assert
            assert isinstance(r.get('clarifications'), list)

    def test_parse_006_无步骤无断言给出提示(self):
        r = AZ.analyze_requirement('验证首页正常显示', 'current_page')
        assert any('识别出操作步骤' in n for n in r['notes'])
        assert any('断言' in n for n in r['notes'])

    def test_parse_007_高风险词全部标记(self):
        r = AZ.analyze_requirement('点击「发布」，点击「删除」，点击「支付」', 'manual')
        words = {x['word'] for x in r['risks']}
        assert {'发布', '删除', '支付'} <= words

    def test_model_008_未配置模型走兜底(self, monkeypatch):
        monkeypatch.delenv('AI_CASE_MODEL_URL', raising=False)
        r = AZ.analyze_requirement(REQ_FULL, 'ai_explore')   # Act
        assert r['analyzer'] == 'rule-fallback'              # Assert
        assert r['model_attempted'] is False

    def test_model_009_模型失败自动兜底不抛出(self, monkeypatch):
        monkeypatch.setenv('AI_CASE_MODEL_URL', 'http://127.0.0.1:1/nope')
        monkeypatch.setenv('AI_CASE_MODEL_TIMEOUT', '1')
        r = AZ.analyze_requirement(REQ_FULL, 'ai_explore')   # Act：连接拒绝
        assert r['analyzer'] == 'rule-fallback'              # Assert
        assert r['model_attempted'] is True

    def test_model_010_模型合法输出被采用(self, monkeypatch):
        class _Resp(object):
            def raise_for_status(self):
                pass

            def json(self):
                return {'analysis': {
                    'goal': '模型目标', 'steps': [{'sid': 'S1', 'action': 'click', 'target': 'X'}],
                    'assertions': [], 'clarifications': [{'qid': 'q1', 'question': '?',
                                                          'options': ['a'], }],
                    'risks': [], 'notes': []}}

        monkeypatch.setenv('AI_CASE_MODEL_URL', 'http://model.fake')
        monkeypatch.setenv('AI_CASE_MODEL_NAME', 'glm-test')
        monkeypatch.setattr(AZ.requests, 'post', lambda *a, **kw: _Resp())
        r = AZ.analyze_requirement(REQ_FULL, 'ai_explore')   # Act
        assert r['analyzer'] == 'model:glm-test'             # Assert
        assert r['clarifications'][0]['answer'] is None      # 澄清被补全默认字段

    def test_model_011_模型输出非法走兜底(self, monkeypatch):
        class _Resp(object):
            def raise_for_status(self):
                pass

            def json(self):
                return {'analysis': '不是字典'}

        monkeypatch.setenv('AI_CASE_MODEL_URL', 'http://model.fake')
        monkeypatch.setattr(AZ.requests, 'post', lambda *a, **kw: _Resp())
        r = AZ.analyze_requirement(REQ_FULL, 'ai_explore')   # Act
        assert r['analyzer'] == 'rule-fallback'              # Assert


# ============================================================
# 集成层：任务 API（Flask test client，存储隔离）
# ============================================================

class TestJobsAPI(object):
    def test_job_001_创建正向_带入口无澄清直接待探索(self, client):
        req = '前置：已登录。从「我的」进入「创作中心」，点击「发布歌曲」。断言：出现「发布成功」'
        job = _mk_job(client, req=req)                       # Act
        assert job['status'] == '待探索'                      # Assert
        assert job['clarifications'] == []
        assert job['analysis']['steps']

    def test_job_002_创建正向_无入口转待补充信息(self, client):
        job = _mk_job(client)                                # Act（REQ_FULL 无前置）
        assert job['status'] == '待补充信息'
        assert {c['qid'] for c in job['clarifications']} == {'precond'}

    def test_job_003_边界_短需求拒绝(self, client):
        r = client.post('/api/ai-case/jobs', json={
            'requirement': '短', 'app_package': 'com.x'}).get_json()
        assert not r['ok'] and '太短' in r['msg']

    def test_job_004_边界_空包名拒绝(self, client):
        r = client.post('/api/ai-case/jobs', json={
            'requirement': REQ_FULL, 'app_package': ''}).get_json()
        assert not r['ok'] and '包名' in r['msg']

    def test_job_005_异常_非法入口模式拒绝(self, client):
        r = client.post('/api/ai-case/jobs', json={
            'requirement': REQ_FULL, 'app_package': 'com.x', 'entry_mode': 'hack'}).get_json()
        assert not r['ok'] and '入口模式' in r['msg']

    def test_job_006_异常_非JSON请求体(self, client):
        r = client.post('/api/ai-case/jobs', data='not-json',
                        content_type='application/json').get_json()
        assert not r['ok']

    def test_job_007_澄清确认推进到待探索(self, client):
        job = _mk_job(client)                                # Arrange
        r = client.post('/api/ai-case/jobs/%d/clarifications' % job['id'],
                        json={'answers': {'precond': '设备上已登录测试账号，直接继续'}}).get_json()
        assert r['ok'] and r['job']['status'] == '待探索'     # Assert
        assert r['job']['clarifications'][0]['answered_at']

    def test_job_008_异常_重复澄清拒绝(self, client):
        job = _mk_job(client)                                # Arrange：先答一次
        url = '/api/ai-case/jobs/%d/clarifications' % job['id']
        client.post(url, json={'answers': {'precond': 'a'}})
        r = client.post(url, json={'answers': {'precond': 'b'}}).get_json()
        assert not r['ok'] and '均已回答' in r['msg']         # Act+Assert：再答

    def test_job_009_异常_未知qid与空answers(self, client):
        job = _mk_job(client)
        r1 = client.post('/api/ai-case/jobs/%d/clarifications' % job['id'],
                         json={'answers': {'nope': 'x'}}).get_json()
        r2 = client.post('/api/ai-case/jobs/%d/clarifications' % job['id'],
                         json={'answers': {}}).get_json()
        assert not r1['ok'] and not r2['ok']

    def test_job_010_取消正向_重复取消_404(self, client):
        job = _mk_job(client)
        r1 = client.post('/api/ai-case/jobs/%d/cancel' % job['id']).get_json()
        r2 = client.post('/api/ai-case/jobs/%d/cancel' % job['id']).get_json()
        r3 = client.post('/api/ai-case/jobs/99999/cancel').get_json()
        assert r1['job']['status'] == '已取消'
        assert not r2['ok'] and not r3['ok']

    def test_job_011_取消联动释放设备锁(self, client, tmp_path):
        job = _mk_job(client)                                # Arrange：任务持锁
        info, err = DEV.acquire_lock('udid-X', job_id=job['id'])
        assert info and not err
        # Act
        client.post('/api/ai-case/jobs/%d/cancel' % job['id'])
        # Assert：锁被联动释放
        assert DEV.get_lock('udid-X') is None

    def test_job_012_列表与详情_404_非法id(self, client):
        _mk_job(client)
        _mk_job(client)
        lst = client.get('/api/ai-case/jobs').get_json()
        assert len(lst['results']) == 2 and lst['results'][0]['id'] > lst['results'][1]['id']
        assert len(client.get('/api/ai-case/jobs?limit=1').get_json()['results']) == 1
        assert not client.get('/api/ai-case/jobs/99999').get_json()['ok']
        # 非法 id 不匹配 int 路由 → Flask 标准 404
        assert client.get('/api/ai-case/jobs/abc').status_code == 404

    def test_job_013_事件流随动作累积(self, client):
        job = _mk_job(client)                                # Arrange
        base = len(job['events'])
        client.post('/api/ai-case/jobs/%d/clarifications' % job['id'],
                    json={'answers': {'precond': 'x'}})
        job2 = client.get('/api/ai-case/jobs/%d' % job['id']).get_json()['job']
        assert len(job2['events']) > base                    # Assert
        assert any(e['type'] == 'human' for e in job2['events'])


# ============================================================
# 集成层：设备观察 / 独占锁 / 设置 / 证据（P2）
# ============================================================

class TestDeviceAPI(object):
    def test_dev_001_锁正向_互斥_释放(self, client):
        r1 = client.post('/api/ai-case/devices/udid-1/lock', json={'job_id': None}).get_json()
        r2 = client.post('/api/ai-case/devices/udid-1/lock', json={'job_id': None}).get_json()
        r3 = client.delete('/api/ai-case/devices/udid-1/lock').get_json()
        r4 = client.post('/api/ai-case/devices/udid-1/lock', json={'job_id': None}).get_json()
        assert r1['ok'] and not r2['ok'] and '锁定' in r2['msg']
        assert r3['ok'] and r4['ok']

    def test_dev_002_异常_非法udid(self, client):
        r = client.post('/api/ai-case/devices/%s/lock' % ('x' * 80), json={}).get_json()
        assert not r['ok']

    def test_dev_003_截图正向_Maestro通道(self, client, fm):
        r = client.post('/api/ai-case/observe/screenshot',
                        json={'udid': 'udid-1'}).get_json()
        assert r['ok'] and r['source'] == 'maestro'
        img = client.get(r['image_url'])
        assert img.status_code == 200 and img.data.startswith(b'\x89PNG')

    def test_dev_004_截图_Maestro失败且无adb兜底_友好报错不挂起(self, client, fm):
        fm.err = MaestroError('Device with id x is not connected')
        r = client.post('/api/ai-case/observe/screenshot', json={'udid': 'udid-1'}).get_json()
        assert not r['ok']
        assert '设备未连接' in r['msg'] and '截图失败' in r['msg']

    def test_dev_005_层级正向_摘要统计(self, client, fm):
        fm.hier = [{'text': '发布', 'rid': 'btn', 'clickable': True}] * 3
        r = client.post('/api/ai-case/observe/hierarchy', json={'udid': 'udid-1'}).get_json()
        assert r['ok'] and r['source'] == 'maestro'
        assert r['summary']['nodes'] == 3 and r['summary']['clickable'] == 3

    def test_dev_006_异常_观察缺udid(self, client):
        r1 = client.post('/api/ai-case/observe/screenshot', json={}).get_json()
        r2 = client.post('/api/ai-case/observe/hierarchy', json={}).get_json()
        assert not r1['ok'] and not r2['ok']

    def test_dev_007_证据路径非法_404(self, client):
        assert client.get('/api/ai-case/evidence/udid-1/../etc.png').status_code == 404
        assert client.get('/api/ai-case/evidence/udid-1/nope.png').status_code == 404

    def test_dev_008_设置_正向与边界(self, client):
        r1 = client.post('/api/ai-case/settings', json={'max_steps': 30}).get_json()
        assert r1['settings']['max_steps'] == 30
        for bad in ({'max_steps': 0}, {'max_steps': 201}, {'max_steps': 'abc'}, {'max_minutes': -1}):
            assert not client.post('/api/ai-case/settings', json=bad).get_json()['ok']

    def test_dev_009_config_包含全部配置段(self, client):
        r = client.get('/api/ai-case/config').get_json()
        assert r['ok']
        for key in ('projects', 'devices', 'entry_modes', 'skills', 'model',
                    'prompts', 'ai_projects', 'maestro', 'model_configured'):
            assert key in r
        assert len(r['entry_modes']) == 3


# ============================================================
# 集成层：配置中心（模型 / 提示词 / Skill / AI 项目）
# ============================================================

class _FakeResp(object):
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class TestConfigAPI(object):
    def test_cfg_001_模型配置_保存回显脱敏_空key不改(self, client):
        r1 = client.put('/api/ai-case/model-config', json={
            'enabled': True, 'base_url': 'https://api.fake/v4/chat/completions',
            'api_key': 'sk-secret-abcd1234', 'model': 'glm-4.7', 'timeout': 30}).get_json()
        assert r1['ok'] and r1['model']['enabled'] is True
        assert '****1234' in r1['model']['api_key'] and 'secret' not in r1['model']['api_key']
        # 空串 = 保持现有密钥
        r2 = client.put('/api/ai-case/model-config', json={'model': 'glm-5'}).get_json()
        assert '****1234' in r2['model']['api_key'] and r2['model']['model'] == 'glm-5'
        # __CLEAR__ = 清除
        r3 = client.put('/api/ai-case/model-config', json={'api_key': '__CLEAR__'}).get_json()
        assert r3['model']['api_key'] == ''

    def test_cfg_002_模型配置_超时边界(self, client):
        assert client.put('/api/ai-case/model-config', json={'timeout': 0}).get_json()['ok'] is False
        assert client.put('/api/ai-case/model-config', json={'timeout': 301}).get_json()['ok'] is False
        assert client.put('/api/ai-case/model-config', json={'timeout': 60}).get_json()['ok']

    def test_cfg_003_模型测试连接_失败路径(self, client, monkeypatch):
        monkeypatch.setattr(RT, 'post_chat', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('连接拒绝')))
        r = client.post('/api/ai-case/model/test', json={
            'base_url': 'https://api.fake', 'api_key': 'k', 'model': 'm'}).get_json()
        assert not r['ok'] and '模型调用失败' in r['msg']

    def test_cfg_004_模型测试连接_成功路径(self, client, monkeypatch):
        monkeypatch.setattr(RT, 'post_chat', lambda *a, **kw: ('OK', 123))
        r = client.post('/api/ai-case/model/test', json={
            'base_url': 'https://api.fake', 'model': 'm'}).get_json()
        assert r['ok'] and r['latency_ms'] == 123 and r['reply'] == 'OK'

    def test_cfg_005_提示词_默认_保存_空拒绝_重置(self, client):
        d0 = client.get('/api/ai-case/prompts').get_json()['prompts']
        assert d0['customized'] is False and '资深' in d0['parse_system']
        r = client.put('/api/ai-case/prompts', json={
            'parse_system': '自定义系统提示词', 'parse_user_template': '需求：{requirement}'}).get_json()
        assert r['prompts']['customized'] is True and r['prompts']['parse_system'] == '自定义系统提示词'
        bad = client.put('/api/ai-case/prompts', json={'parse_system': ''}).get_json()
        assert not bad['ok']
        rs = client.post('/api/ai-case/prompts/reset', json={}).get_json()
        assert rs['prompts']['customized'] is False and '资深' in rs['prompts']['parse_system']

    def test_cfg_006_skills_解析模式校验与上限别名(self, client):
        r = client.put('/api/ai-case/skills', json={'parser_mode': 'hack'}).get_json()
        assert not r['ok']
        r2 = client.put('/api/ai-case/skills', json={
            'parser_mode': 'rule', 'max_steps': 25, 'explore_enabled': False}).get_json()
        assert r2['skills']['parser_mode'] == 'rule' and r2['skills']['max_steps'] == 25
        assert r2['skills']['explore_enabled'] is False
        # 旧 settings 接口与 skills 上限同源
        assert client.get('/api/ai-case/config').get_json()['skills']['max_steps'] == 25

    def test_cfg_007_高风险策略锁定不可改(self, client):
        r = client.put('/api/ai-case/skills', json={'high_risk_policy': 'auto'}).get_json()
        assert r['skills']['high_risk_policy'] == 'manual_confirm'

    def test_cfg_008_AI项目_增删改查与包名校验(self, client):
        r1 = client.post('/api/ai-case/ai-projects', json={
            'name': '云音乐 demo', 'app_package': 'com.netease.demo'}).get_json()
        assert r1['ok'] and r1['project']['id']
        bad = client.post('/api/ai-case/ai-projects', json={
            'name': '坏包名', 'app_package': '不是包名'}).get_json()
        assert not bad['ok']
        dup = client.post('/api/ai-case/ai-projects', json={
            'name': '云音乐 demo', 'app_package': 'com.x.y'}).get_json()
        assert not dup['ok'] and '已存在' in dup['msg']
        up = client.put('/api/ai-case/ai-projects/%d' % r1['project']['id'],
                        json={'app_package': 'com.netease.demo2'}).get_json()
        assert up['project']['app_package'] == 'com.netease.demo2'
        dl = client.delete('/api/ai-case/ai-projects/%d' % r1['project']['id']).get_json()
        assert dl['ok']

    def test_cfg_009_创建任务消费默认项目与设备(self, client):
        pid = client.post('/api/ai-case/ai-projects', json={
            'name': '云音乐', 'app_package': 'com.netease.demo'}).get_json()['project']['id']
        client.put('/api/ai-case/skills', json={
            'default_project_id': pid, 'default_device': 'emu-1'})
        # 不传 app_package / device → 自动带出
        job = _mk_job(client, req='前置：已登录。点击「登录」。断言：出现「首页」', pkg=None)
        assert job['app_package'] == 'com.netease.demo'
        assert job['device'] == 'emu-1' and job['project_name'] == '云音乐'

    def test_cfg_010_未绑定默认项目且未传包名_拒绝并指路配置项(self, client):
        r = client.post('/api/ai-case/jobs', json={
            'requirement': REQ_FULL, 'entry_mode': 'manual'}).get_json()
        assert not r['ok'] and '配置项' in r['msg']

    def test_cfg_011_skill仅规则_不调用模型(self, client, monkeypatch):
        client.put('/api/ai-case/skills', json={'parser_mode': 'rule'})
        called = []

        def _boom(*a, **kw):
            called.append(1)
            raise RuntimeError('不应调用模型')

        monkeypatch.setattr(AZ.requests, 'post', _boom)
        monkeypatch.setenv('AI_CASE_MODEL_URL', 'http://model.fake')
        job = _mk_job(client)                                # Act：rule 模式即使 env 有模型也不调
        assert called == [] and job['analysis']['analyzer'] == 'rule-fallback'
        assert job['analysis']['model_attempted'] is False

    def test_cfg_012_skill模型优先_解析经chat通道(self, client, monkeypatch):
        client.put('/api/ai-case/skills', json={'parser_mode': 'model'})
        client.put('/api/ai-case/model-config', json={
            'enabled': True, 'base_url': 'https://api.fake/chat',
            'api_key': 'k1', 'model': 'glm-test'})

        def _fake_post(url, json=None, headers=None, timeout=None, **kw):
            assert 'api.fake' in url
            content = _json.dumps({'goal': '模型目标',
                                   'steps': [{'sid': 'S1', 'action': 'click', 'target': '登录'}],
                                   'assertions': [], 'clarifications': [], 'risks': [], 'notes': []},
                                  ensure_ascii=False)
            return _FakeResp({'choices': [{'message': {'content': content}}]})

        monkeypatch.setattr(AZ.requests, 'post', _fake_post)
        job = _mk_job(client, req='前置：已登录。点击「登录」。断言：出现「首页」', entry='manual')
        assert job['analysis']['analyzer'] == 'model:glm-test'
        assert job['analysis']['goal'] == '模型目标'


# ============================================================
# 特殊场景：状态机全链（创建→澄清→取消）与幂等
# ============================================================

class TestFlow(object):
    def test_flow_001_全链_创建到取消可重复执行(self, client):
        for _ in range(2):                                   # Act：同一用例跑两遍（幂等）
            job = _mk_job(client, req='前置：已登录。点击「登录」。断言：出现「首页」',
                          entry='manual')
            assert job['status'] == '待探索'
            r = client.post('/api/ai-case/jobs/%d/cancel' % job['id']).get_json()
            assert r['job']['status'] == '已取消'

    def test_flow_002_取消后不能再澄清(self, client):
        job = _mk_job(client)                                # Arrange
        client.post('/api/ai-case/jobs/%d/cancel' % job['id'])
        r = client.post('/api/ai-case/jobs/%d/clarifications' % job['id'],
                        json={'answers': {'precond': 'x'}}).get_json()
        assert not r['ok'] and '已结束' in r['msg']
