# -*- coding: utf-8 -*-
# 用例中文名：操作类型真机验证
# 用例包 opcheck · 元素定位器「②操作」全部操作类型 × 正常/错误数据
# 说明：错误数据组的「失败」即预期结果（验证失败路径正确报错）
import time
import pytest
import allure
from base.app_ui.android.demoProject.app_ui_android_demoProject_client import APP_UI_Android_demoProject_Client
from page_objects.app_ui.android.demoProject.pages.OpcheckPage import OpcheckPage


@allure.parent_suite('快歌APP自动化')
@allure.suite('opcheck')
@pytest.mark.no_recording
class TestOpcheck:

    def setup_class(self):
        self.demoProjectClient = APP_UI_Android_demoProject_Client(is_need_kill_app=False)
        self.appOperator = self.demoProjectClient.appOperator
        self.appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(3)
        self.page = OpcheckPage(self.appOperator)

    # ---------- 点击 ----------
    @allure.title('点击-正常数据：点击存在的根布局')
    def test_01_click_ok(self):
        """点击成功"""
        page = self.page
        page.click_content()

    @allure.title('点击-错误数据：点击不存在的元素')
    def test_02_click_fail(self):
        """点击失败（预期失败）"""
        page = self.page
        page.click_missing()

    # ---------- 输入 ----------
    @allure.title('输入-正常数据：设置搜索框输入文本')
    def test_03_input_ok(self):
        """输入成功"""
        page = self.page
        page.open_settings()
        page.input_settings_search('opcheck2026')
        page.dismiss_keyboard()

    @allure.title('输入-错误数据：向不存在的元素输入')
    def test_04_input_fail(self):
        """输入失败（预期失败）"""
        page = self.page
        page.back_to_kuaige()
        page.input_missing('opcheck')

    # ---------- 长按 ----------
    @allure.title('长按-正常数据：长按根布局2秒')
    def test_05_long_press_ok(self):
        """长按有效"""
        page = self.page
        page.long_press_content()

    @allure.title('长按-错误数据：长按不存在的元素')
    def test_06_long_press_fail(self):
        """长按无效（预期失败）"""
        page = self.page
        page.long_press_missing()

    # ---------- 坐标点击 ----------
    @allure.title('坐标点击-正常数据：屏幕内坐标')
    def test_07_tap_ok(self):
        """坐标点击成功"""
        page = self.page
        page.tap_xy(720, 1500)

    @allure.title('坐标点击-错误数据：非法坐标')
    def test_08_tap_fail(self):
        """坐标点击失败（预期失败）"""
        page = self.page
        page.tap_xy('opcheck', None)

    # ---------- 截图 ----------
    @allure.title('截图-正常数据：正常截图存证')
    def test_09_screenshot_ok(self):
        """截图成功"""
        page = self.page
        page.wait_and_shot('opcheck_screenshot')

    @allure.title('截图-错误数据：超长含斜杠非法文件名')
    def test_10_screenshot_fail(self):
        """截图非法参数（验证异常处理）"""
        page = self.page
        page.appOperator.get_screenshot('opcheck/illegal/' + 'x' * 260)

    # ---------- 固定等待 ----------
    @allure.title('固定等待-正常数据：等待1秒')
    def test_11_sleep_ok(self):
        """固定等待成功"""
        time.sleep(1)

    @allure.title('固定等待-错误数据：等待非法参数')
    def test_12_sleep_fail(self):
        """固定等待失败（预期失败）"""
        time.sleep('opcheck')

    # ---------- 断言存在 ----------
    @allure.title('断言存在-正常数据：根布局存在')
    def test_13_assert_visible_ok(self):
        """断言成功"""
        page = self.page
        page.assert_content()

    @allure.title('断言存在-错误数据：断言不存在的元素')
    def test_14_assert_visible_fail(self):
        """断言失败（预期失败）"""
        page = self.page
        page.assert_missing()

    # ---------- 断言文本 ----------
    @allure.title('断言文本-正常数据：去创作按钮文本匹配')
    def test_15_assert_text_ok(self):
        """断言成功"""
        page = self.page
        page.assert_tab_text('WLAN')

    @allure.title('断言文本-错误数据：文本不匹配')
    def test_16_assert_text_fail(self):
        """断言失败（预期失败）"""
        page = self.page
        page.assert_tab_text('不存在的文本opcheck')

    # ---------- 断言Toast ----------
    @allure.title('断言Toast-错误数据：断言不存在的Toast')
    def test_17_assert_toast_fail(self):
        """断言失败（预期失败）"""
        page = self.page
        page.assert_toast('opcheck_toast_不存在')

    # ---------- 断言消失 ----------
    @allure.title('断言消失-正常数据：不存在的元素已消失')
    def test_18_assert_gone_ok(self):
        """断言成功"""
        page = self.page
        page.assert_missing_gone()

    @allure.title('断言消失-错误数据：存在的元素断言消失')
    def test_19_assert_gone_fail(self):
        """断言失败（预期失败）"""
        page = self.page
        page.assert_content_gone()

    # ---------- 轮询等待出现 ----------
    @allure.title('轮询等待-正常数据：等待根布局出现')
    def test_20_wait_ok(self):
        """轮询等待成功"""
        page = self.page
        page.wait_content(5)

    @allure.title('轮询等待-错误数据：等待不存在的元素超时')
    def test_21_wait_fail(self):
        """轮询等待超时（预期失败）"""
        page = self.page
        page.wait_missing(3)

    # ---------- 出现才点击 ----------
    @allure.title('出现才点击-正常数据：元素出现则点击')
    def test_22_if_click_ok(self):
        """分支点击成功"""
        page = self.page
        page.click_tv_use_if_visible(3)

    @allure.title('出现才点击-分支数据：元素不出现则跳过')
    def test_23_if_click_skip(self):
        """分支跳过（设计语义=通过）"""
        page = self.page
        page.click_missing_if_visible(2)

    # ---------- 自定义代码 ----------
    @allure.title('自定义代码-正常数据：恒真断言')
    def test_24_custom_ok(self):
        """自定义代码成功"""
        assert True, 'custom ok'

    @allure.title('自定义代码-错误数据：恒假断言')
    def test_25_custom_fail(self):
        """自定义代码失败（预期失败）"""
        assert 1 == 2, 'custom fail: 1 != 2'

    # ---------- 特殊操作：收起键盘 ----------
    @allure.title('收起键盘-正常数据：键盘弹出后收起')
    def test_26_keyboard_ok(self):
        """收起键盘成功"""
        page = self.page
        page.open_settings()
        page.input_settings_search('keyboard')
        page.dismiss_keyboard()

    @allure.title('收起键盘-分支数据：无键盘时静默跳过')
    def test_27_keyboard_skip(self):
        """无键盘跳过（设计语义=通过）"""
        page = self.page
        page.dismiss_keyboard()

    # ---------- 特殊操作：首次启动弹窗处理 ----------
    @allure.title('首启弹窗处理-正常数据：无弹窗自动跳过')
    def test_28_first_launch_skip(self):
        """无弹窗跳过（设计语义=通过）"""
        page = self.page
        page.deal_first_launch_dialogs()

    def teardown_class(self):
        self.appOperator.close_app()
