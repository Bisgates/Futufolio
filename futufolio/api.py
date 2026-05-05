"""Public interface for Futu portfolio automation.

This module is intentionally small. External scripts should import from here or
from ``futufolio`` instead of depending on the lower-level UI selector modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .models import RebalanceAction, RebalanceCommand, RebalanceResult
from .rebalance import run_rebalance_command

RebalanceRunner = Callable[[RebalanceCommand], RebalanceResult]


@dataclass(frozen=True)
class FutuPortfolioClient:
    """Small public client around the GUI automation backend."""

    runner: Optional[RebalanceRunner] = None

    def rebalance(self, command: RebalanceCommand) -> RebalanceResult:
        runner = self.runner or run_rebalance_command
        return runner(command)

    def set_position(
        self,
        symbol: str,
        percent: str | int | float = "100",
        *,
        dry_run: bool = False,
        record: bool = False,
        portfolio_code: Optional[str] = None,
        discard_open_manager: bool = False,
        started_at: Optional[float] = None,
    ) -> RebalanceResult:
        return self.rebalance(
            RebalanceCommand(
                symbol=symbol,
                action=RebalanceAction.SET,
                percent=str(percent),
                dry_run=dry_run,
                record=record,
                portfolio_code=portfolio_code,
                discard_open_manager=discard_open_manager,
                started_at=started_at,
            )
        )

    def close_position(
        self,
        symbol: str,
        *,
        dry_run: bool = False,
        record: bool = False,
        portfolio_code: Optional[str] = None,
        discard_open_manager: bool = False,
        started_at: Optional[float] = None,
    ) -> RebalanceResult:
        return self.rebalance(
            RebalanceCommand(
                symbol=symbol,
                action=RebalanceAction.CLOSE,
                dry_run=dry_run,
                record=record,
                portfolio_code=portfolio_code,
                discard_open_manager=discard_open_manager,
                started_at=started_at,
            )
        )


def set_position(symbol: str, percent: str | int | float = "100", **kwargs) -> RebalanceResult:
    """Convenience function for one-off scripts."""

    return FutuPortfolioClient().set_position(symbol, percent, **kwargs)


def close_position(symbol: str, **kwargs) -> RebalanceResult:
    """Convenience function for one-off scripts."""

    return FutuPortfolioClient().close_position(symbol, **kwargs)
