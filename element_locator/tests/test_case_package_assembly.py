# -*- coding: utf-8 -*-
"""元素定位器 · 新建用例包服务端组装测试（v6.15.30）

覆盖 assemble_case_package 的三条主线（qa-engineer-agent 全路径口径）：
- 正向：新页面+新元素文件三件套一次成型；已有页面方法 upsert；特殊操作无元素
- 边界：用例名/文件名规范化；产物只含「新建或有变化」的文件；跨文件同定位复制定义行
- 异常：同名异定位硬拦（共享元素文件禁静默覆盖）；页面绑定元素文件不一致拦截；
        页面文件不存在/无类定义拒绝
全部读写指向临时目录（elements_dir/pages_dir 覆盖），绝不碰真实元素库与页面目录。
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


@pytest.fixture()
def pkg_env(tmp_path):
    """临时元素库 + 页面目录（隔离真实目录）"""
    edir = str(tmp_path / 'elements')
    pdir = str(tmp_path / 'pages')
    os.makedirs(edir)
    os.makedirs(pdir)
    return edir, pdir


def _compile_all(r):
    """产物逐个编译（语法兜底）"""
    assert r['ok'], r.get('msg')
    for f in r['files']:
        compile(f['content'], f['name'], 'exec')


def _file(r, name):
    for f in r['files']:
        if f['name'] == name:
            return f
    return None


ELEMENT = {'name': 'search_btn', 'locator_type': 'ID', 'value': 'com.x:id/btnSearch',
           'wait_type': 'VISIBILITY_OF', 'wait_seconds': 6, 'cn_name': '搜索按钮'}
STEP_CLICK = {'type': 'click', 'element': 'search_btn', 'param': '', 'comment': '点击搜索按钮'}


# ---------------- 正向：新页面 + 新元素文件 ----------------
def test_new_package_basic(pkg_env):
    edir, pdir = pkg_env
    r = cg.assemble_case_package('login_flow', cn_name='登录流程', step=STEP_CLICK,
                                 element=ELEMENT, element_file='loginFlow',
                                 element_file_new=True, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    _compile_all(r)
    names = {f['name'] for f in r['files']}
    assert names == {'test_login_flow.py', 'login_flowPage.py', 'loginFlowElements.py'}
    case = _file(r, 'test_login_flow.py')['content']
    assert 'from page_objects.app_ui.android.demoProject.pages.login_flowPage import LoginFlowPage' in case
    assert 'self.page = LoginFlowPage(self.appOperator)' in case
    assert 'page.click_search_btn()' in case
    page = _file(r, 'login_flowPage.py')['content']
    assert 'from page_objects.app_ui.android.demoProject.elements.loginFlowElements import LoginFlowElements' in page
    assert 'def click_search_btn(self):' in page
    elem = _file(r, 'loginFlowElements.py')['content']
    assert 'self.search_btn = CreateElement.create(Locator_Type.ID' in elem
    assert "desc='搜索按钮'" in elem
    assert r['element_final'] == 'search_btn' and not r['reused']


def test_base_name_normalization(pkg_env):
    """test_ 前缀/.py 后缀/非法字符统一规范化（与前端 newCaseBase 同规则）"""
    edir, pdir = pkg_env
    r = cg.assemble_case_package('test_搜 索-flow.py', step=dict(STEP_CLICK, element='x'),
                                 element=ELEMENT, element_file_new=True, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    _compile_all(r)
    assert _file(r, 'test_搜_索_flow.py') is not None


def test_special_step_no_element(pkg_env):
    """特殊操作（收起键盘）无元素：不产生元素文件，页面不绑元素，产物可编译"""
    edir, pdir = pkg_env
    r = cg.assemble_case_package('kbd_case', step={'type': 'hide_keyboard', 'element': '', 'param': ''},
                                 element=None, element_file_new=True, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    _compile_all(r)
    names = {f['name'] for f in r['files']}
    assert names == {'test_kbd_case.py', 'kbd_casePage.py'}
    page = _file(r, 'kbd_casePage.py')['content']
    assert '_elements' not in page          # 无元素绑定
    assert 'def dismiss_keyboard(self):' in page


# ---------------- 边界：查重复用 ----------------
def test_dedup_same_file_reuses_name(pkg_env):
    """目标元素文件里已有同定位 → 复用库内元素名，定义零改动，页面方法/用例行用终名"""
    edir, pdir = pkg_env
    el.add_element('sharedElements.py', 'btn_back', 'ID', 'com.x:id/btnSearch',
                   elements_dir=edir)
    r = cg.assemble_case_package('reuse_case', step=STEP_CLICK,
                                 element=ELEMENT, element_file='sharedElements.py',
                                 element_file_new=False, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    _compile_all(r)
    assert r['reused'] and r['element_final'] == 'btn_back'
    assert _file(r, 'sharedElements.py') is None           # 定义未变化 → 不入库
    case = _file(r, 'test_reuse_case.py')['content']
    assert 'page.click_btn_back()' in case                 # 用例行用库内名
    page = _file(r, 'reuse_casePage.py')['content']
    assert 'self._elements.btn_back' in page               # 页面方法用库内名


def test_dedup_cross_file_copies_line(pkg_env):
    """其他元素文件有同定位 → 复用其名，定义行整行复制进目标文件（页面绑定不变）"""
    edir, pdir = pkg_env
    el.add_element('otherElements.py', 'btn_search', 'ID', 'com.x:id/btnSearch',
                   wait_seconds=9, cn_name='搜索', elements_dir=edir)
    r = cg.assemble_case_package('cross_case', step=STEP_CLICK,
                                 element=ELEMENT, element_file='crossElements.py',
                                 element_file_new=True, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    _compile_all(r)
    assert r['reused'] and r['element_final'] == 'btn_search'
    elem = _file(r, 'crossElements.py')['content']
    assert 'self.btn_search' in elem and 'wait_seconds=9' in elem   # 整行复制保留等待/中文名
    assert 'self.search_btn' not in elem


def test_dedup_final_name_in_target_conflict_blocked(pkg_env):
    """复用来的名字与目标文件同名元素定位不同 → 硬拦（防静默覆盖牵连其他用例）"""
    edir, pdir = pkg_env
    el.add_element('targetElements.py', 'btn_search', 'ID', 'com.x:id/other',
                   elements_dir=edir)
    el.add_element('otherElements.py', 'btn_search', 'ID', 'com.x:id/btnSearch',
                   elements_dir=edir)
    r = cg.assemble_case_package('conflict_case', step=STEP_CLICK,
                                 element=ELEMENT, element_file='targetElements.py',
                                 element_file_new=False, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    assert not r['ok'] and '禁止静默覆盖' in r['msg']


def test_same_name_diff_locator_in_target_blocked(pkg_env):
    """目标文件里同名元素但定位不同 → 硬拦"""
    edir, pdir = pkg_env
    el.add_element('targetElements.py', 'search_btn', 'ID', 'com.x:id/another',
                   elements_dir=edir)
    r = cg.assemble_case_package('name_hit', step=STEP_CLICK,
                                 element=ELEMENT, element_file='targetElements.py',
                                 element_file_new=False, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    assert not r['ok'] and '禁止静默覆盖' in r['msg']


# ---------------- 正向：复用已有页面 ----------------
PAGE_SRC = '''# -*- coding: utf-8 -*-
from page_objects.app_ui.android.demoProject.elements.sharedElements import SharedElements
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class AaaaPage:
    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = SharedElements()

    def teardown_class(self):
        pass
'''


def test_existing_page_upsert_and_case_import(pkg_env):
    """选已有页面：页面方法 upsert 进该文件，用例 import 真实页面类，元素落其绑定文件"""
    edir, pdir = pkg_env
    el.add_element('sharedElements.py', 'btn_back', 'ID', 'com.x:id/back', elements_dir=edir)
    with open(os.path.join(pdir, 'AaaaPage.py'), 'w', encoding='utf-8') as f:
        f.write(PAGE_SRC)
    r = cg.assemble_case_package('reuse_page_case', step=STEP_CLICK,
                                 element=ELEMENT, element_file='sharedElements.py',
                                 element_file_new=False, page_file='AaaaPage.py',
                                 page_file_new=False, elements_dir=edir, pages_dir=pdir)
    _compile_all(r)
    names = {f['name'] for f in r['files']}
    assert names == {'test_reuse_page_case.py', 'AaaaPage.py', 'sharedElements.py'}
    case = _file(r, 'test_reuse_page_case.py')['content']
    assert 'from page_objects.app_ui.android.demoProject.pages.AaaaPage import AaaaPage' in case
    assert 'self.page = AaaaPage(self.appOperator)' in case
    page = _file(r, 'AaaaPage.py')['content']
    assert 'def click_search_btn(self):' in page and 'teardown_class' in page
    elem = _file(r, 'sharedElements.py')['content']
    assert 'self.btn_back' in elem and 'self.search_btn' in elem   # 原定义不动 + 新增


def test_existing_page_tool_method_not_duplicated(pkg_env):
    """页面已有 dismiss_keyboard（工具方法）→ 不重复生成，页面文件零变化（不入产物）"""
    edir, pdir = pkg_env
    page_src = PAGE_SRC.replace('    def teardown_class(self):',
                                '''    def dismiss_keyboard(self):
        """收起键盘"""

    def teardown_class(self):''')
    with open(os.path.join(pdir, 'AaaaPage.py'), 'w', encoding='utf-8') as f:
        f.write(page_src)
    r = cg.assemble_case_package('tool_case', step={'type': 'hide_keyboard', 'element': '', 'param': ''},
                                 element=None, element_file_new=True, page_file='AaaaPage.py',
                                 page_file_new=False, elements_dir=edir, pages_dir=pdir)
    _compile_all(r)
    assert _file(r, 'AaaaPage.py') is None          # 页面零变化 → 不入库（避免备份噪声）
    assert any('已存在' in n for n in r['notes'])
    assert _file(r, 'test_tool_case.py') is not None


def test_existing_page_elements_file_mismatch_blocked(pkg_env):
    """已有页面绑定了元素文件 A，元素却写向 B → 服务端硬拦（前端会自动对齐，此处兜底）"""
    edir, pdir = pkg_env
    with open(os.path.join(pdir, 'AaaaPage.py'), 'w', encoding='utf-8') as f:
        f.write(PAGE_SRC)
    r = cg.assemble_case_package('mismatch_case', step=STEP_CLICK,
                                 element=ELEMENT, element_file='otherElements.py',
                                 element_file_new=True, page_file='AaaaPage.py',
                                 page_file_new=False, elements_dir=edir, pages_dir=pdir)
    assert not r['ok'] and '绑定元素文件' in r['msg']


def test_missing_page_file_rejected(pkg_env):
    edir, pdir = pkg_env
    r = cg.assemble_case_package('no_page', step=STEP_CLICK, element=ELEMENT,
                                 element_file_new=True, page_file='GhostPage.py',
                                 page_file_new=False, elements_dir=edir, pages_dir=pdir)
    assert not r['ok'] and '不存在' in r['msg']


def test_page_without_class_rejected(pkg_env):
    edir, pdir = pkg_env
    with open(os.path.join(pdir, 'EmptyPage.py'), 'w', encoding='utf-8') as f:
        f.write('# 只有注释\n')
    r = cg.assemble_case_package('no_cls', step=STEP_CLICK, element=ELEMENT,
                                 element_file_new=True, page_file='EmptyPage.py',
                                 page_file_new=False, elements_dir=edir, pages_dir=pdir)
    assert not r['ok'] and '类定义' in r['msg']


# ---------------- 单元：merge_element_line ----------------
def test_merge_element_line_into_pass_body():
    content = el.HEADER + 'class A:\n    def __init__(self):\n        pass\n'
    line = "        self.btn = CreateElement.create(Locator_Type.ID, 'x', wait_type=Wait_By.VISIBILITY_OF)"
    new, action = el.merge_element_line(content, 'btn', line)
    assert action == 'inserted' and 'pass' not in new and 'self.btn' in new
    compile(new, '<elem>', 'exec')


def test_merge_element_line_append_after_last():
    content = el.HEADER + 'class A:\n    def __init__(self):\n        self.a = CreateElement.create(Locator_Type.ID, \'1\')\n'
    line = "        self.b = CreateElement.create(Locator_Type.ID, '2')"
    new, action = el.merge_element_line(content, 'b', line)
    assert action == 'inserted'
    assert new.index('self.a') < new.index('self.b')            # 追加在最后一个元素行之后
    compile(new, '<elem>', 'exec')


def test_merge_element_line_keeps_existing():
    line = "        self.a = CreateElement.create(Locator_Type.ID, 'X')"
    content = el.HEADER + 'class A:\n    def __init__(self):\n' + line + '\n'
    new, action = el.merge_element_line(content, 'a', line + '  # changed')
    assert action == 'kept' and '# changed' not in new           # 同名已存在 → 原定义为准


# ---------------- page_elements_map ----------------
def test_page_elements_map(tmp_path, monkeypatch):
    pdir = str(tmp_path / 'pages')
    os.makedirs(pdir)
    with open(os.path.join(pdir, 'AaaaPage.py'), 'w', encoding='utf-8') as f:
        f.write(PAGE_SRC)
    with open(os.path.join(pdir, 'BarePage.py'), 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n\nclass BarePage:\n    pass\n')
    monkeypatch.setattr(cg, 'PAGES_DIR', pdir)
    mapping = cg.page_elements_map()
    assert mapping['AaaaPage.py'] == 'sharedElements.py'
    assert mapping['BarePage.py'] == ''


# ---------------- 异常：非法入参 ----------------
def test_invalid_base_rejected(pkg_env):
    edir, pdir = pkg_env
    r = cg.assemble_case_package('', step=STEP_CLICK, element=ELEMENT,
                                 element_file_new=True, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    assert not r['ok']


def test_invalid_step_type_rejected(pkg_env):
    edir, pdir = pkg_env
    r = cg.assemble_case_package('bad_step', step={'type': 'no_such_op'},
                                 element=None, element_file_new=True, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    assert not r['ok'] and '步骤' in r['msg']


def test_invalid_element_name_rejected(pkg_env):
    edir, pdir = pkg_env
    r = cg.assemble_case_package('bad_el', step=STEP_CLICK,
                                 element=dict(ELEMENT, name='1按钮'),
                                 element_file_new=True, page_file_new=True,
                                 elements_dir=edir, pages_dir=pdir)
    assert not r['ok'] and '不合法' in r['msg']
