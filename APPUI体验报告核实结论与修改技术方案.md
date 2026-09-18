# APPUI 全流程体验报告 · 核实结论与修改技术方案

> 核实时间：2026-09-18 11:26 · 核实方式：逐条对照源码与运行实例（v6.29）
> 结论总览：**报告 21 项全部属实，无失实项**。报告基于 v6.26/v6.27 走查，之后 v6.29 重构了项目管理页（报告中的部分截图已过时，但问题本身在当前代码中仍然成立，下文逐条标注）。

---

## 一、核实结论明细

| 编号 | 断言 | 核实结果 | 证据位置 |
|---|---|---|---|
| P0-01 | 缺 `pojo.httpResponseResult` 模块，收集阶段 ImportError | ✅ 属实（已复现） | `pojo/` 目录无此文件；`pytest --collect-only` 复现 ModuleNotFoundError |
| P1-01 | 执行参数藏在套件页，四个入口共用 `_runBody()` | ✅ 属实 | `app_testing.js` `_runBody()` 读 `#suiteConf/#suiteUdid/#suiteOwner`；`routes.py _run_nodes()` 空 conf 静默回退第一份 |
| P1-02 | 「设备配置」覆盖参数对 3/4 执行入口无效 | ✅ 属实 | 仅 `app.js startRun()`（选择用例页）传 `appPackage/appActivity`；AT 面板三个入口不传；两处下拉不共享选中状态 |
| P1-03 | 项目只是标签，不绑定元素库/App/conf | ✅ 属实（设计现状） | `project_id` 仅用于筛选与计数 |
| P1-04 | 编排用例的 App 包名/Activity 写死 | ✅ 属实 | `saveOrchCase()` 提交体无这两个字段；`codegen.py` `DEFAULT_APP_PACKAGE/DEFAULT_APP_ACTIVITY` 常量兜底 |
| P1-05 | 切换用例静默清空编排内容 | ✅ 属实 | `orchSel` change → `selectOrchCase()` 无条件覆盖 `_orchSteps`，无 dirty 检查 |
| P2-01 | NOT_RUN 显示成 PENDING | ✅ 属实 | `suiteResultHtml()` 显式把 NOT_RUN 映射为 PENDING 徽章 |
| P2-02 | 空套件/离线时执行按钮不禁用 | ✅ 属实 | 按钮渲染无 disabled 逻辑；后端 `_bad('该套件未包含任何测试用例')` 事后拦截 |
| P2-03 | 套件跨项目混编：前端拦、后端不拦 | ✅ 属实 | `_clean_suite_case_ids()` 只校验用例存在性与去重，无项目一致性校验 |
| P2-04 | 选择用例页没有搜索框（data-key 已铺路） | ✅ 属实 | `run.html #panel-cases` 只有全选/全不选/开始执行；`app.js:224` 注释明确"供顶部搜索框过滤" |
| P2-05 | 同一用例三个名字 | ✅ 属实 | 中文名（YAML）/ pytest node（`TestOrch7::test_orch_7`）/ 文件名（`test_orch7.py`）；v6.29 列表已加「文件名」列，但树与报告仍是 node 名 |
| P2-06 | 报告页两张表同源、空态堆叠 | ✅ 属实 | `report.html`：最近执行（`#recentList`）与报告列表（`#reportList`）同取 `/api/runs` |
| P2-07 | 默认面板落到「设备配置」+ 模板死 `class="on"` | ✅ 属实 | `showRunPanel()` fallback `'exec'`（v6.24 后已是菜单最后一项）；`run.html:18` 死属性仍在 |
| P2-08 | 设备离线只有页脚与设备配置卡提示 | ✅ 属实 | 其余面板执行按钮无状态感知 |
| P3-1 | `_run_nodes(case=None)` 形参从未使用 | ✅ 属实 | 函数体无 `case` 引用 |
| P3-2 | PUT 先改存储再编译，失败不回滚 | ✅ 属实 | `api_case_detail`：`update()` → 编译失败直接 `return _bad`，与 POST 失败删整条的行为不一致 |
| P3-3 | runner.py 文档仍写 kind 两类任务 | ✅ 属实 | `runner.py:13-15` docstring 与 `start_run()` 签名不符 |
| P3-4 | 删 run 不回收报告静态服务进程 | ✅ 属实 | `_report_services` 在 `routes.py`，`delete_run/clear_runs`（runner.py）无法触达，仅 atexit 清理 |
| P3-5 | 项目接口仍校验 member_count/起止日期 | ✅ 属实 | `_clean_project_body()` 三个字段的校验分支还在（v6.26 UI 已删） |
| P3-6 | `list_tasks()` 每次全量扫盘 | ✅ 属实 | `_load_disk_tasks()` 每次 `os.listdir(RUNS_DIR)` + 读全部 result.json |
| P3-7 | `_normalize_disk_task` 归一结果不落盘 | ✅ 属实 | 只改内存对象，磁盘长期存 RUNNING |

---

## 二、修改技术方案

### 方案一（对应 P0-01，最高优先级）：补回依赖 + 环境自检

**1a. 补回 `pojo/httpResponseResult.py`**

核实确认该类只在 `common/httpclient/doRequest.py` 内部构造与赋值，外部无任何读取方，字段就是四个：`status_code / headers / cookies / body`。按 `pojo/elementInfo.py` 的既有风格重建（保持框架 POJO 风格，不是凭猜——字段与赋值语句全部来自 doRequest 实际用法）：

```python
#-*- coding:utf8 -*-
class HttpResponseResult:
    def __init__(self):
        self.status_code = None
        self.headers = None
        self.cookies = None
        self.body = None
```

同时用 `git log --all -- '**/httpResponseResult.py'` 与公司仓库历史再找一次原文件；找到则用原文件替换（保留可能的额外字段）。补回后验收：`pytest -c config/pytest.ini --collect-only -q cases/` 零 error。

**1b. 平台「环境自检」**

- `web_platform/routes.py` `/api/status` 增加一项 `framework_ok`：子进程执行
  `.venv/bin/python -c "import base.app_ui.android.demoProject.app_ui_android_demoProject_client"`（10s 超时，结果按版本缓存 60s 避免每次请求都 fork）
- `app.js` 页脚状态区加第三颗灯：`框架依赖 正常/缺失`；失败时 tooltip 显示 ModuleNotFoundError 的模块名
- `设备配置` 面板的 `devState` 卡同步展示；缺失时「开始执行/执行」按钮禁用，提示"框架缺依赖 X，先解决环境"

### 方案二（对应 P1-01 / P1-02）：执行参数收敛为单一数据源

**核心思路：一处状态（localStorage 持久化）+ 处处回显，而不是四处各自一个下拉。**

1. `app_testing.js` 新增模块级 `ExecSettings`：
   - 状态：`{ conf_file, udid, owner, app_package, app_activity }`，存 `localStorage('appui_exec')`
   - `loadExecSettings()`：页面加载时拉 `/api/appui/device-status`（现成的 conf 列表+defaults 接口）做初始值与合法性校验（conf 不存在回退默认）
2. 「设备配置」页改为这套状态的**编辑器**：改动即写 localStorage + toast「已保存，将用于所有执行入口」（保留手动保存按钮也行，但状态必须落同一份）
3. 「测试套件」顶部卡改为只读回显（conf 名 + udid 尾号 + owner），点「修改」跳设备配置面板；或保留可编辑但 change 时同步写同一状态
4. `_runBody()` 改读 `ExecSettings`；`runCaseById/runSuite/runOrchCase` 执行前弹轻量确认框：**「将在 设备X（conf: kuaige）上执行，发起人 Y」**，确认才发——一次性解决"看不见跑在哪"（P1-01）与"配置不生效"（P1-02）
5. `选择用例` 页 `startRun()` 的 overrides 同样改读 `ExecSettings`（保留页面输入框作为临时覆盖，覆盖值回写状态）

**验收**：四个入口执行前都能看到同一份设备信息；设备配置页改 udid 后，在编排页执行，确认框显示的是新 udid。

### 方案三（对应 P1-03 + P1-04）：项目承载被测 App 与默认元素库

1. **数据模型**：projects 增加三个可选字段 `default_elements_file / app_package / app_activity`（`_clean_project_body` 增加校验：包名格式 `[\w.]+`、元素文件必须在元素库列表内）；「管理项目」弹窗补三个输入（下拉选元素文件、包名/Activity 文本框，可空）
2. **编排带出**：`orchProj` change 时，若用例尚未手填，则自动填充 `#orchElemFile`（项目默认元素库）；`saveOrchCase()` body 增加提交 `app_package/app_activity`（取值优先级：项目默认 > conf 覆盖 > 现有 codegen 常量兜底）
3. **codegen 去硬编码**：`compile_case()` 里 `DEFAULT_APP_PACKAGE` 降级为最后兜底，并在生成文件头注释里标注「包名来源：项目配置 / conf / 内置默认」
4. **批量归属**：「管理项目」弹窗每行加「归入用例」：弹多选列表（未分组用例），批量 PUT 各用例的 project_id
5. **执行带出**（与方案二衔接）：项目有 `app_package` 时，执行确认框回显该项目的 App

**验收**：新建项目「快歌」绑定 `kuaigeLoginElements.py` + 快歌包名 → 编排新用例选「快歌」→ 元素文件与包名自动带出；生成的 test 文件 setup_class 里是快歌包名。

### 方案四（对应 P1-05）：编排 dirty 保护

1. `selectOrchCase()` 载入后保存快照：`_orchSnapshot = JSON.stringify({steps: _orchSteps, name, desc, by, elemFile, proj})`
2. 新增 `orchDirty()`：当前表单+画布序列化后与快照比对
3. `orchSel` change 与 `selectOrchCase(0)`（新建）入口：`orchDirty()` 为真时 `confirmModal('当前用例有未保存修改', '切换将丢失这些修改，确定？', true)`，取消则把下拉值回退到原用例 id
4. 「保存用例」按钮：dirty 时加 `.attn` 样式（琥珀色描边 + 「未保存」小角标），保存成功后移除
5. `beforeunload`：dirty 时浏览器原生确认（防关页丢内容）

### 方案五（对应 P2-01/02/03/08）：状态词表与执行前置校验

1. **NOT_RUN 独立徽章**：`app.js statusBadge()` 增加 `NOT_RUN → 灰色「未执行」`；`suiteResultHtml()` 删除映射 hack；套件表「执行状态」与「最近结果」合并为一列（历史结果跳执行历史弹窗）
2. **执行按钮前置禁用**：
   - 套件表：`case_ids.length === 0` → 执行按钮 `disabled` + `title="套件内无用例"`；空套件行加浅灰样式
   - 全局：`/api/status` 轮询结果（已有 10s 轮询）写入 `window.__devOnline`；离线时四个执行入口统一渲染为禁用 + 旁注「设备离线」；在线恢复自动解禁
3. **套件项目一致性（P2-03 二选一，建议补后端）**：`_clean_suite_case_ids(case_ids, project_id=None)` 增加参数——套件指定了 project_id 时，逐个校验用例 `project_id ∈ {None, 套件 project_id}`，违规报「用例「X」属于项目 Y，与套件项目不一致」；测试补 2 条用例（混入拒绝 + 未分组用例允许）
4. **设备状态条（P2-08）**：把页脚的设备灯抽成 `<div class="envstrip">` 组件函数，AppUI 各面板顶部（编排/测试用例/套件/选择用例）注入；离线红条「设备离线，执行不可用」，在线绿条显示 udid 尾号

### 方案六（对应 P2-04/05/06/07）：信息架构修缮

1. **选择用例补搜索框**：`#panel-cases` treebar 加 `<input id="caseSearch">`，input 事件遍历 `#caseTree li[data-key]`，不命中隐藏、命中高亮；文件级节点按子节点命中情况决定显隐；顺带加「展开全部/收起全部」
2. **用例树显示中文名**：`/api/appui/cases-tree`（新端点，或扩展现有接口）返回 `node → case_name` 映射（`cases_store.list()` 里 `node` 字段反查）；`app.js` 渲染树时编排用例显示 `中文名（文件名::方法）`，原生用例保持原样
3. **报告页合表**：删「最近执行」卡；「报告列表」改名「执行记录」，列合并为 `Run ID | 时间 | 目标 | 对象 | 共/过/失 | 状态 | 报告 | 操作`，统计卡保留在顶部；空态合并为一个带引导按钮（「去选择用例开始第一次执行」）的空态
4. **默认面板**：`showRunPanel()` fallback 从 `'exec'` 改 `'projects'`（与侧边栏第一项一致）；删 `run.html:18` 的死 `class="on"`

### 方案七（对应 P3 七项）：代码层清理（半天内可全部完成）

| # | 改动 | 具体做法 |
|---|---|---|
| 1 | `_run_nodes` 删 `case=None` 形参 | `api_case_run` 调用处同步删；若后续要做"单用例执行写回用例表状态"，再加回来并真用 |
| 2 | PUT 编译失败回滚 | `api_case_detail` 先用旧值快照：`old = {k: case.get(k) for k in patch}`；编译失败 `cases_store.update(cid, old)` 后再 `_bad`；与 POST 语义对齐 |
| 3 | runner.py docstring | 头注释改为"单类任务 app_ui（接口测试已独立到 api_testing 模块）"；顺带删 `_public_task` 里 `kind` 字段或保留注明仅兼容旧前端 |
| 4 | 删 run 回收报告服务 | `runner.manager` 增加可注入回调 `on_run_deleted`；`routes.py` 初始化时注入 `lambda rid: (_report_services.pop(rid, None) or {}).get('proc') and 那个 proc.terminate()`；`clear_runs` 注入批量版；`_cleanup_report_services` 保留兜底 |
| 5 | `_clean_project_body` 删三个死字段分支 | 删 `member_count/start_date/end_date` 校验段（接口兼容：存量 YAML 里的值原样保留不展示，不迁移不报错）；顺带补一条 P3 测试 |
| 6 | `list_tasks` 增量缓存 | manager 增加 `_disk_cache = {mtime: tasks}`：以 `RUNS_DIR` 目录 mtime 为版本号，目录没变直接返回缓存；`delete_run/clear_runs/start_run` 后失效 |
| 7 | `_normalize_disk_task` 落盘 | 归一命中时写回 result.json（`task['normalized']=True` 防重复写）；写失败静默（只读场景不阻塞） |

---

## 三、建议实施顺序与规模

| 批次 | 内容 | 预估规模 | 解锁价值 |
|---|---|---|---|
| 第 1 批 | 方案一（补依赖 + 自检） | 小（1 个新文件 + 2 处小改） | **执行链路立即恢复**，环境问题显性化 |
| 第 2 批 | 方案五（词表/禁用/一致性/状态条） | 中 | 界面不再自相矛盾 |
| 第 3 批 | 方案二（执行参数收敛） | 中 | 消除"不知道跑哪台设备" |
| 第 4 批 | 方案四（dirty 保护） | 小 | 堵数据丢失 |
| 第 5 批 | 方案三（项目承载 App） | 中大 | 「项目」概念立得住 |
| 第 6 批 | 方案六（信息架构） + 方案七（P3 清理） | 中 | 日常效率与可维护性 |

说明：第 2、3 批可并行；方案三依赖方案二的状态模块（App 覆盖参数走同一通道），故排在后面。

---

## 附：核实过程中确认的两个附加事实

1. **P0-01 影响面确认**：`HttpResponseResult` 仅在 `doRequest.py` 内部使用（无外部读取方），重建风险极低；但 `doRequest` 顶层 import 也阻断所有 import 它的接口测试链路，补回后建议跑一次 `pytest --collect-only` 全量确认。
2. **报告时效**：报告基于 v6.26 走查，其中「项目管理页」截图与描述已被 v6.29 重构覆盖（现为核心用例列表 + 管理项目弹窗），但 P1-03 的本质问题（项目不承载执行要素）依然成立，已在方案三中保留处理。
