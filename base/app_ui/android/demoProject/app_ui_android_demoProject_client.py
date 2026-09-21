# -*- coding:utf-8 -*-
# 作者 1532052420
# 创建时间 2018/01/19 22:36
from base.app_ui.android.demoProject.app_ui_android_demoProject_read_config import APP_UI_Android_DemoProject_Read_Config
from appium import webdriver
from base.read_app_ui_config import Read_APP_UI_Config
from common.appium.appOperator import AppOperator
from common.fileTool import FileTool
from common.httpclient.doRequest import DoRequest
from init.app_ui.android.demoProject.demoProjectInit import DemoProjectInit
import os

class APP_UI_Android_demoProject_Client(object):

    __instance=None
    __inited=None

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance=object.__new__(cls)
        return cls.__instance

    def __init__(self,is_need_reset_app=False,is_need_kill_app=False):
        if self.__inited is None:
            self.__inited=True
            self.__is_first=True
            self.config = Read_APP_UI_Config().app_ui_config
            self.device_info=FileTool.readJsonFromFile('config/app_ui_tmp/'+str(os.getppid()))
            self.demoProject_config = APP_UI_Android_DemoProject_Read_Config('config/demoProject/%s'%self.device_info['app_ui_config']).config
            self.current_desired_capabilities = FileTool.readJsonFromFile('config/app_ui_tmp/' + str(os.getppid()) + '_current_desired_capabilities')
            self.fullReset = self.current_desired_capabilities['fullReset']
            self.noReset = self.current_desired_capabilities['noReset']
            self._appium_hub='http://'+self.device_info['server_ip']+':%s/wd/hub'%self.device_info['server_port']
            self._init(self.demoProject_config.init)
            self._delete_last_device_session(self.device_info['device_desc'])
            self.driver = webdriver.Remote(self._appium_hub, desired_capabilities=self.current_desired_capabilities)
            self._save_last_device_session(self.driver.session_id, self.device_info['device_desc'])
            self.appOperator = AppOperator(self.driver,self._appium_hub)
            # 平台「前置清理」（设备配置面板，经 runner 环境变量下传）：清登录态+App 数据。
            # Client 是单例，本块整轮只进一次 = 仅首条用例执行前生效；后续用例构造直接复用实例。
            if os.environ.get('AT_SETUP_RESET') == '1':
                print('[前置清理] 清 App 数据（本轮首条用例前，仅此一次）...')
                self.appOperator.reset_app()

        if is_need_reset_app:
            # appium启动是非重置或者非第一次appium启动，则要进行重置
            if self.__is_first==False or self.noReset==True:
                self.appOperator.reset_app()
        # 注：is_need_kill_app 分支原用于启动演示项目墨迹天气，已随墨迹天气清理移除；
        # 被测 App 统一在用例 setup_class 中显式 start_activity 启动

        self.__is_first=False

    @classmethod
    def instance(cls):
        """当前进程的单例（未构造返回 None）——根 conftest.py 轮末后置清理用"""
        return cls.__instance

    def _init(self,is_init=False):
        print('初始化android基础数据......')
        DemoProjectInit().init(is_init)
        print('初始化android基础数据完成......')

    def _save_last_device_session(self,session, device_desc):
        if not os.path.exists('config/app_ui_tmp'):
            os.mkdir('config/app_ui_tmp')
            with open('config/app_ui_tmp/%s_session' % device_desc, 'w') as f:
                f.write(session)
                f.close()

    def _delete_last_device_session(self,device_desc):
        if os.path.exists('config/app_ui_tmp/%s_session' % device_desc):
            with open('config/app_ui_tmp/%s_session' % device_desc, 'r') as f:
                last_session = f.read()
                last_session = last_session.strip()
                if last_session:
                    doRequest = DoRequest(self._appium_hub)
                    doRequest.setHeaders({'Content-Type': 'application/json'})
                    httpResponseResult = doRequest.delete('/session/' + last_session)
