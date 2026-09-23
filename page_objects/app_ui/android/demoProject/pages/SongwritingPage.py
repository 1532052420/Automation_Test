# -*- coding: utf-8 -*-
# 页面对象（用例包：songwriting）
from page_objects.app_ui.android.demoProject.elements.songwriting_Elements import Songwriting_Elements


class SongwritingPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = Songwriting_Elements()

    def click_btnWriteNewSong(self):
        """点击「一键写歌」"""
        self.appOperator.click(self._elements.btnWriteNewSong)
