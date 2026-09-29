# -*- coding: utf-8 -*-
# 用例中文名：用户搜索-精确昵称
# 用例包 user_search_01 · 点击「搜索入口」
# 流程：
# 1. 拉起快歌主页面
# 2. 点击「搜索入口」
import time
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.User_search_01Page import User_search_01Page


@allure.parent_suite('快歌APP自动化')
@allure.suite('user_search_01')
class TestUserSearch01:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = User_search_01Page(self.appOperator)

    @allure.title('点击「搜索入口」')
    def test_user_search_01(self):
        """点击「搜索入口」 → 在「搜索输入框」输入「所谓伊人，在水一方」 → 点击「搜索提交」 → 断言「用户昵称」文本为「所谓伊人，在水一方」"""
        page = self.page

        # 1. 点击「搜索入口」
        page.click_btnSearch()
        # 在「搜索输入框」输入「所谓伊人，在水一方」
        page.input_search_input('所谓伊人，在水一方')
        # 点击「搜索提交」
        page.click_search_submit()
        # 断言「用户昵称」文本为「所谓伊人，在水一方」
        page.assert_user_nick_text('所谓伊人，在水一方')

    def teardown_class(self):
        self.appOperator.close_app()
