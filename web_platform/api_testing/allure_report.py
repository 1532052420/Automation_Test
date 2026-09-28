# -*- coding: utf-8 -*-
"""接口测试 · Allure 报告生成（移植自 testhub TestExecutionViewSet.generate_allure_report）

流程：执行记录 results → 手写 Allure2 结果 JSON（container + 每请求 result）→
subprocess 调 allure CLI 生成完整报告 → 另写自定义 summary.html 作为入口概览页。
产物目录对齐平台 output/ 约定：output/api_testing/{allure-results,allure-reports}/execution_<id>/
"""
import json
import logging
import os
import shutil
import subprocess
import time

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output', 'api_testing')


def _results_dir(eid):
    return os.path.join(OUTPUT_DIR, 'allure-results', 'execution_%s' % eid)


def report_dir(eid):
    return os.path.join(OUTPUT_DIR, 'allure-reports', 'execution_%s' % eid)


def summary_url(eid):
    return '/api-testing/report/execution_%s/summary.html' % eid


def _find_allure():
    """allure CLI 定位：项目自带（testhub 复制来的发行版）→ 系统路径 → PATH"""
    candidates = [
        os.path.join(BASE_DIR, 'allure', 'bin', 'allure'),
        '/usr/local/bin/allure', '/usr/bin/allure',
        shutil.which('allure') or '',
    ]
    for p in candidates:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _java_ok():
    try:
        r = subprocess.run(['java', '-version'], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _env(env_id):
    from web_platform.api_testing import yaml_store as store
    e = store.environments.get(env_id) if env_id else None
    return (e or {}).get('name') or '-'


def write_result_files(execution):
    """执行记录 → Allure2 结果 JSON（container + 每请求 result，结构与 testhub 相同）"""
    eid = execution['id']
    results_dir = _results_dir(eid)
    os.makedirs(results_dir, exist_ok=True)
    suite_name = execution.get('suite_name') or ('套件 #%s' % eid)
    container = {'uuid': str(eid), 'name': suite_name,
                 'children': ['%s-%s' % (eid, i) for i in range(len(execution.get('results') or []))]}
    with open(os.path.join(results_dir, '%s-container.json' % eid), 'w', encoding='utf-8') as f:
        json.dump(container, f, ensure_ascii=False, indent=2)
    now_ms = int(time.time() * 1000)
    for i, result in enumerate(execution.get('results') or []):
        item = {
            'uuid': '%s-%s' % (eid, i),
            'name': result.get('name', '测试请求 %s' % (i + 1)),
            'status': 'passed' if result.get('passed') else 'failed',
            'stage': 'finished',
            'start': now_ms - 1000, 'stop': now_ms,
            'description': 'Method: %s\nURL: %s' % (result.get('method', 'GET'), result.get('url', '')),
            'historyId': '%s-%s' % (execution.get('suite_id'), i),
            'fullName': '%s / %s' % (suite_name, result.get('name', '请求 %s' % (i + 1))),
            'links': [],
            'labels': [
                {'name': 'suite', 'value': suite_name},
                {'name': 'testClass', 'value': suite_name},
                {'name': 'package', 'value': 'api_testing'},
                {'name': 'project', 'value': execution.get('project_name') or '-'},
            ],
            'parameters': [
                {'name': 'method', 'value': result.get('method', 'GET')},
                {'name': 'url', 'value': result.get('url', '')},
                {'name': 'environment', 'value': _env(execution.get('environment_id'))},
            ],
            'steps': [
                {'name': '发送请求', 'status': 'passed', 'stage': 'finished',
                 'start': now_ms - 1000, 'stop': now_ms - 500, 'steps': []},
                {'name': '验证响应', 'status': 'passed' if result.get('passed') else 'failed',
                 'stage': 'finished', 'start': now_ms - 500, 'stop': now_ms, 'steps': []},
            ],
        }
        if result.get('error'):
            item['statusDetails'] = {'message': result['error'], 'trace': ''}
        with open(os.path.join(results_dir, '%s-%s-result.json' % (eid, i)), 'w', encoding='utf-8') as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
    return results_dir


def write_summary(execution):
    """自定义 summary.html 概览页（样式与结构移植 testhub，绿/红状态卡 + 逐请求明细）"""
    eid = execution['id']
    suite_name = execution.get('suite_name') or ('套件 #%s' % eid)
    status_text = {'COMPLETED': '已完成', 'FAILED': '执行失败', 'RUNNING': '执行中',
                   'PENDING': '待执行', 'CANCELLED': '已取消'}.get(execution.get('status'), execution.get('status') or '-')
    status_class = 'status-passed' if execution.get('status') == 'COMPLETED' else 'status-failed'
    created = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(execution.get('created_at') or time.time()))
    rows = []
    for i, r in enumerate(execution.get('results') or []):
        ok = bool(r.get('passed'))
        rows.append("""
            <div class="test-result-item %(cls)s">
                <div class="test-header">
                    <span class="test-method method-%(m)s">%(m)s</span>
                    <span class="test-name">%(name)s</span>
                    <span style="margin-left:auto">%(oktext)s</span>
                </div>
                <div class="test-url">%(url)s</div>
                %(err)s
            </div>""" % {
            'cls': 'passed' if ok else 'failed', 'm': (r.get('method') or 'GET').lower(),
            'name': r.get('name', '测试请求 %s' % (i + 1)),
            'oktext': '<b style="color:#4caf50">通过</b>' if ok else '<b style="color:#f44336">失败</b>',
            'url': r.get('url') or '',
            'err': ('<div class="test-error"><strong>错误:</strong> %s</div>' % r.get('error')) if r.get('error') else '',
        })
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>测试报告概览 - %(suite)s</title>
<style>
  body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; background: #f5f7fa; color: #333; }
  .header { background: linear-gradient(135deg,#667eea 0%%,#764ba2 100%%); color: #fff; box-shadow: 0 2px 10px rgba(0,0,0,.1); }
  .header-content { display: flex; justify-content: space-between; align-items: flex-start; padding: 2rem; max-width: 1200px; margin: 0 auto; }
  .allure-report-btn { display: inline-block; padding: .8rem 1.5rem; background: rgba(255,255,255,.2); color: #fff;
    border: 2px solid rgba(255,255,255,.3); border-radius: 6px; text-decoration: none; font-weight: bold; }
  .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
  .summary-card, .test-results { background: #fff; border-radius: 10px; padding: 2rem; margin-bottom: 2rem; box-shadow: 0 2px 10px rgba(0,0,0,.1); }
  .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1rem; }
  .summary-item { text-align: center; padding: 1rem; border-radius: 8px; }
  .summary-item.total { background: #e3f2fd; } .summary-item.passed { background: #e8f5e9; } .summary-item.failed { background: #ffebee; }
  .summary-number { font-size: 2rem; font-weight: bold; display: block; }
  .status-badge { display: inline-block; padding: .5rem 1rem; border-radius: 20px; font-weight: bold; }
  .status-passed { background: #4caf50; color: #fff; } .status-failed { background: #f44336; color: #fff; }
  .test-result-item { padding: 1rem; border-left: 4px solid #eee; margin-bottom: 1rem; border-radius: 4px; }
  .test-result-item.passed { border-left-color: #4caf50; background: #f8fff8; }
  .test-result-item.failed { border-left-color: #f44336; background: #fff8f8; }
  .test-header { display: flex; align-items: center; gap: .5rem; margin-bottom: .5rem; }
  .test-method { display: inline-block; padding: .2rem .5rem; border-radius: 4px; font-size: .9rem; color: #fff; background: #2196f3; }
  .method-post { background: #4caf50; } .method-put { background: #ff9800; } .method-delete, .method-patch { background: #f44336; }
  .test-url { color: #666; font-size: .9rem; margin: .5rem 0; word-break: break-all; }
  .test-error { color: #f44336; font-size: .9rem; margin-top: .5rem; padding: .5rem; background: #ffebee; border-radius: 4px; }
  .footer { text-align: center; margin-top: 2rem; padding: 1rem; color: #666; }
</style>
</head>
<body>
  <div class="header"><div class="header-content">
    <div><h1>接口测试报告</h1><p>测试套件: %(suite)s</p><p>项目: %(project)s</p></div>
    <div style="align-self:flex-end"><a class="allure-report-btn" href="index.html" target="_blank">查看完整Allure报告</a></div>
  </div></div>
  <div class="container">
    <div class="summary-card">
      <div class="status-row"><span class="status-badge %(scls)s">状态: %(stext)s</span>
        <span style="color:#666;margin-left:1rem">执行时间: %(created)s</span></div>
      <div class="summary-grid">
        <div class="summary-item total"><span class="summary-number">%(total)s</span><span class="summary-label">总请求数</span></div>
        <div class="summary-item passed"><span class="summary-number">%(passed)s</span><span class="summary-label">通过数</span></div>
        <div class="summary-item failed"><span class="summary-number">%(failed)s</span><span class="summary-label">失败数</span></div>
      </div>
    </div>
    <div class="test-results"><h2>测试结果详情</h2>%(rows)s
    </div>
    <div class="footer"><p>报告生成时间: %(now)s</p></div>
  </div>
</body>
</html>""" % {
        'suite': suite_name, 'project': execution.get('project_name') or '-',
        'scls': status_class, 'stext': status_text, 'created': created,
        'total': execution.get('total_requests') or 0,
        'passed': execution.get('passed_requests') or 0,
        'failed': execution.get('failed_requests') or 0,
        'rows': '\n'.join(rows),
        'now': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    out = report_dir(eid)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'summary.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    return out


def generate(execution):
    """生成完整报告。返回 (report_url, None) 或 (None, 错误消息)"""
    eid = execution['id']
    try:
        write_result_files(execution)
        allure = _find_allure()
        java = _java_ok()
        out = report_dir(eid)
        if not allure:
            logger.warning('allure CLI 不可用，仅生成概览报告')
        elif not java:
            logger.warning('Java 不可用，仅生成概览报告')
        else:
            if os.path.isdir(out):
                shutil.rmtree(out, ignore_errors=True)
            os.makedirs(out, exist_ok=True)
            last_err = ''
            for attempt in range(3):
                try:
                    r = subprocess.run([allure, 'generate', _results_dir(eid), '--clean',
                                        '--output', out], capture_output=True, text=True, timeout=60)
                    if r.returncode == 0:
                        break
                    last_err = (r.stderr or '')[-400:]
                except subprocess.TimeoutExpired:
                    last_err = 'allure 命令超时'
                time.sleep(1)
            else:
                return None, 'Allure 报告生成失败: %s（请检查 Java/Allure 环境）' % last_err
        write_summary(execution)
        return summary_url(eid), None
    except Exception as e:
        logger.exception('生成Allure报告失败')
        return None, str(e)
