# -*- coding: utf-8 -*-
"""
GUI 元素定位器 · 元素库读写
写入格式完全照框架 page_objects/.../elements/ 的现有风格：
    self.<name> = CreateElement.create(Locator_Type.<TYPE>, '<value>', wait_type=Wait_By.<WAIT>)
支持：追加新元素 / 同名覆盖（替换原行）
"""
import keyword
import os
import re

# 元素名允许中文（PEP 3131）：self.<名> 属性访问在 Python 3 合法，
# 页面方法 click_<名> 等派生名同样合法。仅排除 Python 关键字（obj.class 是语法错误）。
NAME_RE = re.compile(r'^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$')
# 长度上限：元素名会派生页面方法名（click_<名>）与报告步骤名，过长影响可读性
NAME_MAX_LEN = 64
# 解析/定位元素行的 name 字符类（与 NAME_RE 保持同一字符集）
_NAME_CLS = r'[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*'


def is_valid_element_name(name):
    """元素名合法性：字母/中文/下划线开头，后续可含数字；≤64 字符；排除 Python 关键字"""
    name = name or ''
    return (len(name) <= NAME_MAX_LEN and bool(NAME_RE.match(name))
            and not keyword.iskeyword(name))

ELEMENTS_DIR = 'page_objects/app_ui/android/demoProject/elements'
# 默认新建元素文件名（用户也可选择写进已有文件）
DEFAULT_FILE = 'locator_gui_elements.py'
# 随机弹窗规则库（element_locator/popup_rules.py 专管）：不是普通元素文件——
# 从「写入元素文件」下拉隔离，避免常规元素误写进弹窗规则（会被执行引擎当作关闭按钮自动点击）
POPUP_FILE = 'popupElements.py'

# 用例管理覆盖上传时自动生成的历史备份 xxx_<时间戳>_backup.py（见 web_platform/admin_routes.py）。
# 这类文件与正式文件内容可能完全相同、且会定义同类名，绝不能出现在任何"可选文件"清单里：
# 被选中就会写入永不被页面 import 的文件（静默失效），或让按类名反解的归属算到错误文件上。
GENERATED_BACKUP_RE = re.compile(r'_\d{8}_\d{6}_backup\.py$')


def is_generated_backup(filename):
    """是否为用例管理自动生成的历史备份文件"""
    return bool(GENERATED_BACKUP_RE.search(filename))

HEADER = '''# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


'''

INDENT = '        '


def to_class_name(filename):
    """locator_gui_elements.py -> LocatorGuiElements；startPageElements.py -> StartPageElements"""
    base = os.path.splitext(filename)[0]
    if '_' in base:
        return ''.join(part[:1].upper() + part[1:] for part in base.split('_') if part)
    return base[:1].upper() + base[1:]


def _escape(value):
    """元素值转义（用于放进单引号字符串）"""
    return str(value).replace('\\', '\\\\').replace("'", "\\'")


DEFAULT_WAIT_SECONDS = 6   # 元素默认显式等待秒数（个别慢页面元素保存时可单独指定更长等待）


def element_line(name, locator_type, value, wait_type='VISIBILITY_OF', wait_seconds=None, comment=None, cn_name=None):
    """wait_seconds：显式等待超时秒数（默认 6，见 DEFAULT_WAIT_SECONDS）；
    comment：元素备注，写在生成行行尾注释（# ...），方便回看元素是什么。
    cn_name：元素中文名（元素管理/报告的显示名），写进 desc= 参数——
    CreateElement.create 的 desc 即"元素中文说明"；有中文名时行尾注释为「中文名 · 备注」。
    传正整数时显式写进生成行，所见即所得；不传/非法则用默认 6。"""
    line = '%sself.%s = CreateElement.create(Locator_Type.%s, \'%s\', wait_type=Wait_By.%s' % (
        INDENT, name, locator_type, _escape(value), wait_type)
    try:
        sec = int(wait_seconds)
        if sec <= 0:
            sec = DEFAULT_WAIT_SECONDS
    except (TypeError, ValueError):
        sec = DEFAULT_WAIT_SECONDS
    line += ', wait_seconds=%d' % sec
    comment_text = str(comment).strip() if comment and str(comment).strip() else ''
    cn_text = str(cn_name).strip() if cn_name and str(cn_name).strip() else ''
    desc_text = cn_text or comment_text
    if desc_text:
        # 业务名称：报告步骤/日志优先显示它（appOperator._element_desc 读取）
        line += ", desc='%s'" % _escape(desc_text)
    line += ')'
    tail = (cn_text + (' · ' + comment_text if comment_text else '')) if cn_text else comment_text
    if tail:
        line += '  # %s' % tail.replace('\n', ' ')
    return line


def list_element_files():
    """枚举现有元素库文件（含默认新文件；弹窗规则库 popupElements.py 不在此列——由 popup_rules 专管）"""
    files = []
    if os.path.isdir(ELEMENTS_DIR):
        files = sorted(f for f in os.listdir(ELEMENTS_DIR)
                       if f.endswith('.py') and f != '__init__.py' and f != POPUP_FILE
                       and not is_generated_backup(f))
    if DEFAULT_FILE not in files:
        files.insert(0, DEFAULT_FILE)
    return files


def list_element_names(filename=None):
    """返回指定元素文件（或不传 = 全部文件）里已定义的 self.<name> 列表，供用例步骤/重复检测用"""
    files = [filename] if filename else list_element_files()
    names = []
    for f in files:
        p = os.path.join(ELEMENTS_DIR, f)
        if not os.path.exists(p):
            continue
        names.extend(re.findall(r'^\s*self\.(%s)\s*=' % _NAME_CLS, _read(p), re.MULTILINE))
    return names


def find_duplicate(locator_type, value, elements_dir=None):
    """跨元素文件查找相同「定位方式 + 定位值」的已存在元素（重复元素检测）。
    返回 {'name':..., 'filename':...} 或 None。文件里存的定位值是转义后的，比对时同样转义。
    elements_dir：目标目录覆盖（与 add_element 一致——写进哪个目录就在哪个目录查重，
    测试指向临时库时不会误查真实元素库，弹窗规则库同理）。"""
    locator_type = (locator_type or '').upper()
    escaped = _escape(value)
    scan_dir = elements_dir or ELEMENTS_DIR
    if not os.path.isdir(scan_dir):
        return None
    # 直接枚举目标目录（不能用 list_element_files()——它读全局 ELEMENTS_DIR 的清单，
    # 扫描目录与其不一致时会漏掉目标目录里的文件）
    files = sorted(f for f in os.listdir(scan_dir)
                   if f.endswith('.py') and f != '__init__.py' and f != POPUP_FILE
                   and not is_generated_backup(f))
    pat = re.compile(
        r'^\s*self\.(%s)\s*=\s*CreateElement\.create\(\s*'
        r'Locator_Type\.(\w+)\s*,\s*\'((?:[^\'\\]|\\.)*)\'' % _NAME_CLS,
        re.MULTILINE)
    for f in files:
        p = os.path.join(scan_dir, f)
        for m in pat.finditer(_read(p)):
            if m.group(2).upper() == locator_type and m.group(3) == escaped:
                return {'name': m.group(1), 'filename': f}
    return None


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _ensure_imports(content):
    """框架部分自带旧元素文件漏写了 import（如 indexPageElements.py），
    写元素前自动补全，保证写入后的文件能直接被框架 import。"""
    if 'from page_objects.createElement import CreateElement' in content:
        return content
    m = re.search(r'^(class\s+\w+[^\n]*\n)', content, re.MULTILINE)
    if not m:
        return content
    block = '\n'.join([
        'from page_objects.createElement import CreateElement',
        'from page_objects.app_ui.locator_type import Locator_Type',
        'from page_objects.app_ui.wait_type import Wait_Type as Wait_By',
        '',
    ])
    return content[:m.start()] + block + content[m.start():]


def _write(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def add_element(filename, name, locator_type, value, wait_type='VISIBILITY_OF', wait_seconds=None,
                comment=None, check_dup=True, elements_dir=None, cn_name=None):
    """
    向元素库文件添加/覆盖元素。
    wait_seconds：显式等待超时秒数（None/非法 = 默认 6）。
    comment：元素备注（生成行行尾 # 注释，可空）。
    check_dup=True 时先做重复检测：库中已有相同定位（且非同名覆盖）→ 不落盘，
    返回 {'ok': False, 'duplicate': {...}}，由前端决定「使用已有元素」还是「强制新建」。
    elements_dir：目标目录覆盖（默认 ELEMENTS_DIR；弹窗规则库 popup_rules 借此把元素行
    与 RULE_OPTIONS 写进同一份可替换路径——测试时整体指向临时副本，不碰真实文件）。
    返回 {'ok': bool, 'content': 文件最新内容, 'action': 'added'|'updated'|'created', 'msg': 说明}
    """
    if not is_valid_element_name(name):
        return {'ok': False, 'msg': '元素名称不合法（允许中文/字母/数字/下划线，不能以数字开头，'
                                    '不能是 Python 关键字）'}
    if not value:
        return {'ok': False, 'msg': '定位值不能为空'}
    locator_type = locator_type.upper()

    if check_dup:
        dup = find_duplicate(locator_type, value, elements_dir=elements_dir)
        if dup and dup['name'] != name:
            return {'ok': False, 'duplicate': dup,
                    'msg': '发现已有元素 %s（%s）使用相同定位，是否直接使用已有元素？'
                           % (dup['name'], dup['filename'])}

    path = os.path.join(elements_dir or ELEMENTS_DIR, filename)
    new_line = element_line(name, locator_type, value, wait_type, wait_seconds, comment, cn_name=cn_name)

    if not os.path.exists(path):
        # 新建文件
        cls = to_class_name(filename)
        content = HEADER + 'class %s:\n' % cls + '    def __init__(self):\n' + new_line + '\n'
        _write(path, content)
        return {'ok': True, 'action': 'created', 'content': content,
                'msg': '已新建元素文件 %s 并添加元素 %s' % (filename, name)}

    content = _read(path)
    # 自动补齐缺失的 import（如框架自带旧文件漏写），再执行覆盖/追加
    content = _ensure_imports(content)

    # 1) 同名覆盖：替换 self.<name> = ... 整行
    pat = re.compile(r'^[ \t]*self\.%s\s*=.*$' % re.escape(name), re.MULTILINE)
    if pat.search(content):
        content = pat.sub(lambda m: new_line, content, count=1)
        _write(path, content)
        return {'ok': True, 'action': 'updated', 'content': content,
                'msg': '元素 %s 已覆盖更新（%s）' % (name, filename)}

    # 2) 追加：在 __init__ 方法体内插入
    init_m = re.search(r'def __init__\(self\):\n', content)
    if not init_m:
        return {'ok': False, 'msg': '元素库文件缺少 __init__ 方法，无法添加元素'}

    body_start = init_m.end()
    after = content[body_start:]
    # 2a) __init__ 里只有 pass → 替换 pass
    pass_m = re.search(r'^[ \t]*pass[ \t]*$', after, re.MULTILINE)
    if pass_m:
        content = content[:body_start] + re.sub(r'^[ \t]*pass[ \t]*$', new_line, after, count=1)
        _write(path, content)
        return {'ok': True, 'action': 'added', 'content': content,
                'msg': '元素 %s 已添加到 %s' % (name, filename)}

    # 2b) 在最后一个 self.xxx = ... 行之后插入（整行匹配，避免把新行插到「等号后」截断原行）
    last_elem = list(re.finditer(r'^[ \t]*self\.%s\s*=.*$' % _NAME_CLS, after, re.MULTILINE))
    if last_elem:
        idx = body_start + last_elem[-1].end()
        content = content[:idx] + '\n' + new_line + content[idx:]
        _write(path, content)
        return {'ok': True, 'action': 'added', 'content': content,
                'msg': '元素 %s 已添加到 %s' % (name, filename)}

    # 2c) 无元素也无 pass（空缩进体）→ 直接缩进追加到方法体
    content = content[:body_start] + new_line + '\n' + content[body_start:]
    _write(path, content)
    return {'ok': True, 'action': 'added', 'content': content,
            'msg': '元素 %s 已添加到 %s' % (name, filename)}


if __name__ == '__main__':
    import sys
    print('现有元素文件:', list_element_files())
    if len(sys.argv) > 3:
        r = add_element(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else 'x')
        print(r['msg'], '| action:', r.get('action'))
        print('--- 文件内容 ---')
        print(r['content'])
