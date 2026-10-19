# -*- coding: utf-8 -*-
"""视觉断言执行日志存储（output/visual_logs/）——执行端写、平台读/清共用。

记录：records.jsonl 每行一条 JSON（time/run_id/case/case_file/name/scope/
match_mode/threshold/ok/err/imgs{baseline,actual,triple}）；图片在 imgs/ 下。

与用例的绑定与级联：
- case_file = 产生断言时的用例文件相对路径（conftest 经 AT_CURRENT_CASE_FILE 下传）；
- 编排用例删除 → prune_by_case_files 按生成文件清单即时级联（记录+图）；
- 其他删除途径（手动删文件/git）→ prune_stale 在读列表时惰性兜底：
  case_file 指向的文件已不存在即连记录带图移除；
- case_file 为空的旧记录不参与绑定、保留。

路径约定：进程 cwd = 项目根（与 element_locator/visual_assets 相同），
绝对路径入参会归一为相对路径后再匹配。
"""
import json
import os

BASE = os.path.join('output', 'visual_logs')
RECORDS = os.path.join(BASE, 'records.jsonl')
IMGS = os.path.join(BASE, 'imgs')


def _norm(p):
    """路径归一：相对项目根 + POSIX 分隔（匹配用）"""
    p = str(p or '').strip()
    if not p:
        return ''
    if os.path.isabs(p):
        try:
            p = os.path.relpath(p)
        except ValueError:
            return p.replace(os.sep, '/')
    return p.replace(os.sep, '/')


def read_all():
    """读全部记录（文件序 = 时间序，最新在尾）"""
    if not os.path.isfile(RECORDS):
        return []
    out = []
    with open(RECORDS, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _remove_imgs(rec):
    for fn in (rec.get('imgs') or {}).values():
        try:
            p = os.path.join(IMGS, os.path.basename(str(fn)))
            if os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass


def _rewrite(recs):
    tmp = RECORDS + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp, RECORDS)


def prune_by_case_files(case_files):
    """按用例文件路径集合即时级联：删除匹配记录与图片，返回删除条数。

    编排用例删除时调用（传入 codegen.remove_generated 的生成文件清单）。"""
    files = {_norm(p) for p in (case_files or []) if p}
    files.discard('')
    if not files or not os.path.isfile(RECORDS):
        return 0
    keep, drop = [], 0
    for r in read_all():
        if _norm(r.get('case_file')) in files:
            _remove_imgs(r)
            drop += 1
        else:
            keep.append(r)
    if drop:
        _rewrite(keep)
    return drop


def prune_stale():
    """惰性清理：case_file 指向的用例文件已不存在 → 记录连图删除，返回删除条数。

    读取列表时调用，兜底不经编排的删除途径。空 case_file 不参与、保留。"""
    dirty, keep, drop = False, [], 0
    for r in read_all():
        cf = _norm(r.get('case_file'))
        if cf and not os.path.isfile(cf):
            _remove_imgs(r)
            dirty, drop = True, drop + 1
        else:
            keep.append(r)
    if dirty:
        _rewrite(keep)
    return drop
