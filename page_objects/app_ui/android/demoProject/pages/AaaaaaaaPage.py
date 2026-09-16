# -*- coding: utf-8 -*-
# 页面对象（用例包：aaaaaaaa）
from page_objects.app_ui.android.demoProject.elements.aaaaaaaaElements import AaaaaaaaElements


class AaaaaaaaPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = AaaaaaaaElements()

    def input_btnRealName(self, text):
        """在「btnRealName」输入"""
        self.appOperator.sendText(self._elements.btnRealName, text)
