# -*- coding: utf-8 -*-
"""代码调试 · pojo / base 配置读取 / API 链路检查项"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dbg_kit import check, assert_true

@check('page_objects.createElement', 'page_objects/createElement.py + pojo/elementInfo.py',
       '元素构造器：CreateElement 生成 ElementInfo 并完整回填各字段')
def _():
    from page_objects.createElement import CreateElement
    from page_objects.app_ui.locator_type import Locator_Type
    from page_objects.app_ui.wait_type import Wait_Type
    from pojo.elementInfo import ElementInfo
    info = CreateElement.create(Locator_Type.ID, 'btn_login',
                                expected_value='登录', wait_type=Wait_Type.VISIBILITY_OF,
                                wait_expected_value='可见', wait_seconds=15)
    assert_true(isinstance(info, ElementInfo), 'create 应返回 ElementInfo，实际 %r' % type(info))
    assert_true(info.locator_type == Locator_Type.ID and info.locator_value == 'btn_login', '定位字段回填异常')
    assert_true(info.expected_value == '登录' and info.wait_seconds == 15, '期望/等待字段回填异常')
    assert_true(info.wait_type == Wait_Type.VISIBILITY_OF, '等待类型回填异常')
    return 'locator=%s value=%s 等待=%s 秒数=15 全部回填正确' % (info.locator_type, info.locator_value, info.wait_type)


@check('pojo.elementInfo', 'pojo/elementInfo.py', '元素信息数据类：默认字段完整性')
def _():
    from pojo.elementInfo import ElementInfo
    e = ElementInfo()
    for attr in ('locator_type', 'locator_value', 'expected_value', 'wait_type', 'wait_expected_value', 'wait_seconds'):
        assert_true(hasattr(e, attr), '缺少字段 %s' % attr)
    return '6 个核心字段齐备'


@check('pojo.httpResponseResult', 'pojo/httpResponseResult.py', 'HTTP 响应数据类：字段结构')
def _():
    from pojo.httpResponseResult import HttpResponseResult
    r = HttpResponseResult()
    for attr in ('status_code', 'body', 'cookies', 'headers'):
        assert_true(hasattr(r, attr), '缺少字段 %s' % attr)
    return 'status_code/body/cookies/headers 齐备'


@check('base.read_report_config', 'base/read_report_config.py + pojo/report_config.py', '报告配置读取（config/report.conf）')
def _():
    from base.read_report_config import Read_Report_Config
    rc = Read_Report_Config().report_config
    assert_true(int(rc.api_port) > 0, 'api_port 异常: %r' % rc.api_port)
    assert_true(int(rc.app_ui_start_port) > 0, 'app_ui_start_port 异常: %r' % rc.app_ui_start_port)
    return 'api_port=%s app_ui_start_port=%s web_ui_chrome_port=%s' % (rc.api_port, rc.app_ui_start_port, rc.web_ui_chrome_port)


@check('base.read_app_ui_config', 'base/read_app_ui_config.py + pojo/app_ui_config.py', 'APP UI 全局配置读取（config/app_ui_config.conf）')
def _():
    from base.read_app_ui_config import Read_APP_UI_Config
    cfg = Read_APP_UI_Config().app_ui_config
    assert_true(int(cfg.max_device_pool) >= 1, 'max_device_pool 异常: %r' % getattr(cfg, 'max_device_pool', None))
    return 'max_device_pool=%s（当前配置仅此一个字段）' % cfg.max_device_pool


@check('base.read_app_ui_devices_info', 'base/read_app_ui_devices_info.py + pojo/app_ui_devices_info.py',
       '多设备配置解析（devices conf → desired_capabilities 全链路）')
def _():
    from base.read_app_ui_devices_info import Read_APP_UI_Devices_Info
    conf = 'config/demoProject/app_ui_android_devices_info_demoProject.conf'
    assert_true(os.path.exists(conf), '设备配置不存在: %s' % conf)
    devices = Read_APP_UI_Devices_Info(conf).devices_info
    assert_true(len(devices) >= 1, '未解析出设备')
    caps = devices[0]['capabilities']
    assert_true(len(caps) >= 1, '未解析出 desired_capabilities（检查 conf 的 appPackages/appActivitys/apps_dirs）')
    cap = caps[0]
    for key in ('udid', 'platformName', 'platformVersion', 'systemPort'):
        assert_true(key in cap and str(cap[key]).strip(), 'capabilities 缺少 %s' % key)
    assert_true('appPackage' in cap or 'bundleId' in cap or 'app' in cap, '缺少被测应用（appPackage/bundleId/app）')
    return '设备=%s 包名=%s activity=%s' % (
        devices[0].get('device_desc'), cap.get('appPackage', cap.get('bundleId', cap.get('app'))), cap.get('appActivity', '-'))


@check('base.read_httpserver_config', 'base/read_httpserver_config.py + pojo/httpserver_config.py', 'HTTP 服务配置读取（config/httpserver.conf）')
def _():
    from base.read_httpserver_config import Read_Http_Server_Config
    hc = Read_Http_Server_Config().httpserver_config
    assert_true(int(hc.httpserver_port) > 0, 'httpserver_port 异常: %r' % hc.httpserver_port)
    assert_true(str(getattr(hc, 'local_ip', '')).strip(), 'local_ip 为空')
    return 'httpserver_port=%s local_ip=%s' % (hc.httpserver_port, getattr(hc, 'local_ip', '-'))


@check('base.api.read_config', 'base/api/demoProject/api_demoProject_read_config.py + pojo/api/demoProjectConfig.py',
       '接口项目配置读取（test 环境）')
def _():
    from base.api.demoProject.api_demoProject_read_config import API_DemoProject_Read_Config
    cfg = API_DemoProject_Read_Config().config
    assert_true(str(cfg.url).startswith('http'), 'url 异常: %r' % cfg.url)
    assert_true(hasattr(cfg, 'init'), '缺少 init 开关字段')
    return 'url=%s init=%s（注意：当前为占位配置，真实被测服务请修改 conf）' % (cfg.url, cfg.init)


@check('base.api.db_clients', 'base/api/demoProject/api_demoProject_db_clients.py', '接口项目 DB 客户端：实例化（当前为占位实现）')
def _():
    from base.api.demoProject.api_demoProject_db_clients import API_DemoProject_DB_Clients
    db = API_DemoProject_DB_Clients()
    assert_true(db is not None, '实例化失败')
    return 'API_DemoProject_DB_Clients 可正常实例化（未配置真实数据库，属占位实现）'


@check('base.api.client', 'base/api/demoProject/api_demoProject_client.py', '接口项目客户端：实例化 + DoRequest 绑定（不发请求）')
def _():
    from base.api.demoProject.api_demoProject_client import API_DemoProject_Client
    from common.httpclient.doRequest import DoRequest
    client = API_DemoProject_Client()
    assert_true(isinstance(client.doRequest, DoRequest), 'doRequest 未绑定 DoRequest 实例')
    assert_true(client.demoProjectConfig is not None, '配置未加载')
    assert_true(client.demoProjectDBClients is not None, 'DB 客户端未初始化')
    return '客户端单例就绪，baseUrl=%s' % client.demoProjectConfig.url


@check('init.api.api_init', 'init/api/api_init.py + init/api/demoProject/demoProjectInit.py', '接口初始化链路真实执行')
def _():
    from init.api.api_init import api_init
    api_init()
    return 'api_init() 执行完成（当前 demo 项目 init 为空实现，真实项目此处应构建测试数据）'
