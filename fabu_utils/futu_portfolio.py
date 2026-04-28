#!/usr/bin/env python3
"""Automate FutuNiuniu portfolio-manager position setup on macOS.

Usage:
    python3 futu_portfolio.py MSFT
    python3 futu_portfolio.py MSFT 50
    python3 futu_portfolio.py MSFT close
    python3 futu_portfolio.py MSFT 0
    python3 futu_portfolio.py MSFT --percent 100 --dry-run

This script drives the existing FutuNiuniu UI via macOS Accessibility.
It does not use a trading API and does not place real brokerage orders.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

try:
    import ApplicationServices as AX
    import Quartz
except ImportError as exc:  # pragma: no cover - environment-specific
    raise SystemExit(
        "Missing PyObjC modules. Install with: python3 -m pip install pyobjc"
    ) from exc

PROCESS_NAME = "FutuNiuniu"
APP_PATH = "/Applications/FutuNiuniu.app"
APPLESCRIPT_NAME = "FutuNiuniu"
MANAGER_TITLE = "组合管理"

KEY_A = 0
KEY_V = 9
KEY_DELETE = 51
CMD = Quartz.kCGEventFlagMaskCommand


@dataclass(frozen=True)
class Rect:
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


def check_accessibility_permission() -> None:
    opts = {AX.kAXTrustedCheckOptionPrompt: True}
    if not AX.AXIsProcessTrustedWithOptions(opts):
        raise SystemExit(
            "Accessibility permission is required. Open System Settings -> "
            "Privacy & Security -> Accessibility, allow your Terminal/Python app, "
            "then run this command again."
        )


def run_quiet(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        **kwargs,
    )


def get_pid() -> int:
    result = subprocess.run(
        ["pgrep", "-x", PROCESS_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        run_quiet(["open", APP_PATH])
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["pgrep", "-x", PROCESS_NAME],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            if result.stdout.strip():
                break
            time.sleep(0.1)
    if not result.stdout.strip():
        raise SystemExit(f"Could not find or launch {APP_PATH}")
    return int(result.stdout.splitlines()[0])


def activate_app() -> None:
    run_quiet(["osascript", "-e", f'tell application "{APPLESCRIPT_NAME}" to activate'])
    time.sleep(0.08)


def focus_window(app, window) -> None:
    AX.AXUIElementSetAttributeValue(app, AX.kAXFrontmostAttribute, True)
    AX.AXUIElementPerformAction(window, AX.kAXRaiseAction)
    AX.AXUIElementSetAttributeValue(window, AX.kAXMainAttribute, True)
    time.sleep(0.08)


def ax_get(element, attribute: str):
    err, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
    return value if err == 0 else None


def ax_children(element) -> list:
    return ax_get(element, AX.kAXChildrenAttribute) or []


def ax_text(element) -> str:
    parts: list[str] = []
    for attr in (
        AX.kAXTitleAttribute,
        AX.kAXDescriptionAttribute,
        AX.kAXValueAttribute,
        AX.kAXIdentifierAttribute,
    ):
        value = ax_get(element, attr)
        if isinstance(value, str) and value:
            parts.append(value)
    return " ".join(parts)


def ax_rect(element) -> Optional[Rect]:
    pos = ax_get(element, AX.kAXPositionAttribute)
    size = ax_get(element, AX.kAXSizeAttribute)
    if pos is None or size is None:
        return None
    try:
        _, point = AX.AXValueGetValue(pos, AX.kAXValueCGPointType, None)
        _, dims = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
        return Rect(point.x, point.y, dims.width, dims.height)
    except Exception:
        return None


def visible_in(element, container: Rect, margin: float = 4) -> bool:
    rect = ax_rect(element)
    if rect is None:
        return False
    return (
        container.x - margin <= rect.x <= container.right + margin
        and container.y - margin <= rect.y <= container.bottom + margin
        and rect.w > 0
        and rect.h > 0
    )


def walk(element) -> Iterable:
    yield element
    for child in ax_children(element):
        yield from walk(child)


def find_descendant(element, predicate: Callable) -> Optional:
    for item in walk(element):
        if predicate(item):
            return item
    return None


def walk_right_side(window) -> Iterable:
    win_rect = ax_rect(window)
    if win_rect is None:
        return
    threshold = win_rect.x + win_rect.w * 0.35
    for child in ax_children(window):
        rect = ax_rect(child)
        if rect and visible_in(child, win_rect) and rect.x > threshold:
            yield from walk(child)


def windows(app) -> list:
    return ax_get(app, AX.kAXWindowsAttribute) or []


def find_window(app, title: str):
    for window in windows(app):
        if ax_get(window, AX.kAXTitleAttribute) == title:
            return window
    return None


def wait_for(predicate: Callable, timeout: float, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    last_value = None
    while time.monotonic() < deadline:
        last_value = predicate()
        if last_value:
            return last_value
        time.sleep(interval)
    return last_value


def mouse_click_xy(x: float, y: float) -> None:
    point = (x, y)
    for event_type in (
        Quartz.kCGEventMouseMoved,
        Quartz.kCGEventLeftMouseDown,
        Quartz.kCGEventLeftMouseUp,
    ):
        event = Quartz.CGEventCreateMouseEvent(
            None, event_type, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.012)


def mouse_click(element) -> None:
    rect = ax_rect(element)
    if rect is None:
        raise RuntimeError("Cannot click element without position/size")
    mouse_click_xy(rect.cx, rect.cy)


def press(element) -> None:
    err = AX.AXUIElementPerformAction(element, AX.kAXPressAction)
    # Some Futu controls return an AX timeout error even though the click succeeds.
    if err not in (0, -25205):
        mouse_click(element)


def keypress(key_code: int, flags: int = 0) -> None:
    for is_down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(None, key_code, is_down)
        if flags:
            Quartz.CGEventSetFlags(event, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.012)


def set_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def replace_text(field, text: str) -> None:
    AX.AXUIElementSetAttributeValue(field, AX.kAXFocusedAttribute, True)
    mouse_click(field)
    time.sleep(0.03)
    set_clipboard(text)
    keypress(KEY_A, CMD)
    keypress(KEY_DELETE)
    keypress(KEY_V, CMD)
    time.sleep(0.08)


def button_text_is(element, label: str) -> bool:
    if ax_get(element, AX.kAXRoleAttribute) != AX.kAXButtonRole:
        return False
    return label in ax_text(element)


def open_manager(app):
    manager = find_window(app, MANAGER_TITLE)
    if manager:
        focus_window(app, manager)
        return manager

    # Navigate to the portfolio tab first, in case the app is on another page.
    for window in windows(app):
        portfolio_button = find_descendant(
            window,
            lambda e: button_text_is(e, "组合") and ax_rect(e) and ax_rect(e).x < 140,
        )
        if portfolio_button:
            press(portfolio_button)
            time.sleep(0.15)
            break

    def manager_button():
        for window in windows(app):
            found = find_descendant(window, lambda e: button_text_is(e, MANAGER_TITLE))
            if found:
                return found
        return None

    button = wait_for(manager_button, timeout=2.5)
    if not button:
        raise RuntimeError("Could not find the '组合管理' button. Is the Portfolio page open?")
    press(button)

    manager = wait_for(lambda: find_window(app, MANAGER_TITLE), timeout=2.5)
    if not manager:
        raise RuntimeError("Clicked '组合管理', but the manager window did not appear.")
    focus_window(app, manager)
    return manager


def visible_text_fields(window) -> list:
    win_rect = ax_rect(window)
    if win_rect is None:
        return []
    return [
        e
        for e in walk(window)
        if ax_get(e, AX.kAXRoleAttribute) == AX.kAXTextFieldRole
        and visible_in(e, win_rect)
    ]


def find_search_field(window):
    win_rect = ax_rect(window)
    # The stock search box is a direct child of the manager window. Avoid a
    # full recursive scan here because the left stock list can expose thousands
    # of off-screen accessibility nodes.
    fields = [
        child
        for child in ax_children(window)
        if ax_get(child, AX.kAXRoleAttribute) == AX.kAXTextFieldRole
    ]
    candidates = [f for f in fields if ax_rect(f) and ax_rect(f).x < win_rect.x + win_rect.w * 0.45]
    if not candidates:
        raise RuntimeError("Could not find the stock search field.")
    return sorted(candidates, key=lambda f: ax_rect(f).y)[0]


def find_visible_checkbox(window, symbol: str):
    win_rect = ax_rect(window)
    target = symbol.upper()
    matches = []
    for item in walk(window):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXCheckBoxRole:
            continue
        title = ax_get(item, AX.kAXTitleAttribute)
        if not isinstance(title, str) or title.upper() != target:
            continue
        if visible_in(item, win_rect):
            matches.append(item)
    if not matches:
        return None
    return sorted(matches, key=lambda e: (ax_rect(e).y, ax_rect(e).x))[0]


def selected_count_text(window) -> str:
    for item in walk(window):
        if ax_get(item, AX.kAXRoleAttribute) == AX.kAXStaticTextRole:
            value = ax_get(item, AX.kAXValueAttribute)
            if isinstance(value, str) and value.startswith("已选择"):
                return value
    return ""


def find_position_field(window, symbol: str):
    win_rect = ax_rect(window)
    if win_rect is None:
        raise RuntimeError("Cannot locate manager window bounds.")
    target = symbol.upper()
    symbol_rows = []
    for item in walk_right_side(window):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXStaticTextRole:
            continue
        value = ax_get(item, AX.kAXValueAttribute)
        rect = ax_rect(item)
        if isinstance(value, str) and value.upper() == target and rect and rect.x > win_rect.x + win_rect.w * 0.35:
            symbol_rows.append(rect.cy)

    fields = [
        f
        for f in walk_right_side(window)
        if ax_get(f, AX.kAXRoleAttribute) == AX.kAXTextFieldRole
        and ax_rect(f)
        and visible_in(f, win_rect)
        and ax_rect(f).x > win_rect.x + win_rect.w * 0.55
    ]
    if not fields:
        raise RuntimeError("Could not find the position percentage field after selecting the stock.")

    if symbol_rows:
        row_y = sorted(symbol_rows)[0]
        same_row = [f for f in fields if abs(ax_rect(f).cy - row_y) < 18]
        if same_row:
            return sorted(same_row, key=lambda f: ax_rect(f).x)[0]

    return sorted(fields, key=lambda f: (ax_rect(f).y, ax_rect(f).x))[0]


def position_row_centers(window, symbol: str) -> list[float]:
    win_rect = ax_rect(window)
    if win_rect is None:
        return []
    target = symbol.upper()
    rows: list[float] = []
    # Scan only the right pane. The left watchlist may expose many off-screen
    # nodes and can make close operations unexpectedly slow.
    for item in walk_right_side(window):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXStaticTextRole:
            continue
        value = ax_get(item, AX.kAXValueAttribute)
        rect = ax_rect(item)
        if (
            isinstance(value, str)
            and value.upper() == target
            and rect
            and visible_in(item, win_rect)
            and rect.x > win_rect.x + win_rect.w * 0.35
        ):
            rows.append(rect.cy)
    return sorted(rows)


def find_delete_button(window, symbol: str):
    win_rect = ax_rect(window)
    if win_rect is None:
        raise RuntimeError("Cannot locate manager window bounds.")

    rows = position_row_centers(window, symbol)
    if not rows:
        return None

    buttons = []
    for item in walk_right_side(window):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXButtonRole:
            continue
        if ax_get(item, AX.kAXDescriptionAttribute) != "paint_tool_delete":
            continue
        rect = ax_rect(item)
        if rect and visible_in(item, win_rect) and rect.x > win_rect.x + win_rect.w * 0.65:
            buttons.append(item)

    if not buttons:
        return None

    row_y = rows[0]
    same_row = [button for button in buttons if abs(ax_rect(button).cy - row_y) < 24]
    if same_row:
        return sorted(same_row, key=lambda button: ax_rect(button).x, reverse=True)[0]
    return sorted(buttons, key=lambda button: abs(ax_rect(button).cy - row_y))[0]


def find_confirm_button(window):
    win_rect = ax_rect(window)
    candidates = []
    # The confirm/cancel buttons are also direct children. Fall back to a full
    # walk only if Futu changes this structure in a future version.
    candidates_source = ax_children(window)
    for item in candidates_source:
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXButtonRole:
            continue
        rect = ax_rect(item)
        desc = ax_get(item, AX.kAXDescriptionAttribute)
        title = ax_get(item, AX.kAXTitleAttribute)
        text = ax_text(item)
        if not rect or not visible_in(item, win_rect):
            continue
        if desc == "pub_button_default" or title == "确定" or "确定" in text:
            candidates.append(item)
    if not candidates:
        for item in walk(window):
            if ax_get(item, AX.kAXRoleAttribute) != AX.kAXButtonRole:
                continue
            rect = ax_rect(item)
            desc = ax_get(item, AX.kAXDescriptionAttribute)
            title = ax_get(item, AX.kAXTitleAttribute)
            text = ax_text(item)
            if not rect or not visible_in(item, win_rect):
                continue
            if desc == "pub_button_default" or title == "确定" or "确定" in text:
                candidates.append(item)
    if not candidates:
        raise RuntimeError("Could not find the confirm button.")
    return sorted(candidates, key=lambda e: (ax_rect(e).y, ax_rect(e).x), reverse=True)[0]


def build_position(symbol: str, percent: str, dry_run: bool = False) -> None:
    check_accessibility_permission()
    pid = get_pid()
    activate_app()
    app = AX.AXUIElementCreateApplication(pid)

    manager = open_manager(app)
    focus_window(app, manager)
    search = find_search_field(manager)
    replace_text(search, symbol)

    checkbox = wait_for(lambda: find_visible_checkbox(manager, symbol), timeout=3.0)
    if not checkbox:
        raise RuntimeError(f"Could not find a visible search result for {symbol!r}.")

    if ax_get(checkbox, AX.kAXValueAttribute) != 1:
        press(checkbox)
        wait_for(lambda: "已选择" in selected_count_text(manager), timeout=1.0)
        time.sleep(0.12)

    position_field = wait_for(lambda: find_position_field(manager, symbol), timeout=2.0)
    replace_text(position_field, percent)

    if dry_run:
        print(f"Dry run complete: {symbol.upper()} is selected and position is set to {percent}%.")
        return

    confirm = find_confirm_button(manager)
    # Futu's custom confirm button can report AXPress success without firing.
    # A real mouse click on the button center is more reliable here.
    mouse_click(confirm)
    closed = wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=2.0)
    if not closed:
        raise RuntimeError("Clicked confirm, but the manager window is still open.")
    print(f"Done: {symbol.upper()} position set to {percent}%.")


def close_position(symbol: str, dry_run: bool = False) -> None:
    check_accessibility_permission()
    pid = get_pid()
    activate_app()
    app = AX.AXUIElementCreateApplication(pid)

    manager = open_manager(app)
    focus_window(app, manager)

    delete_button = wait_for(lambda: find_delete_button(manager, symbol), timeout=2.0)
    if not delete_button:
        raise RuntimeError(f"Could not find {symbol.upper()} in the current portfolio rows.")

    if dry_run:
        rect = ax_rect(delete_button)
        print(
            f"Dry run complete: found delete button for {symbol.upper()} "
            f"at ({rect.cx:.0f}, {rect.cy:.0f}); confirm was not clicked."
        )
        return

    mouse_click(delete_button)
    wait_for(lambda: not position_row_centers(manager, symbol), timeout=1.0)

    confirm = find_confirm_button(manager)
    mouse_click(confirm)
    closed = wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=2.0)
    if not closed:
        raise RuntimeError("Clicked confirm, but the manager window is still open.")
    print(f"Done: {symbol.upper()} was removed from the portfolio.")


def is_close_target(value: str) -> bool:
    normalized = value.strip().lower().rstrip("%")
    if normalized in {"close", "delete", "remove", "rm"}:
        return True
    try:
        return float(normalized) == 0.0
    except ValueError:
        return False


def main(argv: list[str]) -> int:
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
        "--dry-run",
        action="store_true",
        help="Stop before clicking the final confirm button.",
    )
    args = parser.parse_args(argv)

    symbol = args.symbol.strip()
    target = args.target.strip() if args.target else None
    if not symbol:
        raise SystemExit("Symbol cannot be empty.")

    if target and is_close_target(target):
        close_position(symbol=symbol, dry_run=args.dry_run)
        return 0

    percent = str(target if target else args.percent).strip().rstrip("%")
    if not percent:
        raise SystemExit("Percent cannot be empty.")

    build_position(symbol=symbol, percent=percent, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
