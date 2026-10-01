# 媒体产物检测（Media Artifact Validator）

自动化测试平台的**独立插件模块**：检测 AI 生成的音频 / 视频 / 图片产物质量
（文件完整性、轨道、时长、静音、黑屏、冻结帧、空白图等），产出 PASS / FAIL 检测报告。

对应产品方案：《媒体产物检测插件产品方案》V1 范围（首页入口 / 上传 / 类型识别 /
三类检测 / 检测报告）。

## 零耦合边界（重要）

本模块**不 import 任何框架代码**（`web_platform` / `element_locator` 均不引用），
自带模板、静态资源、存储（`data/`）与测试。对框架的全部接触点只有两处：

| 接触点 | 位置 | 删除动作 |
|---|---|---|
| 蓝图注册（2 行） | `web_platform/app.py` 搜「媒体产物检测」 | 删注释与两行注册 |
| 首页入口卡片（1 块） | `web_platform/templates/index.html` 搜「媒体产物检测」 | 删 `<a class="nav-card">` 块 |

两处都删后，整个 `media_validator/` 目录可整体移除，框架其余代码零残留。

## 目录结构

```
media_validator/
├── __init__.py        # 导出 bp / PLUGIN_VERSION
├── routes.py          # Flask 蓝图：页面 + 上传/检测/任务/报告 API（后台线程检测）
├── engine.py          # 检测编排：ffprobe/ffmpeg 测量 → 规则判定 → 结构化报告
├── rules.py           # 三类媒体默认规则 + 外部输入清洗
├── store.py           # tasks.json 原子索引 + uploads/ 流式落盘（单文件 ≤ 500MB）
├── templates/mv.html  # 自包含页面（含主题内联脚本，随平台日夜模式联动）
├── static/mv.css|mv.js
├── vendor/rendercheck/  # 检测引擎底座（MIT，来源与改动见 VENDOR.md）
├── tests/             # pytest：引擎 + API 两层
└── data/              # 运行时数据（gitignore，不入库）
```

## 检测项（V1）

- **音频**：完整性（全量解码）、格式（封装 vs 扩展名）、时长、音频轨、采样率、声道、静音
- **视频**：完整性、视频轨、音频轨、时长、分辨率、FPS、黑屏（blackdetect）、冻结帧（freezedetect）
- **图片**：完整性（解码校验）、格式、尺寸、文件大小、空白/纯色图判定

规则阈值检测前可改（留空 = 仅报告实测值不判定），规则快照随任务存档。

## 状态机与失败语义

`PENDING → RUNNING → PASSED / FAILED / ERROR`

- **FAILED** = 文件有缺陷（有效检测结果）；
- **ERROR** = 基础设施故障（ffmpeg 缺失、引擎异常）——检测工具坏了不伪装成「文件不合格」。

## 启动与访问

平台照常启动（`.venv/bin/python web_platform/app.py`），首页新增「媒体产物检测」卡片，
直达 `http://127.0.0.1:8080/media-validator/`。依赖：本机安装 `ffmpeg` / `ffprobe`
（`brew install ffmpeg`）；未装时页面顶部状态灯转红并禁止检测。

## 测试

```bash
.venv/bin/python -m pytest media_validator/tests -v
```
