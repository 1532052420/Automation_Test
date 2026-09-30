# -*- coding: utf-8 -*-
"""AppUI 用例编排 · 代码生成（YAML 编排 → 框架三件套，接入现有 Appium/pytest 链路）

对应 testhub SceneBuilder 的「ui_flow 执行」在本框架的等价物：
框架执行面只认 cases/pages/elements 三类 Python 文件，因此编排保存时把 YAML
编译为页面文件 + 用例文件（元素文件复用定位器/元素管理维护的同一份元素库，
不生成、只引用），生成文件自动进入「选择用例」树与现有执行/报告链路。

复用 element_locator.case_generator 的步骤映射（page_method_code / case_step_line），
步骤语义与定位器「添加到用例」完全一致；生成文件带标记头，删除编排用例时按标记清理。
"""
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# case_generator.py 用隐式相对导入（import element_library），需先把其目录加入 sys.path
_ELEMENT_LOCATOR_DIR = os.path.join(BASE_DIR, 'element_locator')
if _ELEMENT_LOCATOR_DIR not in sys.path:
    sys.path.insert(0, _ELEMENT_LOCATOR_DIR)

from element_locator.case_generator import (
    PROBE_STEP_TYPES, STEP_TYPES, case_step_line, page_method_code, step_desc,
)
from element_locator.element_library import to_class_name

CASES_DIR = os.path.join(BASE_DIR, 'cases', 'app_ui', 'android', 'demoProject')
PAGES_DIR = os.path.join(BASE_DIR, 'page_objects', 'app_ui', 'android', 'demoProject', 'pages')
PAGES_PKG = 'page_objects.app_ui.android.demoProject.pages'
ELEMENTS_PKG = 'page_objects.app_ui.android.demoProject.elements'

GENERATED_MARK = '# 由平台「用例编排」生成'

# 步骤类型 → 是否必须带元素 / 参数（词表即 case_generator.STEP_TYPES）
_NEEDS_ELEMENT = {'click', 'input', 'long_press', 'assert_visible', 'assert_text',
                  'wait_element', 'assert_gone', 'if_click'}
_NEEDS_PARAM = {'input', 'assert_text', 'assert_toast', 'sleep', 'tap', 'custom'}

# setup_class 启动参数默认值（与定位器临时用例模板一致；用例 YAML 可覆盖）
DEFAULT_APP_PACKAGE = 'com.recordlife.kuaige'
DEFAULT_APP_ACTIVITY = 'com.recordlife.kuaige.feature.main.MainActivity'


def case_base(cid):
    """编排用例的稳定文件基名（不随改名漂移）：orch{id}"""
    return 'orch%d' % cid


def node_of(cid):
    """编译产物的 pytest nodeid（套件执行按此展开）"""
    b = case_base(cid)
    return 'cases/app_ui/android/demoProject/test_%s.py::TestOrch%d::test_orch_%d' % (b, cid, cid)


def _page_class(cid):
    return 'Orch%dPage' % cid


def _generated_paths(cid):
    b = case_base(cid)
    return (os.path.join(CASES_DIR, 'test_%s.py' % b),
            os.path.join(PAGES_DIR, '%sPage.py' % b))


def is_generated(path):
    """文件是否为本模块生成（头部带标记），删除编排用例时只清理这类文件"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return GENERATED_MARK in f.read(200)
    except OSError:
        return False


def remove_generated(cid):
    """删除编排用例时清理其生成文件（只删带标记的，防误删手写文件）"""
    for p in _generated_paths(cid):
        if os.path.exists(p) and is_generated(p):
            os.unlink(p)


def validate_steps(steps):
    """校验步骤列表（类型/元素/参数完备性），返回错误信息或 None"""
    if not steps:
        return '请至少编排一个步骤'
    for i, s in enumerate(steps, 1):
        t = s.get('type')
        if t not in STEP_TYPES:
            return '第 %d 步操作类型不合法: %r' % (i, t)
        el, p = (s.get('element') or '').strip(), (s.get('param') or '').strip()
        if t in _NEEDS_ELEMENT and not el:
            return '第 %d 步（%s）需要选择元素' % (i, step_desc(s))
        if t in _NEEDS_PARAM and not p:
            return '第 %d 步（%s）需要填写参数' % (i, step_desc(s))
        if t == 'tap':
            parts = [x for x in p.split(',') if x.strip()]
            if len(parts) < 2 or not all(x.strip().isdigit() for x in parts[:2]):
                return '第 %d 步坐标格式应为「x,y」（数字）' % i
    return None


def compile_case(case):
    """把编排用例编译为页面文件 + 用例文件（幂等全量覆盖），返回 pytest nodeid。

    case 字段：id / name / elements_file（元素库文件名，如 kuaigeLoginElements.py）/
              steps: [{type, element, param, desc}] / app_package / app_activity（可选）
    """
    cid, name = case['id'], case.get('name') or ('编排用例%d' % cid)
    elements_file = case.get('elements_file')
    steps = case.get('steps') or []
    package = case.get('app_package') or DEFAULT_APP_PACKAGE
    activity = case.get('app_activity') or DEFAULT_APP_ACTIVITY

    elem_class = to_class_name(elements_file)
    page_class = _page_class(cid)
    b = case_base(cid)

    # ---- 页面文件：步骤 → 页面方法（同名方法取最后一次，与定位器更新语义一致）----
    m_order, m_map = [], {}
    for s in steps:
        block = page_method_code(s)
        if not block:
            continue
        mn = (re.search(r'def (\w+)', block) or [None, None])[1]
        if not mn:
            continue
        if mn not in m_map:
            m_order.append(mn)
        m_map[mn] = block
    probe_imports = ('\nfrom page_objects.createElement import CreateElement\n'
                     'from page_objects.app_ui.locator_type import Locator_Type\n'
                     'from page_objects.app_ui.wait_type import Wait_Type as Wait_By\n'
                     if any(s.get('type') in PROBE_STEP_TYPES for s in steps) else '')
    page_py = ('# -*- coding: utf-8 -*-\n'
               + '%s（用例 #%d %s）；手改会在下次保存时被覆盖\n'
               % (GENERATED_MARK, cid, name)
               + 'from %s.%s import %s\n' % (ELEMENTS_PKG, elements_file.replace('.py', ''), elem_class)
               + probe_imports
               + '\n\nclass %s:\n' % page_class
               + '    def __init__(self, appOperator):\n'
               + '        self.appOperator = appOperator\n'
               + '        self._elements = %s()\n' % elem_class
               + ('\n' + '\n'.join(m_map[m] for m in m_order) + '\n' if m_order else ''))

    # ---- 用例文件：setup 模板 + 逐步骤调用行（# i. 描述 注释供报告/回读）----
    lines = []
    for i, s in enumerate(steps, 1):
        lines.append('        # %d. %s' % (i, step_desc(s)))
        lines.append('        %s\n' % case_step_line(s))
    body = '\n'.join(lines)
    orch_doc = ' → '.join(dict.fromkeys(step_desc(s) for s in steps))   # 场景描述：步骤描述汇总去重
    case_py = ('# -*- coding: utf-8 -*-\n'
               + '%s（用例 #%d %s，%d 步）；手改会在下次保存时被覆盖\n'
               % (GENERATED_MARK, cid, name, len(steps))
               + 'import time\n'
               + 'import allure\n'
               + 'from base.app_ui.android.demoProject.app_ui_android_demoProject_client '
                 'import APP_UI_Android_demoProject_Client\n'
               + 'from %s.%sPage import %s\n' % (PAGES_PKG, b, page_class)
               + '\n\n'
               + "@allure.parent_suite('APP UI 自动化')\n"
               + "@allure.suite('%s')\n" % name.replace("'", "\\'")
               + 'class TestOrch%d:\n' % cid
               + '\n'
               + '    def setup_class(self):\n'
               + '        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App\n'
               + '        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)\n'
               + '        self.appOperator = self.demoProjectClient.appOperator\n'
               + "        self.appOperator.start_activity('%s', '%s')\n" % (package, activity)
               + '        time.sleep(3)\n'
               + '        self.page = %s(self.appOperator)\n' % page_class
               + '\n'
               + "    @allure.title('%s · %d 步')\n" % (name.replace("'", "\\'"), len(steps))
               + '    def test_orch_%d(self):\n' % cid
               + ('        """%s"""\n' % orch_doc if orch_doc else '')
               + '        page = self.page\n\n'
               + body + '\n'
               + '    def teardown_class(self):\n'
               + '        self.appOperator.close_app()\n')

    os.makedirs(CASES_DIR, exist_ok=True)
    os.makedirs(PAGES_DIR, exist_ok=True)
    case_path, page_path = _generated_paths(cid)
    for p, content in ((case_path, case_py), (page_path, page_py)):
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp, p)
    return node_of(cid)
