# escrcpy · 投屏控制台（独立项目）

[escrcpy](https://github.com/viarotel-org/escrcpy) 的本机部署：scrcpy 的图形化封装，
实时镜像、鼠标键盘控制、录屏、截图、多设备、键盘映射、群控、AI 助手（Copilot/MCP）。

## 当前部署

- 版本：v3.3.1（mac-x64）
- 位置：`escrcpy/Escrcpy.app`
- 入口：自动化平台首页 → 「投屏控制台 escrcpy」卡片 → 自动拉起桌面 App

## 手动操作

```bash
# 启动
open escrcpy/Escrcpy.app

# 首次启动被 macOS 拦截时，清一次下载标记
xattr -cr escrcpy/Escrcpy.app
```

## 说明

- `Escrcpy.app`（约 300MB 解压后）不入库，与 damai_u2/ 同等对待
- `launcher.py` 提供检测/启动能力，平台 `/api/escrcpy/*` 接口惰性导入本模块
- 前置依赖：adb（平台已自带）；scrcpy 内核已内置在 App 中，无需另装
