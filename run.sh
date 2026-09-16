#!/usr/bin/env bash
# ============================================================
# AutomationTest 统一执行入口
# 自动配置 JAVA_HOME(JDK8) / PATH(venv+brew mvn+cmdline-tools) / ANDROID_HOME
# 用法:
#   ./run.sh api           启动 API 接口自动化测试
#   ./run.sh app           启动 APP(Android) 自动化测试（执行前自动检查设备依赖）
#   ./run.sh start-appium  启动 Appium 3.7 服务(端口4726,后台)
#   ./run.sh stop-appium   停止 Appium 服务
#   ./run.sh status        Appium 服务状态
#   ./run.sh env-check     检查设备自动化依赖（先查再装，缺才装）
#   ./run.sh platform      启动 Web 执行平台(端口8080,后台)并打开页面
#   ./run.sh stop-platform 停止 Web 执行平台
#   ./run.sh report api    生成 API 测试报告
#   ./run.sh report app    生成 APP 测试报告
# ============================================================
set -e
cd "$(dirname "$0")"

# ---------- 环境变量 ----------
export JAVA_HOME="$(/usr/libexec/java_home -v 1.8 2>/dev/null || echo "$HOME/Library/Java/JavaVirtualMachines/jdk8u504-b01/Contents/Home")"
export PATH="$PWD/.venv/bin:/Users/ouyang/homebrew/bin:$HOME/Library/Android/sdk/cmdline-tools/latest/bin:$HOME/Library/Android/sdk/platform-tools:$PATH"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"

APP_DEVICES=config/demoProject/app_ui_android_devices_info_demoProject.conf

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
    if curl -s --max-time 2 http://127.0.0.1:4726/wd/hub/status >/dev/null 2>&1; then
      echo "Appium 已在运行(端口4726)"
    else
      mkdir -p logs
      nohup "$HOME/appium2/node_modules/.bin/appium" --port 4726 --address 127.0.0.1 --base-path /wd/hub --log-level info > logs/appium.log 2>&1 &
      sleep 5
      echo "Appium(3.7.0) 已启动(端口4726), 日志: logs/appium.log"
    fi
    ;;
  stop-appium)
    pkill -f "appium --port 4726" 2>/dev/null && echo "Appium 已停止" || echo "Appium 未在运行"
    ;;
  platform)
    if curl -s --max-time 2 http://127.0.0.1:8080/api/status >/dev/null 2>&1; then
      echo "Web 执行平台已在运行: http://127.0.0.1:8080/"
    else
      mkdir -p logs
      nohup .venv/bin/python web_platform/app.py > logs/platform.log 2>&1 &
      sleep 3
      echo "Web 执行平台已启动: http://127.0.0.1:8080/  日志: logs/platform.log"
    fi
    open http://127.0.0.1:8080/
    ;;
  stop-platform)
    pkill -f "web_platform/app.py" 2>/dev/null && echo "Web 执行平台已停止" || echo "Web 执行平台未在运行"
    ;;
  status)
    curl -s --max-time 3 http://127.0.0.1:4726/wd/hub/status || echo "Appium 未运行, 先执行: ./run.sh start-appium"
    ;;
  report)
    case "$2" in
      api)  shift 2; .venv/bin/python generate_api_test_report.py "$@" ;;
      app)  shift 2; .venv/bin/python generate_app_ui_test_report.py "$@" ;;
      *)    echo "用法: ./run.sh report api|app" ;;
    esac
    ;;
  *)
    echo "用法: ./run.sh {api|app|platform|start-appium|stop-appium|status|env-check|report}"
    echo "  例: ./run.sh api                     # 跑 API 用例"
    echo "      ./run.sh app -d cases/app_ui/android/demoProject/   # 跑指定 APP 用例"
    echo "      ./run.sh platform                # 启动 Web 执行平台"
    ;;
esac