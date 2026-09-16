# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class StarValueElements:
    def __init__(self):
        self.tab_mine = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tabMine', wait_type=Wait_By.VISIBILITY_OF)  # 底部tab-我的（个人主页入口）
        self.entry_star_value = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnStarlightValue', wait_type=Wait_By.VISIBILITY_OF)  # 个人主页-星光值标签
        self.profile_nickname = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tvNickname', wait_type=Wait_By.VISIBILITY_OF)  # 个人主页-昵称（返回断言锚点）
        self.btn_back = CreateElement.create(Locator_Type.XPATH, '//*[@resource-id=\'com.recordlife.kuaige:id/tool_bar\']//android.widget.ImageButton', wait_type=Wait_By.VISIBILITY_OF)  # 星光值详情页-左上角返回箭头
        self.star_nickname = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tv_nickname', wait_type=Wait_By.VISIBILITY_OF)  # 星光值详情页-用户昵称
        self.text_starlight_value = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tv_starlight_value', wait_type=Wait_By.VISIBILITY_OF)  # 星光值详情页-星光值数值
        self.text_gift_wall = CreateElement.create(Locator_Type.XPATH, '//*[@text=\'礼物墙\']', wait_type=Wait_By.VISIBILITY_OF)  # 星光值详情页-礼物墙标题
        self.gift_card_first = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tv_gift_name', wait_type=Wait_By.VISIBILITY_OF)  # 礼物墙-第一个礼物卡片名（多个取第一个）
        self.test_lkwg = CreateElement.create(Locator_Type.XPATH, '//*[@text="洛克王国：世界"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
