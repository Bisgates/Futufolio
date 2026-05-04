"""Command-line interface for single-symbol Futu portfolio rebalancing."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

from .api import FutuPortfolioClient
from .models import RebalanceAction, RebalanceCommand
from .rebalance import is_close_target

# Keep this near the top so elapsed time includes most command startup overhead.
COMMAND_STARTED_AT = time.perf_counter()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set or remove one stock in FutuNiuniu Portfolio Manager."
    )
    parser.add_argument("symbol", help="Stock code, e.g. MSFT, 00700, 300750")
    parser.add_argument(
        "target",
        nargs="?",
        help="Optional target percentage, or close/delete/0 to remove the row.",
    )
    parser.add_argument("--percent", default="100", help="Target position percentage, default: 100")
    parser.add_argument(
        "--record",
        dest="record",
        action="store_true",
        default=False,
        help="Append futu_utils/record.csv after a successful confirmed change.",
    )
    parser.add_argument(
        "--no-record",
        dest="record",
        action="store_false",
        help="Do not append a rebalance CSV record. This is the default.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stop before clicking the final confirm button.",
    )
    parser.add_argument(
        "--portfolio",
        "--portfolio-code",
        dest="portfolio_code",
        metavar="CODE",
        default=os.environ.get("FUTU_PORTFOLIO_CODE", ""),
        help=(
            "Portfolio code to select before opening Portfolio Manager, "
            "e.g. PFL0137605. Can also be set with FUTU_PORTFOLIO_CODE."
        ),
    )
    parser.add_argument(
        "--discard-open-manager",
        action="store_true",
        help=(
            "If Portfolio Manager is already open, click Cancel and choose "
            "not to save before selecting --portfolio."
        ),
    )
    return parser


def command_from_args(args: argparse.Namespace, *, started_at: Optional[float] = None) -> RebalanceCommand:
    target = args.target.strip() if args.target else None
    if target and is_close_target(target):
        return RebalanceCommand(
            symbol=args.symbol,
            action=RebalanceAction.CLOSE,
            dry_run=args.dry_run,
            record=args.record,
            portfolio_code=args.portfolio_code,
            discard_open_manager=args.discard_open_manager,
            started_at=started_at,
        )

    percent = str(target if target else args.percent)
    return RebalanceCommand(
        symbol=args.symbol,
        action=RebalanceAction.SET,
        percent=percent,
        dry_run=args.dry_run,
        record=args.record,
        portfolio_code=args.portfolio_code,
        discard_open_manager=args.discard_open_manager,
        started_at=started_at,
    )


def parse_command(argv: list[str], *, started_at: Optional[float] = None) -> RebalanceCommand:
    return command_from_args(build_parser().parse_args(argv), started_at=started_at)


def main(argv: list[str], *, client: Optional[FutuPortfolioClient] = None) -> int:
    command = parse_command(argv, started_at=COMMAND_STARTED_AT)
    result = (client or FutuPortfolioClient()).rebalance(command)
    for line in result.output_lines():
        print(line)
    return 0


def run() -> None:
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
