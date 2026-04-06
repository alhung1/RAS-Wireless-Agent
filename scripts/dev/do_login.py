"""Login to LabVIEW application using pyautogui."""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.1

from orchestrator.local_automation.screen_utils import (
    capture_window, save_screenshot, get_window_rect,
)

ARTS = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')),
    'artifacts',
    'labview_calibration',
)
os.makedirs(ARTS, exist_ok=True)

user32 = ctypes.windll.user32


def find_lv_windows():
    """Find LabVIEW windows by process."""
    wins = {}
    def _cb(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        vis = user32.IsWindowVisible(hwnd)
        if vis and title:
            if "480" in title or "logon" in title.lower() or "password" in title.lower():
                wins[title] = hwnd
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return wins


def dismiss_dialogs(pid: int):
    """Find and dismiss any small LabVIEW dialog windows."""
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
            pyautogui.click(r[0] + 50, r[1] + h - 30)
            time.sleep(0.5)
            dismissed += 1
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return dismissed


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="Alex")
    parser.add_argument("--password", default="123")
    args = parser.parse_args()

    wins = find_lv_windows()
    print(f"Found windows: {list(wins.keys())}")

    login_title = None
    login_hwnd = None
    for title, hwnd in wins.items():
        if "password" in title.lower() or "logon" in title.lower():
            login_title = title
            login_hwnd = hwnd
            break

    frame_hwnd = None
    for title, hwnd in wins.items():
        if "480.000" in title:
            frame_hwnd = hwnd

    if not login_hwnd:
        print("Login window not found!")
        return False

    # Get PID for dialog dismissal
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(login_hwnd, ctypes.byref(pid))

    # Dismiss any existing error dialogs
    d = dismiss_dialogs(pid.value)
    if d:
        print(f"Dismissed {d} dialog(s)")
        time.sleep(0.5)

    # Focus the frame window
    if frame_hwnd:
        user32.SetForegroundWindow(frame_hwnd)
        time.sleep(0.5)

    # Get login window position
    rect = get_window_rect(login_hwnd)
    left, top, right, bottom = rect
    lw = right - left
    lh = bottom - top
    print(f"Login window: ({left},{top}) {lw}x{lh}")

    if lw < 50 or lh < 50:
        print("Login window too small, skipping")
        return False

    # Calculate field positions (calibrated from the login window)
    name_x = left + int(lw * 0.612)
    name_y = top + int(lh * 0.375)
    pw_x = left + int(lw * 0.612)
    pw_y = top + int(lh * 0.645)

    # Type in Name field
    print(f"Clicking Name at ({name_x},{name_y})")
    pyautogui.click(name_x, name_y)
    time.sleep(0.3)
    pyautogui.click(name_x, name_y)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    pyautogui.typewrite(args.username, interval=0.05)
    time.sleep(0.5)

    # Capture after name
    try:
        img = capture_window(login_hwnd)
        save_screenshot(img, ARTS, "login_after_name.png")
    except:
        pass

    # Type in Password field
    print(f"Clicking Password at ({pw_x},{pw_y})")
    pyautogui.click(pw_x, pw_y)
    time.sleep(0.3)
    pyautogui.click(pw_x, pw_y)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    pyautogui.typewrite(args.password, interval=0.05)
    time.sleep(0.5)

    # Capture after password
    try:
        img = capture_window(login_hwnd)
        save_screenshot(img, ARTS, "login_after_password.png")
    except:
        pass

    # Click green arrow (bottom-right of login form)
    arrow_x = left + int(lw * 0.75)
    arrow_y = top + int(lh * 0.88)
    print(f"Clicking green arrow at ({arrow_x},{arrow_y})")
    pyautogui.click(arrow_x, arrow_y)
    time.sleep(3.0)

    # Check result - look for the login window still existing
    still_visible = user32.IsWindowVisible(login_hwnd)
    print(f"Login window still visible: {still_visible}")
    if not still_visible:
        print("LOGIN SUCCESS!")
        return True

    # Check for error dialog
    d = dismiss_dialogs(pid.value)
    if d:
        print(f"Login failed - dismissed {d} error dialog(s)")
        return False

    print("Login result unclear")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
