# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class PersonalInfoElements:
    def __init__(self):
        self.action_bar_root = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/action_bar_root', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.content = CreateElement.create(Locator_Type.ID, 'android:id/content', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.toolbar = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/toolbar', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.tool_bar = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tool_bar', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.navigationText = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/navigationText', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.toolbarTitle = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/toolbarTitle', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='个人资料')  # 个人资料 · 批量采集
        self.btnAvatar = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnAvatar', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.btnNickname = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnNickname', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.昵称 = CreateElement.create(Locator_Type.XPATH, '//*[@text="昵称"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='昵称')  # 昵称 · 批量采集
        self.白日依山尽 = CreateElement.create(Locator_Type.XPATH, '//*[@text="白日依山尽"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='白日依山尽')  # 白日依山尽 · 批量采集
        self.btnId = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnId', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.ID号 = CreateElement.create(Locator_Type.XPATH, '//*[@text="ID号"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='ID号')  # ID号 · 批量采集
        self.el_829655829 = CreateElement.create(Locator_Type.XPATH, '//*[@text="829655829"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='829655829')  # 829655829 · 批量采集
        self.btnGender = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnGender', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.性别 = CreateElement.create(Locator_Type.XPATH, '//*[@text="性别"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='性别')  # 性别 · 批量采集
        self.女 = CreateElement.create(Locator_Type.XPATH, '//*[@text="女"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='女')  # 女 · 批量采集
        self.btnBirthday = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnBirthday', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.生日 = CreateElement.create(Locator_Type.XPATH, '//*[@text="生日"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='生日')  # 生日 · 批量采集
        self.el_1970_01_01 = CreateElement.create(Locator_Type.XPATH, '//*[@text="1970-01-01"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='1970-01-01')  # 1970-01-01 · 批量采集
        self.btnCity = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnCity', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.所在地 = CreateElement.create(Locator_Type.XPATH, '//*[@text="所在地"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='所在地')  # 所在地 · 批量采集
        self.element_2 = CreateElement.create(Locator_Type.XPATH, '//*[@class="android.widget.TextView"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.btnIntroduction = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnIntroduction', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='批量采集')  # 批量采集
        self.个人简介 = CreateElement.create(Locator_Type.XPATH, '//*[@text="个人简介"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='个人简介')  # 个人简介 · 批量采集
        self.请填写 = CreateElement.create(Locator_Type.XPATH, '//*[@text="请填写"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='请填写')  # 请填写 · 批量采集
        self.contentInput = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/contentInput', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=3, desc='写入歌词输入框')  # 写入歌词输入框
