# -*- coding: utf-8 -*-
"""APP 内置随机弹窗自动处理 · 寄生式扫描器

设计：把关闭弹窗的能力寄生在元素操作的等待轮询里——
  入口先扫一次（兜住上一步延迟出现的）→ 每轮轮询先扫弹窗再找目标元素（兜住等待期间新冒出的）。
弹窗被关掉，目标元素自然可见。页面对象与用例零改动、对弹窗"无感"。

规则来源：page_objects/.../elements/popupElements.py（元素名片 = 定位规则，
RULE_OPTIONS 提供可选的活动页约束与冷却秒数，WHITELIST 为业务白名单）。

安全机制：
- 冷却：同一条规则点击后 cooldown 秒内不再点，防"关了又弹"疯狂点击；
- 限次：单次扫描最多关 MAX_CLOSE_PER_SCAN 个，防嵌套弹窗无限关闭；
- 兜底：扫描只读不抛——任何异常都只记日志，绝不影响用例真实结果；
- 开关：环境变量 POPUP_AUTO_CLOSE=0 可整体停用。
"""
import os
import time
from configparser import ConfigParser

import allure

# 配置文件（与平台 config/ 目录同源，沿用「默认值 < conf 文件 < 环境变量」优先级）
_POPUP_CONF = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           'config', 'popup.conf')


def _conf_values():
    """读 config/popup.conf 的 [popup] 段；文件缺失/段缺失返回空 dict。"""
    try:
        cp = ConfigParser()
        cp.read(_POPUP_CONF, encoding='utf-8')
        return dict(cp.items('popup')) if cp.has_section('popup') else {}
    except Exception:
        return {}


def _int_env(name, conf, key, default):
    raw = os.environ.get(name) or str(conf.get(key, '') or '')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _float_env(name, conf, key, default):
    raw = os.environ.get(name) or str(conf.get(key, '') or '')
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


MAX_CLOSE_PER_SCAN = 2      # 单次扫描最多关闭的弹窗数（防嵌套弹窗）；可被 conf/环境变量覆盖
POLL_INTERVAL = 0.3         # 元素等待轮询间隔（秒），与 popup 扫描共用节奏
MIN_SCAN_INTERVAL = 1.2     # 相邻两次全量扫描的最小间隔（秒）：扫描本身有成本（N 次 find_elements），
                            # 轮询每 0.3s 一轮，节流后大多数轮次只做目标查找，不拖慢 toast 等短生命周期元素


class PopupHandler:

    def __init__(self, driver, logger=None):
        conf = _conf_values()
        self.max_close_per_scan = _int_env('POPUP_MAX_CLOSE_PER_SCAN', conf,
                                           'max_close_per_scan', MAX_CLOSE_PER_SCAN)
        self.min_scan_interval = _float_env('POPUP_MIN_SCAN_INTERVAL', conf,
                                            'min_scan_interval', MIN_SCAN_INTERVAL)
        # 开关：环境变量 > conf；缺省启用
        env_enabled = os.environ.get('POPUP_AUTO_CLOSE')
        if env_enabled is not None and env_enabled != '':
            self.enabled = env_enabled != '0'
        else:
            self.enabled = str(conf.get('enabled', '1')).strip().lower() not in ('0', 'false', 'no', 'off')
        self._driver = driver
        self._log = logger
        self._rules = []          # [{name, lt, lv, cooldown, activity}]
        self._last_click = {}     # 规则名 -> 上次点击时间（冷却用）
        self.close_count = {}     # 规则名 -> 累计关闭次数（观测用）
        self._load_rules()

    def _load_rules(self):
        """从元素库 PopupElements 读取规则；文件缺失/为空则整体停用（不报错）。"""
        try:
            from page_objects.app_ui.android.demoProject.elements.popupElements import PopupElements
            inst = PopupElements()
            options = getattr(PopupElements, 'RULE_OPTIONS', {})
            for name in dir(inst):
                if name.startswith('_'):
                    continue
                info = getattr(inst, name)
                if info.__class__.__name__ != 'ElementInfo':
                    continue
                opt = options.get(name, {})
                anchor = opt.get('anchor')
                self._rules.append({
                    'name': name,
                    'lt': info.locator_type,
                    'lv': info.locator_value,
                    'cooldown': opt.get('cooldown', 2),
                    'activity': opt.get('activity'),
                    'anchor': tuple(anchor) if anchor else None,
                })
        except Exception as e:
            self.enabled = False
            if self._log:
                self._log.info('弹窗规则加载失败，自动关闭停用: %s' % e)
        if self._log:
            self._log.info('弹窗自动处理已启用，规则 %d 条' % len(self._rules))

    def _current_activity(self):
        try:
            return self._driver.current_activity or ''
        except Exception:
            return ''

    def scan(self):
        """扫一轮弹窗：逐规则查找关闭按钮，可见可点就点。返回本次关闭数量。
        节流：距上次扫描不足 min_scan_interval 时直接跳过（扫描本身有成本，
        6 次 find_elements 约 1.2s，不节流会拖慢轮询、错过 toast 等短生命周期元素）。"""
        if not getattr(self, 'enabled', False) or not self._rules:
            return 0
        now = time.time()
        if now - getattr(self, '_last_scan', 0) < self.min_scan_interval:
            return 0
        self._last_scan = now
        closed = 0
        activity = None
        for rule in self._rules:
            if closed >= self.max_close_per_scan:
                break
            if now - self._last_click.get(rule['name'], 0) < rule['cooldown']:
                continue
            if rule['activity']:
                # 活动页约束：该弹窗只在特定页面出现，其他页面跳过扫描（防误关）
                if activity is None:
                    activity = self._current_activity()
                if rule['activity'] not in activity:
                    continue
            try:
                # 先找关闭按钮（无弹窗时 1 次查找即返回），命中才查锚点——把扫描成本压到最低
                elements = self._driver.find_elements(rule['lt'], rule['lv'])
            except Exception:
                continue    # 查找失败（页面刷新中）视为没弹窗
            if not elements:
                continue
            if rule.get('anchor'):
                # 特征锚点：先确认弹窗的特征元素在场上再点关闭——同一个关闭按钮 id
                # 可能被登录弹层等非弹窗界面复用，不加锚点会误关（实测踩坑：误关登录弹层）
                at, av = rule['anchor']
                try:
                    if not self._driver.find_elements(at, av):
                        continue
                except Exception:
                    continue
            for el in elements:
                try:
                    if not el.is_displayed():
                        continue
                    # 先截图存证（关闭前，弹窗还在屏上），再点关闭
                    shot_name = '自动关闭弹窗_%s' % rule['name']
                    try:
                        png = self._driver.get_screenshot_as_png()
                        allure.attach(png, name=shot_name, attachment_type=allure.attachment_type.PNG)
                    except Exception:
                        pass    # 截图失败不拦截关闭动作
                    el.click()
                    self._last_click[rule['name']] = time.time()
                    self.close_count[rule['name']] = self.close_count.get(rule['name'], 0) + 1
                    closed += 1
                    msg = '自动关闭弹窗：%s（第 %d 次）' % (rule['name'], self.close_count[rule['name']])
                    if self._log:
                        self._log.info(msg)
                    try:
                        with allure.step(msg):
                            pass
                    except Exception:
                        pass    # 不在用例上下文时 allure 不可用，忽略
                    break       # 同一规则点一个就够
                except Exception:
                    continue    # 点击失败（弹窗恰好消失等）不重试不报错
        return closed
