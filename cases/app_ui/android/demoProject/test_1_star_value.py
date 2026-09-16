# -*- coding: utf-8 -*-
# 点击返回箭头回跳上一级页面
# 流程：
# 1. 回到主页面（统一用例起点）
# 2. 点击底部「我的」进入个人主页
# 3. 从个人主页点击星光值标签进入星光值详情页
# 4. 断言已进入星光值详情页
# 5. 点击左上角返回箭头
# 6. 断言关闭详情页回跳上一级页面（个人主页）
import time
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.starValuePage import StarValuePage


class Test1StarValue:

    def setup_class(self):
        # is_need_kill_app=False：绕开 demo 客户端硬编码启动，显式启动被测 App
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = StarValuePage(self.appOperator)

    def test_back_to_previous_page(self):
        page = self.page

        # 1. 回到主页面（统一用例起点）
        page.to_main_page()

        # 2. 点击底部「我的」进入个人主页
        page.click_tab_mine()

        # 3. 从个人主页点击星光值标签进入星光值详情页
        page.click_entry_star_value()

        # 4. 断言已进入星光值详情页
        page.assert_star_nickname()

        # 5. 点击左上角返回箭头
        page.click_btn_back()

        # 6. 断言关闭详情页回跳上一级页面（个人主页）
        page.assert_profile_nickname()
        # 点击test_lkwg
        page.click_test_lkwg()
        # 点击test_lkwg
        page.click_test_lkwg()
        # 1111111
        page.click_tesst()
        # 点击tesst
        page.click_tesst()
        # 点击tesst
        page.click_tesst()

    def test_gift_card_no_response(self):
        page = self.page

        # 1. 回到主页面（统一用例起点）
        page.to_main_page()

        # 2. 点击底部「我的」进入个人主页
        page.click_tab_mine()

        # 3. 从个人主页点击星光值标签进入星光值详情页
        page.click_entry_star_value()

        # 4. 断言礼物墙静态展示
        page.assert_text_gift_wall()

        # 5. 点击礼物墙任意礼物卡片，断言不跳转、不弹窗、无响应
        page.assert_gift_card_click_no_response()

    def test_swipe_up_browse_gifts(self):
        page = self.page

        # 1. 回到主页面（统一用例起点）
        page.to_main_page()

        # 2. 点击底部「我的」进入个人主页
        page.click_tab_mine()

        # 3. 从个人主页点击星光值标签进入星光值详情页
        page.click_entry_star_value()

        # 4. 页面上滑滚动
        page.swipe_up(2)

        # 5. 断言页面正常纵向滚动且可浏览礼物卡片
        page.assert_browse_after_swipe()

    def test_swipe_up_to_bottom(self):
        page = self.page

        # 1. 回到主页面（统一用例起点）
        page.to_main_page()

        # 2. 点击底部「我的」进入个人主页
        page.click_tab_mine()

        # 3. 从个人主页点击星光值标签进入星光值详情页
        page.click_entry_star_value()

        # 4. 上滑滚动至礼物墙底部，断言到底后不可再滑动
        page.swipe_to_bottom_and_assert()

    def test_swipe_down_to_top(self):
        page = self.page

        # 1. 回到主页面（统一用例起点）
        page.to_main_page()

        # 2. 点击底部「我的」进入个人主页
        page.click_tab_mine()

        # 3. 从个人主页点击星光值标签进入星光值详情页
        page.click_entry_star_value()

        # 4. 前置：上滑滚动至礼物墙底部
        page.swipe_to_bottom_and_assert()

        # 5. 下滑滚动至礼物墙顶部，断言到顶后不可再滑动
        page.swipe_to_top_and_assert()


    def teardown_class(self):
        self.appOperator.reset_app()
