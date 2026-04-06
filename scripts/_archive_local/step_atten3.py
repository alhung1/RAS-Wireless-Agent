"""Find exact field positions from blue text, then set values."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if 'atten' in buf.value.lower():
            windows.append(hwnd)
    return True
u.EnumWindows(enum_cb, 0)

hwnd = windows[0]
fg = u.GetForegroundWindow()
fg_tid = u.GetWindowThreadProcessId(fg, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, fg_tid, True)
u.ShowWindow(hwnd, 9)
u.BringWindowToTop(hwnd)
u.SetForegroundWindow(hwnd)
u.AttachThreadInput(my_tid, fg_tid, False)
time.sleep(0.8)

ss = pyautogui.screenshot()
arr = np.array(ss)

# The blue text for field values is at:
# y=373-375: x=207 (Start atten), x=446 (Step Size), x=537 (Steps)
# y=421: x=136 (End atten - not needed), x=376 (unknown)

# Find the field bounding boxes by checking colors around the text
# Check the background around each text position
fields_info = [
    ("Start atten", 207, 374),
    ("Step Size", 446, 374),
    ("Steps", 537, 374),
]

for name, tx, ty in fields_info:
    # Sample a box around the text
    print(f"\n{name} area around ({tx}, {ty}):")
    for dy in range(-20, 25, 5):
        for dx in range(-30, 35, 10):
            y, x = ty + dy, tx + dx
            if 0 <= y < 1440 and 0 <= x < 2560:
                c = arr[y, x]
                if c[0] != 23 or c[1] != 255 or c[2] != 255:  # not cyan background
                    print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")

# Crop the fields area
ss.crop((80, 340, 700, 440)).save("artifacts/labview_calibration/atten_text_fields.png")

# The fields are likely white/light colored with blue text
# Let me find the exact field boundaries
for name, tx, ty in fields_info:
    # Find horizontal extent of non-cyan background
    x_left = tx
    while x_left > 0 and not (arr[ty, x_left, 0] == 23 and arr[ty, x_left, 1] == 255 and arr[ty, x_left, 2] == 255):
        x_left -= 1
    x_right = tx
    while x_right < 2559 and not (arr[ty, x_right, 0] == 23 and arr[ty, x_right, 1] == 255 and arr[ty, x_right, 2] == 255):
        x_right += 1
    y_top = ty
    while y_top > 0 and not (arr[y_top, tx, 0] == 23 and arr[y_top, tx, 1] == 255 and arr[y_top, tx, 2] == 255):
        y_top -= 1
    y_bottom = ty
    while y_bottom < 1439 and not (arr[y_bottom, tx, 0] == 23 and arr[y_bottom, tx, 1] == 255 and arr[y_bottom, tx, 2] == 255):
        y_bottom += 1
    cx = (x_left + x_right) // 2
    cy = (y_top + y_bottom) // 2
    print(f"\n{name} field bounds: x=[{x_left},{x_right}] y=[{y_top},{y_bottom}] center=({cx},{cy})")
