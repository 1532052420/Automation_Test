# -*- coding: utf-8 -*-
# 工具生成·手机号登录流程执行验证
import time

from page_objects.app_ui.android.demoProject.elements.kuaigeLoginElements import KuaigeLoginElements


class DemoToolLoginPage:
    """工具生成·手机号登录流程执行验证"""

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = KuaigeLoginElements()

    def deal_first_launch_dialogs(self):
        """首次启动一次性弹窗处理：隐私协议「同意并继续」→ 系统权限「允许」。

        teardown 的 reset_app 会清应用数据，每次首启都会遇到弹窗；
        元素等待仅 2s，无弹窗时快速跳过，不影响正常流程。
        """
        for element, desc in ((self._elements.btn_agree_privacy, '隐私协议弹窗'),
                              (self._elements.btn_system_allow, '系统权限弹窗')):
            try:
                self.appOperator.click(element)
                time.sleep(1)  # 等弹窗收尾动画，避免点击落到下层页面
            except Exception:
                pass  # 该弹窗未出现，跳过

    def dismiss_ime_panel(self):
        """收起键盘/vivo 键盘「键盘选择」面板，避免其遮挡登录按钮。

        Appium 输入文本时切换输入法，vivo 键盘会弹布局选择面板盖住表单；
        仅在键盘可见或面板存在时按一次 BACK，否则不动（防止误触返回导航退出登录页）。
        """
        keyboard_shown = False
        try:
            keyboard_shown = bool(self.appOperator.is_keyboard_shown())
        except Exception:
            pass
        panel_visible = True
        try:
            self.appOperator.getElement(self._elements.panel_ime_chooser)
        except Exception:
            panel_visible = False
        if keyboard_shown or panel_visible:
            self.appOperator.press_keycode(4)  # BACK
            time.sleep(0.5)

    def tap_xy(self, x, y):
        """点任意位置触发登录弹层"""
        self.appOperator.tap(x, y)

    def click_btn_phone_login(self):
        """点击手机号登录入口"""
        self.appOperator.click(self._elements.btn_phone_login)

    def input_et_phone(self, text):
        """输入手机号"""
        self.appOperator.sendText(self._elements.et_phone, text)

    def input_et_code(self, text):
        """输入验证码"""
        self.appOperator.sendText(self._elements.et_code, text)

    def assert_toast(self, text):
        """断言toast（成败截图均入 allure）"""
        ok = self.appOperator.is_toast_visible(text, wait_seconds=5)
        self.appOperator.assert_true_with_shot('断言toast「%s」' % text, ok, '未捕获到「%s」toast' % text)

    def assert_login_layer(self):
        """断言登录弹层已出现（手机登录入口可见）——新旧版本通用：旧版弹层前有'请先登录'toast，新版直接弹层"""
        ok = True
        try:
            self.appOperator.getElement(self._elements.btn_phone_login)
        except Exception:
            ok = False
        self.appOperator.assert_true_with_shot('断言登录弹层出现', ok, '未找到手机号登录入口')

    def click_agree_protocol(self):
        """勾选我已阅读并同意"""
        self.appOperator.click(self._elements.agree_protocol)

    def click_btn_login(self):
        """再次点击立即登录"""
        self.appOperator.click(self._elements.btn_login)

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
        """截图存档"""
        import time
        time.sleep(1)
        self.appOperator.get_screenshot(tag)

    def click_sss(self):
        """点击「12枚勋章」"""
        self.appOperator.click(self._elements.sss)

    def click_btnStarlightValue(self):
        """点击「btnStarlightValue」"""
        self.appOperator.click(self._elements.btnStarlightValue)


