"""Reusable macOS Accessibility and input helpers."""

from __future__ import annotations

import subprocess
import time
from typing import Callable, Iterable, Optional

from .constants import EVENT_PAUSE, FOCUS_SETTLE, KEY_A, KEY_DELETE, KEY_V
from .models import Rect
from .pyobjc_runtime import AX, Quartz, cmd_flag


def run_quiet(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        **kwargs,
    )


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


def visible_in(element, container: Optional[Rect], margin: float = 4) -> bool:
    if container is None:
        return False
    rect = ax_rect(element)
    if rect is None:
        return False
    return (
        container.x - margin <= rect.cx <= container.right + margin
        and container.y - margin <= rect.cy <= container.bottom + margin
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


def mouse_click_point(point: Optional[tuple[float, float]]) -> bool:
    if point is None:
        return False
    mouse_click_xy(point[0], point[1])
    return True


def press(element) -> None:
    err = AX.AXUIElementPerformAction(element, AX.kAXPressAction)
    # Some Futu controls return an AX timeout error even though the click succeeds.
    if err not in (0, -25205):
        rect = ax_rect(element)
        if rect is None:
            raise RuntimeError(f"Cannot press/click element without position/size: {ax_text(element) or '<empty>'}")
        mouse_click_xy(rect.cx, rect.cy)


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
    rect = ax_rect(field)
    if rect is None:
        raise RuntimeError(f"Cannot focus text field without position/size: {ax_text(field) or '<empty>'}")
    mouse_click_xy(rect.cx, rect.cy)
    time.sleep(FOCUS_SETTLE)
    set_clipboard(text)
    keypress(KEY_A, cmd_flag())
    keypress(KEY_DELETE)
    keypress(KEY_V, cmd_flag())
    time.sleep(FOCUS_SETTLE)


def button_text_is(element, label: str) -> bool:
    if ax_get(element, AX.kAXRoleAttribute) != AX.kAXButtonRole:
        return False
    return label in ax_text(element)


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
