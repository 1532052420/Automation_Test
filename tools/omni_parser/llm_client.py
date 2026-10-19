# -*- coding: utf-8 -*-
"""文本大模型客户端（OpenAI 兼容 /chat/completions）：元素清单 + 自然语言意图 → Selenium 代码。
完全独立：requests 直连，不依赖任何 openai SDK。"""
import requests

SYSTEM_PROMPT = '''你是资深 Web 自动化测试工程师。用户会给你：
1. 一张网页截图解析出的可交互元素清单（编号 / 描述 / 置信度 / 边界框坐标）；
2. 用自然语言描述的测试意图。
你的任务：只依据元素清单，生成可直接运行的 Python Selenium 代码。

硬性规则：
- 使用 pytest 风格函数 test_generated()，内含 driver 的最小初始化（chrome，headless 可选参数化）；
- 元素定位优先级：描述里有可见文字 → By.XPATH（contains(text(),...)）；纯图标/无文字 →
  用坐标点击并注释原元素编号（ActionChains(driver).move_to_element_with_offset 或 driver.execute_script）；
- 禁止编造元素清单里不存在的元素或文字；
- 每个动作前加中文注释标注对应元素编号与描述；
- 末尾按意图加合理的断言（driver.title / 页面文本包含等）；
- 只输出一段 Python 代码，不要任何解释文字和 markdown 围栏。'''


class LLMError(Exception):
    pass


def generate_code(cfg, intent, elements, image_size=None):
    """cfg: llm 配置 dict；intent: 自然语言意图；elements: parser.parse 的元素列表。"""
    if not (cfg.get('api_key') or '').strip():
        raise LLMError('LLM api_key 未配置：请在页面「服务配置」填写或编辑 config.yaml')
    lines = []
    for el in elements:
        lines.append('#%d %s（置信度 %s，坐标 %s）' % (
            el['index'], el['description'], el['confidence'],
            ','.join(str(int(v)) for v in el['box_xyxy'])))
    size = ('页面尺寸 %dx%d' % tuple(image_size)) if image_size else ''
    user = ('测试意图：%s\n\n页面元素清单（%d 个可交互元素，%s）：\n%s'
            % (intent.strip() or '未描述（请依据元素清单生成冒烟脚本）',
               len(elements), size, '\n'.join(lines)))
    resp = requests.post(
        cfg['base_url'], timeout=float(cfg.get('timeout') or 60),
        headers={'Authorization': 'Bearer ' + cfg['api_key'],
                 'Content-Type': 'application/json'},
        json={'model': cfg['model'], 'temperature': float(cfg.get('temperature') or 0.3),
              'messages': [{'role': 'system', 'content': SYSTEM_PROMPT},
                           {'role': 'user', 'content': user}]})
    if resp.status_code != 200:
        raise LLMError('LLM 接口 %s：%s' % (resp.status_code, resp.text[:300]))
    data = resp.json()
    try:
        content = data['choices'][0]['message']['content'].strip()
    except Exception:
        raise LLMError('LLM 返回结构异常：%s' % str(data)[:300])
    # 剥掉可能的 markdown 围栏
    if content.startswith('```'):
        content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    return content
