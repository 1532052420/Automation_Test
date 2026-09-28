# -*- coding: utf-8 -*-
"""接口测试 · AI 服务（移植自 testhub AIServiceConfigViewSet，OpenAI 兼容 Chat Completions）

- 配置按 role 分工：doc_extractor（接口→文档）/ naming（参数命名规范）/
  mock_data（模拟数据生成）/ description（参数描述补全）；
- service_type 七种仅作展示，调用统一走 {base_url}/chat/completions；
- 每个功能取全局第一个 role=X 且 is_active 的配置。
"""
import json
import logging

import requests

from web_platform.api_testing import yaml_store as store

logger = logging.getLogger(__name__)

SERVICE_TYPES = ('openai', 'azure', 'anthropic', 'deepseek', 'qwen', 'siliconflow', 'other')
ROLES = ('doc_extractor', 'naming', 'mock_data', 'description')
ROLE_NAMES = {'doc_extractor': '文档提取', 'naming': '命名规范',
              'mock_data': '模拟数据', 'description': '描述补全'}
SERVICE_NAMES = {'openai': 'OpenAI', 'azure': 'Azure OpenAI', 'anthropic': 'Anthropic',
                 'deepseek': 'DeepSeek', 'qwen': '通义千问', 'siliconflow': 'SiliconFlow',
                 'other': '其他(OpenAI兼容)'}


def _active_config(role):
    for c in store.ai_configs.list():
        if c.get('role') == role and c.get('is_active'):
            return c
    return None


def chat(config, prompt, timeout=30, max_tokens_override=None):
    """OpenAI 兼容对话补全，返回 (content, None) 或 (None, 错误消息)"""
    try:
        resp = requests.post(
            '%s/chat/completions' % (config.get('base_url') or '').rstrip('/'),
            headers={'Authorization': 'Bearer %s' % config.get('api_key', ''),
                     'Content-Type': 'application/json'},
            json={'model': config.get('model_name', ''),
                  'messages': [{'role': 'user', 'content': prompt}],
                  'max_tokens': max_tokens_override or int(config.get('max_tokens') or 4096),
                  'temperature': float(config.get('temperature') or 0.7)},
            timeout=timeout)
    except requests.exceptions.Timeout:
        return None, 'AI服务调用超时'
    except requests.exceptions.RequestException as e:
        return None, 'AI服务调用失败: %s' % e
    if resp.status_code != 200:
        return None, 'AI服务调用失败: %s' % resp.status_code
    try:
        return resp.json()['choices'][0]['message']['content'], None
    except Exception as e:
        return None, 'AI响应解析失败: %s' % e


def test_connection(config):
    """连通性测试（max_tokens=10 发 Hello，同 testhub）"""
    content, err = chat(config, 'Hello', timeout=10, max_tokens_override=10)
    if err:
        return False, err
    return True, '连接测试成功'


def _parse_json_content(content):
    """AI 返回内容尽力解析 JSON；失败返回 None（调用方带 raw_content 回传）"""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        # 宽容处理：剥掉 markdown 代码栅栏再试一次
        text = (content or '').strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.lstrip().startswith('json'):
                text = text.lstrip()[4:]
        try:
            return json.loads(text.strip())
        except (json.JSONDecodeError, TypeError):
            return None


def complete_parameter_descriptions(request_id):
    """AI 补全接口参数描述（role=description）"""
    req = store.requests.get(request_id)
    if not req:
        return None, '请求不存在'
    config = _active_config('description')
    if not config:
        return None, '未找到可用的参数描述补全AI配置（AI服务配置里添加 role=描述补全 并启用）'
    prompt = """请为以下API请求的参数生成详细的描述说明：

接口名称: %(name)s
接口描述: %(desc)s
请求方法: %(method)s
请求URL: %(url)s

请求头参数:
%(headers)s

URL参数:
%(params)s

请求体参数:
%(body)s

请为每个参数生成详细的描述说明，包括：
1. 参数用途
2. 数据类型
3. 是否必填
4. 取值范围或示例值
5. 其他注意事项

请返回JSON格式的结果，格式如下：
{
  "headers": {"参数名": "参数描述"},
  "params": {"参数名": "参数描述"},
  "body": {"参数名": "参数描述"}
}""" % {
        'name': req.get('name', ''), 'desc': req.get('description', ''),
        'method': req.get('method', ''), 'url': req.get('url', ''),
        'headers': json.dumps(req.get('headers') or [], ensure_ascii=False, indent=2),
        'params': json.dumps(req.get('params') or {}, ensure_ascii=False, indent=2),
        'body': json.dumps(req.get('body') or {}, ensure_ascii=False, indent=2),
    }
    content, err = chat(config, prompt)
    if err:
        return None, err
    data = _parse_json_content(content)
    if data is None:
        return {'descriptions': {}, 'raw_content': content}, None
    return {'descriptions': data}, None


def generate_mock_data(schema, count):
    """AI 按 schema 生成中文模拟数据（role=mock_data）"""
    if not schema:
        return None, '请提供数据结构定义'
    config = _active_config('mock_data')
    if not config:
        return None, '未找到可用的模拟数据生成AI配置（AI服务配置里添加 role=模拟数据 并启用）'
    prompt = """请根据以下数据结构定义，生成%(count)s条符合该结构的模拟数据：

数据结构定义：
%(schema)s

要求：
1. 数据必须符合给定的结构定义
2. 字符串字段生成有意义的中文内容
3. 数值字段生成合理的数值
4. 日期字段生成有效的日期时间
5. 布尔字段随机生成true/false
6. 数组字段生成适当数量的元素

请返回JSON数组格式的结果。""" % {
        'count': int(count or 1),
        'schema': json.dumps(schema, ensure_ascii=False, indent=2)}
    content, err = chat(config, prompt)
    if err:
        return None, err
    data = _parse_json_content(content)
    if data is None:
        return {'data': [], 'raw_content': content}, None
    return {'data': data}, None


def normalize_parameter_names(parameters):
    """AI 规范化参数命名（role=naming）"""
    if not parameters:
        return None, '请提供参数列表'
    config = _active_config('naming')
    if not config:
        return None, '未找到可用的参数命名规范化AI配置（AI服务配置里添加 role=命名规范 并启用）'
    params_info = '\n'.join('- %s: %s' % (p.get('key', ''), p.get('value', ''))
                            for p in parameters)
    prompt = """请对以下API参数名称进行规范化处理，使其符合RESTful API命名规范：

%(params)s

请返回JSON格式的结果，包含：
1. 原始参数名
2. 建议的规范化参数名（使用小写字母、下划线分隔、语义清晰）
3. 修改原因

返回格式示例：
[
  {"original": "userName", "suggested": "user_name", "reason": "使用下划线分隔单词，符合命名规范"}
]""" % {'params': params_info}
    content, err = chat(config, prompt)
    if err:
        return None, err
    data = _parse_json_content(content)
    if data is None:
        return {'suggestions': [], 'raw_content': content}, None
    return {'suggestions': data}, None


def extract_documentation(request_id):
    """AI 生成接口 Markdown 文档（role=doc_extractor）"""
    req = store.requests.get(request_id)
    if not req:
        return None, '请求不存在'
    config = _active_config('doc_extractor')
    if not config:
        return None, '未找到可用的API文档提取AI配置（AI服务配置里添加 role=文档提取 并启用）'
    prompt = """请根据以下API请求信息，生成详细的API文档：

请求方法: %(method)s
请求URL: %(url)s
请求头: %(headers)s
URL参数: %(params)s
请求体: %(body)s
描述: %(desc)s

请生成包含以下内容的API文档：
1. 接口概述
2. 请求参数说明（包括路径参数、查询参数、请求头、请求体）
3. 响应示例
4. 错误码说明

请以Markdown格式返回文档内容。""" % {
        'method': req.get('method', ''), 'url': req.get('url', ''),
        'headers': json.dumps(req.get('headers') or [], ensure_ascii=False),
        'params': json.dumps(req.get('params') or {}, ensure_ascii=False),
        'body': json.dumps(req.get('body') or {}, ensure_ascii=False),
        'desc': req.get('description', '')}
    content, err = chat(config, prompt)
    if err:
        return None, err
    return {'documentation': content}, None
