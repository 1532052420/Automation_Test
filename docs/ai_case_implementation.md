# AI 用例生成模块 · 实施进度（供后续会话接续）

- 方案：《AI 用例生成模块技术方案（Maestro MCP + 现有 App 自动化平台）》V1.1
  （用户下载目录：`~/Downloads/AI用例生成模块技术方案_Maestro_MCP (1).md`）
- 本文档 = 跨会话检查点。每次实施会话结束前必须更新本文件。
- 最近更新：2026-10-09 19:05（P0 全部收尾 + P2 基础设施完成并验证）

## ✅ 已完成

### P0 技术可行性验证（✅ 全部完成）
- 本机环境：Maestro CLI 2.10.0 ✓ / Java 17.0.20 ✓ / adb ✓ / Python 3.14.7 ✓
- **独立环境**：`ai_case_service/.venv`（python3.14）已建，锁定依赖安装成功，
  导入冒烟通过（langgraph 1.2.14 / mcp 2.3.0 / pydantic 2.14.0）
- **Maestro MCP 真机探针**（2026-10-09 18:18 设备在线窗口完成）：
  - stdio 握手 ✓（newline 分隔 JSON-RPC，server=maestro 1.0.0）
  - tools/list ✓（10 个工具；核心：list_devices / take_screenshot / inspect_screen / run / cheat_sheet）
  - **入参契约**：take_screenshot、inspect_screen、run 都必填 `device_id`；run 用内联 flow YAML
  - list_devices ✓ 枚举到真机 10AG561473007KL（type=real）
  - ⚠ 未闭环：screenshot/inspect/按键三调用真机验证时设备被拔出（18:2x 掉线），
    均已按入参契约实现，待设备再连时在 /ai-case 页「设备观察」点按钮即可验证
- 已知坑：Maestro 2.10 CLI 无 `screenshot` 子命令（MCP 是唯一截图通道）；
  工具返回首段 text 是 Maestro Viewer 推广语（客户端已过滤）

### P1 首页卡片 + 需求解析（✅ 6.14.117 已上线）
- 首页卡片（最近任务状态）→ `/ai-case` 三栏工作台；任务 API + 规则/模型双解析器 +
  状态机 + SSE + 澄清确认 + 取消；任务持久化可恢复；Playwright 全链路零报错

### P2 设备观察与入口确认 · 基础设施（✅ 本次完成）
- `web_platform/ai_case_maestro.py`：官方 maestro mcp 最小 stdio 客户端
  （initialize/tools/call、按 id 分发、串行 RLock、每调用超时、Viewer 文案过滤、
  崩溃自动重启握手）。**踩坑记录：_ensure 在 _rpc 持锁内再走 _rpc 必须用 RLock，
  用 Lock 会永久死锁（已修，探针脚本因无锁未暴露）**
- `web_platform/ai_case_device.py`：adb 兜底（screencap 截图 / uiautomator dump 紧凑层级）、
  设备独占锁（文件锁 config/ai_case/locks/，TTL 30 分钟，持有人是已取消任务自动回收，
  任务取消联动释放）、探索上限配置（config/ai_case/ai_case_settings.yaml，默认 15 跳/5 分钟）、
  证据存档（config/ai_case/evidence/<udid>/，保留最近 20 张）
- 新 API：`GET /devices`、`POST /observe/screenshot`（Maestro 主通道失败自动 adb 兜底，
  来源标注）、`POST /observe/hierarchy`（同兜底）、`POST|DELETE /devices/<udid>/lock`、
  `POST /settings`、`GET /evidence/<udid>/<file>`
- 前端「设备观察」区：手机框画面 + 刷新画面/读取层级/锁定设备三按钮 + 状态标签
  （Maestro 可用性/设备/锁/上限）+ 层级摘要；设备离线时按钮禁用并给指引
- 验证：锁申请/互斥 409/释放 ✓，设置校验 ✓，离线观察秒回友好报错（0.1~2.4s）✓，
  P1 全链路回归 ✓，Playwright 零 JS 报错 ✓

## ⏭️ 下一步（按优先级）

1. **P2 闭环（需设备）**：插上真机后验证 设备观察→截图/层级/锁→（后续探索的前置）。
   若首次截图超时：Maestro 需在手机上装驱动（accessibility 弹窗确认），重试即可。
2. **P2 剩余：AI 探索循环本体**（依赖模型服务）：LangGraph worker（ai_case_service/，
   3.14 venv）编排「观察→决策→执行→复查」，Maestro run 执行点击，候选路径/人工确认
   事件走既有 SSE；设备锁在探索启动时自动获取。
3. **P3 case_spec + 元素映射**：Pydantic 模型、Platform MCP 工具包 YamlStore 只读查询、
   跳转元素定位器采集联动。
4. **P4 试运行 + ZIP**：编译现有 pytest 三件套、复用 runner、build_case_zip 走
   admin_routes「用例包入库」契约。

## ⚠️ 接续注意事项

- 平台 venv 是 **Python 3.8**：web_platform/ 内新增代码必须 3.8 兼容；AI worker 用
  ai_case_service/.venv（3.14）。
- 前端模式：模板+data-page 分发、图标统一 app.js ICONS 字典（**条目多为多行字符串拼接，
  编辑前先读完整条目**）、YamlStore 存储、`{ok: True}` 封装、模板 <style> 内 .aic- 前缀样式。
- git 提交纪律：**禁止 add -A**；damai_u2/、app.py 的 /grab 挂载、index.html 抢票卡片、
  app.js/style.css 中的 damai 相关条目（ticket 图标/icon-red）都不入库——这些文件提交时
  需「HEAD 版本 + 仅本次改动」的 staged 手术（参考 6.14.118 提交做法：
  git show HEAD:file → 重放本次改动 → hash-object + update-index）。
- 平台重启：`kill $(lsof -tiTCP:8080 -sTCP:LISTEN)` 后
  `nohup ./.venv/bin/python web_platform/app.py &`（无 run.sh）；改模板/静态资源后需重启。
- config/ai_case/（任务/锁/证据/设置）是运行时数据，不提交。
