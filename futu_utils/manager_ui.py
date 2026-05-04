"""Selectors and actions inside Futu's Portfolio Manager window."""

from __future__ import annotations

from typing import Iterable, Optional

from .pyobjc_runtime import AX
from .ax_utils import ax_children, ax_get, ax_rect, ax_text, visible_in, walk
from .models import Rect


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
