# -*- coding: utf-8 -*-
"""视觉断言 · 元素区域截图与基线比对（四栏断言改版 · ④断言栏）

模式对标 web_platform/api_testing/media_assertions.py：
公共检测方法返回 (passed, actual, error)，错误累积、阈值可配、绝不硬比不合法输入。

- 比对：元素区域实际截图 vs 基线图（灰度 SSIM，skimage 旧 API / cv2 兜底像素差）；
- 基线缺失 → 自动建立（实际图复制为基线，passed=True 并在 actual 注明，报告可见）；
- 尺寸不一致 → 判「分辨率不匹配」不硬比（跨设备首版限制）；
- 三联图：基线/实际/diff 横向拼接一张 PNG，由调用方 allure.attach（平台 tweaks 自动缩略）。

基线存放约定：page_objects/.../elements/baselines/<元素文件名>/<元素名>.png（随包进 git）。
"""
import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _imread_gray(path):
    import cv2
    import numpy as np
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError('图像读取失败: %s' % path)
    return img


def _similarity(a, b):
    """灰度 SSIM（skimage 旧 API），不可用时退化为归一化像素差相似度"""
    try:
        from skimage.measure import compare_ssim
        return float(compare_ssim(a, b))
    except Exception:
        import cv2
        import numpy as np
        diff = cv2.absdiff(a, b)
        return 1.0 - float(np.count_nonzero(diff)) / diff.size


def _diff_triple(baseline_path, actual_path, out_path, ignore_regions=None):
    """基线/实际/diff 三联图（diff=红色高亮差异区域叠加在灰度实际图上；忽略区域涂白标注）"""
    import cv2
    import numpy as np
    b = cv2.imread(baseline_path)
    a = cv2.imread(actual_path)
    ga = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    if ignore_regions:
        ga = _apply_ignores(ga, ignore_regions)
        gb = _apply_ignores(gb, ignore_regions)
    diff = cv2.absdiff(ga, gb)
    _, mask = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
    mark = a.copy()
    mark[mask > 0] = (0, 0, 255)
    # 忽略区域在 diff 图上涂白（可视化为「已排除」）
    for (x, y, rw, rh) in (ignore_regions or []):
        x1, y1 = max(0, int(x)), max(0, int(y))
        x2, y2 = min(mark.shape[1], int(x) + int(rw)), min(mark.shape[0], int(y) + int(rh))
        if x2 > x1 and y2 > y1:
            mark[y1:y2, x1:x2] = (255, 255, 255)
    h = max(b.shape[0], a.shape[0], mark.shape[0])

    def _pad(img):
        return cv2.copyMakeBorder(img, 0, h - img.shape[0], 0, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255))

    row = np.hstack([_pad(b), _pad(mark), _pad(a)])
    cv2.imwrite(out_path, row)
    return out_path


def _apply_ignores(gray, ignore_regions):
    """忽略区域涂白（比对/diff 均不参与）。ignore_regions: [(x,y,w,h)]（相对本图坐标）"""
    import cv2
    h, w = gray.shape[:2]
    for (x, y, rw, rh) in (ignore_regions or []):
        x1, y1 = max(0, int(x)), max(0, int(y))
        x2, y2 = min(w, int(x) + int(rw)), min(h, int(y) + int(rh))
        if x2 > x1 and y2 > y1:
            gray[y1:y2, x1:x2] = 255
    return gray


def _layout_sim(a, b):
    """Layout 模式：缩放到粗粒度结构图（高 64px）再 SSIM——
    文字/图标内容的小变化被下采样抹平，位置与尺寸变化仍然显著（方案 §11 Layout 语义）"""
    import cv2
    def coarse(g):
        h, w = g.shape[:2]
        nh = 64
        nw = max(1, round(w * nh / h))
        return cv2.resize(g, (nw, nh), interpolation=cv2.INTER_AREA)
    return _similarity(coarse(a), coarse(b))


def compare_images(baseline_path, actual_path, threshold=0.95, diff_out=None,
                   ignore_regions=None, match_mode='strict'):
    """公共检测方法：基线 vs 实际（视觉断言三范围统一入口，两图须同口径裁剪）。
    ignore_regions: [(x,y,w,h)] 相对图内坐标，涂白后不参与比对（diff 图同样标注忽略）。
    match_mode: strict=像素级 SSIM；layout=粗粒度结构比对（内容小变化不敏感）。
    返回 (passed, actual: dict, error: str|None, triple_path: str|None)。"""
    try:
        if not baseline_path or not os.path.isfile(baseline_path):
            return False, None, '基线图不存在: %s' % baseline_path, None
        if not actual_path or not os.path.isfile(actual_path):
            return False, None, '实际截图不存在: %s' % actual_path, None
        a = _imread_gray(baseline_path)
        b = _imread_gray(actual_path)
        if a.shape != b.shape:
            return (False, {'baseline_size': '%dx%d' % (a.shape[1], a.shape[0]),
                            'actual_size': '%dx%d' % (b.shape[1], b.shape[0])},
                    '分辨率不匹配（基线 %dx%d vs 实际 %dx%d）——请在同设备上重新采集基线'
                    % (a.shape[1], a.shape[0], b.shape[1], b.shape[0]), None)
        if ignore_regions:
            a = _apply_ignores(a, ignore_regions)
            b = _apply_ignores(b, ignore_regions)
        sim = _layout_sim(a, b) if match_mode == 'layout' else _similarity(a, b)
        # 差异集中区域（失败时说明「差异在哪个位置」）：忽略涂白后的像素差外接矩形
        try:
            import cv2
            import numpy as np
            diff_m = cv2.absdiff(a, b)
            _, mk = cv2.threshold(diff_m, 24, 255, cv2.THRESH_BINARY)
            ys, xs = np.where(mk > 0)
            diff_bbox = [int(xs.min()), int(ys.min()),
                         int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)] if len(xs) else []
        except Exception:
            diff_bbox = []
        triple = None
        if diff_out:
            try:
                triple = _diff_triple(baseline_path, actual_path, diff_out, ignore_regions)
            except Exception:
                triple = None
        ah, aw = a.shape[:2]
        bh, bw = b.shape[:2]
        actual = {'similarity': round(sim, 4), 'threshold': threshold, 'match_mode': match_mode,
                  'ignored': len(ignore_regions or []),
                  'diff_bbox': diff_bbox,
                  'baseline_size': '%dx%d' % (aw, ah), 'actual_size': '%dx%d' % (bw, bh)}
        err = None if sim >= threshold else ('相似度 %.4f 低于阈值 %.2f（模式 %s）' % (sim, threshold, match_mode))
        if diff_bbox:
            err = (err or '') + '（差异集中区域 x=%d, y=%d, %dx%d——见三联图红色高亮）' % tuple(diff_bbox)
        return (sim >= threshold), actual, err, triple
    except Exception as e:
        return False, None, '视觉比对异常: %s' % e, None


def ensure_baseline(actual_path, baseline_path):
    """基线缺失时自动建立：实际图复制为基线。返回 (ok, err)"""
    try:
        os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
        shutil.copyfile(actual_path, baseline_path)
        return True, None
    except Exception as e:
        return False, str(e)
