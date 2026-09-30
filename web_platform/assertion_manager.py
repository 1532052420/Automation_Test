# -*- coding: utf-8 -*-
"""断言管理（App自动化 · 元素管理下方）：扫描/筛选/编辑用例中的断言内容

兼容两类断言形态（覆盖平台全部断言方式）：
1. 传统断言（用例行直调）：page.assert_<el>() / assert_<el>_text('期望') /
   assert_<el>_gone() / page.assert_toast('文本')
2. 组合断言（四栏改版，内容内嵌页面方法）：页面方法体内的
   assert_{exists|text|toast|gone|visual}_or_record(failures, '断言N·XX', ...) 调用行

编辑范围（P1）：仅断言内容——期望文本 / Toast 文本 / 等待秒数 / 相似度阈值；
断言方式（类型）修改后续再放。写回前 ast 校验 + .bak 备份。
"""
import ast
import os
import re
import shutil

CASES_DIR = 'cases/app_ui/android/demoProject'
PAGES_DIR = 'page_objects/app_ui/android/demoProject/pages'
IND = '    '

# 断言方式 → 中文名 + 可编辑内容字段
ASSERT_KIND_NAMES = {
    'exists': '断言元素是否可见', 'text': '断言文本是否正确', 'toast': '断言Toast是否出现',
    'gone': '断言元素是否消失', 'visual': '视觉断言', 'color': '断言颜色是否正确',
    'visual_asset': '视觉资产断言',
    'visible': '断言元素是否可见',
}
KIND_FROM_LABEL = [('视觉资产', 'visual_asset'), ('视觉', 'visual'), ('Toast', 'toast'), ('颜色', 'color'),
                   ('文本', 'text'), ('消失', 'gone'), ('存在', 'exists')]


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _write(path, content):
    bak = path + '.bak'
    if os.path.isfile(path):
        shutil.copyfile(path, bak)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _kind_from_label(desc):
    for k, v in KIND_FROM_LABEL:
        if k in desc:
            return v
    return ''


def list_case_files():
    if not os.path.isdir(CASES_DIR):
        return []
    return sorted(f for f in os.listdir(CASES_DIR)
                  if f.startswith('test_') and f.endswith('.py') and not f.endswith('.bak'))


def _method_span(content, method_name):
    """方法体 [start, end) 区间；找不到返回 None"""
    m = re.search(r'^%sdef %s\(' % ('    ', re.escape(method_name)), content, re.MULTILINE)
    if not m:
        return None
    start = content.find('\n', m.end()) + 1
    tail = content[start:]
    nxt = re.search(r'\n    (?:def |@|class )', tail)
    end = start + (nxt.start() + 1 if nxt else len(tail))
    return (start, end)


def _call_name(line):
    m = re.match(r'\s*page\.(\w+)\(', line)
    return m.group(1) if m else ''


def _combo_asserts_in_body(body):
    """页面方法体 → 组合断言条目列表 [{label, kind, line_off, line, fields}]（行偏移相对 body）"""
    out = []
    lines = body.split('\n')
    probe_wait = None
    for i, ln in enumerate(lines):
        mw = re.search(r'wait_seconds=(\d+)', ln)
        if 'CreateElement.create(' in ln and mw:
            probe_wait = int(mw.group(1))          # 探针等待秒数（供 exists/gone 编辑）
        m = re.search(r"assert_(\w+)_or_record\(\s*failures,\s*'([^']*)'", ln)
        if not m:
            continue
        kind_word, desc = m.group(1), m.group(2)
        kind = _kind_from_label(desc) or _kind_from_label(kind_word) or kind_word
        # 组合断言常折行：baseline/threshold/expected 等参数多在调用首行的续行上
        full = ln + ' ' + (lines[i + 1] if i + 1 < len(lines) else '')
        entry = {'label': desc, 'kind': kind, 'line_off': i, 'line': ln.rstrip(), 'wait': probe_wait}
        if kind == 'text':
            me = re.search(r"expected='([^']*)'", full)
            entry['content'] = me.group(1) if me else ''
        elif kind == 'toast':
            mt = re.search(r",\s*'([^']*)',\s*wait_seconds", full)
            entry['content'] = mt.group(1) if mt else ''
        elif kind == 'visual':
            mv = re.search(r'threshold=([\d.]+)', full)
            entry['content'] = mv.group(1) if mv else '0.95'
            mb = re.search(r"baseline='([^']*)'", full)
            entry['baseline'] = mb.group(1) if mb else ''
        elif kind == 'visual_asset':
            ma = re.search(r"visual_asset_or_record\(\s*failures,\s*'[^']*',\s*'([^']*)'", full)
            entry['content'] = ma.group(1) if ma else ''
        elif kind == 'gone':
            entry['content'] = str(probe_wait if probe_wait is not None else 2)
        elif kind == 'exists':
            # 组合断言的存在断言：等待秒数 = 探针 create 行的 wait_seconds（可编辑）
            entry['content'] = str(probe_wait) if probe_wait is not None else ''
        out.append(entry)
        probe_wait = None
    return out


def _scan_case(content, case_file, only_method=None):
    """用例文件 → 断言条目（传统直调 + 组合断言经页面方法展开）"""
    from element_locator.case_generator import parse_case_steps, _page_class_of, resolve_page
    entries = []
    for m in re.finditer(r'^    def (\w+)\(self\):', content, re.MULTILINE):
        method = m.group(1)
        if only_method and method != only_method:
            continue
        steps = parse_case_steps(content, method)
        for idx, st in enumerate(steps, 1):
            if (st.get('type') or '').startswith('assert'):
                kind = _norm_kind(st['type'])
                call_line_no = None
                for li, ln in enumerate(content.split('\n'), 1):
                    if ln.strip() == st.get('call', '').strip() and li > 1:
                        call_line_no = li
                        break
                entries.append({
                    'scope': 'case', 'case_file': case_file, 'method': method,
                    'step_no': idx, 'step_desc': st.get('desc', ''),
                    'kind': kind, 'kind_name': ASSERT_KIND_NAMES.get(kind, kind),
                    'element': st.get('element', ''),
                    'content': st.get('param', ''),
                    'line_no': call_line_no, 'line': st.get('call', ''),
                })
                continue
            # 组合断言：步骤调用页面方法 → 方法体内的 or_record 断言展开
            fn = _call_name(st.get('call', ''))
            if not fn:
                continue
            pc = ''
            for cm in re.finditer(r'^class (\w+)', content, re.MULTILINE):
                seg_start = cm.start()
                nxt = re.search(r'^class ', content[cm.end():], re.MULTILINE)
                seg_end = cm.end() + (nxt.start() if nxt else len(content) - cm.end())
                if re.search(r'^    def %s\(' % re.escape(method), content[seg_start:seg_end], re.MULTILINE):
                    pc = re.search(r'self\.page\s*=\s*(\w+)\(', content[seg_start:seg_end])
                    pc = pc.group(1) if pc else ''
                    break
            if not pc:
                continue
            page_class = pc
            hits = [f for f in _list_page_files() if re.search(r'^class %s\b' % re.escape(page_class),
                    _read(os.path.join(PAGES_DIR, f)), re.MULTILINE)]
            if len(hits) != 1:
                continue
            pcontent = _read(os.path.join(PAGES_DIR, hits[0]))
            span = _method_span(pcontent, fn)
            if not span:
                continue
            span_start_line = pcontent[:span[0]].count('\n') + 1   # 方法体起始行号
            body = pcontent[span[0]:span[1]]
            for ca in _combo_asserts_in_body(body):
                entries.append({
                    'scope': 'page', 'case_file': case_file, 'method': method,
                    'step_no': idx, 'step_desc': st.get('desc', ''),
                    'kind': ca['kind'], 'kind_name': ASSERT_KIND_NAMES.get(ca['kind'], ca['kind']),
                    'element': fn.replace('click_', '').replace('check_', ''),
                    'content': ca.get('content', ''),
                    'baseline': ca.get('baseline', ''),
                    'page_file': hits[0], 'page_method': fn,
                    'line_no': span_start_line + ca['line_off'],
                    'line': ca['line'],
                })
    return entries


def _list_page_files():
    if not os.path.isdir(PAGES_DIR):
        return []
    return sorted(f for f in os.listdir(PAGES_DIR)
                  if f.endswith('.py') and f != '__init__.py' and not f.endswith('.bak'))


def list_assertions(case_file=None):
    cases = list_case_files()
    entries = []
    for cf in cases:
        if case_file and cf != case_file:
            continue
        path = os.path.join(CASES_DIR, cf)
        if not os.path.isfile(path):
            continue
        entries.extend(_scan_case(_read(path), cf))
    for e in entries:
        # 可编辑内容：text(期望文本)/toast(文本)/gone·exists(等待秒数，仅组合断言带该参数)/
        # visual(阈值)/color(色值容差)；传统 exists 直调行无参数（等待由元素库定义）→ 不可编辑
        e['editable'] = e['kind'] in ('text', 'toast', 'visual', 'gone', 'color') or \
            (e['kind'] == 'exists' and (e['scope'] == 'page' or bool(str(e.get('content', '')))))
    return cases, entries


def _esc_sq(s):
    return str(s).replace("'", "\\'")


def _rewrite_window(lines, kind, content):
    """在多行窗口内应用断言内容替换，返回 (新行列表, 是否变更)。
    覆盖全部断言方式的内容字段（组合多行调用与传统单行同等支持）。"""
    changed = False

    def sub(ln, pat, repl):
        nonlocal changed
        nl = re.sub(pat, repl, ln)
        if nl != ln:
            changed = True
        return nl

    for i, ln in enumerate(lines):
        if kind == 'text':
            if 'expected=' in ln:
                lines[i] = sub(ln, r"expected='[^']*'", "expected='" + _esc_sq(content) + "'")
            elif '_text(' in ln:
                lines[i] = sub(ln, r"(_text\(')[^']*(')", lambda m: m.group(1) + _esc_sq(content) + m.group(2))
        elif kind == 'toast':
            if 'assert_toast' in ln and "'" in ln:
                # 组合形态：'文本', wait_seconds=…；传统形态：assert_toast('文本')
                nl = re.sub(r"'((?:[^']|\\')*)'(\s*,\s*wait_seconds)",
                            lambda m: "'" + _esc_sq(content) + "'" + m.group(2), ln)
                if nl == ln:
                    nl = re.sub(r"(assert_toast\(')((?:[^']|\\')*)(')",
                                lambda m: m.group(1) + _esc_sq(content) + m.group(3), ln)
                if nl != ln:
                    changed = True
                lines[i] = nl
        elif kind in ('exists', 'gone'):
            if 'wait_seconds=' in ln and ('or_record' in ln or 'CreateElement.create(' in ln):
                lines[i] = sub(ln, r'wait_seconds=\d+', 'wait_seconds=' + str(int(content or 2)))
        elif kind == 'visual':
            if 'threshold=' in ln:
                lines[i] = sub(ln, r'threshold=[\d.]+', 'threshold=' + str(float(content or 0.95)))
        elif kind == 'color':
            if 'expect_rgb=' in ln:
                lines[i] = sub(ln, r'expect_rgb=\([^)]*\)', 'expect_rgb=(' + content + ')')
            if 'tolerance=' in ln:
                lines[i] = sub(ln, r'tolerance=\d+', 'tolerance=' + str(int(content or 20)))
    return lines, changed


def _norm_kind(k):
    """kind 归一化：传统全名 → 短名（组合断言用短名）"""
    return {'assert_text': 'text', 'assert_toast': 'toast', 'assert_gone': 'gone',
            'assert_visible': 'exists'}.get(k, k)


def update_assertion(target, content):
    """target: list_assertions 返回的条目（含 scope/file/line_no/line/kind）。
    按行号+原行内容定位（行号漂移时按原行全文唯一匹配），改写后 ast 校验再落盘。"""
    kind = _norm_kind(target.get('kind', ''))
    if kind not in ('text', 'toast', 'visual', 'gone', 'exists', 'color'):
        return False, '该断言方式暂不支持内容编辑（%s）' % kind, ''
    if target.get('scope') == 'case':
        path = os.path.join(CASES_DIR, target['case_file'])
    else:
        path = os.path.join(PAGES_DIR, target['page_file'])
    if not os.path.isfile(path):
        return False, '文件不存在', ''
    content_bytes = _read(path)
    lines = content_bytes.split('\n')
    idx = int(target.get('line_no') or 0) - 1
    if not (0 <= idx < len(lines)) or lines[idx].strip() != str(target.get('line', '')).strip():
        pos = [i for i, l in enumerate(lines) if l.strip() == str(target.get('line', '')).strip()]
        if len(pos) != 1:
            return False, '断言行已变化，请刷新列表后重试'
        idx = pos[0]
    # 窗口式改写：定位行 ±8 行（组合断言的多行调用/探针行均在窗口内）
    lo, hi = max(0, idx - 8), min(len(lines), idx + 9)
    window = lines[lo:hi]
    new_window, changed = _rewrite_window(window, kind, str(content))
    if not changed:
        return False, '未产生变更（检查断言方式与内容格式）', ''
    lines[lo:hi] = new_window
    new_content = '\n'.join(lines)
    try:
        ast.parse(new_content)
    except SyntaxError as e:
        return False, '修改后语法不合法（已取消保存）: %s' % e, ''
    _write(path, new_content)
    return True, new_content, new_content
