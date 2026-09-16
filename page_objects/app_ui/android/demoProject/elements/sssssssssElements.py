# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（用例包：ssssssssss）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class SssssssssElements:
    def __init__(self):
        self.ssssssss = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/ivGift', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.element_10 = CreateElement.create(Locator_Type.XPATH, '//*[@class="android.widget.ImageButton"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
