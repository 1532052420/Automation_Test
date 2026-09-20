# -*- coding: utf-8 -*-
# 由平台「用例编排」生成（用例 #7 登录冒烟·编排）；手改会在下次保存时被覆盖
from page_objects.app_ui.android.demoProject.elements.kuaigeLoginElements import KuaigeLoginElements


class Orch7Page:
    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = KuaigeLoginElements()

    def click_btn_agree_privacy(self):
        """点击登录"""
        self.appOperator.click(self._elements.btn_agree_privacy)

    def input_et_phone(self, text):
        """在et_phone输入「13800138000」"""
        self.appOperator.sendText(self._elements.et_phone, text)

    def assert_et_code(self):
        """断言et_code出现"""
        self.appOperator.getElement(self._elements.et_code)

