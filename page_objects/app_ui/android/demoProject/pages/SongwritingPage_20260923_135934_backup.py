# -*- coding: utf-8 -*-
# 页面对象（用例包：songwriting）
from page_objects.app_ui.android.demoProject.elements.songwritingElements import SongwritingElements


class SongwritingPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = SongwritingElements()

    def click_btnWriteNewSong(self):
        """点击「btnWriteNewSong」"""
        self.appOperator.click(self._elements.btnWriteNewSong)
