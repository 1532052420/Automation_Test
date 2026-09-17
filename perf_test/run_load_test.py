# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _ROOT / "config" / "load_test_config.yaml"


def _build_locust_argv(
    *,
    config_path: Path,
    locustfile: Path,
    mode: str,
    host: str,
    run_time: str,
    use_headless: bool,
    users: int,
    spawn_rate: float,
    extra: list[str],
) -> list[str]:
    argv = [
        "locust",
        "-f",
        str(locustfile),
        "--test-config",
        str(config_path),
    ]
    if mode:
        argv.extend(["--mode", mode])
    if host:
        argv.extend(["--host", host.rstrip("/")])
    if use_headless:
        argv.append("--headless")
        argv.extend(["--run-time", run_time])
        argv.extend(["-u", "1", "-r", "1"])
        argv.extend(["--stop-timeout", "1"])
    else:
        if users:
            argv.extend(["-u", str(users)])
        if spawn_rate:
            argv.extend(["-r", str(spawn_rate)])
    argv.extend(extra)
    return argv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HTTP 接口性能压测（Locust + 阶梯/脉冲双模式）",
    )
    parser.add_argument(
        "--config",
        "-c",
        default=str(_DEFAULT_CONFIG),
        help="YAML 配置文件路径",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["staircase", "pulse"],
        default="",
        help="压测模式，覆盖配置文件中的 mode",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无 Web UI 运行（推荐 CI/自动化）",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Locust Web UI（默认与 headless 二选一，未指定 headless 时启用 Web）",
    )
    parser.add_argument(
        "--users",
        "-u",
        type=int,
        default=0,
        help="仅在不使用 LoadTestShape 时生效；使用本脚本默认启用 Shape，一般无需设置",
    )
    parser.add_argument(
        "--spawn-rate",
        "-r",
        type=float,
        default=0,
        help="同上，Shape 模式下由配置控制",
    )
    parser.add_argument(
        "--run-time",
        "-t",
        default="",
        help="覆盖配置 common.run_time，如 5m",
    )
    parser.add_argument(
        "--host",
        default="",
        help="覆盖配置 common.host",
    )
    parser.add_argument(
        "--locust-extra",
        nargs=argparse.REMAINDER,
        help="传递给 locust 的额外参数，如 --loglevel DEBUG",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.is_file():
        print(f"错误: 配置文件不存在 {config_path}", file=sys.stderr)
        return 1

    os.environ["LOAD_TEST_CONFIG"] = str(config_path)
    os.chdir(_ROOT)

    sys.path.insert(0, str(_ROOT))
    from config_loader import load_config
    from preflight_check import warn_stale_processes

    warn_stale_processes()

    cfg = load_config(config_path)
    if args.mode:
        cfg["mode"] = args.mode

    run_time = args.run_time or cfg["common"]["run_time"]
    host = args.host or cfg["common"]["host"]
    locustfile = _ROOT / "locustfile.py"

    extra = args.locust_extra or []
    if extra and extra[0] == "--":
        extra = extra[1:]

    use_headless = not args.web
    argv = _build_locust_argv(
        config_path=config_path,
        locustfile=locustfile,
        mode=args.mode,
        host=host,
        run_time=run_time,
        use_headless=use_headless,
        users=args.users,
        spawn_rate=args.spawn_rate,
        extra=extra,
    )

    print("执行命令:", " ".join(argv))
    print(f"压测模式: {cfg['mode']} ({'阶梯递增加压' if cfg['mode'] == 'staircase' else '瞬时脉冲峰值'})")
    print(f"配置文件: {config_path}")
    print(f"报告输出: {cfg.get('report', {}).get('output_path', 'reports/load_test_report.html')}")
    print("提示: Ctrl+C 一次停止压测；若卡住可再按一次强制退出")
    print("-" * 60)

    # 同进程运行 Locust，确保 Ctrl+C 能触发 quitting / atexit 并写出报告
    old_argv = sys.argv
    sys.argv = argv
    try:
        from locust.main import main as locust_main

        locust_main()
        return 0
    except KeyboardInterrupt:
        print("\n[中断] 已捕获 Ctrl+C")
        return 130
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
