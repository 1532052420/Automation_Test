# -*- coding: utf-8 -*-
# 用例中文名：热词搜索
# 用例包 search_hotword · 点击「搜索入口」
# 流程：
# 1. 拉起快歌主页面
# 2. 点击「搜索入口」
import time
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.Search_hotwordPage import Search_hotwordPage


@allure.parent_suite('快歌APP自动化')
@allure.suite('search_hotword')
class TestSearchHotword:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = Search_hotwordPage(self.appOperator)

    @allure.title('点击「搜索入口」')
    def test_search_hotword(self):
        """点击「搜索入口」 → 在「搜索输入框」输入「zhou」 → 点击「搜索提交」 → 等待「用户结果首条」出现（最长60秒） → 断言「用户结果首条」出现"""
        page = self.page

        # 1. 点击「搜索入口」
        page.click_btnSearch()
        # 2. 在「搜索输入框」输入「zhou」
        page.input_search_input('zhou')
        # 3. 点击「搜索提交」
        page.click_search_submit()
        # 4. 等待「用户结果首条」出现（最长60秒）
        page.wait_user_first(60)
        # 5. 断言「用户结果首条」出现
        page.assert_user_first()

    def teardown_class(self):
        self.appOperator.close_app()
