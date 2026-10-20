# -*- coding: utf-8 -*-
"""Web 执行平台 · 页面对象文件管理（元素管理模块「页面文件」视图：列表 / 编辑 / 删除）

数据源：page_objects/app_ui/android/demoProject/pages/*.py —— 与执行框架、
元素定位器共用同一份页面对象（单一数据源）。目录与过滤规则复用
element_locator.case_generator（list_page_files 白名单 + 历史备份排除）。

关联用例数：该页面文件被多少个用例的 self.page 绑定解析命中
（case_files_info 同源口径；同名页面类歧义的用例不计入任何文件）。
保存前做 ast 语法校验（页面文件是框架代码，语法错会让用例导入即崩）；
直接覆盖写、不留备份 —— 与元素管理同哲学：git 即备份。
"""
import ast
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:      # 允许独立运行/导入时定位 element_locator
    sys.path.insert(0, BASE_DIR)

from element_locator import case_generator as cg

PAGES_DIR_ABS = os.path.join(BASE_DIR, cg.PAGES_DIR)   # cg.PAGES_DIR 是相对项目根的路径


def _valid(name):
    """文件名必须在 list_page_files() 白名单内（天然防路径穿越 / __init__ / 历史备份）"""
    return bool(name) and name in set(cg.list_page_files())


def usage_counts():
    """页面文件名 → 关联用例数；统计异常返回 {}（前端据此退回纯列表）"""
    from collections import Counter
    try:
        return dict(Counter(i['page_file'] for i in cg.case_files_info() if i.get('page_file')))
    except Exception:
        return {}


def list_meta():
    """[{name, size, mtime, usage}]，按文件名排序"""
    usage = usage_counts()
    out = []
    for name in cg.list_page_files():
        try:
            st = os.stat(os.path.join(PAGES_DIR_ABS, name))
            size, mtime = st.st_size, int(st.st_mtime)
        except OSError:
            size, mtime = 0, 0
        out.append({'name': name, 'size': size, 'mtime': mtime, 'usage': usage.get(name, 0)})
    return out


def read_content(name):
    """读取文件内容：返回 (ok, content 或错误消息)"""
    if not _valid(name):
        return False, '未知页面文件：%s' % name
    try:
        with open(os.path.join(PAGES_DIR_ABS, name), 'r', encoding='utf-8') as f:
            return True, f.read()
    except OSError as e:
        return False, '读取失败：%s' % e


def save_content(name, content):
    """保存编辑：ast 语法校验通过才整文件覆盖写。返回 (ok, msg)"""
    if not _valid(name):
        return False, '未知页面文件：%s' % name
    if not isinstance(content, str) or not content.strip():
        return False, '内容为空，不予保存'
    try:
        ast.parse(content)
    except SyntaxError as e:
        return False, 'Python 语法错误（第 %s 行）：%s' % (e.lineno, e.msg)
    try:
        with open(os.path.join(PAGES_DIR_ABS, name), 'w', encoding='utf-8') as f:
            f.write(content)
    except OSError as e:
        return False, '写入失败：%s' % e
    return True, '已保存 %s' % name


def delete_page_file(name):
    """删除页面文件（是否被用例关联由前端确认框告知；git 可恢复）。返回 (ok, msg)"""
    if not _valid(name):
        return False, '未知页面文件：%s' % name
    n = usage_counts().get(name, 0)
    try:
        os.remove(os.path.join(PAGES_DIR_ABS, name))
    except OSError as e:
        return False, '删除失败：%s' % e
    if n:
        return True, '已删除 %s（删除前被 %d 个用例关联，相关用例将无法执行）' % (name, n)
    return True, '已删除 %s' % name
