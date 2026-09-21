# -*- coding: utf-8 -*-
# 工具生成·手机号登录流程执行验证
# 流程：
# 0. 首次启动弹窗处理（隐私协议/系统权限，无弹窗自动跳过）
# 1. 点任意位置触发登录弹层
# 2. 断言登录弹层出现（新旧版本通用）
# 3. 点击手机号登录入口
# 4. 输入手机号
# 5. 输入验证码
# 6. 点击立即登录（未勾选协议）
# 7. 断言未勾选协议toast
# 8. 勾选我已阅读并同意
# 9. 再次点击立即登录
# 10. 断言登录成功（登录成功 toast 为主要依据；成败截图入 allure，截图即存证）
import time
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.demoToolLoginPage import DemoToolLoginPage


class TestDemoToolLogin:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = DemoToolLoginPage(self.appOperator)

    def test_phone_login_flow(self):
        page = self.page

        # 0. 首次启动弹窗处理（隐私协议/系统权限，无弹窗自动跳过）
        page.deal_first_launch_dialogs()

        # 1. 点任意位置触发登录弹层（真机 720x1536 坐标；模拟器 1080x2280 为 540,1500）
        page.tap_xy(360, 768)

        # 2. 断言登录弹层出现（新旧版本通用：旧版先弹'请先登录'toast，新版直接弹层）
        page.assert_login_layer()

        # 3. 点击手机号登录入口
        page.click_btn_phone_login()

        # 4. 输入手机号
        page.input_et_phone('10000000000')

        # 5. 输入验证码
        page.input_et_code('8888')

        # 5.5 收起键盘/输入法面板（vivo 键盘布局选择器会遮挡登录按钮）
        page.dismiss_ime_panel()

        # 6. 点击立即登录（未勾选协议）
        page.click_btn_login()

        # 7. 断言未勾选协议toast
        page.assert_toast('请先勾选下方协议')

        # 8. 勾选我已阅读并同意
        page.click_agree_protocol()

        # 9. 再次点击立即登录
        page.click_btn_login()

        # 10. 断言登录成功（登录成功 toast 为主要依据；成败截图入 allure，截图即存证）
        page.assert_login_success()
        # 星光值标签
        page.click_btnStarlightValue()
        # 点击sss
        page.click_sss()
        # 点击btnStarlightValue
        page.click_btnStarlightValue()

    def teardown_class(self):
        self.appOperator.close_app()
