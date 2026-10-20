#!/usr/bin/env bash
# ============================================================
# 自动化测试平台 · 启动入口（只保留 Web 平台相关命令）
# 用法:
#   ./run.command platform          启动 Web 执行平台(端口8080,后台)并打开页面
#   ./run.command stop-platform     停止 Web 执行平台
#   ./run.command restart-platform  重启 Web 执行平台（改完平台代码后让新代码生效）
# ============================================================
set -e
cd "$(dirname "$0")"

# ---------- 环境变量 ----------
export JAVA_HOME="$(/usr/libexec/java_home -v 1.8 2>/dev/null || echo "$HOME/Library/Java/JavaVirtualMachines/jdk8u504-b01/Contents/Home")"
export PATH="$PWD/.venv/bin:/Users/ouyang/homebrew/bin:$HOME/Library/Android/sdk/cmdline-tools/latest/bin:$HOME/Library/Android/sdk/platform-tools:$PATH"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
# 本机平台及其全部子进程（pytest/Appium 探测）不走 HTTP 代理：
# 平台若从带代理的环境启动（AI 会话沙箱、代理终端），继承的 HTTP_PROXY 会让
# Appium 建会话请求被转发给代理——代理一死，执行用例 setup 即 Connection refused。
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY FTP_PROXY http_proxy https_proxy all_proxy ftp_proxy
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
# 同理剥离 AI 会话沙箱注入的 shim（PYTHONPATH→Python、NODE_OPTIONS/NODE_PATH→Node/Appium），
# 否则 Appium 建会话请求解析即崩、平台 Python 文件操作被劫持
unset PYTHONPATH NODE_OPTIONS NODE_PATH

PLATFORM_PORT="${WEB_PLATFORM_PORT:-8080}"

# ---------- 端口治理：诊断 + 确定性清理 + 启动验证 ----------
# 为什么需要：端口被占用时，旧实现只 sleep 3 就宣告"已启动"，
# 实际 Flask 绑定失败已退出，用户看到的是打不开的白页且无从排查。

port_pids() { lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null || true; }

# 打印占用者（PID + 命令行）；无占用返回 1
port_holders() {
  local pids p out=0
  pids="$(port_pids "$1")"
  [ -z "$pids" ] && return 1
  for p in $pids; do
    echo "    pid=$p  $(ps -o command= -p "$p" 2>/dev/null | cut -c1-120)"
    out=1
  done
  [ "$out" = 1 ]
}

# 优雅终止占用端口的进程，必要时强杀；返回 0 表示端口已释放
free_port() {
  local pids left
  pids="$(port_pids "$1")"
  [ -z "$pids" ] && return 0
  echo "    结束占用进程：$pids"
  kill $pids 2>/dev/null || true
  sleep 1
  left="$(port_pids "$1")"
  if [ -n "$left" ]; then
    kill -9 $left 2>/dev/null || true
    sleep 1
  fi
  [ -z "$(port_pids "$1")" ]
}

# 「在线」判定必须校验服务身份，不能只看端口有 HTTP 响应：
# curl -s 对 404 也返回成功，曾经导致任意服务占住 8080 就被误判成"平台已在运行"。
platform_up() { curl -sf --max-time 2 "http://127.0.0.1:${PLATFORM_PORT}/api/status" 2>/dev/null | grep -q 'automation-test-platform'; }

# 轮询等待判定函数返回真（不再用固定 sleep 猜）
wait_for() {
  local fn="$1" secs="${2:-20}" end
  end=$(( $(date +%s) + secs ))
  while [ "$(date +%s)" -lt "$end" ]; do
    "$fn" && return 0
    sleep 0.5
  done
  return 1
}

# 启动失败时把日志尾巴与占用者一并抛出来，杜绝"看起来成功了"
report_start_failure() {
  local log="$1" port="$2"
  echo "✗ 启动失败：端口 $port 上的服务未就绪"
  if [ -f "$log" ]; then
    echo "  --- $log 末尾 ---"
    tail -15 "$log" | sed 's/^/    /'
  fi
  if [ -n "$(port_pids "$port")" ]; then
    echo "  --- 当前端口占用者 ---"
    port_holders "$port"
  fi
}

case "$1" in
  platform)
    PLATFORM_URL="http://127.0.0.1:${PLATFORM_PORT}/"
    if platform_up; then
      echo "Web 执行平台已在运行: ${PLATFORM_URL}"
      echo "  若刚改过平台代码，执行 ./run.command restart-platform 让新代码生效"
    else
      if [ -n "$(port_pids "$PLATFORM_PORT")" ]; then
        echo "✗ 端口 ${PLATFORM_PORT} 已被以下进程占用，但它不是本平台(/api/status 无响应)："
        port_holders "$PLATFORM_PORT"
        echo "  解决办法（二选一）："
        echo "    ./run.command stop-platform                       # 结束占用者后再启动"
        echo "    WEB_PLATFORM_PORT=8081 ./run.command platform     # 换端口启动"
        exit 1
      fi
      mkdir -p logs
      # 多实例日志分文件：默认 8080 用 platform.log，其他端口（如 8081 测试实例）用 platform_<端口>.log，避免互相覆盖
      PLATFORM_LOG=logs/platform.log
      [ "$PLATFORM_PORT" != 8080 ] && PLATFORM_LOG="logs/platform_${PLATFORM_PORT}.log"
      # stdin 显式关到 /dev/null：nohup 只在 stdin 是终端时才兜底重定向，
      # 从脚本/服务管理器启动时它会继承一个可能已失效的 fd，导致平台派生的
      # pytest 子进程 capture 崩溃（任务秒失败且无日志）
      nohup .venv/bin/python web_platform/app.py > "$PLATFORM_LOG" 2>&1 < /dev/null &
      if wait_for platform_up 20; then
        echo "Web 执行平台已启动: ${PLATFORM_URL}  日志: ${PLATFORM_LOG}"
      else
        report_start_failure "$PLATFORM_LOG" "$PLATFORM_PORT"
        exit 1
      fi
    fi
    # 强刷式打开：URL 带秒级时间戳 = 每次唯一 → 浏览器必然真实导航（不会聚焦旧标签页
    # 而不重载），页面与静态资源全量拉新（平台全局 no-store，无缓存可命中）。
    # 「清缓存」由服务端 no-store 天然保证（浏览器对本平台恒不缓存，脚本无法也无须触碰）。
    open "${PLATFORM_URL}?_fresh=$(date +%s)"
    ;;
  stop-platform)
    if [ -z "$(port_pids "$PLATFORM_PORT")" ]; then
      echo "Web 执行平台未在运行(端口 ${PLATFORM_PORT} 无监听)"
    elif free_port "$PLATFORM_PORT"; then
      echo "Web 执行平台已停止(端口 ${PLATFORM_PORT} 已释放)"
    else
      echo "✗ 端口 ${PLATFORM_PORT} 仍被占用："
      port_holders "$PLATFORM_PORT"
      exit 1
    fi
    ;;
  restart-platform)
    "$0" stop-platform
    "$0" platform
    ;;
  status)
    if platform_up; then
      echo "Web 执行平台在运行: http://127.0.0.1:${PLATFORM_PORT}/"
    else
      echo "Web 执行平台未运行, 先执行: ./run.command platform"
      if [ -n "$(port_pids "$PLATFORM_PORT")" ]; then
        echo "  但端口 ${PLATFORM_PORT} 已被占用："
        port_holders "$PLATFORM_PORT"
      fi
    fi
    ;;
  *)
    # 双击 .command 文件 = 无参数运行；默认直接启动平台，别只打印用法让窗口一闪而过
    echo "未指定命令，默认启动 Web 执行平台（双击启动入口）"
    echo "用法: ./run.command {platform|restart-platform|stop-platform|status}"
    echo "  ./run.command platform          # 启动 Web 执行平台并打开页面"
    echo "  ./run.command restart-platform  # 改完平台代码后重启"
    echo ""
    "$0" platform
    ;;
esac
