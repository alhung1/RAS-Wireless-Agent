"""Centralized low-level UI input primitives.

Every mouse click, keystroke, and text entry goes through this module.
Functions accept explicit parameters -- no module-level mutable state.

Product-agnostic: these are generic Win32/pyautogui wrappers.
"""
from __future__ import annotations

import ctypes
import os
import time
from typing import Optional

import cv2
import numpy as np
import pyautogui

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.screen_utils import (
    capture_window,
    get_window_rect,
    save_screenshot,
)

logger = get_logger("ui.input_helpers")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

user32 = ctypes.windll.user32

UI_SETTLE_MS = 150


# ---------------------------------------------------------------------------
# Emergency stop
# ---------------------------------------------------------------------------

class EmergencyStopError(Exception):
    """Raised when the operator creates the stop file to abort the run."""


def check_stop(stop_file: str = os.path.join("artifacts", "STOP")) -> None:
    """Raise EmergencyStopError if the stop-file exists."""
    if os.path.isfile(stop_file):
        raise EmergencyStopError(f"Emergency stop: {stop_file!r} exists")


# ---------------------------------------------------------------------------
# IME
# ---------------------------------------------------------------------------

_EN_US_LAYOUT = 0x04090409


def force_english_ime() -> None:
    """Activate English (US) keyboard layout to prevent CJK input issues."""
    try:
        user32.ActivateKeyboardLayout(_EN_US_LAYOUT, 0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Bounds checking
# ---------------------------------------------------------------------------

def bounds_ok(hwnd: int, ax: int, ay: int) -> bool:
    """Return True if absolute (ax, ay) is within the window rect."""
    rect = get_window_rect(hwnd)
    return (rect[0] <= ax <= rect[2]) and (rect[1] <= ay <= rect[3])


# ---------------------------------------------------------------------------
# Dry-run annotation
# ---------------------------------------------------------------------------

def annotate_target(
    img: np.ndarray,
    px: int,
    py: int,
    label: str,
    color: tuple[int, int, int] = (0, 0, 255),
) -> None:
    """Draw a crosshair + label on *img* at (px, py) for dry-run mode."""
    size = 12
    cv2.line(img, (px - size, py), (px + size, py), color, 2)
    cv2.line(img, (px, py - size), (px, py + size), color, 2)
    cv2.putText(img, label, (px + size + 4, py - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Click
# ---------------------------------------------------------------------------

def safe_click(
    hwnd: int | None,
    px: int,
    py: int,
    *,
    label: str = "",
    dry_run: bool = False,
    dry_run_img: np.ndarray | None = None,
    stop_file: str = "",
    ensure_fg_fn=None,
) -> bool:
    """Click at window-relative (px, py) with bounds guard.

    Returns True if the click was performed (or simulated in dry-run).
    *ensure_fg_fn* is called before clicking to bring the window to front.
    """
    if stop_file:
        check_stop(stop_file)
    if hwnd is None:
        logger.error("safe_click called with hwnd=None, skipping")
        return False

    rect = get_window_rect(hwnd)
    ax = rect[0] + px
    ay = rect[1] + py

    if dry_run:
        tag = label or f"({px},{py})"
        logger.info("[DRY-RUN] WOULD click %s at abs(%d,%d)", tag, ax, ay,
                    extra={"action": "dry_run_click", "step": tag})
        if dry_run_img is not None:
            annotate_target(dry_run_img, px, py, tag)
        return True

    if not bounds_ok(hwnd, ax, ay):
        logger.error("Click at abs(%d,%d) is OUTSIDE window rect %s — rejected",
                     ax, ay, rect,
                     extra={"action": "bounds_reject", "step": label})
        return False

    if ensure_fg_fn:
        ensure_fg_fn(hwnd)
    time.sleep(0.1)
    pyautogui.click(ax, ay)
    return True


def safe_double_click(
    hwnd: int | None,
    px: int,
    py: int,
    *,
    label: str = "",
    dry_run: bool = False,
    stop_file: str = "",
    ensure_fg_fn=None,
) -> bool:
    """Double-click at window-relative (px, py)."""
    if stop_file:
        check_stop(stop_file)
    if hwnd is None:
        return False
    rect = get_window_rect(hwnd)
    ax, ay = rect[0] + px, rect[1] + py
    if dry_run:
        logger.info("[DRY-RUN] WOULD doubleClick %s at abs(%d,%d)",
                    label, ax, ay,
                    extra={"action": "dry_run_dblclick", "step": label})
        return True
    if not bounds_ok(hwnd, ax, ay):
        return False
    if ensure_fg_fn:
        ensure_fg_fn(hwnd)
    time.sleep(0.1)
    pyautogui.doubleClick(ax, ay)
    return True


def safe_triple_click(
    hwnd: int | None,
    px: int,
    py: int,
    *,
    label: str = "",
    dry_run: bool = False,
    dry_run_img: np.ndarray | None = None,
    stop_file: str = "",
    ensure_fg_fn=None,
) -> None:
    """Triple-click at window-relative (px, py)."""
    if stop_file:
        check_stop(stop_file)
    if hwnd is None:
        return
    rect = get_window_rect(hwnd)
    ax, ay = rect[0] + px, rect[1] + py
    if dry_run:
        logger.info("[DRY-RUN] WOULD tripleClick at abs(%d,%d) (%s)",
                    ax, ay, label,
                    extra={"action": "dry_run_tripleclick", "step": label})
        if dry_run_img is not None:
            annotate_target(dry_run_img, px, py, f"3click:{label}")
        return
    if not bounds_ok(hwnd, ax, ay):
        logger.error("tripleClick at abs(%d,%d) OUTSIDE window — rejected",
                     ax, ay)
        return
    if ensure_fg_fn:
        ensure_fg_fn(hwnd)
    time.sleep(0.1)
    pyautogui.tripleClick(ax, ay)


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

def safe_press(
    key: str,
    *,
    label: str = "",
    dry_run: bool = False,
    stop_file: str = "",
) -> None:
    """Press a single key."""
    if stop_file:
        check_stop(stop_file)
    if dry_run:
        logger.info("[DRY-RUN] WOULD press key %r (%s)", key, label,
                    extra={"action": "dry_run_press", "step": label})
        return
    pyautogui.press(key)


def safe_type(
    text: str,
    *,
    interval: float = 0.05,
    label: str = "",
    dry_run: bool = False,
    stop_file: str = "",
) -> None:
    """Type text using pyautogui.typewrite.  Forces English IME first."""
    if stop_file:
        check_stop(stop_file)
    if dry_run:
        logger.info("[DRY-RUN] WOULD type %r (%s)", text, label,
                    extra={"action": "dry_run_type", "step": label})
        return
    force_english_ime()
    pyautogui.typewrite(str(text), interval=interval)


def safe_hotkey(
    *keys: str,
    label: str = "",
    dry_run: bool = False,
    stop_file: str = "",
) -> None:
    """Press a key combination (e.g. 'ctrl', 'a')."""
    if stop_file:
        check_stop(stop_file)
    if dry_run:
        logger.info("[DRY-RUN] WOULD hotkey %s (%s)", keys, label,
                    extra={"action": "dry_run_hotkey", "step": label})
        return
    pyautogui.hotkey(*keys)


# ---------------------------------------------------------------------------
# Field operations (compound actions)
# ---------------------------------------------------------------------------

def type_in_field(
    hwnd: int,
    px: int,
    py: int,
    text: str,
    *,
    dry_run: bool = False,
    ensure_fg_fn=None,
) -> None:
    """Triple-click a field to select all, then type new text."""
    safe_triple_click(hwnd, px, py, label="select_field",
                      dry_run=dry_run, ensure_fg_fn=ensure_fg_fn)
    time.sleep(0.3)
    safe_type(str(text), label="type_in_field", dry_run=dry_run)
    time.sleep(0.2)


def clear_and_type(
    hwnd: int,
    px: int,
    py: int,
    text: str,
    *,
    dry_run: bool = False,
    ensure_fg_fn=None,
) -> None:
    """Click field, End, Backspace x15 to clear, then type.

    More robust than triple-click for LabVIEW numeric fields.
    """
    safe_click(hwnd, px, py, label="clear_and_type_click",
               dry_run=dry_run, ensure_fg_fn=ensure_fg_fn)
    time.sleep(0.2)
    safe_press("end", label="clear_field_end", dry_run=dry_run)
    time.sleep(0.1)
    for _ in range(15):
        safe_press("backspace", label="clear_field_bs", dry_run=dry_run)
        if not dry_run:
            time.sleep(0.03)
    time.sleep(0.1)
    safe_type(str(text), label="clear_and_type_text", dry_run=dry_run)
    time.sleep(0.2)


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

def take_screenshot(
    hwnd: int,
    artifacts_dir: str,
    name: str,
) -> str:
    """Capture a window screenshot, save it, return the file path.

    Falls back to pyautogui full-screen capture if Win32 capture fails.
    """
    abs_dir = os.path.abspath(artifacts_dir)
    os.makedirs(abs_dir, exist_ok=True)
    try:
        img = capture_window(hwnd)
        return save_screenshot(img, abs_dir, name)
    except Exception as e:
        logger.warning("capture_window failed (%s), using pyautogui fallback", e)
    try:
        pil_img = pyautogui.screenshot()
        arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        path = os.path.join(abs_dir, name)
        cv2.imwrite(path, arr)
        return path
    except Exception as e2:
        logger.warning("pyautogui screenshot fallback also failed: %s", e2)
        return ""


# ---------------------------------------------------------------------------
# Short UI settle delay
# ---------------------------------------------------------------------------

def settle(ms: int = UI_SETTLE_MS) -> None:
    """Brief pause to let the UI render after an action.

    Only for UI settling -- NOT for waiting on async operations.
    """
    time.sleep(ms / 1000.0)
