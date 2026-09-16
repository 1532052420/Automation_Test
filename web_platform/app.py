# -*- coding: utf-8 -*-
"""App UI 自动化测试平台 · Web 入口（Flask :8080）

启动：.venv/bin/python web_platform/app.py
入口：./run.sh platform
"""
import os
import sys

# 直接运行本脚本时 sys.path[0] 是 web_platform/ 目录，先把项目根注入再 import 本包
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask

from web_platform.runtime_config import BASE_DIR, WebPlatformConfig

# 框架路径均为相对项目根（config/app_ui_tmp/、output/runs/ 等），统一切到项目根
os.chdir(BASE_DIR)

PLATFORM_CFG = WebPlatformConfig()

app = Flask(__name__,
            static_folder=os.path.join(BASE_DIR, 'web_platform', 'static'),
            static_url_path='/static',
            template_folder=os.path.join(BASE_DIR, 'web_platform', 'templates'))

# 关闭强缓存（改完即刷，对齐元素定位器的开发体验）与全局 no-store
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


@app.after_request
def _no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


from web_platform.routes import bp as platform_bp
app.register_blueprint(platform_bp)

# 代码审查（框架调试）：独立蓝图，纯增量，详见 代码调试/ 目录
from web_platform.debug_routes import bp as debug_bp
app.register_blueprint(debug_bp)

# 管理后台（用例/元素/页面对象 上传与管理）：独立蓝图
from web_platform.admin_routes import bp as admin_bp
app.register_blueprint(admin_bp)

# 元素定位器并入平台（原 8001 独立服务取消）：挂载到 /locator 子路径。
# DispatcherMiddleware 会剥掉 /locator 前缀并处理 /locator → /locator/ 补斜杠跳转，
# 定位器自身的路由（/api/*、/static/*）完全不用改；其前端已改为相对路径请求。
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from element_locator.server import app as locator_app
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {'/locator': locator_app})


if __name__ == '__main__':
    print('App UI 自动化测试平台已启动: http://127.0.0.1:%d/' % PLATFORM_CFG.port)
    print('  若 8080 被占用，可用环境变量 WEB_PLATFORM_PORT=<端口> 覆盖')
    app.run(host='127.0.0.1', port=PLATFORM_CFG.port, debug=False)