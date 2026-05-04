"""Lazy PyObjC runtime loading and permission checks."""

from __future__ import annotations

from typing import Any

_loaded_ax = None
_loaded_quartz = None
_cmd_flag = 0


def load_pyobjc() -> None:
    """Load PyObjC modules once and cache the command-key flag."""
    global _loaded_ax, _loaded_quartz, _cmd_flag
    if _loaded_ax is not None and _loaded_quartz is not None:
        return

    try:
        import ApplicationServices as loaded_ax
        import Quartz as loaded_quartz
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise SystemExit(
            "Missing PyObjC modules. Install with: python3 -m pip install pyobjc"
        ) from exc

    _loaded_ax = loaded_ax
    _loaded_quartz = loaded_quartz
    _cmd_flag = loaded_quartz.kCGEventFlagMaskCommand


def cmd_flag() -> int:
    load_pyobjc()
    return _cmd_flag


class _RuntimeProxy:
    def __init__(self, name: str) -> None:
        self.name = name

    def _target(self) -> Any:
        load_pyobjc()
        return _loaded_ax if self.name == "AX" else _loaded_quartz

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._target(), attr)


AX = _RuntimeProxy("AX")
Quartz = _RuntimeProxy("Quartz")


def check_accessibility_permission() -> None:
    load_pyobjc()
    opts = {AX.kAXTrustedCheckOptionPrompt: True}
    if not AX.AXIsProcessTrustedWithOptions(opts):
        raise SystemExit(
            "Accessibility permission is required. Open System Settings -> "
            "Privacy & Security -> Accessibility, allow your Terminal/Python app, "
            "then run this command again."
        )
