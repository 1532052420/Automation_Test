# -*- coding: utf-8 -*-
# 共享页面对象 · 所有录制用例的页面方法统一追加在此（同名方法自动覆盖）
from page_objects.app_ui.android.demoProject.elements.appSharedElements import AppSharedElements


class AppSharedPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = AppSharedElements()

    def click_btn_demo(self):
        """点击演示按钮"""
        self.appOperator.click(self._elements.btn_demo)


