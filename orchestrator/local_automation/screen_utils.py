"""Screen capture, template matching, and relative-coordinate clicking.

All mouse/keyboard actions work on a **specific window** identified by its
handle.  Coordinates are always relative to the window's client area so
that changes in window position don't break the automation.
"""
from __future__ import annotations

import ctypes
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import ImageGrab

from orchestrator.logging.json_logger import get_logger

logger = get_logger("screen_utils")

TEMPLATES_DIR = Path(__file__).parent / "templates"

try:
    import pytesseract
    pytesseract.get_tesseract_version()
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.warning("pytesseract not installed — OCR verification disabled")
except Exception:
    _OCR_AVAILABLE = False
    logger.warning("Tesseract binary not found on PATH — OCR verification disabled")


# ---------------------------------------------------------------------------
# Win32 helpers
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32

SW_RESTORE = 9
SW_MINIMIZE = 6
WM_CLOSE = 0x0010
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                 ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _set_foreground(hwnd: int) -> None:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.3)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def minimize_window(hwnd: int) -> None:
    """Minimize (iconify) a window to get it out of the way."""
    user32.ShowWindow(hwnd, SW_MINIMIZE)


def close_window(hwnd: int) -> None:
    """Send WM_CLOSE to a window."""
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def set_window_rect(hwnd: int, left: int, top: int, width: int, height: int) -> None:
    """Move and resize the window to exact pixel dimensions."""
    SWP_NOZORDER = 0x0004
    user32.SetWindowPos(hwnd, 0, left, top, width, height, SWP_NOZORDER)
    time.sleep(0.3)


def ensure_window_size(hwnd: int, width: int = 1260, height: int = 690) -> None:
    """Ensure the window is at the target size. Repositions to (0,0)."""
    left, top, right, bottom = get_window_rect(hwnd)
    cur_w = right - left
    cur_h = bottom - top
    if cur_w != width or cur_h != height:
        logger.info(
            "Resizing window from %dx%d to %dx%d",
            cur_w, cur_h, width, height,
            extra={"action": "ensure_window_size", "step": "resize"},
        )
        set_window_rect(hwnd, 0, 0, width, height)
    _set_foreground(hwnd)


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def capture_window(hwnd: int) -> np.ndarray:
    """Capture a screenshot of the window region as a BGR numpy array."""
    _set_foreground(hwnd)
    time.sleep(0.3)
    left, top, right, bottom = get_window_rect(hwnd)
    w = right - left
    h = bottom - top
    if w <= 0 or h <= 0:
        raise RuntimeError(
            f"Window hwnd={hwnd} has zero or negative size ({w}x{h})"
        )
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    arr = np.array(img)
    if arr.size == 0:
        raise RuntimeError("ImageGrab returned empty image")
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def save_screenshot(img: np.ndarray, artifacts_dir: str, name: str) -> str:
    os.makedirs(artifacts_dir, exist_ok=True)
    path = os.path.join(artifacts_dir, name)
    cv2.imwrite(path, img)
    return path


# ---------------------------------------------------------------------------
# Template matching
# ---------------------------------------------------------------------------

def load_template(name: str) -> Optional[np.ndarray]:
    path = TEMPLATES_DIR / name
    if not path.is_file():
        logger.warning("Template not found: %s", path)
        return None
    return cv2.imread(str(path), cv2.IMREAD_COLOR)


def find_template(
    screen: np.ndarray,
    template: np.ndarray,
    threshold: float = 0.80,
) -> Optional[tuple[int, int, int, int]]:
    """Find *template* in *screen*.  Returns (x, y, w, h) of the best
    match or None if below *threshold*.  Coordinates are relative to
    *screen* (i.e. the window's top-left corner).
    """
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < threshold:
        return None
    h, w = template.shape[:2]
    return (max_loc[0], max_loc[1], w, h)


def find_template_center(
    screen: np.ndarray,
    template_name: str,
    threshold: float = 0.80,
) -> Optional[tuple[int, int]]:
    """Return the center (x, y) of *template_name* in *screen*, or None."""
    tpl = load_template(template_name)
    if tpl is None:
        return None
    match = find_template(screen, tpl, threshold)
    if match is None:
        return None
    x, y, w, h = match
    return (x + w // 2, y + h // 2)


def screen_contains(
    screen: np.ndarray,
    template_name: str,
    threshold: float = 0.80,
) -> bool:
    return find_template_center(screen, template_name, threshold) is not None


# ---------------------------------------------------------------------------
# Mouse / Keyboard actions (all relative to window)
# ---------------------------------------------------------------------------

def click_absolute(x: int, y: int, delay: float = 0.1) -> None:
    """Click at absolute screen coordinates using pyautogui."""
    import pyautogui
    pyautogui.click(x, y)
    time.sleep(delay)


_target_window_size: tuple[int, int] | None = None


def set_target_window_size(width: int, height: int) -> None:
    """Set the target window size that click_relative will enforce."""
    global _target_window_size
    _target_window_size = (width, height)


def click_relative(hwnd: int, rx: float, ry: float, delay: float = 0.15) -> None:
    """Click at a position relative to the window (0.0-1.0 fractions)."""
    if _target_window_size:
        ensure_window_size(hwnd, *_target_window_size)
    else:
        _set_foreground(hwnd)
    left, top, right, bottom = get_window_rect(hwnd)
    w = right - left
    h = bottom - top
    ax = left + int(w * rx)
    ay = top + int(h * ry)
    logger.info("click_relative: rx=%.3f ry=%.3f -> abs(%d,%d) win(%d,%d,%d,%d)",
                rx, ry, ax, ay, left, top, w, h,
                extra={"action": "click_relative", "step": "exec"})
    click_absolute(ax, ay, delay)


def click_template(
    hwnd: int,
    screen: np.ndarray,
    template_name: str,
    threshold: float = 0.80,
    delay: float = 0.15,
) -> bool:
    """Find *template_name* on *screen* and click its center.  Returns True
    if the template was found and clicked.
    """
    center = find_template_center(screen, template_name, threshold)
    if center is None:
        logger.warning("Template %r not found on screen", template_name)
        return False
    left, top, _, _ = get_window_rect(hwnd)
    click_absolute(left + center[0], top + center[1], delay)
    return True


def _set_clipboard(text: str) -> None:
    """Set the Windows clipboard to *text*."""
    import win32clipboard
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def type_via_clipboard(text: str) -> None:
    """Set clipboard to *text* then paste with Ctrl+V. Most reliable for
    LabVIEW fields which may not respond to synthetic keystrokes.
    """
    _set_clipboard(text)
    time.sleep(0.1)

    VK_CONTROL = 0x11
    VK_V = 0x56
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, 0x0002, 0)
    user32.keybd_event(VK_CONTROL, 0, 0x0002, 0)
    time.sleep(0.15)


def type_text(text: str, interval: float = 0.05) -> None:
    """Type *text* using pyautogui which works reliably with LabVIEW."""
    import pyautogui
    pyautogui.typewrite(text, interval=interval)


def type_text_special(text: str, interval: float = 0.05) -> None:
    """Type *text* that may contain special chars using pyautogui.write."""
    import pyautogui
    for ch in text:
        pyautogui.press(ch) if len(ch) > 1 else pyautogui.write(ch)
        time.sleep(interval)


def send_keys_raw(text: str) -> None:
    """Use pywinauto keyboard module for key sending."""
    from pywinauto.keyboard import send_keys
    send_keys(text, pause=0.05)


def press_key(vk_code: int) -> None:
    """Press and release a virtual key."""
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk_code, 0, 0x0002, 0)  # KEYEVENTF_KEYUP
    time.sleep(0.05)


def select_all_and_type(hwnd: int, rx: float, ry: float, text: str,
                        use_clipboard: bool = False) -> None:
    """Click a field, select all (Ctrl+A), then type new text.
    Uses pyautogui for LabVIEW compatibility.
    """
    import pyautogui
    if _target_window_size:
        ensure_window_size(hwnd, *_target_window_size)
    else:
        _set_foreground(hwnd)
    left, top, right, bottom = get_window_rect(hwnd)
    ax = left + int((right - left) * rx)
    ay = top + int((bottom - top) * ry)
    pyautogui.click(ax, ay)
    time.sleep(0.2)
    pyautogui.click(ax, ay)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    if use_clipboard:
        type_via_clipboard(text)
    else:
        pyautogui.typewrite(text, interval=0.05)
    time.sleep(0.1)


def triple_click_and_type(hwnd: int, rx: float, ry: float, text: str) -> None:
    """Triple-click a field (select all) then type new text.
    Delegates to select_all_and_type for a more reliable approach."""
    select_all_and_type(hwnd, rx, ry, text, use_clipboard=True)


# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------

def is_ocr_available() -> bool:
    return _OCR_AVAILABLE


def ocr_region(
    img: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    preprocess: bool = True,
) -> str:
    """Extract text from a rectangular region of a BGR image via Tesseract.

    Returns empty string if pytesseract is not installed or OCR fails.
    *preprocess* converts to grayscale + Otsu threshold for cleaner reads
    on LabVIEW's high-contrast controls.
    """
    if not _OCR_AVAILABLE:
        return ""

    x = max(x, 0)
    y = max(y, 0)
    x2 = min(x + w, img.shape[1])
    y2 = min(y + h, img.shape[0])
    if x2 <= x or y2 <= y:
        return ""

    region = img[y:y2, x:x2]
    if region.size == 0:
        return ""

    if preprocess:
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, region = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    try:
        text = pytesseract.image_to_string(
            region, config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ._-/()"
        ).strip()
        return text
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        return ""


def ocr_region_freeform(
    img: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
) -> str:
    """OCR a region with PSM 6 (block of text) for multi-line list content."""
    if not _OCR_AVAILABLE:
        return ""

    x = max(x, 0)
    y = max(y, 0)
    x2 = min(x + w, img.shape[1])
    y2 = min(y + h, img.shape[0])
    if x2 <= x or y2 <= y:
        return ""

    region = img[y:y2, x:x2]
    if region.size == 0:
        return ""

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    try:
        text = pytesseract.image_to_string(thresh, config="--psm 6").strip()
        return text
    except Exception as exc:
        logger.warning("OCR freeform failed: %s", exc)
        return ""
