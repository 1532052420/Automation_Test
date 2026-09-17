# -*- coding: utf-8 -*-
"""元素定位器 · 中文命名元素支持测试

调研结论（2026-09-17）：
- Python 3 标识符原生支持中文（PEP 3131），self.<中文名> 属性、def click_<中文名>()
  页面方法均合法——运行时契约只要求「合法标识符且非关键字」。
- 唯一卡点是各处 ASCII 正则校验/解析：element_library（写入+重复检测+名字清单）、
  web_platform/element_manager（平台元素管理）。已改为中文/字母/数字/下划线同一字符集。
- case_generator 页面方法名由元素名派生（click_<元素>），无独立校验，中文名天然可用。

本文件覆盖中文命名场景：写入/覆盖/重复检测/解析往返/页面方法生成/非法名拒绝。
全部读写指向临时目录（add_element 的 elements_dir 覆盖），绝不碰真实元素库。
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest element_locator/tests/ -q
"""
import os
import sys
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'element_locator'))

import element_library as el  # noqa: E402
import case_generator as cg   # noqa: E402


@pytest.fixture()
def elements_dir(tmp_path):
    """临时元素库目录（隔离真实元素库）"""
    d = str(tmp_path / 'elements')
    os.makedirs(d, exist_ok=True)
    return d


# ---------------- 合法性判断 ----------------
@pytest.mark.parametrize('name', ['登录按钮', 'btn_登录', '首页_顶部Banner', '中文', 'search_btn'])
def test_valid_names(name):
    assert el.is_valid_element_name(name)


@pytest.mark.parametrize('name', ['1btn', 'btn-1', 'btn 1', 'a' * 300, '', None, 'cla ss'])
def test_invalid_names(name):
    assert not el.is_valid_element_name(name)


def test_python_keyword_rejected():
    """class/for 等关键字作属性名会产生语法错误（obj.class），必须拒绝"""
    assert not el.is_valid_element_name('class')
    assert not el.is_valid_element_name('for')
    # 中文不是 Python 关键字，天然安全
    assert el.is_valid_element_name('类')


# ---------------- 写入元素库（中文名） ----------------
def test_add_element_chinese_name(elements_dir):
    r = el.add_element('chinese_elements.py', '登录按钮', 'ID', 'com.x:id/btnLogin',
                       wait_type='VISIBILITY_OF', wait_seconds=6, comment='登录页主按钮',
                       elements_dir=elements_dir)
    assert r['ok'], r
    assert 'self.登录按钮' in r['content']
    # 落盘文件必须是合法 Python
    path = os.path.join(elements_dir, 'chinese_elements.py')
    assert subprocess.run([sys.executable, '-m', 'py_compile', path]).returncode == 0


def test_add_element_chinese_exec_semantics(elements_dir):
    """生成的元素文件按真实语义执行：self.<中文名> 属性可访问（PEP 3131 运行时验证）"""
    el.add_element('exe_elements.py', '手机号输入框', 'ID', 'com.x:id/etPhone',
                   elements_dir=elements_dir)
    path = os.path.join(elements_dir, 'exe_elements.py')
    src = open(path, encoding='utf-8').read()
    # 替换框架 import 为桩，只验证「类定义 + self.中文属性赋值」本身合法可执行
    stub = src.replace('from page_objects.createElement import CreateElement', 'CreateElement = type("C", (), {"create": staticmethod(lambda lt, v, **kw: (lt, v))})') \
              .replace('from page_objects.app_ui.locator_type import Locator_Type', 'class Locator_Type:\n    ID = "id"') \
              .replace('from page_objects.app_ui.wait_type import Wait_Type as Wait_By', 'class Wait_By:\n    VISIBILITY_OF = "visibility"')
    ns = {}
    exec(compile(stub, path, 'exec'), ns)
    # 按 __name__ 过滤（ns 的 key 是 CreateElement，按 key 过滤会漏掉桩类 C）
    stub_names = ('C', 'Locator_Type', 'Wait_By')
    cls = [v for v in ns.values() if isinstance(v, type) and v.__name__ not in stub_names][0]
    inst = cls()
    assert inst.手机号输入框[1] == 'com.x:id/etPhone'


def test_update_chinese_element_overwrite(elements_dir):
    """中文名同名覆盖 = 整行替换"""
    el.add_element('ov_elements.py', '提交按钮', 'ID', 'com.x:id/v1', elements_dir=elements_dir)
    r = el.add_element('ov_elements.py', '提交按钮', 'XPATH', '//android.widget.Button',
                       elements_dir=elements_dir)
    assert r['ok'] and r['action'] == 'updated'
    content = open(os.path.join(elements_dir, 'ov_elements.py'), encoding='utf-8').read()
    assert content.count('self.提交按钮') == 1 and 'XPATH' in content


def test_duplicate_detection_with_chinese(elements_dir):
    """相同定位的中文元素能被重复检测发现；同名不算重复"""
    el.add_element('dup_elements.py', '同意按钮', 'XPATH', "//*[@text='同意']", elements_dir=elements_dir)
    # 同定位不同名 → 拦截
    r = el.add_element('dup_elements.py', '另一个按钮', 'XPATH', "//*[@text='同意']",
                       elements_dir=elements_dir)
    assert not r['ok'] and r['duplicate']['name'] == '同意按钮'
    # 同名 → 覆盖放行
    r2 = el.add_element('dup_elements.py', '同意按钮', 'XPATH', "//*[@text='同意继续']",
                        elements_dir=elements_dir)
    assert r2['ok'] and r2['action'] == 'updated'


def test_list_element_names_includes_chinese(elements_dir, monkeypatch):
    el.add_element('names_elements.py', '返回箭头', 'ID', 'com.x:id/back', elements_dir=elements_dir)
    monkeypatch.setattr(el, 'ELEMENTS_DIR', elements_dir)
    assert '返回箭头' in el.list_element_names('names_elements.py')


# ---------------- 非法名在 add_element 入口被拒 ----------------
@pytest.mark.parametrize('name', ['1按钮', '按钮 1', 'btn-中文', 'class'])
def test_add_element_rejects_bad_names(name, elements_dir):
    r = el.add_element('rej_elements.py', name, 'ID', 'com.x:id/x', elements_dir=elements_dir)
    assert not r['ok'] and '不合法' in r['msg']


# ---------------- case_generator：中文元素名派生页面方法 ----------------
def test_page_method_code_with_chinese_element():
    """click_<中文> 页面方法与 page.<中文>() 调用行都是合法 Python"""
    step = {'type': 'click', 'element': '登录按钮', 'param': '', 'comment': ''}
    block = cg.page_method_code(step)
    assert block and 'def click_登录按钮(self):' in block
    compile('class P:\n' + block, '<page>', 'exec')     # 方法块可编译
    line = cg.case_step_line(step)
    assert line == 'page.click_登录按钮()'
    compile('def t(page):\n    ' + line + '\n', '<case>', 'exec')  # 调用行可编译


def test_input_method_with_chinese_element_compiles():
    step = {'type': 'input', 'element': '手机号输入框', 'param': '13800000000', 'comment': ''}
    block = cg.page_method_code(step)
    assert 'def input_手机号输入框(self, text):' in block
    compile('class P:\n' + block, '<page>', 'exec')


# ---------------- 平台元素管理（web_platform/element_manager）中文往返 ----------------
def test_element_manager_chinese_roundtrip(tmp_path, monkeypatch):
    from web_platform import element_manager as em
    d = str(tmp_path / 'elements')
    os.makedirs(d)
    monkeypatch.setattr(em, 'ELEMENTS_DIR', d)

    # 新增（复制语义）
    ok, p = em.save_element('locator_gui_elements.py', '我的登录按钮', 'ID', 'com.x:id/login',
                            'VISIBILITY_OF', 6, '中文备注', orig_name=None)
    assert ok, p
    # 解析回读
    els = {e['name']: e for e in em.list_elements()}
    assert els['我的登录按钮']['value'] == 'com.x:id/login'
    assert els['我的登录按钮']['desc'] == '中文备注'
    # 编辑
    ok, p = em.save_element('locator_gui_elements.py', '我的登录按钮', 'XPATH', '//android.widget.Button',
                            'ELEMENT_TO_BE_CLICKABLE', 9, '改过', orig_name='我的登录按钮')
    assert ok, p
    els = {e['name']: e for e in em.list_elements()}
    assert els['我的登录按钮']['type'] == 'XPATH' and els['我的登录按钮']['wait_seconds'] == 9
    # 删除
    ok, msg = em.delete_element('locator_gui_elements.py', '我的登录按钮')
    assert ok and '我的登录按钮' not in [e['name'] for e in em.list_elements()]


def test_element_manager_rejects_bad_chinese_variants(tmp_path, monkeypatch):
    from web_platform import element_manager as em
    d = str(tmp_path / 'elements')
    os.makedirs(d)
    monkeypatch.setattr(em, 'ELEMENTS_DIR', d)
    for bad in ('1按钮', '按钮 空格', '按钮-1'):
        ok, p = em.save_element('locator_gui_elements.py', bad, 'ID', 'com.x:id/x',
                                orig_name=None)
        assert not ok and '不合法' in p['msg'], bad
