"""Small data models used by the portfolio automation package."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Rect:
    """Screen rectangle from macOS Accessibility coordinates."""

    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


class RebalanceAction(str, Enum):
    """Supported high-level portfolio operations."""

    SET = "set"
    CLOSE = "close"


@dataclass(frozen=True)
class RebalanceCommand:
    """Public command object for one single-symbol rebalance operation.

    This is the stable interface external scripts should depend on. The UI
    implementation can change behind it without changing user code.
    """

    symbol: str
    action: RebalanceAction = RebalanceAction.SET
    percent: str = "100"
    dry_run: bool = False
    record: bool = False
    portfolio_code: Optional[str] = None
    discard_open_manager: bool = False
    started_at: Optional[float] = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("Symbol cannot be empty.")
        object.__setattr__(self, "symbol", symbol)

        action = RebalanceAction(self.action)
        object.__setattr__(self, "action", action)

        portfolio_code = (self.portfolio_code or "").strip().upper()
        object.__setattr__(self, "portfolio_code", portfolio_code or None)

        if action is RebalanceAction.CLOSE:
            object.__setattr__(self, "percent", "0")
            return

        percent = str(self.percent).strip().rstrip("%").strip()
        if not percent:
            raise ValueError("Percent cannot be empty.")
        object.__setattr__(self, "percent", percent)


@dataclass(frozen=True)
class RebalanceResult:
    """Result returned by the public API and rendered by the CLI."""

    command: RebalanceCommand
    status: str
    message: str
    record_path: Optional[Path] = None
    elapsed: Optional[str] = None

    def output_lines(self) -> list[str]:
        lines: list[str] = []
        if self.record_path is not None:
            lines.append(f"Record written: {self.record_path}")
        lines.append(self.message)
        return lines
