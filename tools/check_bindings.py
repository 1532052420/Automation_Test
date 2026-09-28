#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全库三件套引用扫描：python tools/check_bindings.py（项目根运行）。
报告悬空 import 与页面方法引用的未定义元素（元素改名/漏保存）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_platform.binding_check import scan_dangling_bindings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = scan_dangling_bindings(ROOT)
if not errors:
    print('OK：三件套引用完整，无悬空绑定')
    sys.exit(0)
print('发现 %d 处悬空绑定：' % len(errors))
for e in errors:
    print('  -', e)
sys.exit(1)
