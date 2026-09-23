# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护（用例包：aaaa）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class AaaaElements:
    def __init__(self):
        self.workspace_screen = CreateElement.create(Locator_Type.ID, 'com.huawei.android.launcher:id/workspace_screen', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.xxxxxx = CreateElement.create(Locator_Type.XPATH, '//*[@text="阅读快看版"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='阅读快看版')  # 阅读快看版
        self.workspace = CreateElement.create(Locator_Type.ID, 'com.huawei.android.launcher:id/workspace', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.widget_home = CreateElement.create(Locator_Type.ID, 'com.huawei.android.totemweather:id/widget_home', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.widget_city_date = CreateElement.create(Locator_Type.XPATH, '//*[@text="9月21日星期一  八月十一"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='9月21日星期一  八月十一')  # 9月21日星期一  八月十一
        self.element_45 = CreateElement.create(Locator_Type.ACCESSIBILITY_ID, '电话双指上滑即可展示服务卡片', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.left_widget_area = CreateElement.create(Locator_Type.ID, 'com.huawei.android.totemweather:id/left_widget_area', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='11111')  # 11111
        self.阅读快看版 = CreateElement.create(Locator_Type.XPATH, '//*[@text="阅读快看版"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='阅读快看版')  # 阅读快看版
        self.应用市场 = CreateElement.create(Locator_Type.XPATH, '//*[@text="应用市场"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='应用市场')  # 应用市场
        self.华为商城 = CreateElement.create(Locator_Type.XPATH, '//*[@text="华为商城"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='华为商城')  # 华为商城
        self.钱包 = CreateElement.create(Locator_Type.XPATH, '//*[@text="钱包"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='钱包')  # 钱包
        self.主题 = CreateElement.create(Locator_Type.XPATH, '//*[@text="主题"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='主题')  # 主题
        self.主题11111 = CreateElement.create(Locator_Type.XPATH, '//*[@text="主题"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='主题')  # 主题
        self.element_9 = CreateElement.create(Locator_Type.XPATH, '//*[@class="android.widget.RelativeLayout"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.drag_layer = CreateElement.create(Locator_Type.ID, 'com.huawei.android.launcher:id/drag_layer', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.widget_time_hour = CreateElement.create(Locator_Type.ID, 'com.huawei.android.totemweather:id/widget_time_hour', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
