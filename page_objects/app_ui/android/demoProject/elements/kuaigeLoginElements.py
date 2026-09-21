# -*- coding: utf-8 -*-
# 快歌(kuaige) App · 手机号登录流程元素
# 本文件元素由 GUI 元素定位器 + 框架探测用例定位（见 element_locator/技术实现方案.md）
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class KuaigeLoginElements:
    """快歌 App 登录相关元素（主页触发 / 登录方式选择 / 手机号登录表单）"""

    def __init__(self):
        # ---- 登录方式选择层（点击主页任意位置后弹出）----
        # 手机号登录入口（FrameLayout，含"手机登录"文案）
        self.btn_phone_login = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnPhone', wait_type=Wait_By.VISIBILITY_OF)

        # ---- 首次启动一次性弹窗（teardown reset_app 会 pm clear 清数据，每次首启都会遇到）----
        # 隐私协议弹窗「同意并继续」按钮
        self.btn_agree_privacy = CreateElement.create(Locator_Type.XPATH, "//*[@text='同意并继续']",
                                                      wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=2)
        # 系统权限弹窗「允许」按钮（通知等权限请求）
        self.btn_system_allow = CreateElement.create(Locator_Type.XPATH, "//*[@text='允许']",
                                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=2)
        # vivo 键盘「键盘选择」布局选择器面板（Appium 输入时切换输入法会触发它弹出并遮挡按钮）
        self.panel_ime_chooser = CreateElement.create(Locator_Type.XPATH, "//*[@text='键盘选择']",
                                                      wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=1)

        # ---- 手机号登录表单页 ----
        # 手机号输入框（hint：请输入手机号）
        self.et_phone = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/etPhone', wait_type=Wait_By.VISIBILITY_OF)
        # 验证码输入框（hint：请输入验证码）
        self.et_code = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/etCode', wait_type=Wait_By.VISIBILITY_OF)
        # 立即登录按钮
        self.btn_login = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnLogin', wait_type=Wait_By.VISIBILITY_OF)
        # 我已阅读并同意 - 左侧勾选框 icon（点击切换勾选）。
        # 注意：不要点整行 TextView（可点但会误触《用户协议》链接跳到协议页），用 ivCheck 精确定位
        self.agree_protocol = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/ivCheck', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6, desc='测试')  # 测试
        # 登录成功字段/文案（含 toast 与页面文本，contains 兼容两种）
        self.text_login_success = CreateElement.create(Locator_Type.XPATH, '//*[contains(@text,"登录成功")]', wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED)
        self.btnStarlightValue = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnStarlightValue', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        self.sss = CreateElement.create(Locator_Type.XPATH, '//*[@text="12枚勋章"]', wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)