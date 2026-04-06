"""Step 13: Set Number of pairs 2G/MLO to 8, then advance.
   Window is at (0,0,1288,1040). Need to find the yellow 'Number of pairs 2G/MLO' field."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 468496
u.SetForegroundWindow(hwnd)
time.sleep(0.8)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Crop just the LabVIEW window area
ss.crop((0, 0, 1300, 1050)).save("artifacts/labview_calibration/pairs_focused.png")

# Search exhaustively for yellow-green fields in window area
print("Searching for yellow/green fields (R>150, G>200, B<80)...")
found = {}
for y in range(100, 600):
    row = arr[y, 100:600, :]
    match = (row[:, 0] > 150) & (row[:, 1] > 200) & (row[:, 2] < 80)
    mx = np.where(match)[0]
    if len(mx) > 5:
        mx_abs = mx + 100
        key = (mx_abs.min(), mx_abs.max())
        if key not in found:
            found[key] = []
        found[key].append(y)
        if len(found[key]) <= 2:
            sample = arr[y, mx_abs[0]]
            print(f"  y={y}: x=[{mx_abs.min()},{mx_abs.max()}] R={sample[0]}G={sample[1]}B={sample[2]}")

# Group found regions
print(f"\nFound {len(found)} x-range groups")
for k, ys in found.items():
    y_min, y_max = min(ys), max(ys)
    cx = (k[0] + k[1]) // 2
    cy = (y_min + y_max) // 2
    print(f"  x=[{k[0]},{k[1]}] y=[{y_min},{y_max}] center=({cx},{cy}) height={y_max-y_min}")

# Also sample the exact after_arrow_correct.png coordinates
print("\nDirect color sampling around expected 2G/MLO field (x=380-460, y=270-320):")
for y in range(270, 320, 3):
    for x in range(380, 460, 5):
        c = arr[y, x]
        if c[0] > 100 and c[1] > 100:
            print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")
