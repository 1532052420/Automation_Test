# -*- coding: utf-8 -*-
"""视觉断言资产（App UI 视觉断言方案 §13/§14）

一条资产 = visual_asserts/<名称>/ 下 config.yaml + baseline.png：
  scope: element | region | screen     断言范围（元素/自定义区域/整屏）
  biz_type: 业务类型（Icon/Logo/卡片/Toast…仅管理分类，不影响比对）
  locator: element 范围的稳定定位（执行时实时解析 bounds）
  region:  region 范围的设备绝对坐标（x,y,width,height）
  threshold: 相似度阈值 0~1
  match_mode: strict 像素SSIM | layout 粗粒度结构比对
  ignore_regions: 忽略区域列表（相对视觉区域左上角的坐标，比对时两图同涂白）
baseline = 采集瞬间的裁剪图（未涂忽略区域，忽略在比对时动态应用）。
"""
import base64
import io
import os
import re
import time

ASSETS_DIR = 'page_objects/app_ui/android/demoProject/elements/visual_asserts'

BIZ_TYPES = ['region', 'icon', 'logo', 'image', 'card', 'banner', 'toast', 'popup', 'custom']
BIZ_TYPE_NAMES = {
    'region': '普通区域', 'icon': 'Icon', 'logo': 'Logo', 'image': '图片',
    'card': '卡片', 'banner': 'Banner', 'toast': 'Toast', 'popup': '弹窗', 'custom': '自定义',
}
_NAME_RE = re.compile(r'^[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff-]*$')


def _safe_name(name):
    n = str(name or '').strip()
    return n if _NAME_RE.match(n) else ''


def _dir(name):
    return os.path.join(ASSETS_DIR, _safe_name(name))


def _crop(png_bytes, box):
    """按 (x,y,w,h) 裁剪 PNG；box None 返回原图"""
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes))
    if box:
        x, y, w, h = [int(v) for v in box]
        x2, y2 = min(x + w, img.size[0]), min(y + h, img.size[1])
        if x2 - x < 2 or y2 - y < 2:
            return None
        img = img.crop((x, y, x2, y2))
    return img


def _thumb_dataurl(img, size=(220, 220)):
    t = img.copy()
    t.thumbnail(size)
    buf = io.BytesIO()
    t.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def resolve_box(scope, locator_type, locator_value, region, xml=None):
    """范围 → 裁剪框 (x,y,w,h)。element：xml 内命中节点 bounds（与体检同款匹配）；
    region：前端框选坐标；screen：None=全图。未命中返回 (None, 错误)。"""
    if scope == 'screen':
        return None, None
    if scope == 'region':
        try:
            x, y, w, h = [int(v) for v in (region or [])]
            if w < 2 or h < 2:
                return None, '区域尺寸不合法（%s）' % region
            return (x, y, w, h), None
        except (TypeError, ValueError):
            return None, '区域坐标不合法'
    if scope == 'element':
        if not xml:
            return None, '缺少界面 hierarchy'
        lt = str(locator_type or '').upper()
        lv = (locator_value or '').strip()
        if not lv:
            return None, '元素定位值为空'
        try:
            tree = device.xml_to_tree(xml)
        except Exception as e:
            return None, '元素树解析失败: %s' % str(e)[:80]
        hit = [None]

        def _walk(n):
            if hit[0] is not None:
                return
            rid = n.get('resource-id') or ''
            if lt == 'ID' and rid == lv:
                hit[0] = n
            elif lt == 'ACCESSIBILITY_ID' and (n.get('content-desc') or '') == lv:
                hit[0] = n
            elif lt == 'CLASS_NAME' and (n.get('class') or '') == lv:
                hit[0] = n
            elif lt == 'XPATH':
                import re as _re
                m = _re.search(r"@text='([^']*)'", lv)
                m2 = _re.search(r"@resource-id='([^']*)'", lv)
                if (m and (n.get('text') or '') == m.group(1)) or (m2 and rid == m2.group(1)):
                    hit[0] = n
            for c in n.get('children') or []:
                _walk(c)

        for n in tree.get('all') or []:
            _walk(n)
            if hit[0] is not None:
                break
        if hit[0] is None:
            return None, '元素不在当前屏幕上（hierarchy 未命中该定位）'
        b = hit[0].get('_bounds')
        if isinstance(b, (list, tuple)) and len(b) == 4:
            x1, y1, x2, y2 = [int(v) for v in b]
            return (x1, y1, x2 - x1, y2 - y1), None
        return None, '元素无坐标信息'
    return None, '未知范围 %s' % scope


def capture(scope, locator_type, locator_value, region):
    """当前屏幕 → 裁剪图（PIL Image）。返回 (img, box, err)"""
    import device
    serial = device.get_device(None)
    if not serial:
        return None, None, '未检测到在线设备'
    png = device.screenshot_png(serial)
    if not png:
        return None, None, '屏幕截图失败：' + (device.last_error or '未知原因')
    xml = device.dump_xml(serial) if scope == 'element' else None
    box, err = resolve_box(scope, locator_type, locator_value, region, xml)
    if err:
        return None, None, err
    img = _crop(png, box)
    if img is None:
        return None, None, '区域裁剪失败（bounds=%s）' % (box,)
    return img, box, None


def _norm_regions(regions):
    """忽略区域列表归一化：[(x,y,w,h)]，坐标相对视觉区域左上角"""
    out = []
    for r in (regions or []):
        try:
            x, y, w, h = [int(v) for v in r]
            if w > 0 and h > 0:
                out.append([x, y, w, h])
        except (TypeError, ValueError):
            continue
    return out


def save(name, cfg):
    """保存资产：采集 baseline + 写 config.yaml（已存在则覆盖并留 .prev 备份）"""
    import yaml
    n = _safe_name(name)
    if not n:
        return False, '名称不合法（支持中文/字母/数字/下划线/连字符）'
    scope = cfg.get('scope')
    if scope not in ('element', 'region', 'screen'):
        return False, '断言范围不合法'
    if scope != 'screen' and scope == 'region' and not cfg.get('region'):
        return False, '自定义区域未框选'
    img, box, err = capture(scope, cfg.get('locator_type'), cfg.get('locator_value'), cfg.get('region'))
    if err:
        return False, '基线采集失败：' + err
    d = _dir(n)
    os.makedirs(d, exist_ok=True)
    base_p = os.path.join(d, 'baseline.png')
    if os.path.isfile(base_p):                     # 基准图更新留痕（§18 审计的最小实现）
        import shutil
        shutil.copyfile(base_p, os.path.join(d, 'baseline.prev.png'))
    img.save(base_p)
    conf = {
        'name': n,
        'type': 'visual',
        'scope': scope,
        'biz_type': cfg.get('biz_type') if cfg.get('biz_type') in BIZ_TYPES else 'region',
        'threshold': max(0.0, min(1.0, float(cfg.get('threshold') or 0.98))),
        'match_mode': 'layout' if cfg.get('match_mode') == 'layout' else 'strict',
        'ignore_regions': _norm_regions(cfg.get('ignore_regions')),
        'created': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if scope == 'element':
        conf['locator'] = {'strategy': (cfg.get('locator_type') or 'id').lower(),
                           'value': cfg.get('locator_value')}
    if scope == 'region' and box:
        conf['region'] = list(box)
    with open(os.path.join(d, 'config.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump(conf, f, allow_unicode=True, sort_keys=False)
    return True, {'name': n, 'thumb': _thumb_dataurl(img), 'size': list(img.size)}


def list_assets():
    out = []
    if not os.path.isdir(ASSETS_DIR):
        return out
    import yaml
    for n in sorted(os.listdir(ASSETS_DIR)):
        p = os.path.join(ASSETS_DIR, n, 'config.yaml')
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            continue
        item = {'name': n, 'scope': cfg.get('scope'), 'biz_type': cfg.get('biz_type'),
                'biz_type_name': BIZ_TYPE_NAMES.get(cfg.get('biz_type'), cfg.get('biz_type')),
                'threshold': cfg.get('threshold'), 'match_mode': cfg.get('match_mode'),
                'ignore_count': len(cfg.get('ignore_regions') or []),
                'created': cfg.get('created'), 'has_baseline': os.path.isfile(os.path.join(ASSETS_DIR, n, 'baseline.png'))}
        bp = os.path.join(ASSETS_DIR, n, 'baseline.png')
        if os.path.isfile(bp):
            try:
                from PIL import Image
                with Image.open(bp) as im:
                    item['thumb'] = _thumb_dataurl(im, (140, 140))
            except Exception:
                item['thumb'] = ''
        out.append(item)
    return out


def get_config(name):
    import yaml
    p = os.path.join(_dir(name), 'config.yaml')
    if not os.path.isfile(p):
        return None
    with open(p, encoding='utf-8') as f:
        return yaml.safe_load(f)


def delete(name):
    import shutil
    d = _dir(name)
    if not _safe_name(name) or not os.path.isdir(d):
        return False, '资产不存在'
    shutil.rmtree(d)
    return True, '已删除'


def update_config(name, patch):
    """编辑资产配置（仅开放与采集结果无关的元数据）：
    可编辑 biz_type / threshold / match_mode；名称/范围/基线图不可改（改=重新采集）。
    忽略区域本版只读展示（坐标系相对基线区域，调整请重新采集）。"""
    import yaml
    n = _safe_name(name)
    d = _dir(n)
    cfg_p = os.path.join(d, 'config.yaml')
    if not _safe_name(n) or not os.path.isfile(cfg_p):
        return False, '资产不存在'
    with open(cfg_p, encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}
    if 'biz_type' in patch and patch['biz_type'] in BIZ_TYPES:
        cfg['biz_type'] = patch['biz_type']
    if 'threshold' in patch:
        try:
            cfg['threshold'] = max(0.5, min(1.0, float(patch['threshold'])))
        except (TypeError, ValueError):
            return False, '阈值不合法'
    if 'match_mode' in patch:
        if patch['match_mode'] not in ('strict', 'layout'):
            return False, '比较模式不合法'
        cfg['match_mode'] = patch['match_mode']
    with open(cfg_p, 'w', encoding='utf-8') as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return True, '配置已更新'


def debug_paths(name):
    """调试产物路径：actual（上传的实际图）/ diff（三联图）；不存在返回 None"""
    n = _safe_name(name)
    if not n:
        return None, None
    d = _dir(n)
    a = os.path.join(d, 'debug_actual.png')
    g = os.path.join(d, 'debug_diff.png')
    return (a if os.path.isfile(a) else None), (g if os.path.isfile(g) else None)


def debug_compare(name, actual_bytes):
    """调试比对（零落盘）：上传的实际图 vs 基线，按资产配置执行 SSIM，
    结果（含 diff 三联图）以 base64 返回，图片不保存。
    返回 (ok, data|err)，data 含相似度/阈值/比较模式/忽略区域数等完整参数。"""
    import base64
    import tempfile
    import yaml
    n = _safe_name(name)
    d = _dir(n)
    cfg_p = os.path.join(d, 'config.yaml')
    baseline = os.path.join(d, 'baseline.png')
    if not n or not os.path.isfile(cfg_p):
        return False, '资产不存在'
    if not os.path.isfile(baseline):
        return False, '基线图不存在（请先采集）'
    try:
        with open(cfg_p, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        return False, '配置读取失败: %s' % e
    from common.appium import visual_assertions as _va
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    try:
        tmp.write(actual_bytes)
        tmp.close()
        diff_tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        diff_tmp.close()
        ok, actual, err, triple = _va.compare_images(
            baseline, tmp.name, float(cfg.get('threshold') or 0.98), diff_tmp.name,
            ignore_regions=cfg.get('ignore_regions') or [],
            match_mode=cfg.get('match_mode') or 'strict')
        def _b64(p):
            try:
                with open(p, 'rb') as f:
                    return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
            except Exception:
                return ''
        return True, {
            'passed': ok,
            'similarity': (actual or {}).get('similarity'),
            'threshold': float(cfg.get('threshold') or 0.98),
            'match_mode': cfg.get('match_mode') or 'strict',
            'ignored': len(cfg.get('ignore_regions') or []),
            'baseline_size': (actual or {}).get('baseline_size'),
            'actual_size': (actual or {}).get('actual_size'),
            'err': err or '',
            'triple': _b64(triple) if triple else '',
        }
    finally:
        import os as _os
        for f in (tmp.name, diff_tmp.name):
            try:
                _os.remove(f)
            except OSError:
                pass


def baseline_path(name):
    p = os.path.join(_dir(name), 'baseline.png')
    return p if os.path.isfile(p) else None


# 延迟 import（visual_assets 被 server 引入时 device 已可用）
import device  # noqa: E402
