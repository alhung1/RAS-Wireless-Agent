"""Diagnostic: verify orange arrow click coordinates and test Win32 SendMessage click."""
import ctypes
import ctypes.wintypes
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from orchestrator.local_automation.screen_utils import (
    get_window_rect, capture_window, save_screenshot,
)
import cv2
import numpy as np

user32 = ctypes.windll.user32

# Constants
ORANGE_ARROW_PX = (1184, 939)
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
WINDOW_WIDTH = 1288
WINDOW_HEIGHT = 1040

os.makedirs("artifacts/diag_click", exist_ok=True)


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


def check_dpi():
    """Check DPI awareness and scaling."""
    try:
        awareness = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
        names = {0: "DPI_UNAWARE", 1: "SYSTEM_DPI_AWARE", 2: "PER_MONITOR_DPI_AWARE"}
        print(f"DPI Awareness: {names.get(awareness.value, awareness.value)}")
    except Exception as e:
        print(f"Could not get DPI awareness: {e}")

    try:
        dpi = user32.GetDpiForSystem()
        print(f"System DPI: {dpi} (scaling = {dpi/96*100:.0f}%)")
    except Exception as e:
        print(f"Could not get system DPI: {e}")


def get_client_offset(hwnd):
    """Get the offset from window rect to client area."""
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pt = POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    wr = get_window_rect(hwnd)
    offset_x = pt.x - wr[0]
    offset_y = pt.y - wr[1]
    
    cr = ctypes.wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    client_w = cr.right - cr.left
    client_h = cr.bottom - cr.top
    
    return offset_x, offset_y, client_w, client_h


def win32_click(hwnd, win_x, win_y, label=""):
    """Send click via Win32 PostMessage using client coordinates."""
    wr = get_window_rect(hwnd)
    screen_x = wr[0] + win_x
    screen_y = wr[1] + win_y

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pt = POINT(screen_x, screen_y)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    client_x = pt.x
    client_y = pt.y

    lparam = (client_y << 16) | (client_x & 0xFFFF)
    print(f"  Win32 click {label}: win({win_x},{win_y}) -> screen({screen_x},{screen_y}) -> client({client_x},{client_y})")

    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
    return client_x, client_y


def annotate_and_save(hwnd, filename, targets):
    """Capture window, draw red circles at targets, save."""
    try:
        img = capture_window(hwnd)
        wr = get_window_rect(hwnd)
        ox, oy, cw, ch = get_client_offset(hwnd)
        
        for (wx, wy, label) in targets:
            cx = wx - ox
            cy = wy - oy
            cv2.circle(img, (wx, wy), 15, (0, 0, 255), 3)
            cv2.putText(img, f"{label} win({wx},{wy})", (wx - 80, wy - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.circle(img, (cx + ox, cy + oy), 8, (0, 255, 0), 2)
        
        path = f"artifacts/diag_click/{filename}"
        cv2.imwrite(path, img)
        print(f"  Saved: {path} ({img.shape[1]}x{img.shape[0]})")
        return img
    except Exception as e:
        print(f"  Screenshot failed: {e}")
        return None


def main():
    print("=== DPI/Scaling Check ===")
    check_dpi()

    print("\n=== LabVIEW Windows ===")
    wins = _enum_lv_windows()
    for h, t, w, ht, r in wins:
        print(f"  hwnd={h} title={t!r} size={w}x{ht} rect={r}")

    sub_vi = None
    for h, t, w, ht, r in wins:
        if "400 600" in t.lower():
            sub_vi = (h, t)
            break

    if not sub_vi:
        print("\nNo '400 600 test' sub-VI found. Looking for any VI with arrows...")
        for h, t, w, ht, r in wins:
            if ".vi" in t.lower() and "480" not in t:
                sub_vi = (h, t)
                break

    if not sub_vi:
        print("No suitable LabVIEW sub-VI window found.")
        print("Available windows:")
        for h, t, w, ht, r in wins:
            print(f"  {h}: {t!r}")
        return

    hwnd, title = sub_vi
    print(f"\n=== Target Window: {title!r} (hwnd={hwnd}) ===")

    wr = get_window_rect(hwnd)
    print(f"  Window rect: {wr}")
    print(f"  Window size: {wr[2]-wr[0]}x{wr[3]-wr[1]}")

    ox, oy, cw, ch = get_client_offset(hwnd)
    print(f"  Client offset: ({ox}, {oy})")
    print(f"  Client size: {cw}x{ch}")

    ax = ORANGE_ARROW_PX[0]
    ay = ORANGE_ARROW_PX[1]
    print(f"\n  ORANGE_ARROW_PX = ({ax}, {ay}) [window-relative]")
    print(f"  Absolute screen pos = ({wr[0]+ax}, {wr[1]+ay})")
    print(f"  Client coords = ({ax - ox}, {ay - oy})")

    if ax - ox > cw or ay - oy > ch:
        print(f"  *** WARNING: Click position ({ax-ox}, {ay-oy}) is OUTSIDE client area ({cw}x{ch})! ***")

    print(f"\n=== Screenshot with annotation ===")
    annotate_and_save(hwnd, "before_click.png",
                      [(ax, ay, "arrow")])

    print(f"\n=== Testing Win32 SendMessage click at orange arrow ===")
    win32_click(hwnd, ax, ay, label="orange_arrow")
    time.sleep(1.0)

    annotate_and_save(hwnd, "after_win32_click.png",
                      [(ax, ay, "arrow")])

    print("\nDone. Check artifacts/diag_click/ for screenshots.")


if __name__ == "__main__":
    main()
