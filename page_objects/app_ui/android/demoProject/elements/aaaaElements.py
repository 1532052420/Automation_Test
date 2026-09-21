# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（用例包：aaaa）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class AaaaElements:
    def __init__(self):
        self.workspace_screen = CreateElement.create(Locator_Type.ID, 'com.huawei.android.launcher:id/workspace_screen', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='你有没有一直没说出口的话，或是一段难忘的')  # 你有没有一直没说出口的话，或是一段难忘的
        self.xxxxxx = CreateElement.create(Locator_Type.XPATH, '//*[@text="阅读快看版"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='阅读快看版')  # 阅读快看版
        self.ccccc = CreateElement.create(Locator_Type.XPATH, '//*[@text="音乐"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='音乐')  # 音乐
