"""Optional rebalance CSV recording."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from .constants import RECORD_FILENAME, RECORD_HEADER


def record_file_path() -> Path:
    return Path(__file__).resolve().with_name(RECORD_FILENAME)


def append_rebalance_record(
    *,
    symbol: str,
    stock_name: str,
    before_percent: str,
    after_percent: str,
    price: str = "",
    note: str = "",
    path: Optional[Path] = None,
) -> Path:
    output_path = path or record_file_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    should_write_header = not output_path.exists() or output_path.stat().st_size == 0
    now = datetime.now()
    row = [
        now.strftime("%Y/%m/%d"),
        now.strftime("%H:%M:%S"),
        stock_name,
        symbol.upper(),
        before_percent,
        after_percent,
        price,
        note,
    ]
    with output_path.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        if should_write_header:
            writer.writerow(RECORD_HEADER)
        writer.writerow(row)
    return output_path
