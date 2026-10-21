# Trace 失败诊断（调试阶段 · 与主框架解耦）

对应平台首页第三张卡片「Trace 失败诊断」，两条能力线：

## 一、App 用例失败现场（外部观察者 · 先做）

平台跑真实 App 用例时，`web_platform/app_trace_observer.py` 在旁边**只读旁观**，框架
（appOperator/runner/conftest）零改动：

- 发现 app_ui 任务 RUNNING → 经 Appium HTTP 旁路抓会话**截图 + UI 树**（page_source），
  经 adb 抓**全程 logcat**；顺读 run 日志的「▶ 步骤N / └ ✔✖」行做**步骤标定**；
- 产物：`output/runs/<run_id>/trace/`（caps/ 连续采证 + steps.jsonl + caps.jsonl + logcat.log + meta.json）；
- 用例 PASSED → 现场自动删除；失败/停止/异常 → 自动保留；
- 查看：Trace 诊断页「App 用例失败现场」→ 步骤回放（逐步截图 + UI 树 + logcat 切片），
  或「在线回放报告」（复用既有 Midscene 风格报告）。

「接入框架」（进程内每步精确埋点）为调试通过后的下一阶段，届时本观察者可整体下线。

## 二、网页调试录制（Playwright Trace 回放）

- **独立环境**：playwright 装在本目录 `.venv`，平台主环境（Python 3.8 + flask）零依赖
- **录制**：`web_platform/trace_lab.py` 蓝图拉起子进程
  `trace_lab/.venv/bin/python trace_lab/record.py <url> <out.zip>`
- **产物**：`output/trace_runs/<run_id>/`（trace.zip + trace.png 整页截图 + run.log）
- **回放**：Playwright 官方 trace viewer 离线副本（`web_platform/static/trace_viewer/`，
  取自 venv 内 playwright 1.57.0，Apache-2.0，见目录内 LICENSE.playwright.txt），
  平台路由 `/trace-lab/viewer/<run_id>` 同源加载 trace.zip，无需外网

## 网页录制调试直跑（不经平台）

```bash
trace_lab/.venv/bin/python trace_lab/record.py https://www.baidu.com output/trace_runs/debug/trace.zip --headed
trace_lab/.venv/bin/python -m playwright show-trace output/trace_runs/debug/trace.zip
```

## 网页录制环境安装（一次性）

```bash
python3 -m venv trace_lab/.venv
trace_lab/.venv/bin/pip install -r trace_lab/requirements-trace.txt
trace_lab/.venv/bin/playwright install chromium
```
环境未就绪时，平台「Trace 诊断」页会显示上述命令。

## 下一步（本阶段不做）

- App：进程内埋点（appOperator 步骤层精确留证，替代外部旁观），失败用例 trace 与用例报告打通；
- Web：平台 Web UI 用例接入 Playwright 执行内核（与 Selenium 并存），全程 tracing。

