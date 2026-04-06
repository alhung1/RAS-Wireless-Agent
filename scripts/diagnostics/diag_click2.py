"""Diagnostic 2: Try resizing, check if it sticks, then find orange arrow."""
import ctypes
import ctypes.wintypes
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from orchestrator.local_automation.screen_utils import (
    get_window_rect, set_window_rect, capture_window, save_screenshot,
    _set_foreground,
)
import cv2
import numpy as np

user32 = ctypes.windll.user32

WINDOW_WIDTH = 1288
WINDOW_HEIGHT = 1040

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

os.makedirs("artifacts/diag_click2", exist_ok=True)


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


def get_client_offset(hwnd):
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    wr = get_window_rect(hwnd)
    return pt.x - wr[0], pt.y - wr[1]


def win32_click(hwnd, client_x, client_y, label=""):
    """Send click directly in client coordinates."""
    if client_x < 0 or client_y < 0:
        print(f"  SKIP: negative client coords ({client_x},{client_y})")
        return
    lparam = (client_y << 16) | (client_x & 0xFFFF)
    print(f"  Win32 click {label} at client({client_x},{client_y})")
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


def main():
    wins = _enum_lv_windows()
    print("=== LabVIEW Windows ===")
    for h, t, w, ht, r in wins:
        print(f"  hwnd={h} {t!r} size={w}x{ht} rect={r}")

    sub_vi = None
    for h, t, w, ht, r in wins:
        if "400 600" in t.lower():
            sub_vi = h
            break

    if not sub_vi:
        print("No sub-VI found!")
        return

    hwnd = sub_vi
    print(f"\nTarget: hwnd={hwnd}")

    # Step 1: Show current state
    wr = get_window_rect(hwnd)
    print(f"  Before resize: rect={wr} size={wr[2]-wr[0]}x{wr[3]-wr[1]}")

    try:
        img = capture_window(hwnd)
        cv2.imwrite("artifacts/diag_click2/1_before_resize.png", img)
        print(f"  Screenshot: {img.shape[1]}x{img.shape[0]}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")

    # Step 2: Resize
    print(f"\n  Calling set_window_rect(hwnd, 0, 0, {WINDOW_WIDTH}, {WINDOW_HEIGHT})...")
    set_window_rect(hwnd, 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
    time.sleep(1.0)

    wr2 = get_window_rect(hwnd)
    print(f"  After resize: rect={wr2} size={wr2[2]-wr2[0]}x{wr2[3]-wr2[1]}")

    if wr2[2] - wr2[0] != WINDOW_WIDTH or wr2[3] - wr2[1] != WINDOW_HEIGHT:
        print(f"  *** RESIZE FAILED! Expected {WINDOW_WIDTH}x{WINDOW_HEIGHT}, got {wr2[2]-wr2[0]}x{wr2[3]-wr2[1]} ***")
        # Try with SWP_FRAMECHANGED
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        user32.SetWindowPos(hwnd, 0, 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT, SWP_NOZORDER | SWP_FRAMECHANGED)
        time.sleep(1.0)
        wr3 = get_window_rect(hwnd)
        print(f"  After retry with FRAMECHANGED: size={wr3[2]-wr3[0]}x{wr3[3]-wr3[1]}")

        # Check window style for WS_THICKFRAME (resizable)
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        WS_THICKFRAME = 0x00040000
        WS_MAXIMIZEBOX = 0x00010000
        WS_MINIMIZEBOX = 0x00020000
        WS_SIZEBOX = WS_THICKFRAME
        print(f"  Window style: 0x{style:08X}")
        print(f"    Has WS_THICKFRAME (resizable): {bool(style & WS_THICKFRAME)}")
        print(f"    Has WS_MAXIMIZEBOX: {bool(style & WS_MAXIMIZEBOX)}")
        print(f"    Has WS_MINIMIZEBOX: {bool(style & WS_MINIMIZEBOX)}")

    try:
        img2 = capture_window(hwnd)
        cv2.imwrite("artifacts/diag_click2/2_after_resize.png", img2)
        print(f"  Screenshot after resize: {img2.shape[1]}x{img2.shape[0]}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")

    # Step 3: Find actual arrow position based on current window size
    actual_w = wr2[2] - wr2[0]
    actual_h = wr2[3] - wr2[1]
    ox, oy = get_client_offset(hwnd)
    print(f"\n  Client offset: ({ox}, {oy})")

    # Calculate where arrow should be based on the LabVIEW VI layout
    # The arrow is in the bottom-right corner of the client area
    # From the earlier screenshot at 1030x832:
    #   orange arrow visible at ~(945, 755) in window coords
    #   That's about (85 from right edge, 77 from bottom edge)
    # But this is window coords, not client coords

    # Let's try: find template in the captured image
    try:
        import orchestrator.local_automation.screen_utils as su
        img_cap = capture_window(hwnd)
        center = su.find_template_center(img_cap, "orange_arrow.png", 0.5)
        if center:
            print(f"\n  Template match found at: ({center[0]}, {center[1]})")
        else:
            print(f"\n  Template match NOT found at threshold 0.5")

            # Try lower threshold
            center2 = su.find_template_center(img_cap, "orange_arrow.png", 0.3)
            if center2:
                print(f"  Template match found at threshold 0.3: ({center2[0]}, {center2[1]})")
            else:
                print(f"  Template match NOT found even at threshold 0.3")
    except Exception as e:
        print(f"  Template matching error: {e}")

    # Step 4: Calculate coordinates based on actual window and try clicking
    # Hardcoded offset from bottom-right of window (approximate)
    arrow_from_right = 85
    arrow_from_bottom = 85
    calc_x = actual_w - arrow_from_right
    calc_y = actual_h - arrow_from_bottom
    print(f"\n  Calculated arrow position (from bottom-right offset): ({calc_x}, {calc_y})")

    # Draw both the old and calculated positions
    try:
        img3 = capture_window(hwnd)
        # Old position (will be off-screen if window is small)
        old_x, old_y = 1184, 939
        if old_x < img3.shape[1] and old_y < img3.shape[0]:
            cv2.circle(img3, (old_x, old_y), 15, (0, 0, 255), 3)
            cv2.putText(img3, "OLD", (old_x - 30, old_y - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        # New calculated position
        if calc_x < img3.shape[1] and calc_y < img3.shape[0]:
            cv2.circle(img3, (calc_x, calc_y), 15, (0, 255, 0), 3)
            cv2.putText(img3, "CALC", (calc_x - 30, calc_y - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imwrite("artifacts/diag_click2/3_annotated.png", img3)
        print(f"  Saved annotated screenshot")
    except Exception as e:
        print(f"  Annotation failed: {e}")

    # Step 5: Try Win32 click at calculated position
    print(f"\n=== Attempting Win32 click at calculated position ===")
    _set_foreground(hwnd)
    time.sleep(0.3)

    # Convert window coords to client coords
    client_x = calc_x - ox
    client_y = calc_y - oy
    print(f"  Client coords: ({client_x}, {client_y})")

    # Save before
    try:
        before = capture_window(hwnd)
    except:
        before = None

    win32_click(hwnd, client_x, client_y, label="orange_arrow_calc")
    time.sleep(2.0)

    # Save after
    try:
        after = capture_window(hwnd)
        cv2.imwrite("artifacts/diag_click2/4_after_click.png", after)
        print(f"  Saved after-click screenshot")

        # Check if anything changed
        if before is not None and before.shape == after.shape:
            diff = cv2.absdiff(before, after)
            changed = np.count_nonzero(diff)
            total = diff.size
            pct = changed / total * 100
            print(f"  Pixel change: {pct:.2f}% ({changed}/{total})")
            if pct > 0.1:
                print(f"  >>> Screen CHANGED after click!")
            else:
                print(f"  >>> Screen did NOT change after click")
    except Exception as e:
        print(f"  After-click capture failed: {e}")

    print("\nDone. Check artifacts/diag_click2/")


if __name__ == "__main__":
    main()
