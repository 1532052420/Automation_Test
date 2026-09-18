# -*- coding: utf-8 -*-
# 由平台「用例编排」生成（用例 #7 登录冒烟·编排，4 步）；手改会在下次保存时被覆盖
import time
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.orch7Page import Orch7Page


@allure.parent_suite('APP UI 自动化')
@allure.suite('登录冒烟·编排')
class TestOrch7:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = Orch7Page(self.appOperator)

    @allure.title('登录冒烟·编排 · 4 步')
    def test_orch_7(self):
        page = self.page

        # 1. 点击登录
        page.click_btn_agree_privacy()

        # 2. 在et_phone输入「13800138000」
        page.input_et_phone('13800138000')

        # 3. 断言et_code出现
        page.assert_et_code()

        # 4. 等待1秒
        time.sleep(1.0)

    def teardown_class(self):
        self.appOperator.close_app()
