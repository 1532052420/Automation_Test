"""
GUI 元素定位器 · 元素/操作 追加到用例（「添加到元素库」②③ 后端）
统一步骤结构（step dict）→ 把一步操作代码追加到指定用例文件的方法体：
    cases/app_ui/android/demoProject/test_xxx.py                    （用例行追加）
    page_objects/app_ui/android/demoProject/pages/xxxPage.py        （③ 同步生成页面方法）
元素与用例分离 —— 页面方法/用例只引用元素名 self._elements.<name>，不埋定位值。
支持：追加 test 方法体代码行 / 同名页面方法覆盖 / 自动补 import（用例文件本身在平台上传或手动创建）
"""

import ast
import os
import re
import time

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
    # v6.15.33：框架原生手势/设备能力（appOperator 直映射），贴合原框架设定
    'swipe_up', 'swipe_down', 'swipe_left', 'swipe_right',
    'drag_to', 'press_keycode', 'background_app', 'activate_app',
    'toggle_wifi', 'toggle_airplane',
]

# ④断言栏 · 组合断言类型（操作与断言解耦：一步 = 操作 + 断言组合）
# exists/text/gone/visual 绑定本元素；toast/text_page 页面级
ASSERT_KINDS = ('exists', 'text', 'toast', 'text_page', 'text_page_gone', 'gone', 'visual')

# 页面里固定实现的工具方法：已存在则不重复生成
TOOL_METHODS = {'wait_and_shot', 'tap_xy', 'assert_toast', 'dismiss_keyboard',
                'deal_first_launch_dialogs'}

# 需要构造探针元素（CreateElement/Locator_Type/Wait_By）的步骤类型：
# 生成页面方法时页面文件缺这三个 import 会自动补齐
PROBE_STEP_TYPES = {'wait_element', 'assert_gone', 'if_click', 'deal_first_launch_dialogs'}

# 步骤编辑「等待方式」覆盖支持的元素操作步骤（等待条件+最长等待仅本步生效，不改元素全局定义）；
# assert_text 的等待条件固定为存在探针（_assert_probe PRESENCE），仅支持覆盖最长等待秒数
WAIT_OVERRIDE_OPS = {'click', 'input', 'long_press', 'assert_visible', 'assert_text'}
# Wait_Type 的合法值（与 page_objects/app_ui/wait_type.py 同源；页面方法 kwargs 直接传框架）
WAIT_TYPE_VALUES = ('visibility_of', 'presence_of_element_located', 'element_to_be_clickable')


def list_case_files():
    """枚举现有用例文件（test_*.py）；排除用例管理自动生成的历史备份"""
    if not os.path.isdir(CASES_DIR):
        return []
    return sorted(f for f in os.listdir(CASES_DIR)
                  if f.startswith('test_') and f.endswith('.py')
                  and not element_library.is_generated_backup(f))


def create_case_file(stem, cn_name='', page_file='', element_file=''):
    """后台「新建用例」：三件套同建（对齐框架用例包原生创建模型）。

    stem 纯英文（可含数字/下划线，字母开头），test_ 前缀写死（用户写了也剥掉统一补）。
    page_file：留空自动派生 <stem>Page.py；可自定义（Page 后缀写死，写了也剥掉重补）。
               已存在 → 不重建直接绑定复用（页面按屏幕共享）。
    element_file：留空自动派生 <stem>Elements.py；可自定义（Elements 后缀写死）。
               已存在 → 复用。popupElements.py 保留名硬拦。
    中文名选填，写用例文件头「# 用例中文名：xxx」。
    产物绑定齐全：用例 import 页面并实例化 self.page；页面 import 元素类并装配
    self._elements——出生即成链，定位器打开即可录。
    返回 {'ok', 'file', 'msg', 'created': [...], 'reused': {...}}"""
    stem = (stem or '').strip()
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', stem):
        return {'ok': False,
                'msg': '用例名需为纯英文（可含数字），且以字母开头，收到：%r' % (stem or '空')}
    cn_name = (cn_name or '').strip()
    if '\n' in cn_name or '\r' in cn_name:
        return {'ok': False, 'msg': '中文名不能包含换行'}
    stem = re.sub(r'^test_', '', stem, flags=re.IGNORECASE) or stem
    created, reused = [], {}
    page_bind_cls = None   # 页面为已有文件时，绑定元素类以页面既有 import 为準

    # ---- 先定页面（元素的归属跟着页面走：页面复用时以其已有绑定为準） ----
    page_file = os.path.basename(str(page_file or '').strip())
    page_file = re.sub(r'\.py$', '', page_file, flags=re.IGNORECASE) or (stem + 'Page')
    page_file = re.sub(r'page$', '', page_file, flags=re.IGNORECASE) or page_file
    page_file += 'Page.py'
    if not re.match(r'^\w+\.py$', page_file):
        return {'ok': False, 'msg': '页面文件名不合法：%s' % page_file}
    ppath = os.path.join(PAGES_DIR, page_file)
    if os.path.exists(ppath):
        reused['page'] = page_file
        page_cls = _first_class_of(ppath) or _py_class_name(os.path.splitext(page_file)[0])
        # 已有页面绑定的元素文件与本次不一致时，以页面已有绑定为准（页面找元素，import 哪个是哪个）
        em = re.search(r'from\s+page_objects\.app_ui\.android\.demoProject\.elements\.(\w+)\s+import',
                       _read(ppath))
        if em:
            element_file = em.group(1) + '.py'   # 覆盖入参：跟随页面既有绑定
            page_bind_cls = _elements_class_of(element_file) or _py_class_name(
                os.path.splitext(element_file)[0])
    else:
        page_cls = _py_class_name(os.path.splitext(page_file)[0])

    # ---- 再定元素：入参/派生（页面复用且带绑定时已被覆盖为其绑定） ----
    element_file = _norm_elements_filename(element_file, stem + 'Elements')
    if element_file == 'popupElements.py':
        return {'ok': False, 'msg': 'popupElements.py 是弹窗规则库专管文件，不能占用该名字'}
    epath = os.path.join(element_library.ELEMENTS_DIR, element_file)
    if os.path.exists(epath):
        reused['elements'] = element_file
        elem_cls = _elements_class_of(element_file) or _py_class_name(
            os.path.splitext(element_file)[0])
    else:
        elem_cls = _py_class_name(os.path.splitext(element_file)[0])
        with open(epath, 'w', encoding='utf-8') as f:
            f.write('\n'.join([
                '# -*- coding: utf-8 -*-',
                '# 本文件由 自动化后台「新建用例」创建于 %s' % time.strftime('%Y-%m-%d %H:%M:%S'),
                'from page_objects.createElement import CreateElement',
                'from page_objects.app_ui.locator_type import Locator_Type',
                'from page_objects.app_ui.wait_type import Wait_Type as Wait_By',
                '', '',
                'class %s:' % elem_cls,
                '    def __init__(self):',
                '        pass', '']))
        created.append(element_file)

    # ---- 页面落盘（复用则跳过；新建时绑定上一步定下的元素） ----
    if 'page' not in reused:
        if page_bind_cls is None:
            page_bind_cls = elem_cls
        with open(ppath, 'w', encoding='utf-8') as f:
            f.write('\n'.join([
                '# -*- coding: utf-8 -*-',
                '# 页面对象（用例包：%s）' % stem,
                'from page_objects.app_ui.android.demoProject.elements.%s import %s'
                % (os.path.splitext(element_file)[0], page_bind_cls),
                '', '',
                'class %s:' % page_cls,
                '',
                '    def __init__(self, appOperator):',
                '        self.appOperator = appOperator',
                '        self._elements = %s()' % page_bind_cls, '']))
        created.append(page_file)

    # ---- 用例文件：骨架 + 页面 import + setup_class 实例化（出生即绑定） ----
    filename = 'test_' + stem + '.py'
    path = os.path.join(CASES_DIR, filename)
    if os.path.exists(path):
        return {'ok': False, 'msg': '用例文件 %s 已存在（页面/元素未改动）' % filename}
    cls = 'Test' + element_library.to_class_name(stem)
    lines = ['# -*- coding: utf-8 -*-']
    if cn_name:
        lines.append('# 用例中文名：%s' % cn_name)
    lines += ['# 本文件由 自动化后台「新建用例」创建于 %s' % time.strftime('%Y-%m-%d %H:%M:%S'),
              'import time',
              'from base.app_ui.android.demoProject.app_ui_android_demoProject_client'
              ' import APP_UI_Android_demoProject_Client',
              'from page_objects.app_ui.android.demoProject.pages.%s import %s'
              % (os.path.splitext(page_file)[0], page_cls),
              '', '',
              'class %s:' % cls,
              '',
              '    def setup_class(self):',
              '        self.appOperator = APP_UI_Android_demoProject_Client(is_need_kill_app=False).appOperator',
              '        self.page = %s(self.appOperator)' % page_cls,
              '',
              '    def test_%s(self):' % stem,
              '        """待添加步骤"""',
              '        pass', '']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    created.append(filename)

    parts = []
    parts.append('已新建用例 %s（含页面绑定 self.page）' % filename)
    parts.append('%s页面 %s%s' % ('新建 ' if page_file in created else '复用已有 ',
                                  page_file, '（绑定元素 %s）' % element_file))
    parts.append('%s元素 %s' % ('新建 ' if element_file in created else '复用已有 ',
                                element_file))
    return {'ok': True, 'file': filename, 'created': created, 'reused': reused,
            'msg': '；'.join(parts)}


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


def _asserts_of(step):
    """步骤里的组合断言列表（四栏改版）：非法项剔除。
    键兼容：前端断言卡下发 v 键（{v:'exists',...}），统一归一为 type——
    历史上 v/type 不兼容曾致断言全部静默丢失（v6.14.52 修复、54 回滚复发）。"""
    out = []
    for a in step.get('asserts') or []:
        if isinstance(a, dict):
            t = a.get('type') or a.get('v')
            if t in ASSERT_KINDS:
                a2 = dict(a)
                a2['type'] = t
                out.append(a2)
    return out


def _asserts_desc_suffix(step):
    n = len(_asserts_of(step))
    return ('· 含%d断言' % n) if n else ''


def _visual_baseline_path(step, el):
    """视觉断言基线路径：elements/baselines/<元素文件名>/<元素名>.png（随包进 git）"""
    ef = (step.get('element_file') or '').strip()
    ef = os.path.splitext(os.path.basename(ef))[0] if ef else 'baselines'
    return ('page_objects/app_ui/android/demoProject/elements/baselines/%s/%s.png'
            % (ef, el or 'element'))


def _assert_body_lines(step, el):
    """④断言栏组合断言 → 页面方法断言段代码行（failures 收集式，全量执行）"""
    lines = []
    for i, a in enumerate(_asserts_of(step), 1):
        no = '断言%d' % i
        t = a['type']
        if t == 'exists':
            try:
                w = int(a.get('wait'))
            except (TypeError, ValueError):
                w = 3
            lines.append(_probe_line(el, w))
            lines.append("self.appOperator.assert_exists_or_record(failures, '%s·存在', probe)" % no)
        elif t == 'text':
            try:
                w = int(a.get('wait'))
            except (TypeError, ValueError):
                w = 3
            lines.append(_probe_line(el, w))
            lines.append("self.appOperator.assert_text_or_record(failures, '%s·文本', probe, expected=%s)"
                         % (no, _q(a.get('text') or '')))
        elif t == 'toast':
            lines.append("self.appOperator.assert_toast_or_record(failures, '%s·Toast', %s, wait_seconds=5)"
                         % (no, _q(a.get('toast') or '')))
        elif t == 'text_page':
            lines.append("self.appOperator.assert_page_text_or_record(failures, '%s·页面文本', %s, wait_seconds=5)"
                         % (no, _q(a.get('text') or '')))
        elif t == 'text_page_gone':
            lines.append("self.appOperator.assert_page_text_gone_or_record(failures, '%s·文案消失', %s, wait_seconds=5)"
                         % (no, _q(a.get('text') or '')))
        elif t == 'gone':
            try:
                w = int(a.get('wait'))
            except (TypeError, ValueError):
                w = 2
            lines.append(_probe_line(el, w, visible=False))
            lines.append("self.appOperator.assert_gone_or_record(failures, '%s·消失', probe, wait_seconds=%d)"
                         % (no, w))
        elif t == 'visual':
            try:
                th = float(a.get('threshold'))
            except (TypeError, ValueError):
                th = 0.95
            if (a.get('asset') or '').strip():
                # 视觉资产版：基线/范围/忽略区域/模式全部来自资产库（视觉断言采集产出），
                # 执行器按资产配置自行取实际图（元素探针/区域裁剪/整屏），无需元素探针行
                lines.append("self.appOperator.assert_visual_asset_record(failures, '%s·视觉资产', %s, threshold=%.2f)"
                             % (no, _q(a['asset'].strip()), th))
            else:
                lines.append(_probe_line(el, 3))
                lines.append("self.appOperator.assert_visual_or_record(failures, '%s·视觉', probe,\n"
                             "                                        baseline=%s, threshold=%.2f)"
                             % (no, _q(_visual_baseline_path(step, el)), th))
    return lines


def _probe_line(el, wait_seconds, visible=True):
    """断言段探针行（VISIBILITY/PRESENCE 等待）"""
    wt = 'VISIBILITY_OF' if visible else 'PRESENCE_OF_ELEMENT_LOCATED'
    return ("probe = CreateElement.create(self._elements.%s.locator_type,\n"
            "                             self._elements.%s.locator_value,\n"
            "                             wait_type=Wait_By.%s,\n"
            "                             wait_seconds=%d)") % (el, el, wt, wait_seconds)


def step_desc(step):
    """步骤的可读描述（后端兜底；前端通常会自己生成并让用户可改）"""
    if step.get('desc'):
        return step['desc'].strip() + _asserts_desc_suffix(step)
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
        'swipe_up': '上滑【%s】' % el,
        'swipe_down': '下滑【%s】' % el,
        'swipe_left': '左滑【%s】' % el,
        'swipe_right': '右滑【%s】' % el,
        'drag_to': '拖拽【%s】到【%s】' % (el, p),
        'press_keycode': '按下按键（键码%s）' % p,
        'background_app': '应用退后台%s秒' % p,
        'activate_app': '拉起应用 %s' % p,
        'toggle_wifi': '切换WiFi开关',
        'toggle_airplane': '切换飞行模式开关',
    }.get(t, '未定义步骤') + _asserts_desc_suffix(step)


def _method_block(name, doc, args, body):
    """生成一个页面方法代码块（类内 4 空格缩进，方法体内 8 空格，多行 body 逐行缩进）"""
    args_str = ', '.join(['self'] + (args or []))
    body_ind = '\n'.join((IND * 2 + line) if line.strip() else line for line in body.split('\n'))
    return '%sdef %s(%s):\n%s"""%s"""\n%s\n' % (
        IND, name, args_str, IND * 2, doc, body_ind)


def _shot_line(desc):
    """断言成功后的缩略图截图行（appOperator.get_screenshot 自动 attach 到 allure）。
    返回不带缩进的行——缩进由 _method_block 统一叠加（自带缩进会叠成 16 空格导致 IndentationError）"""
    return "self.appOperator.get_screenshot(%s)" % repr(('断言·' + desc)[:40])


def _probe_body_lines(element_name, seconds_var='timeout_seconds'):
    """构造探针元素代码体：复用元素库定义的定位（元素改定义方法不用改）。
    seconds_var：等待秒数变量名，须与页面方法签名参数一致。"""
    return (
        "probe = CreateElement.create(self._elements.%s.locator_type,\n"
        "                             self._elements.%s.locator_value,\n"
        "                             wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n"
        "                             wait_seconds=%s)"
    ) % (element_name, element_name, seconds_var)


def _has_wait_override(step):
    """步骤是否带等待覆盖（合法秒数或合法等待条件）"""
    if step.get('type') not in WAIT_OVERRIDE_OPS:
        return False
    if re.match(r'^\d+$', str(step.get('wait_sec') or '').strip()):
        return True
    return str(step.get('wait_type') or '').strip() in WAIT_TYPE_VALUES


# 等待覆盖版页面方法的公共体前缀：按本步参数克隆元素（不改元素全局定义，框架按克隆定义等待）
_WAIT_EL_OVERRIDE_BODY = (
    "el = self._elements.%s\n"
    "if wait_seconds is not None or wait_type is not None:\n"
    "    el = CreateElement.create(el.locator_type, el.locator_value, "
    "wait_type=wait_type or el.wait_type, "
    "wait_seconds=wait_seconds if wait_seconds is not None else el.wait_seconds, "
    "desc=getattr(el, 'desc', None))")


def page_method_code(step, force_wait_capable=False):
    """步骤 → 页面方法代码块；sleep/custom 返回 None（不需要页面方法）。
    step.comment（操作备注）优先作为方法 docstring，缺省用步骤描述。
    四栏改版：step.asserts 非空时生成「操作段+断言段」组合方法（全量执行，失败汇总）。
    force_wait_capable：等待覆盖版签名（wait_seconds/wait_type kwargs）——元素操作步骤带
    等待覆盖时生成；不带覆盖时传 True 可维持已升级签名（避免同方法多用例共用时降级）。"""
    if _asserts_of(step):
        return _combo_method_code(step)
    t = step.get('type', '')
    el = step.get('element') or ''
    desc = (step.get('comment') or '').strip() or step_desc(step)
    capable = force_wait_capable or _has_wait_override(step)
    if t == 'click':
        if capable:
            return _method_block('click_%s' % el, desc, ['wait_seconds=None', 'wait_type=None'],
                                 (_WAIT_EL_OVERRIDE_BODY % el) + '\nself.appOperator.click(el)')
        return _method_block('click_%s' % el, desc, [],
                             'self.appOperator.click(self._elements.%s)' % el)
    if t == 'input':
        if capable:
            return _method_block('input_%s' % el, desc, ['text', 'wait_seconds=None', 'wait_type=None'],
                                 (_WAIT_EL_OVERRIDE_BODY % el) + '\nself.appOperator.sendText(el, text)')
        return _method_block('input_%s' % el, desc, ['text'],
                             'self.appOperator.sendText(self._elements.%s, text)' % el)
    if t == 'long_press':
        if capable:
            return _method_block('long_press_%s' % el, desc, ['wait_seconds=None', 'wait_type=None'],
                                 (_WAIT_EL_OVERRIDE_BODY % el) + '\nself.appOperator.touch_long_press(el, duration_sconds=2)')
        return _method_block('long_press_%s' % el, desc, [],
                             'self.appOperator.touch_long_press(self._elements.%s, duration_sconds=2)' % el)
    if t == 'assert_visible':
        if capable:
            return _method_block('assert_%s' % el, desc, ['wait_seconds=None', 'wait_type=None'],
                                 (_WAIT_EL_OVERRIDE_BODY % el) + '\nself.appOperator.getElement(el)\n%s' % _shot_line(desc))
        return _method_block('assert_%s' % el, desc, [],
                             'self.appOperator.getElement(self._elements.%s)\n%s' % (el, _shot_line(desc)))
    if t == 'assert_text':
        # v6.15.73：改用 assert_text_or_fail——实际值入 allure JSON，报告「实际结果」显示真实读值
        # v6.16.11：失败消息参数化——同一方法可被多个断言步骤以不同文本复用，报告文案随 expected 走
        # 等待覆盖：探针语义固定 PRESENCE，仅透传最长等待秒数（wait_seconds or 3 = 框架原默认）
        if '「' in desc:
            pre, rest = desc.rsplit('「', 1)
            tail = rest[rest.find('」'):] if '」' in rest else ''
        else:
            pre, tail = desc + '（', '）'
        body = "self.appOperator.assert_text_or_fail(self._elements.%s, expected, '%s「' + expected + '%s')" % (el, pre, tail)
        if capable:
            body = ("el = self._elements.%s\n"
                    "if wait_seconds is not None:\n"
                    "    el = CreateElement.create(el.locator_type, el.locator_value, "
                    "wait_type=el.wait_type, wait_seconds=wait_seconds, desc=getattr(el, 'desc', None))\n"
                    "self.appOperator.assert_text_or_fail(el, expected, '%s「' + expected + '%s', wait_seconds=wait_seconds or 3)"
                    ) % (el, pre, tail)
            return _method_block('assert_%s_text' % el, desc, ['expected', 'wait_seconds=None'], body)
        return _method_block('assert_%s_text' % el, desc, ['expected'], body)
    if t == 'assert_toast':
        # v6.15.73：改用 assert_toast_or_fail——结果入 allure JSON
        # v6.16.11：失败消息参数化（同 assert_text）
        if '「' in desc:
            pre, rest = desc.rsplit('「', 1)
            tail = rest[rest.find('」'):] if '」' in rest else ''
        else:
            pre, tail = desc + '「', '」'
        return _method_block('assert_toast', desc, ['text'],
                             "self.appOperator.assert_toast_or_fail(text, '%s「' + text + '%s')" % (pre, tail))
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
                + "                                   '等待%s秒内元素仍可见' % wait_seconds)\n"
                + _shot_line(desc))
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
    if t in ('swipe_up', 'swipe_down', 'swipe_left', 'swipe_right'):
        fn = {'swipe_up': 'touch_element_up_slide', 'swipe_down': 'touch_element_down_slide',
              'swipe_left': 'touch_element_left_slide', 'swipe_right': 'touch_element_right_slide'}[t]
        try:
            dur = int(step.get('param'))
        except (TypeError, ValueError):
            dur = 500
        return _method_block('%s_%s' % (t, el), desc, ['duration=%d' % dur],
                             'self.appOperator.%s(self._elements.%s, duration=duration)' % (fn, el))
    if t == 'drag_to':
        dst = (step.get('param') or '').strip()
        return _method_block('drag_%s_to_%s' % (el, dst), desc, [],
                             'self.appOperator.touch_a_element_drag_to_another_element('
                             'self._elements.%s, self._elements.%s)' % (el, dst))
    if t == 'press_keycode':
        return _method_block('press_key', desc, ['keycode'],
                             'self.appOperator.press_keycode(keycode)')
    if t == 'background_app':
        return _method_block('background_run', desc, ['seconds'],
                             'self.appOperator.background_app(seconds)')
    if t == 'activate_app':
        return _method_block('activate', desc, ['app_id'],
                             'self.appOperator.activate_app(app_id)')
    if t == 'toggle_wifi':
        return _method_block('toggle_wifi', desc, [],
                             'self.appOperator.toggle_wifi()')
    if t == 'toggle_airplane':
        return _method_block('toggle_airplane_mode', desc, [],
                             'self.appOperator.toggle_airplane_mode()')
    return None




def _combo_method_code(step):
    """组合断言方法（四栏改版核心）：复用既有单类型方法体作为「操作段」，包上
    try/except 记入 failures（主断言失败不停），后接 ④断言栏的断言段（逐条全量执行），
    末尾 failures 非空则抛 AssertionError 汇总明细。sleep/custom 无页面方法，忽略组合。"""
    t = step.get('type', '')
    el = step.get('element') or ''
    base = page_method_code({k: v for k, v in step.items() if k != 'asserts'})
    if not base:
        return None
    m = re.match(r'\s*def (\w+)\((.*?)\):\n\s*"""(.*?)"""\n([\s\S]*)$', base)
    if not m:
        return None
    name, args_str, doc, body = m.group(1), m.group(2), m.group(3), m.group(4).rstrip('\n')
    desc = (step.get('comment') or '').strip() or step_desc(step)
    lines = ['failures = []', 'try:']
    lines += ['    ' + ln if ln.strip() else ln for ln in body.split('\n')]
    lines += ["except Exception as _e:",
              "    self.appOperator.get_screenshot(%s)" % _q('操作失败_' + TYPE_NAMES_CN.get(t, t)),
              "    failures.append('主操作: %s' % str(_e)[:120])"
              ]
    lines += _assert_body_lines(step, el)
    lines += ['if failures:',
              "    raise AssertionError('%d 项断言未通过：\\n%s' % (len(failures), '\\n'.join(failures)))"]
    body_new = '\n'.join(lines)
    args = [a.strip() for a in args_str.split(',') if a.strip() and a.strip() != 'self']
    return _method_block(name, doc, args, body_new)


TYPE_NAMES_CN = {
    'click': '点击', 'input': '输入', 'long_press': '长按', 'tap': '坐标点击',
    'screenshot': '截图', 'sleep': '固定等待', 'wait_element': '轮询等待出现',
    'if_click': '出现才点击', 'custom': '自定义代码',
    'assert_visible': '断言存在', 'assert_text': '断言文本',
    'assert_toast': '断言Toast', 'assert_gone': '断言消失',
    'swipe_up': '上滑', 'swipe_down': '下滑', 'swipe_left': '左滑', 'swipe_right': '右滑',
    'drag_to': '拖拽到元素', 'press_keycode': '按键',
    'background_app': '退后台', 'activate_app': '拉起应用',
    'toggle_wifi': '切换WiFi', 'toggle_airplane': '切换飞行模式',
}


def _split_call_kwargs(args):
    """调用参数串拆分：尾部关键字参数（wait_seconds=8）与位置参数分离。
    引号内逗号/等号不切分；位置参数以 ', ' 重组（与原串等价）。
    返回 (位置参数串, {关键字名: 值(去引号)})"""
    parts, cur, q = [], '', None
    for ch in args:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in '\'"':
            cur += ch
            q = ch
        elif ch == ',':
            parts.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    pos, kw = [], {}
    for p in parts:
        m = re.match(r'^(\w+)\s*=\s*(.+)$', p)
        if m and p[0] not in '\'"':
            kw[m.group(1)] = _unq(m.group(2))
        else:
            pos.append(p)
    return ', '.join(pos), kw


def _step_wait_kwargs(step):
    """步骤的等待覆盖 → 生成调用行尾的 kwargs 串（', wait_seconds=8, wait_type=...'）。
    非法秒数/越界等待条件静默忽略（与 wait_element 非法回落默认值同一口径）。
    assert_text 等待条件固定为存在探针，只覆盖秒数。"""
    t = step.get('type', '')
    extra = ''
    ws = str(step.get('wait_sec') or '').strip()
    if t in WAIT_OVERRIDE_OPS and re.match(r'^\d+$', ws):
        extra += ', wait_seconds=%d' % int(ws)
    if t in WAIT_OVERRIDE_OPS - {'assert_text'}:
        wt = str(step.get('wait_type') or '').strip()
        if wt in WAIT_TYPE_VALUES:
            extra += ", wait_type='%s'" % wt
    return extra


def _wait_of_parsed(t, kwargs):
    """反解出的关键字参数 → 步骤的等待覆盖字段（wait_type/wait_sec，无覆盖为空串）"""
    if t not in WAIT_OVERRIDE_OPS:
        return '', ''
    wt = kwargs.get('wait_type', '')
    ws = kwargs.get('wait_seconds', '')
    return (wt if wt in WAIT_TYPE_VALUES else '', str(int(ws)) if re.match(r'^\d+$', str(ws)) else '')


def case_step_line(step, var='page'):
    """步骤 → 用例里的一行调用；sleep/custom 返回特殊行（非 page.xxx 调用）。
    var=目标页面对象变量名：'page' 走既有局部别名风格 page.xxx()（兼容历史用例），
    其他（多页面挂接的 page2/page3…）生成 self.<var>.xxx() 直调。"""
    t = step.get('type', '')
    el = step.get('element') or ''
    p = step.get('param') or ''
    pfx = 'page.' if var == 'page' else 'self.%s.' % var
    if t == 'click':
        return '%sclick_%s(%s)' % (pfx, el, _step_wait_kwargs(step).lstrip(', '))
    if t == 'input':
        return '%sinput_%s(%s%s)' % (pfx, el, _q(p), _step_wait_kwargs(step))
    if t == 'long_press':
        return '%slong_press_%s(%s)' % (pfx, el, _step_wait_kwargs(step).lstrip(', '))
    if t == 'assert_visible':
        return '%sassert_%s(%s)' % (pfx, el, _step_wait_kwargs(step).lstrip(', '))
    if t == 'assert_text':
        return '%sassert_%s_text(%s%s)' % (pfx, el, _q(p), _step_wait_kwargs(step))
    if t == 'assert_toast':
        return '%sassert_toast(%s)' % (pfx, _q(p))
    if t == 'wait_element':
        # 秒数写进用例行所见即所得；非法输入回落页面方法默认值（不带参）
        try:
            return '%swait_%s(%d)' % (pfx, el, int(p))
        except (TypeError, ValueError):
            return '%swait_%s()' % (pfx, el)
    if t == 'assert_gone':
        return '%sassert_%s_gone()' % (pfx, el)
    if t == 'if_click':
        try:
            return '%sclick_%s_if_visible(%d)' % (pfx, el, int(p))
        except (TypeError, ValueError):
            return '%sclick_%s_if_visible()' % (pfx, el)
    if t == 'hide_keyboard':
        return '%sdismiss_keyboard()' % pfx
    if t == 'deal_first_launch_dialogs':
        return '%sdeal_first_launch_dialogs()' % pfx
    if t == 'screenshot':
        return '%swait_and_shot(%s)' % (pfx, _q(p))
    if t == 'tap':
        parts = [x.strip() for x in p.split(',') if x.strip()]
        if len(parts) >= 2:
            return '%stap_xy(%s, %s)' % (pfx, parts[0], parts[1])
        return '%stap_xy(%s)' % (pfx, (parts[0] if parts else '0'))
    if t in ('swipe_up', 'swipe_down', 'swipe_left', 'swipe_right'):
        try:
            return '%s%s_%s(%d)' % (pfx, t, el, int(p))
        except (TypeError, ValueError):
            return '%s%s_%s()' % (pfx, t, el)
    if t == 'drag_to':
        return '%sdrag_%s_to_%s()' % (pfx, el, (p or 'target'))
    if t == 'press_keycode':
        return '%spress_key(%s)' % (pfx, int(str(p).strip()))
    if t == 'background_app':
        return '%sbackground_run(%s)' % (pfx, int(str(p).strip()))
    if t == 'activate_app':
        return '%sactivate(%s)' % (pfx, _q(p))
    if t == 'toggle_wifi':
        return '%stoggle_wifi()' % pfx
    if t == 'toggle_airplane':
        return '%stoggle_airplane_mode()' % pfx
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
def _elements_class_of(elements_file):
    """元素文件的真实类名：直接读文件 class 行（唯一可信来源）。
    派生规则（to_class_name）与前端 capFirst 规则在多词文件名上不一致，
    曾导致追加步骤时插入错误类名 import 使整条用例 ImportError。读不到再回退派生。"""
    path = os.path.join(element_library.ELEMENTS_DIR, elements_file)
    m = re.search(r'^\s*class\s+(\w+)', _read(path), re.MULTILINE) if os.path.isfile(path) else None
    return m.group(1) if m else element_library.to_class_name(elements_file)


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


def _page_targets_of(cls_block):
    """类体里全部页面对象实例化行 self.<var> = XxxPage(...) →
    [{var, cls, page_file, elements_file}]（按出现顺序）。
    框架原生允许一个用例挂多个页面（self.page / self.page2 …），v6.15.33 起
    弹窗按此支持选择目标页面；类名归属歧义的目标剔除（与 resolve_page 同防误写策略）。"""
    targets = []
    for m in re.finditer(r'self\.(\w+)\s*=\s*(\w+)\s*\(', cls_block):
        var, cls = m.group(1), m.group(2)
        if any(t['cls'] == cls for t in targets):
            continue
        page_file, elements_file = resolve_page(cls)
        if page_file:
            targets.append({'var': var, 'cls': cls,
                            'page_file': page_file, 'elements_file': elements_file})
    return targets


def _wire_page_into_class(content, page_file, method_name=''):
    """把页面挂接进用例类：缺 import 补 import、缺实例化在 setup_class 末尾补
    self.<var> = <Cls>(self.appOperator)（类里没有任何页面对象时补 self.page）。
    挂进 method_name 所在类（多类文件不串类；缺省挂第一个类）。
    返回 (新内容, var)；页面文件不存在返回 ('', '')。"""
    ppath = os.path.join(PAGES_DIR, page_file)
    if not os.path.isfile(ppath):
        return '', ''
    stem = os.path.splitext(page_file)[0]
    cls = _first_class_of(ppath)
    if not cls:
        return '', ''
    imp = 'from page_objects.app_ui.android.demoProject.pages.%s import %s' % (stem, cls)
    if imp not in content:
        imports = list(re.finditer(r'^(?:from\s+\S+\s+import\s+[^\n]+|import\s+[^\n]+)$',
                                   content, re.MULTILINE))
        if imports:
            pos = imports[-1].end()
            content = content[:pos] + '\n' + imp + content[pos:]
        else:
            content = '# -*- coding: utf-8 -*-\n' + imp + '\n\n' + content
    blocks = _class_blocks(content)
    block = None
    if method_name:
        for _cls_name, b in blocks:
            if re.search(r'^%sdef %s\(' % (IND, re.escape(method_name)), b, re.MULTILINE):
                block = b
                break
    if block is None and blocks:
        block = blocks[0][1]
    if block is None:
        return '', ''
    used = set(re.findall(r'self\.(\w+)\s*=', block))
    var = 'page' if 'page' not in used else 'page2'
    n = 2
    while var in used:
        n += 1
        var = 'page%d' % n
    assign = '%sself.%s = %s(self.appOperator)' % (IND * 2, var, cls)
    m = re.search(r'^%sdef setup_class\(self\):' % IND, block, re.MULTILINE)
    if m:
        tail = block[m.start():]
        nxt = re.search(r'\n%s(?:def |@)|\nclass ' % IND, tail)
        body_end = m.start() + (nxt.start() + 1 if nxt else len(tail))
        seg = block[:body_end].rstrip('\n')
        rest = block[body_end:].lstrip('\n')
        # 与下一方法之间补空行，贴合框架 def 间空行风格（setup_class 后还有方法时）
        sep = '\n\n' if rest.startswith(('%sdef ' % IND, '@')) else '\n'
        new_block = seg + '\n' + assign + sep + rest
    else:
        head = re.search(r'^class\s+\w+[^\n]*\n', block, re.MULTILINE)
        new_block = (block[:head.end()].rstrip('\n') + '\n\n'
                     + IND + 'def setup_class(self):\n' + assign + '\n' + block[head.end():].lstrip('\n'))
    content = content.replace(block, new_block, 1)
    return content, var


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


def _unq(a):
    """剥掉一层成对引号（调用参数/关键字参数值的字面量还原）"""
    a = a.strip()
    if len(a) >= 2 and a[0] == a[-1] and a[0] in '\'"':
        return a[1:-1]
    return a


def _call_to_step(mod, fn, args):
    """调用行 → (type, element, param)：与 case_step_line 的生成规则互逆反解。"""
    if mod == 'time' and fn == 'sleep':
        return 'sleep', '', _unq(args)
    if mod != 'page':
        return 'custom', '', args
    if fn == 'dismiss_keyboard':
        return 'hide_keyboard', '', ''
    if fn == 'deal_first_launch_dialogs':
        return 'deal_first_launch_dialogs', '', ''
    if fn == 'assert_toast':
        return 'assert_toast', '', _unq(args)
    if fn == 'wait_and_shot':
        return 'screenshot', '', _unq(args)
    if fn == 'tap_xy':
        return 'tap', '', ', '.join(a.strip() for a in args.split(',') if a.strip())
    if fn.endswith('_if_visible'):
        return 'if_click', fn[:-len('_if_visible')], _unq(args)
    if fn.startswith('assert_'):
        rest = fn[len('assert_'):]
        if rest.endswith('_text'):
            return 'assert_text', rest[:-len('_text')], _unq(args)
        if rest.endswith('_gone'):
            return 'assert_gone', rest[:-len('_gone')], ''
        return 'assert_visible', rest, ''
    for pre, t in (('input_', 'input'), ('long_press_', 'long_press'),
                   ('wait_', 'wait_element'), ('click_', 'click')):
        if fn.startswith(pre):
            return t, fn[len(pre):], (_unq(args) if t in ('input', 'wait_element') else '')
    return 'custom', '', args


def parse_case_steps(content, method_name):
    """反解方法体为结构化步骤：注释行=步骤描述，其后的 page.xxx(...) / time.sleep(...)
    调用行反解出 type/element/param（与 case_step_line 词表互逆）。返回
    [{'desc', 'call', 'type', 'element', 'param'}]，按出现顺序；docstring 与赋值行跳过。"""
    body = _method_body(content, method_name)
    if not body:
        return []
    steps, cur, in_doc = [], None, False

    def _flush():
        nonlocal cur
        if cur is not None:
            steps.append(cur)
            cur = None

    for raw in body.splitlines():
        s = raw.strip()
        if in_doc:
            if s.endswith('"""') or s.endswith("'''"):
                in_doc = False
            continue
        if s.startswith('"""') or s.startswith("'''"):
            # 单行 docstring 直接跳过；跨行进入 doc 状态直到闭合
            if not (len(s) >= 6 and s.endswith(s[:3])):
                in_doc = True
            continue
        if not s or s == 'page = self.page' or s.startswith('@') or s.startswith('def '):
            continue
        if s.startswith('#'):
            _flush()
            cur = {'desc': re.sub(r'^#\s*(?:\d+[.、]\s*)?', '', s).strip(), 'call': '',
                   'type': 'custom', 'element': '', 'param': ''}
            continue
        m = re.match(r'^(page|time)\.([\w]+)\s*\((.*)\)\s*$', s)
        if not m:
            continue   # 其他语句（赋值/续行等）不进时间轴
        if cur is None:
            cur = {'desc': '', 'call': '', 'type': 'custom', 'element': '', 'param': ''}
        cur['call'] = s
        pos, kwargs = _split_call_kwargs(m.group(3).strip())
        cur['type'], cur['element'], cur['param'] = _call_to_step(m.group(1), m.group(2), pos)
        # 等待覆盖（wait_seconds/wait_type kwargs）反解：仅元素操作步骤携带，无覆盖为空串
        cur['wait_type'], cur['wait_sec'] = _wait_of_parsed(cur['type'], kwargs)
        _flush()
    _flush()
    return steps


def replace_case_steps(content, method_name, steps):
    """用结构化步骤重建用例方法体（parse_case_steps 的逆操作，写回用例文件用）：
    - docstring = 各步描述以「 → 」串联（与定位器生成格式一致）
    - 每步 = 注释行（首个带「1.」编号）+ case_step_line 生成的一行调用
    - 方法体外其余内容（导入/类/其他方法）原样保留
    返回 (new_content, msg)；方法不存在返回 (None, msg)。调用方须自行 ast 校验后落盘。"""
    m = re.search(r'^%sdef %s\(self\):' % (IND, re.escape(method_name)), content, re.MULTILINE)
    if not m:
        return None, '用例文件里没有方法 %s' % method_name
    body_start = content.find('\n', m.end()) + 1
    tail = content[body_start:]
    nxt = re.search(r'\n%s(?:def |@|class )' % IND, tail)
    body_end = body_start + (nxt.start() + 1 if nxt else len(tail))

    descs = []
    lines = [IND * 2 + 'page = self.page', '']
    for i, step in enumerate(steps):
        if step.get('type') not in STEP_TYPES:
            return None, '第 %d 步类型不合法：%s' % (i + 1, step.get('type'))
        desc = (step.get('desc') or '').strip().replace('\n', ' ') or step_desc(step)
        line = case_step_line(step)
        if not line:
            return None, '第 %d 步无法生成代码行' % (i + 1)
        descs.append(desc)
        lines.append(IND * 2 + ('# 1. ' if i == 0 else '# ') + desc)
        lines.append(IND * 2 + line)
    doc = ' → '.join(descs) if descs else '（无步骤）'
    new_body = '\n'.join(lines) + '\n\n'
    return content[:body_start] + '%s"""%s"""\n%s' % (IND * 2, doc, new_body) + content[body_end:], ''


# 老版（无等待参数）页面方法的标准生成形态：签名 + 调用体严格匹配，均对得上才允许升级改写
# （防止覆盖用户手工改过的方法）；assert_visible 块内还带截图行，一并按体匹配
_OLD_STD_BODY = {
    'click': (r'\(self\)', r'self\.appOperator\.click\(self\._elements\.\w+\)'),
    'input': (r'\(self, text\)', r'self\.appOperator\.sendText\(self\._elements\.\w+, text\)'),
    'long_press': (r'\(self\)', r'self\.appOperator\.touch_long_press\(self\._elements\.\w+, duration_sconds=2\)'),
    'assert_visible': (r'\(self\)', r'self\.appOperator\.getElement\(self\._elements\.\w+\)'),
    'assert_text': (r'\(self, expected\)', r"self\.appOperator\.assert_text_or_fail\(self\._elements\.\w+, expected, '[^\n]*'\)"),
}
_WAIT_MNAME = {'click': 'click_%s', 'input': 'input_%s', 'long_press': 'long_press_%s',
               'assert_visible': 'assert_%s', 'assert_text': 'assert_%s_text'}


def _page_method_block(content, mname):
    """页面文件里取方法：返回 (def 行参数串, 方法块全文)；方法不存在返回 (None, '')"""
    m = re.search(r'^%sdef %s\((self[^\n]*)\)[ \t]*:' % (IND, re.escape(mname)), content, re.MULTILINE)
    if not m:
        return None, ''
    nxt = re.search(r'\n%s(?:def |@|class )' % IND, content[m.end():])
    end = m.end() + (nxt.start() + 1 if nxt else len(content) - m.end())
    return m.group(1), content[m.start():end]


def sync_page_methods_for_wait(content, method_name, steps):
    """步骤编辑保存前把页面方法同步到「等待覆盖」形态（api_case_steps_save 专用）。

    - 步骤带等待覆盖（wait_sec/wait_type）→ 对应页面方法升级为可接受 wait_seconds/wait_type
      的签名：方法体内按本步参数克隆元素（复用定位与描述，不改元素全局定义），框架按克隆
      定义等待；assert_text 仅透传秒数（探针条件固定 PRESENCE）。
    - 已是覆盖签名（def 行含 wait_seconds=None）→ 按最新步骤重建（同步 docstring 与元素），
      绝不降级回老签名——页面被多个用例共用，其他用例可能仍以 kwargs 调用。
    - 老签名方法仅在严格匹配标准生成形态时改写；对不上（手工改过）→ 报错，调用方须中止保存，
      否则用例以 kwargs 调用老签名会 TypeError。
    返回 (ok, msg)；页面无需改动时返回 (True, '')。页面文件写盘前 ast 校验。"""
    cls_block = next((b for _name, b in _class_blocks(content)
                      if re.search(r'^%sdef %s\(' % (IND, re.escape(method_name)), b, re.MULTILINE)), None)
    if cls_block is None:
        return False, '用例文件里没有方法 %s' % method_name
    page_class = _page_class_of(cls_block)
    if not page_class:
        return False, '用例方法未绑定页面对象（self.page = XxxPage(...)），无法同步等待覆盖'
    page_file, elements_file = resolve_page(page_class)
    if not page_file:
        return False, '解析不到页面文件（页面类 %s），无法同步等待覆盖' % page_class
    ppath = os.path.join(PAGES_DIR, page_file)
    if not os.path.isfile(ppath):
        return False, '页面文件不存在：%s' % page_file
    pcontent = _read(ppath)

    blocks, touched, errs = [], [], []
    seen = set()
    for st in steps or []:
        t, el = st.get('type', ''), st.get('element') or ''
        if t not in WAIT_OVERRIDE_OPS or not el:
            continue
        mname = _WAIT_MNAME[t] % el
        if mname in seen:
            continue
        seen.add(mname)
        args, _block = _page_method_block(pcontent, mname)
        if args is not None and 'wait_seconds=None' in args:
            blocks.append(page_method_code(st, force_wait_capable=True))
            touched.append(mname)
            continue
        if not _has_wait_override(st):
            continue   # 无覆盖且未升级过：保持原样（老签名照常工作）
        if args is None:
            blocks.append(page_method_code(st, force_wait_capable=True))
            touched.append(mname)
            continue
        sig_re, body_re = _OLD_STD_BODY[t]
        if re.search(r'def %s%s' % (re.escape(mname), sig_re), _block) and \
                re.search(body_re + r'[ \t]*$', _block, re.MULTILINE):
            blocks.append(page_method_code(st, force_wait_capable=True))
            touched.append(mname)
        else:
            errs.append('页面方法 %s() 非标准生成形态（可能手工改过），无法升级等待参数'
                        '——请在 %s 手动为其添加 wait_seconds/wait_type 可选参数' % (mname, page_file))
    if errs:
        return False, '；'.join(errs)
    if not blocks:
        return True, ''
    if elements_file:
        pcontent = _ensure_elements_import(pcontent, elements_file, _elements_class_of(elements_file))
    pcontent = _ensure_probe_imports(pcontent)
    pcontent = _upsert_class_method(pcontent, page_class, blocks)
    try:
        ast.parse(pcontent)
    except SyntaxError as e:
        return False, '页面方法升级后语法校验失败（页面文件未改动）：%s' % e.msg
    _write(ppath, pcontent)
    return True, '页面方法已支持等待覆盖：%s（%s）' % ('、'.join(touched), page_file)


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
                          'page_ambiguous': hits if len(hits) > 1 else [],
                          'page_targets': _page_targets_of(block)})
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
    # docstring 在方法体第一层（IND*2 缩进）。历史 bug：这里曾用 ^IND（4 空格）锚定，
    # 永远匹配不上 → 替换分支成死代码，每次保存都新插一层、旧层永远堆着。循环剥掉全部旧层再插新的。
    dm = None
    rest = body
    while True:
        m2 = re.match(r'^%s(?:"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')[ \t]*\n' % (IND * 2,), rest)
        if not m2:
            break
        dm = m2
        rest = rest[dm.end():]
    new_body = doc_line + rest.lstrip('\n')
    return content[:body_start] + new_body + content[body_end:]


def append_code_to_method(case_file, method_name, step, gen_page_method=False,
                          insert_after_step=None, page_file=''):
    """把 step 生成的一行调用代码插入用例文件指定方法体（不破坏文件结构）。

    step：统一步骤结构（type/element/param/desc + case_comment 步骤描述）。
    insert_after_step：0/None = 追加到方法末尾；N = 插到第 N 个步骤之后（漏步骤时补插中间）。
    步骤描述 case_comment 缺省时自动生成（如「点击 login_btn」），作为该步在用例里的注释。
    gen_page_method=True（功能③）时同步把该操作对应的页面方法生成/更新到目标页面文件。
    page_file（v6.15.33）：指定目标页面文件——用例已实例化的页面直接命中（调用前缀用
    对应 self.<var>）；未实例化的页面自动挂接（补 import + setup_class 实例化，var 取
    page2/page3…）；留空回落该用例 self.page 的既有行为。
    返回 {'ok': bool, 'action': 'appended', 'line':..., 'content':..., 'msg',
          'page_file':..., 'page_method':..., 'page_content':..., 'page_var'}
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*\.py$', case_file):
        return {'ok': False, 'msg': '用例文件名不合法'}
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', method_name):
        return {'ok': False, 'msg': '用例方法名不合法'}
    if not isinstance(step, dict) or step.get('type') not in STEP_TYPES:
        return {'ok': False, 'msg': '步骤结构不合法'}
    # sleep/custom 无页面方法承载断言段：挂断言属非法组合，明确报错（前端已禁用，此处兜底）
    if step.get('type') in ('sleep', 'custom') and _asserts_of(step):
        return {'ok': False, 'msg': '固定等待/自定义代码步骤不支持挂断言（无元素操作主体）——请去掉断言后保存'}
    # 数字类参数校验：sleep/tap 参数原样拼接进代码，非数字会生成 NameError 级损坏用例——入口拦截
    if step.get('type') == 'sleep':
        try:
            float((step.get('param') or '').strip())
        except (TypeError, ValueError):
            return {'ok': False, 'msg': '固定等待秒数需为数字（示例：3 或 1.5），收到：%r'
                                           % (step.get('param') or '')}
    if step.get('type') == 'tap':
        parts = [x.strip() for x in (step.get('param') or '').split(',') if x.strip()]
        ok_xy = len(parts) == 2
        if ok_xy:
            try:
                float(parts[0]); float(parts[1])
            except ValueError:
                ok_xy = False
        if not ok_xy:
            return {'ok': False, 'msg': '坐标点击参数需为 x,y 数字格式（示例：320,540），收到：%r'
                                           % (step.get('param') or '')}
    if step.get('type') in ('press_keycode', 'background_app'):
        try:
            int(str(step.get('param') or '').strip())
        except (TypeError, ValueError):
            return {'ok': False, 'msg': '按键码/后台秒数需为整数（按键示例：4；后台示例：5，-1 为完全停用），收到：%r'
                                           % (step.get('param') or '')}
    if step.get('type') == 'drag_to' and not (step.get('param') or '').strip():
        return {'ok': False, 'msg': '拖拽需要参数：目标元素名（须已保存在元素库）'}
    if step.get('type') == 'activate_app' and not (step.get('param') or '').strip():
        return {'ok': False, 'msg': '拉起应用需要参数：应用包名（如 com.recordlife.kuaige）'}

    path = os.path.join(CASES_DIR, case_file)
    if not os.path.exists(path):
        return {'ok': False, 'msg': '用例文件 %s 不存在（可在测试平台「APP自动化 → 用例上传」上传，或在 cases/app_ui/android/demoProject/ 下按框架格式创建）' % case_file}
    content = _read(path)
    case_before = content   # 撤销用：写入前快照

    # ---- 目标页面解析（v6.15.33 多页面）：方法所在类 → 已实例化页面；指定页面未实例化则自动挂接 ----
    def _class_block_of_method(c):
        for cls_name, block in _class_blocks(c):
            if re.search(r'^%sdef %s\(' % (IND, re.escape(method_name)), block, re.MULTILINE):
                return block
        return None

    block = _class_block_of_method(content)
    targets = _page_targets_of(block) if block else []
    target, wired = None, ''
    want = os.path.basename((page_file or '').strip())
    if want:
        target = next((t for t in targets if t['page_file'] == want), None)
        if target is None:
            ppath = os.path.join(PAGES_DIR, want)
            if not os.path.isfile(ppath):
                return {'ok': False, 'msg': '所选页面文件不存在：%s' % want}
            cls = _first_class_of(ppath)
            hits = find_page_files(cls)
            if len(hits) > 1:
                return {'ok': False, 'msg': ('页面类 %s 在多个文件里重名（%s），import 归属不唯一，'
                                             '已中止——请先给重名文件改名' % (cls, '、'.join(hits)))}
            wired_content, var = _wire_page_into_class(content, want, method_name)
            if not wired_content:
                return {'ok': False, 'msg': '页面 %s 自动接入失败（无法定位类或 setup_class）' % want}
            content = wired_content
            wired = var
            target = {'var': var, 'cls': cls, 'page_file': want,
                      'elements_file': (page_elements_map().get(want) or '')}
    elif targets:
        target = next((t for t in targets if t['var'] == 'page'), targets[0])
    var = target['var'] if target else 'page'

    line = case_step_line(step, var)
    if not line:
        return {'ok': False, 'msg': '该操作类型没有可追加的代码行'}

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
            # 末尾追加：注释接续现有步骤数编号（首步 # 1. 由用例包生成，此后 2、3… 连续）
            step_no = len(list(re.finditer(r'^%s# ' % (IND * 2), body, re.MULTILINE))) + 1
            numbered = (IND * 2 + '# %d. %s\n' % (step_no, case_comment)) if step_no > 1 else comment_line
            new_body = body.rstrip('\n') + '\n' + numbered + IND * 2 + line + '\n\n'
    new_content = content[:body_start] + new_body + content[body_end:]
    new_content = _sync_method_docstring(new_content, method_name)   # docstring 同步步骤描述汇总（场景描述）
    _write(path, new_content)
    result = {'ok': True, 'action': 'appended', 'line': line, 'content': new_content,
              'case_before': case_before,
              'page_file': '', 'page_method': '', 'page_content': '',
              'page_var': var,
              'msg': '代码已追加到 %s::%s：%s' % (case_file, method_name, line)}
    if wired:
        result['msg'] += '；已自动把 %s 接进用例（补 import，setup_class 里加 self.%s = %s(self.appOperator)）' % (target['cls'], wired, target['cls'])
    if not gen_page_method:
        return result

    # ---- 功能③：三件套联动，同步生成/更新页面操作方法（写入目标页面文件） ----
    if not target:
        return {'ok': False, 'case_before': case_before, 'page_file': '',
                'msg': ('已追加用例行，但目标用例没有页面对象（找不到 self.page = XxxPage(...)），'
                        '无法生成操作方法——请在「写入页面文件」下拉选择目标页面后重试')}
    page_class, page_file, elements_file = target['cls'], target['page_file'], target['elements_file']

    method_code = page_method_code(step)
    if not method_code:
        # sleep/custom 等步骤没有对应页面方法，用例行本身就是全部内容
        result['msg'] += '；该操作类型无需页面方法'
        result['page_file'] = page_file
        return result

    # 2) 元素必须在页面引用的元素文件里（一个页面只 import 一个元素文件）；
    #    drag_to 的目标元素（param）同样要落位到该文件
    need_names = [step.get('element') or '']
    if step.get('type') == 'drag_to' and (step.get('param') or '').strip():
        need_names.append((step.get('param') or '').strip())
    for el_name in need_names:
        if not (el_name and elements_file):
            continue
        if el_name in element_library.list_element_names(elements_file):
            continue
        # 元素不在页面引用的元素文件里时不再中断三件套：自动把元素整行从其所在文件
        # 复制/覆盖到目标文件（同名覆盖，用户口径「重复元素覆盖就好了」）；任何文件里都没有才报错
        srcs = [ff for ff in element_library.list_element_files()
                if el_name in element_library.list_element_names(ff)]
        pref = step.get('element_file') or ''
        if pref in srcs:                       # 本步刚保存的文件是最新定义，优先从这复制
            srcs = [pref] + [f for f in srcs if f != pref]
        if not srcs:
            return {'ok': False, 'case_before': case_before, 'page_file': page_file,
                    'msg': ('已追加用例行，但元素 %s 还没保存进任何元素文件，无法生成页面方法'
                            '——请重新保存一次本步操作（三件套会把元素一并入库）' % el_name)}
        cr = element_library.copy_element(srcs[0], elements_file, el_name)
        if not cr.get('ok'):
            return {'ok': False, 'case_before': case_before, 'page_file': page_file,
                    'msg': '已追加用例行，但元素自动同步失败：%s' % cr.get('msg', '')}
        result['msg'] += '；元素 %s 已自动同步到 %s（页面引用的元素文件，取自 %s，同名覆盖）' \
            % (el_name, elements_file, srcs[0])

    # 3) upsert 页面方法：同名元素操作方法覆盖更新；工具方法已存在则不重复生成
    ppath = os.path.join(PAGES_DIR, page_file)
    pcontent = _read(ppath)
    page_before = pcontent   # 撤销用：页面文件写入前快照（仅本次真正写盘时有效）
    mname = re.match(r'%sdef (\w+)' % IND, method_code).group(1)
    exists = set(re.findall(r'^%sdef (\w+)' % IND, pcontent, re.MULTILINE))
    if not (mname in exists and mname in TOOL_METHODS):
        if elements_file:
            pcontent = _ensure_elements_import(pcontent, elements_file,
                                               _elements_class_of(elements_file))
        # 探针类步骤（wait_element/assert_gone/if_click）还要补 CreateElement 等三件 import
        if step.get('type') in PROBE_STEP_TYPES or _asserts_of(step):
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


# ---------------------------------------------------------------------------
# 新建用例包 · 服务端权威组装（元素按页面组织 + 查重复用，v6.15.30）
# ---------------------------------------------------------------------------
def page_elements_map():
    """所有页面文件 → 其 import 的元素文件名（没 import 元素文件为 ''）。
    供「新建用例包」选择已有页面时自动对齐元素文件，以及 /api/library 的 referenced 计算。"""
    out = {}
    for f in list_page_files():
        content = _read(os.path.join(PAGES_DIR, f))
        em = re.search(r'from\s+page_objects\.app_ui\.android\.demoProject\.elements\.(\w+)\s+import', content)
        out[f] = (em.group(1) + '.py') if em else ''
    return out


def _first_class_of(path, fallback=''):
    """py 文件里定义的首个类名（页面/元素文件都是单类约定）；读不到回退 fallback"""
    if os.path.isfile(path):
        m = re.search(r'^\s*class\s+(\w+)', _read(path), re.MULTILINE)
        if m:
            return m.group(1)
    return fallback


def _find_dup_in_content(content, locator_type, value):
    """元素文件内容里查找相同「定位方式+定位值」的元素名（比对规则与 find_duplicate 一致：
    文件里存的是转义后的值，比对时同样转义）。返回元素名或 None"""
    pat = re.compile(
        r'^\s*self\.(%s)\s*=\s*CreateElement\.create\(\s*'
        r'Locator_Type\.(\w+)\s*,\s*\'((?:[^\'\\]|\\.)*)\'' % element_library._NAME_CLS,
        re.MULTILINE)
    escaped = element_library._escape(value)
    for m in pat.finditer(content):
        if m.group(2).upper() == (locator_type or '').upper() and m.group(3) == escaped:
            return m.group(1)
    return None


def _extract_element_line(path, name):
    """从元素文件里抽某元素的完整定义行（copy_element 同源逻辑的内存版）"""
    if not os.path.isfile(path):
        return ''
    m = re.search(r'^[ \t]*self\.%s\s*=.*$' % re.escape(name), _read(path), re.MULTILINE)
    return m.group(0) if m else ''


def _norm_pkg_base(base):
    """用例名规范化：剥 test_ 前缀与 .py 后缀、非法字符转下划线（与前端 newCaseBase 同规则）"""
    base = re.sub(r'\.py$', '', str(base or '').strip(), flags=re.IGNORECASE)
    base = re.sub(r'^test_', '', base, flags=re.IGNORECASE)
    return re.sub(r'[^\w]', '_', base).strip('_')


def _norm_elements_filename(name, default_stem):
    """新建元素文件名规范化：剥 .py、非法字符转 _、保证 Elements 结尾（与前端 pkgElementFileName 同规则）"""
    raw = re.sub(r'\.py$', '', str(name or '').strip(), flags=re.IGNORECASE)
    raw = re.sub(r'[^\w]', '_', raw)
    raw = re.sub(r'_+', '_', raw).strip('_') or default_stem
    return re.sub(r'elements?$', '', raw, flags=re.IGNORECASE) + 'Elements.py'


def _py_class_name(stem):
    """类名派生 + 数字开头兜底（Python 类名不允许数字开头，如用例名 123login → El123login）"""
    cls = element_library.to_class_name(stem)
    return cls if re.match(r'^[A-Za-z_]', cls) else 'El' + cls


def assemble_case_package(base, cn_name='', step=None, element=None,
                          element_file='', element_file_new=True,
                          page_file='', page_file_new=True,
                          elements_dir=None, pages_dir=None):
    """「新建用例包」服务端权威组装：前端只传意图（用例名/步骤/元素/落点选择），
    三件套文件内容由本函数生成——统一查重与页面复用语义，前端不再自行拼文件。

    元素查重复用（避免重复元素，定义只存在一份）：
    - 目标元素文件里已有相同「定位方式+定位值」→ 复用库内元素名，不写重复行；
    - 其他元素文件有同定位 → 复用其元素名，定义行原样复制进目标文件（保持页面静态绑定）；
    - 目标文件里同名元素但定位不同 → 硬拦（共享元素文件禁止静默覆盖，防牵连其他用例）。

    页面复用（元素1 · 用例多 · 页面操作多）：
    - 选已有页面 → 页面方法 upsert 进该文件，用例 import 已有页面类；
    - 新建页面 → 按用例名派生 <base>Page.py 并 import 元素文件。

    产物只含「新建或内容有变化」的文件，交给 import_case_package 原子入库
    （语法校验 + 覆盖备份一条龙）。纯内存组装不落盘，可离线单测。
    返回 {'ok', 'msg', 'files', 'element_final', 'reused', 'notes', ...}"""
    edir = elements_dir or element_library.ELEMENTS_DIR
    pdir = pages_dir or PAGES_DIR
    notes = []
    base = _norm_pkg_base(base)
    if not base or not re.match(r'^\w+$', base):
        return {'ok': False, 'msg': '用例名不合法（字母/数字/下划线）'}
    if step is not None and (not isinstance(step, dict) or step.get('type') not in STEP_TYPES):
        return {'ok': False, 'msg': '步骤结构不合法'}

    # ---- 落点解析与校验 ----
    if element_file_new:
        element_file = _norm_elements_filename(element_file, base + 'Elements')
    else:
        element_file = os.path.basename(str(element_file or '').strip())
        if not re.match(r'^\w+\.py$', element_file) or element_file == element_library.POPUP_FILE:
            return {'ok': False, 'msg': '元素文件名不合法：%s' % (element_file or '空')}
    epath = os.path.join(edir, element_file)
    elem_file_existed = os.path.isfile(epath)

    if page_file_new:
        page_file = os.path.basename(str(page_file or '').strip() or (base + 'Page.py'))
        if not re.match(r'^\w+\.py$', page_file):
            return {'ok': False, 'msg': '页面文件名不合法：%s' % page_file}
    else:
        page_file = os.path.basename(str(page_file or '').strip())
        if not re.match(r'^\w+\.py$', page_file) or not os.path.isfile(os.path.join(pdir, page_file)):
            return {'ok': False, 'msg': '所选页面文件不存在：%s' % (page_file or '空')}

    # ---- 元素：查重 → 终名 → 定义行（全程内存，不落盘） ----
    element_final, elem_line, reused, elem_content = '', '', False, None
    if element:
        el_name = (element.get('name') or '').strip()
        lt = (element.get('locator_type') or '').strip().upper()
        value = (element.get('value') or '').strip()
        if not element_library.is_valid_element_name(el_name):
            return {'ok': False, 'msg': '元素名称不合法：%s（字母/中文/下划线开头，非 Python 关键字）'
                                           % (el_name or '空')}
        if not lt or not value:
            return {'ok': False, 'msg': '定位方式/定位值不能为空'}
        target_content = element_library._ensure_imports(element_library._read(epath)) \
            if elem_file_existed else None
        # 1) 目标文件内同定位 → 直接复用库内定义
        if target_content is not None:
            hit = _find_dup_in_content(target_content, lt, value)
            if hit:
                element_final, reused = hit, True
                notes.append('元素「%s」与 %s 里「%s」同定位：已复用原定义，不写重复行'
                             % (el_name, element_file, hit))
        # 2) 其他文件同定位 → 复用其名，定义行复制进目标文件
        if not element_final:
            cross = element_library.find_duplicate(lt, value, elements_dir=edir)
            if cross and cross['filename'] != element_file:
                element_final, reused = cross['name'], True
                elem_line = _extract_element_line(os.path.join(edir, cross['filename']), cross['name'])
                notes.append('元素与 %s 里「%s」同定位：已复用元素名「%s」，定义行复制到 %s（页面绑定不变）'
                             % (cross['filename'], cross['name'], cross['name'], element_file))
            else:
                element_final = el_name
        # 3) 终名已在目标文件：同定位=无需写行；异定位=硬拦（禁静默覆盖）
        if target_content is not None:
            exist_m = re.search(
                r'^[ \t]*self\.%s\s*=\s*CreateElement\.create\(\s*Locator_Type\.(\w+)\s*,\s*'
                r'\'((?:[^\'\\]|\\.)*)\'' % re.escape(element_final),
                target_content, re.MULTILINE)
            if exist_m:
                if exist_m.group(1).upper() == lt and exist_m.group(2) == element_library._escape(value):
                    elem_line = ''      # 同名同定位 → 定义已在，无需变化
                else:
                    return {'ok': False, 'msg': (
                        '元素文件 %s 里已有同名元素「%s」但定位不同（%s: %s）——'
                        '共享元素文件禁止静默覆盖，请换一个元素名'
                        % (element_file, element_final, exist_m.group(1), exist_m.group(2)))}
        if not elem_line and not reused:
            # 全库无同定位（或目标为全新文件）→ 按用户输入生成定义行
            wait_type = (element.get('wait_type') or 'VISIBILITY_OF').strip() or 'VISIBILITY_OF'
            elem_line = element_library.element_line(
                element_final, lt, value, wait_type, element.get('wait_seconds'),
                None, cn_name=(element.get('cn_name') or '').strip() or None)
        # ---- 目标元素文件内容组装（内存；只有内容有变化才进产物） ----
        if elem_line:
            if target_content is None:
                elem_content = (element_library.HEADER
                                + 'class %s:\n' % _py_class_name(os.path.splitext(element_file)[0])
                                + '    def __init__(self):\n' + elem_line + '\n')
                notes.append('已新建元素文件 %s（%s）' % (element_file, element_final)
                             if not elem_file_existed else
                             '元素文件 %s 缺失已重建（%s）' % (element_file, element_final))
            else:
                elem_content, action = element_library.merge_element_line(
                    target_content, element_final, elem_line)
                if action == 'invalid':
                    return {'ok': False, 'msg': '元素文件 %s 缺少 __init__ 方法，无法追加元素' % element_file}
                if action == 'inserted':
                    notes.append('元素「%s」已追加到 %s' % (element_final, element_file))
        # 查重复用后统一回填终名：页面方法/用例行必须引用库内真实元素名
        # （否则页面方法 self._elements.<用户输入名> 指向不存在的元素 → 运行时 AttributeError）
        if step is not None and element:
            step = dict(step, element=element_final)

    # ---- 页面方法（后端权威实现，与追加用例路径同一份代码） ----
    method_block = page_method_code(step) if step else None

    # ---- 页面：新建模板 / 已有 upsert（内存组装） ----
    page_content = None
    if page_file_new:
        page_class = _py_class_name(os.path.splitext(page_file)[0])
        bind_elements = element is not None or elem_content is not None or elem_file_existed
        lines = [
            '# -*- coding: utf-8 -*-',
            '# 页面对象（用例包：%s）' % base,
        ]
        if bind_elements:
            elem_cls = _py_class_name(os.path.splitext(element_file)[0])
            lines += [
                'from page_objects.app_ui.android.demoProject.elements.%s import %s'
                % (os.path.splitext(element_file)[0], elem_cls),
                '', '',
                'class %s:' % page_class,
                '',
                '    def __init__(self, appOperator):',
                '        self.appOperator = appOperator',
                '        self._elements = %s()' % elem_cls,
                '',
            ]
        else:
            # 纯特殊操作首步（收起键盘等，无元素）：页面不绑元素文件，后续步骤按需补 import
            lines += ['', '', 'class %s:' % page_class, '',
                      '    def __init__(self, appOperator):',
                      '        self.appOperator = appOperator', '']
        if method_block:
            lines += [method_block, '']
        page_content = '\n'.join(lines)
        notes.append('已新建页面对象 %s（%s）' % (page_file, page_class))
    else:
        ppath = os.path.join(pdir, page_file)
        pcontent = _read(ppath)
        page_class = _first_class_of(ppath, '')
        if not page_class:
            return {'ok': False, 'msg': '页面文件 %s 里没有类定义，无法追加页面方法' % page_file}
        if method_block:
            mname = re.match(r'%sdef (\w+)' % IND, method_block).group(1)
            exists = set(re.findall(r'^%sdef (\w+)' % IND, pcontent, re.MULTILINE))
            if mname in exists and mname in TOOL_METHODS:
                notes.append('页面方法 %s() 已存在于 %s（工具方法不重复生成）' % (mname, page_file))
            else:
                em = re.search(r'from\s+page_objects\.app_ui\.android\.demoProject\.elements\.(\w+)\s+import',
                               pcontent)
                page_elem_file = (em.group(1) + '.py') if em else ''
                if element and page_elem_file and element_file != page_elem_file:
                    return {'ok': False, 'msg': (
                        '页面 %s 绑定元素文件 %s，元素须写入该文件（保存前会自动对齐）'
                        % (page_file, page_elem_file))}
                use_ef = page_elem_file or element_file
                pcontent = _ensure_elements_import(pcontent, use_ef, _elements_class_of(use_ef))
                if step and (step.get('type') in PROBE_STEP_TYPES or _asserts_of(step)):
                    pcontent = _ensure_probe_imports(pcontent)
                page_content = _upsert_class_method(pcontent, page_class, [method_block])
                notes.append('页面方法 %s() 已追加到 %s（%s）' % (mname, page_file, page_class))
        else:
            notes.append('该步骤无页面方法（%s），用例行即全部内容'
                         % TYPE_NAMES_CN.get(step.get('type', ''), '自定义'))

    # ---- 用例文件（页面类名用页面文件里的真实类名） ----
    if not page_file_new:
        page_class = _first_class_of(os.path.join(pdir, page_file), '')
        if not page_class:
            return {'ok': False, 'msg': '页面文件 %s 里没有类定义' % page_file}
    step_comment = ((step or {}).get('comment') or '').strip() or (step_desc(step) if step else '')
    first_line = case_step_line(step) if step else 'pass  # 占位'
    cap_camel = ''.join(p[:1].upper() + p[1:] for p in base.split('_') if p)
    head = ['# -*- coding: utf-8 -*-']
    if cn_name:
        head.append('# 用例中文名：%s' % cn_name)
    head += [
        '# 用例包 %s · %s' % (base, step_comment),
        '# 流程：',
        '# 1. 拉起快歌主页面',
        '# 2. %s' % step_comment,
        'import time',
        'import allure',
        'from base.app_ui.android.demoProject.app_ui_android_demoProject_client '
        'import APP_UI_Android_demoProject_Client',
        'from page_objects.app_ui.android.demoProject.pages.%s import %s'
        % (os.path.splitext(page_file)[0], page_class),
        '', '',
        "@allure.parent_suite('快歌APP自动化')",
        "@allure.suite('%s')" % base,
        'class Test%s:' % cap_camel,
        '',
        '    def setup_class(self):',
        '        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App',
        '        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)',
        '        self.appOperator = self.demoProjectClient.appOperator',
        "        self.appOperator.start_activity('com.recordlife.kuaige', "
        "'com.recordlife.kuaige.feature.main.MainActivity')",
        '        time.sleep(3)',
        '        self.page = %s(self.appOperator)' % page_class,
        '',
        "    @allure.title('%s')" % step_comment,
        '    def test_%s(self):' % base,
        '        """%s"""' % step_comment,
        '        page = self.page',
        '',
        '        # 1. %s' % step_comment,
        '        %s' % first_line,
        '',
        '    def teardown_class(self):',
        '        self.appOperator.close_app()',
    ]
    case_py = '\n'.join(head) + '\n'

    # ---- 产物：只收「新建或内容有变化」的文件（未变化的已有文件不重复入库，避免备份噪声） ----
    files = [{'dir': CASES_DIR, 'name': 'test_%s.py' % base, 'content': case_py}]
    if page_content is not None:
        files.append({'dir': PAGES_DIR, 'name': page_file, 'content': page_content})
    if elem_content is not None:
        files.append({'dir': element_library.ELEMENTS_DIR, 'name': element_file, 'content': elem_content})
    for f in files:
        try:
            compile(f['content'], f['name'], 'exec')
        except SyntaxError as e:
            return {'ok': False, 'msg': '组装产物语法错误（%s 第 %s 行：%s）——已取消保存'
                                           % (f['name'], e.lineno, e.msg)}
    return {'ok': True, 'base': base, 'files': files, 'element_final': element_final,
            'reused': reused, 'notes': notes,
            'element_file': element_file, 'page_file': page_file, 'page_class': page_class}


if __name__ == '__main__':
    print('现有用例文件:', list_case_files())
    print('现有页面文件:', list_page_files())
