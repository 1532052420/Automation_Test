# -*- coding: utf-8 -*-
"""AppUI 用例编排 · codegen 编译层测试（YAML 编排 → 框架三件套）

覆盖 AAA 与全路径：产物可编译可导入 / 标记头 / 幂等覆盖 / validate_steps 全分支 / 清理只删标记文件。
运行：cd <项目根> && env -u PYTHONPATH .venv/bin/python -m pytest web_platform/tests/test_codegen.py -q
"""
import os
import py_compile
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from web_platform.app_testing import codegen as cg   # noqa: E402

_CASE = {'id': 42, 'name': "登录冒烟'", 'elements_file': 'kuaigeLoginElements.py',
         'steps': [
             {'type': 'click', 'element': 'btn_agree_privacy', 'param': '', 'desc': '勾选协议'},
             {'type': 'input', 'element': 'et_phone', 'param': "138'000", 'desc': '输入手机号'},
             {'type': 'assert_visible', 'element': 'et_code', 'param': '', 'desc': ''},
             {'type': 'sleep', 'param': '1', 'desc': ''},
         ]}


@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    """CASES_DIR / PAGES_DIR 重定向到临时目录（不污染真实框架目录）"""
    monkeypatch.setattr(cg, 'CASES_DIR', str(tmp_path / 'cases'))
    monkeypatch.setattr(cg, 'PAGES_DIR', str(tmp_path / 'pages'))
    return tmp_path


# ---------------- 编译正向 ----------------
def test_compile_produces_compilable_pair(dirs):
    """TC_CODEGEN_001 正向：编译产出页面+用例文件，均可通过 py_compile，node 返回"""
    node = cg.compile_case(_CASE)
    assert node == cg.node_of(42)
    case_py = os.path.join(cg.CASES_DIR, 'test_orch42.py')
    page_py = os.path.join(cg.PAGES_DIR, 'orch42Page.py')
    assert os.path.exists(case_py) and os.path.exists(page_py)
    py_compile.compile(case_py, doraise=True)
    py_compile.compile(page_py, doraise=True)


def test_compile_generated_mark_and_quotes_escaped(dirs):
    """TC_CODEGEN_002 正向（边界）：产物带标记头；名称/参数中的单引号被转义不破语法"""
    node = cg.compile_case(_CASE)
    case_py = os.path.join(cg.CASES_DIR, 'test_orch42.py')
    page_py = os.path.join(cg.PAGES_DIR, 'orch42Page.py')
    for p in (case_py, page_py):
        with open(p, encoding='utf-8') as f:
            assert cg.GENERATED_MARK in f.readline() + f.readline()   # 标记在编码声明行的下一行
    with open(case_py, encoding='utf-8') as f:
        content = f.read()
    assert "登录冒烟\\'" in content                     # 名称含单引号已转义
    assert "page.input_et_phone('138\\'000')" in content  # 参数含单引号已转义


def test_compile_idempotent_overwrite(dirs):
    """TC_CODEGEN_003 正向（幂等）：重复编译全量覆盖，不留旧步骤残留"""
    cg.compile_case(_CASE)
    changed = dict(_CASE, steps=[{'type': 'sleep', 'param': '2', 'desc': ''}])
    cg.compile_case(changed)
    with open(os.path.join(cg.CASES_DIR, 'test_orch42.py'), encoding='utf-8') as f:
        body = f.read()
    assert 'btn_agree_privacy' not in body and 'time.sleep(2.0)' in body


def test_page_methods_dedup_same_name(dirs):
    """TC_CODEGEN_004 边界：同名页面方法取最后一次（与定位器更新语义一致）"""
    steps = [{'type': 'input', 'element': 'et_phone', 'param': '1', 'desc': ''},
             {'type': 'input', 'element': 'et_phone', 'param': '2', 'desc': ''}]
    cg.compile_case(dict(_CASE, steps=steps))
    with open(os.path.join(cg.PAGES_DIR, 'orch42Page.py'), encoding='utf-8') as f:
        page = f.read()
    assert page.count('def input_et_phone') == 1
    assert '「2」' in page and '「1」' not in page      # 参数体现为最后一次的 docstring


# ---------------- validate_steps ----------------
def test_validate_steps_ok_and_empty():
    """TC_CODEGEN_005 正向/异常：合法步骤通过；空步骤拒绝"""
    assert cg.validate_steps(_CASE['steps']) is None
    assert cg.validate_steps([]) and '至少' in cg.validate_steps([])


def test_validate_steps_bad_type_and_missing():
    """TC_CODEGEN_006 异常：类型非法 / 需元素未选 / 需参数未填 / 坐标格式错"""
    assert '不合法' in cg.validate_steps([{'type': 'hack'}])
    assert '元素' in cg.validate_steps([{'type': 'click'}])
    assert '参数' in cg.validate_steps([{'type': 'input', 'element': 'et_phone'}])
    assert '坐标' in cg.validate_steps([{'type': 'tap', 'param': 'a,b'}])
    assert cg.validate_steps([{'type': 'tap', 'param': '100,200'}]) is None


# ---------------- 清理 ----------------
def test_remove_generated_only_marked(dirs):
    """TC_CODEGEN_007 正向（边界）：删除编排用例只清理带标记的生成文件，手写文件保留"""
    cg.compile_case(_CASE)
    case_py = os.path.join(cg.CASES_DIR, 'test_orch42.py')
    hand_py = os.path.join(cg.CASES_DIR, 'test_hand.py')
    with open(hand_py, 'w', encoding='utf-8') as f:
        f.write('# 手写用例\nclass TestHand:\n    pass\n')
    cg.remove_generated(42)
    assert not os.path.exists(case_py)          # 生成文件被清理
    assert os.path.exists(hand_py)              # 手写文件保留
    cg.remove_generated(999)                    # 清理不存在的 id 不报错
