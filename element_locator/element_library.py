# -*- coding: utf-8 -*-
"""
GUI 元素定位器 · 元素库读写
写入格式完全照框架 page_objects/.../elements/ 的现有风格：
    self.<name> = CreateElement.create(Locator_Type.<TYPE>, '<value>', wait_type=Wait_By.<WAIT>)
支持：追加新元素 / 同名覆盖（替换原行）
"""
import os
import re

ELEMENTS_DIR = 'page_objects/app_ui/android/demoProject/elements'
# 默认新建元素文件名（用户也可选择写进已有文件）
DEFAULT_FILE = 'locator_gui_elements.py'

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


def element_line(name, locator_type, value, wait_type='VISIBILITY_OF', wait_seconds=None, comment=None):
    """wait_seconds：显式等待超时秒数（默认 6，见 DEFAULT_WAIT_SECONDS）；
    comment：元素备注，写在生成行行尾注释（# ...），方便回看元素是什么。
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
    if comment_text:
        # 业务名称：报告步骤/日志优先显示它（appOperator._element_desc 读取）
        line += ", desc='%s'" % _escape(comment_text)
    line += ')'
    if comment_text:
        line += '  # %s' % comment_text.replace('\n', ' ')
    return line


def list_element_files():
    """枚举现有元素库文件（含默认新文件）"""
    files = []
    if os.path.isdir(ELEMENTS_DIR):
        files = sorted(f for f in os.listdir(ELEMENTS_DIR) if f.endswith('.py') and f != '__init__.py')
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
        names.extend(re.findall(r'^\s*self\.([A-Za-z_][A-Za-z0-9_]*)\s*=', _read(p), re.MULTILINE))
    return names


def find_duplicate(locator_type, value):
    """跨元素文件查找相同「定位方式 + 定位值」的已存在元素（重复元素检测）。
    返回 {'name':..., 'filename':...} 或 None。文件里存的定位值是转义后的，比对时同样转义。"""
    locator_type = (locator_type or '').upper()
    escaped = _escape(value)
    for f in list_element_files():
        p = os.path.join(ELEMENTS_DIR, f)
        if not os.path.exists(p):
            continue
        pat = re.compile(
            r'^\s*self\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*CreateElement\.create\(\s*'
            r'Locator_Type\.(\w+)\s*,\s*\'((?:[^\'\\]|\\.)*)\'',
            re.MULTILINE)
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
                comment=None, check_dup=True):
    """
    向元素库文件添加/覆盖元素。
    wait_seconds：显式等待超时秒数（None/非法 = 默认 6）。
    comment：元素备注（生成行行尾 # 注释，可空）。
    check_dup=True 时先做重复检测：库中已有相同定位（且非同名覆盖）→ 不落盘，
    返回 {'ok': False, 'duplicate': {...}}，由前端决定「使用已有元素」还是「强制新建」。
    返回 {'ok': bool, 'content': 文件最新内容, 'action': 'added'|'updated'|'created', 'msg': 说明}
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
        return {'ok': False, 'msg': '元素名称不合法（只允许字母/数字/下划线，且不能以数字开头）'}
    if not value:
        return {'ok': False, 'msg': '定位值不能为空'}
    locator_type = locator_type.upper()

    if check_dup:
        dup = find_duplicate(locator_type, value)
        if dup and dup['name'] != name:
            return {'ok': False, 'duplicate': dup,
                    'msg': '发现已有元素 %s（%s）使用相同定位，是否直接使用已有元素？'
                           % (dup['name'], dup['filename'])}

    path = os.path.join(ELEMENTS_DIR, filename)
    new_line = element_line(name, locator_type, value, wait_type, wait_seconds, comment)

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
    last_elem = list(re.finditer(r'^[ \t]*self\.[A-Za-z_][A-Za-z0-9_]*\s*=.*$', after, re.MULTILINE))
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
