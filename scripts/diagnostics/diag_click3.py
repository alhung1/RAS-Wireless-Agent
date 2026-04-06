"""Diagnostic 3: Try pyautogui click after resize, check VI running state."""
import ctypes
import ctypes.wintypes
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from orchestrator.local_automation.screen_utils import (
    get_window_rect, set_window_rect, capture_window, _set_foreground,
)
import cv2
import numpy as np
import pyautogui

user32 = ctypes.windll.user32
WINDOW_WIDTH = 1288
WINDOW_HEIGHT = 1040
ORANGE_ARROW_PX = (1184, 939)

os.makedirs("artifacts/diag_click3", exist_ok=True)


def _enum_lv_windows():
    results = []
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        if not title:
            return True
        title_l = title.lower()
        if any(k in title_l for k in ["480", "400 600", "test", ".vi"]):
            r = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w = r.right - r.left
            h = r.bottom - r.top
            results.append((hwnd, title, w, h, (r.left, r.top, r.right, r.bottom)))
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))(cb), 0)
    return results


def _force_fg(hwnd):
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


def main():
    wins = _enum_lv_windows()
    sub_vi = None
    for h, t, w, ht, r in wins:
        if "400 600" in t.lower():
            sub_vi = h
            break
    if not sub_vi:
        print("No sub-VI found")
        return

    hwnd = sub_vi
    print(f"Found sub-VI: hwnd={hwnd}")

    # Ensure resized
    set_window_rect(hwnd, 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
    time.sleep(0.5)
    wr = get_window_rect(hwnd)
    print(f"Window size: {wr[2]-wr[0]}x{wr[3]-wr[1]}")

    # Capture before
    _force_fg(hwnd)
    time.sleep(0.3)
    before = capture_window(hwnd)
    cv2.imwrite("artifacts/diag_click3/1_before.png", before)

    # Test 1: pyautogui click at ORANGE_ARROW_PX
    print(f"\n=== Test 1: pyautogui.click at abs ({wr[0]+ORANGE_ARROW_PX[0]}, {wr[1]+ORANGE_ARROW_PX[1]}) ===")
    _force_fg(hwnd)
    time.sleep(0.2)
    ax = wr[0] + ORANGE_ARROW_PX[0]
    ay = wr[1] + ORANGE_ARROW_PX[1]
    print(f"  Clicking at abs ({ax}, {ay})...")
    pyautogui.click(ax, ay)
    time.sleep(2.0)

    after1 = capture_window(hwnd)
    cv2.imwrite("artifacts/diag_click3/2_after_pyautogui.png", after1)
    diff1 = cv2.absdiff(before, after1)
    pct1 = np.count_nonzero(diff1) / diff1.size * 100
    print(f"  Pixel change: {pct1:.2f}%")
    if pct1 > 0.1:
        print(f"  >>> pyautogui click WORKED!")
    else:
        print(f"  >>> pyautogui click had no effect")

    # Test 2: pyautogui double-click
    if pct1 < 0.1:
        print(f"\n=== Test 2: pyautogui double-click ===")
        _force_fg(hwnd)
        time.sleep(0.2)
        pyautogui.doubleClick(ax, ay)
        time.sleep(2.0)
        after2 = capture_window(hwnd)
        cv2.imwrite("artifacts/diag_click3/3_after_dblclick.png", after2)
        diff2 = cv2.absdiff(before, after2)
        pct2 = np.count_nonzero(diff2) / diff2.size * 100
        print(f"  Pixel change: {pct2:.2f}%")

    # Test 3: Keyboard Tab + Space approach
    print(f"\n=== Test 3: Keyboard - Tab to button, Space to click ===")
    _force_fg(hwnd)
    time.sleep(0.2)

    # First click somewhere neutral to ensure the VI has focus
    neutral_x = wr[0] + 500
    neutral_y = wr[1] + 400
    pyautogui.click(neutral_x, neutral_y)
    time.sleep(0.3)

    # Tab multiple times to reach the forward arrow
    for i in range(20):
        pyautogui.press('tab')
        time.sleep(0.1)
    pyautogui.press('space')
    time.sleep(2.0)

    after3 = capture_window(hwnd)
    cv2.imwrite("artifacts/diag_click3/4_after_tab_space.png", after3)
    diff3 = cv2.absdiff(before, after3)
    pct3 = np.count_nonzero(diff3) / diff3.size * 100
    print(f"  Pixel change: {pct3:.2f}%")
    if pct3 > 0.1:
        print(f"  >>> Tab+Space WORKED!")
    else:
        print(f"  >>> Tab+Space had no effect")

    # Test 4: Check if VI is in run mode by looking at toolbar
    print(f"\n=== VI State Check ===")
    # Crop the toolbar area (top 65 pixels) for analysis
    toolbar = before[0:65, :]
    cv2.imwrite("artifacts/diag_click3/5_toolbar.png", toolbar)
    print(f"  Saved toolbar crop. Check if run button shows 'running' state.")

    # Test 5: Try Ctrl+R (LabVIEW Run) first, then click arrow
    print(f"\n=== Test 5: Ctrl+R to run VI, then click arrow ===")
    _force_fg(hwnd)
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'r')
    time.sleep(2.0)

    before5 = capture_window(hwnd)
    cv2.imwrite("artifacts/diag_click3/6_after_ctrl_r.png", before5)

    _force_fg(hwnd)
    time.sleep(0.2)
    pyautogui.click(ax, ay)
    time.sleep(2.0)

    after5 = capture_window(hwnd)
    cv2.imwrite("artifacts/diag_click3/7_after_ctrl_r_click.png", after5)
    diff5 = cv2.absdiff(before5, after5)
    pct5 = np.count_nonzero(diff5) / diff5.size * 100
    print(f"  Pixel change after Ctrl+R then click: {pct5:.2f}%")
    if pct5 > 0.1:
        print(f"  >>> Ctrl+R + click WORKED!")
    else:
        print(f"  >>> Ctrl+R + click had no effect")

    print(f"\nDone. Check artifacts/diag_click3/")


if __name__ == "__main__":
    main()
