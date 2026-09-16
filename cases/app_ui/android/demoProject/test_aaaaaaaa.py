# -*- coding: utf-8 -*-
# 用例包 aaaaaaaa · 在「btnRealName」输入
# 流程：
# 1. 拉起快歌主页面
# 2. 在「btnRealName」输入
import time
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.AaaaaaaaPage import AaaaaaaaPage


@allure.parent_suite('快歌APP自动化')
@allure.suite('aaaaaaaa')
class TestAaaaaaaa:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = AaaaaaaaPage(self.appOperator)

    @allure.title('在「btnRealName」输入')
    def test_aaaaaaaa(self):
        page = self.page

        # 1. 在「btnRealName」输入
        page.input_btnRealName('11111')

    def teardown_class(self):
        self.appOperator.close_app()
