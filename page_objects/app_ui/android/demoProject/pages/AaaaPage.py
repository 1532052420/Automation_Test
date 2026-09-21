# -*- coding: utf-8 -*-
# 页面对象（用例包：aaaa）
from page_objects.app_ui.android.demoProject.elements.aaaaElements import AaaaElements


class AaaaPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = AaaaElements()

    def click_xxxxxx(self):
        """22222"""
        self.appOperator.click(self._elements.xxxxxx)

    def click_ccccc(self):
        """3333333"""
        self.appOperator.click(self._elements.ccccc)

    def click_widget_home(self):
        """点击「widget_home」"""
        self.appOperator.click(self._elements.widget_home)

    def click_widget_city_date(self):
        """点击「widget_city_date」"""
        self.appOperator.click(self._elements.widget_city_date)

    def click_element_45(self):
        """点击「element_45」"""
        self.appOperator.click(self._elements.element_45)

    def click_left_widget_area(self):
        """点击「left_widget_area」"""
        self.appOperator.click(self._elements.left_widget_area)

    def click_阅读快看版(self):
        """点击「阅读快看版」"""
        self.appOperator.click(self._elements.阅读快看版)

    def click_应用市场(self):
        """点击「应用市场」"""
        self.appOperator.click(self._elements.应用市场)

    def click_华为商城(self):
        """点击「华为商城」"""
        self.appOperator.click(self._elements.华为商城)

    def click_钱包(self):
        """点击「钱包」"""
        self.appOperator.click(self._elements.钱包)

    def click_主题11111(self):
        """点击「主题」"""
        self.appOperator.click(self._elements.主题11111)

    def click_主题(self):
        """点击「主题」"""
        self.appOperator.click(self._elements.主题)

    def click_element_9(self):
        """点击「element_9」"""
        self.appOperator.click(self._elements.element_9)

    def click_workspace_screen(self):
        """点击「workspace_screen」"""
        self.appOperator.click(self._elements.workspace_screen)

    def click_workspace(self):
        """点击「workspace」"""
        self.appOperator.click(self._elements.workspace)

    def click_drag_layer(self):
        """点击「drag_layer」"""
        self.appOperator.click(self._elements.drag_layer)

    def click_widget_time_hour(self):
        """点击「widget_time_hour」"""
        self.appOperator.click(self._elements.widget_time_hour)


