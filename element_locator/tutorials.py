# -*- coding: utf-8 -*-
"""
GUI 元素定位器 · 右侧教学数据
结构化方式：list 套 tuple（元祖套列表），层级可折叠
  外层 list       -> 一级分类（可折叠）
  每一项是 tuple  -> (分类名, 子项list)   或   (标题, 方法签名, 一句话说明, 示例代码)
叶子固定 4 元素：标题 / 方法签名 / 一句话说明 / 完整示例代码
只讲"怎么写"，不讲原理；方法全部来自框架 common/appium/appOperator.py 真实封装

教学优先级：① 框架内置方法/工具（appOperator、AssertTool）→ ② Appium 自带常见方法
（所有示例方法名都与 appOperator.py / assertTool.py 源码逐一核对过）
"""

# 通用说明片段，用于部分示例开头
CLIENT_NOTE = "client 为用例里的客户端对象，通常已定义；appOperator = client.appOperator"

TUTORIALS = [
    ("点击 Click", [
        ("点击元素",
         "appOperator.click(元素)",
         "点击已定位到的元素（会自动等待元素出现，默认30秒）",
         "appOperator.click(client.kuaigeLoginElements.btn_phone_login)"),
        ("点击坐标",
         "appOperator.tap(x, y, duration=None)",
         "按屏幕坐标直接点击，duration 为按住时长(毫秒)",
         "appOperator.tap(360, 1400)   # 点屏幕 (360,1400)"),
        ("长按元素",
         "appOperator.touch_long_press(元素, xoffset=None, yoffset=None, duration_sconds=10)",
         "长按元素，默认长按10秒，可传坐标偏移",
         "appOperator.touch_long_press(element, duration_sconds=2)"),
        ("点击后打开的新元素", None,
         "提示：页面跳转后元素会失效，需重新定位再点击", None),
    ]),
    ("滑动 Swipe", [
        ("屏幕左滑",
         "appOperator.touch_left_slide(start_x_percent=0.5, start_y_percent=0.5, duration=500)",
         "从屏幕中心向左滑(起点用屏幕百分比，0~1)",
         "appOperator.touch_left_slide(start_y_percent=0.5)"),
        ("屏幕右滑",
         "appOperator.touch_right_slide(start_x_percent=0.5, start_y_percent=0.5, duration=500)",
         "从屏幕中心向右滑",
         "appOperator.touch_right_slide()"),
        ("屏幕上滑",
         "appOperator.touch_up_slide(start_x_percent=0.5, start_y_percent=0.5, duration=500)",
         "从屏幕中心向上滑（常用于列表上滑加载）",
         "appOperator.touch_up_slide()"),
        ("屏幕下滑",
         "appOperator.touch_down_slide(start_x_percent=0.5, start_y_percent=0.5, duration=500)",
         "从屏幕中心向下滑",
         "appOperator.touch_down_slide()"),
        ("元素滑到屏幕左边缘",
         "appOperator.touch_element_left_slide(元素, ...)",
         "以元素为起点向左滑到屏幕边缘（列表项左滑删除等）",
         "appOperator.touch_element_left_slide(element)"),
        ("元素滑到屏幕右/上/下边缘",
         "appOperator.touch_element_right_slide / touch_element_up_slide / touch_element_down_slide(元素, ...)",
         "同上，方向不同",
         "appOperator.touch_element_right_slide(element)"),
        ("两个元素间滑动",
         "appOperator.touch_a_element_to_another_element_slide(start_element, end_element, ...)",
         "从元素A滑到元素B",
         "appOperator.touch_a_element_to_another_element_slide(ele_a, ele_b)"),
        ("拖拽元素到另一元素",
         "appOperator.touch_a_element_drag_to_another_element(start_element, end_element, ...)",
         "拖拽（仅iOS适用，Android用滑动）",
         "appOperator.touch_a_element_drag_to_another_element(ele_a, ele_b)"),
        ("任意起止点滑动",
         "appOperator.touch_slide(start_element=None, start_x=None, start_y=None, end_element=None, end_x=None, end_y=None, duration=None)",
         "最全能的滑动，元素/坐标随意组合",
         "appOperator.touch_slide(start_x=500, start_y=1500, end_x=500, end_y=300, duration=1000)"),
    ]),
    ("输入 SendText", [
        ("输入文本",
         "appOperator.sendText(元素, 文本)",
         "先自动清空输入框再输入文本",
         "appOperator.sendText(elements.search_city, '北京')"),
        ("键盘回退/回车",
         "appOperator.press_keycode(KEYCODE)",
         "67=删除 66=回车 4=返回 3=首页 24/25=音量",
         "appOperator.press_keycode(66)   # 回车"),
        ("隐藏键盘",
         "appOperator.hide_keyboard()",
         "收起软键盘",
         "appOperator.hide_keyboard()"),
    ]),
    ("断言 Assert", [
        # ============ ① 框架内置：appOperator 断言方法（最优先） ============
        ("Toast 是否出现",
         "appOperator.is_toast_visible(文本, wait_seconds=5)",
         "框架内置【最常用】。返回 True/False，配合 assert 用；toast 只显示几秒，点完操作立刻断言",
         "assert appOperator.is_toast_visible('操作成功'), '未弹出\"操作成功\"toast'"),
        ("Toast 加大等待时间",
         "appOperator.is_toast_visible(文本, wait_seconds=10)",
         "慢 toast（网络请求后才弹）把 wait_seconds 加大，断言前会轮询等待",
         "assert appOperator.is_toast_visible('登录成功', wait_seconds=10)"),
        ("Toast 正则匹配",
         "appOperator.is_toast_visible(r'成功|失败', wait_seconds=5, isRegexp=True)",
         "toast 内容每次会变时用正则（isRegexp=True，仅 UiAutomator2 生效）",
         "assert appOperator.is_toast_visible(r'数据\\d+条', isRegexp=True)"),
        ("元素是否存在（出现即通过）",
         "appOperator.getElement(元素)",
         "框架内置。找不到会一直等到超时再抛异常；能拿到元素就说明它出现了 → 直接当断言用",
         "appOperator.getElement(elements.text_login_success)   # 断言\"登录成功\"文案出现"),
        ("元素是否显示",
         "appOperator.is_displayed(元素)",
         "框架内置。元素在页面上可见则 True，隐藏/被遮挡则 False",
         "assert appOperator.is_displayed(elements.start_btn), '首页按钮不可见'"),
        ("元素是否可用（可点击）",
         "appOperator.is_enabled(元素)",
         "框架内置。按钮置灰/禁用时返回 False",
         "assert appOperator.is_enabled(elements.btn_login), '登录按钮不可用'"),
        ("元素是否选中",
         "appOperator.is_selected(元素)",
         "框架内置。适合单选框/复选框/RadioButton/Tab 选中态断言",
         "assert appOperator.is_selected(elements.tab_selected), 'Tab 未选中'"),
        ("元素文本相等",
         "appOperator.getText(元素) == 期望值",
         "框架内置 getText 取元素文字，再用 Python assert 比较",
         "assert appOperator.getText(elements.page_title) == '我的', '页面标题错误'"),
        ("元素文本包含关键字",
         "预期字符串 in appOperator.getText(元素)",
         "文本长、只关心包含某几个字时用 in（比相等抗干扰）",
         "assert '登录成功' in appOperator.getText(elements.result_text)"),
        ("断言当前页面（Activity）",
         "appOperator.get_current_activity()",
         "框架内置。拿当前前台 Activity 名，断言跳转到了预期页面",
         "assert appOperator.get_current_activity() == '.feature.login.phone.PhoneLoginActivity'"),
        ("断言当前包名",
         "appOperator.get_current_package()",
         "框架内置。确认前台 App 是自己测的那个，防误切到别的 App",
         "assert appOperator.get_current_package() == 'com.recordlife.kuaige'"),
        ("元素数量断言",
         "len(appOperator.getElements(元素))",
         "框架内置。断言同 id/text 的元素个数（列表项、广告位、Tab 数量）",
         "assert len(appOperator.getElements(elements.city_btns)) == 5, '按钮数量不对'"),
        ("元素属性断言（Appium 常见）",
         "appOperator.get_attribute(元素, 'checked')",
         "Appium 方法经框架封装。可断言 text / resource-id / checked / enabled / selected / displayed 等属性",
         "assert appOperator.get_attribute(elements.agree_check, 'checked') == 'true'"),
        # ============ ① 框架内置：common/assertTool.py 工具类 ============
        ("字符串正则匹配（AssertTool）",
         "AssertTool.isRegularMatch(源字符串, 正则)",
         "框架内置工具 common/assertTool.py。判断文本是否符合正则（锚定开头），适合格式校验：手机号/邮箱/金额",
         "from common.assertTool import AssertTool\nphone = appOperator.getText(elements.et_phone)\nassert AssertTool.isRegularMatch(phone, r'^1\\d{10}$'), '手机号格式不对'"),
        ("两个文件内容是否一致（AssertTool）",
         "AssertTool.isFilesEqual(文件1, 文件2)",
         "框架内置工具。比较两个文件内容是否一样（下载校验/上传结果校验）",
         "from common.assertTool import AssertTool\nassert AssertTool.isFilesEqual('/tmp/a.pdf', '/tmp/b.pdf'), '文件不一致'"),
        ("文件大小是否一致（AssertTool）",
         "AssertTool.isFilesSizeEqual(文件1, 文件2)",
         "框架内置工具。只比大小不比内容，速度快",
         "from common.assertTool import AssertTool\nassert AssertTool.isFilesSizeEqual('/tmp/a.pdf', '/tmp/b.pdf')"),
        # ============ ② Appium 自带常见断言写法（框架已封装的优先用上面的） ============
        ("Appium：page_source 包含关键字",
         "'关键字' in appOperator.get_page_source()",
         "兜底断言：把整个页面 XML 拿来做关键字包含判断，元素难定位时的最后手段",
         "assert '登录成功' in appOperator.get_page_source(), '页面源码中没有该文字'"),
        ("Appium：driver 直接断言元素",
         "driver.find... .text / .is_displayed()",
         "框架已封装的不必绕过；仅当封装方法缺失时可用 driver 原生（client.appium_driver）",
         "el = appOperator.getElement(elements.start_btn)\nassert el.text == '开始测试'"),
    ]),
    ("长流程步骤（轮询/分支/收键盘）", [
        # ============ 元素定位器「操作类型」下拉新增的四类长流程步骤 ============
        # 对应 case_generator.STEP_TYPES: wait_element / assert_gone / if_click / hide_keyboard
        ("轮询等待元素出现（生成中/加载慢）",
         "操作类型选「轮询等待出现」→ 生成 page.wait_元素名(最长秒数)",
         "元素一出现立刻继续（不干等），最长等 N 秒，超时用例失败。适合：歌曲生成中、页面加载慢、弹窗延迟出现",
         "# 元素定位器自动生成的页面方法（页面文件里）\n"
         "def wait_save_success(timeout_seconds=60):\n"
         "    probe = CreateElement.create(self._elements.text_save_success.locator_type,\n"
         "                                 self._elements.text_save_success.locator_value,\n"
         "                                 wait_type=Wait_By.PRESENCE_OF_ELEMENT_LOCATED,\n"
         "                                 wait_seconds=timeout_seconds)\n"
         "    self.appOperator.getElement(probe)\n"
         "# 用例里调用：page.wait_save_success(60)"),
        ("断言元素消失（弹窗已关闭）",
         "操作类型选「断言消失」→ 生成 page.assert_元素名_gone()",
         "反向断言：元素必须「找不到」才算通过；元素还在 = 用例失败并截图。适合：点确定后验证弹窗消失",
         "# 元素定位器自动生成的页面方法（页面文件里）\n"
         "def assert_save_success_gone(wait_seconds=2):\n"
         "    probe = CreateElement.create(..., wait_seconds=wait_seconds)\n"
         "    gone = True\n"
         "    try:\n"
         "        self.appOperator.getElement(probe)\n"
         "        gone = False\n"
         "    except Exception:\n"
         "        pass\n"
         "    self.appOperator.assert_true_with_shot('断言「保存成功弹窗」已消失', gone,\n"
         "                                       '等待%s秒内元素仍可见' % wait_seconds)\n"
         "# 用例里调用：page.assert_save_success_gone()"),
        ("分支：元素出现才点击（偶发弹窗）",
         "操作类型选「出现才点击(分支)」→ 生成 page.click_元素名_if_visible(探测秒数)",
         "弹窗出现了就点它，没出现就跳过继续（不会因没弹而卡死用例）。适合：今日首次发布领金豆、活动挽留弹窗",
         "# 元素定位器自动生成的页面方法（页面文件里）\n"
         "def click_get_bean_if_visible(timeout_seconds=3):\n"
         "    probe = CreateElement.create(..., wait_seconds=timeout_seconds)\n"
         "    try:\n"
         "        self.appOperator.click(self.appOperator.getElement(probe))\n"
         "    except Exception:\n"
         "        pass   # 没弹窗，跳过\n"
         "# 用例里调用：page.click_get_bean_if_visible(3)"),
        ("收起键盘（输入完点下一步）",
         "操作类型选「收起键盘」→ 生成 page.dismiss_keyboard()",
         "键盘可见才收起（is_keyboard_shown 判断），个别 ROM 异常时按返回键兜底。无需选元素",
         "# 元素定位器自动生成的页面方法（页面文件里）\n"
         "def dismiss_keyboard():\n"
         "    try:\n"
         "        if self.appOperator.is_keyboard_shown():\n"
         "            self.appOperator.hide_keyboard()\n"
         "    except Exception:\n"
         "        self.appOperator.press_keycode(4)\n"
         "    import time\n"
         "    time.sleep(1)\n"
         "# 用例里调用：page.dismiss_keyboard()"),
    ]),
    ("获取元素 Get", [
        ("定位单个元素",
         "appOperator.getElement(元素信息)",
         "返回元素对象，找不到会在30秒内重试直到超时",
         "element = appOperator.getElement(elements.start_btn)"),
        ("定位多个元素",
         "appOperator.getElements(元素信息)",
         "返回元素列表，用下标取第N个",
         "btns = appOperator.getElements(elements.city_btns)\nappOperator.click(btns[2])"),
        ("父元素下找子元素",
         "appOperator.getSubElement(父元素, 子元素信息)",
         "在父元素范围内找单个子元素",
         "child = appOperator.getSubElement(parent, elements.city_name)"),
        ("父元素下找多个子元素",
         "appOperator.getSubElements(父元素, 子元素信息)",
         "在父元素范围内找多个子元素",
         "children = appOperator.getSubElements(parent, elements.city_name)"),
        ("元素文本",
         "appOperator.getText(元素)",
         "获取元素上显示的文本",
         "text = appOperator.getText(element)"),
        ("获取元素中心坐标",
         "appOperator.get_element_center_location(元素)",
         "返回 {'x':..,'y':..}，可配合 tap 使用",
         "xy = appOperator.get_element_center_location(element)\nappOperator.tap(xy['x'], xy['y'])"),
        ("获取元素属性（Appium 常见）",
         "appOperator.get_attribute(元素, 属性名)",
         "Appium 方法经框架封装。常用属性：text / resource-id / content-desc / checked / enabled / selected / displayed",
         "checked = appOperator.get_attribute(elements.agree_check, 'checked')"),
        ("元素是否显示",
         "appOperator.is_displayed(元素)",
         "返回 True/False",
         "assert appOperator.is_displayed(element)"),
    ]),
    ("重复元素（同 id / 同 text）", [
        ("页面有 N 个相同元素怎么办",
         "appOperator.getElements(元素信息)",
         "同 id 的元素有多个时，定位会命中第一个/随机一个。正确做法：先把它们全部取出，再按下标取第 i 个（下标从 0 开始）",
         "btns = appOperator.getElements(elements.city_btns)\nappOperator.click(btns[2])  # 点击第 3 个"),
        ("按下标取第 N 个（推荐）",
         "appOperator.getElements(元素信息)[i]",
         "i 从 0 开始：0 是第一个、1 是第二个……配合页面从上到下的顺序取",
         "imgs = appOperator.getElements(elements.img_list)\nappOperator.click(imgs[4])  # 第 5 张图"),
        ("XPath 下标定位",
         "(//*[@resource-id='xxx'])[n]",
         "n 从 1 开始；适用于直接写在元素库里（Locator_Type.XPATH）",
         "element = appOperator.getElement(elements.city_btns)\n# 元素库值写: (//*[@resource-id='com.x:id/abk'])[2]"),
        ("UiSelector instance 定位",
         "new UiSelector().resourceId('xxx').instance(n)",
         "n 从 0 开始，和 getElements()[i] 下标一致；写在元素库里用 Locator_Type.ANDROID_UIAUTOMATOR",
         "element = appOperator.getElement(elements.city_btns)\n# 元素库值写: new UiSelector().resourceId('com.x:id/abk').instance(1)"),
        ("父元素内找子元素再取第 N 个",
         "appOperator.getSubElements(父元素, 子元素信息)[i]",
         "多个列表项结构相同：先在父容器内找所有子元素，再按下标取，比全局 XPath 下标更稳",
         "list_box = appOperator.getElement(elements.list_box)\nitems = appOperator.getSubElements(list_box, elements.item_name)\nappOperator.click(items[0])"),
        ("重复 text 元素",
         "appOperator.getElements(元素信息) 或 UiSelector().text('xxx').instance(n)",
         "text 相同的按钮/标签同理，用下标区分；len(getElements(元素)) 可拿到个数",
         "assert len(appOperator.getElements(elements.start_btn)) >= 3"),
    ]),
    ("等待 / 页面状态", [
        ("元素出现(隐式内含)",
         "appOperator.getElement(元素信息)",
         "getElement 内部自带显式等待，一般不需要单独等待",
         "appOperator.getElement(elements.start_btn)"),
        ("等待页面标题出现",
         "appOperator.explicit_wait_page_title(元素信息)",
         "框架内置。专门等待某页面标题/文案出现后再走下一步",
         "appOperator.explicit_wait_page_title(elements.page_title)"),
        ("获取当前 Activity",
         "appOperator.get_current_activity()",
         "拿当前页面名，调试/断言用",
         "activity = appOperator.get_current_activity()"),
        ("获取当前包名",
         "appOperator.get_current_package()",
         "拿当前应用包名",
         "pkg = appOperator.get_current_package()"),
        ("获取页面源码XML",
         "appOperator.get_page_source()",
         "返回当前页面完整 XML（元素定位调试利器）",
         "xml = appOperator.get_page_source()"),
        ("获取窗口尺寸",
         "appOperator.get_window_size()",
         "返回窗口宽高，适配不同分辨率屏幕用",
         "size = appOperator.get_window_size()\nprint(size['width'], size['height'])"),
    ]),
    ("截图 / 录屏", [
        ("截图并附加到报告",
         "appOperator.get_screenshot(文件名)",
         "截图自动带时间戳并附到 allure 报告",
         "appOperator.get_screenshot('login_page')"),
        ("元素截图存本地",
         "appOperator.save_element_image(元素, 图片名)",
         "只截某个元素的图，存 output/tmp/",
         "path = appOperator.save_element_image(element, 'logo.png')"),
        ("开始录屏",
         "appOperator.start_recording_screen()",
         "开始录屏（华为等无 screenrecord 设备自动跳过）",
         "appOperator.start_recording_screen()"),
        ("停止录屏",
         "appOperator.stop_recording_screen(文件名='')",
         "停止录屏并附加到 allure 报告",
         "appOperator.stop_recording_screen('case1')"),
    ]),
    ("启动 / 关闭 App", [
        ("回到指定 Activity",
         "appOperator.start_activity(包名, Activity名)",
         "强制把 App 拉回指定页面",
         "appOperator.start_activity('com.recordlife.kuaige', 'com.recordlife.kuaige.feature.main.MainActivity')"),
        ("启动 App",
         "appOperator.launch_app()",
         "启动 App（不重置数据）",
         "appOperator.launch_app()"),
        ("关闭 App",
         "appOperator.close_app()",
         "关闭 App",
         "appOperator.close_app()"),
        ("重置 App(清数据)",
         "appOperator.reset_app()",
         "清空应用数据并重启（慎用，会丢登录态）",
         "appOperator.reset_app()"),
        ("后台/前台切换",
         "appOperator.background_app() / activate_app()",
         "模拟按 Home 键后再回来",
         "appOperator.background_app()\nappOperator.activate_app()"),
    ]),
    ("系统按键 / 开关", [
        ("按系统键",
         "appOperator.press_keycode(KEYCODE)",
         "4=返回 3=首页 66=回车 67=删除 187=多任务",
         "appOperator.press_keycode(4)   # 返回键"),
        ("锁屏 / 解锁",
         "appOperator.lock_screen(seconds=None) / unlock_screen()",
         "锁屏N秒后可解锁",
         "appOperator.lock_screen(3)\nappOperator.unlock_screen()"),
        ("飞行模式",
         "appOperator.toggle_airplane_mode()",
         "切换飞行模式开关",
         "appOperator.toggle_airplane_mode()"),
        ("WiFi 开关",
         "appOperator.toggle_wifi()",
         "切换 WiFi 开关",
         "appOperator.toggle_wifi()"),
        ("定位服务开关",
         "appOperator.toggle_location_services()",
         "切换定位服务",
         "appOperator.toggle_location_services()"),
        ("摇一摇设备",
         "appOperator.shake_device()",
         "模拟摇动手机",
         "appOperator.shake_device()"),
    ]),
    ("数据 / 其他", [
        ("上传文件(选择器)",
         "appOperator.uploadFile(元素, 文件路径)",
         "点击上传按钮后调用，填入本地文件路径",
         "appOperator.uploadFile(choose_btn, '/Users/me/a.png')"),
        ("读取剪贴板",
         "appOperator.get_clipboard()",
         "返回剪贴板文本",
         "text = appOperator.get_clipboard()"),
        ("写入剪贴板",
         "appOperator.set_clipboard(文本)",
         "设置剪贴板内容",
         "appOperator.set_clipboard('hello')"),
        ("推送文件到设备",
         "appOperator.push_file_to_device(设备路径, 本地路径)",
         "第 1 个参数是手机上的目标路径，第 2 个是电脑上的源文件（框架签名如此）",
         "appOperator.push_file_to_device('/sdcard/a.txt', '/tmp/a.txt')"),
        ("从设备拉文件",
         "appOperator.pull_file_from_device(设备路径, 本地路径)",
         "第 1 个参数是手机上的文件，第 2 个是存到电脑的位置",
         "appOperator.pull_file_from_device('/sdcard/a.txt', '/tmp/a.txt')"),
    ]),
]


def search_tutorials(keyword):
    """在教学树中搜索标题/方法/说明/示例，返回命中的分支树（保持层级结构）"""
    kw = (keyword or '').strip().lower()
    if not kw:
        return TUTORIALS

    def walk(items):
        out = []
        for item in items:
            if len(item) == 2 and isinstance(item[1], list):
                # 分类：分类名直接命中 → 整类保留（小白搜"滑动"就该看到全部滑动方法）；
                # 否则只保留子项有命中的分类（层级结构不变）
                if kw in str(item[0]).lower():
                    out.append((item[0], item[1]))
                    continue
                children = walk(item[1])
                if children:
                    out.append((item[0], children))
            else:
                # 叶子 (标题, 签名, 说明, 示例)
                title, sig, desc, code = (list(item) + [None] * 4)[:4]
                blob = ' '.join(str(x) for x in (title, sig, desc, code) if x).lower()
                if kw in blob:
                    out.append(item)
        return out

    return walk(TUTORIALS)