#!/usr/bin/env bash
# ============================================================
# 自动化测试平台（macOS 双击运行 · 默认终端启动）
# 双击 → 终端窗口启动平台并自动打开浏览器页面，
#       终端实时滚动显示平台运行日志；
#       Ctrl+C 仅退出日志查看，平台继续在后台运行；
#       彻底停止请执行 ./run.command stop-platform
# ============================================================
cd "$(dirname "$0")" || exit 1

./run.command platform

if curl -sf --max-time 2 "http://127.0.0.1:8080/api/status" >/dev/null 2>&1; then
  echo ""
  echo "=================================================="
  echo "  平台运行中 · 实时日志如下（Ctrl+C 退出本窗口，平台不停）"
  echo "  停止平台请另开终端执行: ./run.command stop-platform"
  echo "=================================================="
  tail -n 40 -f logs/platform.log
else
  echo ""
  echo "✗ 平台未能启动，请查看上方错误信息（回车关闭窗口）"
  read -r _
fi
