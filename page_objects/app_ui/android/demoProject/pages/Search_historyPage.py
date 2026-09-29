# -*- coding: utf-8 -*-
# 页面对象（用例包：search_history）
from page_objects.app_ui.android.demoProject.elements.search_historyElements import Search_historyElements


class Search_historyPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = Search_historyElements()

    def click_btnSearch(self):
        """点击「搜索入口」"""
        self.appOperator.click(self._elements.btnSearch)

    def input_search_input(self, text):
        """在「搜索输入框」输入「zhou」"""
        self.appOperator.sendText(self._elements.search_input, text)

    def click_search_submit(self):
        """点击「搜索提交」"""
        self.appOperator.click(self._elements.search_submit)

    def click_search_cancel(self):
        """点击「取消返回」"""
        self.appOperator.click(self._elements.search_cancel)


