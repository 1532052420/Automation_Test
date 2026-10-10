# AI 用例生成模块 · 实施进度（供后续会话接续）

- 方案：《AI 用例生成模块技术方案（Maestro MCP + 现有 App 自动化平台）》V1.1
  （用户下载目录：`~/Downloads/AI用例生成模块技术方案_Maestro_MCP (1).md`）
- 本文档 = 跨会话检查点。每次实施会话结束前必须更新本文件。
- 最近更新：2026-10-10 09:34（P2.5 配置中心完成：菜单栏 + 模型/提示词/Skill 配置，6.14.120）

## ✅ 已完成

### P2.5 配置中心（✅ 2026-10-10，6.14.120）
- /ai-case 左侧菜单栏：生成工作台 / 配置项（复用平台 .runlayout .subnav 模式）
- 项目与设备：AI 项目绑定包名（ai_case_projects.yaml）+ 默认项目/默认设备；任务创建自动带出包名与设备，工作台不再出现包名/设备字段
- 模型配置面板：启用开关 / Base URL / API Key（服务端 YAML 保存、回显脱敏、留空不改、`__CLEAR__` 清除）/ 模型名 / 超时 / 测试连接；适配层支持 GLM/OpenAI 风格 chat completions（取 choices[0].message.content，容忍 ``` 围栏），失败自动回落规则解析
- 提示词配置面板：系统提示词 + 用户模板（{requirement}/{entry_mode}）可编辑 / 恢复默认；默认源 `web_platform/ai_case_prompts.py`
- Skill 配置面板：解析技能（模型优先 / 仅规则 force_rule）、真机探索开关与上限（与旧 settings 接口同源）、元素库检索 / 采集联动 / 试运行开关（P3/P4 生效位）；高风险策略接口层锁定 manual_confirm（方案 8.6）
- 新 API：model-config(GET/PUT) / model/test / prompts(GET/PUT/reset) / skills(GET/PUT) / ai-projects(CRUD)
- 测试：套件扩到 47 项全过（新增配置中心 12 项）；Playwright 8 项（菜单/四卡/配置驱动建任务/窄屏）全过
- 踩坑记录：前端对 PUT 路由误用 POST 全部 405（已加 putJson）；测试 fake 形参 `json` 遮蔽 json 模块（用 `_json` 别名）；**平台通栏布局样式按 `body[data-page]` scoped**（style.css 只对 run/api-test 声明了 `main{max-width:none}`），新菜单页必须在自己的样式里补同款声明 + 用 `.submain`/`.panel[hidden]` 平台结构，否则侧栏会被 1180px 居中限宽顶到页面中间；带 display 的类会盖过 UA `[hidden]`，需作者规则兜底

### 前置完成项（详见 git 历史 6.14.116~119 与下文）
- P0 全部（Maestro 2.10.0 / Java 17 / ai_case_service 独立 venv / MCP 探针：握手、工具清单、设备枚举）
- P1 首页卡片 + 需求解析 + 状态机 + SSE；P2 设备观察（Maestro 客户端 / 独占锁 / 截图层级 / 证据）
- 验收测试 45 项 + 报告 docs/ai_case_test_report.md（修复 5 缺陷，含严重级 send_file 500）

## ⏭️ 下一步（按优先级）

1. **P2 闭环（需设备 + 需模型）**：设备重插后在观察区验证截图/层级/按键（首次调用手机需确认 Maestro 驱动授权）；配置面板填入真实 GLM 服务 → 验证模型解析质量（规则兜底保留）
2. **P2 探索循环本体**：LangGraph worker（ai_case_service/.venv，3.14）编排「观察→决策→执行→复查」，消费 skills.explore_* 与设备锁；候选路径 / 人工确认事件走既有 SSE
3. **P3 case_spec + 元素映射**：Pydantic 模型、Platform MCP 只读工具（消费 skills.element_search_enabled）、跳转元素定位器采集
4. **P4 试运行 + ZIP**：编译现有 pytest 三件套、复用 runner、build_case_zip 契约入库

## ⚠️ 接续注意事项

- 平台 venv 是 **Python 3.8**：web_platform/ 内新代码必须 3.8 兼容；AI worker 用 ai_case_service/.venv（3.14）
- 前端模式：图标统一 app.js ICONS 字典（多行拼接条目先读完整再改）；页面样式用模板 <style> 的 .aic- 前缀；**对 PUT 路由必须用 ai_case.js 里的 putJson**
- git 提交纪律：禁止 add -A；damai 相关（damai_u2/、app.py /grab 挂载、index.html 抢票卡、app.js ticket 图标、style.css icon-red、changelog 6.14.117 补行）不入库——共享文件提交用「git show HEAD:file → 重放本次改动 → hash-object + update-index」手术（6.14.118/120 两次实践）
- 平台重启：kill $(lsof -tiTCP:8080 -sTCP:LISTEN) 后 nohup ./.venv/bin/python web_platform/app.py &（无 run.sh）；改模板/静态资源必须重启
- config/ai_case/ 是运行时数据（任务/锁/证据/设置/**模型密钥**），不提交
