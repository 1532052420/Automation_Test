#!/usr/bin/env bash
# ============================================================
# 自动化测试启动器（macOS 双击运行）
# 用法：双击本文件（或终端执行 ./自动化执行入口.command）
# 依赖：手机/模拟器在线并授权（APP 测试）、Appium 服务
# ============================================================
cd "$(dirname "$0")" || exit 1

# 复用 run.sh 的环境变量配置（JAVA_HOME/PATH/ANDROID_HOME）
RUN_SH="$(pwd)/run.sh"
APP_DIR="cases/app_ui/android/demoProject"

menu() {
  echo ""
  echo "=================================================="
  echo "   自动化测试启动器"
  echo "=================================================="
  echo " 1) 接口自动化测试（API）"
  echo " 2) APP 自动化测试（Android）"
  echo " 3) APP 测试（指定关键字，如 -k demo_tool）"
  echo " 4) 生成测试报告"
  echo " 5) Appium 服务（启动/停止/状态）"
  echo " 6) 环境检查（设备/依赖自动补齐）"
  echo " 7) Web 执行平台（含元素定位器）  http://127.0.0.1:8080"
  echo " 8) 重启 Web 执行平台（改完平台代码后让新代码生效）"
  echo " q) 退出"
  echo "=================================================="
}

do_api() {
  echo ">>> 开始接口自动化测试..."
  "$RUN_SH" api
  echo ""
  echo ">>> 接口测试执行完毕，回车返回菜单"
  read -r _
}

do_app() {
  echo ">>> 开始 APP 自动化测试（目录：$APP_DIR）"
  echo "    执行前请确认：手机在线并已授权、Appium 已启动（菜单 5）"
  "$RUN_SH" app -d "$APP_DIR"
  echo ""
  echo ">>> APP 测试执行完毕，回车返回菜单"
  read -r _
}

do_app_kw() {
  echo ">>> 输入关键字（文件名/类名/方法名包含，直接回车 = 全部用例）："
  read -r KW
  if [ -z "$KW" ]; then
    "$RUN_SH" app -d "$APP_DIR"
  else
    "$RUN_SH" app -d "$APP_DIR" -k "$KW"
  fi
  echo ""
  echo ">>> APP 测试执行完毕，回车返回菜单"
  read -r _
}

do_report() {
  echo ">>> 选择要生成的报告："
  echo " 1) APP 测试报告"
  echo " 2) 接口测试报告"
  echo " 其他) 返回"
  read -r REP
  case "$REP" in
    1) .venv/bin/python generate_app_ui_test_report.py ;;
    2) .venv/bin/python generate_api_test_report.py ;;
    *) return ;;
  esac
  echo ""
  echo ">>> 报告生成完毕，回车返回菜单"
  read -r _
}

do_appium() {
  echo ">>> Appium 服务："
  echo " 1) 启动（端口 4726）"
  echo " 2) 停止"
  echo " 3) 状态"
  read -r AP
  case "$AP" in
    1) "$RUN_SH" start-appium ;;
    2) "$RUN_SH" stop-appium ;;
    3) "$RUN_SH" status ;;
    *) return ;;
  esac
  echo ""
  echo ">>> 回车返回菜单"
  read -r _
}

while true; do
  menu
  read -r -p "请选择: " CHOICE
  case "$CHOICE" in
    1) do_api ;;
    2) do_app ;;
    3) do_app_kw ;;
    4) do_report ;;
    5) do_appium ;;
    6) "$RUN_SH" env-check; echo ""; echo ">>> 环境检查完毕，回车返回菜单"; read -r _ ;;
    7) "$RUN_SH" platform; sleep 1 ;;
    8) "$RUN_SH" restart-platform; sleep 1 ;;
    q|Q) echo "再见"; exit 0 ;;
    *) echo "无效选择：$CHOICE" ;;
  esac
done
