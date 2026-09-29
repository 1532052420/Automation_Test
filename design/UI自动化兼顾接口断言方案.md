> ⚠️ **v2 修订（2026-09-29，开发者/产品视角复盘）**：本档 2 的录入入口修正为「**用例编排**」（接口步骤无元素，不进元素定位器向导）；环境配置（base_url/token）从第一天起走接口测试模块现成环境变量体系（`config/api_testing/environments.yaml`），不固化进生成代码；并立产品规则——UI 用例内接口步骤仅限「异步状态轮询」与「产物内容校验」两类。详见《接口断言插入流程图.html》v2。

# UI 自动化兼顾接口断言 · 方案（调研结论）

> 场景：跑 AppUI 自动化时同时校验接口层数据。典型例子——快歌写歌要 5 分钟，5 分钟后断言产出的作品（视频/音频）。
> 结论先行：**能做，且约 80% 的积木已经在库里**。以下按「零开发立即可用 → 轻封装 → 平台化」三档给方案。

---

## 一、为什么能做（已核实的代码事实）

| 能力 | 现状 | 位置 |
|---|---|---|
| UI 用例进程发 HTTP | `requests 2.27.1` 在同一 venv，pytest 子进程可直接 import，conftest 无代理限制 | requirements.txt |
| 长等待 | `wait_element` 轮询等待（最长 N 秒，为「生成中/加载慢」设计）——UI 层等作品卡出现 | case_generator.py |
| **音视频断言** | `check_media(path, options)` 已实现：格式 / 时长范围 / 有无声音 / 分辨率 / 码率，基于 ffprobe（已装） | web_platform/api_testing/media_assertions.py:179 |
| 接口 JSON 断言 | 接口测试模块 6 种断言（status_code/json_path/contains…）引擎现成 | web_platform/api_testing/executor.py |
| 自定义代码步骤 | 定位器操作类型 `custom` 已支持在生成用例里写任意 Python 行 | case_generator STEP_TYPES |
| 失败证据链 | 用例失败自动截图+录屏+allure | cases/app_ui/conftest.py |

唯一缺口：**UI 用例与接口断言之间没有"胶水原语"**——现在只能靠 custom 步骤手写。

## 二、写歌 5 分钟场景的目标形态

```
UI 用例（一条 pytest 用例内顺序执行）：
 1. UI：进入写歌页，输入歌词，点「生成」          ← 现有能力
 2. 接口：轮询作品状态接口（每 15s 查一次，最长 5 分钟，
    json_path 断言 status=="完成"）              ← 本方案新增的胶水
 3. 下载：从接口响应拿作品 URL，下载视频/音频到本地  ← requests 一行
 4. 断言：check_media 校验视频格式/时长/有无声音、
    音频非静音；失败自动截图+视频留证入 allure     ← 已有，直接 import
```

## 三、三档落地方案

### 档 1：零开发，今天就能用（custom 步骤手写）

定位器操作类型选「自定义代码」，或直接在用例文件里写：

```python
def test_write_song(self):
    page = self.page
    page.click_btn_write()                      # UI 步骤（定位器生成）
    # ↓ 接口轮询 + 断言（custom 手写，约 10 行）
    import requests, time
    from web_platform.api_testing.media_assertions import check_media
    for _ in range(20):                          # 最长 5 分钟
        r = requests.get(API_BASE + '/works/latest',
                         headers={'Authorization': 'Bearer ' + TOKEN}, timeout=10).json()
        if r['data']['status'] == 2: break       # 2=完成
        time.sleep(15)
    assert r['data']['status'] == 2, '5分钟内作品未生成完成'
    url = r['data']['video_url']
    path = '/tmp/work_%d.mp4' % r['data']['id']
    with open(path, 'wb') as f: f.write(requests.get(url, timeout=60).content)
    ok, actual, err = check_media(path, {'duration_min': 30, 'sound': True})
    assert ok, '作品音视频校验失败: %s' % err
```

- 优点：零改造，立即生效；缺点：每条用例手写 10 行，token/接口地址散落。

### 档 2：轻封装（推荐，约 +120 行）——appOperator 加两个原语 + 定位器加一种操作类型

**新增 `common/appium/api_assert.py`**（挂在 appOperator 旁边，用例里 `self.appOperator.xxx` 直调）：

```python
def api_wait_json(self, desc, url, json_path, expected, timeout=300, interval=15,
                  headers=None, params=None):
    """接口轮询断言：轮询直到 json_path 取值 == expected，超时抛 AssertionError（截图留证）"""

def api_download_and_check(self, desc, url, media_opts=None, save_to='output/tmp/'):
    """下载文件 + 音视频断言（内部直接调 check_media），失败附 ffprobe 明细"""
```

**定位器/生成器侧**（照视觉断言同一套路，改动面已知）：
- `STEP_TYPES` 加 `api_assert`（参数=URL、json_path、期望值、超时/间隔）与 `media_check`（下载 URL + 时长/声音选项）；
- `case_generator.page_method_code` 两个分支 + 前端镜像；
- ④…啊不，现在断言卡组里加两张卡：「**断言接口字段**」「**断言作品音视频**」，勾选即配参数。

生成出来的用例就是干净的：

```python
page.click_btn_write()
page.wait_works_ready()          # api_wait_json 生成（轮询状态接口）
page.check_work_video()          # api_download_and_check 生成（下载+音视频断言）
```

### 档 3：平台化（后续演进，非本期）

- 环境打通：UI 用例复用接口测试模块的「环境变量」体系（base_url/token 存 `config/api_testing/environments.yaml`，用例读 `{{base_url}}`）；
- 平台报告：UI 用例里的接口断言结果单独成段展示（allure step 天然支持，已自动）。

## 四、接入前提（需要你/后端提供，共 2 项）

1. **作品查询接口**：写歌提交后，查询当前用户最新作品的接口（返回 status、video_url / audio_url 字段）；
2. **鉴权方式**：该接口怎么带登录态——测试账号+密码走登录接口换 token 最理想（可自动化）；若必须用 App 内 token，则需要 adb 读 SharedPreferences / 拦包拿 token 的辅助（复杂一档，建议优先问后端要测试账号直连）。

测试环境地址若与外网隔离，确认 Mac 本机可直接访问该 API 域名即可（UI 跑在本机 pytest 进程里，不走手机网络）。

## 五、风险与对策

| 风险 | 对策 |
|---|---|
| 5 分钟轮询拖长用例时长、超时阈值难定 | 轮询参数可配（timeout/interval 暴露成操作参数）；轮询期间不占设备，不影响并行 |
| 作品 URL 有时效/防盗链 | 拿到 status=完成 后立即下载；下载失败重试 2 次 |
| token 过期 | 档 3 的环境体系里做 token 自动刷新；档 1/2 先手动配 |
| 接口断言失败但 UI 正常（或反之） | 断言独立成 allure step，失败截图+响应体入证，定位一目了然 |

## 六、建议

**先档 1 验证链路**（拿真实接口手写一条跑通，确认字段与鉴权）→ **再上档 2**（原语+断言卡，把 10 行手写变成勾选配置）。档 2 工作量小（复用视觉断言刚趟平的全部管线），随时可开工。
