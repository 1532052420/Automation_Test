# AutomationTest 项目代理规范

本项目的所有任务在执行前，必须先声明：**「我已按照 agents.md 执行了 xxx skill」**，并 genuinely 按对应 skill 的规范执行，而不是只走声明形式。

## 三条强制规范（全项目默认启用）

以下三条规范为**项目默认生效**，无需每次手动指定、无需用户显式调用 skill；只要任务落在对应触发范围内，即自动适用。

| # | skill | 默认启用的触发范围 | 安装位置 |
|---|-------|------------------|---------|
| 1 | `ponytail` | 写代码、改代码、修 bug、重构、审查 diff、选型依赖 | `.workbuddy/skills/ponytail/` |
| 2 | `icon-generator` | 为 App / 网页（含 web_platform 测试平台）产出或修改图标 | `.workbuddy/skills/icon-generator/` |
| 3 | `qa-engineer-agent` | 设计测试策略、编写测试用例、执行测试验收 | `.workbuddy/skills/qa-engineer-agent/` |

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

## 执行声明格式

每次任务开始时输出一行，例如：

- 「我已按照 agents.md 执行了 ponytail skill」
- 「我已按照 agents.md 执行了 icon-generator skill」
- 「我已按照 agents.md 执行了 qa-engineer-agent skill」

任务同时涉及多个规范时，逐条声明。未涉及编码/UI/测试的纯问答任务可不声明。

## 停用方式

单一任务临时绕过：在任务中说明「本次不用 ponytail」（或对应 skill）。全局停用需删除 `.workbuddy/skills/` 下对应目录并同步更新本文件。
