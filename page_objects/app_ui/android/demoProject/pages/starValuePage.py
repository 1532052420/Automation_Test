# -*- coding: utf-8 -*-
# 点击返回箭头回跳上一级页面
import time

from page_objects.app_ui.android.demoProject.elements.starValueElements import StarValueElements
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class StarValuePage:
    """星光值模块交互用例页面对象（元素定位器生成 + 滚动/弹窗辅助方法）"""

    def __init__(self, appOperator):
        self.appOperator = appOperator
        self._elements = StarValueElements()

    def assert_star_nickname(self):
        """断言已进入星光值详情页"""
        self.appOperator.getElement(self._elements.star_nickname)

    def click_btn_back(self):
        """点击左上角返回箭头"""
        self.appOperator.click(self._elements.btn_back)

    def assert_profile_nickname(self):
        """断言关闭详情页回跳上一级页面（个人主页）"""
        self.appOperator.getElement(self._elements.profile_nickname)

    def assert_text_gift_wall(self):
        """断言礼物墙静态展示"""
        self.appOperator.getElement(self._elements.text_gift_wall)

    def click_tab_mine(self):
        """点击底部「我的」进入个人主页"""
        self.appOperator.click(self._elements.tab_mine)

    def click_entry_star_value(self):
        """从个人主页点击星光值标签进入星光值详情页"""
        self.appOperator.click(self._elements.entry_star_value)

    # ---- 以下为辅助方法：统一入口 / 弹窗处理 / 滚动 / 无响应断言 ----
    def deal_popups(self):
        """关闭主页面可能出现的活动弹窗（签到/充值促销等，通用关闭按钮），无弹窗快速跳过"""
        try:
            probe = CreateElement.create(Locator_Type.XPATH,
                                         "//*[@resource-id='com.recordlife.kuaige:id/btnClose']",
                                         wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=2)
            self.appOperator.click(probe)
            time.sleep(1)
        except Exception:
            pass

    def to_main_page(self):
        """回到主页面（统一用例起点）：拉起主 Activity；若停留在二级页则逐级返回直到出现底部 tab"""
        self.appOperator.start_activity('com.recordlife.kuaige',
                                        'com.recordlife.kuaige.feature.main.MainActivity')
        time.sleep(2)
        probe = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/tabMine',
                                     wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=2)
        for _ in range(4):
            try:
                self.appOperator.getElement(probe)
                break
            except Exception:
                self.appOperator.press_keycode(4)
                time.sleep(1)
        self.deal_popups()

    def swipe_up(self, times=1):
        """页面上滑滚动（内容上移，浏览下方礼物卡片）；记录滑动前可见内容供滚动断言比对。
        注意：详情页头部（头像/累计获得/礼物墙标题）为固定区域不随滚动，仅礼物网格滚动。"""
        self._src_before_swipe = self._visible_source()
        for _ in range(int(times)):
            self.appOperator.touch_up_slide(0.5, 0.6, 500)
            time.sleep(1.2)

    def swipe_down(self, times=1):
        """页面向下滚动（内容下移，回到上方）"""
        for _ in range(int(times)):
            self.appOperator.touch_down_slide(0.5, 0.4, 500)
            time.sleep(1.2)

    def _visible_source(self):
        """当前屏幕可见节点 XML（只含可见元素，用于滚动位置比对）"""
        return self.appOperator.get_page_source()

    def swipe_to_bottom_and_assert(self):
        """反复上滑直到页面内容连续两次不再变化（到达礼物墙底部），断言到底后不可再滑动。
        礼物墙按礼物类型聚合展示，约3~4屏，循环上限10次足够。"""
        stable = 0
        last_src = ''
        for _ in range(10):
            src = self._visible_source()
            if src == last_src:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            last_src = src
            self.appOperator.touch_up_slide(0.5, 0.6, 500)
            time.sleep(1.5)
        ok = stable >= 2
        self.appOperator.assert_true_with_shot(
            '断言已滑动到礼物墙底部（连续两次上滑内容不再变化）', ok,
            '上滑10次后页面内容仍在变化，未到达礼物墙底部')

    def swipe_to_top_and_assert(self):
        """反复下滑直到页面内容连续两次不再变化（回到礼物墙顶部），断言顶部元素可见"""
        stable = 0
        last_src = ''
        for _ in range(10):
            src = self._visible_source()
            if src == last_src:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            last_src = src
            self.appOperator.touch_down_slide(0.5, 0.4, 500)
            time.sleep(1.5)
        ok = True
        try:
            self.appOperator.getElement(self._elements.text_gift_wall)
            self.appOperator.getElement(self._elements.gift_card_first)
        except Exception:
            ok = False
        self.appOperator.assert_true_with_shot(
            '断言已滑动到礼物墙顶部（「礼物墙」标题与礼物卡片可见）', ok,
            '下滑后未回到礼物墙顶部：标题或礼物卡片不可见')

    def assert_browse_after_swipe(self):
        """断言上滑后页面正常滚动且可继续浏览礼物卡片：
        头部为固定区域，以「滑动前后可见礼物内容变化」判定纵向滚动发生，以礼物卡片仍可见判定可浏览"""
        src_after = self._visible_source()
        scrolled = (src_after != getattr(self, '_src_before_swipe', ''))
        self.appOperator.assert_true_with_shot(
            '断言上滑后礼物区域发生纵向滚动（可见内容变化）', scrolled,
            '上滑后可见内容未变化，页面未发生滚动')
        self.appOperator.getElement(self._elements.gift_card_first)

    def assert_gift_card_click_no_response(self):
        """点击礼物墙礼物卡片，断言无响应：不跳转（Activity不变）、不弹窗（详情页元素仍在）"""
        before_activity = self.appOperator.get_current_activity()
        self.appOperator.click(self._elements.gift_card_first)
        time.sleep(1.5)
        after_activity = self.appOperator.get_current_activity()
        ok = (before_activity == after_activity)
        try:
            self.appOperator.getElement(self._elements.text_gift_wall)
        except Exception:
            ok = False
        self.appOperator.assert_true_with_shot(
            '断言点击礼物卡片无响应（不跳转、不弹窗）', ok,
            '点击礼物卡片后页面发生变化：activity %s -> %s 或详情页元素消失'
            % (before_activity, after_activity))

    def click_test_lkwg(self):
        """点击「洛克王国：世界」"""
        self.appOperator.click(self._elements.test_lkwg)

    def click_tesst(self):
        """点击「toolbarLayout」"""
        self.appOperator.click(self._elements.tesst)

    def click_tvTitle(self):
        """点击「tvTitle」"""
        self.appOperator.click(self._elements.tvTitle)

    def click_appBarLayout(self):
        """点击「appBarLayout」"""
        self.appOperator.click(self._elements.appBarLayout)

    def click_element_10(self):
        """点击「element_10」"""
        self.appOperator.click(self._elements.element_10)

    def click_btnStarlightValue(self):
        """点击「btnStarlightValue」"""
        self.appOperator.click(self._elements.btnStarlightValue)


