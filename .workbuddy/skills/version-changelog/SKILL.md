---
name: version-changelog
description: 平台与元素定位器的版本号与更新日志维护规范。任何对项目产物（代码 / UI / 配置 / 文档）产生修改的任务，收尾时必须执行：按规则递增版本号（普通修改 +1、重大改造 +2），并在 web_platform/changelog.py 的 CHANGELOG 顶部追加一条精确到秒的变更记录。当用户提到「版本号」「更新日志」「changelog」「发版」「记录本次改动」，或任何改动类任务收尾时使用。
---

# 版本号与更新日志

平台（`web_platform/`）与元素定位器（`element_locator/`）**共用同一个版本号**，唯一数据源：
**`web_platform/changelog.py`**。

## 五条铁律

1. **只改一处**。版本号与日志只写在 `web_platform/changelog.py`。禁止在 `web_platform/static/app.js`、`element_locator/server.py`、`element_locator/static/index.html` 等处硬编码版本号——定位器的 `APP_VERSION` 从该文件读取后加 `v` 前缀（显示为 `v3.3`）。
2. **递增规则**：有修改 → 版本号 **+1**（3.3 → 3.4）；重大改造 / 不兼容变更 → **+2**（3.3 → 3.5）。**同一次任务只升一次**。
3. **必须记录**：在 `CHANGELOG` **顶部**（最新在前）追加一条：
   ```python
   {
       'version': '3.4',
       'time': '2026-09-16 15:49:34',   # 精确到秒；必须用 date 命令取真实时间，不要手写
       'title': '一句话概括本次改动',
       'changes': [
           '改了什么 / 修了什么——面向使用者描述效果，不要只罗列文件路径',
       ],
   }
   ```
4. **不用另写界面**：平台左下角「📋 更新日志」按钮读 `/api/changelog`（数据即本文件），自动展示版本号、更新时间（秒级）与明细；侧边栏品牌处的版本号也自动同步。
5. **强一致**：`APP_VERSION` 必须等于 `CHANGELOG[0]['version']`。

## 执行步骤（任务收尾时）

```bash
# 1. 取真实时间（禁止手写或心算时间）
date '+%Y-%m-%d %H:%M:%S'
```

2. 编辑 `web_platform/changelog.py`：`APP_VERSION` 改为新版本号，`CHANGELOG` 顶部插入新条目。
3. 自检一致性：
   ```bash
   .venv/bin/python -c "from web_platform.changelog import APP_VERSION, CHANGELOG as C; \
   print(APP_VERSION, C[0]['version']); assert APP_VERSION == C[0]['version']"
   ```
4. 让新版本号生效：`./run.sh restart-platform`（前端静态文件刷新即可，但版本号来自后端，需重启）。
5. 回读验证：`curl -s --noproxy '*' http://127.0.0.1:8080/api/changelog | .venv/bin/python -m json.tool | head -20`。

## 例外（不升版本号）

- 纯问答、纯读取、纯排查，且**未改动任何文件**。
- 只改了一次性临时脚本且不入库（但若产出了面向使用者的新能力，仍应记录）。

## 常见错误

- ❌ 改了代码忘了升版本 → 用户无法从界面判断手上是不是新版。
- ❌ 手写时间导致时间不准 → 必须用 `date` 取。
- ❌ `APP_VERSION` 与 `CHANGELOG[0]` 不一致 → 界面显示与日志对不上。
- ❌ 在 `app.js` / `server.py` 里又写一份版本号 → 下次必然两边不同步。
- ❌ 为每个小改动都写一条巨长日志 → 一次任务合并为一条，条目描述"效果"而非"改了哪个文件"。
