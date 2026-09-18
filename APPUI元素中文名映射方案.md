# 元素中文名映射方案（元素管理显示中文 · 添加用例弹窗增加中文字段）

> 目标：元素管理的「名称」列显示中文（如"悬浮球"），下方副行显示代码名（floating_icon_parent）。
> 中文名在元素定位器「添加测试用例」弹窗中录入。**本方案不动框架执行链路，仅展示层与元素行注释位。**

## 一、现状核实（方案依据）

| 层 | 现状 | 结论 |
|---|---|---|
| 框架 | `CreateElement.create(..., desc=None)`——签名已含 `desc`，源码注释明确写"**元素中文说明**……仅作备注透传" | **中文名有现成承载位，零格式风险** |
| 元素库行 | `self.floating_icon_parent = CreateElement.create(Locator_Type.ID, '…', wait_type=…)  # 备注`；带备注时 add_element 会同时写 `desc='备注'` 与行尾 `# 备注` | 中文名可落 `desc=`，备注留行尾 `#` |
| 解析层 | `web_platform/element_manager.py list_elements()` 已解析 `desc`（先 `desc=` 参数、后行尾注释）→ `/api/appui/elements` 已返回 | 只需拆分出 `cn_name` 字段 |
| 元素管理列表 | 名称列 = `name`（代码名）；列为 名称/类型/标签/预览/使用次数/创建时间/操作 | 前端只改名称列渲染 |

## 二、数据约定（唯一规则，全链路遵守）

元素行（示例）：

```python
self.floating_icon_parent = CreateElement.create(Locator_Type.ID, 'com.xxx:id/floating', wait_type=Wait_By.VISIBILITY_OF, desc='悬浮球')  # 悬浮球 · 右下角悬浮入口
```

- **`desc=` 参数 = 元素中文名**（元素管理/报告的显示名；无中文时缺省）
- **行尾 `#` 注释 = 备注**（沿用现有；有中文名时格式 `# 中文名 · 备注`，便于纯文本回看）
- **兼容旧数据**：无 `desc` 的旧元素 → 元素管理主行仍显示代码名，无副行，不迁移不报错

## 三、改动清单（4 个文件，均为小改）

### 1. 元素定位器「添加测试用例」弹窗（element_locator/static/index.html + index.js）

- ① 元素栏新增字段 **「元素中文名」**（紧跟元素名称旁），placeholder：`如：悬浮球（元素管理中显示的名称）`
- **预填规则**：点选截图元素后，若节点有中文 `text` 自动预填（比代码名更聪明，多数情况零输入）
- 保存链路：`add_element` 增加可选参数 `cn_name`；`element_library.element_line()` 生成行时 `desc=` 位置写 cn_name，行尾注释写 `cn_name · comment`（无备注则只写 cn_name）
- 临时用例包（新建用例文件）的 `elementLinePreview()` 同步同样规则

### 2. 元素库生成（element_locator/element_library.py）

- `add_element(..., cn_name=None)`、`element_line(..., cn_name=None)`：新增可选参数，`desc='中文名'`；**不传 cn_name 时行为与现在完全一致**（老调用方零影响）
- 重复检测逻辑不变（仍按 locator_type+value）

### 3. 解析层（web_platform/element_manager.py）

- `list_elements()`：每个元素增加输出字段 **`cn_name`**——取 `_DESC_RE` 匹配的 `desc=` 值；`name` 保持代码名不变
- 保存/编辑接口（`save_element`）同步接受 `cn_name`（元素管理的编辑弹窗可改中文名）

### 4. 元素管理前端（web_platform/templates/run.html + static/app.js）

- **名称列渲染**：主行 = `cn_name || name`（粗体中文）；`cn_name` 存在时副行 `.path` 灰色小字显示 `name`（代码名）
- 搜索框同时匹配 `cn_name` 与 `name`（输入"悬浮球"或"floating"都能命中）
- 元素编辑弹窗新增「中文名」字段（可选，与定位器弹窗一致）

## 四、明确不做（边界）

- ❌ 不改执行链路：页面方法名（`click_floating_icon_parent`）、用例代码引用、Allure 报告里的元素标识**保持代码名**——改名会牵动三件套联动，风险远超收益
- ❌ 不迁移旧元素：显示名随下次编辑自然补全
- ❌ 元素定位器自身的元素树/详情仍显示代码名（那是开发视角；用户没要求改）

## 五、验收标准

1. 定位器弹窗填「中文名：悬浮球」保存 → 元素库行含 `desc='悬浮球'`
2. 元素管理列表名称列：主行"悬浮球"，副行 `floating_icon_parent`
3. 旧元素（无数值化名）显示不回归：主行代码名、无副行
4. 元素管理搜索"悬浮球"可命中；搜索 `floating_icon_parent` 仍可命中
5. 全量回归通过；执行/报告链路不受影响（跑一次真机用例验证）

## 六、工作量与版本

- 预估：定位器弹窗+element_library 1 小时；解析层+元素管理前端 1 小时；回归+真机验证 0.5 小时
- 版本：实现时 +1（当前 6.38 → 6.39，单数不推送；若合并其它改动到 6.40 则推送）
