# -*- coding: utf-8 -*-
# 用例包 ssssssssss · 点击「ivGift」
# 流程：
# 1. 拉起快歌主页面
# 2. 点击「ivGift」
import time
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.SsssssssssPage import SsssssssssPage


@allure.parent_suite('快歌APP自动化')
@allure.suite('ssssssssss')
class TestSsssssssss:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = SsssssssssPage(self.appOperator)

    @allure.title('点击「ivGift」')
    def test_ssssssssss(self):
        page = self.page

        # 1. 点击「ivGift」
        page.click_ssssssss()
        # 点击element_10
        page.click_element_10()

    def teardown_class(self):
        self.appOperator.close_app()
