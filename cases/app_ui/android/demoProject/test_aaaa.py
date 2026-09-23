# -*- coding: utf-8 -*-
# 用例中文名：测试
# 用例包 aaaa · 点击「workspace_screen」
# 流程：
# 1. 拉起快歌主页面
# 2. 点击「workspace_screen」
import time
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.AaaaPage import AaaaPage


@allure.parent_suite('快歌APP自动化')
@allure.suite('aaaa')
class TestAaaa:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = AaaaPage(self.appOperator)

    @allure.title('点击「workspace_screen」')
    def test_aaaa(self):
        """点击「workspace_screen」 → 点击xxxxxx → cccc → cccc → 点击workspace → 点击workspace_screen → 点击workspace_screen → 点击widget_home → 点击widget_city_date → 点击element_45 → 点击left_widget_area → 点击阅读快看版 → 点击应用市场 → 点击华为商城 → 点击钱包 → 点击钱包 → 点击主题 → 点击主题 → 点击主题 → 点击主题11111 → 点击主题 → 点击主题 → 点击workspace → 点击workspace → 点击workspace → 点击workspace → 点击workspace → 点击workspace → 点击element_9 → 点击workspace_screen → 点击workspace_screen → 点击workspace_screen → 点击workspace_screen → 点击workspace_screen → 点击workspace → 点击workspace → 点击workspace → 点击workspace → 点击workspace → 点击workspace → 点击drag_layer → 点击drag_layer → 点击widget_time_hour"""
        page = self.page

        # 1. 点击「workspace_screen」
        page.click_workspace_screen()
        # 点击xxxxxx
        page.click_xxxxxx()
        # cccc
        page.click_ccccc()
        # cccc
        page.click_ccccc()
        # 点击workspace
        page.click_workspace()
        # 点击workspace_screen
        page.click_workspace_screen()
        # 点击workspace_screen
        page.click_workspace_screen()
        # 点击widget_home
        page.click_widget_home()
        # 点击widget_city_date
        page.click_widget_city_date()
        # 点击element_45
        page.click_element_45()
        # 点击left_widget_area
        page.click_left_widget_area()
        # 点击阅读快看版
        page.click_阅读快看版()
        # 点击应用市场
        page.click_应用市场()
        # 点击华为商城
        page.click_华为商城()
        # 点击钱包
        page.click_钱包()
        # 点击钱包
        page.click_钱包()
        # 点击主题
        page.click_主题()
        # 点击主题
        page.click_主题()
        # 点击主题
        page.click_主题()
        # 点击主题11111
        page.click_主题11111()
        # 点击主题
        page.click_主题()
        # 点击主题
        page.click_主题()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击element_9
        page.click_element_9()
        # 点击workspace_screen
        page.click_workspace_screen()
        # 点击workspace_screen
        page.click_workspace_screen()
        # 点击workspace_screen
        page.click_workspace_screen()
        # 点击workspace_screen
        page.click_workspace_screen()
        # 点击workspace_screen
        page.click_workspace_screen()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击workspace
        page.click_workspace()
        # 点击drag_layer
        page.click_drag_layer()
        # 点击drag_layer
        page.click_drag_layer()
        # 点击widget_time_hour
        page.click_widget_time_hour()

    def teardown_class(self):
        self.appOperator.close_app()
