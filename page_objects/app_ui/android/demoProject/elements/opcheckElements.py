# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（用例包：opcheck）
# 操作类型验证专用元素表：success 组（真实存在）+ missing 组（必然不存在）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class OpcheckElements:
    def __init__(self):
        self.content = CreateElement.create(Locator_Type.ID, 'android:id/content', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=3, desc='页面根布局')  # 页面根布局
        self.missing = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/opcheck_missing_404', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=3, desc='不存在的元素')  # 不存在的元素
        self.tab_text = CreateElement.create(Locator_Type.XPATH, "//*[@text='音乐MV']", wait_type=Wait_By.VISIBILITY_OF, wait_seconds=5, desc='顶部Tab音乐MV')  # 顶部Tab音乐MV
        self.tv_use = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tvUse', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=3, desc='去创作按钮')  # 去创作按钮
