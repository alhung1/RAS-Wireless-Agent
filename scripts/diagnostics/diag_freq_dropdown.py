"""Diagnostic: capture the freq_channel screen and print window dimensions.

Finds the 481.300 VI (or falls back to the active VI), resizes it,
captures a screenshot, and prints key measurements so we can calibrate
the Freq Range dropdown coordinate.
"""
import sys, os, time, ctypes
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ctypes import wintypes
from orchestrator.local_automation.screen_utils import (
    get_window_rect, set_window_rect, capture_window, save_screenshot,
)

user32 = ctypes.windll.user32
WINDOW_WIDTH = 1288
WINDOW_HEIGHT = 1040

def enum_lv_windows():
    results = []
    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        if not title:
            return True
        hints = ["480", "481", "400 600", "RvR", "logon", "table", "freq", "channel"]
        if any(h.lower() in title.lower() for h in hints):
            r = get_window_rect(hwnd)
            w = r[2] - r[0]
            h = r[3] - r[1]
            if w > 10 and h > 10:
                results.append((hwnd, title, w, h, r))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return results

def main():
    wins = enum_lv_windows()
    print("All LabVIEW windows:")
    for hwnd, title, w, h, r in wins:
        print(f"  hwnd={hwnd}  {w}x{h}  rect={r}  title={title!r}")

    target = None
    for hwnd, title, w, h, r in wins:
        if "481.300" in title or "freq" in title.lower():
            target = hwnd
            break

    if not target:
        for hwnd, title, w, h, r in wins:
            if "480 000" not in title.lower() and w > 200 and h > 200:
                target = hwnd
                break

    if not target:
        print("ERROR: No suitable LabVIEW VI window found")
        return

    print(f"\nTarget window: hwnd={target}")
    print(f"  title = {ctypes.create_unicode_buffer(256).value}")
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(target, buf, 256)
    print(f"  title = {buf.value!r}")

    rect_before = get_window_rect(target)
    print(f"  rect BEFORE resize: {rect_before}")
    print(f"  size BEFORE: {rect_before[2]-rect_before[0]}x{rect_before[3]-rect_before[1]}")

    set_window_rect(target, 0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
    time.sleep(0.5)

    rect_after = get_window_rect(target)
    w_after = rect_after[2] - rect_after[0]
    h_after = rect_after[3] - rect_after[1]
    print(f"  rect AFTER resize: {rect_after}")
    print(f"  size AFTER: {w_after}x{h_after}")

    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    my_tid = kernel32.GetCurrentThreadId()
    if fg_tid != my_tid:
        user32.AttachThreadInput(my_tid, fg_tid, True)
    user32.ShowWindow(target, 9)
    user32.BringWindowToTop(target)
    user32.SetForegroundWindow(target)
    if fg_tid != my_tid:
        user32.AttachThreadInput(my_tid, fg_tid, False)
    time.sleep(0.3)

    os.makedirs("artifacts", exist_ok=True)
    img = capture_window(target)
    path = save_screenshot(img, "artifacts", "diag_freq_dropdown.png")
    print(f"\nScreenshot saved: {path}")
    print(f"  Image shape: {img.shape}  (height x width x channels)")
    print(f"  Image size: {img.shape[1]}x{img.shape[0]} pixels")
    print()
    print("COORDINATE MAPPING:")
    print(f"  Window logical size: {w_after}x{h_after}")
    print(f"  Screenshot pixel size: {img.shape[1]}x{img.shape[0]}")
    if w_after > 0:
        ratio_x = img.shape[1] / w_after
        ratio_y = img.shape[0] / h_after
        print(f"  Pixel/Logical ratio: x={ratio_x:.3f}  y={ratio_y:.3f}")
        print()
        print("To convert screenshot pixel -> code coordinate:")
        print(f"  code_x = screenshot_x / {ratio_x:.3f}")
        print(f"  code_y = screenshot_y / {ratio_y:.3f}")

if __name__ == "__main__":
    main()
