#!/usr/bin/env python3
"""Automate FutuNiuniu portfolio-manager position setup on macOS.

Usage:
    python3 futu_portfolio.py MSFT
    python3 futu_portfolio.py MSFT 50
    python3 futu_portfolio.py MSFT close
    python3 futu_portfolio.py MSFT 0
    python3 futu_portfolio.py MSFT 100 --no-record
    python3 futu_portfolio.py MSFT --percent 100 --dry-run
    python3 futu_portfolio.py MSFT 50 --portfolio PFL0137605

This script drives the existing FutuNiuniu UI via macOS Accessibility.
It does not use a trading API and does not place real brokerage orders.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

# Keep this near the top so the final elapsed time includes most command startup
# and import overhead.
COMMAND_STARTED_AT = time.perf_counter()

PROCESS_NAME = "FutuNiuniu"
APP_PATH = "/Applications/FutuNiuniu.app"
APPLESCRIPT_NAME = "FutuNiuniu"
MANAGER_TITLE = "组合管理"
RECORD_FILENAME = "alpha_second.csv"
RECORD_HEADER = ["日期", "时间", "股票名称", "代码", "变化前持仓", "变化后持仓", "成交价", "说明"]
PORTFOLIO_CODE_RE = re.compile(r"PFL\d+", re.IGNORECASE)

KEY_A = 0
KEY_V = 9
KEY_DELETE = 51
AX = None
Quartz = None
CMD = 0
EVENT_PAUSE = 0.003
FOCUS_SETTLE = 0.01
SEARCH_RESULT_SETTLE = 0.24
ROW_SETTLE = 0.02
PORTFOLIO_SETTLE = 0.15


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


def load_pyobjc() -> None:
    global AX, Quartz, CMD
    if AX is not None and Quartz is not None:
        return

    try:
        import ApplicationServices as loaded_ax
        import Quartz as loaded_quartz
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise SystemExit(
            "Missing PyObjC modules. Install with: python3 -m pip install pyobjc"
        ) from exc

    AX = loaded_ax
    Quartz = loaded_quartz
    CMD = Quartz.kCGEventFlagMaskCommand


def check_accessibility_permission() -> None:
    load_pyobjc()
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


def wait_for(predicate: Callable, timeout: float, interval: float = 0.02):
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
        time.sleep(EVENT_PAUSE)


def mouse_click(element) -> None:
    rect = ax_rect(element)
    if rect is None:
        raise RuntimeError("Cannot click element without position/size")
    mouse_click_xy(rect.cx, rect.cy)


def search_result_checkbox_point(window) -> Optional[tuple[float, float]]:
    win_rect = ax_rect(window)
    if win_rect is None:
        return None
    return win_rect.x + 59, win_rect.y + 162


def first_position_field_point(window) -> Optional[tuple[float, float]]:
    win_rect = ax_rect(window)
    if win_rect is None:
        return None
    return win_rect.x + win_rect.w - 98, win_rect.y + 170


def confirm_button_point(window) -> Optional[tuple[float, float]]:
    win_rect = ax_rect(window)
    if win_rect is None:
        return None
    return win_rect.x + win_rect.w - 62, win_rect.y + win_rect.h - 32


def mouse_click_point(point: Optional[tuple[float, float]]) -> bool:
    if point is None:
        return False
    mouse_click_xy(point[0], point[1])
    return True


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
        time.sleep(EVENT_PAUSE)


def set_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def set_text_via_ax(field, text: str) -> bool:
    AX.AXUIElementSetAttributeValue(field, AX.kAXFocusedAttribute, True)
    err = AX.AXUIElementSetAttributeValue(field, AX.kAXValueAttribute, text)
    return err == 0


def replace_text(field, text: str, settle: float = 0.0) -> None:
    if set_text_via_ax(field, text):
        if settle:
            time.sleep(settle)
        return

    AX.AXUIElementSetAttributeValue(field, AX.kAXFocusedAttribute, True)
    mouse_click(field)
    time.sleep(FOCUS_SETTLE)
    set_clipboard(text)
    keypress(KEY_A, CMD)
    keypress(KEY_DELETE)
    keypress(KEY_V, CMD)
    time.sleep(FOCUS_SETTLE)


def button_text_is(element, label: str) -> bool:
    if ax_get(element, AX.kAXRoleAttribute) != AX.kAXButtonRole:
        return False
    return label in ax_text(element)


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


def find_sheet(window):
    sheet_role = getattr(AX, "kAXSheetRole", "AXSheet")
    return find_descendant(window, lambda e: ax_get(e, AX.kAXRoleAttribute) == sheet_role)


def find_button_by_description(element, description: str, *, prefer_right: bool = False):
    buttons = []
    for item in walk(element):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXButtonRole:
            continue
        if ax_get(item, AX.kAXDescriptionAttribute) != description:
            continue
        rect = ax_rect(item)
        if rect:
            buttons.append(item)
    if not buttons:
        return None
    return sorted(buttons, key=lambda item: ax_rect(item).x, reverse=prefer_right)[0]


def click_manager_sheet_choice(manager, *, save: bool) -> bool:
    sheet = find_sheet(manager)
    if not sheet:
        return False
    description = "pub_button_default" if save else "pub_button_normal"
    button = find_button_by_description(sheet, description, prefer_right=save)
    if not button:
        return False
    mouse_click(button)
    return True


def close_manager_without_saving(app) -> bool:
    manager = find_window(app, MANAGER_TITLE)
    if not manager:
        return True

    focus_window(app, manager)
    if click_manager_sheet_choice(manager, save=False):
        return bool(wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=1.5))

    cancel = find_button_by_description(manager, "pub_button_normal", prefer_right=False)
    if not cancel:
        return False
    mouse_click(cancel)

    def closed_or_sheet():
        current = find_window(app, MANAGER_TITLE)
        if not current:
            return True
        sheet = find_sheet(current)
        return sheet or None

    result = wait_for(closed_or_sheet, timeout=1.0)
    if result is True:
        return True

    manager = find_window(app, MANAGER_TITLE)
    if manager and click_manager_sheet_choice(manager, save=False):
        return bool(wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=1.5))
    return False


def ensure_portfolio_page(app) -> None:
    portfolio_button = find_portfolio_nav_button(app)
    if portfolio_button:
        press(portfolio_button)
        wait_for(lambda: find_manager_button(app), timeout=2.5)


def element_text_values(element) -> list[str]:
    values: list[str] = []
    for attr in (
        AX.kAXTitleAttribute,
        AX.kAXDescriptionAttribute,
        AX.kAXValueAttribute,
        AX.kAXIdentifierAttribute,
    ):
        value = ax_get(element, attr)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def element_matches_portfolio_code(element, portfolio_code: str) -> bool:
    target = portfolio_code.strip().upper()
    if not target:
        return False

    for value in element_text_values(element):
        normalized = value.strip().upper()
        codes = [match.upper() for match in PORTFOLIO_CODE_RE.findall(normalized)]
        if target in codes or normalized == target or target in normalized.split():
            return True
    return False


def visible_portfolio_codes(app) -> list[str]:
    found: set[str] = set()
    for window in windows(app):
        if ax_get(window, AX.kAXTitleAttribute) == MANAGER_TITLE:
            continue
        win_rect = ax_rect(window)
        if win_rect is None:
            continue
        for item in walk(window):
            rect = ax_rect(item)
            if not rect or not visible_in(item, win_rect):
                continue
            for value in element_text_values(item):
                found.update(match.upper() for match in PORTFOLIO_CODE_RE.findall(value))
    return sorted(found)


def portfolio_list_rect(app) -> Optional[Rect]:
    for window in windows(app):
        win_rect = ax_rect(window)
        if win_rect is None:
            continue
        for item in walk(window):
            if ax_get(item, AX.kAXRoleAttribute) != AX.kAXTableRole:
                continue
            rect = ax_rect(item)
            desc = ax_get(item, AX.kAXDescriptionAttribute)
            identifier = ax_get(item, AX.kAXIdentifierAttribute)
            if (
                rect
                and visible_in(item, win_rect)
                and rect.x < win_rect.x + win_rect.w * 0.35
                and (
                    desc == "gridView"
                    or identifier == "accessibility.futu.FTQPortfolioGridViewController"
                )
            ):
                return rect
    return None


def find_visible_portfolio_code(app, portfolio_code: str):
    candidates = []
    for window in windows(app):
        if ax_get(window, AX.kAXTitleAttribute) == MANAGER_TITLE:
            continue
        win_rect = ax_rect(window)
        if win_rect is None:
            continue
        for item in walk(window):
            rect = ax_rect(item)
            if not rect or not visible_in(item, win_rect):
                continue
            if element_matches_portfolio_code(item, portfolio_code):
                candidates.append((rect.w * rect.h, rect.y, rect.x, item))
    if not candidates:
        return None
    # Prefer the smallest matching visible element. In Futu's list this is
    # usually the code label itself, which is a safe click target for the row.
    return sorted(candidates, key=lambda candidate: candidate[:3])[0][3]


def futu_window_info():
    pid = int(subprocess.check_output(["pgrep", "-x", PROCESS_NAME]).splitlines()[0])
    window_infos = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
    )
    candidates = [
        info
        for info in window_infos
        if info.get("kCGWindowOwnerPID") == pid
        and info.get("kCGWindowLayer") == 0
        and info.get("kCGWindowIsOnscreen")
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda info: info["kCGWindowBounds"]["Width"] * info["kCGWindowBounds"]["Height"],
    )


def capture_futu_window_image():
    info = futu_window_info()
    if info is None:
        return None, None
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        info["kCGWindowNumber"],
        Quartz.kCGWindowImageBoundsIgnoreFraming,
    )
    return image, info


def ocr_click_portfolio_code(app, portfolio_code: str) -> bool:
    try:
        import Vision
    except ImportError:
        return False

    image, info = capture_futu_window_image()
    list_rect = portfolio_list_rect(app)
    if image is None or info is None or list_rect is None:
        return False

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(False)
    if hasattr(request, "setRecognitionLanguages_"):
        request.setRecognitionLanguages_(["en-US", "zh-Hans"])

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
    success, _ = handler.performRequests_error_([request], None)
    if not success:
        return False

    bounds = info["kCGWindowBounds"]
    win_x = float(bounds["X"])
    win_y = float(bounds["Y"])
    win_w = float(bounds["Width"])
    win_h = float(bounds["Height"])
    target = portfolio_code.strip().upper()
    candidates: list[tuple[float, float, float]] = []

    for observation in request.results() or []:
        top_candidates = observation.topCandidates_(3)
        if not top_candidates:
            continue
        for candidate in top_candidates:
            text = candidate.string().upper()
            codes = [match.upper() for match in PORTFOLIO_CODE_RE.findall(text)]
            if target not in codes and text.strip() != target:
                continue

            box = observation.boundingBox()
            cx = win_x + (box.origin.x + box.size.width / 2) * win_w
            cy = win_y + (1 - box.origin.y - box.size.height / 2) * win_h
            if (
                list_rect.x <= cx <= list_rect.right
                and list_rect.y <= cy <= list_rect.bottom
            ):
                candidates.append((candidate.confidence(), cx, cy))

    if not candidates:
        return False

    _, x, y = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    mouse_click_xy(x, y)
    time.sleep(PORTFOLIO_SETTLE)
    return True


def select_portfolio(
    app,
    portfolio_code: Optional[str],
    *,
    discard_open_manager: bool = False,
) -> None:
    if not portfolio_code:
        return

    normalized = portfolio_code.strip().upper()
    if not normalized:
        return

    if find_window(app, MANAGER_TITLE):
        if discard_open_manager:
            if not close_manager_without_saving(app):
                raise RuntimeError(
                    "A Portfolio Manager window is already open and could not be discarded."
                )
        else:
            raise RuntimeError(
                "A Portfolio Manager window is already open. Close it before using "
                f"--portfolio {normalized}, or pass --discard-open-manager to close it "
                "without saving first."
            )

    ensure_portfolio_page(app)
    target = find_visible_portfolio_code(app, normalized)
    if not target:
        target = wait_for(lambda: find_visible_portfolio_code(app, normalized), timeout=2.0)
    if not target and ocr_click_portfolio_code(app, normalized):
        return
    if not target:
        seen_codes = visible_portfolio_codes(app)
        seen_text = ", ".join(seen_codes) if seen_codes else "none"
        raise RuntimeError(
            f"Could not find visible portfolio code {normalized!r}. "
            "Open the Portfolio page and make sure that portfolio is visible in the list. "
            f"Visible portfolio codes seen by Accessibility: {seen_text}."
        )

    mouse_click(target)
    time.sleep(PORTFOLIO_SETTLE)


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


def left_search_results(window):
    win_rect = ax_rect(window)
    if win_rect is None:
        return None
    for child in ax_children(window):
        rect = ax_rect(child)
        if (
            ax_get(child, AX.kAXRoleAttribute) == AX.kAXScrollAreaRole
            and rect
            and visible_in(child, win_rect)
            and rect.x < win_rect.x + win_rect.w * 0.45
        ):
            return child
    return None


def right_position_area(window):
    win_rect = ax_rect(window)
    if win_rect is None:
        return None
    for child in ax_children(window):
        rect = ax_rect(child)
        if (
            ax_get(child, AX.kAXRoleAttribute) == AX.kAXScrollAreaRole
            and rect
            and visible_in(child, win_rect)
            and rect.x > win_rect.x + win_rect.w * 0.35
        ):
            return child
    return None


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


def find_first_position_field(window):
    win_rect = ax_rect(window)
    area = right_position_area(window)
    if win_rect is None or area is None:
        return None

    fields = []
    for item in walk(area):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXTextFieldRole:
            continue
        rect = ax_rect(item)
        if rect and visible_in(item, win_rect):
            fields.append(item)
    if not fields:
        return None
    return sorted(fields, key=lambda item: (ax_rect(item).y, ax_rect(item).x))[0]


def first_position_symbol(window) -> str:
    area = right_position_area(window)
    area_rect = ax_rect(area) if area else None
    win_rect = ax_rect(window)
    if area is None or area_rect is None or win_rect is None:
        return ""

    symbols: list[tuple[float, float, str]] = []
    for item in walk(area):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXStaticTextRole:
            continue
        value = ax_get(item, AX.kAXValueAttribute)
        rect = ax_rect(item)
        if (
            isinstance(value, str)
            and value
            and rect
            and visible_in(item, win_rect)
            and area_rect.x <= rect.x <= area_rect.x + 100
            and area_rect.y <= rect.y <= area_rect.y + 55
        ):
            symbols.append((rect.y, rect.x, value))
    if not symbols:
        return ""
    return sorted(symbols)[0][2].upper()


def find_first_search_checkbox(window):
    source = left_search_results(window)
    if source is None:
        return None
    for item in walk(source):
        if ax_get(item, AX.kAXRoleAttribute) == AX.kAXCheckBoxRole:
            return item
    return None


def find_first_matching_search_checkbox(window, symbol: str):
    checkbox = find_first_search_checkbox(window)
    title = ax_get(checkbox, AX.kAXTitleAttribute) if checkbox else None
    if isinstance(title, str) and title.upper() == symbol.upper():
        return checkbox
    return None


def find_visible_checkbox(window, symbol: str):
    win_rect = ax_rect(window)
    target = symbol.upper()
    source = left_search_results(window) or window
    for item in walk(source):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXCheckBoxRole:
            continue
        title = ax_get(item, AX.kAXTitleAttribute)
        if not isinstance(title, str) or title.upper() != target:
            continue
        if visible_in(item, win_rect):
            return item
    return None


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

    if not symbol_rows:
        return None

    row_y = sorted(symbol_rows)[0]
    same_row = [f for f in fields if abs(ax_rect(f).cy - row_y) < 18]
    if same_row:
        return sorted(same_row, key=lambda f: ax_rect(f).x)[0]

    return None


def find_existing_position_field(window, symbol: str):
    first_field = find_first_position_field(window)
    if not first_field:
        return None
    if first_position_symbol(window) == symbol.upper():
        return first_field

    win_rect = ax_rect(window)
    if win_rect is None:
        return None
    rows = position_row_centers(window, symbol)
    if not rows:
        return None

    fields = [
        f
        for f in walk_right_side(window)
        if ax_get(f, AX.kAXRoleAttribute) == AX.kAXTextFieldRole
        and ax_rect(f)
        and visible_in(f, win_rect)
        and ax_rect(f).x > win_rect.x + win_rect.w * 0.55
    ]
    row_y = rows[0]
    same_row = [f for f in fields if abs(ax_rect(f).cy - row_y) < 18]
    if not same_row:
        return None
    return sorted(same_row, key=lambda f: ax_rect(f).x)[0]


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


def format_percent(value) -> str:
    text = "" if value is None else str(value).strip().rstrip("%").strip()
    if not text:
        return ""
    try:
        return f"{float(text):.2f}%"
    except ValueError:
        return f"{text}%"


def position_row_details(window, symbol: str) -> dict[str, str]:
    win_rect = ax_rect(window)
    rows = position_row_centers(window, symbol)
    if win_rect is None or not rows:
        return {"name": "", "percent": ""}

    row_y = rows[0]
    row_texts: list[tuple[float, str]] = []
    row_fields = []
    for item in walk_right_side(window):
        rect = ax_rect(item)
        if not rect or not visible_in(item, win_rect) or abs(rect.cy - row_y) >= 24:
            continue
        role = ax_get(item, AX.kAXRoleAttribute)
        value = ax_get(item, AX.kAXValueAttribute)
        if role == AX.kAXStaticTextRole and isinstance(value, str) and value:
            row_texts.append((rect.x, value))
        elif role == AX.kAXTextFieldRole:
            row_fields.append(item)

    row_texts.sort(key=lambda item: item[0])
    target = symbol.upper()
    name = ""
    for index, (_, value) in enumerate(row_texts):
        if value.upper() == target:
            for _, next_value in row_texts[index + 1 :]:
                if next_value not in {"%", "美股", "港股", "沪深"}:
                    name = next_value
                    break
            break

    percent = ""
    if row_fields:
        field = sorted(row_fields, key=lambda item: ax_rect(item).x)[0]
        percent = format_percent(ax_get(field, AX.kAXValueAttribute))

    return {"name": name, "percent": percent}


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


def elapsed_seconds(started_at: float) -> str:
    return f"{time.perf_counter() - started_at:.2f}s"


def build_position(
    symbol: str,
    percent: str,
    dry_run: bool = False,
    record: bool = True,
    portfolio_code: Optional[str] = None,
    discard_open_manager: bool = False,
    started_at: Optional[float] = None,
) -> None:
    check_accessibility_permission()
    pid = get_pid()
    app = AX.AXUIElementCreateApplication(pid)
    activate_app(app)

    select_portfolio(app, portfolio_code, discard_open_manager=discard_open_manager)
    manager = open_manager(app)
    position_field = find_existing_position_field(manager, symbol)
    if not position_field:
        search = find_search_field(manager)
        replace_text(search, symbol, settle=SEARCH_RESULT_SETTLE)

        position_field = None
        checkbox = find_first_matching_search_checkbox(manager, symbol)
        if not checkbox:
            checkbox = wait_for(
                lambda: find_first_matching_search_checkbox(manager, symbol),
                timeout=0.4,
                interval=0.01,
            )
        if checkbox and mouse_click_point(search_result_checkbox_point(manager)):
            time.sleep(ROW_SETTLE)
            position_field = wait_for(lambda: find_position_field(manager, symbol), timeout=0.6)

        if not position_field:
            checkbox = checkbox or wait_for(lambda: find_visible_checkbox(manager, symbol), timeout=2.0)
            if not checkbox:
                raise RuntimeError(f"Could not find a visible search result for {symbol!r}.")
            mouse_click(checkbox)
            time.sleep(ROW_SETTLE)
            position_field = wait_for(lambda: find_position_field(manager, symbol), timeout=1.0)
    if not position_field:
        raise RuntimeError("Could not find the position percentage field after selecting the stock.")
    if record:
        details = position_row_details(manager, symbol)
        before_percent = details["percent"] or format_percent(ax_get(position_field, AX.kAXValueAttribute))
        after_percent = format_percent(percent)
    replace_text(position_field, percent)

    if dry_run:
        portfolio_text = f" in portfolio {portfolio_code.strip().upper()}" if portfolio_code else ""
        print(
            f"Dry run complete: {symbol.upper()} is selected{portfolio_text} "
            f"and position is set to {percent}%."
        )
        return

    if not mouse_click_point(confirm_button_point(manager)):
        confirm = find_confirm_button(manager)
        # Futu's custom confirm button can report AXPress success without firing.
        # A real mouse click on the button center is more reliable here.
        mouse_click(confirm)
    closed = wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=2.0)
    if not closed:
        raise RuntimeError("Clicked confirm, but the manager window is still open.")
    if record:
        path = append_rebalance_record(
            symbol=symbol,
            stock_name=details["name"],
            before_percent=before_percent,
            after_percent=after_percent,
        )
        print(f"Record written: {path}")
    elapsed = f" Elapsed: {elapsed_seconds(started_at)}." if started_at is not None else ""
    portfolio_text = f" in portfolio {portfolio_code.strip().upper()}" if portfolio_code else ""
    print(f"Done: {symbol.upper()} position set to {percent}%{portfolio_text}.{elapsed}")


def close_position(
    symbol: str,
    dry_run: bool = False,
    record: bool = True,
    portfolio_code: Optional[str] = None,
    discard_open_manager: bool = False,
    started_at: Optional[float] = None,
) -> None:
    check_accessibility_permission()
    pid = get_pid()
    app = AX.AXUIElementCreateApplication(pid)
    activate_app(app)

    select_portfolio(app, portfolio_code, discard_open_manager=discard_open_manager)
    manager = open_manager(app)

    delete_button = wait_for(lambda: find_delete_button(manager, symbol), timeout=2.0)
    if not delete_button:
        raise RuntimeError(f"Could not find {symbol.upper()} in the current portfolio rows.")
    if record:
        details = position_row_details(manager, symbol)
        before_percent = details["percent"]

    if dry_run:
        rect = ax_rect(delete_button)
        portfolio_text = f" in portfolio {portfolio_code.strip().upper()}" if portfolio_code else ""
        print(
            f"Dry run complete: found delete button for {symbol.upper()}{portfolio_text} "
            f"at ({rect.cx:.0f}, {rect.cy:.0f}); confirm was not clicked."
        )
        return

    mouse_click(delete_button)
    wait_for(lambda: not position_row_centers(manager, symbol), timeout=1.0)

    if not mouse_click_point(confirm_button_point(manager)):
        confirm = find_confirm_button(manager)
        mouse_click(confirm)
    closed = wait_for(lambda: find_window(app, MANAGER_TITLE) is None, timeout=2.0)
    if not closed:
        raise RuntimeError("Clicked confirm, but the manager window is still open.")
    if record:
        path = append_rebalance_record(
            symbol=symbol,
            stock_name=details["name"],
            before_percent=before_percent,
            after_percent="0.00%",
        )
        print(f"Record written: {path}")
    elapsed = f" Elapsed: {elapsed_seconds(started_at)}." if started_at is not None else ""
    portfolio_text = f" {portfolio_code.strip().upper()}" if portfolio_code else ""
    print(f"Done: {symbol.upper()} was removed from the portfolio{portfolio_text}.{elapsed}")


def is_close_target(value: str) -> bool:
    normalized = value.strip().lower().rstrip("%")
    if normalized in {"close", "delete", "remove", "rm"}:
        return True
    try:
        return float(normalized) == 0.0
    except ValueError:
        return False


def main(argv: list[str]) -> int:
    started_at = COMMAND_STARTED_AT
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
        "--no-record",
        dest="record",
        action="store_false",
        default=True,
        help="Do not append fabu_utils/alpha_second.csv after a successful change.",
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
    args = parser.parse_args(argv)

    symbol = args.symbol.strip()
    target = args.target.strip() if args.target else None
    portfolio_code = args.portfolio_code.strip().upper()
    if not symbol:
        raise SystemExit("Symbol cannot be empty.")

    should_record = args.record
    if target and is_close_target(target):
        close_position(
            symbol=symbol,
            dry_run=args.dry_run,
            record=should_record,
            portfolio_code=portfolio_code,
            discard_open_manager=args.discard_open_manager,
            started_at=started_at,
        )
        return 0

    percent = str(target if target else args.percent).strip().rstrip("%")
    if not percent:
        raise SystemExit("Percent cannot be empty.")

    build_position(
        symbol=symbol,
        percent=percent,
        dry_run=args.dry_run,
        record=should_record,
        portfolio_code=portfolio_code,
        discard_open_manager=args.discard_open_manager,
        started_at=started_at,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
