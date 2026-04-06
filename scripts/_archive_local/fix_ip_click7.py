"""Horizontal sweep across the dropdown to find the clickable zone."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

pyautogui.press('escape')
time.sleep(0.3)

# First, let me measure pixel-perfectly from a screenshot
ss = pyautogui.screenshot()

# Find the "Not Valid" yellow text in the dropdown
# Search for yellow pixels (R>240, G>240, B<30) in the y=530-560 range
arr = np.array(ss)
for y in [535, 540, 545, 550, 555]:
    row = arr[y, :, :]
    yellow = (row[:, 0] > 240) & (row[:, 1] > 240) & (row[:, 2] < 30)
    yellow_x = np.where(yellow)[0]
    if len(yellow_x) > 0:
        # Find clusters (breaks between yellow regions)
        diffs = np.diff(yellow_x)
        breaks = np.where(diffs > 5)[0]
        clusters = []
        start = yellow_x[0]
        for b in breaks:
            clusters.append((start, yellow_x[b]))
            start = yellow_x[b + 1]
        clusters.append((start, yellow_x[-1]))
        print(f"y={y}: Yellow clusters: {clusters}")

# Now I know exactly where the dropdown control is
# Let me also get the gray arrow position
for y in [540, 545, 550]:
    row = arr[y, :, :]
    gray = (row[:, 0] > 180) & (row[:, 0] < 220) & (row[:, 1] > 180) & (row[:, 1] < 220) & (row[:, 2] > 180) & (row[:, 2] < 220)
    gray_x = np.where(gray)[0]
    if len(gray_x) > 0:
        # Find clusters after x=400
        filtered = gray_x[gray_x > 400]
        if len(filtered) > 0:
            print(f"y={y}: Gray pixels after x=400: [{filtered.min()}, {filtered.max()}]")
