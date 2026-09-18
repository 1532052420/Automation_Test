# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class LocatorGuiElements:
    def __init__(self):
        self.search_btn = CreateElement.create(Locator_Type.XPATH, '//*[@text="搜索"]', wait_type=Wait_By.ELEMENT_TO_BE_CLICKABLE)
        self.csxxxxxxxxxx = CreateElement.create(Locator_Type.ID, 'com.huawei.android.launcher:id/workspace_screen', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=30)
        self.image = CreateElement.create(Locator_Type.XPATH, '//*[@resource-id="com.vivo.browser:id/image"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
