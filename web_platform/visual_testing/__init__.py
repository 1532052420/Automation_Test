# -*- coding: utf-8 -*-
"""视觉测试（Percy/Maestro 调研落地 · 一期本地模式）

独立模块：Maestro YAML 流程管理 + 本机运行 + 截图收集 + SSIM 三图比对。
不依赖 Percy 云端（PERCY_TOKEN 未配置也可完整使用），不与现有视觉断言/接口测试耦合，
便于后续整体抽出交付。二期规划接入 Percy CLI（app:exec 编排），三期接云端审批工作流。
"""
