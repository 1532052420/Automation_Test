# -*- coding: utf-8 -*-
"""OmniParser 独立工具服务（FastAPI，默认 127.0.0.1:8090）。

完全独立：不 import 自动化测试框架的任何模块；配置只读写本目录 config.yaml。
接口：
  GET  /                工具页面
  GET  /api/ping        存活探测（平台首页卡片状态灯用）
  POST /api/parse       上传截图 → 元素清单
  POST /api/generate    意图 + 元素清单 → Selenium 代码
  GET  /api/config      读配置（api_key 打码）
  POST /api/config      保存配置（写回 config.yaml）
"""
import io
import os

import yaml
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import llm_client
from parser import OmniParser

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, 'config.yaml')
STATIC = os.path.join(BASE, 'static')

app = FastAPI(title='OmniParser 屏幕解析（独立工具）')
# 平台首页卡片状态灯会跨域探测 /api/ping，放开只读探测
app.add_middleware(CORSMiddleware, allow_origins=['*'],
                    allow_methods=['GET'], allow_headers=['*'])
_parser = None
_parse_error = None


def load_config():
    with open(CFG_PATH, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def save_config(cfg):
    with open(CFG_PATH, 'w', encoding='utf-8') as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def get_parser():
    """懒加载单例：模型几 GB，首次解析才加载；失败信息缓存给前端展示。"""
    global _parser, _parse_error
    if _parse_error:
        raise RuntimeError(_parse_error)
    if _parser is None:
        cfg = load_config().get('parser') or {}
        _parser = OmniParser(
            model_dir=cfg.get('model_dir') or 'models',
            device=cfg.get('device') or 'auto',
            conf_threshold=cfg.get('conf_threshold', 0.05),
            iou_threshold=cfg.get('iou_threshold', 0.45))
        try:
            _parser.load()
        except Exception as e:               # 模型缺失/加载失败 → 明确报给前端
            _parser = None
            _parse_error = str(e)
            raise RuntimeError(_parse_error)
    return _parser


@app.get('/')
def index():
    return FileResponse(os.path.join(STATIC, 'index.html'))


@app.get('/api/ping')
def ping():
    cfg = load_config()
    return {'ok': True, 'service': 'omni_parser',
            'device': (cfg.get('parser') or {}).get('device') or 'auto',
            'models_loaded': bool(_parser and _parser.loaded)}


@app.post('/api/parse')
def api_parse(file: UploadFile = File(None), image_b64: str = Form(None)):
    import base64
    from PIL import Image
    raw = file.file.read() if file is not None else base64.b64decode(
        (image_b64 or '').split(',', 1)[-1])
    if not raw:
        return JSONResponse({'ok': False, 'msg': '未收到截图'}, status_code=400)
    try:
        image = Image.open(io.BytesIO(raw)).convert('RGB')
        result = get_parser().parse(image)
    except RuntimeError as e:
        return JSONResponse({'ok': False, 'msg': str(e)}, status_code=503)
    except Exception as e:
        return JSONResponse({'ok': False, 'msg': '解析失败：%s' % e}, status_code=500)
    return {'ok': True, **result}


@app.post('/api/generate')
def api_generate(intent: str = Form(''), elements: str = Form('[]'),
                 image_size: str = Form('')):
    import json
    try:
        els = json.loads(elements)
    except Exception:
        els = []
    try:
        size = json.loads(image_size) if image_size else None
        code = llm_client.generate_code(load_config().get('llm') or {},
                                        intent, els, size)
    except llm_client.LLMError as e:
        return JSONResponse({'ok': False, 'msg': str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({'ok': False, 'msg': '生成失败：%s' % e}, status_code=500)
    return {'ok': True, 'code': code}


@app.get('/api/config')
def api_config_get():
    cfg = load_config()
    llm = cfg.get('llm') or {}
    key = llm.get('api_key') or ''
    if len(key) > 8:                        # 打码返回，前端只回显首尾
        llm['api_key_masked'] = key[:4] + '****' + key[-4:]
    else:
        llm['api_key_masked'] = key
    return {'ok': True, 'config': cfg}


@app.post('/api/config')
def api_config_post(llm_base_url: str = Form(''), llm_api_key: str = Form(''),
                    llm_model: str = Form(''), conf_threshold: float = Form(None),
                    port: int = Form(None)):
    cfg = load_config()
    llm = cfg.setdefault('llm', {})
    if llm_base_url:
        llm['base_url'] = llm_base_url
    if llm_api_key and '****' not in llm_api_key:   # 打码值原样传回时不覆盖
        llm['api_key'] = llm_api_key
    if llm_model:
        llm['model'] = llm_model
    if conf_threshold is not None:
        cfg.setdefault('parser', {})['conf_threshold'] = conf_threshold
        global _parser, _parse_error
        if _parser is not None:
            _parser.conf = float(conf_threshold)
    if port:
        cfg.setdefault('server', {})['port'] = int(port)
    save_config(cfg)
    return {'ok': True, 'msg': '已保存（端口改动需重启服务）'}


if __name__ == '__main__':
    import uvicorn
    port = int((load_config().get('server') or {}).get('port') or 8090)
    uvicorn.run(app, host='127.0.0.1', port=port)
