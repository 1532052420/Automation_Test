# -*- coding: utf-8 -*-
# 快歌 App · 主页与写歌入口检查页面对象（用例包：home_check）
from page_objects.app_ui.android.demoProject.elements.homeCheckElements import HomeCheckElements


class HomeCheckPage:
    """主页与写歌入口：断言主页 tab、进入写歌页断言一键写歌、返回主页"""

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = HomeCheckElements()

    def assert_tab_home(self):
        """断言主页加载完成（底部首页 tab 可见）"""
        self.appOperator.getElement(self._elements.tab_home)

    def click_tab_write_song(self):
        """点击底部【写歌】按钮"""
        self.appOperator.click(self._elements.tab_write_song)

    def assert_btn_one_key_write(self):
        """断言进入写歌页面（一键写歌按钮可见）"""
        self.appOperator.getElement(self._elements.btn_one_key_write)

    def back_to_main(self):
        """返回键回主页"""
        self.appOperator.press_keycode(4)

    def assert_back_to_main(self):
        """断言返回主页（首页 tab 仍可见）"""
        self.appOperator.getElement(self._elements.tab_home)
