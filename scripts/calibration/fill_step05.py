"""Fill step 05 fields using raw mouse_event/keybd_event."""
import sys
import os
import ctypes
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from orchestrator.local_automation.screen_utils import get_window_rect

u = ctypes.windll.user32

MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002

screen_w = u.GetSystemMetrics(0)
screen_h = u.GetSystemMetrics(1)

VK_BACK = 0x08
VK_DELETE = 0x2E
VK_HOME = 0x24
VK_END = 0x23
VK_SHIFT = 0x10
VK_ENTER = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B


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
    time.sleep(0.03)
    u.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
    time.sleep(0.03)


def raw_type_num(text):
    VK_MAP = {str(i): 0x30 + i for i in range(10)}
    for ch in text:
        vk = VK_MAP.get(ch, ord(ch.upper()))
        scan = u.MapVirtualKeyW(vk, 0)
        u.keybd_event(vk, scan, 0, 0)
        time.sleep(0.05)
        u.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)


def raw_type_text(text):
    for ch in text:
        if ch == ' ':
            raw_key(0x20)
        elif ch.isupper():
            u.keybd_event(VK_SHIFT, 0, 0, 0)
            time.sleep(0.02)
            vk = ord(ch)
            raw_key(vk)
            u.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        else:
            raw_key(ord(ch.upper()))
        time.sleep(0.03)


def clear_field():
    """Clear a field by pressing End then Backspace many times."""
    raw_key(VK_END)
    time.sleep(0.1)
    for _ in range(15):
        raw_key(VK_BACK)
        time.sleep(0.03)
    time.sleep(0.1)


def click_clear_type_num(sx, sy, value):
    """Click field, clear it, type new value."""
    raw_click(sx, sy, clicks=1)
    time.sleep(0.3)
    clear_field()
    time.sleep(0.2)
    raw_type_num(value)
    time.sleep(0.3)


def find_freq_vi():
    results = []
    def cb(h, _):
        if not u.IsWindowVisible(h):
            return True
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(h, buf, 256)
        if '481.300' in buf.value:
            results.append(h)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    u.EnumWindows(WNDENUMPROC(cb), 0)
    return results[0] if results else None


hwnd = find_freq_vi()
if not hwnd:
    print("ERROR: freq VI not found")
    sys.exit(1)

print(f"Found VI: hwnd={hwnd}")

u.BringWindowToTop(hwnd)
time.sleep(0.3)
u.SetFocus(hwnd)
time.sleep(0.5)

rect = get_window_rect(hwnd)
left, top = rect[0], rect[1]
print(f"Window at ({left},{top}) size {rect[2]-rect[0]}x{rect[3]-rect[1]}")

# Press Escape first to cancel any edit mode
raw_key(VK_ESCAPE)
time.sleep(0.3)

# RF channel 2G = 10
print("Setting RF channel 2G = 10")
click_clear_type_num(left + 385, top + 612, "10")

# RF channel 5G = 44
print("Setting RF channel 5G = 44")
click_clear_type_num(left + 535, top + 612, "44")

# RF channel 6G = 69
print("Setting RF channel 6G = 69")
click_clear_type_num(left + 690, top + 612, "69")

# User information = "2G test"
print("Setting User information = 2G test")
raw_click(left + 560, top + 687, clicks=1)
time.sleep(0.3)
clear_field()
time.sleep(0.2)
raw_type_text("2G test")
time.sleep(0.5)

# Capture result
from PIL import ImageGrab
import numpy as np
import cv2

img = ImageGrab.grab(bbox=(left, top, left + 1260, top + 950))
arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
out = r'c:\Projects\RAS Wireless Agent\artifacts\labview_calibration\step05_all_filled.png'
cv2.imwrite(out, arr)
print(f"Saved: {out}")
print("DONE!")
