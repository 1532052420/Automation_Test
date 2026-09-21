"""
GUI 元素定位器 · 元素/操作 追加到用例（「添加到元素库」②③ 后端）
统一步骤结构（step dict）→ 把一步操作代码追加到指定用例文件的方法体：
    cases/app_ui/android/demoProject/test_xxx.py                    （用例行追加）
    page_objects/app_ui/android/demoProject/pages/xxxPage.py        （③ 同步生成页面方法）
元素与用例分离 —— 页面方法/用例只引用元素名 self._elements.<name>，不埋定位值。
支持：追加 test 方法体代码行 / 同名页面方法覆盖 / 自动补 import（用例文件本身在平台上传或手动创建）
"""

import os
import re

import element_library

CASES_DIR = 'cases/app_ui/android/demoProject'
PAGES_DIR = 'page_objects/app_ui/android/demoProject/pages'

IND = '    '  # 类内方法缩进（4 空格，与框架一致）

# 步骤类型清单（前端下拉与此一致）
# 长流程用例四件套：wait_element(轮询等待出现) / assert_gone(断言消失) /
# hide_keyboard(收起键盘) / if_click(分支·出现才点击)——写歌全流程等含等待/分支的
# 用例不再需要脱离工具手写（2026-09 复盘沉淀）
STEP_TYPES = [
    'click', 'input', 'long_press', 'assert_visible', 'assert_text',
    'assert_toast', 'wait_element', 'assert_gone', 'if_click',
    'screenshot', 'tap', 'sleep', 'hide_keyboard', 'custom',
    'deal_first_launch_dialogs',
]

# 页面里固定实现的工具方法：已存在则不重复生成
TOOL_METHODS = {'wait_and_shot', 'tap_xy', 'assert_toast', 'dismiss_keyboard',
                'deal_first_launch_dialogs'}

# 需要构造探针元素（CreateElement/Locator_Type/Wait_By）的步骤类型：
# 生成页面方法时页面文件缺这三个 import 会自动补齐
PROBE_STEP_TYPES = {'wait_element', 'assert_gone', 'if_click', 'deal_first_launch_dialogs'}


def list_case_files():
    """枚举现有用例文件（test_*.py）；排除用例管理自动生成的历史备份"""
    if not os.path.isdir(CASES_DIR):
        return []
    return sorted(f for f in os.listdir(CASES_DIR)
                  if f.startswith('test_') and f.endswith('.py')
                  and not element_library.is_generated_backup(f))


def list_page_files():
    """枚举现有页面对象文件；排除用例管理自动生成的历史备份"""
    if not os.path.isdir(PAGES_DIR):
        return []
    return sorted(f for f in os.listdir(PAGES_DIR)
                  if f.endswith('.py') and f != '__init__.py'
                  and not element_library.is_generated_backup(f))


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _write(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _escape(s):
    return str(s).replace('\\', '\\\\').replace("'", "\\'")


def _q(s):
    """生成单引号字符串字面量"""
    return "'%s'" % _escape(s)


def step_desc(step):
    """步骤的可读描述（后端兜底；前端通常会自己生成并让用户可改）"""
    if step.get('desc'):
        return step['desc'].strip()
    t = step.get('type', '')
    el = step.get('element') or ''
    p = step.get('param') or ''
    return {
        'click': '点击%s' % el,
        'input': '在%s输入「%s」' % (el, p),
        'long_press': '长按%s' % el,
        'assert_visible': '断言%s出现' % el,
        'assert_text': '断言%s文本为「%s」' % (el, p),
        'assert_toast': '断言toast「%s」' % p,
        'wait_element': '等待【%s】出现（最长%s秒）' % (el, p or 60),
        'assert_gone': '断言【%s】已消失' % el,
        'if_click': '若【%s】出现则点击（最长等%s秒）' % (el, p or 3),
        'screenshot': '截图：%s' % p,
        'tap': '点击坐标(%s)' % p,
        'sleep': '等待%s秒' % p,
        'hide_keyboard': '收起键盘',
        'custom': (p or '自定义代码').splitlines()[0],
        'deal_first_launch_dialogs': '首次启动弹窗处理（无弹窗自动跳过）',
    }.get(t, '未定义步骤')


def _method_block(name, doc, args, body):
    """生成一个页面方法代码块（类内 4 空格缩进，方法体内 8 空格，多行 body 逐行缩进）"""
    args_str = ', '.join(['self'] + (args or []))
    body_ind = '\n'.join((IND * 2 + line) if line.strip() else line for line in body.split('\n'))
    return '%sdef %s(%s):\n%s"""%s"""\n%s\n' % (
        IND, name, args_str, IND * 2, doc, body_ind)


def _probe_body_lines(element_name, seconds_var='timeout_seconds'):
    """构造探针元素代码体：复用元素库定义的定位（元素改定义方法不用改）。
    seconds_var：等待秒数变量名，须与页面方法签名参数一致。"""
    return (
        "probe = CreateElement.create(self._elements.%s.locator_type,\n"
        "                             self._elements.%s.locator_value,\n"
        "                             wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n"
        "                             wait_seconds=%s)"
    ) % (element_name, element_name, seconds_var)


def page_method_code(step):
    """步骤 → 页面方法代码块；sleep/custom 返回 None（不需要页面方法）。
    step.comment（操作备注）优先作为方法 docstring，缺省用步骤描述。"""
    t = step.get('type', '')
    el = step.get('element') or ''
    desc = (step.get('comment') or '').strip() or step_desc(step)
    if t == 'click':
        return _method_block('click_%s' % el, desc, [],
                             'self.appOperator.click(self._elements.%s)' % el)
    if t == 'input':
        return _method_block('input_%s' % el, desc, ['text'],
                             'self.appOperator.sendText(self._elements.%s, text)' % el)
    if t == 'long_press':
        return _method_block('long_press_%s' % el, desc, [],
                             'self.appOperator.touch_long_press(self._elements.%s, duration_sconds=2)' % el)
    if t == 'assert_visible':
        return _method_block('assert_%s' % el, desc, [],
                             'self.appOperator.getElement(self._elements.%s)' % el)
    if t == 'assert_text':
        return _method_block('assert_%s_text' % el, desc, ['expected'],
                             "assert self.appOperator.getText(self._elements.%s) == expected, '%s'" % (el, desc))
    if t == 'assert_toast':
        return _method_block('assert_toast', desc, ['text'],
                             "assert self.appOperator.is_toast_visible(text, wait_seconds=5), '%s'" % desc)
    if t == 'wait_element':
        # 轮询等待元素出现：探针按 PRESENCE 等待 timeout_seconds，超时 getElement 抛错=用例失败
        try:
            timeout = int(step.get('param'))
        except (TypeError, ValueError):
            timeout = 60
        body = _probe_body_lines(el) + '\nself.appOperator.getElement(probe)'
        return _method_block('wait_%s' % el, desc, ['timeout_seconds=%d' % timeout], body)
    if t == 'assert_gone':
        # 断言元素消失：探针短等待内仍找得到=失败（assert_true_with_shot 截图存证）
        body = (_probe_body_lines(el, 'wait_seconds') + '\n'
                + 'gone = True\n'
                + 'try:\n'
                + '    self.appOperator.getElement(probe)\n'
                + '    gone = False\n'
                + 'except Exception:\n'
                + '    pass\n'
                + "self.appOperator.assert_true_with_shot('%s', gone,\n" % desc
                + "                                   '等待%s秒内元素仍可见' % wait_seconds)")
        return _method_block('assert_%s_gone' % el, desc, ['wait_seconds=2'], body)
    if t == 'if_click':
        # 分支：元素出现才点击（探测超时不算失败，用例继续——用于「首发布弹窗」类分支处理）
        try:
            probe_sec = int(step.get('param'))
        except (TypeError, ValueError):
            probe_sec = 3
        body = (_probe_body_lines(el) + '\n'
                + 'try:\n'
                + '    self.appOperator.click(self.appOperator.getElement(probe))\n'
                + 'except Exception:\n'
                + '    pass')
        return _method_block('click_%s_if_visible' % el, desc, ['timeout_seconds=%d' % probe_sec], body)
    if t == 'hide_keyboard':
        body = ('try:\n'
                + '    if self.appOperator.is_keyboard_shown():\n'
                + '        self.appOperator.hide_keyboard()\n'
                + 'except Exception:\n'
                + '    self.appOperator.press_keycode(4)\n'
                + 'import time\n'
                + 'time.sleep(1)')
        return _method_block('dismiss_keyboard', desc, [], body)
    if t == 'screenshot':
        return _method_block('wait_and_shot', desc, ['tag'],
                             "import time\ntime.sleep(1)\nself.appOperator.get_screenshot(tag)")
    if t == 'tap':
        return _method_block('tap_xy', desc, ['x', 'y'],
                             'self.appOperator.tap(x, y)')
    if t == 'deal_first_launch_dialogs':
        # 首次启动弹窗处理：隐私协议「同意并继续」→ 系统权限「允许」，出现才点、无弹窗自动跳过。
        # 探针自包含（文本定位，不依赖页面元素文件），任何页面都能生成；
        # 已有同名方法的页面（如 demoToolLoginPage）走 TOOL_METHODS 守卫不覆盖。
        body = ('import time\n'
                + 'for _lval, _desc in (\n'
                + '        ("//*[@text=\'同意并继续\']", \'隐私协议弹窗\'),\n'
                + '        ("//*[@text=\'允许\']", \'系统权限弹窗\'),\n'
                + '):\n'
                + '    probe = CreateElement.create(Locator_Type.XPATH, _lval,\n'
                + '                                 wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n'
                + '                                 wait_seconds=2)\n'
                + '    try:\n'
                + '        self.appOperator.click(self.appOperator.getElement(probe))\n'
                + '        time.sleep(1)  # 等弹窗收尾动画，避免点击落到下层页面\n'
                + '    except Exception:\n'
                + '        pass  # 该弹窗未出现，跳过')
        return _method_block('deal_first_launch_dialogs', desc, [], body)
    return None


def case_step_line(step):
    """步骤 → 用例里的一行调用；sleep/custom 返回特殊行（非 page.xxx 调用）"""
    t = step.get('type', '')
    el = step.get('element') or ''
    p = step.get('param') or ''
    if t == 'click':
        return 'page.click_%s()' % el
    if t == 'input':
        return 'page.input_%s(%s)' % (el, _q(p))
    if t == 'long_press':
        return 'page.long_press_%s()' % el
    if t == 'assert_visible':
        return 'page.assert_%s()' % el
    if t == 'assert_text':
        return 'page.assert_%s_text(%s)' % (el, _q(p))
    if t == 'assert_toast':
        return 'page.assert_toast(%s)' % _q(p)
    if t == 'wait_element':
        # 秒数写进用例行所见即所得；非法输入回落页面方法默认值（不带参）
        try:
            return 'page.wait_%s(%d)' % (el, int(p))
        except (TypeError, ValueError):
            return 'page.wait_%s()' % el
    if t == 'assert_gone':
        return 'page.assert_%s_gone()' % el
    if t == 'if_click':
        try:
            return 'page.click_%s_if_visible(%d)' % (el, int(p))
        except (TypeError, ValueError):
            return 'page.click_%s_if_visible()' % el
    if t == 'hide_keyboard':
        return 'page.dismiss_keyboard()'
    if t == 'deal_first_launch_dialogs':
        return 'page.deal_first_launch_dialogs()'
    if t == 'screenshot':
        return 'page.wait_and_shot(%s)' % _q(p)
    if t == 'tap':
        parts = [x.strip() for x in p.split(',') if x.strip()]
        if len(parts) >= 2:
            return 'page.tap_xy(%s, %s)' % (parts[0], parts[1])
        return 'page.tap_xy(%s)' % (parts[0] if parts else '0')
    if t == 'sleep':
        try:
            return 'time.sleep(%s)' % float(p)
        except ValueError:
            return 'time.sleep(%s)' % (p or '1')
    if t == 'custom':
        return p
    return None


# ---------------------------------------------------------------------------
# 页面对象文件生成
# ---------------------------------------------------------------------------
def _ensure_elements_import(content, elements_file, elements_class):
    """页面文件缺失元素类 import 时自动补全（class 行之前）"""
    need = 'from page_objects.app_ui.android.demoProject.elements.%s import %s' % (
        os.path.splitext(elements_file)[0], elements_class)
    if need not in content:
        m = re.search(r'^(class\s+\w+[^\n]*\n)', content, re.MULTILINE)
        if m:
            content = content[:m.start()] + need + '\n\n' + content[m.start():]
    return content


# wait_element/assert_gone/if_click 页面方法里构造探针需要的三件 import（缺了跑不起来）
_PROBE_IMPORTS = [
    'from page_objects.createElement import CreateElement',
    'from page_objects.app_ui.locator_type import Locator_Type',
    'from page_objects.app_ui.wait_type import Wait_Type as Wait_By',
]


def _ensure_probe_imports(content):
    """探针类步骤的页面方法用到 CreateElement/Locator_Type/Wait_By，
    页面文件没 import 时自动补全（class 行之前，插入前压掉块尾空行保持整洁）。"""
    m = re.search(r'^(class\s+\w+[^\n]*\n)', content, re.MULTILINE)
    if not m:
        return content
    lines = [imp for imp in _PROBE_IMPORTS if imp not in content]
    if not lines:
        return content
    head = content[:m.start()].rstrip('\n') + '\n' if content[:m.start()].strip() else ''
    return head + '\n'.join(lines) + '\n' + content[m.start():]


def _upsert_class_method(content, cls, method_blocks, before=None):
    """把 method_blocks 追加到 class cls 的类体；同名方法先移除。
    before 指定方法名时（如 'teardown_class'），新方法插到它前面，保证 teardown 始终在类尾。
    类不存在或没有方法块时原样返回。"""
    if not method_blocks:
        return content
    m = re.search(r'^class %s\b' % re.escape(cls), content, re.MULTILINE)
    if not m:
        return content
    cls_start = m.start()
    tail = content[cls_start + 1:]
    nxt = re.search(r'^class\s', tail, re.MULTILINE)
    cls_end = cls_start + 1 + nxt.start() if nxt else len(content)
    cls_body = content[cls_start:cls_end]

    for block in method_blocks:
        name = re.match(r'%sdef (\w+)' % IND, block).group(1)
        pat = re.compile(r'\n?^    def %s\(.*?(?=\n    def |\nclass |\Z)' % re.escape(name),
                         re.MULTILINE | re.DOTALL)
        cls_body = pat.sub('', cls_body)

    # 插入点：before 方法（如 teardown_class）之前，否则类体末尾
    insert_at = len(cls_body)
    if before:
        bm = re.search(r'^%sdef %s\b' % (IND, re.escape(before)), cls_body, re.MULTILINE)
        if bm:
            insert_at = bm.start()
    new_body = (cls_body[:insert_at].rstrip('\n') + '\n\n' + '\n\n'.join(method_blocks) + '\n\n'
                + cls_body[insert_at:].lstrip('\n'))
    return content[:cls_start] + new_body + content[cls_end:]


# ---------------------------------------------------------------------------
# 用例文件快速追加（「添加元素」弹窗 → 保存并添加到用例）
# ---------------------------------------------------------------------------
def _class_blocks(content):
    """按 class 切块：[(类名, 类体文本)]，供"方法 → 类 → 页面对象"归属解析"""
    blocks = []
    for m in re.finditer(r'^class\s+(\w+)[^\n]*\n', content, re.MULTILINE):
        start = m.start()
        nxt = re.search(r'^class\s', content[m.end():], re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(content)
        blocks.append((m.group(1), content[start:end]))
    return blocks


def _page_class_of(cls_block):
    """类体里 self.page = XxxPage( → 页面类名"""
    m = re.search(r'self\.page\s*=\s*(\w+)\(', cls_block)
    return m.group(1) if m else ''


def find_page_files(page_class):
    """所有定义了 page_class 的页面文件。同名类出现在多个文件时归属不唯一——
    按类名反解会静默取第一个、把页面方法写进错误的文件，因此必须由调用方显式拦下。"""
    if not page_class:
        return []
    pat = re.compile(r'^class\s+%s\b' % re.escape(page_class), re.MULTILINE)
    return [f for f in list_page_files()
            if pat.search(_read(os.path.join(PAGES_DIR, f)))]


def resolve_page(page_class):
    """页面类名 → (页面文件名, 页面引用的元素文件名)。
    找不到、或同名类命中多个文件（归属歧义）时返回 ('', '')，绝不静默取首个。"""
    hits = find_page_files(page_class)
    if len(hits) != 1:
        return '', ''
    content = _read(os.path.join(PAGES_DIR, hits[0]))
    em = re.search(r'from\s+page_objects\.app_ui\.android\.demoProject\.elements\.(\w+)\s+import', content)
    return hits[0], ((em.group(1) + '.py') if em else '')


def _method_body(content, method_name):
    """方法体文本（含缩进），找不到返回 None"""
    m = re.search(r'^%sdef %s\(self\):' % (IND, re.escape(method_name)), content, re.MULTILINE)
    if not m:
        return None
    start = content.find('\n', m.end()) + 1
    tail = content[start:]
    nxt = re.search(r'\n%s(?:def |@|class )' % IND, tail)
    return content[start:start + (nxt.start() + 1 if nxt else len(tail))]


def method_steps(content, method_name):
    """提取方法体里的步骤描述（# 注释行，自动去掉「N.」编号），按出现顺序返回。"""
    body = _method_body(content, method_name)
    if not body:
        return []
    steps = []
    for cm in re.finditer(r'^%s# (.+)$' % (IND * 2), body, re.MULTILINE):
        desc = re.sub(r'^\d+[\.、]\s*', '', cm.group(1).strip())
        if desc:
            steps.append(desc)
    return steps


def element_usage_in_cases(element_name):
    """元素被哪些用例文件使用：统计 page.<操作>_元素名( 调用（click/input/long_press/assert/wait/if_click 等）。
    一个元素可被多个用例、每种操作多次引用——这是三件套的既定数据关系。"""
    pat = re.compile(r'page\.(?:click|input|long_press|assert|wait)_%s(?:_text|_gone|_if_visible)?\('
                     % re.escape(element_name))
    used = []
    for f in list_case_files():
        p = os.path.join(CASES_DIR, f)
        if not os.path.exists(p):
            continue
        n = len(pat.findall(_read(p)))
        if n:
            used.append({'file': f, 'count': n})
    return used


def case_files_info():
    """返回用例文件的"三件套归属"信息，供「添加到元素库」联动：
    [{file, class, methods, method_steps:{方法: [步骤描述...]}, page_class, page_file, elements_file}]
    page_file/elements_file = 该类 self.page 使用的页面对象及其引用的元素文件"""
    infos = []
    for f in list_case_files():
        p = os.path.join(CASES_DIR, f)
        if not os.path.exists(p):
            continue
        content = _read(p)
        # 用例中文名映射（与平台选择用例同源）：文件头「# 用例中文名：xxx」
        m_cn = re.search(r'^#\s*用例中文名[：:]\s*(.+?)\s*$', content, re.MULTILINE)
        cn_name = m_cn.group(1).strip() if m_cn else ''
        for cls_name, block in _class_blocks(content):
            methods = re.findall(r'^%sdef (\w+)\(' % IND, block, re.MULTILINE)
            msteps = {}
            for mname in methods:
                if mname not in ('setup_class', 'teardown_class'):
                    msteps[mname] = method_steps(block, mname)
            page_class = _page_class_of(block)
            hits = find_page_files(page_class)
            page_file, elements_file = resolve_page(page_class)
            infos.append({'file': f, 'class': cls_name, 'methods': methods,
                          'method_steps': msteps,
                          'cn_name': cn_name,
                          'page_class': page_class, 'page_file': page_file,
                          'elements_file': elements_file,
                          'page_ambiguous': hits if len(hits) > 1 else []})
    return infos


def _sync_method_docstring(content, method_name):
    """把方法 docstring 同步为步骤描述汇总（供平台选择用例「场景描述」列展示）。
    步骤描述与方法体 # 注释同源（method_steps）；无步骤（如 setup_class）不动。"""
    steps = method_steps(content, method_name)
    if not steps:
        return content
    m = re.search(r'^%sdef %s\(self\):' % (IND, re.escape(method_name)), content, re.MULTILINE)
    if not m:
        return content
    body_start = content.find('\n', m.end()) + 1
    if body_start <= 0:
        return content
    tail = content[body_start:]
    nxt = re.search(r'\n%s(?:def |@|class )' % IND, tail)
    body_end = body_start + (nxt.start() + 1 if nxt else len(tail))
    body = content[body_start:body_end]
    doc_line = IND * 2 + '"""' + ' → '.join(steps) + '"""\n'
    dm = re.match(r'^%s(?:"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')[ \t]*\n' % IND, body)
    if dm:   # 已有 docstring → 整段替换（追加步骤后保持汇总最新）
        new_body = doc_line + body[dm.end():].lstrip('\n')
    else:    # 没有 docstring → 插到方法体最前（必须是第一条语句）
        new_body = doc_line + body.lstrip('\n')
    return content[:body_start] + new_body + content[body_end:]


def append_code_to_method(case_file, method_name, step, gen_page_method=False, insert_after_step=None):
    """把 step 生成的一行调用代码插入用例文件指定方法体（不破坏文件结构）。

    step：统一步骤结构（type/element/param/desc + case_comment 步骤描述）。
    insert_after_step：0/None = 追加到方法末尾；N = 插到第 N 个步骤之后（漏步骤时补插中间）。
    步骤描述 case_comment 缺省时自动生成（如「点击 login_btn」），作为该步在用例里的注释。
    gen_page_method=True（功能③）时同步把该操作对应的页面方法生成/更新到
    目标用例 self.page 所引用的页面文件（三件套联动），并校验元素文件归属。
    返回 {'ok': bool, 'action': 'appended', 'line':..., 'content':..., 'msg',
          'page_file':..., 'page_method':..., 'page_content':...}
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*\.py$', case_file):
        return {'ok': False, 'msg': '用例文件名不合法'}
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', method_name):
        return {'ok': False, 'msg': '用例方法名不合法'}
    if not isinstance(step, dict) or step.get('type') not in STEP_TYPES:
        return {'ok': False, 'msg': '步骤结构不合法'}
    line = case_step_line(step)
    if not line:
        return {'ok': False, 'msg': '该操作类型没有可追加的代码行'}

    path = os.path.join(CASES_DIR, case_file)
    if not os.path.exists(path):
        return {'ok': False, 'msg': '用例文件 %s 不存在（可在测试平台「APP自动化 → 用例上传」上传，或在 cases/app_ui/android/demoProject/ 下按框架格式创建）' % case_file}
    content = _read(path)
    case_before = content   # 撤销用：写入前快照

    m = re.search(r'^%sdef %s\(self\):' % (IND, re.escape(method_name)), content, re.MULTILINE)
    if not m:
        return {'ok': False, 'msg': '用例文件 %s 里没有方法 %s（先在用例文件里创建该方法再追加）'
                                   % (case_file, method_name)}
    body_start = content.find('\n', m.end()) + 1
    if body_start <= 0:
        return {'ok': False, 'msg': '无法定位方法体'}

    # 步骤描述（step.case_comment）写在代码行上方；缺省自动生成，让每步都有注释可读
    case_comment = ((step.get('case_comment') or '').strip() or step_desc(step)).replace('\n', ' ')
    comment_line = IND * 2 + '# ' + case_comment + '\n'

    tail = content[body_start:]
    nxt = re.search(r'\n%s(?:def |@|class )' % IND, tail)
    body_end = body_start + (nxt.start() + 1 if nxt else len(tail))
    body = content[body_start:body_end]

    # 插入位置：insert_after_step='front' → 第 1 步之前；=N → 第 N 步之后；0/None → 末尾追加。
    # 首次启动弹窗处理语义上只能在所有操作之前，无条件强制前插（防止误插中间/末尾）。
    if step.get('type') == 'deal_first_launch_dialogs':
        insert_after_step = 'front'
    if insert_after_step == 'front':
        anchors = list(re.finditer(r'^%s# ' % (IND * 2), body, re.MULTILINE))
        if anchors:
            first = anchors[0].start()
            new_body = (body[:first].rstrip('\n') + '\n\n' + comment_line + IND * 2 + line + '\n\n'
                        + body[first:].lstrip('\n'))
        else:
            new_body = body.rstrip('\n') + '\n' + comment_line + IND * 2 + line + '\n\n'
    else:
        try:
            after_n = int(insert_after_step or 0)
        except (TypeError, ValueError):
            after_n = 0
        if after_n > 0:
            anchors = list(re.finditer(r'^%s# ' % (IND * 2), body, re.MULTILINE))
            if after_n > len(anchors):
                return {'ok': False, 'msg': '目标方法只有 %d 个步骤，没有第 %d 步' % (len(anchors), after_n)}
            chunk_end = anchors[after_n].start() if after_n < len(anchors) else len(body)
            new_body = (body[:chunk_end].rstrip('\n') + '\n\n' + comment_line + IND * 2 + line + '\n\n'
                        + body[chunk_end:].lstrip('\n'))
        else:
            new_body = body.rstrip('\n') + '\n' + comment_line + IND * 2 + line + '\n\n'
    new_content = content[:body_start] + new_body + content[body_end:]
    new_content = _sync_method_docstring(new_content, method_name)   # docstring 同步步骤描述汇总（场景描述）
    _write(path, new_content)
    result = {'ok': True, 'action': 'appended', 'line': line, 'content': new_content,
              'case_before': case_before,
              'page_file': '', 'page_method': '', 'page_content': '',
              'msg': '代码已追加到 %s::%s：%s' % (case_file, method_name, line)}
    if not gen_page_method:
        return result

    # ---- 功能③：三件套联动，同步生成/更新页面操作方法 ----
    # 1) 目标方法所在类 → 该类使用的页面对象类 → 页面文件 + 其引用的元素文件
    page_class = ''
    for cls_name, block in _class_blocks(new_content):
        if re.search(r'^%sdef %s\(' % (IND, re.escape(method_name)), block, re.MULTILINE):
            page_class = _page_class_of(block)
            break
    hits = find_page_files(page_class)
    if len(hits) > 1:
        return {'ok': False, 'case_before': case_before, 'page_file': '',
                'msg': ('已追加用例行，但页面类 %s 在多个文件里重名（%s），归属不唯一，'
                        '已中止写入页面方法——请先给重名文件改名或删除，再重试'
                        % (page_class, '、'.join(hits)))}
    page_file, elements_file = resolve_page(page_class)
    if not page_file:
        return {'ok': False, 'case_before': case_before, 'page_file': '',
                'msg': ('已追加用例行，但目标用例没有页面对象（找不到 self.page = XxxPage(...)），'
                        '无法生成操作方法——请先给该用例补页面对象文件')}

    method_code = page_method_code(step)
    if not method_code:
        # sleep/custom 等步骤没有对应页面方法，用例行本身就是全部内容
        result['msg'] += '；该操作类型无需页面方法'
        result['page_file'] = page_file
        return result

    # 2) 元素必须在页面引用的元素文件里（一个页面只 import 一个元素文件）
    el_name = step.get('element') or ''
    if el_name and elements_file:
        if el_name not in element_library.list_element_names(elements_file):
            where = [ff for ff in element_library.list_element_files()
                     if el_name in element_library.list_element_names(ff)]
            return {'ok': False, 'case_before': case_before, 'page_file': page_file,
                    'msg': ('已追加用例行，但元素 %s 不在页面 %s 引用的元素文件 %s 里（元素实际在: %s）。'
                            '请把元素保存到 %s（保存元素时「写入元素文件」选它），或在元素库统一后重试'
                            % (el_name, page_file, elements_file,
                               '、'.join(where) or '任何文件中都没有', elements_file))}

    # 3) upsert 页面方法：同名元素操作方法覆盖更新；工具方法已存在则不重复生成
    ppath = os.path.join(PAGES_DIR, page_file)
    pcontent = _read(ppath)
    page_before = pcontent   # 撤销用：页面文件写入前快照（仅本次真正写盘时有效）
    mname = re.match(r'%sdef (\w+)' % IND, method_code).group(1)
    exists = set(re.findall(r'^%sdef (\w+)' % IND, pcontent, re.MULTILINE))
    if not (mname in exists and mname in TOOL_METHODS):
        if elements_file:
            pcontent = _ensure_elements_import(pcontent, elements_file,
                                               element_library.to_class_name(elements_file))
        # 探针类步骤（wait_element/assert_gone/if_click）还要补 CreateElement 等三件 import
        if step.get('type') in PROBE_STEP_TYPES:
            pcontent = _ensure_probe_imports(pcontent)
        pcontent = _upsert_class_method(pcontent, page_class, [method_code])
        _write(ppath, pcontent)
        result['msg'] += '；页面方法 %s() 已生成/更新到 %s' % (mname, page_file)
        result['page_before'] = page_before
    else:
        result['msg'] += '；页面方法 %s() 已存在于 %s（不重复生成）' % (mname, page_file)
        result['page_before'] = ''   # 页面文件未被改动，无需撤销
    result['page_file'] = page_file
    result['page_method'] = mname
    result['page_content'] = pcontent
    return result


if __name__ == '__main__':
    print('现有用例文件:', list_case_files())
    print('现有页面文件:', list_page_files())
