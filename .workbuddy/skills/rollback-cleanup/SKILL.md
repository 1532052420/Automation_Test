# 回滚后残留清查（rollback-cleanup）

代码 `git reset --hard` 回滚到旧版本后，跟踪文件会变干净，但**未跟踪垃圾与缓存不会跟着回滚**。本 skill 是本项目实测过的清查清单。

## 清查清单（按顺序）

1. **确认版本落点**：`grep APP_VERSION web_platform/changelog.py` + `git log --oneline -3`，确认 HEAD 提交与目标版本一致、`git status` 无已跟踪文件改动（有则回滚不彻底）。
2. **清缓存**（可再生，直接删）：
   - `find . -name "__pycache__" -type d` 排除 `.venv/`、`ponytail-main/`、`escrcpy/`、`.workbuddy/`、`.git/` 后删除
   - `.pytest_cache` / `.ruff_cache` / `.mypy_cache`
   - **注意**：`find -exec rm -rf {} +` 在代理沙箱可能被 SIGTERM（exit 137）中途夭折，必须删后用只读 find 复数复核；删不干净就改用**显式路径分批 rm**。
3. **查垃圾文件**——两种命名都要查，缺一不可：
   - `find . -name "*.bak"`（手工备份）
   - `find . -name "*_backup.py"`（管理后台上传自动备份，格式 `{stem}_{YYYYmmdd_HHMMSS}_backup.py`）⚠️ 只查 `*.bak` 会漏掉这类
   - `find . -name "*.uploading"`（两阶段用例包入库中断残留，正常流程会自清，中断则留下）
   - 位置重点：`cases/`、`page_objects/`、`element_locator/`、`web_platform/`
4. **区分已跟踪/未跟踪**：`git ls-files --error-unmatch <file>` 或看 `git status` 中是 `??` 还是 ` D`。
   - 未跟踪 → 直接 rm。
   - **已提交进仓库的备份**（如 SongwritingPage_20260923_135934_backup.py）→ `git rm --cached` + `rm`，留 staged D 随下次发版 commit 出库。
5. **孤儿页面判定**：页面文件 import 的 elements 文件是否存在（`ls page_objects/app_ui/android/demoProject/elements/`）、是否被任何用例引用（`grep -rn <类名> cases/ page_objects/ --include="*.py"`）。import 不存在的元素文件 = 必炸的死文件。
6. **逐字节相同验证**：`diff <backup> <正式文件>` 无输出即相同（macOS 文件系统大小写不敏感，`aaaaPage.py` 与 `AaaaPage.py` 是同一文件）。
7. **stash 清点**：`git stash list`。老分支的保底 stash 需用户确认后 `git stash drop`，不可擅自删。
8. **删除后必须只读复核**：本环境命令回显不可靠（双执行 + SIGTERM），用 `git status --short` + `ls` 确认终态。

## 不该动的

- `perf_test/.venv/`、`ponytail-main/`、`escrcpy/`、`.workbuddy/` 内的缓存
- 用户自己的未跟踪产物（design/docs html、tools/solopi、config 新文件等）——只报告，不删
- 沙箱内删除频繁被杀时，改用提权执行（escalation-approved）+ 显式路径

## 删除纪律

- 先列清单（含每个文件的判定依据）→ 用户确认 → 分批删 → 只读复核。
- 误删已跟踪文件用 `git restore <file>` 秒恢复；发现工作区出现**非本会话造成的 D 行**时先 restore 再查因。
