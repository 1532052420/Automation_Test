# -*- coding: utf-8 -*-
"""平台 · YAML 存储层（唯一持久化出入口）

设计约定（为后续迁移数据库预留）：
- 全部实体都通过 YamlStore 的 list/get/create/update/delete 访问，
  业务代码不直接碰文件；
- 每类实体一个 YAML 文件（<data_dir>/<name>.yaml），格式：
    meta:   {next_id: int}          # 自增主键
    items:  [ {...}, ... ]          # 实体列表，dict 字段与模型字段同名
- 未来换库时只需把 YamlStore 换成同等接口的 DB 实现（list/get/create/update/delete），
  调用方零改动；字段结构即表结构。
"""
import os
import threading
import time

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'config')

_write_lock = threading.Lock()


def _now():
    """秒级时间戳（字段名与 testhub 的 auto_now_add 字段对应）"""
    return int(time.time())


class YamlStore:
    """单类实体的 YAML 仓库。线程安全（写加锁 + 原子替换写）。"""

    def __init__(self, name, data_dir=None):
        self.name = name
        self.path = os.path.join(data_dir or DATA_DIR, '%s.yaml' % name)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write({'meta': {'next_id': 1}, 'items': []})

    def _read(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {'meta': {'next_id': 1}, 'items': []}

    def _write(self, data):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp, self.path)      # 原子替换，断电不损坏

    # ---------------- CRUD（未来换 DB 只改这一层） ----------------
    def list(self, **cond):
        """按字段等值过滤；字段值带 _gte/_lte 后缀做数值比较（histories 按时间裁剪用）"""
        items = self._read().get('items') or []
        out = []
        for it in items:
            ok = True
            for k, v in cond.items():
                if k.endswith('_gte'):
                    ok = it.get(k[:-4], 0) >= v
                elif k.endswith('_lte'):
                    ok = it.get(k[:-4], 0) <= v
                else:
                    ok = it.get(k) == v
                if not ok:
                    break
            if ok:
                out.append(it)
        return out

    def get(self, item_id):
        for it in self._read().get('items') or []:
            if it.get('id') == int(item_id):
                return it
        return None

    def create(self, data):
        with _write_lock:
            doc = self._read()
            item = dict(data or {})
            item['id'] = doc['meta']['next_id']
            doc['meta']['next_id'] += 1
            item.setdefault('created_at', _now())
            item.setdefault('updated_at', _now())
            doc['items'].append(item)
            self._write(doc)
            return item

    def update(self, item_id, patch):
        with _write_lock:
            doc = self._read()
            for it in doc['items']:
                if it.get('id') == int(item_id):
                    patch = {k: v for k, v in (patch or {}).items() if k != 'id'}
                    it.update(patch)
                    it['id'] = int(item_id)          # 主键不可被 patch 改写
                    it['updated_at'] = _now()
                    self._write(doc)
                    return it
            return None

    def delete(self, item_id):
        with _write_lock:
            doc = self._read()
            before = len(doc['items'])
            doc['items'] = [it for it in doc['items'] if it.get('id') != int(item_id)]
            if len(doc['items']) == before:
                return False
            self._write(doc)
            return True

    def replace_all(self, items):
        """整体替换（测试/导入用）"""
        with _write_lock:
            doc = self._read()
            doc['items'] = list(items or [])
            self._write(doc)
