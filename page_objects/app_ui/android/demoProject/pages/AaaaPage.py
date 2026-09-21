# -*- coding: utf-8 -*-
# 页面对象（用例包：aaaa）
from page_objects.app_ui.android.demoProject.elements.aaaaElements import AaaaElements


class AaaaPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = AaaaElements()

    def click_workspace_screen(self):
        """点击「workspace_screen」"""
        self.appOperator.click(self._elements.workspace_screen)

    def click_xxxxxx(self):
        """22222"""
        self.appOperator.click(self._elements.xxxxxx)

    def click_ccccc(self):
        """3333333"""
        self.appOperator.click(self._elements.ccccc)


