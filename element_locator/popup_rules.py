# -*- coding: utf-8 -*-
"""GUI 元素定位器 · 随机弹窗规则库读写

规则库文件：page_objects/app_ui/android/demoProject/elements/popupElements.py
- 元素行（关闭按钮）由 element_library.add_element 生成/覆盖（复用既有转义与插入逻辑）
- RULE_OPTIONS 附加约束（锚点/冷却/活动页）由本模块整体重渲染维护
- 执行侧 common/appium/popup_handler.py 在元素等待轮询里按规则被动扫描关闭
"""
import ast
import os
import re

from element_library import ELEMENTS_DIR, element_line

POPUP_FILE = 'popupElements.py'
POPUP_PATH = os.path.join(ELEMENTS_DIR, POPUP_FILE)

# 弹窗关闭按钮的默认等待方式：出现即判存在（扫描用 find_elements 直查，
# wait 参数仅影响该元素被常规流程使用时的行为，取短等待避免拖慢轮询）
DEFAULT_WAIT_TYPE = 'PRESENCE_OF_ELEMENT_LOCATED'
DEFAULT_WAIT_SECONDS = 1
DEFAULT_COOLDOWN = 2

# 锚点/关闭按钮允许的定位方式（与 Locator_Type 一致，driver.find_elements 可直用）
ALLOWED_TYPES = ('ID', 'XPATH')

_ELEM_RE = re.compile(
    r"^[ \t]*self\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*CreateElement\.create\(\s*"
    r"Locator_Type\.(\w+)\s*,\s*'((?:[^'\\]|\\.)*)'"
    r"((?:[^)])|\n)*?"          # 其余参数（wait_type/wait_seconds/desc...，展示用）
    r"\)[ \t]*(?:#[ \t]*(.*))?$",
    re.MULTILINE)

_OPTIONS_BLOCK_RE = re.compile(r'^[ \t]*RULE_OPTIONS = \{.*?^[ \t]*\}[ \t]*$',
                               re.MULTILINE | re.DOTALL)

# 渲染头注释（_render_options 每次都会写）；重写前须先清掉旧份，否则反复登记/删除会堆叠
_HEADER_FIRST_LINE = '    # 规则附加约束（元素定位器「登记随机弹窗」自动维护，手工编辑请保持语法）：'
_HEADER_RE = re.compile(r'^[ \t]*' + re.escape(_HEADER_FIRST_LINE.strip()) + r'\n(?:[ \t]*#[^\n]*\n)*',
                        re.MULTILINE)


def _strip_rendered_headers(content):
    """移除所有由 _render_options 生成过的头注释块（含其后的 # 说明行）"""
    return _HEADER_RE.sub('', content)


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _write(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _parse_options(content):
    """解析 RULE_OPTIONS 字典（块内允许中文注释，用 ast.parse 而非 literal_eval）。
    解析失败返回空 dict（不阻断列表展示与新增）。"""
    m = _OPTIONS_BLOCK_RE.search(content)
    if not m:
        return {}
    try:
        tree = ast.parse('x = ' + m.group(0).strip())
        return ast.literal_eval(tree.body[0].value)
    except Exception:
        return {}


def _render_options(options):
    """渲染 RULE_OPTIONS 块（含维护说明注释）；options 为空时返回空串（块整体移除）。"""
    if not options:
        return ''
    lines = [
        '',
        '    # 规则附加约束（元素定位器「登记随机弹窗」自动维护，手工编辑请保持语法）：',
        '    #   anchor   关闭按钮与弹窗特征成对出现才点关闭——同一个关闭按钮 id 常被非弹窗界面复用，无锚点会误关',
        '    #   activity 仅在该活动页内扫描；cooldown 同规则点击冷却秒数（默认 2）',
        '    RULE_OPTIONS = {',
    ]
    for name in sorted(options):
        opt = options[name] or {}
        lines.append("        '%s': {" % name)
        if opt.get('activity'):
            lines.append("            'activity': %r," % str(opt['activity']))
        lines.append("            'cooldown': %d," % int(opt.get('cooldown', DEFAULT_COOLDOWN)))
        if opt.get('anchor'):
            at, av = opt['anchor']
            lines.append('            %r: %r,' % (str('anchor'), (str(at), str(av))))
        lines.append('        },')
    lines.append('    }')
    return '\n'.join(lines) + '\n'


def parse_rules():
    """规则列表：[{name, locator_type, locator_value, anchor, cooldown, activity, comment}]"""
    if not os.path.exists(POPUP_PATH):
        return []
    content = _read(POPUP_PATH)
    options = _parse_options(content)
    rules = []
    for m in _ELEM_RE.finditer(content):
        name, lt, lv, _rest, comment = m.groups()
        opt = options.get(name, {})
        anchor = opt.get('anchor')
        rules.append({
            'name': name,
            'locator_type': lt,
            'locator_value': lv.replace("\\'", "'").replace('\\\\', '\\'),
            'anchor': {'type': anchor[0], 'value': anchor[1]} if anchor else None,
            'cooldown': int(opt.get('cooldown', DEFAULT_COOLDOWN)),
            'activity': opt.get('activity') or '',
            'comment': (comment or '').strip(),
        })
    return rules


def _upsert_options(content, name, entry):
    """更新/新增 name 的约束项并整体重渲染 RULE_OPTIONS 块（先清旧注释头，防反复登记堆叠）。"""
    options = _parse_options(content)
    options[name] = entry
    new_block = _render_options(options)
    content = _strip_rendered_headers(content)
    m = _OPTIONS_BLOCK_RE.search(content)
    if m:
        return content[:m.start()] + new_block + content[m.end():]
    return content.rstrip('\n') + '\n' + new_block


def _remove_options(content, name):
    content = _strip_rendered_headers(content)
    m = _OPTIONS_BLOCK_RE.search(content)
    if not m:
        return content
    options = _parse_options(content)
    options.pop(name, None)
    new_block = _render_options(options)
    return content[:m.start()] + new_block + content[m.end():]


def add_rule(name, locator_type, value, anchor_type=None, anchor_value=None,
             cooldown=None, activity=None, comment=None):
    """登记/更新一条弹窗规则：关闭按钮元素行 + RULE_OPTIONS 约束。
    元素行复用 element_library.add_element（同名覆盖、缺 __init__ 容错等既有逻辑）。"""
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name or ''):
        return {'ok': False, 'msg': '规则名不合法（只允许字母/数字/下划线，且不能以数字开头）'}
    lt = (locator_type or '').upper()
    if lt not in ALLOWED_TYPES:
        return {'ok': False, 'msg': '不支持的定位方式（可选：ID / XPATH）'}
    if not (value or '').strip():
        return {'ok': False, 'msg': '关闭按钮定位值不能为空'}
    if (anchor_value or '').strip() and (anchor_type or '').upper() not in ALLOWED_TYPES:
        return {'ok': False, 'msg': '锚点定位方式不合法'}
    # 同定位已被其他规则登记 → 提示复用，避免两条规则抢着关同一按钮
    for r in parse_rules():
        if r['name'] != name and r['locator_type'] == lt and r['locator_value'] == value:
            return {'ok': False, 'msg': '该定位已登记为规则 %s，请直接调整那条规则或换用其他关闭按钮' % r['name']}

    from element_library import add_element
    # 元素行与 RULE_OPTIONS 写进同一份文件：目录跟随 POPUP_PATH（测试可整体指向临时副本）
    r = add_element(os.path.basename(POPUP_PATH), name, lt, value.strip(),
                    wait_type=DEFAULT_WAIT_TYPE,
                    wait_seconds=DEFAULT_WAIT_SECONDS,
                    comment=comment or None, check_dup=False,
                    elements_dir=os.path.dirname(os.path.abspath(POPUP_PATH)))
    if not r['ok']:
        return r

    entry = {'cooldown': int(cooldown) if cooldown else DEFAULT_COOLDOWN}
    if (anchor_value or '').strip():
        entry['anchor'] = (anchor_type.upper(), anchor_value.strip())
    if (activity or '').strip():
        entry['activity'] = activity.strip()
    content = _read(POPUP_PATH)
    content = _upsert_options(content, name, entry)
    _write(POPUP_PATH, content)
    return {'ok': True, 'msg': '规则 %s 已登记（弹窗自动处理将在用例执行时被动生效）' % name,
            'rules': parse_rules()}


def delete_rule(name):
    """删除一条规则：移除关闭按钮元素行 + RULE_OPTIONS 里的约束项。"""
    if not os.path.exists(POPUP_PATH):
        return {'ok': False, 'msg': '规则库文件不存在'}
    content = _read(POPUP_PATH)
    pat = re.compile(r'^[ \t]*self\.%s\s*=.*\n?' % re.escape(name), re.MULTILINE)
    if not pat.search(content):
        return {'ok': False, 'msg': '规则 %s 不存在' % name}
    content = pat.sub('', content)
    content = _remove_options(content, name)
    _write(POPUP_PATH, content)
    return {'ok': True, 'msg': '规则 %s 已删除' % name, 'rules': parse_rules()}
