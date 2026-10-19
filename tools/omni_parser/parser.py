# -*- coding: utf-8 -*-
"""OmniParser 推理封装：截图 → 可交互元素（边界框 + 置信度 + 图标功能描述）。

模型：microsoft/OmniParser-v2.0（icon_detect 检测 + icon_caption(Florence-2) 描述）。
完全独立：不 import 自动化测试框架的任何模块。
"""
import os

import torch
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))

# Florence-2 图标描述任务（官方 pipeline 同款提示词）
CAPTION_TASK = '<MORE_DETAILED_CAPTION>'


def resolve_device(preference='auto'):
    """auto: cuda → mps → cpu 依次探测。"""
    if preference in ('auto', ''):
        if torch.cuda.is_available():
            return 'cuda'
        if getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available():
            return 'mps'
        return 'cpu'
    return preference


class OmniParser:
    """懒加载封装：模型几 GB，首次调用 parse 时才真正加载。"""

    def __init__(self, model_dir='models', device='auto',
                 conf_threshold=0.05, iou_threshold=0.45):
        self.model_dir = os.path.join(BASE, model_dir)
        self.device_name = resolve_device(device)
        self.conf = float(conf_threshold)
        self.iou = float(iou_threshold)
        self._det = None
        self._cap_model = None
        self._cap_processor = None
        self.loaded = False

    # ---------- 模型加载 ----------
    def load(self):
        if self.loaded:
            return
        det_path = os.path.join(self.model_dir, 'icon_detect', 'model.pt')
        if not os.path.isfile(det_path):
            raise FileNotFoundError(
                '未找到检测权重 %s —— 先执行 download_models.py 下载模型' % det_path)
        self._load_detector(det_path)
        self._load_caption()
        self.loaded = True

    def _load_detector(self, det_path):
        # 优先 v3 TorchScript（MIT、免 ultralytics），否则 v2 权重走 ultralytics
        for jit_name in ('model_v3.pt', 'model.script.pt'):
            jit_path = os.path.join(self.model_dir, 'icon_detect', jit_name)
            if os.path.isfile(jit_path):
                self._det = torch.jit.load(jit_path, map_location=self.device_name)
                self._det.eval()
                self._det_kind = 'jit'
                return
        from ultralytics import YOLO
        self._det = YOLO(det_path)
        self._det_kind = 'yolo'

    def _load_caption(self):
        from transformers import AutoProcessor, AutoModelForCausalLM
        cap_dir = os.path.join(self.model_dir, 'icon_caption')
        if not os.path.isdir(cap_dir):
            raise FileNotFoundError('未找到描述模型 %s' % cap_dir)
        cap_device = 'cpu' if self.device_name == 'mps' else self.device_name
        # Florence-2 在 MPS 上有已知数值问题，描述模型兜底 CPU（检测仍走 GPU/MPS）
        self._cap_device = cap_device
        self._cap_processor = AutoProcessor.from_pretrained(
            cap_dir, trust_remote_code=True)
        self._cap_model = AutoModelForCausalLM.from_pretrained(
            cap_dir, trust_remote_code=True,
            torch_dtype=torch.float32).to(cap_device)
        self._cap_model.eval()

    # ---------- 推理 ----------
    def parse(self, image):
        """PIL.Image → 元素列表 [{index, description, confidence, box_xyxy}]。"""
        self.load()
        w, h = image.size
        boxes, confs = self._detect(image)
        elements = []
        if len(boxes):
            descs = self._caption(image, boxes)
        else:
            descs = []
        for i, (box, conf, desc) in enumerate(zip(boxes, confs, descs), 1):
            elements.append({
                'index': i,
                'description': desc,
                'confidence': round(float(conf), 3),
                'box_xyxy': [round(float(v), 1) for v in box],
            })
        return {'image_size': [w, h], 'elements': elements}

    def _detect(self, image):
        if self._det_kind == 'yolo':
            res = self._det.predict(image, conf=self.conf, iou=self.iou,
                                    imgsz=1280, verbose=False,
                                    device=self.device_name)[0]
            if res.boxes is None or len(res.boxes) == 0:
                return [], []
            return (res.boxes.xyxy.cpu().numpy().tolist(),
                    res.boxes.conf.cpu().numpy().tolist())
        # TorchScript 路径（icon_detect_v3）：letterbox 1280 推理后还原坐标
        imgsz = 1280
        scale = min(imgsz / image.width, imgsz / image.height)
        nw, nh = int(image.width * scale), int(image.height * scale)
        canvas = Image.new('RGB', (imgsz, imgsz), (114, 114, 114))
        canvas.paste(image.resize((nw, nh)), (0, 0))
        t = torch.from_numpy(
            __import__('numpy').asarray(canvas)).permute(2, 0, 1).float() / 255.0
        with torch.no_grad():
            out = self._det(t.unsqueeze(0).to(self.device_name))
        boxes, confs = [], []
        for det in out[0]:  # (N,6) cx,cy,w,h,conf,cls
            cx, cy, bw, bh, cf = det[:5].tolist()
            if cf < self.conf:
                continue
            x1, y1 = (cx - bw / 2) / scale, (cy - bh / 2) / scale
            x2, y2 = (cx + bw / 2) / scale, (cy + bh / 2) / scale
            boxes.append([x1, y1, x2, y2])
            confs.append(cf)
        return boxes, confs

    def _caption(self, image, boxes, batch_size=8):
        from PIL import ImageOps
        descs = []
        for start in range(0, len(boxes), batch_size):
            crops = []
            for (x1, y1, x2, y2) in boxes[start:start + batch_size]:
                crop = image.crop((int(x1), int(y1), int(x2), int(y2)))
                # 扩边 10% 让描述模型看到上下文（官方同款 expand 思路）
                pad_x = (x2 - x1) * 0.1
                pad_y = (y2 - y1) * 0.1
                crop = image.crop((max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y)),
                                   min(image.width, int(x2 + pad_x)),
                                   min(image.height, int(y2 + pad_y))))
                crop = ImageOps.pad(crop, (64, 64))
                crops.append(crop)
            texts = [CAPTION_TASK] * len(crops)
            inputs = self._cap_processor(text=texts, images=crops,
                                         return_tensors='pt').to(self._cap_device)
            with torch.no_grad():
                generated = self._cap_model.generate(
                    input_ids=inputs['input_ids'],
                    pixel_values=inputs['pixel_values'].to(torch.float32),
                    max_new_tokens=32, num_beams=1, do_sample=False)
            for gen in self._cap_processor.batch_decode(generated, skip_special_tokens=True):
                # Florence-2 输出形如 "<CAPTION> 文本" 或直接文本，剥任务前缀
                descs.append(gen.split('</s>')[0].split('> ')[-1].strip() or '未命名元素')
        return descs
