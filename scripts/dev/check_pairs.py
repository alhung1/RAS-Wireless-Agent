"""Check current screen state."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if buf.value and ('400' in buf.value or '480' in buf.value or 'Chariot' in buf.value or 'v2.03' in buf.value):
            rect = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(rect))
            windows.append((hwnd, buf.value, rect.left, rect.top, rect.right, rect.bottom))
    return True
u.EnumWindows(enum_cb, 0)

print("Windows found:")
for w in windows:
    print(f"  {w[0]}: '{w[1]}' rect=({w[2]},{w[3]},{w[4]},{w[5]})")

# Bring the Chariot window to front
for w in windows:
    if 'Chariot' in w[1]:
        u.SetForegroundWindow(w[0])
        print(f"\nActivated: '{w[1]}'")
        time.sleep(0.5)
        break

ss = pyautogui.screenshot()
print(f"Screenshot: {ss.size}")
ss.save("artifacts/labview_calibration/pairs_current.png")

arr = np.array(ss)

# Sample colors at various points in the middle area
print("\nColor sampling (middle of screen):")
for y in range(200, 800, 50):
    for x in range(300, 800, 50):
        c = arr[y, x]
        if c[0] != c[1] or c[1] != c[2]:  # Not gray/cyan
            if not (c[0] < 50 and c[1] > 200 and c[2] > 200):  # Not pure cyan
                print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")
