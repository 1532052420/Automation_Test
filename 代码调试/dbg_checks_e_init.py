# -*- coding: utf-8 -*-
"""代码调试 · init 初始化链路 / 全框架导入扫描检查项"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dbg_kit import check, Skip, assert_true, setup_java_home

@check('init.java.maven', 'init/java/java_maven_init.py', 'Java 依赖初始化真实执行（mvn 依赖就绪校验，jar 已缓存时秒级）')
def _():
    setup_java_home()
    from init.java.java_maven_init import java_maven_init
    java_maven_init()
    libs = os.path.join('common', 'java', 'lib', 'java', 'libs')
    jars = [f for f in os.listdir(libs) if f.endswith('.jar')] if os.path.isdir(libs) else []
    assert_true(len(jars) >= 10, '依赖 libs 目录 jar 不足: %d' % len(jars))
    return 'java_maven_init() 执行完成，libs 目录 %d 个 jar 就绪' % len(jars)


@check('init.httpserver.config', 'init/httpserver/http_server_init.py', 'HTTP 文件服务初始化（仅配置与接口校验，不启动进程）')
def _():
    import inspect
    from init.httpserver.http_server_init import http_server_init, start_http_server
    assert_true(callable(http_server_init) and callable(start_http_server), '初始化函数缺失')
    from base.read_httpserver_config import Read_Http_Server_Config
    port = Read_Http_Server_Config().httpserver_config.httpserver_port
    assert_true(int(port) > 0, 'httpserver 端口配置异常: %r' % port)
    return 'http_server_init 就绪（端口 %s）；真实进程由 run_app_ui_test 启动，此处不重复拉起' % port


@check('init.appui.demo_project', 'init/app_ui/android/demoProject/demoProjectInit.py', 'APP 项目初始化链路真实执行（默认空实现）')
def _():
    from init.app_ui.android.demoProject.demoProjectInit import DemoProjectInit
    DemoProjectInit().init()
    return 'DemoProjectInit().init() 执行完成（当前为空实现占位）'


@check('framework.import_sweep', '全框架导入扫描', 'base/cases/common/init/page_objects/pojo 全部模块逐一 import（0 失败为目标）')
def _():
    roots = ['base', 'cases', 'common', 'init', 'page_objects', 'pojo']
    total, failed = 0, []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for fn in filenames:
                if not fn.endswith('.py'):
                    continue
                rel = os.path.join(dirpath, fn)
                dotted = rel[:-3].replace(os.sep, '.')
                if dotted.endswith('.__init__'):
                    dotted = dotted[:-9]
                total += 1
                try:
                    importlib.import_module(dotted)
                except Exception as e:
                    failed.append('%s -> %s: %s' % (rel, type(e).__name__, e))
    assert_true(not failed, '%d/%d 个模块导入失败:\n%s' % (len(failed), total, '\n'.join(failed)))
    return '%d 个框架模块全部可导入（含被测用例文件）' % total
