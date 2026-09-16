# App 元素定位器（element_locator）

框架内置的可视化元素定位器：连上真机 → 看实时截图 → 点元素拿坐标和定位写法 → **一键写进框架元素库**；带**双击执行器**可先在设备上真实点击验证；右侧内置操作教学（点击/滑动/toast 断言…），不用上网查。
当前版本 **v3.2**（左上角徽章，用于确认本地代码是否已更新）。

> 技术架构、坐标映射原理、配置方法与移植到其他项目的步骤见 **[技术实现方案.md](技术实现方案.md)**。

## 启动

定位器已并入 Web 执行平台（同一进程，挂在 `/locator` 子路径），不再有独立的 8001 服务：

```bash
cd ~/Desktop/AutomationTest
./run.sh platform                    # 平台 + 定位器一起启动
./run.sh restart-platform            # 改完定位器代码后一键生效
open http://127.0.0.1:8080/locator/  # 定位器页面
```

前提：手机已连电脑并允许 USB 调试（`adb devices` 能看到设备）。

## 三栏怎么用

| 位置 | 功能 |
|---|---|
| **左：设备截图** | 点「刷新」加载当前手机画面；**点截图任意位置** → 自动选中该处元素（红框高亮 + 联动中间栏）；**双击截图 → 真机真实点击该元素**，立刻验证定位准不准 |
| **中：元素/坐标** | 元素树（可折叠、可搜索）；点元素看属性/坐标 + 定位写法（ID / XPath / UIAutomator）；「▶ 设备上点击」= 对选中元素真机点击；「一键添加」写进元素库 |
| **右：操作教学** | 点击、滑动、输入、toast 断言、重复元素、截图、系统按键…默认收起、点击展开，每条有完整示例代码，**点「复制」即用**；顶部搜索「点击 / 滑动 / toast / 断言」即搜即得 |

## 双击执行器（验证定位）

- **双击截图上某个元素**，或选中元素后点 **「▶ 设备上点击」** → 工具通过 `adb input tap` 在真机真实点击该元素，随后自动刷新截图，让你亲眼看到页面变化，确认"定位到的就是它"。
- 点完发现点错了？说明定位表达式有偏差，改选命中候选层或改用重复元素下标写法（见下）。

## 重复元素怎么办

页面有 N 个一模一样的元素（如同一个 `resource-id`）时，工具会自动提示 **「页面共有 N 个同名」**，并直接给你带下标的写法，不会定位偏差：

```python
# XPath 下标（第 2 个）
self.item2 = CreateElement.create(Locator_Type.XPATH, '(//*[@resource-id="com.recordlife.kuaige:id/img"])[2]', wait_type=Wait_By.VISIBILITY_OF)

# 或 UiSelector instance（从 0 数，第 2 个 = instance(1)）
self.item2 = CreateElement.create(Locator_Type.UIAT, 'new UiSelector().resourceId("com.recordlife.kuaige:id/img").instance(1)', wait_type=Wait_By.VISIBILITY_OF)

# 或在用例里取列表再按下标拿
item = appOperator.getElements(elements.imgs)[1]
```

同时「操作教学 → 重复元素」分类里有 6 种完整做法。

## 一键添加元素 → 怎么在用例里用

1. 截图里点到元素 → 「一键添加」→ 改名称（如 `search_btn`）、选定位方式 → 保存
2. 元素会写入 `page_objects/app_ui/android/demoProject/elements/`（默认新建 `locator_gui_elements.py`；同名重复添加 = **覆盖**；漏 import 自动补）
3. 用例里引用：

```python
from page_objects.app_ui.android.demoProject.elements.locator_gui_elements import LocatorGuiElements
elements = LocatorGuiElements()

appOperator.click(elements.search_btn)                 # 点击
appOperator.sendText(elements.search_city, '北京')      # 输入
item = appOperator.getElements(elements.city_btns)[1]   # 重复元素取第 2 个
assert appOperator.is_toast_visible('操作成功')          # 断言 toast
```

## 添加到用例 / 新建用例包（两条入库通路）

定位器右侧「添加到用例」有两个模式，两者产物都能被平台执行页直接选中运行：

**① 添加到已有用例（选目标用例文件）**
选目标用例文件 → 选目标测试方法 → 选用途（仅存元素库 / 追加到用例 / 元素+用例+操作）→ 保存。
代码追加到该用例方法体末尾；选「元素+用例+操作」时同步生成页面对象方法。归属由用例的
`self.page = XxxPage(...)` 反解得出，页面文件字段只读（改它等于换目标用例）。

**② 新建用例包（三件套一次生成）**
填用例名 → 一键生成三件套，两个出口：

| 出口 | 行为 |
|---|---|
| **💾 保存到框架** | 直接入库（与平台同进程调用，享受同一套 py 语法校验 / 同名自动备份 / 上传人登记）。**先全部校验、全部通过才落盘**，任一文件语法错则一个都不写 |
| **⬇ 下载用例包（zip）** | 下载 zip，再到平台「**用例管理 → 📦 上传用例包**」上传入库（同一套校验逻辑，适合局域网/离线上传） |

三件套落点（与弹窗预览一致）：

```
cases/app_ui/android/demoProject/test_<用例名>.py                  ← 用例（含 test_<用例名> 方法）
page_objects/app_ui/android/demoProject/pages/<首字母大写>Page.py   ← 页面操作
page_objects/app_ui/android/demoProject/elements/<用例名>Elements.py ← 元素库
```

> 注意：用例必须落在 `cases/app_ui/**` 下平台才扫得到——这一步由定位器自动带上，无需手填。

**三个提效工具**

| 工具 | 位置 | 说明 |
|---|---|---|
| **🟢 树对比（Diff）** | 左栏「树对比」开关 | 每次刷新与上一次元素树对比：新节点标 🟢，消失的在树顶部 🔴 摘要列出——快速发现页面跳转与弹窗 |
| **🎯 体检** | 选中元素 → 定位写法下方 | 按选中定位在当前页面**真实查找**：唯一命中 ✅ / 多处 ⚠️ / 未命中 ❌，命中时在截图上画框——页面改版后验证老定位是否还活着 |
| **↩ 撤销上一步** | 左栏底部「本次会话已录 N 步」 | 「添加到用例」写入的步骤可按倒序撤销，用例文件与页面方法**恢复到写入前内容**（逐字节） |

撤销说明：只支持撤销**本次会话**内追加的步骤（倒序，不能跳步），关闭页面后记录清空；手动改过的文件以你改动后的现状为准。

## 常见问题

- **截图空白/刷新失败**：确认手机亮屏（黑屏时 uiautomator dump 不出内容）、USB 调试已授权
- **页面没变/功能是旧的**：左上角看版本号是不是 v3.2；是旧版说明浏览器缓存了，`Cmd+Shift+R`（Mac）或 `Ctrl+F5`（Win）强刷，或点开页面后浏览器右上角「开发者工具 → Network → Disable cache」
- **平台起不来/端口被占**：`./run.sh status` 会列出占用者；`./run.sh restart-platform` 一键重启
- 定位器与平台同进程（`/locator` 子路径），改完代码用 `./run.sh restart-platform` 生效

## 技术栈

Python 3.8 + Flask（venv 已内置），设备数据走 adb（screencap + uiautomator dump + input tap），**不依赖 Appium session**。目录改名说明：原 `gui/` 已更名为 `element_locator/`。


## 多设备切换（v3.0）

服务器可同时连接多台 Android 手机：

- 侧栏底部（内嵌模式在顶部工具条）**📱 设备下拉**：列出全部在线设备（型号 · Android 版本），切换即刷新对应设备画面
- 每台设备的状态（截图/元素树/选中项/真机点击）完全独立，切换时自动清空上一台痕迹，避免坐标错位
- 上次选中的设备会被记住（刷新页面不跳回第一台）
- 选中的设备中途掉线：自动回退到第一台在线设备并提示
- 局域网同事各自选一台设备使用互不干扰；选同一台时会互相影响（占用锁后续迭代）
- 底层：uiautomator2 降级通道按设备隔离（每台独立 session 与 adb forward 主机端口），杜绝多设备串台
