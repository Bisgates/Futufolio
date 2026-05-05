"""Selectors and actions inside Futu's Portfolio Manager window."""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional, TypeVar

from .pyobjc_runtime import AX
from .ax_utils import ax_children, ax_get, ax_rect, ax_text, visible_in, walk
from .models import Rect


T = TypeVar("T")
SCROLL_SETTLE = 0.015
SCROLL_SCAN_VALUES = (
    0.0,
    0.08,
    0.16,
    0.24,
    0.32,
    0.40,
    0.48,
    0.56,
    0.64,
    0.72,
    0.80,
    0.88,
    0.96,
    1.0,
)


def walk_right_side(window) -> Iterable:
    win_rect = ax_rect(window)
    if win_rect is None:
        return
    threshold = win_rect.x + win_rect.w * 0.35
    for child in ax_children(window):
        rect = ax_rect(child)
        if rect and visible_in(child, win_rect) and rect.x > threshold:
            yield from walk(child)


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


def safely_visible_in_right_position_area(element, window) -> bool:
    area = right_position_area(window)
    area_rect = ax_rect(area) if area else None
    if area_rect is None:
        return False
    return visible_in(element, area_rect, margin=0)


def raw_position_row_centers(window, symbol: str) -> list[float]:
    area = right_position_area(window)
    area_rect = ax_rect(area) if area else None
    if area is None or area_rect is None:
        return []

    target = symbol.upper()
    rows: list[float] = []
    for item in walk(area):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXStaticTextRole:
            continue
        value = ax_get(item, AX.kAXValueAttribute)
        rect = ax_rect(item)
        if (
            isinstance(value, str)
            and value.upper() == target
            and rect
            and area_rect.x <= rect.x <= area_rect.x + 100
        ):
            rows.append(rect.cy)
    return sorted(rows)


def bring_position_symbol_into_view(window, symbol: str) -> bool:
    area = right_position_area(window)
    area_rect = ax_rect(area) if area else None
    current_value = right_position_scroll_value(window)
    if area_rect is None or current_value is None:
        return False

    rows = raw_position_row_centers(window, symbol)
    if not rows:
        return False

    target_y = rows[0]
    if area_rect.y <= target_y <= area_rect.bottom:
        return True

    direction = 1.0 if target_y > area_rect.bottom else -1.0
    probe_value = max(0.0, min(1.0, current_value + direction * 0.08))
    if probe_value == current_value:
        return False

    if not set_right_position_scroll_value(window, probe_value):
        return False

    probe_rows = raw_position_row_centers(window, symbol)
    if not probe_rows:
        set_right_position_scroll_value(window, current_value)
        return False

    probe_y = probe_rows[0]
    y_per_scroll = (probe_y - target_y) / (probe_value - current_value)
    if abs(y_per_scroll) < 1:
        set_right_position_scroll_value(window, current_value)
        return False

    desired_y = area_rect.y + area_rect.h * 0.5
    desired_value = current_value + (desired_y - target_y) / y_per_scroll
    return set_right_position_scroll_value(window, desired_value)


def right_position_scroll_bar(window):
    area = right_position_area(window)
    if area is None:
        return None

    scroll_bar = ax_get(area, AX.kAXVerticalScrollBarAttribute)
    if scroll_bar is not None:
        return scroll_bar

    for child in ax_children(area):
        if ax_get(child, AX.kAXRoleAttribute) != AX.kAXScrollBarRole:
            continue
        rect = ax_rect(child)
        if rect and rect.h >= rect.w:
            return child
    return None


def right_position_scroll_value(window) -> Optional[float]:
    scroll_bar = right_position_scroll_bar(window)
    if scroll_bar is None:
        return None
    value = ax_get(scroll_bar, AX.kAXValueAttribute)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def set_right_position_scroll_value(window, value: float) -> bool:
    scroll_bar = right_position_scroll_bar(window)
    if scroll_bar is None:
        return False
    bounded = max(0.0, min(1.0, value))
    err = AX.AXUIElementSetAttributeValue(scroll_bar, AX.kAXValueAttribute, bounded)
    if err != 0:
        return False
    time.sleep(SCROLL_SETTLE)
    return True


def find_across_position_pages(window, finder: Callable[[], T | None]) -> T | None:
    """Run a visible-row finder, then scan the right position list by scroll page.

    The fast path still checks the current visible rows first.  The scroll
    fallback fixes portfolios where the target symbol exists but is currently
    below/above the visible slice of the selected-position table.
    """

    found = finder()
    if found:
        return found

    original_value = right_position_scroll_value(window)
    if original_value is None:
        return None

    if not set_right_position_scroll_value(window, 0.0):
        return None

    found = finder()
    if found:
        return found

    seen_values = {round(right_position_scroll_value(window) or 0.0, 4)}
    for target_value in SCROLL_SCAN_VALUES[1:]:
        if not set_right_position_scroll_value(window, target_value):
            break
        current_value = right_position_scroll_value(window)
        if current_value is not None:
            rounded = round(current_value, 4)
            if rounded in seen_values and target_value >= 1.0:
                break
            seen_values.add(rounded)

        found = finder()
        if found:
            return found

    set_right_position_scroll_value(window, original_value)
    return None


def find_search_field(window):
    win_rect = ax_rect(window)
    if win_rect is None:
        raise RuntimeError("Cannot locate manager window bounds.")
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
    area = right_position_area(window)
    if area is None:
        return None

    fields = []
    for item in walk(area):
        if ax_get(item, AX.kAXRoleAttribute) != AX.kAXTextFieldRole:
            continue
        rect = ax_rect(item)
        if rect and safely_visible_in_right_position_area(item, window):
            fields.append(item)
    if not fields:
        return None
    return sorted(fields, key=lambda item: (ax_rect(item).y, ax_rect(item).x))[0]


def first_position_symbol(window) -> str:
    area = right_position_area(window)
    area_rect = ax_rect(area) if area else None
    if area is None or area_rect is None:
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
            and safely_visible_in_right_position_area(item, window)
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
    if win_rect is None:
        return None
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
        if (
            isinstance(value, str)
            and value.upper() == target
            and rect
            and safely_visible_in_right_position_area(item, window)
            and rect.x > win_rect.x + win_rect.w * 0.35
        ):
            symbol_rows.append(rect.cy)

    fields = [
        f
        for f in walk_right_side(window)
        if ax_get(f, AX.kAXRoleAttribute) == AX.kAXTextFieldRole
        and ax_rect(f)
        and safely_visible_in_right_position_area(f, window)
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
        and safely_visible_in_right_position_area(f, window)
        and ax_rect(f).x > win_rect.x + win_rect.w * 0.55
    ]
    row_y = rows[0]
    same_row = [f for f in fields if abs(ax_rect(f).cy - row_y) < 18]
    if not same_row:
        return None
    return sorted(same_row, key=lambda f: ax_rect(f).x)[0]


def find_existing_position_field_across_pages(window, symbol: str):
    if bring_position_symbol_into_view(window, symbol):
        found = find_existing_position_field(window, symbol)
        if found:
            return found
    return find_across_position_pages(
        window,
        lambda: find_existing_position_field(window, symbol),
    )


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
            and safely_visible_in_right_position_area(item, window)
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
        if (
            rect
            and safely_visible_in_right_position_area(item, window)
            and rect.x > win_rect.x + win_rect.w * 0.65
        ):
            buttons.append(item)

    if not buttons:
        return None

    row_y = rows[0]
    same_row = [button for button in buttons if abs(ax_rect(button).cy - row_y) < 24]
    if same_row:
        return sorted(same_row, key=lambda button: ax_rect(button).x, reverse=True)[0]
    return sorted(buttons, key=lambda button: abs(ax_rect(button).cy - row_y))[0]


def find_delete_button_across_pages(window, symbol: str):
    if bring_position_symbol_into_view(window, symbol):
        found = find_delete_button(window, symbol)
        if found:
            return found
    return find_across_position_pages(
        window,
        lambda: find_delete_button(window, symbol),
    )


def format_percent(value) -> str:
    text = "" if value is None else str(value).strip().rstrip("%").strip()
    if not text:
        return ""
    try:
        return f"{float(text):.2f}%"
    except ValueError:
        return f"{text}%"


def position_row_details(window, symbol: str) -> dict[str, str]:
    rows = position_row_centers(window, symbol)
    if not rows:
        return {"name": "", "percent": ""}

    row_y = rows[0]
    row_texts: list[tuple[float, str]] = []
    row_fields = []
    for item in walk_right_side(window):
        rect = ax_rect(item)
        if (
            not rect
            or not safely_visible_in_right_position_area(item, window)
            or abs(rect.cy - row_y) >= 24
        ):
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


def find_confirm_button(window):
    win_rect = ax_rect(window)
    if win_rect is None:
        raise RuntimeError("Cannot locate manager window bounds.")
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
