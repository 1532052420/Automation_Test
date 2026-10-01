# 视觉断言采集面板 · V5「渐变强调」设计规格

> 原型：`design_vacl/v5.html`（日/夜双模式，`?m=night` 切换）；JPG 截图 `design_vacl/img/v5_day.jpg`、`v5_night.jpg`。
> 落地范围：元素定位器 `#visualPanel`（视觉断言开启时的右侧采集表单），文件 `element_locator/static/index.html` + `static/index.js`（vaRenderPanel）+ `static/style.css`。

## 1. 设计语言

渐变描边卡片（呼应平台调试弹窗 V7）：三色渐变（红→琥珀→绿）寓意「比对三态：失败→警告→通过」，包裹一张日/夜自适应的内容卡。卡内以三色圆点小节标题组织信息层级：**红点=断言范围（比对什么）→ 琥珀点=比对参数（怎么比）→ 绿点=忽略与预览（跳过什么）**。

## 2. 布局与尺寸

| 区块 | 规格 |
|------|------|
| 渐变外框 | 圆角 16px，内边距 2px（即描边宽），背景 `linear-gradient(135deg,#EF4444,#F59E0B 40%,#10B981 80%)` |
| 内容卡 `.va5-in` | 圆角 14px（=外框 16 − 描边 2），内边距 14px 14px 12px，日 `#ffffff` / 夜 `#1e2025` |
| 标题行 `.va5-hd` | 左「🧪 视觉断言采集」14.5px/700；右 hint「基线比对」11.5px muted；下边距 12px |
| 小节标题 `.va5-sec` | 8px 圆点（红/琥珀/绿）+ 12.5px/700 文字，上边距 12px 下边距 8px |
| 名称/类型/阈值 | 沿用定位器既有 `.field` + `input/select`（与全站控件一致，含夜间适配） |
| 分段控件 `.va5-seg` | 容器：圆角 9px、内边距 3px、项间隙 2px；按钮：flex:1、上下 7px、12px 字、圆角 7px；选中项白底（夜 `#2a2d33`）+ 品牌蓝字 + `0 1px 4px` 投影 |
| 忽略区域 chips | 沿用既有 `.va-chip` 琥珀虚线样式（含夜间），添加按钮 `.btn.ghost.mini` |
| 基线预览 `.va5-pv` | max-height 200px、圆角 8px、边框 1px（日 `#e5e7eb` / 夜 `#303236`） |
| 底部操作 | 沿用 `.detail-foot`：预览（ghost）+ 保存视觉断言（primary 蓝），左对齐 |

面板宽度不写死：`#visualPanel` 流式跟随右栏（原型 490px 仅为展示尺寸，落地取容器实际宽度）。

## 3. 颜色表（日 / 夜）

| 令牌 | 日间 | 夜间 | 用途 |
|------|------|------|------|
| 渐变描边 | `#EF4444→#F59E0B→#10B981`（135°，两模式一致） | 同左 | 外框 |
| 卡片底 | `#ffffff` | `#1e2025` | 内容卡 |
| 主文字 | `#1f2937` | `#f3f4f6` | 标题 |
| 小节文字 | `#374151` | `#e5e7eb` | 小节标题 |
| hint/次要 | 沿用全站 `.hint`（含夜间覆盖） | 同左 | 说明文字 |
| 分段容器底 | `#eef1f5` | `#141519` | `.va5-seg` |
| 分段选中底 | `#ffffff` | `#2a2d33` | `.on` 项 |
| 分段选中字 | `var(--sky) #409eff` | `#66b1ff` | `.on` 项 |
| 分段未选中字 | `#6b7280` | `#9aa3af` | `.va5-seg button` |
| 圆点 | 红 `#EF4444` / 琥珀 `#F59E0B` / 绿 `#10B981`（两模式一致） | 同左 | 小节标记 |
| 预览边框 | `#e5e7eb` | `#303236` | `.va5-pv` |

## 4. 交互与 JS 规格（index.js）

状态机沿用 `var va`，新增 `match` 字段：

- `va = { on, scope:'element', match:'strict', region, ignores, ignoreArmed, preview, els }`
- 开启模式（vaToggleMode）重置：`scope='element'; match='strict'; region=null; ignores=[]; ignoreArmed=false`

| 交互 | 规范 |
|------|------|
| 范围分段（红点区） | 点击按钮 → `va.scope` 更新 + 选中态同步；**副作用与旧 radio 一致**：`ignores=[]`、`region=null`、重画截图标注（vaDrawRects）、刷新 chips 与范围提示（vaSyncHints） |
| 类型下拉 | change → vaSyncHints（Toast 类型专属提示） |
| 模式分段（琥珀点区） | 点击 → `va.match` 更新 + 选中态同步（无其他副作用） |
| 阈值输入 | 沿用 vaCollect 读取 `#va-th`（50~100，默认 98） |
| 添加忽略区域 | 校验已有视觉区域 → `ignoreArmed=true` + 黄色提示，回截图拖拽（原链路不变） |
| 预览 / 保存 | 原链路不变（`api/visual_asset/preview`、`api/visual_asset/save`）；vaCollect 的 `match_mode` 改读 `va.match`（原 `input[name=va-match]:checked` 随 radio 移除废弃） |

保留 ID 兼容：`va-name / va-biz / va-th / va-chips / va-preview / va-preview-btn / va-save-btn / va-add-ignore / va-scope-hint / va-biz-hint / va-ignore-hint` 全部不变，仅 radio 换分段、新增 `va-scope-seg / va-match-seg`。

## 5. 验收清单

1. 日/夜两模式：渐变描边一致，卡片底/文字/分段控件/chips/预览边框全部可读无硬编码穿帮
2. 范围切换三档：提示文案切换、截图标注重画、已加忽略区域清空
3. 模式切换 Strict/Layout 即选即用（保存请求 match_mode 正确）
4. 名称/类型/阈值/忽略/预览/保存全链路与改造前行为一致（回归）
