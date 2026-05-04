"""Portfolio selection helpers for the Futu portfolio page."""

from __future__ import annotations

import re
import subprocess
import time
from typing import Optional

from .constants import MANAGER_TITLE, PORTFOLIO_SETTLE, PROCESS_NAME
from .pyobjc_runtime import AX, Quartz
from .ax_utils import (
    ax_get,
    ax_rect,
    find_button_by_description,
    find_descendant,
    mouse_click,
    mouse_click_xy,
    visible_in,
    wait_for,
    walk,
)
from .futu_app import ensure_portfolio_page, find_window, focus_window, windows
from .models import Rect

PORTFOLIO_CODE_RE = re.compile(r"PFL\d+", re.IGNORECASE)


def find_sheet(window):
    sheet_role = getattr(AX, "kAXSheetRole", "AXSheet")
    return find_descendant(window, lambda e: ax_get(e, AX.kAXRoleAttribute) == sheet_role)


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
