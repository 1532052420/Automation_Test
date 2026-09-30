# -*- coding: utf-8 -*-
"""视觉测试 · 页面与 REST 路由（独立模块，URL 前缀 /visual）

Maestro 流程管理 + 运行 + 截图比对看板；数据自管（data/ 目录），不读平台其他模块。
"""
import os

from flask import Blueprint, jsonify, render_template, request, send_file

from web_platform.visual_testing import runner

bp = Blueprint('visual_testing', __name__, url_prefix='/visual')


@bp.route('/')
def page():
    return render_template('visual.html')


# ---------------- 流程管理 ----------------
@bp.route('/api/flows')
def api_flows():
    return jsonify({'ok': True, 'flows': runner.list_flows()})


@bp.route('/api/flows/<name>')
def api_flow_content(name):
    p = runner.flow_path(name)
    if not p:
        return jsonify({'ok': False, 'msg': '流程不存在'}), 404
    with open(p, encoding='utf-8') as f:
        return jsonify({'ok': True, 'content': f.read()})


@bp.route('/api/flows', methods=['POST'])
def api_save_flow():
    d = request.get_json(silent=True) or {}
    ok, msg = runner.save_flow(d.get('name'), d.get('content'))
    return jsonify({'ok': ok, 'msg': msg})


@bp.route('/api/flows/<name>', methods=['DELETE'])
def api_delete_flow(name):
    ok, msg = runner.delete_flow(name)
    return jsonify({'ok': ok, 'msg': msg})


# ---------------- 运行 ----------------
@bp.route('/api/runs', methods=['POST'])
def api_start_run():
    d = request.get_json(silent=True) or {}
    run_id, msg = runner.start_run(d.get('flow'))
    return jsonify({'ok': bool(run_id), 'run_id': run_id, 'msg': msg})


@bp.route('/api/runs')
def api_runs():
    return jsonify({'ok': True, 'runs': runner.list_runs()})


@bp.route('/api/runs/<run_id>')
def api_run_detail(run_id):
    r = runner.get_run(run_id)
    if not r:
        return jsonify({'ok': False, 'msg': '运行记录不存在'}), 404
    return jsonify({'ok': True, **r})


@bp.route('/api/runs/<run_id>/stop', methods=['POST'])
def api_stop_run(run_id):
    ok, msg = runner.stop_run(run_id)
    return jsonify({'ok': ok, 'msg': msg})


@bp.route('/api/runs/<run_id>/baseline', methods=['POST'])
def api_adopt_baseline(run_id):
    d = request.get_json(silent=True) or {}
    ok, msg = runner.adopt_baseline(run_id, d.get('shot'))
    return jsonify({'ok': ok, 'msg': msg})


# ---------------- 图片服务（严格限制在 data 目录内，防路径穿越） ----------------
@bp.route('/api/img')
def api_img():
    rel = (request.args.get('path') or '').strip()
    root = os.path.realpath(runner.DATA_DIR)
    p = os.path.realpath(os.path.join(root, rel)) if rel else ''
    if not rel or not p.startswith(root + os.sep) or not p.endswith('.png') or not os.path.isfile(p):
        return jsonify({'ok': False, 'msg': '图片不存在'}), 404
    return send_file(p)
