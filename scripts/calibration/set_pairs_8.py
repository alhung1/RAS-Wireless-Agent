"""Set Number of pairs 2G/MLO to 8 and advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

# Activate window and wait
hwnd = 468496
u.SetForegroundWindow(hwnd)
time.sleep(1.5)

# Take screenshot
ss = pyautogui.screenshot()
arr = np.array(ss)
print(f"Screenshot size: {ss.size}")

# Search for yellow-green field color more broadly
print("Searching for all non-cyan, non-gray colored regions in window area...")
for y in range(100, 800, 2):
    row = arr[y, 100:600, :]
    # Looking for any bright, saturated color (not gray, not cyan, not black)
    bright = (row[:, 0] > 100) | (row[:, 1] > 100)
    not_gray = np.abs(row[:, 0].astype(int) - row[:, 1].astype(int)) > 30
    not_cyan = ~((row[:, 0] < 30) & (row[:, 1] > 180) & (row[:, 2] > 180))
    match = bright & not_gray & not_cyan
    mx = np.where(match)[0]
    if len(mx) > 10:
        mx_abs = mx + 100
        sample = arr[y, mx_abs[0]]
        if sample[0] > 120 and sample[1] > 120:  # Bright enough
            print(f"  y={y}: x=[{mx_abs.min()},{mx_abs.max()}] R={sample[0]}G={sample[1]}B={sample[2]} count={len(mx)}")

# Also look for the dark outline of the "4" digit
print("\nLooking for dark text in Number of pairs area (y=280-340, x=380-480):")
for y in range(280, 340):
    row = arr[y, 380:480, :]
    dark = (row[:, 0] < 40) & (row[:, 1] < 40) & (row[:, 2] < 40)
    dx = np.where(dark)[0]
    if len(dx) > 0:
        print(f"  y={y}: dark at x={list(dx+380)}")

# Sample exact center of where "4" should be based on the visual image
# The crop (0,0,1300,1050) shows "4" at roughly 34% from left, 31% from top  
# That would be ~442, ~325
test_coords = [(430, 310), (440, 315), (450, 320), (460, 325), (435, 320)]
print("\nSampling at expected field locations:")
for x, y in test_coords:
    c = arr[y, x]
    print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")
