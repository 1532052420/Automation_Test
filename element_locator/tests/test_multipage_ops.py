# -*- coding: utf-8 -*-
"""元素定位器 · 多页面挂接 + 框架原生操作类型测试（v6.15.33）

覆盖 append_code_to_method 的页面选择/自动挂接与新操作类型（qa-engineer-agent 全路径口径）：
- 正向：多页面用例任选目标页面（前缀 self.pageN）；未实例化页面自动挂接（import + setup_class 实例化）；
        新操作类型（滑动/拖拽/按键/前后台/开关）生成合法页面方法与用例行
- 边界：默认回落 self.page（旧语义回归）；drag_to 目标元素自动同步到页面绑定元素文件
- 异常：按键/后台秒数非整数拦截；拖拽缺目标元素名拦截；所选页面文件不存在拦截
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest element_locator/tests/ -q
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'element_locator'))

import element_library as el  # noqa: E402
import case_generator as cg   # noqa: E402


CASE_HEAD = '''# -*- coding: utf-8 -*-
import time
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.PageA import PageA


class TestMp:

    def setup_class(self):
        self.appOperator = APP_UI_Android_demoProject_Client(is_need_kill_app=False).appOperator
        self.page = PageA(self.appOperator)

    def test_mp(self):
        """点击 a"""
        page = self.page

        # 1. 点击 a
        page.click_btn_a()
'''

PAGE_A = '''# -*- coding: utf-8 -*-
from page_objects.app_ui.android.demoProject.elements.MpAElements import MpAElements


class PageA:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = MpAElements()

    def click_btn_a(self):
        """点击 a"""
        self.appOperator.click(self._elements.btn_a)
'''

PAGE_B = '''# -*- coding: utf-8 -*-
from page_objects.app_ui.android.demoProject.elements.MpBElements import MpBElements


class PageB:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = MpBElements()

    def noop(self):
        """空操作"""
        pass
'''

ELEM_A = '''# -*- coding: utf-8 -*-
from page_objects.createElement import CreateElement


class MpAElements:
    def __init__(self):
        self.btn_a = CreateElement.create('ID', 'com.x:id/btnA')
        self.btn_dst = CreateElement.create('ID', 'com.x:id/btnDst')
'''

ELEM_B = '''# -*- coding: utf-8 -*-
from page_objects.createElement import CreateElement


class MpBElements:
    def __init__(self):
        self.btn_b = CreateElement.create('ID', 'com.x:id/btnB')
'''


@pytest.fixture()
def mp_env(tmp_path, monkeypatch):
    """临时用例/页面/元素目录，重定向 case_generator 与 element_library 的目录常量"""
    cdir = str(tmp_path / 'cases')
    pdir = str(tmp_path / 'pages')
    edir = str(tmp_path / 'elements')
    for d in (cdir, pdir, edir):
        os.makedirs(d)
    open(os.path.join(cdir, 'test_mp.py'), 'w', encoding='utf-8').write(CASE_HEAD)
    open(os.path.join(pdir, 'PageA.py'), 'w', encoding='utf-8').write(PAGE_A)
    open(os.path.join(pdir, 'PageB.py'), 'w', encoding='utf-8').write(PAGE_B)
    open(os.path.join(edir, 'MpAElements.py'), 'w', encoding='utf-8').write(ELEM_A)
    open(os.path.join(edir, 'MpBElements.py'), 'w', encoding='utf-8').write(ELEM_B)
    monkeypatch.setattr(cg, 'CASES_DIR', cdir)
    monkeypatch.setattr(cg, 'PAGES_DIR', pdir)
    monkeypatch.setattr(el, 'ELEMENTS_DIR', edir)
    return cdir, pdir, edir


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _append(mp_env, step, **kw):
    return cg.append_code_to_method('test_mp.py', 'test_mp', step,
                                    gen_page_method=True, **kw)


# ---------------- 正向：多页面解析与选择 ----------------
def test_page_targets_parsed(mp_env):
    cdir, pdir, edir = mp_env
    open(os.path.join(cdir, 'test_mp2.py'), 'w', encoding='utf-8').write(
        CASE_HEAD.replace('self.page = PageA(self.appOperator)',
                          'self.page = PageA(self.appOperator)\n        self.page2 = PageB(self.appOperator)'))
    infos = [i for i in cg.case_files_info() if i['file'] == 'test_mp2.py']
    tgt = infos[0]['page_targets']
    assert [(t['var'], t['page_file']) for t in tgt] == [('page', 'PageA.py'), ('page2', 'PageB.py')]


def test_append_to_second_page_prefix(mp_env):
    """已有用例选第二个页面：用例行前缀 self.page2，方法写进该页面文件"""
    cdir, pdir, edir = mp_env
    open(os.path.join(cdir, 'test_mp.py'), 'w', encoding='utf-8').write(
        CASE_HEAD.replace('self.page = PageA(self.appOperator)',
                          'self.page = PageA(self.appOperator)\n        self.page2 = PageB(self.appOperator)'))
    r = _append(mp_env, {'type': 'click', 'element': 'btn_b', 'param': ''},
                page_file='PageB.py')
    assert r['ok'], r.get('msg')
    assert r['line'] == 'self.page2.click_btn_b()'
    assert r['page_file'] == 'PageB.py'
    assert 'click_btn_b' in _read(os.path.join(pdir, 'PageB.py'))
    compile(_read(os.path.join(cdir, 'test_mp.py')), 'test_mp.py', 'exec')


def test_append_auto_wiring(mp_env):
    """选未实例化页面：自动补 import + setup_class 体内实例化 self.page2（8 空格方法体缩进）"""
    cdir, pdir, edir = mp_env
    r = _append(mp_env, {'type': 'toggle_wifi', 'element': '', 'param': ''},
                page_file='PageB.py')
    assert r['ok'], r.get('msg')
    case_txt = _read(os.path.join(cdir, 'test_mp.py'))
    assert 'from page_objects.app_ui.android.demoProject.pages.PageB import PageB' in case_txt
    # 关键：实例化必须落在 setup_class 方法体内（8 空格），且后续 def 仍是类方法（4 空格）——
    # 落到类体层（4 空格）语法合法但 import 即 NameError、pytest 不再收集，属事故级
    assert '\n        self.page2 = PageB(self.appOperator)\n' in case_txt
    assert not case_txt.startswith(('\n    self.page2', '# -*- coding: utf-8 -*-\n    self.page2'))
    assert '\n    def test_mp(self):' in case_txt
    assert 'self.page2.toggle_wifi()' in case_txt
    assert '接进用例' in r['msg']
    page_txt = _read(os.path.join(pdir, 'PageB.py'))
    assert 'def toggle_wifi(' in page_txt and 'toggle_wifi()' in page_txt
    compile(case_txt, 'test_mp.py', 'exec')
    compile(page_txt, 'PageB.py', 'exec')


def test_append_default_falls_back_to_self_page(mp_env):
    """不指定页面：回落 self.page 既有语义（page. 前缀 + 写 PageA）——回归保护"""
    r = _append(mp_env, {'type': 'click', 'element': 'btn_a', 'param': ''})
    assert r['ok'], r.get('msg')
    assert r['line'] == 'page.click_btn_a()'
    assert r['page_file'] == 'PageA.py'


# ---------------- 正向：新操作类型 ----------------
@pytest.mark.parametrize('t,param,line,method_sig', [
    ('swipe_up', '800', 'page.swipe_up_btn_a(800)', 'def swipe_up_btn_a(self, duration=800):'),
    ('swipe_down', '', 'page.swipe_down_btn_a()', 'def swipe_down_btn_a(self, duration=500):'),
    ('swipe_left', 'x', 'page.swipe_left_btn_a()', 'def swipe_left_btn_a(self, duration=500):'),
    ('swipe_right', '300', 'page.swipe_right_btn_a(300)', 'def swipe_right_btn_a(self, duration=300):'),
    ('press_keycode', '4', 'page.press_key(4)', 'def press_key(self, keycode):'),
    ('background_app', '-1', 'page.background_run(-1)', 'def background_run(self, seconds):'),
    ('activate_app', 'com.x', "page.activate('com.x')", 'def activate(self, app_id):'),
    ('toggle_wifi', '', 'page.toggle_wifi()', 'def toggle_wifi(self):'),
    ('toggle_airplane', '', 'page.toggle_airplane_mode()', 'def toggle_airplane_mode(self):'),
])
def test_new_op_types(mp_env, t, param, line, method_sig):
    r = _append(mp_env, {'type': t, 'element': 'btn_a', 'param': param})
    assert r['ok'], r.get('msg')
    assert r['line'] == line
    page_txt = _read(os.path.join(mp_env[1], 'PageA.py'))
    assert method_sig in page_txt
    compile(_read(os.path.join(mp_env[0], 'test_mp.py')), 't', 'exec')
    compile(page_txt, 'p', 'exec')


def test_drag_to_generates_and_syncs_dst_element(mp_env):
    """drag_to：方法引用 self._elements.btn_dst，目标元素已在绑定文件 → 直接生成"""
    r = _append(mp_env, {'type': 'drag_to', 'element': 'btn_a', 'param': 'btn_dst'})
    assert r['ok'], r.get('msg')
    assert r['line'] == 'page.drag_btn_a_to_btn_dst()'
    page_txt = _read(os.path.join(mp_env[1], 'PageA.py'))
    assert 'touch_a_element_drag_to_another_element(' in page_txt
    assert 'self._elements.btn_dst' in page_txt


def test_drag_to_copies_dst_from_other_file(mp_env):
    """drag_to 目标元素不在绑定文件但在其他文件 → 自动复制行过来"""
    open(os.path.join(mp_env[2], 'MpBElements.py'), 'w', encoding='utf-8').write(
        ELEM_B.replace("self.btn_b = CreateElement.create('ID', 'com.x:id/btnB')",
                       "self.btn_b = CreateElement.create('ID', 'com.x:id/btnB')\n        self.far_dst = CreateElement.create('ID', 'com.x:id/far')"))
    r = _append(mp_env, {'type': 'drag_to', 'element': 'btn_a', 'param': 'far_dst'})
    assert r['ok'], r.get('msg')
    assert 'far_dst' in _read(os.path.join(mp_env[2], 'MpAElements.py'))


# ---------------- 异常 ----------------
def test_press_keycode_non_int_blocked(mp_env):
    r = _append(mp_env, {'type': 'press_keycode', 'element': '', 'param': 'abc'})
    assert not r['ok'] and '整数' in r['msg']


def test_background_app_non_int_blocked(mp_env):
    r = _append(mp_env, {'type': 'background_app', 'element': '', 'param': 'x'})
    assert not r['ok'] and '整数' in r['msg']


def test_drag_to_missing_dst_blocked(mp_env):
    r = _append(mp_env, {'type': 'drag_to', 'element': 'btn_a', 'param': ''})
    assert not r['ok'] and '目标元素名' in r['msg']


def test_page_file_not_exist_blocked(mp_env):
    r = _append(mp_env, {'type': 'toggle_wifi', 'element': '', 'param': ''},
                page_file='NopePage.py')
    assert not r['ok'] and '不存在' in r['msg']
