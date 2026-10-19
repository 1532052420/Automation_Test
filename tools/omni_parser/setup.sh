#!/bin/bash
# OmniParser 独立工具 · 一键安装（手动执行）：建独立 venv → 装依赖 → 下模型
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3.12}
echo "== 1/3 使用 $PY 创建独立虚拟环境 .venv =="
"$PY" -m venv .venv
./.venv/bin/pip install -U pip -q
echo "== 2/3 安装依赖（torch 等约 2GB，耐心等）=="
./.venv/bin/pip install -r requirements.txt
echo "== 3/3 下载 OmniParser 模型权重（约 6GB，直连失败自动切 hf-mirror）=="
./.venv/bin/python download_models.py
echo "== 完成。运行：./.venv/bin/python server.py 然后打开 http://127.0.0.1:8090 =="
