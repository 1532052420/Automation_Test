# -*- coding: utf-8 -*-
"""三件套跨文件引用检查（元素 ↔ 页面对象静态绑定的完整性护栏）。

静态绑定的两个断裂场景在此拦截/报告：
1. import 级悬空：页面对象 import 的元素模块文件不存在（元素文件被删）；
   用例 import 的页面对象文件不存在（页面文件被删）。
2. 属性级悬空：页面方法引用 self._elements.<名>，但元素类 __init__ 未定义
   self.<名>（元素被改名或漏保存）——覆盖「同名覆盖只能改定位值、改名必断」的短板。

两个入口：
- check_staged_bindings(staged, root)：用例包入库时调用（admin_routes.import_case_package）。
  staged = [(kind, name, target_abs, tmp_path), ...]；新文件读暂存内容、旧文件读磁盘，
  悬空即整体回滚——三件套不可半成品。
- scan_dangling_bindings(root)：全库扫描（tools/check_bindings.py / 排查用），
  返回问题清单字符串。
"""
import ast
import os


def _parse(path):
    try:
        with open(path, encoding='utf-8') as f:
            return ast.parse(f.read())
    except Exception:
        return None


def _self_attrs(tree):
    """类体内 self.XXX = ... 赋值的属性名集合（元素类的元素定义）。"""
    attrs = set()
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if isinstance(node, ast.ClassDef):
            for item in ast.walk(node):
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                                and t.value.id == 'self'):
                            attrs.add(t.attr)
    return attrs


def _elem_refs(tree):
    """页面/用例文件 AST → [(module_str, lineno)]：import 的 page_objects 子模块。"""
    refs = []
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('page_objects.'):
            refs.append((node.module, node.lineno))
    return refs


def _elements_attr_uses(tree):
    """页面方法体里 self._elements.<名> 的引用名集合。"""
    uses = set()
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute)
                and node.value.attr == '_elements'
                and isinstance(node.value.value, ast.Name) and node.value.value.id == 'self'):
            uses.add(node.attr)
    return uses


def _module_to_path(root, module):
    """page_objects.a.b.c → <root>/page_objects/a/b/c.py"""
    return os.path.normpath(os.path.join(root, module.replace('.', '/') + '.py'))


def _read_src(target, staged_map):
    """优先读暂存内容（本次入库的新版本），否则读磁盘。返回 (src_path or None)。"""
    if target in staged_map:
        return staged_map[target]
    return target if os.path.isfile(target) else None


def check_staged_bindings(staged, root):
    """入库时校验：staged 新文件 + 磁盘旧文件构成的可引用集合内，引用必须闭合。
    返回错误字符串列表（空 = 通过）。"""
    staged_map = {os.path.normpath(t): tmp for _, _, t, tmp in staged}
    errors = []
    for kind, name, target, tmp in staged:
        if kind not in ('pages', 'cases') or not name.endswith('.py'):
            continue
        tree = _parse(tmp)
        if tree is None:            # 语法错由 _stage_file 负责，这里跳过
            continue
        rel = os.path.relpath(target, root).replace(os.sep, '/')
        # import 级：引用的 page_objects 子模块必须存在（staged 或磁盘）
        for module, lineno in _elem_refs(tree):
            dep = _module_to_path(root, module)
            if dep not in staged_map and not os.path.isfile(dep):
                errors.append('%s: 第 %d 行引用模块 %s 不存在（悬空 import：被引用文件已删除或未随包上传）'
                              % (rel, lineno, module))
        # 属性级：仅页面对象——self._elements.<名> 必须在元素类中定义
        if kind != 'pages':
            continue
        uses = _elements_attr_uses(tree)
        if not uses:
            continue
        # 本页面对象 import 的元素模块（生成器约定：单元素模块；多模块取并集）
        elem_targets = [_module_to_path(root, m) for m, _ in _elem_refs(tree)
                        if '/elements/' in _module_to_path(root, m)]
        defined = set()
        for et in elem_targets:
            src = _read_src(et, staged_map)
            if src:
                defined |= _self_attrs(_parse(src))
        missing = uses - defined
        if missing:
            errors.append('%s: 方法引用了元素 %s，但元素类中未定义（元素被改名或未保存）'
                          % (rel, '、'.join(sorted(missing))))
    return errors


def scan_dangling_bindings(root):
    """全库扫描磁盘现状：pages/ 与 cases/ 下所有 py 的悬空引用清单。"""
    errors = []
    for sub in ('pages', 'cases'):
        base = os.path.join(root, 'page_objects', 'app_ui', 'android', 'demoProject', sub) \
            if sub == 'pages' else os.path.join(root, 'cases', 'app_ui', 'android', 'demoProject')
        if not os.path.isdir(base):
            continue
        for fn in sorted(os.listdir(base)):
            if not fn.endswith('.py'):
                continue
            path = os.path.join(base, fn)
            tree = _parse(path)
            if tree is None:
                continue
            rel = os.path.relpath(path, root).replace(os.sep, '/')
            for module, lineno in _elem_refs(tree):
                dep = _module_to_path(root, module)
                if not os.path.isfile(dep):
                    errors.append('%s: 第 %d 行悬空 import %s' % (rel, lineno, module))
            if sub == 'pages':
                uses = _elements_attr_uses(tree)
                if uses:
                    elem_targets = [_module_to_path(root, m) for m, _ in _elem_refs(tree)
                                    if '/elements/' in _module_to_path(root, m)]
                    defined = set()
                    for et in elem_targets:
                        if os.path.isfile(et):
                            defined |= _self_attrs(_parse(et))
                    missing = uses - defined
                    if missing:
                        errors.append('%s: 引用未定义元素 %s' % (rel, '、'.join(sorted(missing))))
    return errors
