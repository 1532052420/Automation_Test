# -*- coding: utf-8 -*-
# 快歌(kuaige) App · 手机号登录页面类
from page_objects.app_ui.android.demoProject.elements.kuaigeLoginElements import KuaigeLoginElements


class KuaigeLoginPage:
    """快歌 App 登录流程操作封装：点任意位置触发登录 → 手机号登录 → 勾选协议 → 断言结果"""

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = KuaigeLoginElements()

    def tap_anywhere_to_trigger_login(self):
        """点击屏幕任意一个地方（主页内容区），触发登录弹层 + '请先登录' toast"""
        self.appOperator.tap(360, 768)

    def assert_need_login_toast(self):
        """断言 toast：请先登录"""
        assert self.appOperator.is_toast_visible('请先登录', wait_seconds=5), \
            '未弹出"请先登录"toast'

    def click_phone_login(self):
        """点击 手机号登录 入口（登录方式选择层）"""
        self.appOperator.click(self._elements.btn_phone_login)

    def input_phone(self, phone):
        """在手机号输入框输入手机号"""
        self.appOperator.sendText(self._elements.et_phone, phone)

    def input_code(self, code):
        """在验证码输入框输入验证码"""
        self.appOperator.sendText(self._elements.et_code, code)

    def click_login(self):
        """点击 立即登录"""
        self.appOperator.click(self._elements.btn_login)

    def assert_need_agree_toast(self):
        """断言 toast：请先勾选下方协议（未勾选协议点立即登录时弹出）"""
        assert self.appOperator.is_toast_visible('请先勾选下方协议', wait_seconds=5), \
            '未弹出"请先勾选下方协议"toast'

    def check_agreement(self):
        """点击 我已阅读并同意（切换协议勾选状态）"""
        self.appOperator.click(self._elements.agree_protocol)

    def assert_login_success(self):
        """断言登录成功：登录成功 toast 为主要依据（框架 is_toast_visible），
        toast 已完成生命周期时兜底页面文案（getElement）；成败截图由框架断言方法统一处理"""
        ok = self.appOperator.is_toast_visible('登录成功', wait_seconds=5)
        if not ok:
            try:
                self.appOperator.getElement(self._elements.text_login_success)
                ok = True
            except Exception:
                pass
        self.appOperator.assert_true_with_shot('断言登录成功', ok, '未捕获到「登录成功」toast 或页面文案')

    def wait_and_shot(self, tag):
        """页面稳定 1 秒 + 截图存档（相当于'刷新页面'观察一下）"""
        import time
        time.sleep(1)
        self.appOperator.get_screenshot(tag)
