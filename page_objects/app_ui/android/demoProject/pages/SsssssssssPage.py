# -*- coding: utf-8 -*-
# 页面对象（用例包：ssssssssss）
from page_objects.app_ui.android.demoProject.elements.sssssssssElements import SssssssssElements


class SsssssssssPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = SssssssssElements()

    def click_ssssssss(self):
        """点击「ivGift」"""
        self.appOperator.click(self._elements.ssssssss)

    def click_element_10(self):
        """点击「element_10」"""
        self.appOperator.click(self._elements.element_10)


