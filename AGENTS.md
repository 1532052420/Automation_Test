# AutomationTest 项目代理规范

本项目的所有任务在执行前，必须先声明：**「我已按照 agents.md 执行了 xxx skill」**，并 genuinely 按对应 skill 的规范执行，而不是只走声明形式。

## 四条强制规范（全项目默认启用）+ 一条按需规范

以下四条规范为**项目默认生效**，无需每次手动指定、无需用户显式调用 skill；只要任务落在对应触发范围内，即自动适用。

| # | skill | 默认启用的触发范围 | 安装位置 |
|---|-------|------------------|---------|
| 1 | `ponytail` | 写代码、改代码、修 bug、重构、审查 diff、选型依赖 | `.workbuddy/skills/ponytail/` |
| 2 | `icon-generator` | 为 App / 网页（含 web_platform 测试平台）产出或修改图标 | `.workbuddy/skills/icon-generator/` |
| 3 | `qa-engineer-agent` | 设计测试策略、编写测试用例、执行测试验收 | `.workbuddy/skills/qa-engineer-agent/` |
| 4 | `version-changelog` | **任何对项目产物（代码/UI/配置/文档）产生修改的任务** | `.workbuddy/skills/version-changelog/` |
| 5 | `frontend-design` | 新增页面 / 可点击 HTML 原型的视觉方向（**按需启用，非默认强制**） | `.workbuddy/skills/frontend-design/` |
| 6 | `version-github-release` | **版本号迭代收尾**（version-changelog 递增之后）：双数→推送 GitHub，单数→不上传 | `.workbuddy/skills/version-github-release/` |

> 同一份 skill 亦同步存放于 `.zcode/skills/`（ZCode/Qoder 运行时读取路径）。两处内容需保持一致，权威副本为 `.workbuddy/skills/`。

### 1. 编码任务 — 严格执行 ponytail skill

涉及写代码、改代码、修 bug、重构、选型依赖时，一律按 `.workbuddy/skills/ponytail/SKILL.md` 的阶梯执行：
YAGNI（先问要不要做）→ 复用本仓库已有实现 → 标准库 → 平台原生特性 → 已装依赖 → 一行能写就不写五十行。最短可用 diff 优先，不做未要求的抽象。默认强度 `full`。

配套子 skill（同一目录，按需自动加载）：`ponytail-review`（diff 审查）、`ponytail-audit`（全库审计）、`ponytail-debt`（技术债台账）、`ponytail-gain`（收益看板）、`ponytail-help`（速查卡）。
ponytail 完整插件仓库备份在 `ponytail-main/`（含 hooks、MCP、命令、文档与示例，供参考及在其他运行时安装使用）。

### 2. UI 交付 — 严格执行 icon-generator skill

为 App、网页（含 web_platform 测试平台）产出或修改图标时，按 `.workbuddy/skills/icon-generator/SKILL.md` 执行：SVG 单一源文件（24×24 网格、统一描边/圆角/配色），脚本导出 16~256 六档 PNG，风格与现有 UI 一致后方可交付。

### 3. 测试验收 — 严格执行 qa-engineer-agent skill

设计测试策略、编写测试用例、执行测试验收时，按 `.workbuddy/skills/qa-engineer-agent/SKILL.md` 执行：测试金字塔（单元 60% / 集成 30% / E2E 10%）、AAA 模式（Arrange-Act-Assert）、全路径覆盖（正向 → 边界 → 异常 → 特殊场景）、测试隔离且幂等、报告必有证据（状态统计 + 缺陷分级）。测试用例格式遵循其 TC_ID 标准。

### 4. 版本号与更新日志 — 严格执行 version-changelog skill

**任何对项目产物产生修改的任务（含代码、UI、配置、文档），收尾时必须执行**，规范见 `.workbuddy/skills/version-changelog/SKILL.md`：

- **唯一数据源**：`web_platform/changelog.py` 的 `APP_VERSION` 与 `CHANGELOG`。平台与元素定位器**共用同一版本号**，禁止在别处硬编码（定位器 `APP_VERSION` 只是读取后加 `v` 前缀）。
- **递增规则**：有修改 → 版本号 **+1**（3.3 → 3.4）；重大改造 / 不兼容变更 → **+2**（3.3 → 3.5）。
- **必录内容**：在 `CHANGELOG` **顶部**追加一条，含版本号、**更新时间（精确到秒）**、一句话标题、本次「改了什么 / 修了什么」明细。
- **无需改 UI**：平台左下角「📋 更新日志」入口自动读该数据源展示，不必另写界面。
- 同一次任务只升一次版本号；确无任何产物改动的纯问答可跳过。

紧接着执行 `.workbuddy/skills/version-github-release/SKILL.md`（用户 2026-09-18 明确要求）：

- **双数版本号 → 提交并推送到 GitHub**（`automation_test` = `1532052420/Automation_Test`）；**单数 → 不上传**。
- 每次执行完必须原样回复结论：`已执行skill，版本号为单数，未上传` 或 `已执行skill，版本号为双数，已上传`。
- 禁止 force push；推送后必须用 `git ls-remote` 复核（本机写操作回显不可靠），不得假报成功。

### 5. UI 视觉设计 — 按需启用 frontend-design skill（非默认强制）

来源：`anthropics/skills` 官方 `frontend-design`（[skills.sh 页面](https://skills.sh/anthropics/skills/frontend-design)），已装到 `.workbuddy/skills/frontend-design/`。**它不默认生效**——只在需要「新页面 / 可点击 HTML 原型」的视觉方向时加载。

用途：产出不落俗套的界面视觉方案（配色、字体、版式、动效的取舍），并把想法快速落成浏览器可打开、可点击的 HTML 原型，用于评审对齐与跟研发/设计师沟通。

项目内的三条硬边界（写在该 skill 末尾「本项目适配」一节，冲突时以其为准）：

- **不覆盖主题契约**：`web_platform` 与 `element_locator` 已统一「日间默认 + `html.night` 夜间覆盖」，颜色走 `style.css` 的 CSS 变量。改既有页面时视觉语言服从现状，设计自由度只用在新增页面上。
- **不引外部资源**：内网环境，禁止 CDN 字体 / 外链图片 / 在线 JS。
- **图标仍走 icon-generator**：需要图标时按第 2 条规范出 SVG 源文件再导出 PNG。

## 执行声明格式

每次任务开始时输出一行，例如：

- 「我已按照 agents.md 执行了 ponytail skill」
- 「我已按照 agents.md 执行了 icon-generator skill」
- 「我已按照 agents.md 执行了 qa-engineer-agent skill」
- 「我已按照 agents.md 执行了 version-changelog skill」

任务同时涉及多个规范时，逐条声明。未涉及编码/UI/测试/改动的纯问答任务可不声明。

## 停用方式

单一任务临时绕过：在任务中说明「本次不用 ponytail」（或对应 skill）。全局停用需删除 `.workbuddy/skills/` 下对应目录并同步更新本文件。
