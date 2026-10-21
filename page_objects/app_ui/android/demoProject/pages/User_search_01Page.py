# -*- coding: utf-8 -*-
# 页面对象（用例包：user_search_01）
from page_objects.app_ui.android.demoProject.elements.user_search_01Elements import User_search_01Elements
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By
class User_search_01Page:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = User_search_01Elements()

    def click_search_submit(self):
        """点击「搜索提交」"""
        self.appOperator.click(self._elements.search_submit)

    def assert_user_nick_text(self, expected):
        """断言「用户昵称」文本为 expected（参数化：同一方法可被多个断言步骤以不同文本复用，报告文案随 expected 走）"""
        self.appOperator.assert_text_or_fail(self._elements.user_nick, expected, '断言「用户昵称」文本为「' + expected + '」')

    def click_btnSearch(self, wait_seconds=None, wait_type=None):
        """点击「搜索入口」"""
        el = self._elements.btnSearch
        if wait_seconds is not None or wait_type is not None:
            el = CreateElement.create(el.locator_type, el.locator_value, wait_type=wait_type or el.wait_type, wait_seconds=wait_seconds if wait_seconds is not None else el.wait_seconds, desc=getattr(el, 'desc', None))
        self.appOperator.click(el)


    def input_search_input(self, text, wait_seconds=None, wait_type=None):
        """在「搜索输入框」输入「所谓伊人，在水一方」"""
        el = self._elements.search_input
        if wait_seconds is not None or wait_type is not None:
            el = CreateElement.create(el.locator_type, el.locator_value, wait_type=wait_type or el.wait_type, wait_seconds=wait_seconds if wait_seconds is not None else el.wait_seconds, desc=getattr(el, 'desc', None))
        self.appOperator.sendText(el, text)


