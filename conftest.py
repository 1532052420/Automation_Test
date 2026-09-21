# -*- coding: utf-8 -*-
"""仓库根 conftest · 轮末后置清理（平台「设备配置 → 后置清理」开启时生效）。

设计（与平台 v6.54 的清理语义对齐）：
- 前置清理：Client 构造时按 AT_SETUP_RESET 清一次（Client 单例 = 仅首条用例前）；
- 用例之间：恒为冷启动——每条用例 teardown_class close_app（停进程保留数据），
  下一条 setup_class start_activity 重新拉起、落在首页，无需每条用例写登录步骤；
- 后置清理：本钩子在 pytest 会话结束（全部用例跑完，含失败/报错）后执行一次，
  按 AT_TEARDOWN_RESET 清 App 数据——比"末条用例的 teardown 里清"更可靠：
  不依赖用例文件自己写对，也覆盖整轮被跳过/中断的场景。
"""


def pytest_sessionfinish(session, exitstatus):
    import os
    if os.environ.get('AT_TEARDOWN_RESET') != '1':
        return
    try:
        from base.app_ui.android.demoProject.app_ui_android_demoProject_client \
            import APP_UI_Android_demoProject_Client
        inst = APP_UI_Android_demoProject_Client.instance()
        if inst and getattr(inst, 'appOperator', None):
            print('[后置清理] 清 App 数据（本轮全部用例已结束）...')
            inst.appOperator.reset_app()
        else:
            print('[后置清理] 本轮未构造 App 客户端（无设备用例执行），跳过')
    except Exception as e:
        print('[后置清理] 失败: %s' % e)
