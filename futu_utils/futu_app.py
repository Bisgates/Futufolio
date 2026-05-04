"""FutuNiuniu application and window navigation helpers."""

from __future__ import annotations

import subprocess
import time

from .constants import APP_PATH, APPLESCRIPT_NAME, FOCUS_SETTLE, MANAGER_TITLE, PROCESS_NAME
from .pyobjc_runtime import AX
from .ax_utils import (
    ax_get,
    ax_rect,
    button_text_is,
    find_descendant,
    press,
    run_quiet,
    wait_for,
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


def activate_app(app=None) -> None:
    if app is not None:
        err = AX.AXUIElementSetAttributeValue(app, AX.kAXFrontmostAttribute, True)
        if err == 0:
            return
    run_quiet(["osascript", "-e", f'tell application "{APPLESCRIPT_NAME}" to activate'])
    time.sleep(FOCUS_SETTLE)


def focus_window(app, window) -> None:
    AX.AXUIElementSetAttributeValue(app, AX.kAXFrontmostAttribute, True)
    AX.AXUIElementSetAttributeValue(window, AX.kAXMainAttribute, True)
    time.sleep(FOCUS_SETTLE)


def windows(app) -> list:
    return ax_get(app, AX.kAXWindowsAttribute) or []


def find_window(app, title: str):
    for window in windows(app):
        if ax_get(window, AX.kAXTitleAttribute) == title:
            return window
    return None


def find_portfolio_nav_button(app):
    for window in windows(app):
        portfolio_button = find_descendant(
            window,
            lambda e: button_text_is(e, "组合") and ax_rect(e) and ax_rect(e).x < 140,
        )
        if portfolio_button:
            return portfolio_button
    return None


def find_manager_button(app):
    for window in windows(app):
        found = find_descendant(window, lambda e: button_text_is(e, MANAGER_TITLE))
        if found:
            return found
    return None


def ensure_portfolio_page(app) -> None:
    portfolio_button = find_portfolio_nav_button(app)
    if portfolio_button:
        press(portfolio_button)
        wait_for(lambda: find_manager_button(app), timeout=2.5)


def open_manager(app):
    manager = find_window(app, MANAGER_TITLE)
    if manager:
        focus_window(app, manager)
        return manager

    button = find_manager_button(app)
    if not button:
        # Navigate to the portfolio tab only when the manager button is not
        # already visible. This is the hot path after the first successful run.
        portfolio_button = find_portfolio_nav_button(app)
        if portfolio_button:
            press(portfolio_button)

        button = wait_for(lambda: find_manager_button(app), timeout=2.5)
    if not button:
        raise RuntimeError("Could not find the '组合管理' button. Is the Portfolio page open?")
    press(button)

    manager = wait_for(lambda: find_window(app, MANAGER_TITLE), timeout=2.5)
    if not manager:
        raise RuntimeError("Clicked '组合管理', but the manager window did not appear.")
    focus_window(app, manager)
    return manager
