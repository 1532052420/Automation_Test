# Percy + Maestro 视觉测试集成调研方案

> 调研时间：2026-09-30 · 状态：**仅调研，未实施**（用户要求：数据与功能做成可视化、尽量做成独立模块便于后续输出）
> 仓库：https://github.com/percy/percy-maestro-app （Percy 官方 SDK for Maestro，Android + iOS）

---

## 一、percy-maestro-app 是什么

Percy（BrowserStack 旗下视觉测试平台）官方提供的 **Maestro 流程视觉测试 SDK**。Maestro 是
YAML 驱动的移动 UI 测试框架；该 SDK 让 Maestro 流程在跑功能步骤的同时**逐屏截图上传 Percy 云端**，
由云端完成「基线 vs 当前」的视觉比对，产出 diff 高亮、基线审批（approve）等视觉回归管理能力。

### 1.1 工作原理（README 实录拆解）

```
Maestro YAML 流程
  └─ runScript: 图像注入 polyfill（percyImageLib.js，iOS 才需要）
  └─ runFlow:  子流程（一个 sub-flow = 一组 Percy 快照）
       └─ runScript: percySnapshot(...)   ← GraalJS 脚本内调 SDK
             └─ 本机截图 → POST http://localhost:5338（Percy CLI 本地中转）
                   └─ @percy/cli 进程聚合 → 上传 Percy 云端 build
                         └─ 云端比对：新快照 vs 已批准基线 → diff/新增/无变化
```

关键机制：
- **依赖双进程**：`percy app:exec -- maestro test xxx.yaml`，Percy CLI 与 maestro 必须同机同时运行；
  CLI 在本地 5338 端口起中转服务，SDK 截图推给它。
- **子流程 = 快照分组**：SDK 用 `maestro.launchApp`/`runFlow` 的层级推断快照的 `tagName`，
  README 强调 sub-flow 名即快照名（Android 示例 flow 里每个子流程末尾调 `percySnapshot`）。
- **平台要求**：Maestro ≥ 2.0；Node.js ≥ 14；Android 走真实/模拟设备均可，iOS 需额外注入图像 polyfill。
- **云端归属**：比对、基线审批、历史趋势全部在 Percy（BrowserStack）云端，本地只出截图。

### 1.2 运行前提（本机实测）

| 项 | 要求 | 本机现状 | 结论 |
|---|---|---|---|
| Node.js | ≥ 14 | v22.14.0 | ✅ |
| Maestro | ≥ 2.0 | **2.10.0 已装**（含 Maestro Studio.app） | ✅ |
| Android 设备 | adb 在线 | 已验证可跑真机（本轮调研中设备短暂掉线，属 USB 抖动） | ✅ |
| @percy/cli | 同机运行 | 未装，`npx @percy/cli` 可拉取 | ✅ 可补 |
| **PERCY_TOKEN** | BrowserStack 账号签发 | **本机无任何 Percy 凭据** | ⚠️ **唯一硬门槛** |

> 结论：本地链路（Maestro + 设备 + Percy CLI 中转）完全具备；**云端比对依赖 BrowserStack 账号与付费额度**，
> 截图会上传第三方云（数据出境/保密需评估）。

---

## 二、与我们现有视觉断言的关系（重叠与差异）

平台已有自研视觉断言（`common/appium/visual_assertions.py`，SSIM 算法 + 本地基线 + 三图比对）：

| 维度 | 自研视觉断言（已有） | Percy + Maestro（调研对象） |
|---|---|---|
| 比对算法 | SSIM（scikit-image），本地执行 | Percy 云端（DOM/像素混合，算法闭源） |
| 基线管理 | 文件随 git（elements/baselines/） | 云端集中管理 + **人工审批approve** 流程 |
| 触发方式 | Appium 用例内断言步骤 | Maestro YAML 流程逐屏快照 |
| 报告呈现 | Allure 三图（基线/实际/diff） | Percy Web 控制台（diff 高亮、历史趋势、多分辨率） |
| 成本/依赖 | 零外部依赖 | BrowserStack 账号 + 付费额度 + 截图上云 |
| 与平台耦合 | 深度耦合（元素库/页面方法/断言管理） | **零耦合**（独立 YAML 流程 + 独立 CLI） |

**定位建议**：两者是互补而非替代——自研断言管「用例内单元素视觉点检」，Percy/Maestro 管「整屏流程级
视觉回归 + 基线审批工作流」。若引入，应做成**并行模块**，不动现有视觉断言。

---

## 三、集成方案（调研结论：可做，建议独立模块）

### 3.1 模块形态（对齐 api_testing 的移植先例）

新建独立目录 `web_platform/visual_testing/`（不与现有模块互相 import，便于日后整体抽出交付）：

```
web_platform/visual_testing/
  __init__.py          # Blueprint: visual_test_bp（URL 前缀 /visual）
  routes.py            # 页面 + REST API
  runner.py            # Maestro + Percy CLI 进程编排（subprocess 队列）
  parser.py            # Maestro YAML 解析（流程/子流程清单、快照点位）
  store.py             # 运行记录 JSON 存储（复用 yaml_store 模式，目录内自管）
  templates/visual.html
  static/visual.js
```

### 3.2 功能与数据可视化设计

**页面一：流程管理**
- Maestro YAML 流程列表（`maestro/flows/*.yaml`），新建/编辑（YAML 高亮文本框）/删除
- 解析展示：流程名、子流程清单、每个子流程的快照点位（`percySnapshot` 调用数）
- 可视化：流程步骤树（复用平台现有 steps-list 样式）

**页面二：运行中心**
- 一键运行：`percy app:exec -- maestro test <flow>` 后台进程，实时日志流（复用执行用例的日志轮询模式）
- 运行状态机：排队 → Percy CLI 启动 → maestro 执行中 → 上传中 → 完成/失败
- 可视化：进度时间线 + 实时终端输出

**页面三：结果看板（数据可视化核心）**
- Build 列表：从 Percy CLI 的 JSON 输出 / Percy API 拉取（build id、通过率、diff/新增/缺失快照数、状态）
- 快照对比视图：基线 | 实际 | diff 三联图（与现有视觉断言三图同款布局，数据源换成 Percy 返回）
- 基线审批工作流：diff 快照逐个「采纳为基线 / 拒绝」（调 Percy API），审批状态时间线
- 趋势图：按流程维度统计「新增/变化/未变化」快照数的历史曲线（复用平台图表样式）

### 3.3 数据来源（三条通路，按可用性排序）

1. **本地进程输出**（零依赖可用）：Percy CLI 运行日志 + `--json` 输出 → 解析 build/snapshot 状态，
   本地留存截图（`visual_testing/data/<run_id>/`）——不依赖云端也能看三图
2. **Percy REST API**（需 TOKEN）：build 详情、快照 diff 结果、审批动作——只有云端有完整能力
3. **本地兜底模式**（自研比对接管）：不上云时，对本地截图跑现有 SSIM 引擎出 diff——
   保证「无 BrowserStack 账号时模块依然有完整可视化产出」

### 3.4 分期路线（建议）

| 期 | 内容 | 依赖 | 工作量预估 |
|---|---|---|---|
| 一期 | 模块骨架 + Maestro YAML 管理 + 本地运行（`maestro test` 直跑，截图存本地 + SSIM 三图） | 无（Maestro 已装） | 小 |
| 二期 | 接入 Percy CLI：`app:exec` 编排、JSON 日志解析、Build 看板 | @percy/cli（可装） | 中 |
| 三期 | Percy 云 API：diff 快照拉取、基线审批工作流、趋势图 | **PERCY_TOKEN（需申请）** | 中 |

### 3.5 风险与决策点

| 风险 | 影响 | 缓解 |
|---|---|---|
| Percy 为付费 SaaS，需 BrowserStack 账号 | 三期功能受阻；截图上云合规 | 一二期完全不依赖云端；三期前先申请试用评估额度 |
| 截图上传第三方云 | 数据保密 | 敏感项目走「本地兜底模式」（SSIM 接管） |
| Percy CLI 与 maestro 必须同机 | 部署约束 | 平台本就单机跑 adb 设备，天然满足 |
| iOS 依赖额外 polyfill 与 Mac 构建链 | 暂无用例 | 一期只做 Android |
| 设备稳定性（本轮调研中设备 USB 掉线一次） | 运行中断 | 运行中心暴露设备在线状态，复用平台设备检测 |

---

## 四、结论

1. **可行**：本机 Maestro 2.10 + Node 22 + 真机链路齐备，唯一硬门槛是 Percy 云端需要 BrowserStack 凭据。
2. **建议**：按 api_testing 移植先例做**独立模块 `visual_testing`**（不与现有视觉断言耦合），一二期不依赖
   云端即可交付完整可视化（流程管理 + 本地运行 + SSIM 三图看板），三期再接 Percy 云端审批工作流。
3. **待用户决策**：是否申请 BrowserStack/Percy 试用账号（决定三期是否启动）；视觉断言与 Percy 的
   并行定位是否认可。
