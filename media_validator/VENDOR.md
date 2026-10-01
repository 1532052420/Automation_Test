# vendor/rendercheck 来源与改动说明

- 上游项目：开源库 rendercheck（v0.4.1，MIT License）
- 用途：媒体产物检测插件（`media_validator/`）的**底层测量引擎**。上游库专注
  「AI 生成媒体缺陷检测」（响度/静音/黑帧/冻结帧/完整性等），与本插件定位完全一致。
- 协议：MIT。本仓库为私有仓库、仅本机部署。

## 保留内容

`_core.py`（失败语义/跳过收集）、`_ffmpeg.py`（ffprobe/ffmpeg 测量封装）、
`media.py`（17 个确定性检测断言）、`captions.py` / `text.py` / `lipsync.py`
（media 的确定性依赖）、`py.typed`。

插件引擎（`media_validator/engine.py`）直接调用 `_ffmpeg` 的测量原语
（`streams` / `duration` / `measure` / `measure_video` / `signalstats` 等），
以结构化「检测项 → 期望规则 → 实测值」报告呈现；`media.py` 的断言层保留备用。

## 抹除的上游身份/发布信息

git 提交历史、README、CHANGELOG、CONTRIBUTING、SECURITY、`.github/`（CI/ISSUE 模板）、
`npm/`、`docs/`、`bench/`、`examples/`、`action.yml`、`Dockerfile`、`server.json`
（MCP 注册）、`pyproject.toml`（PyPI 作者元数据）、`LICENSE`（版权声明文件，已移除），
以及库内 `cli.py` / `mcp.py` / `demo.py` / `vision.py`
（Anthropic 网络层，V1 不含 AI 判定）/ `config.py` / `presets.py`（CLI 配置层）。

## 相对上游的代码改动（仅 1 处，均为 Python 3.8 兼容）

`_ffmpeg.py` 两处 `zip(a, b, strict=False)` → `zip(a, b)`（3.10+ 参数；
plain zip 行为与 strict=False 完全等价，语义不变）。
上游其余文件逐字节未改。平台 venv 为 Python 3.8.20，升级前请勿移除此补丁。

## 升级方式

整个 `vendor/rendercheck/` 目录为静态副本，可整体替换为新版文件后重打上述补丁；
插件自身代码不感知其内部结构（只经 `engine.py` 一处调用）。
