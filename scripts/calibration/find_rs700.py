"""Navigate the AP listbox backwards from WAC740 to find RS700."""
import sys, os, ctypes, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from orchestrator.local_automation.screen_utils import (
    get_window_rect, set_window_rect, capture_window, save_screenshot
)
from PIL import ImageGrab
import numpy as np, cv2

u = ctypes.windll.user32
k = ctypes.windll.kernel32

MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002

screen_w = u.GetSystemMetrics(0)
screen_h = u.GetSystemMetrics(1)


def raw_click(sx, sy, clicks=1):
    ax = int(sx * 65535 / screen_w)
    ay = int(sy * 65535 / screen_h)
    u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE, ax, ay, 0, 0)
    time.sleep(0.15)
    for _ in range(clicks):
        u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.08)


def raw_key(vk):
    scan = u.MapVirtualKeyW(vk, 0)
    u.keybd_event(vk, scan, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)


popup_hwnd = 140398
tid = u.GetWindowThreadProcessId(popup_hwnd, None)
my_tid = k.GetCurrentThreadId()

print("Attaching thread...")
u.AttachThreadInput(my_tid, tid, True)

try:
    set_window_rect(popup_hwnd, 0, 0, 800, 900)
    time.sleep(0.3)
    u.SetForegroundWindow(popup_hwnd)
    time.sleep(0.3)
    u.SetFocus(popup_hwnd)
    time.sleep(0.5)

    rect = get_window_rect(popup_hwnd)
    left, top = rect[0], rect[1]

    # Click directly on WAC740 text (first visible item, y ~120)
    print("Clicking WAC740...")
    raw_click(left + 100, top + 120, clicks=1)
    time.sleep(0.5)

    # Capture to verify selection
    img = capture_window(popup_hwnd)
    save_screenshot(img, 'artifacts/labview_calibration', 'rs700_start.png')

    # Now press UP arrow to navigate backwards
    VK_UP = 0x26
    print("Pressing UP x60 (should go from WAC to R entries)...")
    for i in range(60):
        raw_key(VK_UP)
        time.sleep(0.08)

        if (i + 1) % 15 == 0:
            time.sleep(0.3)
            img = ImageGrab.grab(bbox=rect)
            arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            fname = 'rs700_up_%03d.png' % (i + 1)
            cv2.imwrite(r'c:\Projects\RAS Wireless Agent\artifacts\labview_calibration\%s' % fname, arr)
            print("  Step %d captured" % (i + 1))

    # Final capture
    img = capture_window(popup_hwnd)
    save_screenshot(img, 'artifacts/labview_calibration', 'rs700_after_up60.png')

finally:
    u.AttachThreadInput(my_tid, tid, False)
    print("Done.")
