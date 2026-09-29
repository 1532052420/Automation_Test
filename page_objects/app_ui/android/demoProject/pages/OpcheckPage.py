# -*- coding: utf-8 -*-
# 页面对象（用例包：opcheck · 操作类型真机验证）
# 每个方法体与元素定位器「添加测试用例」生成的代码语义完全一致（pkgMethodBlock 同源）
from page_objects.app_ui.android.demoProject.elements.opcheckElements import OpcheckElements


class OpcheckPage:

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = OpcheckElements()

    # ---------- 点击 ----------
    def click_missing(self):
        """点击「不存在的元素」"""
        self.appOperator.click(self._elements.missing)

    def click_tv_use(self):
        """点击「去创作按钮」"""
        self.appOperator.click(self._elements.tv_use)

    # ---------- 输入（载体：系统设置搜索框，App 内无稳定可达输入框） ----------
    def open_settings(self):
        """打开系统设置（输入操作载体页）"""
        import time
        self.appOperator._driver.activate_app('com.android.settings')
        time.sleep(2)

    def back_to_kuaige(self):
        """回到快歌 App"""
        import time
        self.appOperator._driver.activate_app('com.recordlife.kuaige')
        time.sleep(2)

    def input_settings_search(self, text):
        """在「系统设置搜索框」输入内容（先进搜索输入页）"""
        import time
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        self.open_search_input()
        probe = CreateElement.create(Locator_Type.ID, 'android:id/search_src_text',
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=6)
        el = self.appOperator.getElement(probe)
        el.clear()
        el.send_keys(text)

    def input_missing(self, text):
        """在「不存在的元素」输入"""
        self.appOperator.sendText(self._elements.missing, text)

    # ---------- 长按 ----------
    def long_press_content(self):
        """长按「页面根布局」"""
        self.appOperator.touch_long_press(self._elements.content, duration_sconds=2)

    def long_press_missing(self):
        """长按「不存在的元素」"""
        self.appOperator.touch_long_press(self._elements.missing, duration_sconds=2)

    # ---------- 坐标点击 ----------
    def tap_xy(self, x, y):
        """点击坐标"""
        self.appOperator.tap(x, y)

    # ---------- 截图 ----------
    def wait_and_shot(self, tag):
        """截图"""
        import time
        time.sleep(1)
        self.appOperator.get_screenshot(tag)

    # ---------- 断言存在 ----------
    def assert_content(self):
        """断言「页面根布局」出现"""
        self.appOperator.getElement(self._elements.content)
        self.appOperator.get_screenshot('断言·断言「页面根布局」出现')

    def assert_missing(self):
        """断言「不存在的元素」出现"""
        self.appOperator.getElement(self._elements.missing)
        self.appOperator.get_screenshot('断言·断言「不存在的元素」出现')

    # ---------- 断言文本 ----------
    def assert_tv_use_text(self, expected):
        """断言「去创作按钮」文本"""
        assert self.appOperator.getText(self._elements.tv_use) == expected, '断言「去创作按钮」文本为「%s」' % expected
        self.appOperator.get_screenshot('断言·断言「去创作按钮」文本')

    def assert_tab_text(self, expected):
        """断言「设置页WLAN」文本（设置页文案稳定，测试载体）"""
        import time
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        self.open_settings()
        probe = CreateElement.create(Locator_Type.XPATH, "//*[@text='WLAN']",
                                     wait_type=Wait_By.VISIBILITY_OF, wait_seconds=6)
        el = self.appOperator.getElement(probe)
        assert self.appOperator.getText(el) == expected, '断言WLAN文本为「%s」' % expected
        self.appOperator.get_screenshot('断言·断言WLAN文本')

    def open_search_input(self):
        """打开设置搜索输入页（点「搜索设置项」进输入框，属测试准备）"""
        import time
        self.open_settings()
        self.appOperator.tap(792, 447)
        time.sleep(2)

    # ---------- 断言Toast ----------
    def assert_toast(self, text):
        """断言Toast"""
        assert self.appOperator.is_toast_visible(text, wait_seconds=5), '断言Toast包含「%s」' % text
        self.appOperator.get_screenshot('断言·断言Toast')

    # ---------- 断言消失 ----------
    def assert_missing_gone(self, wait_seconds=2):
        """断言「不存在的元素」已消失"""
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        probe = CreateElement.create(self._elements.missing.locator_type,
                                     self._elements.missing.locator_value,
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                     wait_seconds=wait_seconds)
        gone = True
        try:
            self.appOperator.getElement(probe)
            gone = False
        except Exception:
            pass
        self.appOperator.assert_true_with_shot('断言「不存在的元素」已消失', gone,
                                               '等待' + str(wait_seconds) + '秒内元素仍可见')

    def assert_content_gone(self, wait_seconds=2):
        """断言「页面根布局」已消失"""
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        probe = CreateElement.create(self._elements.content.locator_type,
                                     self._elements.content.locator_value,
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                     wait_seconds=wait_seconds)
        gone = True
        try:
            self.appOperator.getElement(probe)
            gone = False
        except Exception:
            pass
        self.appOperator.assert_true_with_shot('断言「页面根布局」已消失', gone,
                                               '等待' + str(wait_seconds) + '秒内元素仍可见')

    # ---------- 轮询等待出现 ----------
    def wait_content(self, timeout_seconds=5):
        """等待「页面根布局」出现"""
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        probe = CreateElement.create(self._elements.content.locator_type,
                                     self._elements.content.locator_value,
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                     wait_seconds=timeout_seconds)
        self.appOperator.getElement(probe)

    def wait_missing(self, timeout_seconds=3):
        """等待「不存在的元素」出现"""
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        probe = CreateElement.create(self._elements.missing.locator_type,
                                     self._elements.missing.locator_value,
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                     wait_seconds=timeout_seconds)
        self.appOperator.getElement(probe)

    # ---------- 出现才点击 ----------
    def click_tv_use_if_visible(self, timeout_seconds=3):
        """若「去创作按钮」出现则点击"""
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        probe = CreateElement.create(self._elements.tv_use.locator_type,
                                     self._elements.tv_use.locator_value,
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                     wait_seconds=timeout_seconds)
        try:
            self.appOperator.click(self.appOperator.getElement(probe))
        except Exception:
            pass

    def click_missing_if_visible(self, timeout_seconds=2):
        """若「不存在的元素」出现则点击"""
        from page_objects.createElement import CreateElement
        from page_objects.app_ui.locator_type import Locator_Type
        from page_objects.app_ui.wait_type import Wait_Type as Wait_By
        probe = CreateElement.create(self._elements.missing.locator_type,
                                     self._elements.missing.locator_value,
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                     wait_seconds=timeout_seconds)
        try:
            self.appOperator.click(self.appOperator.getElement(probe))
        except Exception:
            pass

    # ---------- 特殊操作 ----------
    def dismiss_keyboard(self):
        """收起键盘（键盘在才收，否则不动）"""
        try:
            if self.appOperator.is_keyboard_shown():
                self.appOperator.hide_keyboard()
        except Exception:
            self.appOperator.press_keycode(4)
        import time
        time.sleep(1)

    def deal_first_launch_dialogs(self):
        """首次启动弹窗处理（无弹窗自动跳过）"""
        import time
        for _lval, _desc in (
                ("//*[@text='同意并继续']", '隐私协议弹窗'),
                ("//*[@text='允许']", '系统权限弹窗'),
        ):
            from page_objects.createElement import CreateElement
            from page_objects.app_ui.locator_type import Locator_Type
            from page_objects.app_ui.wait_type import Wait_Type as Wait_By
            probe = CreateElement.create(Locator_Type.XPATH, _lval,
                                         wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,
                                         wait_seconds=2)
            try:
                self.appOperator.click(self.appOperator.getElement(probe))
                time.sleep(1)
            except Exception:
                pass

    def click_content(self):
        """点击「content」· 含2断言"""
        failures = []
        try:
                    self.appOperator.click(self._elements.content)
        except Exception as _e:
            self.appOperator.get_screenshot('操作失败_点击')
            failures.append('主操作: %s' % str(_e)[:120])
        probe = CreateElement.create(self._elements.content.locator_type,
                                     self._elements.content.locator_value,
                                     wait_type=Wait_By.VISIBILITY_OF,
                                     wait_seconds=3)
        self.appOperator.assert_text_or_record(failures, '断言1·文本', probe, expected='测试文本A')
        probe = CreateElement.create(self._elements.content.locator_type,
                                     self._elements.content.locator_value,
                                     wait_type=Wait_By.VISIBILITY_OF,
                                     wait_seconds=3)
        self.appOperator.assert_visual_or_record(failures, '断言2·视觉', probe,
                                                baseline='page_objects/app_ui/android/demoProject/elements/baselines/opcheckElements/content.png', threshold=0.9)
        if failures:
            raise AssertionError('%d 项断言未通过：\n%s' % (len(failures), '\n'.join(failures)))


