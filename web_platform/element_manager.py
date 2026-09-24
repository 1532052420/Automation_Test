# -*- coding: utf-8 -*-
"""Web 执行平台 · AppUI 元素管理（元素库的列表 / 编辑 / 删除 / 复制）

数据源：page_objects/app_ui/android/demoProject/elements/*.py —— 与元素定位器、
执行框架共用同一份元素库（单一数据源），这里只是「读出来展示 + 行级编辑」。

解析约定（与 element_locator/element_library.py 的写入格式一致）：
    self.<name> = CreateElement.create(Locator_Type.<TYPE>, '<value>',
                                       wait_type=Wait_By.<WAIT>,
                                       wait_seconds=N, desc='...')  # 行尾备注

写回复用 element_locator.element_library.add_element（同名覆盖 = 整行替换），
保证「平台编辑的元素」与「定位器采集的元素」走同一条生成逻辑，格式永不漂移。
"""
import os
import re
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:      # 允许 `python web_platform/element_manager.py` 独立运行
    sys.path.insert(0, BASE_DIR)

from element_locator.element_library import add_element, is_valid_element_name

ELEMENTS_DIR = os.path.join(BASE_DIR, 'page_objects', 'app_ui', 'android', 'demoProject', 'elements')
POPUP_FILE = 'popupElements.py'          # 随机弹窗规则库，不进普通元素管理（popup_rules 专管）
DEFAULT_FILE = 'locator_gui_elements.py'  # 复制/新建元素的默认落点

# 用例管理历史备份 xxx_<时间戳>_backup.py 绝不入库清单（与 element_library 约定一致）
_BACKUP_RE = re.compile(r'_\d{8}_\d{6}_backup\.py$')

# 元素行解析：名称 / 定位方式 / 定位值（存的是转义后的值）+ 其余参数与行尾备注。
# 元素名允许中文（与 element_library.NAME_RE 同一字符集，PEP 3131）；
# 定位值支持单/双引号字符串（内部可含另一种引号，如 '//*[@text="xx"]'）；
# rest 跨行吃到语句收尾的 `)`（wait_type/wait_seconds 常写在续行）。
# 注意：行尾注释用 [^\n] 限定不跨行——否则 DOTALL 下会把整个文件吞进上一个匹配。
_NAME_CLS = r'[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*'
_ELEMENT_PAT = re.compile(
    r'^\s*self\.(?P<name>%s)\s*=\s*CreateElement\.create\(\s*' % _NAME_CLS
    + r'Locator_Type\.(?P<type>\w+)\s*,\s*'
    r'(?P<value_str>\'(?:[^\'\\]|\\.)*\'|"(?:[^"\\]|\\.)*")'
    r'(?P<rest>.*?)\)[ \t]*(?P<comment>#[^\n]*)?$',
    re.MULTILINE | re.DOTALL)
_WAIT_TYPE_RE = re.compile(r'Wait_By\.(\w+)')
_WAIT_SEC_RE = re.compile(r'wait_seconds=(\d+)')
_DESC_RE = re.compile(r"desc='((?:[^'\\]|\\.)*)'")
_TAIL_COMMENT_RE = re.compile(r'#\s*([^\n]*)$')
_NAME_RE = re.compile(r'^%s$' % _NAME_CLS)

# 编辑弹窗可选的定位方式（常用集合；写回按字面生成，与 Locator_Type 枚举名一致）
LOCATOR_TYPES = ('ID', 'XPATH', 'ACCESSIBILITY_ID', 'CLASS_NAME', 'NAME',
                 'TAG_NAME', 'CSS_SELECTOR', 'ANDROID_UIAUTOMATOR')
WAIT_TYPES = ('VISIBILITY_OF', 'PRESENCE_OF_ELEMENT_LOCATED', 'ELEMENT_TO_BE_CLICKABLE')


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _unescape(v):
    return str(v).replace("\\'", "'").replace('\\\\', '\\')


def _parse_value(vstr):
    """把带引号的定位值字面量还原成原始值（按引号风格反转义）"""
    q, body = vstr[0], vstr[1:-1]
    if q == '"':
        return _unescape(body.replace('\\"', '"'))
    return _unescape(body)


def list_element_files():
    """可选元素文件（含默认落点；__init__/弹窗规则库/历史备份除外）"""
    files = []
    if os.path.isdir(ELEMENTS_DIR):
        files = sorted(f for f in os.listdir(ELEMENTS_DIR)
                       if f.endswith('.py') and f != '__init__.py'
                       and f != POPUP_FILE and not _BACKUP_RE.search(f))
    if DEFAULT_FILE not in files:
        files.insert(0, DEFAULT_FILE)
    return files


def _usage_counts():
    """元素使用次数：扫描 page_objects 页面文件里 `.元素名` 的引用行数。
    页面方法经 self._elements.<name> 引用元素，cases 只调页面方法不直接用元素，
    所以只扫 page_objects 即可反映真实使用面。"""
    root = os.path.join(BASE_DIR, 'page_objects')
    counts = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            try:
                content = _read(os.path.join(dirpath, fn))
            except OSError:
                continue
            for m in re.finditer(r'\.\s*(%s)\b' % _NAME_CLS, content):
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


def list_elements():
    """全量元素列表（文件 mtime 兼作创建时间；使用次数按页面引用统计）。
    含弹窗规则库 popupElements.py 的规则元素（popup=True）——元素管理只读展示：
    该文件由 popup_rules 专管，RULE_OPTIONS/WHITELIST 与元素行同文件共存，
    走普通编辑会重写整文件把规则抹掉，故列表不带编辑/删除入口。"""
    usages = _usage_counts()
    elements = []
    for fname in list_element_files() + [POPUP_FILE]:
        popup = fname == POPUP_FILE
        path = os.path.join(ELEMENTS_DIR, fname)
        if not os.path.isfile(path):
            continue
        try:
            created_at = int(os.path.getmtime(path))
        except OSError:
            created_at = 0
        for m in _ELEMENT_PAT.finditer(_read(path)):
            rest = m.group('rest') or ''
            if m.group('comment'):
                rest += '  ' + m.group('comment')
            wt = _WAIT_TYPE_RE.search(rest)
            ws = _WAIT_SEC_RE.search(rest)
            desc_m = _DESC_RE.search(rest)
            desc = _unescape(desc_m.group(1)) if desc_m else ''
            if not desc:
                tail = _TAIL_COMMENT_RE.search(rest)
                desc = tail.group(1).strip() if tail else ''
            name = m.group('name')
            elements.append({
                'name': name,
                # 元素中文名（desc= 参数首段）：元素管理/报告的显示名；旧元素缺省为空
                'cn_name': (desc.split(' · ')[0].strip() if desc else ''),
                'type': m.group('type'),
                'value': _parse_value(m.group('value_str')),
                'wait_type': wt.group(1) if wt else 'VISIBILITY_OF',
                'wait_seconds': int(ws.group(1)) if ws else 6,
                'desc': desc,
                'file': fname,
                'popup': popup,
                'usage_count': usages.get(name, 0),
                'created_at': created_at,
            })
    return elements


def delete_element(filename, name):
    """从元素文件中删除一行元素定义（同名只删第一处；找不到报错）。
    popupElements.py（随机弹窗规则库）受管可删：单行正则移除，同文件 RULE_OPTIONS/WHITELIST
    常量不受影响（v6.11.0 用户要求：元素管理支持删除随机弹窗元素）。"""
    if not is_valid_element_name(name or ''):
        return False, '元素名称不合法'
    if filename != POPUP_FILE and filename not in list_element_files():
        return False, '元素文件不存在或不受管: %s' % filename
    path = os.path.join(ELEMENTS_DIR, filename)
    if not os.path.isfile(path):
        return False, '元素文件不存在: %s' % filename
    content = _read(path)
    pat = re.compile(r'^[ \t]*self\.%s\s*=.*\n?' % re.escape(name), re.MULTILINE)
    new_content, n = pat.subn('', content, count=1)
    if n == 0:
        return False, '元素 %s 在 %s 中未找到（可能已被删除）' % (name, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    return True, '已删除元素 %s（%s）' % (name, filename)


def delete_file(filename):
    """删除整个元素文件（直接删除，不留备份——用户口径：删就删干净）。
    规则库 popupElements.py / 备份文件不在 list_element_files 白名单，天然删不到。"""
    if filename not in list_element_files():
        return False, '元素文件不存在或不可删除: %s' % filename
    src = os.path.join(ELEMENTS_DIR, filename)
    try:
        os.remove(src)
    except OSError as e:
        return False, '删除失败：%s' % e
    return True, '元素文件 %s 已删除' % filename


def save_element(filename, name, locator_type, value, wait_type='VISIBILITY_OF',
                 wait_seconds=None, desc='', orig_name=None, cn_name=None):
    """编辑（同名整行替换 / 改名 = 删旧增新）与复制（落到任意受管元素文件）。

    返回 (ok, payload)；payload 携带 duplicate 供前端提示改用已有元素。
    写回统一走 element_library.add_element —— 与定位器共用同一套行生成/重复检测。"""
    name = (name or '').strip()
    if not is_valid_element_name(name):
        return False, {'msg': '元素名称不合法（允许中文/字母/数字/下划线，不能以数字开头，'
                              '不能是 Python 关键字，最长 64 字符）'}
    if not str(value or '').strip():
        return False, {'msg': '定位值不能为空'}
    # popupElements.py（随机弹窗规则库）单行增改与 delete_element 同口径放行：
    # 只动 self.xxx 元素行，同文件 RULE_OPTIONS/WHITELIST 常量不受影响
    if filename != POPUP_FILE and filename not in list_element_files():
        return False, {'msg': '目标元素文件不存在或不受管: %s' % filename}
    locator_type = (locator_type or '').upper()
    if locator_type not in LOCATOR_TYPES:
        return False, {'msg': '定位方式不合法: %s' % locator_type}
    if wait_type not in WAIT_TYPES:
        wait_type = 'VISIBILITY_OF'
    try:
        wait_seconds = int(wait_seconds) if wait_seconds not in (None, '') else None
    except (TypeError, ValueError):
        wait_seconds = None

    try:
        # 改名场景：先删旧行，避免新旧两行并存（页面方法仍引用旧名时会静默失效）
        if orig_name and orig_name != name:
            ok, msg = delete_element(filename, orig_name)
            if not ok:
                return False, {'msg': '原名元素处理失败：%s' % msg}
        r = add_element(filename, name, locator_type, str(value).strip(),
                        wait_type=wait_type, wait_seconds=wait_seconds,
                        comment=(desc or '').strip() or None,
                        check_dup=not (orig_name == name),
                        elements_dir=ELEMENTS_DIR,
                        cn_name=(cn_name or '').strip() or None)
    except Exception as e:
        return False, {'msg': '写入元素库失败: %s' % e}
    if not r.get('ok'):
        return False, r   # 携带 duplicate / msg（重复定位等），供前端提示
    verb = {'added': '已添加', 'updated': '已更新', 'created': '已新建文件并写入'}.get(
        r.get('action'), '已保存')
    return True, {'msg': '%s元素 %s（%s）' % (verb, name, filename)}


if __name__ == '__main__':
    for el in list_elements():
        print('%-28s %-18s usage=%-3d %s' % (el['name'], el['type'], el['usage_count'], el['file']))
