# -*- coding: utf-8 -*-
# 用例包 home_check · 主页与写歌入口检查
# 流程：
# 1. 拉起快歌主页面
# 2. 断言主页加载完成（底部首页 tab 可见）
# 3. 点击底部【写歌】按钮
# 4. 断言进入写歌页面（一键写歌按钮可见）
# 5. 返回键回主页，断言首页 tab 仍可见
import time
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.homeCheckPage import HomeCheckPage


@allure.parent_suite('快歌APP自动化')
@allure.suite('主页检查')
class TestHomeCheck:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = HomeCheckPage(self.appOperator)

    @allure.title('主页·底部tab与写歌入口检查')
    def test_check_main_tabs_and_write_entry(self):
        page = self.page

        # 1. 断言主页加载完成
        page.assert_tab_home()

        # 2. 点击底部【写歌】按钮
        page.click_tab_write_song()

        # 3. 断言进入写歌页面
        page.assert_btn_one_key_write()

        # 4. 返回键回主页
        page.back_to_main()
        time.sleep(2)

        # 5. 断言返回主页
        page.assert_back_to_main()

    def teardown_class(self):
        self.appOperator.close_app()
