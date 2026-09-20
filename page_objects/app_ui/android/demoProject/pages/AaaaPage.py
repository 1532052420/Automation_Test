# -*- coding: utf-8 -*-
# 页面对象（用例包：aaaa）
from page_objects.app_ui.android.demoProject.elements.aaaaElements import AaaaElements


class AaaaPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = AaaaElements()

    def click_aaaaa(self):
        """点击「快歌」"""
        self.appOperator.click(self._elements.aaaaa)
