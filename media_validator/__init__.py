# -*- coding: utf-8 -*-
"""媒体产物检测（Media Artifact Validator）· 独立插件模块

方案来源：《媒体产物检测插件产品方案》。检测引擎基于 vendor/rendercheck
（MIT，基于上游开源库 rendercheck v0.4.1 供应商化，改动清单见 VENDOR.md）。

本模块与自动化测试平台框架**零耦合**：不 import 任何 web_platform / element_locator
代码，自带模板、静态资源、存储与测试。对框架的全部接触点只有两处（删除即整体下线）：
1. web_platform/app.py 里的两行蓝图注册；
2. web_platform/templates/index.html 首页的一张入口卡片。

对外只暴露 bp 与 PLUGIN_VERSION。
"""
from media_validator.routes import bp

PLUGIN_VERSION = '1.0.0'

__all__ = ['bp', 'PLUGIN_VERSION']
