# -*- coding: utf-8 -*-
"""接口测试 · 定时任务调度器（移植自 testhub run_all_scheduled_tasks 管理命令 + ScheduledTask 模型语义）

- 触发器：CRON（croniter）/ INTERVAL（固定间隔秒）/ ONCE（单次执行时间）；
- 任务类型：TEST_SUITE（套件执行）/ API_REQUEST（单请求执行）；
- 状态机：ACTIVE / PAUSED / COMPLETED / FAILED，统计 last/next/total/success/failed；
- 调度循环：后台 daemon 线程每 60s 检查到期任务，与 testhub 的 while True + sleep(60) 一致；
- 通知：webhook POST（email 留配置字段，SMTP 参数从 settings 读取，未配置则跳过）。
任务数据持久化走 YAML 存储层（tasks / task_logs）。
"""
import logging
import threading
import time
from datetime import datetime, timedelta

from web_platform.api_testing import yaml_store as store
from web_platform.api_testing.executor import execute_suite, execute_single_request, run_in_thread

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60     # 检查间隔（秒），与 testhub 调度命令默认值一致


def calculate_next_run(task, now=None):
    """计算下次运行时间（移植 ScheduledTask.calculate_next_run）→ 返回 epoch 秒或 None"""
    now = now or datetime.now()
    try:
        if task.get('trigger_type') == 'CRON' and task.get('cron_expression'):
            from croniter import croniter
            it = croniter(task['cron_expression'], now)
            return int(it.get_next(datetime).timestamp())
        if task.get('trigger_type') == 'INTERVAL' and task.get('interval_seconds'):
            return int((now + timedelta(seconds=int(task['interval_seconds']))).timestamp())
        if task.get('trigger_type') == 'ONCE' and task.get('execute_at'):
            # execute_at 存 epoch 秒
            return int(task['execute_at']) if int(task['execute_at']) > int(now.timestamp()) else None
    except Exception as e:
        logger.warning('计算下次运行时间失败: %s', e)
    return None


def _ts():
    return int(time.time())


def _notify_wanted(task, success):
    """通知开关判定：任务级配置优先（notify_on_success/failure），未配置回退全局设置。
    notification_type: email|webhook|both（对应 testhub TaskNotificationSetting.notification_type）"""
    cfg = store.get_settings()
    ntype = task.get('notification_type') or 'both'
    want_task = task.get('notify_on_success') if success else task.get('notify_on_failure')
    if want_task is None:
        want_task = cfg.get('notify_on_success') if success else cfg.get('notify_on_failure')
    if not want_task:
        return []
    channels = []
    if ntype in ('email', 'both'):
        channels.append('email')
    if ntype in ('webhook', 'both'):
        channels.append('webhook')
    return channels


def _notify_log(task, channel, ok, content, recipient_info=None, bot_info=None,
                error='', response_info=None, sender_email=''):
    """每次发送（成功/失败）写 NotificationLog（与 testhub NotificationLog 字段同名）"""
    store.notification_logs.create({
        'task_id': task.get('id'), 'task_name': task.get('name', ''),
        'task_type': task.get('task_type', ''), 'notification_type': 'task_execution',
        'channel': channel, 'sender_name': 'AutomationTest平台',
        'sender_email': sender_email,
        'recipient_info': recipient_info or [], 'webhook_bot_info': bot_info or {},
        'notification_content': content[:2000],
        'status': 'success' if ok else 'failed', 'error_message': str(error or '')[:500],
        'response_info': response_info or {}, 'sent_at': int(time.time()),
    })
    store.trim_logs()


def _dingtalk_sign(secret):
    """钉钉加签：timestamp\nsecret HMAC-SHA256 → urlencode signature（同 testhub）"""
    import base64
    import hashlib
    import hmac
    import urllib.parse
    ts = str(round(time.time() * 1000))
    sign = base64.b64encode(hmac.new(secret.encode(), ('%s\n%s' % (ts, secret)).encode(),
                                     hashlib.sha256).digest())
    return ts, urllib.parse.quote_plus(sign)


def _send_webhook_bot(bot, content):
    """按机器人类型发 webhook：企微 markdown / 飞书 interactive / 钉钉 加签 markdown / 通用 text"""
    import requests as _rq
    btype = (bot.get('type') or 'generic').lower()
    url = bot.get('webhook_url') or ''
    if btype == 'wechat':
        payload = {'msgtype': 'markdown', 'markdown': {'content': content}}
    elif btype == 'feishu':
        color = 'green'
        payload = {'msg_type': 'interactive',
                   'card': {'config': {'wide_screen_mode': True},
                            'header': {'title': {'tag': 'plain_text', 'content': '接口测试通知'},
                                       'template': color},
                            'elements': [{'tag': 'div', 'text': {'tag': 'lark_md', 'content': content}}]}}
    elif btype == 'dingtalk':
        payload = {'msgtype': 'markdown', 'markdown': {'title': '接口测试通知', 'text': content}}
        if bot.get('secret'):
            ts, sign = _dingtalk_sign(bot['secret'])
            sep = '& ' if '?' in url else '?'
            url = '%s%stimestamp=%s&sign=%s' % (url, sep, ts, sign)
    else:
        payload = {'text': content}
    resp = _rq.post(url, json=payload, timeout=10)
    return resp.status_code, (resp.text or '')[:500]


def _send_notification(task, log, success):
    """通知：webhook 多机器人 + 邮件，逐渠道写通知日志；失败不阻塞调度。
    收件人 = 任务 notify_emails（回退全局）；机器人 = 设置里 enabled 的 bots（旧单 url 兼容）。"""
    channels = _notify_wanted(task, success)
    if not channels:
        return
    cfg = store.get_settings()
    title = '定时任务「%s」%s' % (task.get('name'), '执行成功' if success else '执行失败')
    result = log.get('result') or {}
    brief = ('结果: %s\n状态: %s\n通过/总数: %s/%s\n结束时间: %s' % (
        '成功' if success else '失败', log.get('status'),
        result.get('passed_requests', result.get('success', '-')),
        result.get('total_requests', '-'), log.get('end_time')))
    content = '**%s**\n%s' % (title, brief)
    if log.get('error_message'):
        content += '\n错误: %s' % log['error_message']

    emails = task.get('notify_emails') if task.get('notify_emails') else cfg.get('notify_emails') or []
    if 'webhook' in channels:
        bots = [b for b in (cfg.get('webhook_bots') or []) if b.get('enabled') and b.get('webhook_url')]
        if not bots and cfg.get('webhook_url'):
            bots = [{'name': '默认机器人', 'type': 'generic', 'webhook_url': cfg['webhook_url'],
                     'secret': '', 'enabled': True}]
        for bot in bots:
            bot_info = {'bot_type': bot.get('type'), 'bot_name': bot.get('name'),
                        'webhook_url': (bot.get('webhook_url') or '')[:50]}
            try:
                code, text = _send_webhook_bot(bot, content)
                _notify_log(task, 'webhook', code == 200, content,
                            recipient_info=[{'name': bot.get('name', ''), 'email': ''}],
                            bot_info=bot_info, error='' if code == 200 else 'HTTP %s' % code,
                            response_info={'status_code': code, 'body': text})
            except Exception as e:
                logger.warning('webhook 通知失败: %s', e)
                _notify_log(task, 'webhook', False, content,
                            recipient_info=[{'name': bot.get('name', ''), 'email': ''}],
                            bot_info=bot_info, error=str(e))
    if 'email' in channels and cfg.get('smtp_host') and emails:
        try:
            import smtplib
            from email.header import Header
            from email.mime.text import MIMEText
            body = '%s\n%s' % (title, brief)
            msg = MIMEText(body, 'plain', 'utf-8')
            msg['Subject'] = Header(title, 'utf-8')
            msg['From'] = cfg.get('smtp_from') or cfg['smtp_user']
            msg['To'] = ', '.join(emails)
            port = int(cfg.get('smtp_port') or 465)
            if cfg.get('smtp_use_ssl', True):
                server = smtplib.SMTP_SSL(cfg['smtp_host'], port, timeout=15)
            else:
                server = smtplib.SMTP(cfg['smtp_host'], port, timeout=15)
            try:
                if cfg.get('smtp_user'):
                    server.login(cfg['smtp_user'], cfg.get('smtp_password') or '')
                server.sendmail(msg['From'], emails, msg.as_string())
            finally:
                server.quit()
            _notify_log(task, 'email', True, body, recipient_info=[{'name': '', 'email': e} for e in emails],
                        sender_email=msg['From'])
        except Exception as e:
            logger.warning('邮件通知失败: %s', e)
            _notify_log(task, 'email', False, content,
                        recipient_info=[{'name': '', 'email': e} for e in emails],
                        error=str(e), sender_email=cfg.get('smtp_from') or cfg.get('smtp_user') or '')


def _execute_task_async(task, log):
    """后台线程执行任务并回写日志/统计（移植 _execute_task_async，去掉 Django）"""
    def execute():
        try:
            store.task_logs.update(log['id'], {'status': 'RUNNING', 'start_time': _ts()})
            if task.get('task_type') == 'TEST_SUITE':
                result = execute_suite(store.suites.get(task.get('suite_id')) or {},
                                       executed_by='scheduler:%s' % task.get('id'))
                success = result.get('status') == 'COMPLETED'
            elif task.get('task_type') == 'API_REQUEST':
                history = execute_single_request(task.get('request_id'),
                                                 task.get('environment_id'),
                                                 executed_by='scheduler:%s' % task.get('id'))
                ok = all(a.get('passed') for a in history.get('assertions_results') or []) \
                    and not history.get('error_message')
                success = bool(ok)
                result = {'history_id': history.get('id'), 'success': success,
                          'status_code': history.get('status_code')}
            else:
                raise ValueError('未知的任务类型: %s' % task.get('task_type'))

            store.task_logs.update(log['id'], {'status': 'COMPLETED' if success else 'FAILED',
                                               'end_time': _ts(), 'result': result})
            _update_task_stats(task['id'], success, result)
            fresh = store.tasks.get(task['id'])
            fresh_log = store.task_logs.get(log['id'])
            if fresh and fresh_log:
                _send_notification(fresh, fresh_log, success)
        except Exception as e:
            logger.exception('定时任务执行失败')
            store.task_logs.update(log['id'], {'status': 'FAILED', 'end_time': _ts(),
                                               'error_message': str(e)[:500]})
            _update_task_stats(task['id'], False, {})
    return run_in_thread(execute)


def _update_task_stats(task_id, success, result):
    """移植 ScheduledTask.update_run_stats：统计 +1、next_run 重算"""
    task = store.tasks.get(task_id)
    if not task:
        return
    patch = {
        'last_run_time': _ts(),
        'total_runs': int(task.get('total_runs') or 0) + 1,
        'successful_runs': int(task.get('successful_runs') or 0) + (1 if success else 0),
        'failed_runs': int(task.get('failed_runs') or 0) + (0 if success else 1),
        'last_result': result or {},
        'error_message': '' if success else str((result or {}).get('error', ''))[:500],
    }
    if task.get('trigger_type') == 'ONCE':
        patch['status'] = 'COMPLETED'       # 单次任务跑完即完成（与 testhub 一致）
        patch['next_run_time'] = None
    else:
        patch['next_run_time'] = calculate_next_run(task)
    store.tasks.update(task_id, patch)


def create_task_log(task):
    return store.task_logs.create({
        'task_id': task['id'], 'task_name': task.get('name'),
        'trigger': task.get('_trigger', 'scheduler'),
        'status': 'PENDING', 'start_time': None, 'end_time': None,
        'result': {}, 'error_message': '',
    })


def run_task_now(task_id, trigger='manual'):
    """立即执行（testhub ScheduledTaskViewSet.run_now）"""
    task = store.tasks.get(task_id)
    if not task:
        return None, '任务不存在'
    if task.get('status') == 'RUNNING_FLAG':
        return None, '任务正在运行'
    task['_trigger'] = trigger
    log = create_task_log(task)
    _execute_task_async(task, log)
    return log, ''


def check_due_tasks():
    """检查到期任务并触发（单次检查，供循环与测试调用）。返回本次触发数"""
    now = _ts()
    fired = 0
    for task in store.tasks.list(status='ACTIVE'):
        nxt = task.get('next_run_time')
        if not nxt:
            # 首次激活/历史数据缺 next_run_time → 立即补算
            store.tasks.update(task['id'], {'next_run_time': calculate_next_run(task)})
            continue
        if now >= int(nxt):
            run_task_now(task['id'], trigger='scheduler')
            fired += 1
    return fired


def _loop():
    while True:
        try:
            check_due_tasks()
        except Exception as e:
            logger.exception('调度循环出错: %s', e)
        time.sleep(CHECK_INTERVAL)


_started = False


def start_scheduler():
    """进程内启动调度线程（Flask 启动时调用一次，daemon 不阻塞退出）"""
    global _started
    if _started:
        return
    _started = True
    run_in_thread(_loop)
    logger.info('接口测试定时任务调度器已启动（每 %ds 检查一次）', CHECK_INTERVAL)
