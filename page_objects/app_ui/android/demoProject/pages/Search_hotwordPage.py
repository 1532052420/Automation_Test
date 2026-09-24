# -*- coding: utf-8 -*-
# 页面对象（用例包：search_hotword）
from page_objects.app_ui.android.demoProject.elements.search_hotwordElements import Search_hotwordElements
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By
class Search_hotwordPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = Search_hotwordElements()

    def click_btnSearch(self):
        """点击「搜索入口」"""
        self.appOperator.click(self._elements.btnSearch)

    def input_search_input(self, text):
        """在「搜索输入框」输入「zhou」"""
        self.appOperator.sendText(self._elements.search_input, text)

    def click_search_submit(self):
        """点击「搜索提交」"""
        self.appOperator.click(self._elements.search_submit)

    def wait_user_first(self, timeout_seconds=60):
        """等待「用户结果首条」出现"""
        probe = CreateElement.create(self._elements.user_first.locator_type,
                                     self._elements.user_first.locator_value,
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                     wait_seconds=timeout_seconds)
        self.appOperator.getElement(probe)

    def assert_user_first(self):
        """断言「用户结果首条」出现"""
        self.appOperator.getElement(self._elements.user_first)


