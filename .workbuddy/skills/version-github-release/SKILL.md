---
name: version-github-release
description: 版本号迭代后的 GitHub 发布规则（严格执行）。每当 version-changelog 递增版本号（web_platform/changelog.py 的 APP_VERSION）之后必须执行本 skill：版本号为双数 → 提交并推送到 GitHub；版本号为单数 → 不上传。收尾必须原样回复「已执行skill，版本号为单数，未上传」或「已执行skill，版本号为双数，已上传」。当用户提到「上传 github」「推送」「发版」「双数上传」「github 备份」「迭代版本号」，或任何递增版本号的任务收尾时使用。
agent_created: true
---

# 版本号迭代 → GitHub 发布（严格执行）

> 用户契约（2026-09-18 明确要求）：**版本号只要迭代到双数，就上传一次 GitHub；单数不上传。**
> 每次执行后必须原样回复结论句式，不得省略、不得 paraphrase。

## 触发时机

任何任务收尾执行 `version-changelog`（递增 `web_platform/changelog.py` 的 `APP_VERSION`）之后，**立即**执行本 skill。两个 skill 的顺序固定：先定版本号（+1 / +2），再按奇偶决定是否上传。

## 判定依据

唯一依据是 `web_platform/changelog.py` 里 `APP_VERSION` 的**当前值**（递增后的值），不得凭记忆或对话历史推断。

| 版本号 | 动作 |
|---|---|
| **双数**（6.28 / 6.30 / 6.32 …） | **提交 + 推送到 GitHub** |
| **单数**（6.29 / 6.31 / 6.33 …） | **不上传**（只保留本地版本号与 changelog 递增） |

读取方式（勿手抄版本号）：

```bash
cd /Users/ouyang/Desktop/AutomationTest
env -u PYTHONPATH ./.venv/bin/python -c "from web_platform.changelog import APP_VERSION; print(APP_VERSION)"
```

## 执行步骤

1. 读取 `APP_VERSION` 并判定奇偶。
2. **单数 → 直接跳到第 4 步**（不上传，工作区改动保持未提交状态即可）。
3. **双数 → 依次执行**（任一步失败立即停下并如实报告，不得谎报成功）：
   a. 提交本地改动（幂等写法）：
      ```bash
      git -C /Users/ouyang/Desktop/AutomationTest add -A
      git -C /Users/ouyang/Desktop/AutomationTest commit -m "平台 v<版本号>：<changelog 顶部标题>"   # 若报 nothing to commit 则跳过
      ```
   b. 先同步远端（**禁止 force**）：
      ```bash
      git -C /Users/ouyang/Desktop/AutomationTest fetch automation_test main
      git -C /Users/ouyang/Desktop/AutomationTest rebase automation_test/main    # 有冲突则停下报告，不自动解决
      ```
   c. 推送：
      ```bash
      git -C /Users/ouyang/Desktop/AutomationTest push automation_test HEAD:main
      ```
   d. **只读复核**（本机写操作回显不可靠，禁止凭 push 输出判断成败）：
      ```bash
      git -C /Users/ouyang/Desktop/AutomationTest rev-parse HEAD
      git -C /Users/ouyang/Desktop/AutomationTest ls-remote --heads automation_test
      # 两个哈希一致才算推送成功
      ```
4. 回复固定句式（原样，一字不改）：
   - 单数：`已执行skill，版本号为单数，未上传`
   - 双数：`已执行skill，版本号为双数，已上传`

## 硬约束

- 远端 `automation_test` = `https://github.com/1532052420/Automation_Test.git` 是默认推送目标；`origin` = `AutomationTest` 仓库，**仅当用户明确指定**时才推。
- **禁止** `--force` / `--force-with-lease` / 删除远端分支等破坏性操作。
- **禁止**推送单数版本（用户明确要求「单数不上传」）。
- 推送失败（凭据缺失 / 网络不通 / rebase 冲突）：本地提交要保留，回复里写清失败原因 + 待办，并把结论句式降级为「已执行skill，版本号为双数，**上传失败**：<原因>」——不允许假报「已上传」。
- 首次执行时的正常现象：本仓库 git 此前只提交到 v6.11，v6.12 之后的改动都在工作区，第一次双数推送会把它们一并提交，属预期行为。

## 与其它 skill 的关系

- `version-changelog`：管「版本号 + 更新日志」；本 skill 管「是否上传 GitHub」。二者串联，顺序不可颠倒。
- `ponytail`：管写码阶梯；与本 skill 无交叉。
