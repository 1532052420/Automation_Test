# -*- coding: utf-8 -*-
"""
GUI 元素定位器 · 批量采集核心（方案：app_automation_element_collection_plan.md 第一阶段）

纯函数模块：输入 hierarchy XML，输出「过滤 + 去重 + 命名 + 定位候选」齐备的候选元素清单。
不碰设备（dump 由 device.py 负责）、不碰元素库（入库由 element_library.add_elements_batch 负责），
方便离线单测与后续调整过滤规则。

核心原则（与方案 §21 对齐）：
- 原始 Hierarchy 由调用方存档，这里只读不写；
- 不因为没有 text 就过滤元素（clickable/focusable/scrollable/可输入都算有效候选）；
- 不把纯布局节点放进元素库；
- 去重不只依赖 text（指纹 = resource-id/text/content-desc/class，无语义标识时补 bounds）；
- 定位候选直接复用 device.gen_locators（与单元素采集同一套词表与优先级）。
"""
import re

import device


# ---------- 有效元素判定（方案 §7 / §8） ----------

def _is_candidate(node):
    """有效候选：命中任一「有效属性」。纯布局容器（无任何业务属性/交互能力）被过滤。"""
    if node.get('resource-id') or node.get('text') or node.get('content-desc'):
        return True
    if node.get('clickable') or node.get('focusable') or node.get('scrollable'):
        return True
    cls = node.get('class') or ''
    if 'EditText' in cls or 'TextField' in cls:   # 可输入节点常无 text/id 之外的标识
        return True
    return False


# ---------- 名称生成（方案 §11，与 element_library.is_valid_element_name 对齐） ----------

def _slugify(raw):
    """属性值 → 合法元素名片段：保留中文/字母/数字/下划线，其余折叠为下划线。"""
    s = re.sub(r'[^\w\u4e00-\u9fff]+', '_', str(raw or '').strip())
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit():
        s = 'el_' + s
    return s[:60] if s else ''


def _gen_name(node, counters):
    """命名优先级：resource-id 末段 → text → content-desc → element_NNN。
    批内重名自动加 _2/_3 后缀（counters 记账）。"""
    rid = (node.get('resource-id') or '').strip()
    base = ''
    if rid:
        base = _slugify(rid.rsplit('/', 1)[-1])
    if not base:
        base = _slugify(node.get('text'))
    if not base:
        base = _slugify(node.get('content-desc'))
    if not base:
        base = 'element_%03d' % counters['seq']
    name = base
    while name in counters['used']:
        counters['seq'] += 1
        m = re.match(r'^(.*?)(_(\d+))?$', name)
        name = (m.group(1) or 'element') + '_' + str(counters['seq'])
    counters['used'].add(name)
    return name


def collect_from_xml(xml_text):
    """hierarchy XML → 采集结果。
    返回 {'raw': 原始节点数, 'items': [候选元素], 'filtered': [被过滤明细], 'stats': {...}}。
    item: {name, cn_name, locator_type, value, candidates, comment}
    filtered: [{name, reason}]（名称为 text/rid/class 摘要，原因可追踪，方案 §13）。"""
    data = device.xml_to_tree(xml_text)
    all_nodes = data['all']
    counters = {'used': set(), 'seq': 1}
    items, filtered = [], []
    seen = {}          # fingerprint -> 首个 item（批内去重）
    for idx, n in enumerate(all_nodes):
        rid = (n.get('resource-id') or '').strip()
        text = (n.get('text') or '').strip()
        desc = (n.get('content-desc') or '').strip()
        cls = (n.get('class') or '').strip()
        label = text or rid.rsplit('/', 1)[-1] or desc or cls or ('node#%d' % idx)
        if not _is_candidate(n):
            filtered.append({'name': label, 'reason': '无有效属性（纯布局容器）'})
            continue
        # 指纹（方案 §9）：有 resource-id 时以 rid 为身份（同 rid 视为重复，方案第一优先级）；
        # 无 rid 时补 bounds —— 同 text 的左右两个按钮是不同元素（§9 明确不能按 text 误删）
        fp = (rid, text, desc, cls)
        if not rid:
            fp = fp + tuple(n.get('_bounds') or ())
        if fp in seen:
            seen[fp]['_dup_count'] = seen[fp].get('_dup_count', 1) + 1
            filtered.append({'name': label, 'reason': '与「%s」重复' % seen[fp]['name'],
                             'is_dup': True})
            continue
        cands = device.gen_locators(n, all_nodes)
        if not cands:
            filtered.append({'name': label, 'reason': '无法生成稳定定位'})
            continue
        name = _gen_name(n, counters)
        cn_name = (text or desc or '').strip()[:60] or ''
        item = {
            'name': name, 'cn_name': cn_name,
            'locator_type': cands[0]['locator_type'], 'value': cands[0]['value'],
            'candidates': cands, 'comment': '批量采集',
            '_index': idx, '_bounds': n.get('_bounds'),
        }
        seen[fp] = item
        items.append(item)

    # 统计口径与方案 §12 一致：raw = 无效过滤 + 去重 + 最终候选
    invalid_total = sum(1 for f in filtered if not f.get('is_dup'))
    dup_total = len(all_nodes) - len(items) - invalid_total
    stats = {
        'raw': len(all_nodes),
        'filtered': invalid_total,
        'valid': len(all_nodes) - invalid_total,
        'dup': dup_total,
        'final': len(items),
    }
    return {'raw': stats['raw'], 'stats': stats, 'items': items, 'filtered': filtered}
