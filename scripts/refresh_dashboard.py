"""QQQ 监控盘数据刷新脚本（双模式）。

模式说明：
- daily：日频全量刷新（收盘后产出正式信号）
- guard：盘中轻量守护（只追加熔断预警，不重算正式决策）
- auto（默认）：美东常规交易时段内跑 guard，否则跑 daily
"""

import argparse

from app.config import PROJECT_ROOT
from app.db import SnapshotRepository
from app.scheduler import refresh_once, run_intraday_guard
from app.services.session import is_regular_session_open

# 快照数据库与静态导出路径（沿用既有 PROJECT_ROOT 约定）
DB_PATH = PROJECT_ROOT / "data" / "dashboard.sqlite"
EXPORT_PATH = PROJECT_ROOT / "static" / "data" / "dashboard.json"


def resolve_action(mode: str, session_open: bool) -> str:
    """纯函数：根据模式与盘中状态决定刷新动作（返回 "daily" 或 "guard"）。"""
    if mode == "auto":
        return "guard" if session_open else "daily"
    return mode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="刷新 QQQ 监控盘数据")
    parser.add_argument(
        "--mode",
        choices=["auto", "daily", "guard"],
        default="auto",
        help="auto=按盘中状态自动选择；daily=日频全量；guard=盘中轻量守护",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    repository = SnapshotRepository(DB_PATH)
    action = resolve_action(args.mode, is_regular_session_open())
    if action == "guard":
        run_intraday_guard(repository, EXPORT_PATH)
    else:
        refresh_once(repository, EXPORT_PATH)


if __name__ == "__main__":
    main()
