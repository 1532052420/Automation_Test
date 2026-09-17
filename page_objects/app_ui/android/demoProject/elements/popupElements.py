# -*- coding: utf-8 -*-
# 本文件由 GUI 元素定位器自动生成/维护
# 用途：APP 内置随机弹窗的关闭按钮规则库（自动处理方案的"元素层"）
#
# ★ 定位（重要）：随机弹窗 = 不可预测时机弹出的运营/促销弹窗。处理是「被动识别」——
#   正常用例执行时，框架在每次元素等待的轮询里扫描本规则库，偶遇弹窗就截图挂 allure 并关闭。
#   不为弹窗写专门用例、不主动触发验证；正常用例执行中偶遇即处理，遇不到就待命。
#
# 维护约定：日常执行用例时从 allure 截图（附件名「自动关闭弹窗_规则名」）或日志发现新弹窗
#   → 元素定位器抓 UI 树 → 找关闭按钮（ID 优先）→ 追加一行 + 配锚点；用例层永远不用改。
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type as Wait_By


class PopupElements:
    """随机弹窗关闭按钮规则库：由 common/appium/popup_handler.py 在每次元素等待轮询时被动识别"""

    def __init__(self):
        self.popup_checkin_close = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/btnClose', wait_type=Wait_By.VISIBILITY_OF)  # 随机弹窗·签到弹窗关闭按钮（任务中心/广场签到弹窗通用）
        self.popup_recharge_exit_close = CreateElement.create(Locator_Type.XPATH, '//android.widget.ImageView[@clickable=\'true\' and not(@resource-id)]', wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=1)  # 随机弹窗·充值页返回挽留弹窗关闭×（无ID；仅在RechargeKCoinActivity内扫描，配合RULE_OPTIONS活动约束）
        self.popup_promo_close = CreateElement.create(Locator_Type.ID, 'com.recordlife.kuaige:id/iv_close', wait_type=Wait_By.VISIBILITY_OF)  # 随机弹窗·限时充值优惠弹窗关闭按钮（个人页/充值后概率弹出，右上角×）

    # 规则附加约束（可选）：元素名 -> {anchor: 弹窗特征(类型,值)——场上出现特征才点关闭,
    # activity: 仅在该活动页内扫描, cooldown: 同规则点击冷却秒数}
    # 未配置的规则默认全页面扫描、冷却 2 秒。
    # ★ 锚点很重要：同一个关闭按钮 id（如 btnClose）会被登录弹层等非弹窗界面复用，
    #   不加锚点会把它们误当弹窗关掉（实测踩坑：误关登录弹层导致登录用例失败）

    # 规则附加约束（元素定位器「登记随机弹窗」自动维护，手工编辑请保持语法）：
    #   anchor   关闭按钮与弹窗特征成对出现才点关闭——同一个关闭按钮 id 常被非弹窗界面复用，无锚点会误关
    #   activity 仅在该活动页内扫描；cooldown 同规则点击冷却秒数（默认 2）

    # 规则附加约束（元素定位器「登记随机弹窗」自动维护，手工编辑请保持语法）：
    #   anchor   关闭按钮与弹窗特征成对出现才点关闭——同一个关闭按钮 id 常被非弹窗界面复用，无锚点会误关
    #   activity 仅在该活动页内扫描；cooldown 同规则点击冷却秒数（默认 2）
    RULE_OPTIONS = {
        'popup_checkin_close': {
            'cooldown': 2,
            'anchor': ('xpath', "//*[contains(@text,'今日签到')]"),
        },
        'popup_promo_close': {
            'cooldown': 2,
            'anchor': ('xpath', "//*[contains(@text,'限时充值优惠')]"),
        },
        'popup_recharge_exit_close': {
            'activity': '.feature.recharge.RechargeKCoinActivity',
            'cooldown': 2,
            'anchor': ('id', 'com.recordlife.kuaige:id/bg'),
        },
    }



    # 业务弹窗白名单：不允许自动关闭、需用例/页面对象显式处理的弹窗
    # - 新用户「选择性别和年龄」引导弹窗：无关闭按钮，必须完成选择
    WHITELIST = ['选择性别和年龄']

    # ★ 使用须知（已知边界）：
    # 1) 本身要操作某弹窗的用例（如签到流程用例），执行前设置环境变量 POPUP_AUTO_CLOSE=0
    #    关闭自动处理，否则弹窗会被先关掉导致用例找不到弹窗内按钮；
    # 2) 规则锚点里的文案（如'今日签到'）若 App 改版文案变化，需同步更新锚点；
    # 3) 弹窗处理不做断言：偶遇即截图挂 allure + 关闭 + 写日志，用例结果不受影响。
