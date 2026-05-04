#!/usr/bin/env python3
"""Compatibility entrypoint for FutuNiuniu portfolio rebalancing.

Usage:
    python3 futu_utils/futu_portfolio.py MSFT
    python3 futu_utils/futu_portfolio.py MSFT 50
    python3 futu_utils/futu_portfolio.py MSFT close
    python3 futu_utils/futu_portfolio.py MSFT 100 --record

This script drives the existing FutuNiuniu UI via macOS Accessibility.
It does not use a trading API and does not place real brokerage orders.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futu_utils.cli import run


if __name__ == "__main__":
    run()
