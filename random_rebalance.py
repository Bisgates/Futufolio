"""Randomly rebalance one symbol m times (even) within an n-minute window.

Alternates target position 0 -> 20 -> 0 -> ... sequentially. All m random
times are generated upfront (sorted, at least 5s apart so each GUI run can
finish). After each rebalance is confirmed done, the exact completion
timestamp is appended to a CSV: time_stamp, <symbol>, <before>, <after>.

Usage:
    uv run python random_rebalance.py 1 2          # 2 rebalances within 1 minute
    uv run python random_rebalance.py 10 4 --symbol MSFT --portfolio PFL0184708
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from futufolio import FutuPortfolioClient

CSV_HEADER = ["time_stamp", "symbol", "before", "after"]
DEFAULT_PORTFOLIO = "PFL0184708"
# Each GUI rebalance takes a few seconds; scheduled runs must not overlap.
MIN_GAP_SECONDS = 5.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("minutes", type=float, help="Window length n in minutes.")
    parser.add_argument("times", type=int, help="Rebalance count m, must be even.")
    parser.add_argument("--symbol", default="MSFT", help="Stock code, default: MSFT")
    parser.add_argument("--high", default="20", help="High target percent, default: 20")
    parser.add_argument(
        "--portfolio",
        default=os.environ.get("FUTU_PORTFOLIO_CODE", DEFAULT_PORTFOLIO),
        help=f"Portfolio code, default: {DEFAULT_PORTFOLIO} (or FUTU_PORTFOLIO_CODE).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help=(
            "Output CSV path (overwritten if it exists). Default: a new "
            "random_rebalance_log_<timestamp>.csv next to this script."
        ),
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed.")
    return parser


def schedule_offsets(window_seconds: float, count: int) -> list[float]:
    """Pick `count` sorted random offsets in [0, window], at least MIN_GAP apart."""
    if window_seconds < (count - 1) * MIN_GAP_SECONDS:
        raise ValueError(
            f"Window of {window_seconds:.0f}s is too short for {count} rebalances "
            f"with a {MIN_GAP_SECONDS:.0f}s minimum gap."
        )
    # Sample in the gap-free residual space, then add the mandatory gaps back.
    free = window_seconds - (count - 1) * MIN_GAP_SECONDS
    offsets = sorted(random.uniform(0, free) for _ in range(count))
    return [t + i * MIN_GAP_SECONDS for i, t in enumerate(offsets)]


def new_csv(path: Path | None) -> Path:
    """Start a fresh CSV for this run (header only), overwriting any old file."""
    if path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(__file__).resolve().with_name(f"random_rebalance_log_{stamp}.csv")
    with path.open("w", encoding="utf-8", newline="") as file:
        csv.writer(file).writerow(CSV_HEADER)
    return path


def append_row(path: Path, row: list[str]) -> None:
    with path.open("a", encoding="utf-8", newline="") as file:
        csv.writer(file).writerow(row)


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.times < 2 or args.times % 2 != 0:
        print("Error: times must be a positive even number.", file=sys.stderr)
        return 1

    if args.seed is not None:
        random.seed(args.seed)

    client = FutuPortfolioClient()
    csv_path = new_csv(args.csv)
    print(f"Recording to {csv_path}")
    offsets = schedule_offsets(args.minutes * 60.0, args.times)
    start = time.monotonic()
    print(f"Window: {args.minutes} min, {args.times} rebalances at offsets (s): "
          f"{[round(o, 1) for o in offsets]}")

    for i, offset in enumerate(offsets):
        wait = start + offset - time.monotonic()
        if wait > 0:
            print(f"[{i + 1}/{args.times}] sleeping {wait:.1f}s ...")
            time.sleep(wait)

        before, after = ("0", args.high) if i % 2 == 0 else (args.high, "0")
        print(f"[{i + 1}/{args.times}] {args.symbol} {before} => {after}")
        kwargs = dict(portfolio_code=args.portfolio, discard_open_manager=True)
        if after == "0":
            result = client.close_position(args.symbol, **kwargs)
        else:
            result = client.set_position(args.symbol, after, **kwargs)
        done_at = datetime.now()  # confirmed-complete timestamp, taken right after return

        if result.status != "done":
            print(f"Error: unexpected status {result.status!r}: {result.message}", file=sys.stderr)
            return 1
        time_stamp = done_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        append_row(csv_path, [time_stamp, args.symbol.upper(), before, after])
        print(f"    done at {time_stamp}, recorded -> {csv_path}")

    print(f"All {args.times} rebalances finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
