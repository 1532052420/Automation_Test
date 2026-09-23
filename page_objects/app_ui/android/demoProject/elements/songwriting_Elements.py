# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（用例包：songwriting）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class Songwriting_Elements:
    def __init__(self):
        self.btnWriteNewSong = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnWriteNewSong', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=3, desc='一键写歌')  # 一键写歌 · 一键写歌入口
        self.contentInput = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/contentInput', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=3, desc='写入歌词输入框')  # 写入歌词输入框
