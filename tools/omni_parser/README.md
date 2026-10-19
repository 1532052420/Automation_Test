# OmniParser 屏幕解析 · Web 自动化代码生成（独立工具）

> **完全独立**的项目：不 import 自动化测试框架的任何模块、不共享平台配置与依赖。
> 定位：上传 **Web 页面截图** → OmniParser 识别可交互元素 → 自然语言描述意图 →
> 免费档文本大模型生成 **Selenium Python** 自动化代码。
> APP（Android）接入为后续规划，当前仅支持 Web。

## 目录结构

```
tools/omni_parser/
  server.py            # 独立服务（FastAPI，默认 127.0.0.1:8090）
  parser.py            # OmniParser 推理封装（icon_detect 检测 + icon_caption 描述）
  llm_client.py        # 文本大模型客户端（OpenAI 兼容 /chat/completions）
  config.yaml          # 手动配置：LLM 地址/密钥/模型、阈值、端口
  requirements.txt     # 独立依赖（Python 3.12 + torch，与平台 3.8 venv 完全分开）
  download_models.py   # 模型权重下载（microsoft/OmniParser-v2.0，约 6GB）
  setup.sh             # 一键：建独立 venv → 装依赖 → 下模型
  static/index.html    # 工具页面
  models/              # 权重目录（setup.sh 自动下载，也可手动放置）
```

## 安装（手动，一次性）

```bash
cd tools/omni_parser
./setup.sh
```

- 前置：Python 3.12（`python3.12 --version`）；能访问 HuggingFace（不通时 setup.sh 自动切 hf-mirror.com 镜像）。
- 权重约 6GB，装完可用 `./.venv/bin/python download_models.py` 单独重下。

## 运行

```bash
cd tools/omni_parser
./.venv/bin/python server.py
# 浏览器打开 http://127.0.0.1:8090
```

首次使用先在页面左侧「服务配置」填 LLM（OpenAI 兼容接口，如智谱 GLM-4-Flash 免费档），
或直接编辑 `config.yaml`。配置只存在本目录，与平台无关。

## 与平台的关系

- 平台**首页有一张「屏幕解析」卡片入口**，点击新窗口打开本工具；
  卡片上有在线/离线状态灯（仅浏览器侧探测，不依赖平台后端）。
- 平台不 import 本目录任何代码；本目录也不 import 平台任何代码。
- 端口改了的话，同步改平台首页卡片链接（web_platform/templates/index.html）。

## 许可证说明

- 模型：microsoft/OmniParser-v2.0 的 icon_detect / icon_caption 为 MIT。
- 检测推理默认用 ultralytics 运行 YOLO 权重（AGPL-3.0）：**仅限内部使用**；
  如需规避，改用 icon_detect_v3 TorchScript 权重（parser.py 已支持 torch.jit 直载）。

## APP 接入规划（未实现）

Android 真机截图的检出质量待实测（OmniParser 训练数据以 Web/桌面为主）。
后续接入点：截图源从"上传"扩为"adb 实时截屏"，代码生成目标从 Selenium 扩为
uiautomator2 / Appium；服务与页面结构不变。
