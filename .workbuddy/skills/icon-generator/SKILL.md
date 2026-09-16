---
name: icon-generator
description: 网页与数字界面设计师和平面设计师在开发App、网页或设计UI界面时，当需要快速产出高质量Icon，使用此技能即可一键生成多尺寸、风格统一的标准图标，彻底解决图标设计耗时痛点，大幅提升视觉交付效率！
---

# Icon Generator Skill

一键产出多尺寸、风格统一的标准图标。核心原则：**SVG 单一源文件，尺寸导出交给脚本，绝不手绘多份。**

## 工作流

1. **画一个 SVG 源文件**（24×24 viewBox，本项目的图标基准网格）
   - 落盘到 `web_platform/static/icons/src/<name>.svg`（路径不存在时随图标一并创建）
2. **按标准尺寸集导出 PNG**：16 / 32 / 48 / 64 / 128 / 256
   - 落盘到 `web_platform/static/icons/<name>-<size>.png`
3. **自检**：每个尺寸肉眼可辨、风格一致，方可交付

## 风格统一规范（所有图标必须遵守）

- viewBox 统一 `0 0 24 24`，内容留 2px 安全边距（图形控制在 2~22 范围内）
- 描边统一 `stroke-width: 2`，`stroke-linecap: round`、`stroke-linejoin: round`（线性图标）
- 面性图标用单一填充色，不混用渐变
- 圆角与曲线优先，避免尖角；同一套图标只选「线性」或「面性」一种，不混用
- 配色沿用项目现有 UI 主色；不确定时先看 `web_platform` 现有页面用色，再定图标色

## 导出方式（按 ponytail 原则，取最简可用的一条）

优先级从高到低，取第一条可用的：

1. **rsvg-convert**：`rsvg-convert -w 32 -h 32 icon.svg -o icon-32.png`（循环尺寸集）
2. **macOS 自带 qlmanage**：`qlmanage -t -s 256 -o . icon.svg`
3. **Python（项目已有 .venv）**：`cairosvg` 库，一行一个尺寸；未安装则 `pip install cairosvg`

禁止：引入图标构建框架、写通用图标管线类——一个 10 行左右的导出循环脚本足够。

## 交付清单

- [ ] `src/<name>.svg` 源文件存在
- [ ] 6 个尺寸 PNG 全部生成，命名 `<name>-<size>.png`
- [ ] 与现有图标并排对比，风格（线宽/圆角/配色）无违和
- [ ] 引用图标的页面/组件已更新路径

> 一次只做一套图标。批量需求逐套进行，每套独立验收。
