# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（用例包：user_search_01）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class User_search_01Elements:
    def __init__(self):
        self.btnSearch = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnSearch', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='搜索入口')  # 搜索入口
        self.search_input = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/etSearch', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='搜索输入框')  # 搜索输入框
        self.search_submit = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnSearch', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='搜索提交')  # 搜索提交
        self.user_nick = CreateElement.create(Locator_Type.XPATH, '//*[@resource-id="com.recordlife.kuaige:id/tvNickname"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='用户昵称')  # 用户昵称
