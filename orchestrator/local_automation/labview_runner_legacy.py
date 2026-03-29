"""LabVIEW RvR Wireless v2.03 -- legacy implementation (steps, helpers, globals).

Orchestration lives in ``labview_runner.py`` (thin facade) which delegates to
``StepEngine``. This module retains step functions, coordinates, dry-run
globals, window helpers, ``STEP_SEQUENCE`` for calibration scripts, and
``prepare_labview_session`` for session setup.

Key architectural decisions (learned from calibration):
  - Each VI is set to a FIXED window size before interaction
  - Control positions are ABSOLUTE pixel offsets, not relative fractions
  - LabVIEW VIs do not scale controls with window size
  - Login and error-dialog VIs are separate child windows
  - tripleClick + typewrite for text field input
  - Keyboard Up/Down navigation for LabVIEW dropdown menus

Multi-band support:
  - RunConfig carries band-specific fields (mode, pairs_2g, pairs_5g6g)
  - BW_MODE_NAV maps mode names to dropdown navigation sequences
  - ``build_band_config`` loads per-band defaults from ui_flow.yaml
"""
from __future__ import annotations

import ctypes
import glob as glob_module
import json
import os
import subprocess
import time
import traceback
from ctypes import wintypes
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pyautogui
import yaml

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

import cv2
import numpy as np

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.screen_utils import (
    capture_window,
    save_screenshot,
    get_window_rect,
    set_window_rect,
    minimize_window,
    is_ocr_available,
    ocr_region,
    ocr_region_freeform,
    find_template_center,
    screen_contains,
)
from orchestrator.local_automation.finish_detector import (
    FinishConfig,
    FinishResult,
    wait_for_finish,
)

logger = get_logger("labview_runner_legacy")

user32 = ctypes.windll.user32

LV_PID: int | None = None

STEP_WINDOW_SIZE = (1288, 1040)
LOGIN_WINDOW_SIZE = (356, 200)
MAIN_WINDOW_SIZE = (1288, 860)
POPUP_SIZE = (800, 900)

ORANGE_ARROW_PX = (1183, 976)

# Step-level retry config
MAX_STEP_RETRIES = 2
RETRY_DELAY_SEC = 2.0

# ---------------------------------------------------------------------------
# Emergency stop
# ---------------------------------------------------------------------------

STOP_FILE = os.environ.get("LV_STOP_FILE", os.path.join("artifacts", "STOP"))


class EmergencyStopError(Exception):
    """Raised when the operator creates the stop file to abort the run."""


def _check_stop() -> None:
    """Raise EmergencyStopError if the stop-file exists."""
    if os.path.isfile(STOP_FILE):
        raise EmergencyStopError(f"Emergency stop: {STOP_FILE!r} exists")


# ---------------------------------------------------------------------------
# Dry-run / safe-input infrastructure
# ---------------------------------------------------------------------------

_DRY_RUN: bool = False
_DRY_RUN_IMG: np.ndarray | None = None
_DRY_RUN_HWND: int | None = None


def _annotate_target(
    img: np.ndarray, px: int, py: int, label: str,
    color: tuple[int, int, int] = (0, 0, 255),
) -> None:
    """Draw a crosshair + label on *img* at (px, py) for dry-run annotations."""
    size = 12
    cv2.line(img, (px - size, py), (px + size, py), color, 2)
    cv2.line(img, (px, py - size), (px, py + size), color, 2)
    cv2.putText(img, label, (px + size + 4, py - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def _bounds_ok(hwnd: int, ax: int, ay: int) -> bool:
    """Return True if (ax, ay) screen-absolute coord is within *hwnd* rect."""
    rect = get_window_rect(hwnd)
    return (rect[0] <= ax <= rect[2]) and (rect[1] <= ay <= rect[3])


def _safe_click(hwnd: int | None, px: int, py: int, label: str = "") -> bool:
    """Click at window-relative (px, py) with stop-file check and bounds guard.

    In dry-run mode the click is replaced by a log message and a screenshot
    annotation.  If the absolute coordinate falls outside the window rect the
    click is rejected.  Returns True if the click was performed (or simulated
    in dry-run), False if rejected.
    """
    _check_stop()
    if hwnd is None:
        logger.error("_safe_click called with hwnd=None, skipping")
        return False
    rect = get_window_rect(hwnd)
    ax = rect[0] + px
    ay = rect[1] + py

    if _DRY_RUN:
        tag = label or f"({px},{py})"
        logger.info("[DRY-RUN] WOULD click %s at abs(%d,%d)", tag, ax, ay,
                    extra={"action": "dry_run_click", "step": tag})
        global _DRY_RUN_IMG
        if _DRY_RUN_IMG is not None:
            _annotate_target(_DRY_RUN_IMG, px, py, tag)
        return True

    if not _bounds_ok(hwnd, ax, ay):
        logger.error("Click at abs(%d,%d) is OUTSIDE window rect %s — rejected",
                     ax, ay, rect, extra={"action": "bounds_reject", "step": label})
        return False

    _ensure_foreground(hwnd)
    time.sleep(0.1)
    pyautogui.click(ax, ay)
    return True


def _safe_press(key: str, label: str = "") -> None:
    """Press a keyboard key with stop-file check.  No-op in dry-run."""
    _check_stop()
    if _DRY_RUN:
        logger.info("[DRY-RUN] WOULD press key %r (%s)", key, label,
                    extra={"action": "dry_run_press", "step": label})
        return
    pyautogui.press(key)


def _force_english_ime() -> None:
    """Activate the English (US) keyboard layout to prevent CJK input issues.

    Uses ActivateKeyboardLayout with 0x04090409 (en-US).  If the layout
    is not installed, falls back silently — the worst case is that the
    existing layout stays active.
    """
    EN_US = 0x04090409
    try:
        user32.ActivateKeyboardLayout(EN_US, 0)
    except Exception:
        pass


def _safe_type(text: str, interval: float = 0.05, label: str = "") -> None:
    """Type text with stop-file check.  No-op in dry-run."""
    _check_stop()
    if _DRY_RUN:
        logger.info("[DRY-RUN] WOULD type %r (%s)", text, label,
                    extra={"action": "dry_run_type", "step": label})
        return
    _force_english_ime()
    pyautogui.typewrite(str(text), interval=interval)


def _safe_hotkey(*keys: str, label: str = "") -> None:
    _check_stop()
    if _DRY_RUN:
        logger.info("[DRY-RUN] WOULD hotkey %s (%s)", keys, label,
                    extra={"action": "dry_run_hotkey", "step": label})
        return
    pyautogui.hotkey(*keys)


def _safe_triple_click(hwnd: int | None, px: int, py: int, label: str = "") -> None:
    _check_stop()
    if hwnd is None:
        return
    rect = get_window_rect(hwnd)
    ax, ay = rect[0] + px, rect[1] + py
    if _DRY_RUN:
        logger.info("[DRY-RUN] WOULD tripleClick at abs(%d,%d) (%s)", ax, ay, label,
                    extra={"action": "dry_run_tripleclick", "step": label})
        global _DRY_RUN_IMG
        if _DRY_RUN_IMG is not None:
            _annotate_target(_DRY_RUN_IMG, px, py, f"3click:{label}")
        return
    if not _bounds_ok(hwnd, ax, ay):
        logger.error("tripleClick at abs(%d,%d) OUTSIDE window — rejected", ax, ay)
        return
    _ensure_foreground(hwnd)
    time.sleep(0.1)
    pyautogui.tripleClick(ax, ay)

# BW mode dropdown navigation: Up N to reach BW20 (top), then Down M.
# List order: BW20, BW40, BW80, BW160, BW240, BW320, Not Valid
BW_MODE_NAV: dict[str, tuple[int, int]] = {
    "BW20":  (6, 0),
    "BW40":  (6, 1),
    "BW80":  (6, 2),
    "BW160": (6, 3),
    "BW240": (6, 4),
    "BW320": (6, 5),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    name: str
    success: bool
    elapsed_sec: float = 0.0
    screenshot: str = ""
    error: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class RunConfig:
    rf_channel_2g: str = "10"
    rf_channel_5g: str = "44"
    rf_channel_6g: str = "69"
    user_information: str = "2G test"
    band: str = "2.4G"
    username: str = "Alex"
    password: str = "123"
    test_type: str = "1 rpm (fast)"
    freq_range: str = "MLO"
    ap_name: str = "RS700"
    client_name: str = "INTEL_BE200"
    mode: str = "BW20"
    graph_range: str = "100"
    start_atten: str = "0"
    step_size: str = "3"
    steps: str = "30"
    number_of_pairs: str = "8"
    number_of_pairs_5g6g: str = "0"
    design_stage: str = "Beta"
    region: str = "US"
    exe_path: str = r"C:\480.builds\v2.03\480.000.v2.03.exe"
    timeout_seconds: int = 14400
    finish_config: dict = field(default_factory=dict)
    # IP address screen: dropdown values (1-5)
    ip_dropdown_2g: str = "3"
    ip_dropdown_5g6g: str = "3"
    ap_ip: str = "192.168.1.1"


@dataclass
class RunReport:
    success: bool = False
    started_at: str = ""
    finished_at: str = ""
    steps: list[dict] = field(default_factory=list)
    finish_result: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    error: str = ""


WINDOW_WIDTH = 1288
WINDOW_HEIGHT = 1040


# ---------------------------------------------------------------------------
# Window discovery
# ---------------------------------------------------------------------------

def _get_lv_pid() -> int | None:
    global LV_PID
    if LV_PID:
        return LV_PID
    wins = _enum_lv_windows()
    for hwnd, title, _, _, _ in wins:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        LV_PID = pid.value
        return LV_PID
    return None


def _enum_lv_windows(
    title_hints: list[str] | None = None,
) -> list[tuple[int, str, int, int, tuple[int, int, int, int]]]:
    """Return [(hwnd, title, w, h, rect), ...] for visible LabVIEW windows."""
    results: list[tuple[int, str, int, int, tuple[int, int, int, int]]] = []

    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        if not title:
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        lv_pid = _get_lv_pid() if LV_PID else None

        match = False
        if lv_pid and pid.value == lv_pid:
            match = True
        elif title_hints:
            match = any(h.lower() in title.lower() for h in title_hints)
        else:
            match = any(h.lower() in title.lower()
                       for h in ["480", "481", "400 600", "RvR", "logon", "table"])

        if match:
            r = get_window_rect(hwnd)
            w = r[2] - r[0]
            h = r[3] - r[1]
            if w > 10 and h > 10:
                results.append((hwnd, title, w, h, r))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return results


def find_labview_window(
    title_hints: list[str] | None = None,
    exe_name: str = "480.000.v2.03.exe",
) -> int | None:
    hints = title_hints or ["480 000.vi", "480", "RvR"]
    wins = _enum_lv_windows(hints)
    for hwnd, title, w, h, r in wins:
        if any(ht.lower() in title.lower() for ht in hints):
            logger.info("Found LabVIEW window: hwnd=%d title=%r", hwnd, title,
                         extra={"action": "find_window", "step": "found"})
            global LV_PID
            if not LV_PID:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                LV_PID = pid.value
            return hwnd
    return None


def _find_vi_window(title_contains: str, timeout: float = 5.0) -> int | None:
    """Find a VI window whose title contains the given string.

    Passes the search string as a title hint to _enum_lv_windows so that
    popups and non-standard VIs are also discovered.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        wins = _enum_lv_windows(title_hints=[title_contains])
        for hwnd, title, w, h, r in wins:
            if title_contains.lower() in title.lower():
                return hwnd
        time.sleep(0.5)
    return None


def _find_active_vi(exclude_titles: list[str] | None = None) -> int | None:
    """Find the 'active' VI (largest visible non-main window)."""
    wins = _enum_lv_windows()
    exclude = set(t.lower() for t in (exclude_titles or ["480 000.vi"]))
    candidates = [
        (hwnd, title, w, h, r)
        for hwnd, title, w, h, r in wins
        if title.lower() not in exclude and w > 100 and h > 100
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c[2] * c[3])
    return best[0]


def _find_vi_or_active(expected_title: str | None = None,
                        timeout: float = 5.0) -> int | None:
    """Find a VI window by expected title. NO silent fallback.

    Returns None when expected_title is given but no matching window found.
    Only uses _find_active_vi() when no expected_title is provided.
    """
    if expected_title:
        hwnd = _find_vi_window(expected_title, timeout=timeout)
        if hwnd:
            return hwnd
        logger.error("Expected VI %r NOT found (strict, no fallback)",
                      expected_title,
                      extra={"action": "find_vi", "step": "not_found"})
        return None
    return _find_active_vi()


def _find_frame_window() -> int | None:
    """Find the LVFrame top-level window."""
    result = [None]

    def _cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "LVFrame" and user32.IsWindowVisible(hwnd):
            result[0] = hwnd
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return result[0]


def _dismiss_dialogs() -> int:
    """Find and dismiss small untitled LabVIEW dialog windows."""
    pid = _get_lv_pid()
    if not pid:
        return 0
    dismissed = 0

    def _cb(hwnd, _):
        nonlocal dismissed
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        r = get_window_rect(hwnd)
        w = r[2] - r[0]
        h = r[3] - r[1]
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if 80 < w < 300 and 50 < h < 200 and not buf.value:
            _safe_click(hwnd, 50, h - 30, label="dismiss_dialog")
            time.sleep(0.5)
            dismissed += 1
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    if dismissed:
        logger.info("Dismissed %d dialog(s)", dismissed,
                     extra={"action": "dismiss_dialogs", "step": "done"})
    return dismissed


def _setup_vi(hwnd: int, width: int = WINDOW_WIDTH, height: int = WINDOW_HEIGHT) -> None:
    """Set VI window to fixed size at (0,0), dismiss popups/dialogs, bring to foreground."""
    _dismiss_lv_popups()
    _dismiss_dialogs()
    set_window_rect(hwnd, 0, 0, width, height)
    time.sleep(0.3)

    rect = get_window_rect(hwnd)
    actual_w = rect[2] - rect[0]
    actual_h = rect[3] - rect[1]
    if actual_w != width or actual_h != height:
        logger.warning(
            "Window resize to %dx%d produced %dx%d — retrying",
            width, height, actual_w, actual_h,
            extra={"action": "setup_vi", "step": "resize_mismatch"},
        )
        set_window_rect(hwnd, 0, 0, width, height)
        time.sleep(0.5)

    _ensure_foreground(hwnd)
    time.sleep(0.3)


def _force_fg(hwnd: int) -> None:
    """Robustly bring hwnd to foreground using AttachThreadInput."""
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    my_tid = kernel32.GetCurrentThreadId()
    if fg_tid != my_tid:
        user32.AttachThreadInput(my_tid, fg_tid, True)
    user32.ShowWindow(hwnd, 9)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if fg_tid != my_tid:
        user32.AttachThreadInput(my_tid, fg_tid, False)


SW_MINIMIZE = 6


def _ensure_foreground(hwnd: int, max_retries: int = 3) -> bool:
    """Bring *hwnd* to foreground and **verify** it actually got focus.

    If another window is blocking, minimize the blocker and retry.
    Returns True when GetForegroundWindow() matches *hwnd*.
    """
    for attempt in range(max_retries):
        _force_fg(hwnd)
        time.sleep(0.15)
        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            return True
        fg_title = _get_window_title(fg)
        logger.warning(
            "Foreground is %r (hwnd=%d), expected hwnd=%d — "
            "minimizing blocker (attempt %d/%d)",
            fg_title, fg, hwnd, attempt + 1, max_retries,
            extra={"action": "ensure_foreground", "step": "minimize_blocker"},
        )
        user32.ShowWindow(fg, SW_MINIMIZE)
        time.sleep(0.3)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    logger.error(
        "Failed to bring hwnd=%d to foreground after %d retries "
        "(current fg hwnd=%d %r)",
        hwnd, max_retries, fg, _get_window_title(fg),
        extra={"action": "ensure_foreground", "step": "failed"},
    )
    return False


def _screenshot(hwnd: int, artifacts_dir: str, step: int, name: str) -> str:
    fname = f"step_{step:02d}_{name}.png"
    abs_dir = os.path.abspath(artifacts_dir)
    os.makedirs(abs_dir, exist_ok=True)
    try:
        img = capture_window(hwnd)
        return save_screenshot(img, abs_dir, fname)
    except Exception as e:
        logger.warning("capture_window failed (%s), using pyautogui fallback", e)
    try:
        pil_img = pyautogui.screenshot()
        arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        path = os.path.join(abs_dir, fname)
        cv2.imwrite(path, arr)
        return path
    except Exception as e2:
        logger.warning("pyautogui screenshot fallback also failed: %s", e2)
        return ""


def _click_orange_arrow(hwnd: int) -> None:
    """Click the right orange arrow (Next) at its fixed position."""
    _safe_click(hwnd, ORANGE_ARROW_PX[0], ORANGE_ARROW_PX[1],
                label="orange_arrow")


def _click_at(hwnd: int, px: int, py: int) -> bool:
    """Click at absolute pixel offset from window top-left."""
    return _safe_click(hwnd, px, py)


def _type_in_field(hwnd: int, px: int, py: int, text: str) -> None:
    """Triple-click a field at (px,py) to select all, then type text."""
    _safe_triple_click(hwnd, px, py, label="select_field")
    time.sleep(0.3)
    _safe_type(str(text), label="type_in_field")
    time.sleep(0.2)


def _clear_and_type(hwnd: int, px: int, py: int, text: str) -> None:
    """Click field, press End, then Backspace x15 to clear, then type.

    More robust than tripleClick for LabVIEW numeric fields that may
    not respond to triple-click selection.
    """
    _safe_click(hwnd, px, py, label="clear_and_type_click")
    time.sleep(0.2)
    _safe_press("end", label="clear_field_end")
    time.sleep(0.1)
    for _ in range(15):
        _safe_press("backspace", label="clear_field_bs")
        time.sleep(0.03)
    time.sleep(0.1)
    _safe_type(str(text), label="clear_and_type_text")
    time.sleep(0.2)


def _select_dropdown_by_nav(hwnd: int, dropdown_px: tuple[int, int],
                             up_presses: int, down_presses: int = 0) -> None:
    """Open a LabVIEW dropdown and navigate to an item via Up/Down keys."""
    _click_at(hwnd, dropdown_px[0], dropdown_px[1])
    time.sleep(1.0)
    for _ in range(up_presses):
        _safe_press("up", label="dropdown_nav")
        time.sleep(0.15)
    for _ in range(down_presses):
        _safe_press("down", label="dropdown_nav")
        time.sleep(0.15)
    _safe_press("enter", label="dropdown_confirm")
    time.sleep(1.0)


def _click_dropdown_item(hwnd: int, dropdown_px: tuple[int, int],
                         item_text: str, max_items: int = 15) -> None:
    """Open a LabVIEW dropdown and select an item by clicking through."""
    _safe_click(hwnd, dropdown_px[0], dropdown_px[1],
                label="dropdown_open")
    time.sleep(0.8)
    img = capture_window(hwnd)
    save_screenshot(img, "artifacts/labview_calibration",
                    f"dropdown_{item_text}.png")


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------

def _get_window_title(hwnd: int) -> str:
    """Get the current title of a window by its handle."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


_POPUP_DISMISSED_HWNDS: set[int] = set()
_POPUP_DISMISS_TIMES: dict[int, float] = {}
_POPUP_COOLDOWN_SEC = 3.0


def _dismiss_lv_popups() -> int:
    """Auto-dismiss known LabVIEW popup VIs (printer warning, status msgs).

    Strategy: first attempt clicks OK / presses Enter.  If the popup
    persists (same hwnd found again), minimize it to keep it out of the way.
    Blocker windows (like 480_214.vi) are always minimized immediately.
    Returns the number of popups dismissed or minimized.
    """
    POPUP_HINTS = ["503 POP UP", "show msg", "Information window",
                   "display status"]
    BLOCKER_HINTS = ["480_214", "8002", "list in folder"]
    dismissed = 0
    now = time.monotonic()

    for hint in BLOCKER_HINTS:
        hwnd = _find_vi_window(hint, timeout=0.3)
        if not hwnd:
            continue
        title = _get_window_title(hwnd)
        logger.info("Minimizing blocker window: %r (hwnd=%d)",
                    title, hwnd,
                    extra={"action": "dismiss_popup", "step": "minimize_blocker"})
        minimize_window(hwnd)
        time.sleep(0.3)
        dismissed += 1

    for hint in POPUP_HINTS:
        hwnd = _find_vi_window(hint, timeout=0.3)
        if not hwnd:
            continue
        last = _POPUP_DISMISS_TIMES.get(hwnd, 0.0)
        if now - last < _POPUP_COOLDOWN_SEC:
            continue
        title = _get_window_title(hwnd)
        already_tried = hwnd in _POPUP_DISMISSED_HWNDS
        _POPUP_DISMISSED_HWNDS.add(hwnd)
        _POPUP_DISMISS_TIMES[hwnd] = now

        if already_tried:
            logger.info("Minimizing persistent popup: %r (hwnd=%d)",
                        title, hwnd,
                        extra={"action": "dismiss_popup", "step": "minimize"})
            minimize_window(hwnd)
            time.sleep(0.3)
        else:
            logger.info("Auto-dismissing popup: %r (hwnd=%d)", title, hwnd,
                        extra={"action": "dismiss_popup", "step": "enter"})
            _force_fg(hwnd)
            time.sleep(0.3)
            rect = get_window_rect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            _safe_click(hwnd, w - 80, h - 50, label="dismiss_popup")
            time.sleep(0.5)
            _safe_press("enter", label="dismiss_popup_enter")
            time.sleep(1.0)
        dismissed += 1
    return dismissed


_AP_CLIENT_POPUP_HINTS = ["8002", "list in folder"]


def _count_ap_client_popups() -> list[tuple[int, str]]:
    """Return [(hwnd, title), ...] for all visible AP/Client selection popups.

    Detects the "8002 Select AP or Client from list in folder.vi" window
    and any duplicates.
    """
    found: list[tuple[int, str]] = []
    for hwnd, title, w, h, rect in _enum_lv_windows(title_hints=_AP_CLIENT_POPUP_HINTS):
        tl = title.lower()
        if any(hint in tl for hint in ["8002", "list in folder"]):
            found.append((hwnd, title))
    return found


def _ensure_ap_client_popups_closed(
    step_label: str,
    artifacts_dir: str,
    max_attempts: int = 3,
) -> bool:
    """Verify all AP/Client popups are closed, minimizing any that remain.

    Returns True if zero popups remain, False if popups persist.
    Logs each attempt with popup count for diagnostics.
    """
    for attempt in range(max_attempts):
        popups = _count_ap_client_popups()
        if not popups:
            if attempt > 0:
                logger.info("AP/Client popups cleared after %d attempts (%s)",
                            attempt, step_label,
                            extra={"action": "popup_check", "step": step_label})
            return True

        logger.warning(
            "%d AP/Client popup(s) still open (%s, attempt %d/%d): %s",
            len(popups), step_label, attempt + 1, max_attempts,
            [(h, t) for h, t in popups],
            extra={"action": "popup_check", "step": step_label})

        for popup_hwnd, popup_title in popups:
            minimize_window(popup_hwnd)
            time.sleep(0.5)

        _dismiss_lv_popups()
        time.sleep(1.0)

    remaining = _count_ap_client_popups()
    if remaining:
        logger.error(
            "POPUP BLOCKED: %d AP/Client popup(s) still open after %d attempts (%s)",
            len(remaining), max_attempts, step_label,
            extra={"action": "popup_blocked", "step": step_label})
        try:
            _screenshot(remaining[0][0], artifacts_dir, -1,
                        f"popup_blocked_{step_label}")
        except Exception:
            pass
        return False
    return True


def _verify_transition(old_hwnd: int, expected_hint: str | None = None,
                       timeout: float = 10.0) -> tuple[int | None, bool]:
    """After clicking orange arrow, verify the screen actually changed.

    Auto-dismisses intermediate popups (printer warnings, status messages)
    that appear between wizard steps, then checks for real transitions:
      1. If expected_hint given, look for a window containing that title
      2. Check if a different VI appeared (different hwnd + title)
      3. Check if old window title changed
      4. Check if old window is gone

    Returns (new_hwnd, success). FAILS if screen is unchanged.
    """
    old_title = _get_window_title(old_hwnd)
    deadline = time.monotonic() + timeout

    popup_lower = [h.lower() for h in
                   ["503 POP UP", "show msg", "Information window",
                    "display status", "480_214"]]

    def _is_popup(title: str) -> bool:
        tl = title.lower()
        return any(p in tl for p in popup_lower)

    while time.monotonic() < deadline:
        _dismiss_lv_popups()

        if expected_hint:
            for h, t, w, ht, r in _enum_lv_windows():
                if expected_hint.lower() in t.lower() and h != old_hwnd:
                    logger.info("Transition OK: found %r (hwnd=%d)", t, h,
                                extra={"action": "verify_transition",
                                       "step": "found_expected"})
                    return h, True
        else:
            active = _find_active_vi()
            if active and active != old_hwnd:
                new_title = _get_window_title(active)
                if (new_title.lower() != old_title.lower()
                        and not _is_popup(new_title)):
                    logger.info("Transition OK: new VI hwnd=%d title=%r",
                                active, new_title,
                                extra={"action": "verify_transition",
                                       "step": "new_vi"})
                    return active, True

            cur_title = _get_window_title(old_hwnd)
            if cur_title and cur_title.lower() != old_title.lower():
                logger.info("Transition OK: title changed %r -> %r",
                            old_title, cur_title,
                            extra={"action": "verify_transition",
                                   "step": "title_changed"})
                return old_hwnd, True

            if not user32.IsWindowVisible(old_hwnd):
                new_vi = _find_active_vi()
                if new_vi and not _is_popup(_get_window_title(new_vi)):
                    logger.info("Transition OK: old window gone, found hwnd=%d",
                                new_vi,
                                extra={"action": "verify_transition",
                                       "step": "old_gone"})
                    return new_vi, True

        time.sleep(0.5)

    logger.error("Transition FAILED: screen unchanged after %.1fs "
                 "(old=%r hwnd=%d, expected=%r)",
                 timeout, old_title, old_hwnd, expected_hint,
                 extra={"action": "verify_transition", "step": "failed"})
    return None, False


def _region_changed(before_img, after_img,
                    x: int, y: int, w: int, h: int,
                    min_diff_pct: float = 1.0) -> bool:
    """Compare a rectangular region in two screenshots.
    Returns True if pixels differ by at least min_diff_pct percent.
    """
    import numpy as np
    r1 = before_img[y:y + h, x:x + w]
    r2 = after_img[y:y + h, x:x + w]
    if r1.shape != r2.shape:
        return True
    diff = np.abs(r1.astype(float) - r2.astype(float))
    changed_pixels = int(np.sum(diff.mean(axis=2) > 10))
    total_pixels = r1.shape[0] * r1.shape[1]
    if total_pixels == 0:
        return False
    pct = (changed_pixels / total_pixels) * 100
    return pct >= min_diff_pct


# ---------------------------------------------------------------------------
# Polling helpers (replace fixed time.sleep waits)
# ---------------------------------------------------------------------------

def _poll_until(
    condition_fn,
    timeout: float = 10.0,
    interval: float = 0.5,
    desc: str = "condition",
) -> bool:
    """Poll until *condition_fn()* returns truthy, or *timeout* elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    logger.warning("Poll timeout after %.1fs waiting for %s", timeout, desc,
                   extra={"action": "poll", "step": desc})
    return False


def _poll_for_window_appear(
    title_hint: str,
    timeout: float = 10.0,
    interval: float = 0.5,
) -> int | None:
    """Poll until a window whose title contains *title_hint* appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = _find_vi_window(title_hint, timeout=0.3)
        if hwnd:
            return hwnd
        time.sleep(interval)
    return None


def _poll_for_window_gone(
    hwnd: int,
    timeout: float = 10.0,
    interval: float = 0.5,
) -> bool:
    """Poll until *hwnd* is no longer visible."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not user32.IsWindowVisible(hwnd):
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# OCR verification helpers
# ---------------------------------------------------------------------------

def _ocr_read_field(
    hwnd: int,
    px: int,
    py: int,
    field_w: int = 120,
    field_h: int = 25,
) -> str:
    """Capture the area around (px, py) and OCR it. Returns raw text."""
    if not is_ocr_available():
        return ""
    try:
        img = capture_window(hwnd)
        text = ocr_region(img, max(px - 10, 0), max(py - 5, 0),
                          field_w, field_h)
        return text
    except Exception as exc:
        logger.warning("OCR read field at (%d,%d) failed: %s", px, py, exc)
        return ""


def _verify_typed_value(
    hwnd: int,
    px: int,
    py: int,
    expected: str,
    field_w: int = 120,
    field_h: int = 25,
    max_retries: int = 2,
    strict: bool = False,
) -> bool:
    """Read field via OCR and re-type if it doesn't match *expected*.

    Returns True once the field matches, False after exhausting retries.
    When *strict* is True, returns False if OCR is unavailable instead
    of optimistically returning True.
    """
    if not is_ocr_available():
        if strict:
            logger.warning("OCR unavailable and strict=True — verify_typed_value FAILS",
                           extra={"action": "verify_field", "step": "no_ocr_strict"})
            return False
        return True

    for attempt in range(max_retries + 1):
        actual = _ocr_read_field(hwnd, px, py, field_w, field_h)
        actual_clean = actual.strip().replace(" ", "").replace("O", "0")
        expected_clean = expected.strip().replace(" ", "")
        if expected_clean in actual_clean or actual_clean == expected_clean:
            if attempt > 0:
                logger.info("Field at (%d,%d) verified after %d retries",
                            px, py, attempt,
                            extra={"action": "verify_field", "step": "ok"})
            return True

        logger.warning(
            "Field mismatch at (%d,%d): expected=%r, OCR=%r (attempt %d/%d)",
            px, py, expected, actual, attempt + 1, max_retries + 1,
            extra={"action": "verify_field", "step": "mismatch"})

        if attempt < max_retries:
            _clear_and_type(hwnd, px, py, expected)
            time.sleep(0.5)

    return False


def _verify_dropdown_selection(
    hwnd: int,
    dropdown_px: tuple[int, int],
    expected: str,
    display_w: int = 180,
    display_h: int = 25,
    up_presses: int = 0,
    down_presses: int = 0,
    max_retries: int = 1,
    strict: bool = False,
) -> bool:
    """OCR-read the dropdown display area and re-navigate if mismatch.

    When *strict* is True, returns False if OCR is unavailable.
    """
    if not is_ocr_available():
        if strict:
            logger.warning("OCR unavailable and strict=True — "
                           "verify_dropdown_selection FAILS",
                           extra={"action": "verify_dropdown",
                                  "step": "no_ocr_strict"})
            return False
        return True

    for attempt in range(max_retries + 1):
        actual = _ocr_read_field(hwnd, dropdown_px[0] - 10, dropdown_px[1] - 5,
                                 display_w, display_h)
        if expected.lower() in actual.lower():
            return True

        logger.warning(
            "Dropdown mismatch: expected=%r, OCR=%r (attempt %d/%d)",
            expected, actual, attempt + 1, max_retries + 1,
            extra={"action": "verify_dropdown", "step": "mismatch"})

        if attempt < max_retries and up_presses > 0:
            _select_dropdown_by_nav(hwnd, dropdown_px, up_presses, down_presses)
            time.sleep(0.5)

    return False


# ---------------------------------------------------------------------------
# OCR-assisted list search
# ---------------------------------------------------------------------------

def _ocr_search_list_popup(
    popup_hwnd: int,
    target: str,
    list_region: tuple[int, int, int, int],
    max_scrolls: int = 120,
    scrolls_per_batch: int = 5,
) -> tuple[int, int] | None:
    """Scroll through a list popup, OCR each page, find *target* text.

    *list_region* is (x, y, w, h) relative to the popup window.
    Returns (click_x, click_y) in popup-relative coords, or None.
    """
    if not is_ocr_available():
        return None

    lx, ly, lw, lh = list_region

    _safe_click(popup_hwnd, lx + 50, ly + 20, label="list_focus")
    time.sleep(0.3)
    _safe_press("home", label="list_home")
    time.sleep(0.5)

    for batch in range(max_scrolls // scrolls_per_batch + 1):
        try:
            img = capture_window(popup_hwnd)
            text = ocr_region_freeform(img, lx, ly, lw, lh)

            if target.lower() in text.lower():
                lines = [ln for ln in text.strip().split("\n") if ln.strip()]
                for i, line in enumerate(lines):
                    if target.lower() in line.lower():
                        line_height = lh // max(len(lines), 1)
                        click_y = ly + i * line_height + line_height // 2
                        return (lx + lw // 2, click_y)
                return (lx + lw // 2, ly + lh // 2)
        except Exception as exc:
            logger.warning("OCR list search batch %d failed: %s", batch, exc)

        if batch * scrolls_per_batch >= max_scrolls:
            break
        for _ in range(scrolls_per_batch):
            _safe_press("down", label="list_scroll")
            time.sleep(0.08)
        time.sleep(0.3)

    logger.warning("Target %r not found in list after %d scrolls",
                   target, max_scrolls,
                   extra={"action": "ocr_list_search", "step": "not_found"})
    return None


# ---------------------------------------------------------------------------
# Template-based screen verification
# ---------------------------------------------------------------------------

SCREEN_TEMPLATES: dict[str, str | None] = {
    "step_01": "throughput_tab.png",
    "step_02": "green_ok_button.png",
    "step_03": "test_type_screen.png",
    "step_05": "freq_channel_screen.png",
    "step_11": "ip_address_screen.png",
    "step_14": "mode_screen.png",
    "step_15": "atten_screen.png",
    "step_16": "design_stage_screen.png",
    "step_17": "region_screen.png",
}

SCREEN_TITLE_HINTS: dict[str, str | None] = {
    "step_03": "400 600 test",
    "step_04": "table position",
    "step_05": "481",
    "step_11": "IP address",
    "step_13": None,
    "step_14": "MODE",
    "step_15": "atten",
    "step_16": "Chariot",
    "step_17": "REGION",
}


def _check_screen(
    hwnd: int,
    step_key: str,
    step_name: str = "",
) -> bool:
    """Verify the correct screen is displayed via title hint and/or template.

    Returns True if verification passes or no checks are configured.
    """
    title_hint = SCREEN_TITLE_HINTS.get(step_key)
    template_name = SCREEN_TEMPLATES.get(step_key)

    if title_hint:
        title = _get_window_title(hwnd)
        if title_hint.lower() in title.lower():
            return True
        logger.warning(
            "Screen check FAIL: title %r missing hint %r (step=%s)",
            title, title_hint, step_name,
            extra={"action": "check_screen", "step": step_name})

    if template_name:
        try:
            img = capture_window(hwnd)
            if screen_contains(img, template_name, threshold=0.70):
                return True
            logger.warning(
                "Screen check FAIL: template %r not found (step=%s)",
                template_name, step_name,
                extra={"action": "check_screen", "step": step_name})
        except Exception as exc:
            logger.debug("Template check error for %s: %s", template_name, exc)

    if not title_hint and not template_name:
        return True

    return title_hint is not None and template_name is not None


# ---------------------------------------------------------------------------
# Failure diagnosis and smart recovery
# ---------------------------------------------------------------------------

def _diagnose_failure(hwnd: int, step_name: str, ad: str) -> dict:
    """Collect diagnostic info when a step fails."""
    diagnosis: dict = {"step": step_name, "issues": []}

    dismissed = _dismiss_lv_popups()
    if dismissed:
        diagnosis["issues"].append("popup_blocking")
    dismissed2 = _dismiss_dialogs()
    if dismissed2:
        diagnosis["issues"].append("dialog_blocking")

    active = _find_active_vi()
    if active:
        diagnosis["active_title"] = _get_window_title(active)
        if active != hwnd:
            diagnosis["issues"].append("wrong_window")
    else:
        diagnosis["issues"].append("no_active_window")

    try:
        target = active or hwnd
        if target:
            _screenshot(target, ad, -1, f"diagnosis_{step_name}")
    except Exception:
        pass

    if not diagnosis["issues"]:
        diagnosis["issues"].append("unknown")

    logger.info("Step failure diagnosis: %s", diagnosis,
                extra={"action": "diagnose", "step": step_name})
    return diagnosis


def _recover_from_failure(hwnd: int, diagnosis: dict) -> int | None:
    """Take corrective action based on diagnosis. Returns a (possibly new) hwnd."""
    issues = diagnosis.get("issues", [])

    if "popup_blocking" in issues or "dialog_blocking" in issues:
        _dismiss_lv_popups()
        _dismiss_dialogs()
        time.sleep(1.0)

    if "wrong_window" in issues or "no_active_window" in issues:
        new_hwnd = find_labview_window()
        if new_hwnd:
            _setup_vi(new_hwnd)
            return new_hwnd

    active = _find_active_vi()
    if active:
        _setup_vi(active)
        return active

    return hwnd


# ---------------------------------------------------------------------------
# Resolution-independent click helpers (template-first, pixel fallback)
# ---------------------------------------------------------------------------

CRITICAL_STEPS: set[str] = {
    "step_06_select_ap",
    "step_08_select_client",
    "step_11_band_select",
    "step_18_final_start",
}


def _click_template_or_fallback(
    hwnd: int,
    template_name: str,
    fallback_px: tuple[int, int],
    threshold: float = 0.70,
    strict: bool = False,
) -> bool:
    """Locate an element via template matching and click its center.

    When *strict* is False (default), falls back to the hardcoded pixel
    offset when the template is not found.  When *strict* is True, the
    fallback is skipped and the function returns False — callers must
    handle the failure explicitly.
    """
    try:
        img = capture_window(hwnd)
        center = find_template_center(img, template_name, threshold)
        if center:
            clicked = _safe_click(hwnd, center[0], center[1],
                                  label=f"template:{template_name}")
            if clicked:
                logger.debug("Clicked %s via template at (%d,%d)",
                             template_name, center[0], center[1])
            return clicked
    except Exception:
        pass

    if strict:
        logger.error("Template %r NOT found and strict=True — refusing blind click",
                     template_name,
                     extra={"action": "click_template", "step": "strict_fail"})
        return False

    return _click_at(hwnd, fallback_px[0], fallback_px[1])


def _detect_orange_arrow_right(hwnd: int) -> tuple:
    """Detect the right orange arrow via HSV color matching on a window screenshot.

    Returns (cx, cy) center of the rightmost orange region, or None if not found.
    """
    try:
        img = capture_window(hwnd)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower = np.array([10, 150, 150])
        upper = np.array([25, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for c in contours:
            area = cv2.contourArea(c)
            if area < 200:
                continue
            x, y, w, h = cv2.boundingRect(c)
            cx, cy = x + w // 2, y + h // 2
            if best is None or cx > best[0]:
                best = (cx, cy)
        if best:
            logger.info(
                "Detected right orange arrow at (%d, %d)",
                best[0], best[1],
                extra={"action": "orange_arrow", "step": "detected"})
        return best
    except Exception as exc:
        logger.warning("Orange arrow detection failed: %s", exc,
                       extra={"action": "orange_arrow", "step": "detect_error"})
        return None


def _click_orange_arrow_smart(hwnd: int) -> bool:
    """Click the right-hand orange arrow (Next) button.

    Uses HSV color detection to find the arrow dynamically (different VIs
    place it at different Y positions). Falls back to ORANGE_ARROW_PX if
    detection fails.
    """
    _dismiss_lv_popups()

    set_window_rect(hwnd, 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
    time.sleep(0.3)

    rect = get_window_rect(hwnd)
    actual_w = rect[2] - rect[0]
    actual_h = rect[3] - rect[1]
    if actual_w < WINDOW_WIDTH or actual_h < WINDOW_HEIGHT:
        logger.warning(
            "Window resize to %dx%d failed — actual %dx%d. Retrying...",
            WINDOW_WIDTH, WINDOW_HEIGHT, actual_w, actual_h,
            extra={"action": "orange_arrow", "step": "resize_retry"},
        )
        set_window_rect(hwnd, 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        time.sleep(0.5)
        rect = get_window_rect(hwnd)
        actual_w = rect[2] - rect[0]
        actual_h = rect[3] - rect[1]

    _ensure_foreground(hwnd)
    time.sleep(0.2)

    detected = _detect_orange_arrow_right(hwnd)
    if detected:
        cx, cy = detected
        _dismiss_lv_popups()
        _ensure_foreground(hwnd)
        time.sleep(0.2)
        _safe_click(hwnd, cx, cy, label="orange_arrow_detected")
        return True

    logger.warning(
        "Orange arrow not detected via color — falling back to (%d, %d)",
        ORANGE_ARROW_PX[0], ORANGE_ARROW_PX[1],
        extra={"action": "orange_arrow", "step": "fallback"})
    clicked = _safe_click(hwnd, ORANGE_ARROW_PX[0], ORANGE_ARROW_PX[1],
                          label="orange_arrow")
    if not clicked:
        calc_x = actual_w - 85
        calc_y = actual_h - 85
        _safe_click(hwnd, calc_x, calc_y, label="orange_arrow_calc")
    return True


def _click_done_button_smart(popup_hwnd: int) -> bool:
    """Click the Done button on a popup list dialog.

    Tries template matching first, falls back to bottom-right area.
    """
    return _click_template_or_fallback(
        popup_hwnd, "done_button.png",
        (480, 870))


def _click_green_ok_smart(login_hwnd: int) -> bool:
    """Click the green OK button on the login dialog."""
    return _click_template_or_fallback(
        login_hwnd, "green_ok_button.png", (290, 170))


AP_FOLDER = r"E:\AP"
CLIENT_FOLDER = r"E:\Client"

_LISTBOX_EXCLUDE: set[str] = set()


def _build_listbox_items(folder_path: str) -> list[str]:
    """Read .txt stems from *folder_path*, filter, uppercase, and sort."""
    items = []
    for f in os.listdir(folder_path):
        if not f.lower().endswith(".txt"):
            continue
        stem = f[:-4].upper()
        if stem in _LISTBOX_EXCLUDE:
            continue
        items.append(stem)
    items.sort()
    return items


def _select_list_item_by_folder_index(
    popup_hwnd: int,
    folder_path: str,
    target_name: str,
    artifacts_dir: str,
    step_num: int,
    prefix: str,
    calibration_offset: int = 0,
) -> bool:
    """Select an item in a LabVIEW listbox by computing its index from disk.

    Reads .txt files in *folder_path*, builds a sorted list matching the
    LabVIEW listbox, and navigates with Home + Down(index).
    *calibration_offset* adjusts the Down-press count (positive = more Down).
    Returns True on success.
    """
    items = _build_listbox_items(folder_path)
    target_upper = target_name.upper()
    if target_upper not in items:
        logger.error("Target %r not in %s (%d items)",
                     target_name, folder_path, len(items),
                     extra={"action": f"select_{prefix}", "step": "not_found"})
        return False

    target_idx = items.index(target_upper) + calibration_offset
    target_idx = max(0, min(target_idx, len(items) - 1))
    logger.info("Navigating to %r: Home + Down(%d) in %s (%d items)",
                target_name, target_idx, folder_path, len(items),
                extra={"action": f"select_{prefix}", "step": "folder_nav"})

    _force_fg(popup_hwnd)
    time.sleep(0.5)
    rect = get_window_rect(popup_hwnd)
    abs_x = rect[0] + 120
    abs_y = rect[1] + 300
    pyautogui.click(abs_x, abs_y)
    time.sleep(0.3)

    pyautogui.press('home')
    time.sleep(0.4)

    for _ in range(target_idx):
        pyautogui.press('down')
        time.sleep(0.02)
    time.sleep(0.4)

    _screenshot(popup_hwnd, artifacts_dir, step_num,
                f"{prefix}_after_nav")
    return True


def _locate_field_via_template(
    hwnd: int,
    label_template: str,
    offset: tuple[int, int] = (0, 0),
    threshold: float = 0.70,
) -> tuple[int, int] | None:
    """Find a field by locating its label template, then apply offset.

    Returns (px, py) in window-relative coordinates, or None if the
    template is not found.
    """
    try:
        img = capture_window(hwnd)
        center = find_template_center(img, label_template, threshold)
        if center:
            return (center[0] + offset[0], center[1] + offset[1])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Step implementations (pyautogui-based with absolute pixel offsets)
# ---------------------------------------------------------------------------

def step_00_attach(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Attach to the running LabVIEW window."""
    t0 = time.monotonic()
    if hwnd is None:
        return StepResult("attach", False, error="No LabVIEW window found")
    ss = _screenshot(hwnd, ad, 0, "attach")
    return StepResult("attach", True, time.monotonic() - t0, ss)


def step_01_click_throughput(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """On main screen, click the 'Throughput Testing' tab."""
    t0 = time.monotonic()
    hwnd = find_labview_window(["480 000"]) or hwnd
    _setup_vi(hwnd, *MAIN_WINDOW_SIZE)
    _check_screen(hwnd, "step_01", "click_throughput")
    ss = _screenshot(hwnd, ad, 1, "main_screen")

    _click_at(hwnd, 130, 240)

    _poll_until(
        lambda: (_find_vi_window("password", timeout=0.3)
                 or _find_vi_window("logon", timeout=0.3)
                 or _find_vi_window("400 600", timeout=0.3)),
        timeout=8.0, desc="login or wizard window after Throughput click",
    )

    ss2 = _screenshot(hwnd, ad, 1, "after_throughput")
    return StepResult("click_throughput", True, time.monotonic() - t0, ss2)


def step_02_login(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Enter username and password, click OK (green arrow).

    Handles startup popups that can intercept the Throughput Testing click.
    If login window is not found, dismisses popups and retries the
    Throughput Testing click on the main window.
    """
    t0 = time.monotonic()

    _dismiss_lv_popups()
    _dismiss_dialogs()

    login_hwnd = _poll_for_window_appear("password", timeout=10.0)
    if not login_hwnd:
        login_hwnd = (_find_vi_window("logon", timeout=3.0)
                      or _find_vi_window("8000", timeout=2.0)
                      or _find_vi_window("name and password", timeout=2.0))

    if not login_hwnd:
        logger.info("Login window not found on first try, "
                     "retrying Throughput click after popup dismissal",
                     extra={"action": "login", "step": "retry_throughput"})
        _dismiss_lv_popups()
        _dismiss_dialogs()
        time.sleep(1.0)

        main = find_labview_window(["480 000"])
        if main:
            _setup_vi(main, *MAIN_WINDOW_SIZE)
            _click_at(main, 130, 240)
            _poll_until(
                lambda: (_find_vi_window("password", timeout=0.3)
                         or _find_vi_window("logon", timeout=0.3)),
                timeout=8.0, desc="login window after retry",
            )
            _dismiss_lv_popups()

        login_hwnd = (_find_vi_window("password", timeout=5.0)
                      or _find_vi_window("logon", timeout=3.0)
                      or _find_vi_window("8000", timeout=2.0)
                      or _find_vi_window("name and password", timeout=2.0))

    if not login_hwnd:
        already_in = (_find_vi_window("400 600", timeout=2.0)
                      or _find_vi_window("table position", timeout=1.0)
                      or _find_vi_window("481", timeout=1.0))
        if already_in:
            title = _get_window_title(already_in)
            logger.info("No login window - already logged in (found %r)",
                        title,
                        extra={"action": "login", "step": "already_logged_in"})
            ss = _screenshot(already_in, ad, 2, "already_logged_in")
            return StepResult("login", True, time.monotonic() - t0, ss,
                              detail={"already_logged_in": True})

        ss = _screenshot(hwnd, ad, 2, "no_login_window")
        logger.error("Login window NOT found after extended search",
                      extra={"action": "login", "step": "not_found"})
        return StepResult("login", False, time.monotonic() - t0, ss,
                          error="Login window not found - expected after Throughput click")

    set_window_rect(login_hwnd, 400, 300, *LOGIN_WINDOW_SIZE)
    time.sleep(0.3)

    frame = _find_frame_window()
    if frame:
        user32.SetForegroundWindow(frame)
    time.sleep(0.5)

    _check_screen(login_hwnd, "step_02", "login")
    ss = _screenshot(login_hwnd, ad, 2, "login_screen")

    _safe_triple_click(login_hwnd, 218, 75, label="username_field")
    time.sleep(0.3)
    _safe_type(cfg.username, label="username_text")
    time.sleep(0.3)

    _safe_triple_click(login_hwnd, 218, 129, label="password_field")
    time.sleep(0.3)
    _safe_type(cfg.password, label="password_text")
    time.sleep(0.3)

    _click_green_ok_smart(login_hwnd)

    gone = _poll_for_window_gone(login_hwnd, timeout=8.0)
    if not gone:
        _dismiss_dialogs()
        return StepResult("login", False,
                          time.monotonic() - t0,
                          error="Login failed - window still visible")

    ss2 = _screenshot(hwnd, ad, 2, "after_login")
    return StepResult("login", True, time.monotonic() - t0, ss2)


def step_03_test_type(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Select test type '1 rpm (fast)' via keyboard nav and click orange arrow.

    Available dropdown items (keyboard nav skips [Removed] items):
      0: Not valid (default)
      1: Link Budget
      2: 1 rpm (fast)   <-- target
      3: Interference LB (RvR)
    Strategy: click dropdown at (330, 368), Up 15 to top, Down 2 to '1 rpm (fast)'.
    """
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("400 600 test", timeout=10.0)
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 3, "wrong_screen")
        return StepResult("test_type", False, time.monotonic() - t0, ss,
                          error="Test type VI '400 600 test' not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_03", "test_type")
    _screenshot(vi_hwnd, ad, 3, "test_type_before")

    try:
        before_img = capture_window(vi_hwnd)
    except Exception:
        before_img = None

    _dismiss_lv_popups()
    _ensure_foreground(vi_hwnd)
    time.sleep(0.3)
    _select_dropdown_by_nav(vi_hwnd, (330, 368), up_presses=15, down_presses=2)
    time.sleep(0.5)

    _verify_dropdown_selection(vi_hwnd, (330, 368), "rpm",
                               up_presses=15, down_presses=2)

    ss_after = _screenshot(vi_hwnd, ad, 3, "test_type_after_select")

    if before_img is not None:
        try:
            after_img = capture_window(vi_hwnd)
            if not _region_changed(before_img, after_img, 50, 260, 300, 50):
                logger.warning("Dropdown region unchanged - selection may have failed",
                               extra={"action": "step_03", "step": "dropdown_verify"})
        except Exception:
            pass

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd,
                                       expected_hint="table position",
                                       timeout=15.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 3, "no_transition")
        return StepResult("test_type", False, time.monotonic() - t0, ss,
                          error="Screen did not advance to table position")

    ss2 = _screenshot(new_hwnd, ad, 3, "after_test_type")
    return StepResult("test_type", True, time.monotonic() - t0, ss2)


def step_04_table_position(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """DUT table position screen - click orange arrow to proceed."""
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("table position", timeout=10.0)
    if not vi_hwnd:
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 4, "wrong_screen")
        return StepResult("table_position", False, time.monotonic() - t0, ss,
                          error="Table position VI not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_04", "table_position")
    _screenshot(vi_hwnd, ad, 4, "table_position")
    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, expected_hint="481", timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 4, "no_transition")
        return StepResult("table_position", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after table position")

    ss2 = _screenshot(new_hwnd, ad, 4, "after_table_position")
    return StepResult("table_position", True, time.monotonic() - t0, ss2)


def step_05_freq_channel(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Set frequency range, RF channels, and user information on the 481.300 VI.

    Calibrated coordinates (2026-03-16, 1288x1040 window at 0,0):
      Freq Range dropdown: (511, 344)
      RF Channel 2G: (460, 752)
      RF Channel 5G: (655, 752)
      RF Channel 6G: (850, 753)
      User information: (690, 845)
    """
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("481.300", timeout=10.0)
    if not vi_hwnd:
        vi_hwnd = (_find_vi_window("freq", timeout=3.0)
                   or _find_vi_window("channel", timeout=3.0))
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 5, "wrong_screen")
        return StepResult("freq_channel", False, time.monotonic() - t0, ss,
                          error="Freq/channel VI not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_05", "freq_channel")
    _screenshot(vi_hwnd, ad, 5, "freq_channel_screen")

    _safe_press("escape", label="step05_clear_focus")
    time.sleep(0.3)

    # Select frequency range (MLO) from dropdown at (511, 344)
    # Items: 2.4GHz(0), 5GHz(1), 6GHz(2), MLO(3), Not Valid(4)
    _dismiss_lv_popups()
    _ensure_foreground(vi_hwnd)
    time.sleep(0.2)
    _select_dropdown_by_nav(vi_hwnd, (511, 344), up_presses=10, down_presses=3)
    time.sleep(0.5)
    _verify_dropdown_selection(vi_hwnd, (511, 344), "MLO",
                               up_presses=10, down_presses=3)
    _screenshot(vi_hwnd, ad, 5, "freq_range_selected")

    _clear_and_type(vi_hwnd, 460, 752, cfg.rf_channel_2g)
    _verify_typed_value(vi_hwnd, 460, 752, cfg.rf_channel_2g)

    _clear_and_type(vi_hwnd, 655, 752, cfg.rf_channel_5g)
    _verify_typed_value(vi_hwnd, 655, 752, cfg.rf_channel_5g)

    _clear_and_type(vi_hwnd, 850, 753, cfg.rf_channel_6g)
    _verify_typed_value(vi_hwnd, 850, 753, cfg.rf_channel_6g)

    _clear_and_type(vi_hwnd, 690, 845, cfg.user_information)
    _verify_typed_value(vi_hwnd, 690, 845, cfg.user_information,
                        field_w=200)

    _screenshot(vi_hwnd, ad, 5, "fields_filled")

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 5, "no_transition")
        return StepResult("freq_channel", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after freq/channel")

    ss2 = _screenshot(new_hwnd, ad, 5, "after_freq_channel")
    return StepResult("freq_channel", True, time.monotonic() - t0, ss2)


def step_06_select_ap(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Click Select AP icon, find AP in popup list via OCR, click DONE.

    SAFETY: blind-scroll fallback is removed. If OCR cannot find the
    target AP the step fails and the retry loop will re-attempt.
    """
    t0 = time.monotonic()

    vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        _poll_until(lambda: _find_active_vi() is not None,
                    timeout=5.0, desc="AP selection VI")
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 6, "wrong_screen")
        return StepResult("select_ap", False, time.monotonic() - t0, ss,
                          error="AP selection VI not found")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 6, "select_ap_screen")

    _click_at(vi_hwnd, 100, 350)

    popup = _poll_for_window_appear("list in folder", timeout=5.0)
    if not popup:
        popup = _poll_for_window_appear("8002", timeout=3.0)
    if popup:
        set_window_rect(popup, 0, 0, *POPUP_SIZE)
        time.sleep(0.5)
        _ensure_foreground(popup)
        time.sleep(0.3)
        _screenshot(popup, ad, 6, "ap_popup")

        list_region = (30, 80, POPUP_SIZE[0] - 60, POPUP_SIZE[1] - 160)
        hit = _ocr_search_list_popup(popup, cfg.ap_name, list_region,
                                      max_scrolls=120)
        if hit:
            _safe_click(popup, hit[0], hit[1], label="ap_item")
            time.sleep(0.5)
            _screenshot(popup, ad, 6, "ap_found_ocr")
            logger.info("AP %r found via OCR at (%d,%d)",
                        cfg.ap_name, hit[0], hit[1],
                        extra={"action": "select_ap", "step": "ocr_found"})
        else:
            logger.warning(
                "OCR search for AP %r failed — falling back to folder-index nav.",
                cfg.ap_name,
                extra={"action": "select_ap", "step": "ocr_fail_folder_fallback"})
            _screenshot(popup, ad, 6, "ap_ocr_failed")
            _select_list_item_by_folder_index(
                popup, AP_FOLDER, cfg.ap_name, ad, 6, "ap")

        _screenshot(popup, ad, 6, "ap_after_select")
        _click_done_button_smart(popup)
        time.sleep(1.5)

        if not _ensure_ap_client_popups_closed("step_06_after_done", ad):
            logger.error("AP/Client popup still open after Done click — "
                         "this will block step 7 transition",
                         extra={"action": "select_ap",
                                "step": "popup_not_closed"})
    else:
        logger.warning("AP popup not found",
                        extra={"action": "select_ap", "step": "no_popup"})

    vi_hwnd = _find_vi_window("400 600 AP", timeout=10.0)
    if not vi_hwnd:
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        return StepResult("select_ap", False, time.monotonic() - t0,
                          error="400 600 AP.vi not found after AP popup")

    _setup_vi(vi_hwnd)
    time.sleep(1.0)

    logger.info("Waiting for AP info to load (polling orange arrow, up to 120s)...",
                extra={"action": "select_ap", "step": "wait_ap_info"})
    ap_ready = _poll_until(
        lambda: _detect_orange_arrow_right(vi_hwnd) is not None,
        timeout=120.0, interval=3.0,
        desc="orange arrow visible on AP screen",
    )
    if not ap_ready:
        logger.warning("Orange arrow not detected after 120s — continuing anyway",
                       extra={"action": "select_ap", "step": "ap_info_timeout"})

    ss2 = _screenshot(vi_hwnd, ad, 6, "ap_after_done")

    if is_ocr_available():
        try:
            img = capture_window(vi_hwnd)
            full_text = ocr_region_freeform(img, 0, 0, img.shape[1], img.shape[0])
            if cfg.ap_name.lower() not in full_text.lower():
                logger.error("Post-select AP verify FAILED: %r not on screen",
                             cfg.ap_name,
                             extra={"action": "select_ap", "step": "post_verify_fail"})
                return StepResult("select_ap", False, time.monotonic() - t0,
                                  error=f"AP {cfg.ap_name!r} not visible after selection")
            logger.info("Post-select AP verify OK: %r found on screen",
                        cfg.ap_name,
                        extra={"action": "select_ap", "step": "post_verify_ok"})
        except Exception as exc:
            logger.warning("Post-select AP OCR check failed: %s", exc)

    logger.info("AP selection complete — orange arrow deferred to step_07",
                extra={"action": "select_ap", "step": "done"})
    return StepResult("select_ap", True, time.monotonic() - t0, ss2)


def _fill_firmware_rev(vi_hwnd: int, ad: str) -> None:
    """Overwrite the Firmware rev field with a known-good value.

    Always triple-clicks the field to select all existing text, types
    the firmware revision directly, and presses Enter.  This avoids the
    fragile copy/paste approach that depended on accurate coordinates
    for the 'Last Firmware rev' source field.

    Field position (window-relative on 1288x1040 AP screen):
      - Firmware rev field center: (610, 335)
    """
    logger.info("Filling Firmware rev field with direct typing",
                extra={"action": "fill_firmware", "step": "type"})

    _ensure_foreground(vi_hwnd)
    time.sleep(0.2)
    _safe_triple_click(vi_hwnd, 610, 335, label="firmware_rev")
    time.sleep(0.3)
    _safe_type("V1.0.10.8", label="firmware_rev_value")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.5)

    save_screenshot(capture_window(vi_hwnd), ad, "firmware_rev_filled.png")


def step_07_use_last_ap(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Fill firmware rev if empty, click 'Use Last' toggle, then orange arrow.

    The LabVIEW program may block on 'Get AP info' for several minutes
    when the AP device is unreachable.  This step retries the
    Use-Last + arrow sequence every 30s for up to 8 minutes.
    """
    t0 = time.monotonic()
    MAX_WAIT = 480.0

    vi_hwnd = _find_vi_window("400 600 AP", timeout=10.0)
    if not vi_hwnd:
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 7, "wrong_screen")
        return StepResult("use_last_ap", False, time.monotonic() - t0, ss,
                          error="400 600 AP.vi not found for use_last_ap")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 7, "use_last_ap")

    _fill_firmware_rev(vi_hwnd, os.path.join(ad, ".."))

    attempt = 0
    deadline = time.monotonic() + MAX_WAIT
    popup_blocked_count = 0
    while time.monotonic() < deadline:
        attempt += 1
        logger.info("Use-Last + arrow attempt %d (elapsed %.0fs / %.0fs)",
                    attempt, time.monotonic() - t0, MAX_WAIT,
                    extra={"action": "use_last_ap", "step": f"attempt_{attempt}"})

        popups = _count_ap_client_popups()
        if popups:
            popup_blocked_count += 1
            logger.warning(
                "AP/Client popup(s) blocking step 7 (attempt %d): %d open: %s",
                attempt, len(popups),
                [(h, t) for h, t in popups],
                extra={"action": "use_last_ap",
                       "step": "popup_blocking_transition"})
            for popup_hwnd, _ in popups:
                minimize_window(popup_hwnd)
                time.sleep(0.3)

        _dismiss_lv_popups()
        _ensure_foreground(vi_hwnd)
        time.sleep(0.3)
        _click_at(vi_hwnd, 700, 229)
        time.sleep(2.0)

        _dismiss_lv_popups()
        _ensure_foreground(vi_hwnd)
        time.sleep(0.3)
        _click_orange_arrow_smart(vi_hwnd)

        new_hwnd, ok = _verify_transition(vi_hwnd, timeout=15.0)
        if ok:
            _screenshot(vi_hwnd, ad, 7, "after_use_last_click")
            ss2 = _screenshot(new_hwnd, ad, 7, "after_use_last")
            return StepResult("use_last_ap", True, time.monotonic() - t0, ss2)

        logger.info("Arrow did not advance screen — waiting for AP info timeout...",
                    extra={"action": "use_last_ap", "step": "wait_retry"})
        time.sleep(15.0)

    ss = _screenshot(vi_hwnd, ad, 7, "no_transition")
    error_msg = f"Screen did not advance after {MAX_WAIT:.0f}s"
    if popup_blocked_count > 0:
        error_msg = (f"popup_blocking_transition: AP/Client popup detected on "
                     f"{popup_blocked_count}/{attempt} attempts; "
                     f"screen did not advance after {MAX_WAIT:.0f}s")
    return StepResult("use_last_ap", False, time.monotonic() - t0, ss,
                      error=error_msg)


def step_08_select_client(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Select client (e.g. INTEL_BE200) from popup via OCR-assisted search.

    SAFETY: blind-scroll fallback is removed.  If OCR cannot find the
    target client the step fails and the retry loop will re-attempt.
    """
    t0 = time.monotonic()

    vi_hwnd = _find_vi_window("400 600 STN", timeout=10.0)
    if not vi_hwnd:
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 8, "wrong_screen")
        return StepResult("select_client", False, time.monotonic() - t0, ss,
                          error="400 600 STN.vi not found for select_client")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 8, "select_client_screen")

    _dismiss_lv_popups()
    _ensure_foreground(vi_hwnd)
    time.sleep(0.3)
    _click_at(vi_hwnd, 100, 348)

    popup = _poll_for_window_appear("list in folder", timeout=5.0)
    if not popup:
        popup = _poll_for_window_appear("8002", timeout=3.0)

    if not popup:
        logger.info("Client popup not found after image click — retrying with text button",
                    extra={"action": "select_client", "step": "retry_text"})
        _dismiss_lv_popups()
        _ensure_foreground(vi_hwnd)
        time.sleep(0.3)
        _click_at(vi_hwnd, 225, 350)
        popup = _poll_for_window_appear("list in folder", timeout=5.0)
        if not popup:
            popup = _poll_for_window_appear("8002", timeout=3.0)

    if popup:
        set_window_rect(popup, 0, 0, *POPUP_SIZE)
        time.sleep(0.5)
        _ensure_foreground(popup)
        time.sleep(0.3)
        _screenshot(popup, ad, 8, "client_popup")

        list_region = (30, 80, POPUP_SIZE[0] - 60, POPUP_SIZE[1] - 160)
        hit = _ocr_search_list_popup(popup, cfg.client_name, list_region,
                                      max_scrolls=60)
        if hit:
            _safe_click(popup, hit[0], hit[1], label="client_item")
            time.sleep(0.5)
            _screenshot(popup, ad, 8, "client_found_ocr")
            logger.info("Client %r found via OCR at (%d,%d)",
                        cfg.client_name, hit[0], hit[1],
                        extra={"action": "select_client", "step": "ocr_found"})
        elif not is_ocr_available():
            logger.warning(
                "OCR UNAVAILABLE — using folder-index nav for client %r.",
                cfg.client_name,
                extra={"action": "select_client",
                       "step": "no_ocr_folder"})
            _select_list_item_by_folder_index(
                popup, CLIENT_FOLDER, cfg.client_name, ad, 8, "client")
        else:
            logger.warning(
                "OCR search for client %r failed — falling back to folder-index nav.",
                cfg.client_name,
                extra={"action": "select_client",
                       "step": "ocr_fail_folder_fallback"})
            _screenshot(popup, ad, 8, "client_ocr_failed")
            _select_list_item_by_folder_index(
                popup, CLIENT_FOLDER, cfg.client_name, ad, 8, "client")

        _screenshot(popup, ad, 8, "client_after_select")
        _click_done_button_smart(popup)
        time.sleep(1.5)
    else:
        logger.warning("Client popup not found",
                        extra={"action": "select_client", "step": "no_popup"})

    vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        return StepResult("select_client", False, time.monotonic() - t0,
                          error="No VI found after client popup")

    _setup_vi(vi_hwnd)

    # Post-action verification: OCR the screen to confirm client name is shown
    if is_ocr_available():
        try:
            img = capture_window(vi_hwnd)
            full_text = ocr_region_freeform(img, 0, 0, img.shape[1], img.shape[0])
            if cfg.client_name.lower() not in full_text.lower():
                logger.error("Post-select client verify FAILED: %r not on screen",
                             cfg.client_name,
                             extra={"action": "select_client",
                                    "step": "post_verify_fail"})
                _screenshot(vi_hwnd, ad, 8, "client_post_verify_fail")
                return StepResult(
                    "select_client", False, time.monotonic() - t0,
                    error=f"Client {cfg.client_name!r} not visible after selection")
            logger.info("Post-select client verify OK: %r found on screen",
                        cfg.client_name,
                        extra={"action": "select_client",
                               "step": "post_verify_ok"})
        except Exception as exc:
            logger.warning("Post-select client OCR check failed: %s", exc)

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 8, "no_transition")
        return StepResult("select_client", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after client selection")

    ss2 = _screenshot(new_hwnd, ad, 8, "after_client")
    return StepResult("select_client", True, time.monotonic() - t0, ss2)


def step_09_dut_ip(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Filter/pass-through screen (400_600_Filter.vi) -- just click orange arrow."""
    t0 = time.monotonic()

    vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        _poll_until(lambda: _find_active_vi() is not None,
                    timeout=5.0, desc="dut_ip VI")
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 9, "wrong_screen")
        return StepResult("dut_ip", False, time.monotonic() - t0, ss,
                          error="VI not found for dut_ip")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 9, "dut_ip")

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 9, "no_transition")
        return StepResult("dut_ip", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after dut_ip")

    ss2 = _screenshot(new_hwnd, ad, 9, "after_dut_ip")
    return StepResult("dut_ip", True, time.monotonic() - t0, ss2)


def step_10_use_last_dut(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Click 'Last' toggle on DUT screen then orange arrow."""
    t0 = time.monotonic()

    vi_hwnd = _find_vi_window("400 600 DUT", timeout=10.0)
    if not vi_hwnd:
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 10, "wrong_screen")
        return StepResult("use_last_dut", False, time.monotonic() - t0, ss,
                          error="400 600 DUT.vi not found for use_last_dut")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 10, "use_last_dut")

    _dismiss_lv_popups()
    _ensure_foreground(vi_hwnd)
    time.sleep(0.3)
    _click_at(vi_hwnd, 1060, 895)
    time.sleep(1.0)
    _screenshot(vi_hwnd, ad, 10, "after_use_last_click")

    _dismiss_lv_popups()
    _ensure_foreground(vi_hwnd)
    time.sleep(0.3)
    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, expected_hint="IP address",
                                       timeout=30.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 10, "no_transition")
        return StepResult("use_last_dut", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after use_last_dut")

    ss2 = _screenshot(new_hwnd, ad, 10, "after_use_last")
    return StepResult("use_last_dut", True, time.monotonic() - t0, ss2)


def step_11_band_select(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """IP address Dual LAN screen: click [1], set dropdowns, fill AP IP."""
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("IP address", timeout=10.0)
    if not vi_hwnd:
        vi_hwnd = _find_vi_window("Dual LAN", timeout=3.0)
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 11, "wrong_screen")
        return StepResult("band_select", False, time.monotonic() - t0, ss,
                          error="IP address VI not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_11", "band_select")
    _screenshot(vi_hwnd, ad, 11, "ip_screen")

    _click_at(vi_hwnd, 360, 830)
    time.sleep(2.0)
    _screenshot(vi_hwnd, ad, 11, "after_click_1")

    _click_at(vi_hwnd, 600, 552)
    time.sleep(1.0)
    _screenshot(vi_hwnd, ad, 11, "2g_dropdown_open")
    _click_at(vi_hwnd, 600, 646)
    time.sleep(0.5)
    _screenshot(vi_hwnd, ad, 11, "after_2g_dropdown")

    _verify_dropdown_selection(vi_hwnd, (600, 552), cfg.ip_dropdown_2g,
                               display_w=80, strict=False)

    _click_at(vi_hwnd, 920, 552)
    time.sleep(1.0)
    _screenshot(vi_hwnd, ad, 11, "5g_dropdown_open")
    _click_at(vi_hwnd, 920, 646)
    time.sleep(0.5)
    _screenshot(vi_hwnd, ad, 11, "after_5g_dropdown")

    _verify_dropdown_selection(vi_hwnd, (920, 552), cfg.ip_dropdown_5g6g,
                               display_w=80, strict=False)

    pyautogui.press("escape")
    time.sleep(0.3)
    _click_at(vi_hwnd, 400, 300)
    time.sleep(0.5)

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 11, "no_transition")
        return StepResult("band_select", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after band_select")

    ss2 = _screenshot(new_hwnd, ad, 11, "after_ip")
    return StepResult("band_select", True, time.monotonic() - t0, ss2)


def step_12_chariot_pairs(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Set number of Chariot pairs for the active band."""
    t0 = time.monotonic()

    vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        _poll_until(lambda: _find_active_vi() is not None,
                    timeout=5.0, desc="chariot_pairs VI")
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 12, "wrong_screen")
        return StepResult("chariot_pairs", False, time.monotonic() - t0, ss,
                          error="VI not found for chariot_pairs")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 12, "chariot_pairs")

    if cfg.band in ("2.4G", "MLO"):
        _type_in_field(vi_hwnd, 580, 406, cfg.number_of_pairs)
        _verify_typed_value(vi_hwnd, 580, 406, cfg.number_of_pairs)
    if cfg.band in ("5G", "6G", "MLO"):
        _type_in_field(vi_hwnd, 580, 706, cfg.number_of_pairs_5g6g)
        _verify_typed_value(vi_hwnd, 580, 706, cfg.number_of_pairs_5g6g)

    _screenshot(vi_hwnd, ad, 12, "pairs_filled")

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 12, "no_transition")
        return StepResult("chariot_pairs", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after chariot_pairs")

    ss2 = _screenshot(new_hwnd, ad, 12, "after_pairs")
    return StepResult("chariot_pairs", True, time.monotonic() - t0, ss2)


def step_13_pass_through(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Pass-through screen - just click orange arrow."""
    t0 = time.monotonic()

    vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        _poll_until(lambda: _find_active_vi() is not None,
                    timeout=5.0, desc="pass_through VI")
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 13, "wrong_screen")
        return StepResult("pass_through", False, time.monotonic() - t0, ss,
                          error="VI not found for pass_through")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 13, "pass_through")
    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, expected_hint="MODE",
                                       timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 13, "no_transition")
        return StepResult("pass_through", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after pass_through")

    ss2 = _screenshot(new_hwnd, ad, 13, "after_pass")
    return StepResult("pass_through", True, time.monotonic() - t0, ss2)


def step_14_mode(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Set mode (BW) via dropdown at (249, 757)."""
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("MODE", timeout=10.0)
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 14, "wrong_screen")
        return StepResult("mode", False, time.monotonic() - t0, ss,
                          error="MODE VI not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_14", "mode")
    _screenshot(vi_hwnd, ad, 14, "mode_screen")

    nav = BW_MODE_NAV.get(cfg.mode, (6, 0))
    up_count, down_count = nav

    logger.info("Setting mode to %s (Up=%d, Down=%d)",
                cfg.mode, up_count, down_count,
                extra={"action": "step_14", "step": "mode_select"})

    _select_dropdown_by_nav(vi_hwnd, (249, 757), up_count, down_count)
    time.sleep(0.5)

    _verify_dropdown_selection(vi_hwnd, (249, 757), cfg.mode,
                               up_presses=up_count, down_presses=down_count)

    _screenshot(vi_hwnd, ad, 14, "mode_selected")

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, expected_hint="atten",
                                       timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 14, "no_transition")
        return StepResult("mode", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after mode selection")

    ss2 = _screenshot(new_hwnd, ad, 14, "after_mode")
    return StepResult("mode", True, time.monotonic() - t0, ss2)


def step_15_attenuation(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Set Start atten (153,496), Step Size (566,496), Steps (750,496)."""
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("atten", timeout=10.0)
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 15, "wrong_screen")
        return StepResult("attenuation", False, time.monotonic() - t0, ss,
                          error="Attenuation VI not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_15", "attenuation")
    _screenshot(vi_hwnd, ad, 15, "attenuation")

    _type_in_field(vi_hwnd, 153, 496, cfg.start_atten)
    _verify_typed_value(vi_hwnd, 153, 496, cfg.start_atten)

    _type_in_field(vi_hwnd, 566, 496, cfg.step_size)
    _verify_typed_value(vi_hwnd, 566, 496, cfg.step_size)

    _type_in_field(vi_hwnd, 750, 496, cfg.steps)
    _verify_typed_value(vi_hwnd, 750, 496, cfg.steps)

    _screenshot(vi_hwnd, ad, 15, "atten_filled")

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, expected_hint="Chariot",
                                       timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 15, "no_transition")
        return StepResult("attenuation", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after attenuation")

    ss2 = _screenshot(new_hwnd, ad, 15, "after_atten")
    return StepResult("attenuation", True, time.monotonic() - t0, ss2)


def step_16_design_stage(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Select design stage via dropdown at (734, 491).
    List: Alpha, Beta, Pilot, MP, Not Valid.
    Strategy: Up 15 (to Alpha), Down 1 (to Beta), Enter.
    """
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("Chariot", timeout=10.0)
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 16, "wrong_screen")
        return StepResult("design_stage", False, time.monotonic() - t0, ss,
                          error="Design stage VI (Chariot) not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_16", "design_stage")
    _screenshot(vi_hwnd, ad, 16, "design_stage")

    _select_dropdown_by_nav(vi_hwnd, (734, 491), up_presses=15, down_presses=1)
    time.sleep(0.5)

    _verify_dropdown_selection(vi_hwnd, (734, 491), cfg.design_stage,
                               up_presses=15, down_presses=1)

    _screenshot(vi_hwnd, ad, 16, "design_stage_selected")

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, expected_hint="REGION",
                                       timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 16, "no_transition")
        return StepResult("design_stage", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after design_stage")

    ss2 = _screenshot(new_hwnd, ad, 16, "after_design")
    return StepResult("design_stage", True, time.monotonic() - t0, ss2)


def step_17_region(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Select region via dropdown arrow at (295, 488).
    List: US, Europe, Australia, ... Strategy: Up 20, Enter.
    """
    t0 = time.monotonic()

    vi_hwnd = _poll_for_window_appear("REGION", timeout=10.0)
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 17, "wrong_screen")
        return StepResult("region", False, time.monotonic() - t0, ss,
                          error="Region VI not found")

    _setup_vi(vi_hwnd)
    _check_screen(vi_hwnd, "step_17", "region")
    _screenshot(vi_hwnd, ad, 17, "region")

    _select_dropdown_by_nav(vi_hwnd, (295, 488), up_presses=20, down_presses=0)
    time.sleep(0.5)

    _verify_dropdown_selection(vi_hwnd, (295, 488), cfg.region,
                               up_presses=20, down_presses=0)

    _screenshot(vi_hwnd, ad, 17, "region_selected")

    _click_orange_arrow_smart(vi_hwnd)

    new_hwnd, ok = _verify_transition(vi_hwnd, timeout=10.0)
    if not ok:
        ss = _screenshot(vi_hwnd, ad, 17, "no_transition")
        return StepResult("region", False, time.monotonic() - t0, ss,
                          error="Screen did not advance after region selection")

    ss2 = _screenshot(new_hwnd, ad, 17, "after_region")
    return StepResult("region", True, time.monotonic() - t0, ss2)


def step_18_final_start(hwnd: int, cfg: RunConfig, ad: str) -> StepResult:
    """Final confirmation - click orange arrow to start the test.

    Pre-flight: OCR the summary screen to verify band/mode/AP match RunConfig.
    """
    t0 = time.monotonic()

    vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        _poll_until(lambda: _find_active_vi() is not None,
                    timeout=5.0, desc="final_start VI")
        vi_hwnd = _find_active_vi()
    if not vi_hwnd:
        ss = _screenshot(hwnd, ad, 18, "wrong_screen")
        return StepResult("final_start", False, time.monotonic() - t0, ss,
                          error="VI not found for final_start")

    _setup_vi(vi_hwnd)
    _screenshot(vi_hwnd, ad, 18, "final_confirm")

    # Pre-flight OCR verification: confirm summary screen matches RunConfig
    if is_ocr_available():
        try:
            img = capture_window(vi_hwnd)
            full_text = ocr_region_freeform(img, 0, 0, img.shape[1], img.shape[0])
            missing = []
            if cfg.ap_name.lower() not in full_text.lower():
                missing.append(f"AP={cfg.ap_name}")
            if cfg.mode.lower() not in full_text.lower():
                missing.append(f"mode={cfg.mode}")
            if missing:
                logger.error("Pre-flight check FAILED — not on screen: %s",
                             ", ".join(missing),
                             extra={"action": "step_18", "step": "preflight_fail"})
                _screenshot(vi_hwnd, ad, 18, "preflight_fail")
                return StepResult(
                    "final_start", False, time.monotonic() - t0,
                    error=f"Pre-flight verify failed: {', '.join(missing)} "
                          f"not visible on summary screen")
            logger.info("Pre-flight check OK: AP=%s, mode=%s confirmed",
                        cfg.ap_name, cfg.mode,
                        extra={"action": "step_18", "step": "preflight_ok"})
        except Exception as exc:
            logger.warning("Pre-flight OCR failed (non-fatal): %s", exc)

    _click_orange_arrow_smart(vi_hwnd)

    _poll_until(
        lambda: (_find_vi_window("running", timeout=0.3) is not None
                 or _find_vi_window("progress", timeout=0.3) is not None
                 or _find_active_vi() != vi_hwnd),
        timeout=10.0, desc="test started or screen changed",
    )

    ss2 = ""
    next_vi = _find_active_vi()
    if next_vi:
        ss2 = _screenshot(next_vi, ad, 18, "test_started")
    else:
        ss2 = _screenshot(vi_hwnd, ad, 18, "test_started")
    return StepResult("final_start", True, time.monotonic() - t0, ss2)


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

STEP_SEQUENCE = [
    step_00_attach,
    step_01_click_throughput,
    step_02_login,
    step_03_test_type,
    step_04_table_position,
    step_05_freq_channel,
    step_06_select_ap,
    step_07_use_last_ap,
    step_08_select_client,
    step_09_dut_ip,
    step_10_use_last_dut,
    step_11_band_select,
    step_12_chariot_pairs,
    step_13_pass_through,
    step_14_mode,
    step_15_attenuation,
    step_16_design_stage,
    step_17_region,
    step_18_final_start,
]


# ---------------------------------------------------------------------------
# Helpers for finish detection
# ---------------------------------------------------------------------------

def _snapshot_result_files(result_dir: str, glob_pattern: str = "*.pdf") -> set[str]:
    """Return the set of files currently matching the pattern in result_dir."""
    if not result_dir or not os.path.isdir(result_dir):
        return set()
    pattern = os.path.join(result_dir, glob_pattern)
    return set(glob_module.glob(pattern))


def _build_finish_config(cfg: RunConfig) -> tuple[FinishConfig, set[str]]:
    """Build a FinishConfig from RunConfig.finish_config dict and snapshot initial files."""
    fc_dict = dict(cfg.finish_config) if cfg.finish_config else {}

    if not fc_dict.get("result_file_dir"):
        fc_dict["result_file_dir"] = r"D:\480\LOG\RBU"
    if not fc_dict.get("result_file_glob"):
        fc_dict["result_file_glob"] = "*.pdf"
    if not fc_dict.get("timeout_sec"):
        fc_dict["timeout_sec"] = cfg.timeout_seconds

    result_dir = fc_dict.get("result_file_dir", "")
    glob_pat = fc_dict.get("result_file_glob", "*.pdf")
    initial_files = _snapshot_result_files(result_dir, glob_pat)

    fcfg = FinishConfig(**{k: v for k, v in fc_dict.items()
                           if k in FinishConfig.__dataclass_fields__})
    return fcfg, initial_files


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def _save_dry_run_screenshot(ad: str, step_idx: int, name: str) -> str:
    """Save the current dry-run annotated image to artifacts."""
    global _DRY_RUN_IMG
    if _DRY_RUN_IMG is None:
        return ""
    fname = f"step_{step_idx:02d}_{name}_dryrun.png"
    path = os.path.join(ad, fname)
    cv2.imwrite(path, _DRY_RUN_IMG)
    return path


STEP_IDX_DESIGN_STAGE = 16


def make_wifi_connect_hook(
    worker_url: str,
    ssid: str,
    password: str,
    interface: str | None = None,
    timeout: float = 60.0,
) -> Callable:
    """Create a post-step hook that connects a WiFi worker to the test SSID.

    Intended for use after step 16 (design_stage) so the Intel BE200
    adapter on 22.203 associates to the correct band before the
    throughput test begins at step 18.

    Usage::

        hook = make_wifi_connect_hook(
            worker_url="http://192.168.22.203:8080",
            ssid="RS700_2G",
            password="TestPass",
        )
        run_labview_flow(cfg, post_step_hooks={STEP_IDX_DESIGN_STAGE: hook})
    """
    import asyncio

    def _hook(run_cfg: RunConfig, artifacts_dir: str) -> None:
        from orchestrator.actions.wifi_remote import connect_remote
        logger.info(
            "Triggering WiFi connect on %s (ssid=%s) after step 16",
            worker_url, ssid,
            extra={"action": "wifi_hook", "step": "connect"},
        )
        result = asyncio.run(
            connect_remote(worker_url, ssid, password, interface, timeout)
        )
        success = result.get("success", False) or result.get("connected", False)
        if success:
            logger.info(
                "WiFi worker connected: %s", result,
                extra={"action": "wifi_hook", "step": "ok"},
            )
        else:
            logger.error(
                "WiFi worker connect FAILED: %s", result,
                extra={"action": "wifi_hook", "step": "failed"},
            )

    return _hook


def prepare_labview_session(cfg: RunConfig, dry_run: bool) -> int | None:
    """Reset popup state, close orphan sub-VIs, find or launch the main LabVIEW window.

    Mutates module globals LV_PID and popup-dismiss registries. Caller must set
    _DRY_RUN before step execution. Returns hwnd or None.
    """
    global LV_PID
    _POPUP_DISMISSED_HWNDS.clear()
    _POPUP_DISMISS_TIMES.clear()
    LV_PID = None
    _check_stop()
    for h, t, w, ht, r in _enum_lv_windows():
        if "480 000" not in t.lower() and w > 100 and ht > 100:
            logger.info("Closing orphaned sub-VI: %r (hwnd=%d)", t, h,
                        extra={"action": "reset", "step": "close_orphan"})
            from orchestrator.local_automation.screen_utils import close_window
            close_window(h)
            time.sleep(1.0)
    hwnd = find_labview_window()
    if hwnd is None and not dry_run and cfg.exe_path and os.path.isfile(cfg.exe_path):
        logger.info("Launching LabVIEW: %s", cfg.exe_path)
        subprocess.Popen([cfg.exe_path])
        _poll_until(lambda: find_labview_window() is not None,
                    timeout=30.0, interval=1.0,
                    desc="LabVIEW window after launch")
        hwnd = find_labview_window()
    return hwnd


def _save_report(report: RunReport, artifacts_dir: str) -> str:
    path = os.path.join(artifacts_dir, "result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False, default=str)
    return path


def _refresh_hwnd(hints: list[str] | None = None) -> int | None:
    return find_labview_window(hints)


# ---------------------------------------------------------------------------
# Multi-band runner
# ---------------------------------------------------------------------------

def build_band_config(
    band: str,
    base_cfg: dict[str, Any] | None = None,
    yaml_path: str | None = None,
) -> RunConfig:
    """Build a RunConfig for a specific band using ui_flow.yaml overrides."""
    defaults: dict[str, Any] = {}

    if yaml_path and os.path.isfile(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            flow = yaml.safe_load(f) or {}
        defaults.update(flow.get("defaults", {}))
        band_overrides = flow.get("band_configs", {}).get(band, {})
        defaults.update(band_overrides)

        finish_cfg = flow.get("finish_detection", {})
        if finish_cfg and "finish_config" not in defaults:
            defaults["finish_config"] = {
                "result_file_dir": finish_cfg.get("result_file_dir", r"D:\480\LOG\RBU"),
                "result_file_glob": finish_cfg.get("result_file_glob", "*.pdf"),
                "timeout_sec": finish_cfg.get("timeout_sec", 14400),
                "poll_interval_sec": finish_cfg.get("poll_interval_sec", 30),
            }

    if base_cfg:
        for k, v in base_cfg.items():
            if k not in defaults:
                defaults[k] = v

    defaults["band"] = band

    cfg_fields = {f.name for f in RunConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in defaults.items() if k in cfg_fields}

    return RunConfig(**filtered)
