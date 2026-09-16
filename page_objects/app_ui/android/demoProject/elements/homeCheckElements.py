# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（真机抓取）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class HomeCheckElements:
    def __init__(self):
        self.tab_home = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tabHome', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=10, desc='底部tab-首页')  # 底部tab-首页
        self.tab_write_song = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnCompose', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=10, desc='底部tab-写歌按钮')  # 底部tab-写歌按钮
        self.btn_one_key_write = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnWriteNewSong', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=10, desc='写歌页-一键写歌按钮')  # 写歌页-一键写歌按钮
