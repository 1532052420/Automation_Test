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

    def click_element_16(self):
        """点击「element_16」"""
        self.appOperator.click(self._elements.element_16)

    def click_element_12(self):
        """第四步"""
        self.appOperator.click(self._elements.element_12)


