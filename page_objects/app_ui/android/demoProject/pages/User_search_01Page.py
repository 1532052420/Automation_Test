# -*- coding: utf-8 -*-
# 页面对象（用例包：user_search_01）
from page_objects.app_ui.android.demoProject.elements.user_search_01Elements import User_search_01Elements


class User_search_01Page:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = User_search_01Elements()

    def click_btnSearch(self):
        """点击「搜索入口」"""
        self.appOperator.click(self._elements.btnSearch)

    def input_search_input(self, text):
        """在「搜索输入框」输入「所谓伊人，在水一方」"""
        self.appOperator.sendText(self._elements.search_input, text)

    def click_search_submit(self):
        """点击「搜索提交」"""
        self.appOperator.click(self._elements.search_submit)

    def assert_user_nick_text(self, expected):
        """断言「用户昵称」文本为 expected（参数化：同一方法可被多个断言步骤以不同文本复用，报告文案随 expected 走）"""
        self.appOperator.assert_text_or_fail(self._elements.user_nick, expected, '断言「用户昵称」文本为「' + expected + '」')


