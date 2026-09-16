#-*- coding:utf8 -*-
# 作者 1532052420
# 创建时间 2018/01/19 22:36
# github https://github.com/1532052420

from appium.webdriver.common.touch_action import TouchAction
from appium.webdriver.common.multi_action import MultiAction
from appium.webdriver.webdriver import WebDriver
from appium.webdriver.webelement import WebElement
from common.dateTimeTool import DateTimeTool
from common.httpclient.doRequest import DoRequest
from page_objects.createElement import CreateElement
from page_objects.app_ui.locator_type import Locator_Type
from page_objects.app_ui.wait_type import Wait_Type  as Wait_By
from pojo.elementInfo import ElementInfo
from PIL import Image
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

import allure
import logging
logger = logging.getLogger('appOperator')
import base64
import time
import ujson
import os

# 操作步骤编号：日志里给每个操作标「步骤N」并分行展示（动作/详情/结果各占一行），
# 每条用例开始时由 conftest 调 reset_action_step_no() 归零
_action_step_no = 0


def _next_action_step_no():
    global _action_step_no
    _action_step_no += 1
    return _action_step_no


def reset_action_step_no():
    """重置操作步骤编号（每条用例开始时调用）"""
    global _action_step_no
    _action_step_no = 0


def _log_action_result(step_no, action, detail, ok, cost_ms=None, extra=''):
    """按步骤样式分行记录操作日志：动作/详情/结果各占一行，allure 日志附件里一眼一个步骤。"""
    lines = ['▶ 步骤%d · %s' % (step_no, action)]
    for key, value in detail:
        lines.append('   ├ %s: %s' % (key, value))
    if ok:
        cost = (' · 耗时 %dms' % cost_ms) if cost_ms is not None else ''
        lines.append('   └ ✔ 成功%s%s' % (cost, (' · ' + extra) if extra else ''))
    else:
        lines.append('   └ ✖ 失败 · %s' % extra)
    msg = '\n'.join(lines)
    if ok:
        logger.info(msg)
    else:
        logger.error(msg)

class AppOperator:
    """
    类中的element参数可以有appium.webdriver.webelement.WebElement和pojo.elementInfo.ElementInfo类型
    """

    def __init__(self,driver:WebDriver,appium_hub):
        self._doRequest=DoRequest(appium_hub)
        self._doRequest.setHeaders({'Content-Type':'application/json'})
        self._driver=driver
        self._session_id=driver.session_id
        # 获得设备支持的性能数据类型
        self._performance_types=ujson.loads(self._doRequest.post_with_form('/session/'+self._session_id+'/appium/performanceData/types').body)['value']
        # 当前窗口大小/位置：UiAutomator2 等移动端驱动不支持这两个命令（Appium 3 直接返回
        # UnknownCommand 404），而框架内部并未使用这两个属性——取不到就置空，
        # 不能让整个 session 构造在这里中断（否则所有 APP 用例在 setup 阶段即报错）。
        self._window_size=self._safe_window(self.get_window_size)
        self._window_rect=self._safe_window(self.get_window_rect)

    @staticmethod
    def _safe_window(fn):
        """调用驱动获取窗口信息，驱动不支持时返回 None 并告警（不抛异常）"""
        try:
            return fn()
        except Exception as e:
            logger.warning('获取窗口信息失败（当前驱动可能不支持，已忽略）: %s' % str(e)[:100])
            return None

    def _change_element_to_webElement_type(self,element):
        if isinstance(element, ElementInfo):
            webElement=self.getElement(element)
        elif isinstance(element,WebElement):
            webElement=element
        else:
            return element
        return webElement

    def get(self,url):
        self._driver.get(url)

    def get_current_url(self):
        return self._driver.current_url

    def getTitle(self):
        return self._driver.title

    def getText(self,element):
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            return webElement.text

    def _element_desc(self,element):
        """生成元素描述(用于日志/allure step)，如 [id:com.xxx:id/btn]"""
        locator_type=getattr(element,'locator_type','')
        locator_value=getattr(element,'locator_value','')
        return '[%s:%s]'%(locator_type,locator_value)

    def click(self,element):
        desc=self._element_desc(element)
        step_no=_next_action_step_no()
        with allure.step('点击元素 %s'%desc):
            t0=time.time()
            try:
                webElement=self._change_element_to_webElement_type(element)
                if webElement:
                    try:
                        webElement.click()
                    except StaleElementReferenceException:
                        # uiautomator2 8.x 元素缓存严格：find 与 click 之间界面刷新(如 toast 消失)会使引用失效，重定位一次再点
                        webElement=self._change_element_to_webElement_type(element)
                        if webElement:
                            webElement.click()
                _log_action_result(step_no, '点击元素', [('定位', desc)], True,
                                   cost_ms=int((time.time()-t0)*1000))
            except Exception as exc:
                _log_action_result(step_no, '点击元素', [('定位', desc)], False,
                                   extra=str(exc)[:150])
                raise
        
    def click_web_element(self,element):
        """由于混合应用存在点击无效的情况，故混合应用的点击采用selenium的tab操作确保能够正常点击

        Args:
            element (ElementInfo): [description]
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            actions = TouchAction(self._driver)
            actions.tap(webElement).perform()

    def submit(self,element):
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement.submit()

    def sendText(self,element,text):
        desc=self._element_desc(element)
        step_no=_next_action_step_no()
        with allure.step('输入 %s 「%s」'%(desc,text)):
            t0=time.time()
            try:
                webElement=self._change_element_to_webElement_type(element)
                if webElement:
                    webElement.clear()
                    webElement.send_keys(text)
                _log_action_result(step_no, '输入文本',
                                   [('目标', desc), ('内容', '「%s」' % text)],
                                   True, cost_ms=int((time.time()-t0)*1000))
            except Exception as exc:
                _log_action_result(step_no, '输入文本',
                                   [('目标', desc), ('内容', '「%s」' % text)],
                                   False, extra=str(exc)[:150])
                raise

    def is_displayed(self,element):
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            flag=webElement.is_displayed()
            return flag

    def is_enabled(self,element):
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            flag = webElement.is_enabled()
            return flag

    def is_selected(self,element):
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            flag = webElement.is_selected()
            return flag

    def select_dropDownBox_by_value(self,element,value):
        """
        适用单选下拉框
        :param element:
        :param value:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement = Select(webElement)
            webElement.select_by_value(value)

    def select_dropDownBox_by_text(self,element,text):
        """
        适用单选下拉框
        :param element:
        :param text:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement = Select(webElement)
            webElement.select_by_visible_text(text)

    def select_dropDownBox_by_index(self,element,index):
        """
        适用单选下拉框,下标从0开始
        :param element:
        :param index:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement = Select(webElement)
            webElement.select_by_index(index)

    def select_dropDownBox_by_values(self,element,values):
        """
        适用多选下拉框
        :param element:
        :param values:以数组传参
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement = Select(webElement)
            webElement.deselect_all()
            for value in values:
                webElement.select_by_value(value)

    def select_dropDownBox_by_texts(self,element,texts):
        """
        适用多选下拉框
        :param element:
        :param texts:以数组传参
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement = Select(webElement)
            webElement.deselect_all()
            for text in texts:
                webElement.select_by_visible_text(text)

    def select_dropDownBox_by_indexs(self,element,indexs):
        """
        适用多选下拉框，下标从0开始
        :param element:
        :param indexs: 以数组传参
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement = Select(webElement)
            webElement.deselect_all()
            for index in indexs:
                webElement.select_by_index(index)

    def get_window_handles(self):
        """获得窗口句柄，仅适用于web

        Returns:
            [type]: [description]
        """
        return self._driver.window_handles

    def switch_to_window(self,window_name):
        """
        仅适用于web
        :param window_name:
        :return:
        """
        self._driver.switch_to.window(window_name)

    def switch_to_frame(self,frame_reference):
        """
        仅适用于web
        :param frame_reference: 支持窗口名、frame索引、(i)frame元素
        :return:
        """
        frame_reference=self._change_element_to_webElement_type(frame_reference)
        self._driver.switch_to.frame(frame_reference)

    def page_forward(self):
        """
        仅适用于web
        :return:
        """
        self._driver.forward()

    def page_back(self):
        """
        仅适用于web
        :return:
        """
        self._driver.back()

    def web_alert(self,action_type='accept'):
        """
        仅适用于web
        :action_type accept、dismiss
        :return:
        """
        if action_type:
            action_type.lower()
        alert = self._driver.switch_to.alert
        if action_type=='accept':
            alert.accept()
        elif action_type=='dismiss':
            alert.dismiss()

    def get_alert_text(self):
        """
        仅适用于web
        :return:
        """
        alert=self._driver.switch_to.alert
        return alert.text
    
    def scroll_to_show(self,element,is_top_align=True):
        """
        仅适用于web,滚动页面直至元素可见
        :param element:
        :param is_top_align: 是否元素与窗口顶部对齐，否则与窗口底部对齐
        :return:
        """
        webElement = self._change_element_to_webElement_type(element)
        if webElement:
            if is_top_align:
                self._driver.execute_script("arguments[0].scrollIntoView();", webElement)
            else:
                self._driver.execute_script("arguments[0].scrollIntoView(false);", webElement)

    def get_screenshot(self,fileName):
        fileName=DateTimeTool.getNowTime('%Y%m%d%H%M%S%f_')+fileName
        allure.attach(name=fileName,body=self._driver.get_screenshot_as_png(),attachment_type=allure.attachment_type.PNG)

    def refresh(self):
        self._driver.refresh()

    def uploadFile(self,element,filePath):
        """
        仅适用于web
        适用于元素为input且type="file"的文件上传
        :param element:
        :param filePath:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            webElement.send_keys(os.path.abspath(filePath))

    def switch_to_parent_frame(self):
        """
        切换到父frame(仅适用于web)
        :return:
        """
        self._driver.switch_to.parent_frame()

    def get_property(self,element,property_name):
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            return webElement.get_property(property_name)

    def get_attribute(self,element,attribute_name):
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            return webElement.get_attribute(attribute_name)

    def get_element_outer_html(self,element):
        return self.get_attribute(element,'outerHTML')

    def get_element_inner_html(self, element):
        return self.get_attribute(element,'innerHTML')

    def get_page_source(self):
        """
        获得app的层次结构xml，web页面源码
        """
        return self._driver.page_source

    def get_element_rgb(self,element,x_percent=0,y_percent=0):
        """
        获得元素上的rgb值,默认返回元素左上角坐标轴
        :param element
        :param x_percent x轴百分比位置,范围0~1
        :param y_percent y轴百分比位置,范围0~1
        """
        img = Image.open(self.save_element_image(element,'element_rgb'))
        pix = img.load()
        width = img.size[0]
        height = img.size[1]
        point_rgb=pix[width * x_percent, height * y_percent]
        point_rgb=point_rgb[:3]
        return point_rgb

    def save_element_image(self,element,image_file_name):
        """
        截取元素图片
        :param image_file_name: 保存图片的文件名
        :return: 图片存储的路径
        """
        webElement = self._change_element_to_webElement_type(element)
        webElement_x=webElement.location['x']
        webElement_y = webElement.location['y']
        webElement_width=webElement.size['width']
        webElement_height=webElement.size['height']
        window_x=self._window_rect['x']
        window_y=self._window_rect['y']
        window_width=self._window_rect['width']
        window_height=self._window_rect['height']
        left_percent=webElement_x/window_width
        top_percent=webElement_y/window_height
        right_percent=(webElement_x+webElement_width)/window_width
        bottom_percent=(webElement_y+webElement_height)/window_height
        # 进行屏幕截图
        image_file_name = DateTimeTool.getNowTime('%Y%m%d%H%M%S%f_') + '%s.png'%image_file_name
        if not os.path.exists('output/tmp/'):
            os.mkdir('output/tmp/')
        image_file_name = os.path.abspath('output/tmp/' + image_file_name)
        self._driver.get_screenshot_as_file(image_file_name)
        img = Image.open(image_file_name)
        # 裁切应用区域图片并保存
        img = img.crop((window_x,window_y,window_x+window_width,window_y+window_height))
        img.save(image_file_name)
        img_size=img.size
        img_width=img_size[0]
        img_height=img_size[1]
        # 裁切元素区域图片并保存
        img = img.crop((left_percent*img_width, top_percent*img_height, right_percent*img_width, bottom_percent*img_height))
        img.save(image_file_name)
        return image_file_name

    def get_captcha(self,element,language='eng'):
        """
        识别图片验证码，如需使用该方法必须配置jpype1、字体库等依赖环境
        :param element: 验证码图片元素
        :param language: eng:英文,chi_sim:中文
        :return:
        """
        # 识别图片验证码
        from common.captchaRecognitionTool import CaptchaRecognitionTool
        captcha_image_file_name=self.save_element_image(element,'captcha')
        captcha=CaptchaRecognitionTool.captchaRecognition(captcha_image_file_name,language)
        captcha=captcha.strip()
        captcha=captcha.replace(' ','')
        return captcha

    def get_table_data(self,element,data_type='text'):
        """
        以二维数组返回表格每一行的每一列的数据[[row1][row2][colume1,clume2]]
        :param element:
        :param data_type: text-返回表格文本内容,html-返回表格html内容,webElement-返回表格元素
        :return:
        """
        if isinstance(element, ElementInfo):
            # 由于表格定位经常会出现【StaleElementReferenceException: Message: stale element reference: element is not attached to the page document 】异常错误,
            # 解决此异常只需要用显示等待，保证元素存在即可，显示等待类型中visibility_of_all_elements_located有实现StaleElementReferenceException异常捕获,
            # 所以强制设置表格定位元素时使用VISIBILITY_OF
            element.wait_type=Wait_By.VISIBILITY_OF
            webElement = self.getElement(element)
        elif isinstance(element,WebElement):
            webElement = element
        else:
            return None
        table_data = []
        table_trs = webElement.find_elements(By.TAG_NAME, 'tr')
        try:
            for tr in table_trs:
                tr_data=[]
                tr_tds = tr.find_elements(By.TAG_NAME, 'td')
                if data_type.lower()=='text':
                    for td in tr_tds:
                        tr_data.append(td.text)
                elif data_type.lower()=='html':
                    for td in tr_tds:
                        tr_data.append(td.get_attribute('innerHTML'))
                elif data_type.lower()=='webelement':
                    tr_data=tr_tds
                table_data.append(tr_data)
        except StaleElementReferenceException as e:
                print('获取表格内容异常:' + e.msg)
        return table_data

    def get_window_size(self):
        return self._driver.get_window_size()
    
    def get_window_rect(self):
        return self._driver.get_window_rect()

    def app_alert(self, platformName,action_type='accept',buttonLabel=None):
        """
        仅适用于app
        :platformName android、ios
        :action_type accept、dismiss
        :buttonLabel
        :return:
        """
        if action_type:
            action_type.lower()
        if platformName:
            platformName.lower()
        script=None
        script_arg={}
        if buttonLabel:
            script_arg.update({'buttonLabel': buttonLabel})
        if platformName=='android':
            # 仅支持UiAutomator2
            if action_type == 'accept':
                script = 'mobile:acceptAlert'
            elif action_type == 'dismiss':
                script = 'mobile:dismissAlert'
        elif platformName=='ios':
            # 仅支持XCUITest
            script='mobile:alert'
            script_arg.update({'action':action_type})
        self._driver.execute_script(script,script_arg)

    def is_toast_visible(self, text, platformName='android', automationName='UiAutomator2', isRegexp=False, wait_seconds=5):
        """
        仅支持Android
        :param text:
        :param platformName: android、ios
        :param automationName: 支持UiAutomator2、Espresso
        :param isRegexp: 仅当automaitionName为Espresso时有效
        :return:
        """
        if not text:
            return False
        if 'android' == platformName.lower():
            if 'uiautomator2' == automationName.lower():
                with allure.step('检查 toast「%s」(最多等%ds)'%(text,wait_seconds)):
                    toast_element = CreateElement.create(Locator_Type.XPATH, ".//*[contains(@text,'%s')]" % text, None,
                                                         Wait_By.PRESENCE_OF_ELEMENT_LOCATED, wait_seconds=wait_seconds)
                    try:
                        self.getElement(toast_element)
                        logger.info('toast「%s」出现'%text)
                        return True
                    except:
                        return False
            elif 'espresso' == automationName.lower():
                script_arg = {'text': text}
                if isRegexp:
                    script_arg.update({'isRegexp': True})
                script = 'mobile:isToastVisible'
                return self._driver.execute_script(script, script_arg)
        elif 'ios' == platformName.lower():
            return False

    def assert_true_with_shot(self, desc, ok, fail_msg=''):
        """
        断言并对结果截图存证(入 allure)：通过截成功图；失败截失败图后抛 AssertionError
        :param desc: 断言描述，如「断言登录成功」
        :param ok: 断言结果(真值)
        :param fail_msg: 失败时的补充说明
        """
        step_no=_next_action_step_no()
        if ok:
            with allure.step('断言：「%s」'%desc):
                self.get_screenshot('断言成功_%s'%desc)
            _log_action_result(step_no, '断言「%s」'%desc, [], True, extra='成功截图已入 allure')
            return True
        with allure.step('断言失败：「%s」 %s'%(desc,fail_msg)):
            self.get_screenshot('断言失败_%s'%desc)
        _log_action_result(step_no, '断言「%s」'%desc, [], False,
                           extra='%s（失败截图已入 allure）'%fail_msg)
        raise AssertionError('断言「%s」失败：%s'%(desc,fail_msg))

    def get_geolocation(self):
        """
        返回定位信息,纬度/经度/高度
        :return:
        """
        httpResponseResult=self._doRequest.get('/session/'+self._session_id+'/location')
        return httpResponseResult.body

    def set_geolocation(self,latitude,longitude,altitude):
        """
        设置定位信息
        :param latitude: 纬度 -90 ~ 90
        :param longitude: 精度 ~180 ~ 180
        :param altitude: 高度
        :return:
        """
        geolocation={}
        location={}
        location.update({'latitude':latitude})
        location.update({'longitude':longitude})
        location.update({'altitude':altitude})
        geolocation.update({'location':location})
        self._doRequest.post_with_form('/session/'+self._session_id+'/location',params=ujson.dumps(geolocation))

    def start_activity(self,package_name,activity_name):
        """
        启动Android的activity
        """
        self._driver.start_activity(package_name,activity_name)

    def get_current_activity(self):
        """
        获得Android的activity
        :return:
        """
        return self._driver.current_activity

    def get_current_package(self):
        """
        获得Android的package
        :return:
        """
        return self._driver.current_package

    def execute_javascript(self,script):
        """
        仅适用于web
        :param script:
        :return:
        """
        self._driver.execute_script(script)

    def install_app(self,filePath):
        self._driver.install_app(os.path.abspath(filePath))

    def remove_app(self,app_id):
        self._driver.remove_app(app_id)

    def launch_app(self):
        # Appium 2+/3+ 移除了 /appium/app/launch 端点，等价实现为 activate_app
        app_package = self._driver.capabilities.get('appPackage')
        if app_package:
            return self._driver.activate_app(app_package)
        return self._driver.launch_app()

    def reset_app(self):
        """
        重置app，可以进入下一轮app测试
        Appium 2+/3+ 移除了 W3C /reset 端点，等价实现：停 app + 清数据；
        mobile:clearApp 不可用(如旧版 Appium 1.x 的 uiautomator2 driver)时回退 adb pm clear
        :return:
        """
        app_package = self._driver.capabilities.get('appPackage')
        if app_package:
            try:
                self._driver.terminate_app(app_package)
            except Exception:
                pass
            try:
                return self._driver.execute_script('mobile: clearApp', {'appId': app_package})
            except Exception:
                udid = self._driver.capabilities.get('udid') or ''
                cmd = ['adb']
                if udid:
                    cmd += ['-s', udid]
                cmd += ['shell', 'pm', 'clear', app_package]
                import subprocess
                return subprocess.run(cmd, capture_output=True, timeout=30).stdout
        return self._driver.reset()

    def close_app(self):
        # Appium 2+/3+ 移除了 /appium/app/close 端点，等价实现为 terminate_app
        app_package = self._driver.capabilities.get('appPackage')
        if app_package:
            return self._driver.terminate_app(app_package)
        return self._driver.close_app()

    def background_app(self,seconds):
        """
        后台运行
        :param seconds: -1代表完全停用
        :return:
        """
        self._driver.background_app(seconds)

    def activate_app(self,app_id):
        """
        :param app_id: IOS是bundleId，Android是Package名
        """
        self._driver.activate_app(app_id)

    def terminate_app(self,app_id,timeout=None):
        """
        :param app_id IOS是bundleId，Android是Package名
        :param timeout 重试超时时间，仅支持Android
        """
        if timeout:
            self._driver.terminate_app(app_id,timeout=timeout)
        else:
            self._driver.terminate_app(app_id)

    def get_app_state(self,app_id):
        """
        :param app_id IOS是bundleId，Android是Package名
        :return: 0:未安装,1:不在运行,2:在后台运行或者挂起,3:在后台运行,4:在前台运行
        """
        return self._driver.query_app_state(app_id)

    def get_clipboard(self):
        return self._driver.get_clipboard()

    def set_clipboard(self,text):
        self._driver.set_clipboard(text)

    def push_file_to_device(self,device_filePath,local_filePath):
        """
        上传文件设备
        :param device_filePath:
        :param local_filePath:
        :return:
        """
        local_filePath=os.path.abspath(local_filePath)
        with open(local_filePath,'rb') as f:
            data=base64.b64encode(f.read())
            f.close()
        self._driver.push_file(device_filePath,data)

    def pull_file_from_device(self,device_filePath,local_filePath):
        """
        从设备上下载文件
        :param device_filePath:
        :param local_filePath:
        :return:
        """
        local_filePath = os.path.abspath(local_filePath)
        data=self._driver.pull_file(device_filePath)
        with open(local_filePath,'wb') as f:
            f.write(base64.b64decode(data))
            f.close()

    def shake_device(self):
        """
        仅支持IOS,详见https://github.com/appium/appium/blob/master/docs/en/commands/device/interactions/shake.md
        :return:
        """
        self._driver.shake()

    def lock_screen(self,seconds=None):
        self._driver.lock(seconds)

    def unlock_screen(self):
        self._driver.unlock()

    def press_keycode(self,keycode):
        """
        按键盘按键，仅支持Android
        :param keycode: 键盘上每个按键的ascii
        :return:
        """
        self._driver.press_keycode(keycode)

    def long_press_keycode(self,keycode):
        """
        长按键盘按键，仅支持Android
        :param keycode:
        :return:
        """
        self._driver.long_press_keycode(keycode)

    def hide_keyboard(self,key_name = None, key = None, strategy = None):
        """
        隐藏键盘,ios需要指定key_name或strategy,Android无需参数
       :param key_name:
        :param key:
        :param strategy:
        :return:
        """
        self._driver.hide_keyboard(key_name,key,strategy)

    def is_keyboard_shown(self):
        """
        查询键盘是否可见(仅App可用)
        :return:
        """
        return self._driver.is_keyboard_shown()

    def toggle_airplane_mode(self):
        """
        切换飞行模式(开启关闭),仅支持Android
        :return:
        """
        self._doRequest.post_with_form('/session/'+self._session_id+'/appium/device/toggle_airplane_mode')

    def toggle_data(self):
        """
        切换蜂窝数据模式(开启关闭),仅支持Android
        :return:
        """
        self._doRequest.post_with_form('/session/'+self._session_id+'/appium/device/toggle_data')

    def toggle_wifi(self):
        """
        切换wifi模式(开启关闭),仅支持Android
        :return:
        """
        self._driver.toggle_wifi()

    def toggle_location_services(self):
        """
        切换定位服务模式(开启关闭),仅支持Android
        :return:
        """
        self._driver.toggle_location_services()

    def get_performance_date(self,data_type,package_name=None,data_read_timeout=10):
        """
        获得设备性能数据
        :param package_name:
        :param data_type: cpuinfo、batteryinfo、networkinfo、memoryinfo
        :param data_read_timeout:
        :return:
        """
        if data_type in self._driver.get_performance_data_types():
            return self._driver.get_performance_data(package_name,data_type,data_read_timeout)

    def start_recording_screen(self):
        """
        默认录制为3分钟,android最大只能3分钟,ios最大只能10分钟。如果录制产生的视频文件过大无法放到手机内存里会抛异常，所以尽量录制短视频
        :return:
        """
        self._driver.start_recording_screen(forcedRestart=True)

    def stop_recording_screen(self,fileName=''):
        """
        停止录像并将视频附加到报告里
        :param fileName:
        :return:
        """
        fileName = DateTimeTool.getNowTime('%Y%m%d%H%M%S%f_') + fileName
        data=self._driver.stop_recording_screen()
        allure.attach(name=fileName, body=base64.b64decode(data), attachment_type=allure.attachment_type.MP4)

    def get_device_time(self,format=None):
        """
        获得设备时间
        :param format: eg.YYYY-MM-DD
        :return:
        """
        return self._driver.get_device_time(format)

    def get_element_location(self,element):
        """
        获得元素在屏幕的位置,x、y坐标为元素左上角
        :param element:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            return webElement.location

    def get_element_center_location(self,element):
        """
        获得元素中心的x、y坐标
        :param element:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            rect=webElement.rect
            height=rect['height']
            width=rect['width']
            x=rect['x']
            y=rect['y']
            result_x=x+width/2
            result_y=y+height/2
            return {'x':result_x,'y':result_y}

    def touch_element_left_slide(self,element,start_x_percent=0.5,start_y_percent=0.5,duration=500,edge_type='element'):
        """
        通过元素宽度、高度的百分比值的位置点击滑动到元素或者屏幕的左边缘
        :param element:
        :param start_x_percent: 相对元素宽度的百分比
        :param start_y_percent: 相对元素高度的百分比
        :param duration:
        :param edge_type: element:滑动到元素边缘,screen:滑动到屏幕边缘
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            rect=webElement.rect
            height = rect['height']
            width = rect['width']
            x = rect['x']
            y = rect['y']
            start_x = x + width * start_x_percent
            start_y = y + height * start_y_percent
            if edge_type.lower()=='element':
                end_x=x+0.01
                end_y=y+height*0.5
            elif edge_type.lower()=='screen':
                end_x = 0+0.01
                end_y = self._window_size['height'] * 0.5
            else:
                end_x=start_x
                end_y=end_x
            self._driver.swipe(start_x=start_x,start_y=start_y,end_x=end_x,end_y=end_y,duration=duration)

    def touch_element_right_slide(self,element,start_x_percent=0.5,start_y_percent=0.5,duration=500,edge_type='element'):
        """
        通过元素宽度、高度的百分比值的位置点击滑动到元素或者屏幕的右边缘
        :param element:
        :param start_x_percent: 相对元素宽度的百分比
        :param start_y_percent: 相对元素高度的百分比
        :param duration:
        :param edge_type: element:滑动到元素边缘,screen:滑动到屏幕边缘
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            rect=webElement.rect
            height = rect['height']
            width = rect['width']
            x = rect['x']
            y = rect['y']
            start_x = x + width*start_x_percent
            start_y = y + height*start_y_percent
            if edge_type.lower()=='element':
                end_x = x + width*0.99
                end_y = y + height * 0.5
            elif edge_type.lower()=='screen':
                end_x = self._window_size['width'] * 0.99
                end_y = self._window_size['height'] * 0.5
            else:
                end_x=start_x
                end_y=end_x
            self._driver.swipe(start_x=start_x,start_y=start_y,end_x=end_x,end_y=end_y,duration=duration)

    def touch_element_up_slide(self,element,start_x_percent=0.5,start_y_percent=0.5,duration=500,edge_type='element'):
        """
        通过元素宽度、高度的百分比值的位置点击滑动到元素或者屏幕的上边缘
        :param element:
        :param start_x_percent: 相对元素宽度的百分比
        :param start_y_percent: 相对元素高度的百分比
        :param duration:
        :param edge_type: element:滑动到元素边缘,screen:滑动到屏幕边缘
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            rect=webElement.rect
            height = rect['height']
            width = rect['width']
            x = rect['x']
            y = rect['y']
            start_x = x + width*start_x_percent
            start_y = y + height*start_y_percent
            if edge_type.lower()=='element':
                end_x = x + width * 0.5
                end_y = y+0.01
            elif edge_type.lower()=='screen':
                end_x = self._window_size['width'] * 0.5
                end_y = 0+0.01
            else:
                end_x=start_x
                end_y=end_x
            self._driver.swipe(start_x=start_x,start_y=start_y,end_x=end_x,end_y=end_y,duration=duration)

    def touch_element_down_slide(self,element,start_x_percent=0.5,start_y_percent=0.5,duration=500,edge_type='element'):
        """
        通过元素宽度、高度的百分比值的位置点击滑动到元素或者屏幕的下边缘
        :param element:
        :param start_x_percent: 相对元素宽度的百分比
        :param start_y_percent: 相对元素高度的百分比
        :param duration:
        :param edge_type: element:滑动到元素边缘,screen:滑动到屏幕边缘
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            rect=webElement.rect
            height = rect['height']
            width = rect['width']
            x = rect['x']
            y = rect['y']
            start_x = x + width*start_x_percent
            start_y = y + height*start_y_percent
            if edge_type.lower()=='element':
                end_x = x + width * 0.5
                end_y = y + height*0.99
            elif edge_type.lower()=='screen':
                end_x = self._window_size['width'] * 0.5
                end_y = self._window_size['height'] * 0.99
            else:
                end_x=start_x
                end_y=end_x
            self._driver.swipe(start_x=start_x,start_y=start_y,end_x=end_x,end_y=end_y,duration=duration)

    def touch_a_element_to_another_element_slide(self,src_element,dst_element,src_start_x_percent=0.5,src_start_y_percent=0.5,
                                                dst_end_x_percent=0.5,dst_end_y_percent=0.5,duration=500):
        """
        通过一个元素宽度、高度的百分比值的位置点击滑动到另一个元素宽度、高度的百分比值的位置
        :param src_element: 开始的元素
        :param dst_element: 结束的元素
        :param src_start_x_percent: 相对元素宽度的百分比
        :param src_start_y_percent: 相对元素高度的百分比
        :param dst_end_x_percent: 相对元素宽度的百分比
        :param dst_end_y_percent: 相对元素高度的百分比
        :return:
        """
        if src_start_x_percent>=1:
            src_start_x_percent=0.99
        if src_start_y_percent>=1:
            src_start_y_percent=0.99
        if dst_end_x_percent>=1:
            dst_end_x_percent=0.99
        if dst_end_y_percent>=1:
            dst_end_y_percent=0.99
        src_webElement=self._change_element_to_webElement_type(src_element)
        dst_webElement = self._change_element_to_webElement_type(dst_element)
        if src_webElement and dst_webElement:
            src_rect=src_webElement.rect
            src_height = src_rect['height']
            src_width = src_rect['width']
            src_x = src_rect['x']
            src_y = src_rect['y']
            dst_rect=dst_webElement.rect
            dst_height = dst_rect['height']
            dst_width = dst_rect['width']
            dst_x = dst_rect['x']
            dst_y = dst_rect['y']
            # 计算位置
            start_x=src_x+src_width*src_start_x_percent
            start_y=src_y+src_height*src_start_y_percent
            end_x=dst_x+dst_width*dst_end_x_percent
            end_y=dst_y+dst_height*dst_end_y_percent
            self._driver.swipe(start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y, duration=duration)

    def touch_a_element_move_to_another_element(self, src_element, dst_element, src_start_x_percent=0.5,
                                                src_start_y_percent=0.5,
                                                dst_end_x_percent=0.5, dst_end_y_percent=0.5, long_press=True,
                                                duration=0):
        """
        通过一个元素宽度、高度的百分比值的位置点击移动到另一个元素宽度、高度的百分比值的位置
        :param src_element: 开始的元素
        :param dst_element: 结束的元素
        :param src_start_x_percent: 相对元素宽度的百分比
        :param src_start_y_percent: 相对元素高度的百分比
        :param dst_end_x_percent: 相对元素宽度的百分比
        :param dst_end_y_percent: 相对元素高度的百分比
        :param long_press: 是否长按
        :param duration: 耗时
        :return:
        """
        if src_start_x_percent >= 1:
            src_start_x_percent = 0.99
        if src_start_y_percent >= 1:
            src_start_y_percent = 0.99
        if dst_end_x_percent >= 1:
            dst_end_x_percent = 0.99
        if dst_end_y_percent >= 1:
            dst_end_y_percent = 0.99
        src_webElement = self._change_element_to_webElement_type(src_element)
        dst_webElement = self._change_element_to_webElement_type(dst_element)
        if src_webElement and dst_webElement:
            src_rect = src_webElement.rect
            src_height = src_rect['height']
            src_width = src_rect['width']
            src_x = src_rect['x']
            src_y = src_rect['y']
            dst_rect = dst_webElement.rect
            dst_height = dst_rect['height']
            dst_width = dst_rect['width']
            dst_x = dst_rect['x']
            dst_y = dst_rect['y']
            # 计算位置
            start_x = src_x + src_width * src_start_x_percent
            start_y = src_y + src_height * src_start_y_percent
            end_x = dst_x + dst_width * dst_end_x_percent
            end_y = dst_y + dst_height * dst_end_y_percent
            self.touch_move_to(start_x, start_y, end_x, end_y, long_press, duration)

    def touch_a_element_drag_to_another_element(self, src_element, dst_element, src_start_x_percent=0.5,
                                                src_start_y_percent=0.5,
                                                dst_end_x_percent=0.5, dst_end_y_percent=0.5, duration=0.5):
        """
        【仅适用IOS】通过一个元素宽度、高度的百分比值的位置点击拖拽到另一个元素宽度、高度的百分比值的位置
        :param src_element: 开始的元素
        :param dst_element: 结束的元素
        :param src_start_x_percent: 相对元素宽度的百分比
        :param src_start_y_percent: 相对元素高度的百分比
        :param dst_end_x_percent: 相对元素宽度的百分比
        :param dst_end_y_percent: 相对元素高度的百分比
        :return:
        """
        if src_start_x_percent >= 1:
            src_start_x_percent = 0.99
        if src_start_y_percent >= 1:
            src_start_y_percent = 0.99
        if dst_end_x_percent >= 1:
            dst_end_x_percent = 0.99
        if dst_end_y_percent >= 1:
            dst_end_y_percent = 0.99
        src_webElement = self._change_element_to_webElement_type(src_element)
        dst_webElement = self._change_element_to_webElement_type(dst_element)
        if src_webElement and dst_webElement:
            src_rect = src_webElement.rect
            src_height = src_rect['height']
            src_width = src_rect['width']
            src_x = src_rect['x']
            src_y = src_rect['y']
            dst_rect = dst_webElement.rect
            dst_height = dst_rect['height']
            dst_width = dst_rect['width']
            dst_x = dst_rect['x']
            dst_y = dst_rect['y']
            # 计算位置
            start_x = src_x + src_width * src_start_x_percent
            start_y = src_y + src_height * src_start_y_percent
            end_x = dst_x + dst_width * dst_end_x_percent
            end_y = dst_y + dst_height * dst_end_y_percent
            self._driver.execute_script("mobile:dragFromToForDuration",
                                        {"duration": duration, "element": None, "fromX": start_x, "fromY": start_y,
                                         "toX": end_x, "toY": end_y})

    def get_element_size_in_pixels(self,element):
        """
        返回元素的像素大小
        :param element:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            return webElement.size

    def get_all_contexts(self):
        """
        获得能够自动化测所有上下文(混合应用中的原生应用和web应用)
        :return:
        """
        return self._driver.contexts

    def get_current_context(self):
        """
        获得当前appium中正在运行的上下文(混合应用中的原生应用和web应用)
        :return:
        """
        return self._driver.current_context

    def switch_context(self,context_name):
        """
        切换上下文(混合应用中的原生应用和web应用)
        :param context_name:
        :return:
        """
        context={}
        context.update({'name':context_name})
        self._doRequest.post_with_form('/session/'+self._session_id+'/context',params=ujson.dumps(context))

    def mouse_move_to(self,element,xoffset=None,yoffset=None):
        """
        移动鼠标到指定位置(仅适用于Windows、mac)
        1、如果xoffset和yoffset都None,则鼠标移动到指定元素的正中间
        2、如果element、xoffset和yoffset都不为None,则根据元素的左上角做x和y的偏移移动鼠标
        :param element:
        :param xoffset:
        :param yoffset:
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if element:
            actions = ActionChains(self._driver)
            if xoffset and yoffset:
                actions.move_to_element_with_offset(webElement,xoffset,yoffset)
            actions.move_to_element(webElement)
            actions.perform()

    def mouse_click(self):
        """
        点击鼠标当前位置(仅适用于Windows、mac)
        :return:
        """
        actions = ActionChains(self._driver)
        actions.click()
        actions.perform()

    def mouse_double_click(self):
        """
        双击鼠标当前位置(仅适用于Windows、mac)
        :return:
        """
        actions = ActionChains(self._driver)
        actions.double_click()
        actions.perform()

    def mouse_click_and_hold(self):
        """
        长按鼠标(仅适用于Windows、mac)
        :return:
        """
        actions = ActionChains(self._driver)
        actions.click_and_hold()
        actions.perform()

    def mouse_release_click_and_hold(self):
        """
        停止鼠标长按(仅适用于Windows、mac)
        :return:
        """
        actions = ActionChains(self._driver)
        actions.release()
        actions.perform()

    def touch_move_to(self,start_x,start_y,end_x,end_y,long_press=True,duration=0):
        """
        点击从一个点移动到另外一个点
        :param start_x:
        :param start_y:
        :param end_x:
        :param end_y:
        :param long_press: 是否长按
        :param duration: 为0时不会出现惯性滑动
        :return:
        """
        if long_press:
            action = TouchAction(self._driver)
            action.long_press(x=start_x,y=start_y,duration=duration).move_to(x=end_x,y=end_y).release().perform()
        else:
            actions = TouchAction(self._driver)
            actions.press(x=start_x, y=start_y).wait(duration)
            actions.move_to(x=end_x, y=end_y)
            actions.perform()
            
    def tap(self,x:float,y:float,duration=None):
        """点击坐标

        Args:
            x (float):
            y (float):
            duration ([type], optional): [description]. Defaults to None.
        """
        step_no=_next_action_step_no()
        with allure.step('点击坐标 (%s, %s)'%(x,y)):
            t0=time.time()
            try:
                self._driver.tap([(x,y)],duration)
                _log_action_result(step_no, '点击坐标', [('坐标', '(%s, %s)' % (x, y))],
                                   True, cost_ms=int((time.time()-t0)*1000))
            except Exception as exc:
                _log_action_result(step_no, '点击坐标', [('坐标', '(%s, %s)' % (x, y))],
                                   False, extra=str(exc)[:150])
                raise

    def touch_tap(self,element,xoffset=None,yoffset=None,count=1,is_perfrom=True):
        """
        触屏点击
        1、如果xoffset和yoffset都None,则在指定元素的正中间进行点击
        2、如果element、xoffset和yoffset都不为None,则根据元素的左上角做x和y的偏移然后进行点击
        :param element:
        :param xoffset:
        :param yoffset:
        :param count: 点击次数
        :param is_perfrom 是否马上执行动作,不执行可以返回动作给多点触控执行
        :return:
        """
        webElement=self._change_element_to_webElement_type(element)
        if webElement:
            actions=TouchAction(self._driver)
            actions.tap(webElement,xoffset,yoffset,count)
            if is_perfrom:
                actions.perform()
            return actions

    def touch_long_press(self,element,xoffset=None,yoffset=None,duration_sconds=10,is_perfrom=True):
        """
        触屏长按
        1、如果xoffset和yoffset都None,则在指定元素的正中间进行长按
        2、如果element、xoffset和yoffset都不为None,则根据元素的左上角做x和y的偏移然后进行长按
        :param element:
        :param xoffset:
        :param yoffset:
        :param duration_sconds: 长按秒数
        :param is_perfrom 是否马上执行动作,不执行可以返回动作给多点触控执行
        :return:
        """
        webElement = self._change_element_to_webElement_type(element)
        if webElement:
            actions = TouchAction(self._driver)
            actions.long_press(webElement,xoffset,yoffset,duration_sconds*1000)
            if is_perfrom:
                actions.perform()
            return actions

    def multi_touch_actions_perform(self,touch_actions):
        """
        多点触控执行
        :param touch_actions:
        :return:
        """
        multiActions=MultiAction(self._driver)
        for actions in touch_actions:
            multiActions.add(actions)
        multiActions.perform()

    def touch_slide(self,start_element=None,start_x=None, start_y=None, end_element=None,end_x=None, end_y=None, duration=None):
        """
        滑动屏幕,在指定时间内从一个位置滑动到另外一个位置
        1、如果start_element不为None,则从元素的中间位置开始滑动
        2、如果end_element不为None,滑动结束到元素的中间位置
        :param start_element:
        :param end_element:
        :param start_x:
        :param start_y:
        :param end_x:
        :param end_y:
        :param duration: 毫秒
        :return:
        """
        start_webElement=self._change_element_to_webElement_type(start_element)
        end_webElement=self._change_element_to_webElement_type(end_element)
        if start_webElement:
            start_webElement_location=self.get_element_location(start_webElement)
            start_x=start_webElement_location['x']
            start_y=start_webElement_location['y']
        if end_webElement:
            end_webElement_location=self.get_element_location(end_webElement)
            end_x=end_webElement_location['x']
            end_y=end_webElement_location['y']
        self._driver.swipe(start_x,start_y,end_x,end_y,duration)

    def touch_left_slide(self,start_x_percent=0.5,start_y_percent=0.5,duration=500):
        """
        通过屏幕宽度、高度的百分比值的位置点击滑动到元素的左边缘
        :param element:
        :param start_x_percent: 相对屏幕宽度的百分比
        :param start_y_percent: 相对屏幕高度的百分比
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        start_x=self._window_size['width']*start_x_percent
        start_y=self._window_size['height']*start_y_percent
        end_x=0
        end_y=self._window_size['height']*0.5
        self._driver.swipe(start_x,start_y,end_x,end_y,duration)

    def touch_right_slide(self,start_x_percent=0.5,start_y_percent=0.5,duration=500):
        """
        通过屏幕宽度、高度的百分比值的位置点击滑动到元素的右边缘
        :param element:
        :param start_x_percent: 相对屏幕宽度的百分比
        :param start_y_percent: 相对屏幕高度的百分比
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        start_x=self._window_size['width']*start_x_percent
        start_y=self._window_size['height']*start_y_percent
        end_x=self._window_size['width']*0.99
        end_y=self._window_size['height']*0.5
        self._driver.swipe(start_x,start_y,end_x,end_y,duration)

    def touch_up_slide(self,start_x_percent=0.5,start_y_percent=0.5,duration=500):
        """
        通过屏幕宽度、高度的百分比值的位置点击滑动到元素的上边缘
        :param element:
        :param start_x_percent: 相对屏幕宽度的百分比
        :param start_y_percent: 相对屏幕高度的百分比
        :return:
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        start_x=self._window_size['width']*start_x_percent
        start_y=self._window_size['height']*start_y_percent
        end_x=self._window_size['width']*0.5
        end_y=0
        self._driver.swipe(start_x,start_y,end_x,end_y,duration)

    def touch_down_slide(self,start_x_percent=0.5,start_y_percent=0.5,duration=500):
        """
        通过屏幕宽度、高度的百分比值的位置点击滑动到元素的下边缘
        :param element:
        :param start_x_percent: 相对屏幕宽度的百分比
        :param start_y_percent: 相对屏幕高度的百分比
        :return:
        :return:
        """
        if start_x_percent>=1:
            start_x_percent=0.99
        if start_y_percent>=1:
            start_y_percent=0.99
        start_x=self._window_size['width']*start_x_percent
        start_y=self._window_size['height']*start_y_percent
        end_x=self._window_size['width']*0.5
        end_y=self._window_size['height']*0.99
        self._driver.swipe(start_x,start_y,end_x,end_y,duration)

    def getElement(self,elementInfo):
        """
        定位单个元素
        :param elementInfo:
        :return:
        """
        webElement=None
        locator_type=elementInfo.locator_type
        locator_value=elementInfo.locator_value
        wait_type = elementInfo.wait_type
        wait_seconds = elementInfo.wait_seconds
        wait_expected_value = elementInfo.wait_expected_value
        if wait_expected_value:
            wait_expected_value = wait_expected_value

        # 查找元素,为了保证元素被定位,都进行显式等待。
        # 等待超时时 selenium 原生 TimeoutException 会把 Appium 服务端 JS 堆栈整段拼进消息，
        # allure 步骤里全是噪声，统一在这里精简成一句人话（保留定位器与等待时长）
        try:
            if wait_type == Wait_By.TITLE_IS:
                webElement = WebDriverWait(self._driver, wait_seconds).until(expected_conditions.title_is(wait_expected_value))
            elif wait_type == Wait_By.TITLE_CONTAINS:
                webElement = WebDriverWait(self._driver, wait_seconds).until(expected_conditions.title_contains(wait_expected_value))
            elif wait_type == Wait_By.PRESENCE_OF_ELEMENT_LOCATED:
                webElement = WebDriverWait(self._driver, wait_seconds).until(expected_conditions.presence_of_element_located((locator_type, locator_value)))
            elif wait_type == Wait_By.ELEMENT_TO_BE_CLICKABLE:
                webElement = WebDriverWait(self._driver, wait_seconds).until(expected_conditions.element_to_be_clickable((locator_type, locator_value)))
            elif wait_type == Wait_By.ELEMENT_LOCATED_TO_BE_SELECTED:
                webElement = WebDriverWait(self._driver, wait_seconds).until(expected_conditions.element_located_to_be_selected((locator_type, locator_value)))
            elif wait_type == Wait_By.VISIBILITY_OF:
                webElements = WebDriverWait(self._driver,wait_seconds).until((expected_conditions.visibility_of_all_elements_located((locator_type,locator_value))))
                if len(webElements)>0:
                    webElement=webElements[0]
            else:
                # selenium4 移除了 find_element_by_*；locator_type 的值与 By/AppiumBy 常量字符串一致，统一走 find_element(by, value)
                webElement = WebDriverWait(self._driver,wait_seconds).until(lambda driver:driver.find_element(locator_type, locator_value))
            return webElement
        except TimeoutException:
            raise TimeoutException('等待元素超时(%ss)：%s 元素未找到' % (wait_seconds, self._element_desc(elementInfo))) from None

    def getElements(self,elementInfo):
        """
        定位多个元素
        :param elementInfo:
        :return:
        """
        webElements=None
        locator_type=elementInfo.locator_type
        locator_value=elementInfo.locator_value
        wait_type = elementInfo.wait_type
        wait_seconds = elementInfo.wait_seconds

        # 查找元素,为了保证元素被定位,都进行显式等待（超时异常精简同 getElement）
        try:
            if wait_type == Wait_By.PRESENCE_OF_ELEMENT_LOCATED:
                webElements = WebDriverWait(self._driver, wait_seconds).until(expected_conditions.presence_of_all_elements_located((locator_type, locator_value)))
            elif wait_type == Wait_By.VISIBILITY_OF:
                webElements = WebDriverWait(self._driver, wait_seconds).until(expected_conditions.visibility_of_all_elements_located((locator_type,locator_value)))
            else:
                # selenium4 移除了 find_element_by_*；locator_type 的值与 By/AppiumBy 常量字符串一致，统一走 find_element(by, value)
                webElements = WebDriverWait(self._driver,wait_seconds).until(lambda driver:driver.find_elements(locator_type, locator_value))
            return webElements
        except TimeoutException:
            raise TimeoutException('等待元素超时(%ss)：%s 元素未找到' % (wait_seconds, self._element_desc(elementInfo))) from None

    def getSubElement(self,parent_element,sub_elementInfo):
        """
        获得元素的单个子元素
        :param parent_element: 父元素
        :param sub_elementInfo: 子元素,只能提供pojo.elementInfo.ElementInfo类型
        :return:
        """
        webElement=self._change_element_to_webElement_type(parent_element)
        if not webElement:
            return None
        if not isinstance(sub_elementInfo,ElementInfo):
            return None

        # 通过父元素查找子元素
        locator_type=sub_elementInfo.locator_type
        locator_value=sub_elementInfo.locator_value
        wait_seconds = sub_elementInfo.wait_seconds

        # 查找元素,为了保证元素被定位,都进行显式等待
        # 子元素定位同样用统一 find_element(by, value)
        subWebElement = WebDriverWait(webElement,wait_seconds).until(lambda webElement:webElement.find_element(locator_type, locator_value))
        return subWebElement

    def getSubElements(self, parent_element, sub_elementInfo):
        """
        获得元素的多个子元素
        :param parent_element: 父元素
        :param sub_elementInfo: 子元素,只能提供pojo.elementInfo.ElementInfo类型
        :return:
        """
        webElement=self._change_element_to_webElement_type(parent_element)
        if not webElement:
            return None
        if not isinstance(sub_elementInfo,ElementInfo):
            return None

        # 通过父元素查找多个子元素
        locator_type = sub_elementInfo.locator_type
        locator_value = sub_elementInfo.locator_value
        wait_seconds = sub_elementInfo.wait_seconds

        # 查找元素,为了保证元素被定位,都进行显式等待
        subWebElements = WebDriverWait(webElement,wait_seconds).until(lambda webElement:webElement.find_elements(locator_type, locator_value))
        return subWebElements

    def explicit_wait_page_title(self,elementInfo):
        """
        仅适用于web
        显式等待页面title
        :param elementInfo:
        :return:
        """
        self.getElement(elementInfo)

    def getDriver(self):
        return self._driver