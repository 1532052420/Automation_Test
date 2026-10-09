# -*- coding: utf-8 -*-
"""AI 用例生成 · 需求解析器

两级实现（对应《AI 用例生成模块技术方案》V1.1 第一步「解析需求」）：
1. 模型适配层：环境变量配置了 AI_CASE_MODEL_URL 时优先调用模型服务（结构化 JSON 输出），
   密钥只走环境变量，不进代码/前端；
2. 规则兜底：未配置模型或模型输出不合法时，退回中文关键词规则解析——
   能力有限，结果一律标注 analyzer='rule-fallback'，步骤/断言等全部视为待人工确认，
   绝不把兜底结果伪装成模型结论（方案 8.4：不允许"模型认为通过"式的造假）。

铁律：需求没写明的业务规则不编造；信息不足生成澄清问题（clarifications），
而不是直接生成已确认状态的正式步骤。
"""
import os
import re

# 高风险业务关键词（方案 8.6：探索阶段默认禁止自动提交，仅标记提醒）
RISK_WORDS = ('发布', '删除', '支付', '购买', '下单', '发帖', '转账', '提交订单')

ACTION_VERB_MAP = (
    ('启动', 'launch'), ('打开 App', 'launch'), ('打开APP', 'launch'), ('打开应用', 'launch'),
    ('点击', 'click'), ('点按', 'click'), ('按下', 'click'), ('长按', 'click'),
    ('输入', 'input'), ('填写', 'input'),
    ('选择', 'select'), ('勾选', 'select'), ('选中', 'select'),
    ('进入', 'click'), ('切换到', 'click'),
)

_SPLIT_RE = re.compile(r'[。；;！？\n]+')
_SUB_RE = re.compile(r'[，,]+')
_QUOTED_RE = re.compile(r'「([^」]+)」')
_ENTRY_RE = re.compile(r'从[「]?([^」，。；;；\n]+)[」]?进入[「]?([^」，。；;；\n]+)[」]?')


def _clauses(text):
    return [c.strip() for c in _SPLIT_RE.split(text or '') if c.strip()]


def _quoted_in(after):
    m = re.search(r'[「《]([^」》]+)[」》]', after)
    return m.group(1).strip() if m else None


def _clean_tail(after):
    """动词后的文本 → 目标描述（到逗号/「后」为止，去引号残留）"""
    tail = re.split(r'[，,、]|之后?$|以后$', after)[0]
    return tail.strip(' 「」了的了：:').strip()


def _parse_action(clause):
    """子句 → (动作, 目标, 值)；目标锚定在第一个动作动词之后；识别不出返回 None"""
    low = clause.replace(' ', '')
    if re.search(r'启动|打开(APP|App|应用)', low):
        return 'launch', _quoted_in(clause) or 'App', None
    best = None
    for verb, act in ACTION_VERB_MAP:
        idx = low.find(verb)
        if idx < 0:
            continue
        if best is None or idx < best[0]:
            best = (idx, verb, act)
    if best is None:
        return None
    idx, verb, act = best
    after = low[idx + len(verb):]
    quoted = _quoted_in(after)
    value = None
    if act == 'input':
        value = quoted
        target = re.sub(r'[「《][^」》]*[」》]', '', after)
        target = _clean_tail(target)[:16] or '输入框'
    else:
        target = quoted or _clean_tail(after)[:16]
    if not target:
        return None
    return act, target, value


def _parse_assertion(clause, force=False):
    """断言子句 → {type, target, raw}；识别不出返回 None。
    force=True 用于断言句内的逗号分段（首段带「断言：」，后续段不带）。"""
    if '断言' not in clause and not clause.startswith('预期'):
        if not force:
            return None
        if not re.search(r'出现|提示|展示|新增|不再|视觉|截图', clause):
            return None
    target = _quoted_in(clause)
    low = clause.replace(' ', '')
    if '不再出现' in low or '不再包含' in low:
        atype = 'text_gone'
        target = target or _clean_tail(low.split('不再出现', 1)[-1] if '不再出现' in low
                                       else low.split('不再包含', 1)[-1])[:16]
    elif re.search(r'列表.{0,6}新增|新增', low):
        atype = 'list_added'
        target = target or clause[:16]
    elif '视觉' in low or '截图' in low:
        atype = 'visual'
    elif '出现' in low or '提示' in low or '展示' in low:
        atype = 'text_contains'
        if not target:
            m = re.search(r'(?:出现|提示|展示)[「]?([^」，。;；]+)', low)
            target = (m.group(1).strip(' 「」') if m else None) or low[:16]
    else:
        return None
    return {'type': atype, 'target': target or '（未写明，需确认）', 'raw': clause}


def _rule_analyze(text, entry_mode):
    clauses = _clauses(text)
    steps, assertions, preconditions, risks, notes = [], [], [], [], []

    entry_path = None
    m = _ENTRY_RE.search(text)
    if m:
        entry_path = [m.group(1).strip(), m.group(2).strip()]

    sid = 0

    def add_step(action, target, value, raw, source):
        nonlocal sid
        if action != 'launch' and not any(s['action'] == 'launch' for s in steps):
            sid += 1
            steps.append({'sid': 'S%d' % sid, 'action': 'launch', 'target': 'App',
                          'value': None, 'raw': '（推断）进入需求场景前先启动应用', 'source': 'inferred'})
        sid += 1
        steps.append({'sid': 'S%d' % sid, 'action': action, 'target': target, 'value': value,
                      'raw': raw, 'source': source})

    prev_assert = False
    for sent in clauses:
        # 断言句：整句按逗号再分段，逐段识别（首段带「断言：」，后续段不带也能识别）；
        # 紧跟断言句之后的续句（如「；列表新增该歌曲」无「断言」前缀）按断言继续识别
        is_assert = '断言' in sent or sent.startswith('预期') or \
            (prev_assert and re.search(r'出现|提示|展示|新增|不再|视觉|截图', sent))
        if is_assert:
            prev_assert = True
            for seg in _SUB_RE.split(sent):
                a = _parse_assertion(seg.strip(), force=True)
                if a:
                    assertions.append(a)
            continue
        prev_assert = False
        # 操作句：按逗号切子段，逐段识别动作（一条需求常逗号连写多个动作）
        for sub in _SUB_RE.split(sent):
            sub = sub.strip()
            if not sub:
                continue
            low = sub.replace(' ', '')
            if re.match(r'^(前置|前提|已登录|账号)', low):
                preconditions.append(sub)
                continue
            act = _parse_action(sub)
            if not act:
                continue
            action, target, value = act
            add_step(action, target, value, sub, 'requirement')
            for w in RISK_WORDS:
                if w in low and action in ('click', 'select'):
                    risks.append({'level': 'high', 'word': w, 'clause': sub,
                                  'note': '疑似业务写入动作：探索/试运行阶段不自动提交，需人工确认（方案 8.6）'})
                    break

    clarifications = []
    if entry_mode == 'ai_explore' and not entry_path:
        clarifications.append({
            'qid': 'entry', 'question': '需求未写明入口路径，如何确定探索起点？',
            'options': ['我手动打开页面后设为入口', '从设备当前页面开始', 'AI 从应用首页自动探索'],
            'answer': None, 'answered_at': None,
        })
    if not preconditions:
        clarifications.append({
            'qid': 'precond', 'question': '需求未写明前置条件（登录账号 / 测试环境），如何处理？',
            'options': ['设备上已登录测试账号，直接继续', '探索前我先在设备上手动登录', '无账号前置，跳过'],
            'answer': None, 'answered_at': None,
        })
    if not steps:
        notes.append('未能从需求中识别出操作步骤：请用「点击／输入／选择／断言：…」等动宾句式描述')
    if not assertions:
        notes.append('需求未包含断言：生成的用例将只有操作步骤，建议补充「断言：出现／不再出现／列表新增…」')

    goal = ''
    for c in clauses:
        if not _parse_assertion(c):
            goal = re.sub(r'^(验证|测试一下|测试)', '', c).strip()
            break
    return {
        'goal': goal[:60],
        'entry_path': entry_path,
        'preconditions': preconditions,
        'steps': steps,
        'assertions': assertions,
        'clarifications': clarifications,
        'risks': risks,
        'notes': notes,
        'analyzer': 'rule-fallback',
        'analyzer_note': '规则解析器 v0（未接模型）：仅做关键词结构化，结果需人工确认',
    }


def _valid_model_result(data):
    return isinstance(data, dict) and isinstance(data.get('steps'), list) \
        and isinstance(data.get('clarifications'), list)


def _call_model(text):
    """调用模型服务（若配置）。返回 dict 或 None（未配置/失败/输出不合法）。"""
    url = os.environ.get('AI_CASE_MODEL_URL')
    if not url:
        return None
    try:
        import requests
        headers = {}
        key = os.environ.get('AI_CASE_MODEL_KEY')
        if key:
            headers['Authorization'] = 'Bearer ' + key
        payload = {'requirement': text}
        name = os.environ.get('AI_CASE_MODEL_NAME')
        if name:
            payload['model'] = name
        timeout = float(os.environ.get('AI_CASE_MODEL_TIMEOUT') or 20)
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get('analysis'), dict):
            data = data['analysis']
        if not _valid_model_result(data):
            return None
        data.setdefault('clarifications', [])
        for c in data['clarifications']:
            c.setdefault('answer', None)
            c.setdefault('answered_at', None)
        data['analyzer'] = 'model:' + (name or 'custom')
        data.setdefault('analyzer_note', '模型解析结果，仍需人工确认后才会进入后续阶段')
        return data
    except Exception:
        return None


def analyze_requirement(text, entry_mode):
    """解析需求：模型优先，规则兜底。返回 analysis dict（含 clarifications）。"""
    result = _call_model(text)
    if result is not None:
        return result
    result = _rule_analyze(text, entry_mode)
    result['model_attempted'] = bool(os.environ.get('AI_CASE_MODEL_URL'))
    return result
