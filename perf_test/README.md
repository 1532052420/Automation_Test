# HTTP 接口性能压测（Locust）

基于 Python + Locust，参考 JMeter 线程组设计，支持 **阶梯递增加压** 与 **瞬时脉冲峰值** 两种模式，参数全部外置 YAML 配置，压测结束自动生成 HTML 报告（含 TPS/耗时/错误率图表及类「查看结果树」明细）。

## 快速开始

```bash
cd perf_test
pip install -r requirements.txt
```

**一键运行（推荐）**

1. 编辑 `config/load_test_config.yaml`
2. 任选一种方式启动：
   - 双击 `run.bat`（Windows）
   - 或执行：`python run.py`

报告生成在 `reports/load_test_report.html`。

**其他用法**

```bash
# 脉冲峰值模式
python run.py --mode pulse

# 带 Locust Web UI
python run.py --web

# 完整命令行参数（与 run.py 相同）
python run_load_test.py --headless
```

报告默认输出：`reports/load_test_report.html`

## 配置说明

编辑 `config/load_test_config.yaml`：

| 区块 | 说明 |
|------|------|
| `mode` | `staircase` 阶梯加压 / `pulse` 脉冲峰值 |
| `common` | VU、循环次数、总时长、host、孵化速率 |
| `request` | 路径、方法、请求头、请求体 |
| `staircase` | 起始用户、每阶增量、每阶时长 |
| `pulse` | 基准/峰值并发、尖峰时长与周期 |
| `report` | HTML 路径、是否采集响应体、样本上限 |

## 直接使用 Locust CLI

```bash
set LOAD_TEST_CONFIG=config\load_test_config.yaml
locust -f locustfile.py --headless --run-time 2m -u 1 -r 1 --test-config config\load_test_config.yaml
```

> 启用 `LoadTestShape` 时，实际并发由配置中的阶梯/脉冲曲线控制，`-u`/`-r` 仅作占位。


---

## 归属：本模块已并入 AppUI 自动化测试平台

- 位置：`perf_test/`（平台子模块），侧边栏「⚡ 性能压测」页可视化配置与执行
- 配置单一数据源：`perf_test/config/load_test_config.yaml`（平台页面保存即写它）
- 依赖隔离：压测跑在 `perf_test/.venv`（Python 3.13 + locust 2.x），与平台主环境
  （Python 3.8 + flask 1.1.2）完全隔离；首次使用：
  ```bash
  python3 -m venv perf_test/.venv
  perf_test/.venv/bin/pip install -r perf_test/requirements-perf.txt
  ```
- 命令行直跑（不经平台）：
  ```bash
  perf_test/.venv/bin/python perf_test/run_load_test.py --config perf_test/config/load_test_config.yaml --headless
  ```
- 报告：压测结束后由平台收集到 `output/perf_runs/<run_id>/report.html`，可在线查看
