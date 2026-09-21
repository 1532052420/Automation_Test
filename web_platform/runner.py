# -*- coding: utf-8 -*-
"""Web 执行平台 · ExecutionManager

职责（对齐技术方案）：
- 创建执行任务（run_id，独立目录 output/runs/{run_id}/）
- 准备 pytest 前置（pytest.ini、执行上下文文件、前置校验）
- subprocess 独立进程跑 pytest（不阻塞 Web，浏览器关闭不影响执行）
- 实时收集日志（内存环形缓冲 + 落盘）
- 状态机 PENDING / RUNNING / PASSED / FAILED / STOPPED / ERROR
- 停止（进程组 SIGTERM → 超时 SIGKILL）
- 结果解析与归档（result.json）

支持两类任务（kind）：
- app_ui：设备自动化。前置校验 Appium / adb 在线 / App 已安装，写 config/app_ui_tmp/<pid> 设备文件。
两类任务只有「前置校验 + 上下文文件」不同，其余机制完全共用。

约束：第一版串行，同一时刻只允许 1 个执行任务；设备配置仅取第一台。
"""
import os
import re
import shutil
import signal
import subprocess
import json
import sys
import threading
import time
import ujson

from common.pytest import deal_pytest_ini_file
from web_platform.runtime_config import (
    BASE_DIR,
    adb_devices,
    check_appium,
    parse_devices_info,
)

RUNS_DIR = os.path.join(BASE_DIR, 'output', 'runs')
APP_UI_TMP_DIR = os.path.join(BASE_DIR, 'config', 'app_ui_tmp')
PYTHON_BIN = sys.executable or os.path.join(BASE_DIR, '.venv', 'bin', 'python')

# 任务级超时(秒)：设备/驱动挂起时客户端可能永久阻塞，超时强杀并标 ERROR 上报
RUN_TIMEOUT_SECONDS = 30 * 60

# pytest -v 进度行两种形态：
# 1) 未开 log_cli 时 node 与结果同行：cases/...py::C::m PASSED [100%]
# 2) 平台启用 --log-cli-level=INFO 后结果词独立成行：PASSED [100%]
_PROGRESS_RE = re.compile(r'(?:::[^ ]+\s+)?(PASSED|FAILED|ERROR|SKIPPED)(?:\s+\[\s*\d+%\])?\s*$')


def _now_str():
    return time.strftime('%Y-%m-%d %H:%M:%S')


EXEC_CLEANUP_FILE = os.path.join(BASE_DIR, 'config', 'exec_cleanup.json')


def _cleanup_cfg():
    """「前后置清理」卡片保存的持久化配置（文件缺失/损坏按全关处理）"""
    try:
        with open(EXEC_CLEANUP_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    return bool(cfg.get('setup_reset')), bool(cfg.get('teardown_reset'))


class ExecutionManager(object):
    """执行任务生命周期管理器（进程内单例）。"""

    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()
        # 启动锁：串行化 start_run 主体，消除"互斥检查→任务注册"窗口期的并发双任务竞态
        self._start_lock = threading.Lock()
        self._run_seq = self._next_run_seq()

    # ------------------------------------------------------------------ 查询
    def _next_run_seq(self):
        """下一个 run 序号：按 output/runs 现有 run_id 里的日期取当天序号+1"""
        day = time.strftime('%Y%m%d')
        seq = 0
        if os.path.isdir(RUNS_DIR):
            for name in os.listdir(RUNS_DIR):
                m = re.match(r'^%s_(\d{3})$' % day, name)
                if m:
                    seq = max(seq, int(m.group(1)))
        return seq + 1

    def get_task(self, run_id):
        with self._lock:
            task = self._tasks.get(run_id)
            if task:
                return self._public_task(task)
        # 服务重启后内存态丢失，从磁盘 result.json 回退（历史任务只读）
        return self._load_disk_task(run_id)

    @staticmethod
    def _normalize_disk_task(task):
        """磁盘历史任务归一：平台重启后进程已不存在，残留的 RUNNING/PENDING（幽灵任务）
        归一为 ERROR 并注明原因，避免历史列表永远显示「执行中"""
        if task.get('status') in ('PENDING', 'RUNNING'):
            task['status'] = 'ERROR'
            reason = '平台重启，任务中断（进程已不存在）'
            task['error_msg'] = ((task.get('error_msg') or '') + '；' + reason).lstrip('；')
            if not task.get('end_time'):
                task['end_time'] = task.get('start_time')
        return task

    def _load_disk_task(self, run_id):
        path = os.path.join(RUNS_DIR, run_id, 'result.json')
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return self._normalize_disk_task(ujson.loads(f.read()))
        except Exception:
            return None

    def list_tasks(self, limit=100):
        """历史任务（内存态 + 磁盘 result.json 合并），按 run_id 倒序"""
        from_disk = self._load_disk_tasks()
        with self._lock:
            tasks = list(from_disk)
            mem_ids = set()
            for t in self._tasks.values():
                mem_ids.add(t['run_id'])
                tasks = [x for x in tasks if x['run_id'] != t['run_id']]
                tasks.append(self._public_task(t))
            tasks.sort(key=lambda t: t['run_id'], reverse=True)
            return tasks[:limit]

    def running_task(self):
        with self._lock:
            for t in self._tasks.values():
                if t['status'] in ('PENDING', 'RUNNING'):
                    return self._public_task(t)
            return None

    def _load_disk_tasks(self):
        """扫描 output/runs/*/result.json，返回已持久化的历史任务（公开结构）"""
        tasks = []
        if not os.path.isdir(RUNS_DIR):
            return tasks
        for name in os.listdir(RUNS_DIR):
            result_path = os.path.join(RUNS_DIR, name, 'result.json')
            if os.path.isfile(result_path):
                try:
                    with open(result_path, 'r', encoding='utf-8') as f:
                        tasks.append(self._normalize_disk_task(ujson.loads(f.read())))
                except Exception:
                    continue
        return tasks

    def _public_task(self, task):
        """对外暴露的任务结构（去掉进程/流等内部对象）"""
        return {
            'run_id': task['run_id'],
            'status': task['status'],
            'kind': task.get('kind', 'app_ui'),
            'env': task.get('env', ''),
            'owner': task.get('owner', ''),
            'marker': task.get('marker', ''),
            'start_time': task['start_time'],
            'end_time': task['end_time'],
            'conf_file': task['conf_file'],
            'device_desc': task['device_desc'],
            'device_model': task.get('device_model', ''),
            'app_package': task['app_package'],
            'udid': task['udid'],
            'overrides': task.get('overrides', {}),
            'case_nodes': task['case_nodes'],
            'total': task['total'],
            'passed': task['passed'],
            'failed': task['failed'],
            'error': task['error'],
            'skipped': task['skipped'],
            'exit_code': task['exit_code'],
            'error_msg': task['error_msg'],
            'allure_dir': task['allure_dir'],
            'log_path': task['log_path'],
            'report_dir': task['report_dir'],
            'stop_requested': task['stop_requested'],
        }

    def get_log(self, run_id, offset=0):
        """返回该任务从 offset 行起的日志（增量），以及最新 offset。
        服务重启后内存态丢失，回退读磁盘上的 run 日志文件。"""
        with self._lock:
            task = self._tasks.get(run_id)
            if task:
                lines = task['log_lines']
                return {'ok': True, 'lines': lines[offset:], 'offset': len(lines)}
        disk = self._load_disk_task(run_id)
        if disk and disk.get('log_path'):
            path = os.path.join(BASE_DIR, disk['log_path'])
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.read().splitlines()
                return {'ok': True, 'lines': lines[offset:], 'offset': len(lines)}
        return {'ok': False, 'msg': '任务不存在或日志不可用'}

    # ------------------------------------------------------------------ 创建
    def start_run(self, conf_file, case_nodes, overrides=None,
                  owner='', marker='', timeout_minutes=None,
                  setup_reset=None, teardown_reset=None):
        """创建并启动一个执行任务。case_nodes 为用例节点路径列表（文件/类/方法级）。

        APP UI 设备自动化专用执行器（接口测试已由 api_testing 模块独立承接）。
        overrides={udid?, appPackage?, appActivity?} 覆盖式生效（仅本次执行，不写回 conf 文件）。
        owner 为发起人（多人共用平台时区分谁跑的）；marker 为 pytest 标记表达式（-m）；
        timeout_minutes 覆盖默认任务超时。
        setup_reset/teardown_reset（设备配置「前置/后置清理」）：经环境变量 AT_SETUP_RESET /
        AT_TEARDOWN_RESET 下传 pytest——前置=首条用例前清 App 数据（Client 构造时一次），
        后置=全部用例结束后清一次（根 conftest.py 的 pytest_sessionfinish）。
        返回 (ok, run_id 或错误信息)。"""
        if not case_nodes:
            return False, '请至少选择一个用例'
        if not conf_file:
            return False, '请选择设备配置文件(conf)'
        with self._start_lock:
            return self._start_run_locked(conf_file, case_nodes, overrides,
                                          owner, marker, timeout_minutes,
                                          setup_reset, teardown_reset)

    def _start_run_locked(self, conf_file, case_nodes, overrides=None,
                          owner='', marker='', timeout_minutes=None,
                          setup_reset=None, teardown_reset=None):
        """启动主体（持有 _start_lock：校验与任务注册串行，互斥检查才会命中并发请求）"""
        with self._lock:
            for t in self._tasks.values():
                if t['status'] in ('PENDING', 'RUNNING'):
                    return False, '已有任务 %s 正在运行(%s)，请等待完成或先停止' % (
                        t['run_id'], t['status'])
            run_id = '%s_%03d' % (time.strftime('%Y%m%d'), self._run_seq)
            self._run_seq += 1

        # 1. 准备 pytest.ini（-c 强指，缺文件 pytest 直接报错）
        try:
            deal_pytest_ini_file()
        except Exception as e:
            return False, 'pytest.ini 准备失败: %s' % e

        # 2. 前置校验（放在建目录之前，失败不留孤儿目录）
        device_info = None
        current_capabilities = {}
        device_model = ''
        final_udid = ''
        # 2.1 解析设备配置（取第一台设备，第一版单选）
        devices_info = parse_devices_info(conf_file)
        if not devices_info:
            return False, '配置文件 %s 解析不到设备信息' % conf_file
        device_info = devices_info[0]
        capabilities = device_info.get('capabilities') or []
        if not capabilities:
            return False, '设备 %s 没有可用的 desired_capabilities' % device_info['device_desc']
        current_capabilities = capabilities[0]

        # 2.2 应用执行参数覆盖（udid/包名/Activity，仅本次执行生效）
        # 清理策略：未显式传参（None）时读「前后置清理」卡片保存的持久化配置
        saved_setup, saved_teardown = _cleanup_cfg()
        if setup_reset is None:
            setup_reset = saved_setup
        if teardown_reset is None:
            teardown_reset = saved_teardown
        overrides = {k: str(v).strip() for k, v in (overrides or {}).items()
                     if v and str(v).strip()}
        for key in ('udid', 'appPackage', 'appActivity'):
            if overrides.get(key):
                current_capabilities[key] = overrides[key]

        # 3. 前置校验
        # 3.1 Appium 可用
        ok, msg = check_appium(device_info['server_ip'], device_info['server_port'])
        if not ok:
            return False, 'Appium 不可用(%s:%s)：%s（先执行 ./run.sh start-appium）' % (
                device_info['server_ip'], device_info['server_port'], msg)
        # 3.2 目标设备 adb 在线（含 overrides 覆盖后的最终 udid），并取真实设备型号
        # （conf 的 devices_desc 只是人工起的别名，如 xiaomi；真实品牌型号以 adb 为准，如华为 FGD AL00）
        final_udid = current_capabilities.get('udid', '')
        adb = adb_devices()
        online_devices = [d for d in adb['devices'] if d['state'] == 'device']
        online = {d['udid'] for d in online_devices}
        if final_udid not in online:
            return False, '设备 %s 不在线（当前在线: %s）' % (
                final_udid, ', '.join(sorted(online)) or '无')
        device_model = next((d.get('model') or '' for d in online_devices
                             if d['udid'] == final_udid), '')

        # 3.3 被测 App 是否已安装——未装时 Appium 深处只报 "Activity class does not exist"，
        # 难以定位；这里提前给出明确提示（换新设备最常见的坑：设备是干净的，App 没装）
        check_package = current_capabilities.get('appPackage', '')
        if check_package:
            try:
                r = subprocess.run(['adb', '-s', final_udid, 'shell', 'pm', 'list', 'packages', check_package],
                                   capture_output=True, timeout=10)
                installed = ('package:%s' % check_package) in r.stdout.decode('utf-8', 'ignore')
            except Exception:
                installed = True  # 检查本身失败不拦截执行，交给 Appium 原有流程
            if not installed:
                return False, ('设备 %s(%s) 未安装被测 App「%s」，请先安装 APK 后重试。'
                               '安装命令: adb -s %s install <apk路径>') % (
                    final_udid, device_model or '未知型号', check_package, final_udid)

        # 4. 建运行目录与 allure 结果目录
        run_dir = os.path.join(RUNS_DIR, run_id)
        allure_dir = os.path.join(run_dir, 'allure-results')
        log_dir = os.path.join(run_dir, 'logs')
        try:
            os.makedirs(allure_dir, exist_ok=True)
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            return False, '创建运行目录失败: %s' % e
        log_path = os.path.join(log_dir, 'test_%s.log' % run_id)

        # 5. 写本次执行的上下文文件（框架按约定读的全局文件）
        tmp_files = []
        try:
            # APP UI：pytest 侧用 os.getppid() 找本进程写入的设备文件
            tmp_files = [os.path.join(APP_UI_TMP_DIR, str(os.getpid())),
                         os.path.join(APP_UI_TMP_DIR, '%s_current_desired_capabilities' % os.getpid())]
            os.makedirs(APP_UI_TMP_DIR, exist_ok=True)
            self._write_json(tmp_files[0], device_info)
            self._write_json(tmp_files[1], current_capabilities)
        except Exception as e:
            return False, '写执行临时文件失败: %s' % e

        task = {
            'run_id': run_id, 'status': 'PENDING',
            'kind': 'app_ui', 'owner': owner, 'marker': marker,
            'start_time': _now_str(), 'end_time': None,
            'conf_file': conf_file,
            'device_desc': device_info['device_desc'] if device_info else '',
            'device_model': device_model,
            'app_package': current_capabilities.get('appPackage', ''),
            'udid': final_udid,
            'overrides': overrides or {},
            'case_nodes': list(case_nodes),
            'total': len(case_nodes), 'passed': 0, 'failed': 0,
            'error': 0, 'skipped': 0,
            'exit_code': None, 'error_msg': '',
            'allure_dir': os.path.relpath(allure_dir, BASE_DIR).replace(os.sep, '/'),
            'log_path': os.path.relpath(log_path, BASE_DIR).replace(os.sep, '/'),
            'report_dir': '',
            'stop_requested': False,
            'process': None,
            'log_lines': [],
            'stop_flag': False,
            'tmp_files': tmp_files,
            'result_path': os.path.join(run_dir, 'result.json'),
        }
        with self._lock:
            self._tasks[run_id] = task

        # 6. 组装 pytest 命令并启动子进程（独立进程组，便于整组停止）
        #    --log-cli-level=INFO：appOperator 的 操作日志(点击/输入/toast/断言)实时打到 stdout，
        #    平台实时日志框与 logs/test.log 双通道收集
        #    注意：接口任务不需要额外参数——环境通过第 5 步写入的 config/tmp/env.json 传递，
        #    与 run_api_test.py 的 -e 语义一致（-e 是它的 argparse 参数，不是 pytest 参数）。
        pytest_args = [PYTHON_BIN, '-u', '-m', 'pytest', '-c', 'config/pytest.ini',
                       '-v', '--log-cli-level=INFO',
                       '--alluredir', os.path.relpath(allure_dir, BASE_DIR).replace(os.sep, '/')]
        if marker:
            pytest_args += ['-m', marker]
        pytest_args += list(case_nodes)
        try:
            proc = subprocess.Popen(
                pytest_args, cwd=BASE_DIR,
                start_new_session=True,
                # 清理策略（设备配置「前置/后置清理」）经环境变量下传：
                # 平台自身进程环境里没有这两个变量，必须显式传，不能靠继承
                env=dict(os.environ,
                         AT_SETUP_RESET='1' if setup_reset else '',
                         AT_TEARDOWN_RESET='1' if teardown_reset else ''),
                # 显式 DEVNULL：pytest 不需要 stdin。不指定会继承平台自身的 stdin，
                # 而平台被 nohup/systemd/Popen 以非终端方式启动时该 fd 可能已失效，
                # pytest 的 capture 会以 "saved filedescriptor not valid anymore" 崩掉，
                # 表现为任务 1 秒内 FAILED、无日志无明细。
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1)
        except Exception as e:
            task['status'] = 'ERROR'
            task['error_msg'] = '启动 pytest 失败: %s' % e
            task['end_time'] = _now_str()
            self._archive(task)
            return False, task['error_msg']

        task['process'] = proc
        task['status'] = 'RUNNING'
        # 超时可按任务覆盖（接口任务通常远短于设备任务）；下限 1 分钟防误填
        try:
            timeout_s = int(timeout_minutes) * 60 if timeout_minutes else RUN_TIMEOUT_SECONDS
        except (TypeError, ValueError):
            timeout_s = RUN_TIMEOUT_SECONDS
        timeout_s = max(60, timeout_s)
        task['timeout_seconds'] = timeout_s
        task['deadline'] = time.time() + timeout_s

        # 7. 后台线程：读日志流、统计进度、等进程结束、定终态、归档；看门狗独立计时防挂起
        threading.Thread(target=self._monitor, args=(task,), daemon=True).start()
        threading.Thread(target=self._watchdog, args=(task,), daemon=True).start()
        return True, run_id

    @staticmethod
    def _write_json(path, obj):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(ujson.dumps(obj, ensure_ascii=False))

    # ------------------------------------------------------------------ 监控
    def _monitor(self, task):
        proc = task['process']
        log_f = open(task['log_path'], 'w', encoding='utf-8')
        try:
            for raw in iter(proc.stdout.readline, b''):
                text = raw.decode('utf-8', 'ignore')
                # pytest 进度行用 \r 刷新（非 \n），binary readline 会把多次刷新拼成一块；
                # 按 \r/\n 都切段，保证每段独立入日志且结果统计(PASSED/FAILED...)可命中
                for seg in re.split(r'[\r\n]', text):
                    if not seg:
                        continue
                    task['log_lines'].append(seg)
                    log_f.write(seg + '\n')
                    self._count_progress(task, seg)
        except Exception:
            pass
        finally:
            log_f.close()

        exit_code = proc.wait()
        task['exit_code'] = exit_code
        task['end_time'] = _now_str()
        if task['stop_flag']:
            task['status'] = 'STOPPED'
        elif task.get('timed_out'):
            task['status'] = 'ERROR'
            task['error_msg'] = ('执行超时(%d分钟)被强制停止，疑似设备/驱动挂起(uiautomator 崩溃或连接无响应)或接口服务无响应，'
                                 '请查看日志最后输出与 Appium 服务日志(logs/appium.log)'
                                 % ((task.get('timeout_seconds') or RUN_TIMEOUT_SECONDS) // 60))
        elif exit_code == 0:
            task['status'] = 'PASSED'
        else:
            task['status'] = 'FAILED'
        self._archive(task)

    def _watchdog(self, task):
        """任务看门狗：超过 deadline 强杀整个进程组（含 pytest 可能卡住的子进程），状态上报 ERROR。"""
        deadline = task.get('deadline') or 0
        while time.time() < deadline:
            proc = task.get('process')
            if not proc or proc.poll() is not None:
                return
            time.sleep(15)
        proc = task.get('process')
        if proc and proc.poll() is None:
            task['timed_out'] = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _count_progress(self, task, line):
        m = _PROGRESS_RE.search(line)
        if not m:
            return
        result = m.group(1)
        if result == 'PASSED':
            task['passed'] += 1
        elif result == 'FAILED':
            task['failed'] += 1
        elif result == 'ERROR':
            task['error'] += 1
        elif result == 'SKIPPED':
            task['skipped'] += 1

    def _archive(self, task):
        """把任务持久化为 result.json（供历史查询与进程重启恢复），并清理设备临时文件"""
        with self._lock:
            data = self._public_task(task)
        try:
            with open(task['result_path'], 'w', encoding='utf-8') as f:
                f.write(ujson.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print('警告: 归档 %s 失败: %s' % (task['run_id'], e))
        self._cleanup_device_tmp_files(task)

    def _cleanup_device_tmp_files(self, task):
        """任务结束后清理本平台进程写入的执行上下文临时文件（config/app_ui_tmp/<pid>*、
        config/tmp/env.json），避免多次执行后脏文件堆积；运行中的任务不清理（pytest 子进程还要读取）"""
        if task.get('status') in ('PENDING', 'RUNNING'):
            return
        for f in task.get('tmp_files') or []:
            try:
                if os.path.isfile(f):
                    os.remove(f)
            except Exception as e:
                print('警告: 清理设备临时文件 %s 失败: %s' % (f, e))

    # ------------------------------------------------------------------ 停止
    def stop_run(self, run_id):
        with self._lock:
            task = self._tasks.get(run_id)
            if not task:
                return False, '任务不存在'
            if task['status'] not in ('PENDING', 'RUNNING'):
                return False, '任务已处于 %s 状态，无需停止' % task['status']
            task['stop_flag'] = True
            task['stop_requested'] = True
            proc = task['process']

        # 整进程组 SIGTERM → 超时 SIGKILL
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        def _force_kill():
            try:
                proc.wait(timeout=8)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        threading.Thread(target=_force_kill, daemon=True).start()
        return True, '已发送停止信号，进程清理中...'

    # ------------------------------------------------------------------ 删除/清空
    def delete_run(self, run_id):
        """删除一条执行记录（run 目录 = allure 数据/报告/日志一并删除）。
        正在运行的任务禁止删除。只作用于平台的 output/runs/，不影响命令行 output/app_ui/。"""
        if not re.match(r'^\d{8}_\d{3}$', str(run_id)):
            return False, 'run_id 不合法'
        with self._lock:
            task = self._tasks.get(run_id)
            if task and task['status'] in ('PENDING', 'RUNNING'):
                return False, '任务 %s 正在运行(%s)，请先停止再删除' % (run_id, task['status'])
            if task:
                del self._tasks[run_id]
        run_dir = os.path.join(RUNS_DIR, run_id)
        if os.path.isdir(run_dir):
            shutil.rmtree(run_dir, ignore_errors=True)
        return True, '已删除执行记录 %s（含 allure 数据/报告/日志）' % run_id

    def clear_runs(self):
        """清空全部已结束的执行记录（正在运行的保留）"""
        with self._lock:
            for rid in list(self._tasks.keys()):
                if self._tasks[rid]['status'] not in ('PENDING', 'RUNNING'):
                    del self._tasks[rid]
        removed = 0
        if os.path.isdir(RUNS_DIR):
            for name in os.listdir(RUNS_DIR):
                if re.match(r'^\d{8}_\d{3}$', name):
                    run_dir = os.path.join(RUNS_DIR, name)
                    # 跳过仍在运行的任务目录
                    with self._lock:
                        running = any(t['run_id'] == name and t['status'] in ('PENDING', 'RUNNING')
                                      for t in self._tasks.values())
                    if running:
                        continue
                    shutil.rmtree(run_dir, ignore_errors=True)
                    removed += 1
        return True, '已清空 %d 条执行记录' % removed

    # ------------------------------------------------------------------ 报告
    def generate_report(self, run_id):
        """生成 run 的 Allure 报告（allure generate 到 run/report/）并返回报告目录。
        支持历史任务（内存无则从磁盘 result.json 取 allure_dir）。返回 (ok, msg)"""
        with self._lock:
            task = self._tasks.get(run_id)
            disk = None
            if not task:
                disk = self._load_disk_task(run_id)
            if task:
                allure_rel = task['allure_dir']
            elif disk:
                allure_rel = disk.get('allure_dir') or ''
            else:
                return False, '任务不存在'
            if not allure_rel:
                return False, '任务没有 Allure 数据目录记录'
        allure_dir = os.path.join(BASE_DIR, allure_rel)
        report_dir = os.path.join(RUNS_DIR, run_id, 'report')
        if not os.path.isdir(allure_dir):
            return False, '没有 Allure 结果数据(%s)' % allure_rel
        shutil.rmtree(report_dir, ignore_errors=True)
        os.makedirs(report_dir, exist_ok=True)
        cmd = ['allure', 'generate', allure_dir, '-o', report_dir, '--clean']
        try:
            p = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, timeout=120)
        except Exception as e:
            return False, 'allure generate 失败: %s' % e
        if p.returncode != 0:
            return False, 'allure generate 失败: %s' % p.stderr.decode('utf-8', 'ignore')[-500:]
        report_rel = 'output/runs/%s/report' % run_id
        if task:
            task['report_dir'] = report_rel
            self._archive(task)
        else:
            self._patch_disk_result(run_id, {'report_dir': report_rel})
        return True, report_dir

    def _patch_disk_result(self, run_id, fields):
        """更新磁盘 result.json 的部分字段（历史任务回退场景）"""
        path = os.path.join(RUNS_DIR, run_id, 'result.json')
        try:
            data = self._load_disk_task(run_id) or {}
            data.update(fields)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(ujson.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print('警告: 更新 %s 失败: %s' % (path, e))


# 进程内单例（Flask 各请求共享同一执行管理器）
manager = ExecutionManager()