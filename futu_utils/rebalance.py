"""High-level single-symbol portfolio rebalance workflows."""

from __future__ import annotations

import time
from typing import Optional

from .ax_utils import ax_get, ax_rect, mouse_click, mouse_click_point, replace_text, wait_for
from .constants import MANAGER_TITLE, ROW_SETTLE, SEARCH_RESULT_SETTLE
from .futu_app import activate_app, find_window, get_pid, open_manager
from .manager_ui import (
    confirm_button_point,
    find_confirm_button,
    find_delete_button,
    find_existing_position_field,
    find_first_matching_search_checkbox,
    find_position_field,
    find_search_field,
    find_visible_checkbox,
    format_percent,
    position_row_centers,
    position_row_details,
    search_result_checkbox_point,
)
from .models import RebalanceAction, RebalanceCommand, RebalanceResult
from .portfolio_selector import select_portfolio
from .pyobjc_runtime import AX, check_accessibility_permission
from .recorder import append_rebalance_record


CLOSE_TARGETS = {"close", "delete", "remove", "rm"}


def elapsed_seconds(started_at: Optional[float]) -> Optional[str]:
    if started_at is None:
        return None
    return f"{time.perf_counter() - started_at:.2f}s"


def portfolio_phrase(command: RebalanceCommand) -> str:
    return f" in portfolio {command.portfolio_code}" if command.portfolio_code else ""


def with_elapsed(message: str, elapsed: Optional[str]) -> str:
    return f"{message} Elapsed: {elapsed}." if elapsed else message


def run_rebalance_command(command: RebalanceCommand) -> RebalanceResult:
    """Execute one public command object through the GUI automation backend."""

    if command.action is RebalanceAction.CLOSE:
        return _close_position(command)
    return _build_position(command)


def build_position(
    symbol: str,
    percent: str,
    dry_run: bool = False,
    record: bool = False,
    portfolio_code: Optional[str] = None,
    discard_open_manager: bool = False,
    started_at: Optional[float] = None,
) -> RebalanceResult:
    """Set one symbol to a target percent.

    Kept as a compatibility Python API; new code can use
    :class:`futu_utils.api.FutuPortfolioClient` or :class:`RebalanceCommand`.
    """

    return _build_position(
        RebalanceCommand(
            symbol=symbol,
            action=RebalanceAction.SET,
            percent=percent,
            dry_run=dry_run,
            record=record,
            portfolio_code=portfolio_code,
            discard_open_manager=discard_open_manager,
            started_at=started_at,
        )
    )


def close_position(
    symbol: str,
    dry_run: bool = False,
    record: bool = False,
    portfolio_code: Optional[str] = None,
    discard_open_manager: bool = False,
    started_at: Optional[float] = None,
) -> RebalanceResult:
    """Remove one symbol from the current portfolio rows."""

    return _close_position(
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


def _prepare_manager(command: RebalanceCommand):
    check_accessibility_permission()
    pid = get_pid()
    app = AX.AXUIElementCreateApplication(pid)
    activate_app(app)
    select_portfolio(
        app,
        command.portfolio_code,
        discard_open_manager=command.discard_open_manager,
    )
    return app, open_manager(app)


def _build_position(command: RebalanceCommand) -> RebalanceResult:
    app, manager = _prepare_manager(command)

    position_field = find_existing_position_field(manager, command.symbol)
    if not position_field:
        search = find_search_field(manager)
        replace_text(search, command.symbol, settle=SEARCH_RESULT_SETTLE)

        position_field = None
        checkbox = find_first_matching_search_checkbox(manager, command.symbol)
        if not checkbox:
            checkbox = wait_for(
                lambda: find_first_matching_search_checkbox(manager, command.symbol),
                timeout=0.4,
                interval=0.01,
            )
        if checkbox and mouse_click_point(search_result_checkbox_point(manager)):
            time.sleep(ROW_SETTLE)
            position_field = wait_for(
                lambda: find_position_field(manager, command.symbol), timeout=0.6
            )

        if not position_field:
            checkbox = checkbox or wait_for(
                lambda: find_visible_checkbox(manager, command.symbol), timeout=2.0
            )
            if not checkbox:
                raise RuntimeError(f"Could not find a visible search result for {command.symbol!r}.")
            mouse_click(checkbox)
            time.sleep(ROW_SETTLE)
            position_field = wait_for(
                lambda: find_position_field(manager, command.symbol), timeout=1.0
            )
    if not position_field:
        raise RuntimeError("Could not find the position percentage field after selecting the stock.")

    details = {"name": "", "percent": ""}
    before_percent = ""
    after_percent = format_percent(command.percent)
    if command.record:
        details = position_row_details(manager, command.symbol)
        before_percent = details["percent"] or format_percent(
            ax_get(position_field, AX.kAXValueAttribute)
        )

    replace_text(position_field, command.percent)

    if command.dry_run:
        return RebalanceResult(
            command=command,
            status="dry-run",
            message=(
                f"Dry run complete: {command.symbol} is selected{portfolio_phrase(command)} "
                f"and position is set to {command.percent}%."
            ),
        )

    if not mouse_click_point(confirm_button_point(manager)):
        confirm = find_confirm_button(manager)
        # Futu's custom confirm button can report AXPress success without firing.
        # A real mouse click on the button center is more reliable here.
        mouse_click(confirm)
    closed = wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=2.0)
    if not closed:
        raise RuntimeError("Clicked confirm, but the manager window is still open.")

    record_path = None
    if command.record:
        record_path = append_rebalance_record(
            symbol=command.symbol,
            stock_name=details["name"],
            before_percent=before_percent,
            after_percent=after_percent,
        )

    elapsed = elapsed_seconds(command.started_at)
    return RebalanceResult(
        command=command,
        status="done",
        message=with_elapsed(
            f"Done: {command.symbol} position set to {command.percent}%{portfolio_phrase(command)}.",
            elapsed,
        ),
        record_path=record_path,
        elapsed=elapsed,
    )


def _close_position(command: RebalanceCommand) -> RebalanceResult:
    app, manager = _prepare_manager(command)

    delete_button = wait_for(lambda: find_delete_button(manager, command.symbol), timeout=2.0)
    if not delete_button:
        raise RuntimeError(f"Could not find {command.symbol} in the current portfolio rows.")

    details = {"name": "", "percent": ""}
    before_percent = ""
    if command.record:
        details = position_row_details(manager, command.symbol)
        before_percent = details["percent"]

    if command.dry_run:
        rect = ax_rect(delete_button)
        if rect is None:
            raise RuntimeError("Found delete button, but could not read its screen bounds.")
        return RebalanceResult(
            command=command,
            status="dry-run",
            message=(
                f"Dry run complete: found delete button for {command.symbol}{portfolio_phrase(command)} "
                f"at ({rect.cx:.0f}, {rect.cy:.0f}); confirm was not clicked."
            ),
        )

    mouse_click(delete_button)
    wait_for(lambda: not position_row_centers(manager, command.symbol), timeout=1.0)

    if not mouse_click_point(confirm_button_point(manager)):
        confirm = find_confirm_button(manager)
        mouse_click(confirm)
    closed = wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=2.0)
    if not closed:
        raise RuntimeError("Clicked confirm, but the manager window is still open.")

    record_path = None
    if command.record:
        record_path = append_rebalance_record(
            symbol=command.symbol,
            stock_name=details["name"],
            before_percent=before_percent,
            after_percent="0.00%",
        )

    elapsed = elapsed_seconds(command.started_at)
    return RebalanceResult(
        command=command,
        status="done",
        message=with_elapsed(
            f"Done: {command.symbol} was removed from the portfolio{portfolio_phrase(command)}.",
            elapsed,
        ),
        record_path=record_path,
        elapsed=elapsed,
    )


def is_close_target(value: str) -> bool:
    normalized = value.strip().lower().rstrip("%")
    if normalized in CLOSE_TARGETS:
        return True
    try:
        return float(normalized) == 0.0
    except ValueError:
        return False
