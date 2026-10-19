#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""下载 OmniParser 模型权重到 models/（约 6GB，一次性）。
直连 HuggingFace 不通时自动切 hf-mirror.com 镜像。"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(BASE, 'models')

try:
    from huggingface_hub import snapshot_download
except ImportError:
    sys.exit('缺 huggingface_hub：请先在独立 venv 里执行 pip install -r requirements.txt')


def main():
    try:
        path = snapshot_download('microsoft/OmniParser-v2.0', local_dir=TARGET)
    except Exception as e:
        print('直连失败（%s），切换 hf-mirror.com 镜像重试…' % e)
        os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
        path = snapshot_download('microsoft/OmniParser-v2.0', local_dir=TARGET)
    print('模型已就绪：', path)
    need = ['icon_detect/model.pt', 'icon_caption/model.safetensors']
    miss = [f for f in need if not os.path.exists(os.path.join(TARGET, f))]
    if miss:
        print('警告：缺少关键文件 %s' % miss)


if __name__ == '__main__':
    main()
