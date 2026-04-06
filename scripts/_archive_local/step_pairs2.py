"""Step 13: Set Number of pairs 2G/MLO to 8, then advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

# Find all LabVIEW windows
windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if 'Chariot' in buf.value or '400 600' in buf.value:
            rect = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(rect))
            windows.append((hwnd, buf.value, rect.left, rect.top, rect.right, rect.bottom))
    return True
u.EnumWindows(enum_cb, 0)

for w in windows:
    print(f"  {w[0]}: '{w[1]}' ({w[2]},{w[3]},{w[4]},{w[5]})")

hwnd = windows[0][0]
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Sample the color at approximate "Number of pairs 2G/MLO" field location
# From the screenshot it appears around x=410, y=295
for y in [285, 290, 295, 300, 305]:
    for x in [395, 400, 405, 410, 415, 420, 425, 430, 435, 440]:
        c = arr[y, x]
        if c[0] > 150:
            print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")

# Broader yellow/green search
print("\nBroadly searching for colored fields...")
for y in range(200, 800, 3):
    row = arr[y, 300:600, :]
    # Yellow-green fields (high R, high G, low B)
    match = (row[:, 0] > 180) & (row[:, 1] > 180) & (row[:, 2] < 120)
    mx = np.where(match)[0]
    if len(mx) > 10:
        mx_abs = mx + 300
        print(f"  y={y}: x=[{mx_abs.min()},{mx_abs.max()}] count={len(mx)} sample=R{arr[y,mx_abs[0],0]}G{arr[y,mx_abs[0],1]}B{arr[y,mx_abs[0],2]}")

# Crop the field area for visual inspection
crop = ss.crop((350, 250, 550, 350))
crop.save("artifacts/labview_calibration/pairs_field_area.png")

# Also try wider search
crop2 = ss.crop((350, 470, 550, 570))
crop2.save("artifacts/labview_calibration/pairs_field_5g_area.png")
