# 录制调试中心（调试阶段 · 与主框架解耦）

对应平台首页第三张卡片「录制调试中心」。上游官方工具原封不动，本目录与平台侧代码
只做**启动器 / 产物落盘 / 项目配置**：

## 一、Web 录制 = Playwright 官方 codegen（microsoft/playwright）

- 平台「Web 录制」→ `playwright codegen --target python -o <产物> <入口地址>`：
  弹出真实浏览器窗口，操作实时生成 Python 代码写入产物文件
- 产物默认存 `recordings/web/*.py`（项目配置可改保存目录/入口地址/浏览器/视口）

## 二、App 录制 = Maestro Studio（mobile-dev-inc/maestro）

- 平台「App 录制」→ `maestro studio` → 浏览器打开 http://127.0.0.1:9999，
  在 Studio 界面对真机点选控件生成命令，导出 YAML 存 `recordings/app/`

## 二点五、步骤生成（写好步骤 → 生成脚本，可反复执行）

不想「操作录制」时，可直接写步骤稿（YAML），平台生成标准 Playwright 脚本：

- 步骤稿存 `recordings/web/<名字>.steps.yaml`，「生成脚本」产出同名 `.py`；
- 改步骤 = 改 .steps.yaml → 重新生成 → 调试运行（脚本永手改会被覆盖，源头是步骤稿）；
- 规范（页面「步骤生成」段有完整速查表）：

```yaml
name: 流程名            # 产物命名来源
base_url: https://...   # 可选：goto 相对地址的前缀
viewport: "1280,720"    # 可选
steps:
  - goto: /s?wd=x                              # 打开页面
  - fill: {selector: "#kw", text: "自动化"}     # 输入
  - click: "#su"                               # 点击（简写=选择器）
  - press: Enter                               # 按键
  - wait: 2                                    # 等待秒
  - wait_for: "#list"                          # 等元素出现
  - hover: ".menu"                             # 悬停
  - select: {selector: "#s", value: "M"}       # 下拉（value/label/index）
  - check: "#agree"                            # 勾选 / uncheck
  - screenshot: 结果.png                        # 整页截图（output/record_shots/）
  - slide: {selector: ".btn", track: ".track"}  # 滑块/拖拽（codegen 录不到的手势）：
                                               #   目标三选一 distance: 300 / to: "元素" / track: "轨道"，
                                               #   可加 steps: 30（分步移动）、hold: 0.3（松手前停顿秒）
  - assert_visible: "#list"                    # 断言可见
  - assert_text: {selector: "body", contains: "ok"}   # 断言文本
  - assert_title: {contains: "百度"}            # 断言标题
  # 每步可加 desc: 说明 → 生成注释
```

- 选择器即 Playwright 选择器语法：`#id`、`text=登录`、`role=button[name="提交"]`、`css=`/`xpath=`；
- 断言用 expect 自动等待，失败即 AssertionError → 调试运行自动留 trace；
- App 端不需要生成：Maestro 官方 YAML 本身就是步骤规范，写好直接调试运行。

## 三、调试运行（录制产物 → 自动带 trace 执行）

- Web：`trace_lab/debug_web.py` 包裹执行任意 codegen 产物——脚本创建的每个
  context 自动开启 tracing（截图+DOM+源码），browser.close()/脚本结束时落盘
  `output/trace_runs/<run_id>/trace.zip`，平台「打开 trace 回放」进官方 viewer
- App：`maestro test <流程.yaml>` 真机执行（需设备在线），日志实时回显

## 四、项目配置

`trace_lab/record_project.yaml`：Web 入口地址/浏览器/视口/保存目录 + App 保存目录，
页面「项目配置」卡片可编辑。

## 五、App 用例失败现场（外部观察者）

平台跑真实 App 用例时，`web_platform/app_trace_observer.py` 只读旁观（框架零改动）：
Appium 旁路采会话**截图 + UI 树**、adb 抓**全程 logcat**、运行日志「▶ 步骤N」标定步骤；
用例 PASSED 自动清现场，失败/停止自动保留；回放用逐步查看页或既有 Midscene 报告。

## 环境依赖（一次性）

```bash
python3 -m venv trace_lab/.venv
trace_lab/.venv/bin/pip install -r trace_lab/requirements-trace.txt
trace_lab/.venv/bin/playwright install chromium
# maestro 已随机安装（~/.maestro/bin/maestro）
```

## 官方 trace viewer 离线副本

`web_platform/static/trace_viewer/`（取自 playwright 1.57.0，Apache-2.0，
见目录内 LICENSE.playwright.txt）；`/trace-lab/viewer/<run_id>` 同源加载，无需外网。

## 下一步（本阶段不做）

- App：进程内埋点（appOperator 步骤层精确留证，替代外部旁观）；
- Web：平台 Web UI 用例接入 Playwright 执行内核（与 Selenium 并存），全程 tracing。

