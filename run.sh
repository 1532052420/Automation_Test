#!/usr/bin/env bash
# ============================================================
# AutomationTest 统一执行入口
# 自动配置 JAVA_HOME(JDK8) / PATH(venv+brew mvn+cmdline-tools) / ANDROID_HOME
# 用法:
#   ./run.sh api            启动 API 接口自动化测试
#   ./run.sh app            启动 APP(Android) 自动化测试（执行前自动检查设备依赖）
#   ./run.sh start-appium   启动 Appium 3.7 服务(端口4726,后台)
#   ./run.sh stop-appium    停止 Appium 服务
#   ./run.sh status         Appium 服务状态
#   ./run.sh env-check      检查设备自动化依赖（先查再装，缺才装）
#   ./run.sh platform       启动 Web 执行平台(端口8080,后台)并打开页面
#   ./run.sh stop-platform  停止 Web 执行平台
#   ./run.sh restart-platform  重启 Web 执行平台（改完平台代码后让新代码生效）
#   ./run.sh report api     生成 API 测试报告
#   ./run.sh report app     生成 APP 测试报告
# ============================================================
set -e
cd "$(dirname "$0")"

# ---------- 环境变量 ----------
export JAVA_HOME="$(/usr/libexec/java_home -v 1.8 2>/dev/null || echo "$HOME/Library/Java/JavaVirtualMachines/jdk8u504-b01/Contents/Home")"
export PATH="$PWD/.venv/bin:/Users/ouyang/homebrew/bin:$HOME/Library/Android/sdk/cmdline-tools/latest/bin:$HOME/Library/Android/sdk/platform-tools:$PATH"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"

APP_DEVICES=config/demoProject/app_ui_android_devices_info_demoProject.conf
APPIUM_PORT=4726
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
appium_up()   { curl -sf --max-time 2 "http://127.0.0.1:${APPIUM_PORT}/wd/hub/status" 2>/dev/null | grep -q '"ready"'; }

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
  api)
    shift
    .venv/bin/python run_api_test.py "$@"
    ;;
  app)
    # 规矩：执行前先查设备依赖，缺才装，有则跳过
    ./ensure_env.sh
    shift
    .venv/bin/python run_app_ui_test.py -tt phone -dif "$APP_DEVICES" "$@"
    ;;
  env-check)
    ./ensure_env.sh
    ;;
  start-appium)
    # Appium 3.7.0 独立安装于 ~/appium2，driver(uiautomator2) 在 ~/.appium；需 ANDROID_HOME(本脚本头部已导出)
    if appium_up; then
      echo "Appium 已在运行(端口${APPIUM_PORT})"
    else
      if port_holders "$APPIUM_PORT"; then
        echo "✗ 端口 ${APPIUM_PORT} 被以下进程占用，但它不是可用的 Appium："
        port_holders "$APPIUM_PORT"
        echo "  先清理：./run.sh stop-appium"
        exit 1
      fi
      mkdir -p logs
      # Appium 3.7.0/base-driver 10.8.0 上游缺陷：proxyRouteIsAvoided 收到完整 URL 导致
      # driver 的 NO_PROXY 白名单全部失配，所有命令被误代理给设备端 server 而 404。
      # 幂等补丁，详见 deploy/patch_appium_base_driver.py；已打则跳过。
      .venv/bin/python deploy/patch_appium_base_driver.py || true
      nohup "$HOME/appium2/node_modules/.bin/appium" --port "$APPIUM_PORT" --address 127.0.0.1 --base-path /wd/hub --log-level info > logs/appium.log 2>&1 &
      if wait_for appium_up 30; then
        echo "Appium(3.7.0) 已启动(端口${APPIUM_PORT}), 日志: logs/appium.log"
      else
        report_start_failure logs/appium.log "$APPIUM_PORT"
        exit 1
      fi
    fi
    ;;
  stop-appium)
    # 按端口精确清理：不管是谁启动的、cmdline 长什么样，只要占着 4726 就能清掉
    if [ -z "$(port_pids "$APPIUM_PORT")" ]; then
      echo "Appium 未在运行(端口 ${APPIUM_PORT} 无监听)"
    elif free_port "$APPIUM_PORT"; then
      echo "Appium 已停止(端口 ${APPIUM_PORT} 已释放)"
    else
      echo "✗ 端口 ${APPIUM_PORT} 仍被占用："
      port_holders "$APPIUM_PORT"
      exit 1
    fi
    ;;
  platform)
    PLATFORM_URL="http://127.0.0.1:${PLATFORM_PORT}/"
    if platform_up; then
      echo "Web 执行平台已在运行: ${PLATFORM_URL}"
      echo "  若刚改过平台代码，执行 ./run.sh restart-platform 让新代码生效"
    else
      if [ -n "$(port_pids "$PLATFORM_PORT")" ]; then
        echo "✗ 端口 ${PLATFORM_PORT} 已被以下进程占用，但它不是本平台(/api/status 无响应)："
        port_holders "$PLATFORM_PORT"
        echo "  解决办法（二选一）："
        echo "    ./run.sh stop-platform                       # 结束占用者后再启动"
        echo "    WEB_PLATFORM_PORT=8081 ./run.sh platform     # 换端口启动"
        exit 1
      fi
      mkdir -p logs
      # stdin 显式关到 /dev/null：nohup 只在 stdin 是终端时才兜底重定向，
      # 从脚本/服务管理器启动时它会继承一个可能已失效的 fd，导致平台派生的
      # pytest 子进程 capture 崩溃（任务秒失败且无日志）
      nohup .venv/bin/python web_platform/app.py > logs/platform.log 2>&1 < /dev/null &
      if wait_for platform_up 20; then
        echo "Web 执行平台已启动: ${PLATFORM_URL}  日志: logs/platform.log"
      else
        report_start_failure logs/platform.log "$PLATFORM_PORT"
        exit 1
      fi
    fi
    open "$PLATFORM_URL"
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
    if appium_up; then
      curl -s --max-time 3 "http://127.0.0.1:${APPIUM_PORT}/wd/hub/status"; echo
    else
      echo "Appium 未运行, 先执行: ./run.sh start-appium"
    fi
    if platform_up; then
      echo "Web 执行平台在运行: http://127.0.0.1:${PLATFORM_PORT}/"
    else
      echo "Web 执行平台未运行, 先执行: ./run.sh platform"
      if [ -n "$(port_pids "$PLATFORM_PORT")" ]; then
        echo "  但端口 ${PLATFORM_PORT} 已被占用："
        port_holders "$PLATFORM_PORT"
      fi
    fi
    ;;
  report)
    case "$2" in
      api)  shift 2; .venv/bin/python generate_api_test_report.py "$@" ;;
      app)  shift 2; .venv/bin/python generate_app_ui_test_report.py "$@" ;;
      *)    echo "用法: ./run.sh report api|app" ;;
    esac
    ;;
  *)
    echo "用法: ./run.sh {api|app|platform|restart-platform|start-appium|stop-appium|stop-platform|status|env-check|report}"
    echo "  例: ./run.sh api                     # 跑 API 用例"
    echo "      ./run.sh app -d cases/app_ui/android/demoProject/   # 跑指定 APP 用例"
    echo "      ./run.sh platform                # 启动 Web 执行平台"
    echo "      ./run.sh restart-platform        # 改完平台代码后重启"
    ;;
esac
