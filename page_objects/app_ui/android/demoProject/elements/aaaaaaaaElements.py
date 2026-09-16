# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（用例包：aaaaaaaa）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class AaaaaaaaElements:
    def __init__(self):
        self.btnRealName = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnRealName', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.element_16 = CreateElement.create(Locator_Type.XPATH, '//*[@class="android.view.View"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.element_12 = CreateElement.create(Locator_Type.XPATH, '//*[@class="android.widget.FrameLayout"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
