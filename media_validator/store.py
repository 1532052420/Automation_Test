# -*- coding: utf-8 -*-
"""媒体产物检测 · 任务与上传文件存储（独立模块，不依赖框架任何代码）

持久化极简：tasks.json 单文件索引 + uploads/ 平面目录。
- 索引读写全程持锁，写走「临时文件 + os.replace」原子替换；
- 任务 id 形如 20261001_093015_a3f2（时间戳 + 4 位随机），文件名即 id__原名；
- 删除任务 = 移除索引记录 + 删除上传文件，无任何残留。
"""
import json
import os
import re
import threading
import time
import uuid

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_MODULE_DIR, 'data')
UPLOADS_DIR = os.path.join(DATA_DIR, 'uploads')
TASKS_FILE = os.path.join(DATA_DIR, 'tasks.json')

# 单文件上传上限（字节）。方案未定值，取 500MB 兜底 4K 短片
MAX_UPLOAD_BYTES = 500 * 1024 * 1024

_lock = threading.Lock()


def _ensure_dirs():
    for d in (DATA_DIR, UPLOADS_DIR):
        if not os.path.isdir(d):
            os.makedirs(d)


def new_task_id():
    return time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:4]


def safe_filename(name):
    """保留可读性的净化文件名：去路径、去控制符，压缩空白；保留中文"""
    name = re.sub(r'[\\/]+', '_', str(name or 'unnamed'))
    name = re.sub(r'[\x00-\x1f]', '', name).strip().strip('.')
    name = re.sub(r'\s+', ' ', name)
    return name[:120] or 'unnamed'


def load_tasks():
    """全部任务（按创建时间倒序）；文件不存在/损坏视为空表"""
    with _lock:
        return _load_from(TASKS_FILE)


def get_task(task_id):
    with _lock:
        for t in _load_from(TASKS_FILE):
            if t.get('id') == task_id:
                return t
    return None


def upsert_task(task):
    """插入或按 id 覆盖任务记录，原子落盘"""
    upsert_task_into(TASKS_FILE, task)


def upsert_task_into(tasks_file, task):
    """按显式路径落盘任务（供后台线程用：线程生命期长于请求上下文，
    不能依赖可能被并发改动的模块级路径，否则会把任务写进错误的存储）。"""
    with _lock:
        tasks = _load_from(tasks_file)
        out, replaced = [], False
        for t in tasks:
            if t.get('id') == task['id']:
                out.append(task)
                replaced = True
            else:
                out.append(t)
        if not replaced:
            out.append(task)
        _save_to(tasks_file, out)


def delete_task(task_id):
    """删除任务记录与其上传文件；返回被删的任务（找不到返回 None）"""
    with _lock:
        tasks = _load_from(TASKS_FILE)
        victim = next((t for t in tasks if t.get('id') == task_id), None)
        if victim is None:
            return None
        _save_to(TASKS_FILE, [t for t in tasks if t.get('id') != task_id])
    if victim.get('stored_path') and os.path.isfile(victim['stored_path']):
        try:
            os.remove(victim['stored_path'])
        except OSError:
            pass
    return victim


def _load_from(tasks_file):
    try:
        with open(tasks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    # 兼容两种落盘形态（纯数组 / {"tasks": [...]}），并滤掉畸形条目防幽灵行
    if isinstance(data, dict):
        data = data.get('tasks') if isinstance(data.get('tasks'), list) else list(data.values())
    if not isinstance(data, list):
        return []
    return [t for t in data if isinstance(t, dict)]


def _save_to(tasks_file, tasks):
    _ensure_dirs()
    tmp = tasks_file + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=1)
    os.replace(tmp, tasks_file)


def save_upload(file_storage, filename, task_id):
    """流式落盘上传文件（带大小上限），返回 (绝对路径, 实际字节数)。

    超限抛 ValueError，由路由转拒收。流式写避免大文件占内存。
    """
    return save_stream(file_storage.stream, filename, task_id)


def save_stream(stream, filename, task_id, max_bytes=None):
    """把任意字节流（上传文件 / URL 下载 / 本地路径副本）流式写入 uploads/。

    超限抛 ValueError 并清理半成品。max_bytes 缺省用模块上限。
    """
    _ensure_dirs()
    if max_bytes is None:
        max_bytes = MAX_UPLOAD_BYTES
    stored_name = '%s__%s' % (task_id, safe_filename(filename))
    path = os.path.join(UPLOADS_DIR, stored_name)
    size = 0
    with open(path, 'wb') as f:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                f.close()
                os.remove(path)
                raise ValueError('文件超过单文件上限 %dMB' % (max_bytes // (1024 * 1024)))
            f.write(chunk)
    return path, size
