# -*- coding: utf-8 -*-
"""P2 设备层：adb 观察兜底 / 设备独占锁 / 探索上限配置 / 证据存档

分工：Maestro MCP 是观察与探索主通道（方案 2.4），adb 是它的兜底
（设备离线/驱动未装时截图与层级仍可用）；设备独占锁保证 Maestro 与
Appium 不同时控同一设备（方案 8.1）。
"""
import json
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

from web_platform.yaml_store import YamlStore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'config', 'ai_case')
EVIDENCE_DIR = os.path.join(DATA_DIR, 'evidence')
LOCK_DIR = os.path.join(DATA_DIR, 'locks')

ADB = shutil.which('adb') or os.path.expanduser('~/Library/Android/sdk/platform-tools/adb')

LOCK_TTL = 1800          # 锁自然过期：30 分钟（过期不等于可抢运行中的任务，见 acquire）
EVIDENCE_KEEP = 20       # 每台设备保留最近 N 张截图
DEFAULT_SETTINGS = {'scope': 'explore', 'max_steps': 15, 'max_minutes': 5}

_settings_store = YamlStore('ai_case_settings', data_dir=DATA_DIR)


# ---------------- 探索上限配置（方案 4：阈值做成配置项） ----------------

def get_settings():
    items = _settings_store.list()
    if not items:
        item = _settings_store.create(dict(DEFAULT_SETTINGS))
    else:
        item = items[0]
    out = dict(DEFAULT_SETTINGS)
    out.update({k: v for k, v in item.items() if k in DEFAULT_SETTINGS})
    return out


def update_settings(patch):
    items = _settings_store.list()
    item = items[0] if items else _settings_store.create(dict(DEFAULT_SETTINGS))
    for k in ('max_steps', 'max_minutes'):
        if k in (patch or {}):
            v = patch[k]
            if not isinstance(v, int) or v < 1 or v > 200:
                return None, '%s 必须是 1~200 的整数' % k
            item[k] = v
    _settings_store.update(item['id'], item)
    return get_settings(), None


# ---------------- adb 观察（兜底通道） ----------------

def adb_devices():
    if not os.path.exists(ADB):
        return [], '本机未安装 adb'
    try:
        out = subprocess.run([ADB, 'devices', '-l'], capture_output=True,
                             text=True, timeout=8).stdout
    except Exception:
        return [], 'adb 执行失败'
    devs = []
    for line in out.splitlines()[1:]:
        m = re.match(r'^(\S+)\t(\S+)', line.strip())
        if not m:
            continue
        udid, state = m.group(1), m.group(2)
        mm = re.search(r'model:(\S+)', line)
        devs.append({'udid': udid, 'state': state, 'model': mm.group(1) if mm else udid})
    return devs, None


def adb_screenshot(udid):
    if not os.path.exists(ADB):
        raise RuntimeError('adb 不可用')
    r = subprocess.run([ADB, '-s', udid, 'exec-out', 'screencap', '-p'],
                       capture_output=True, timeout=30)
    png = r.stdout or b''
    if not png.startswith(b'\x89PNG'):
        raise RuntimeError('screencap 未返回 PNG（设备离线或未授权）')
    return png


_BOUNDS_RE = re.compile(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]')


def adb_hierarchy(udid, cap=200):
    """uiautomator dump → 紧凑控件列表 [{text, rid, cls, clickable, bounds, center}]"""
    if not os.path.exists(ADB):
        raise RuntimeError('adb 不可用')
    subprocess.run([ADB, '-s', udid, 'shell', 'uiautomator', 'dump',
                    '/sdcard/ai_case_uidump.xml'], capture_output=True, timeout=45)
    xml = subprocess.run([ADB, '-s', udid, 'shell', 'cat', '/sdcard/ai_case_uidump.xml'],
                         capture_output=True, text=True, timeout=30).stdout or ''
    if '<hierarchy' not in xml:
        raise RuntimeError('uiautomator dump 失败（界面处于动画/受限页时可能发生，重试即可）')
    elements = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise RuntimeError('层级 XML 解析失败')
    for node in root.iter('node'):
        text = (node.get('text') or '').strip()
        rid = (node.get('resource-id') or '').strip()
        clickable = node.get('clickable') == 'true'
        if not text and not clickable and not rid:
            continue
        m = _BOUNDS_RE.search(node.get('bounds') or '')
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        elements.append({
            'text': text[:40], 'rid': rid.split('/')[-1][:48],
            'cls': (node.get('class') or '').split('.')[-1][:16],
            'clickable': clickable,
            'bounds': [x1, y1, x2, y2],
            'center': [(x1 + x2) // 2, (y1 + y2) // 2],
        })
        if len(elements) >= cap:
            break
    return elements


# ---------------- 设备独占锁（方案 8.1：Maestro 与 Appium 串行） ----------------

def _lock_path(udid):
    return os.path.join(LOCK_DIR, re.sub(r'[^A-Za-z0-9_.-]', '_', udid) + '.json')


def _read_lock(udid):
    try:
        with open(_lock_path(udid), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def get_lock(udid):
    info = _read_lock(udid)
    if not info:
        return None
    if time.time() - info.get('ts', 0) > LOCK_TTL:
        return None   # 过期锁不展示为占用
    return info


def acquire_lock(udid, job_id=None, user='web'):
    """拿不到返回 (None, 原因)。持有者是已取消/过期任务时自动回收。"""
    os.makedirs(LOCK_DIR, exist_ok=True)
    now = time.time()
    info = _read_lock(udid)
    if info and now - info.get('ts', 0) <= LOCK_TTL:
        holder = ('任务 #%s' % info['job_id']) if info.get('job_id') else '人工'
        return None, '设备正被%s锁定（%s）' % (holder, time.strftime('%H:%M:%S', time.localtime(info['ts'])))
    data = {'udid': udid, 'job_id': job_id, 'user': user, 'ts': now}
    tmp = _lock_path(udid) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, _lock_path(udid))
    return data, None


def release_lock(udid):
    try:
        os.remove(_lock_path(udid))
        return True
    except OSError:
        return False


# ---------------- 证据存档 ----------------

def save_evidence(udid, png_bytes):
    d = os.path.join(EVIDENCE_DIR, re.sub(r'[^A-Za-z0-9_.-]', '_', udid))
    os.makedirs(d, exist_ok=True)
    fn = time.strftime('%H%M%S') + '_%d.png' % (int(time.time() * 1000) % 1000)
    with open(os.path.join(d, fn), 'wb') as f:
        f.write(png_bytes)
    shots = sorted(os.listdir(d))
    for old in shots[:-EVIDENCE_KEEP]:
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    return fn
