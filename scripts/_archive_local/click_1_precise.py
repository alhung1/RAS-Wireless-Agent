"""Precisely locate [1] button and click it, then arrow."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
u.SetForegroundWindow(794676)
time.sleep(0.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Scan the [0][1] area precisely: y 800-840, x 200-400
# Look for button-like elements (raised 3D buttons with gray fill)
print("Scanning for [0][1] buttons (y=800-840, x=200-400):")
for y in range(800, 840):
    row = arr[y, 200:400, :]
    # Standard Windows button gray: ~192,192,192 or ~212,208,200
    gray_mask = ((row[:, 0] > 180) & (row[:, 0] < 230) &
                 (row[:, 1] > 180) & (row[:, 1] < 230) &
                 (row[:, 2] > 180) & (row[:, 2] < 230))
    gx = np.where(gray_mask)[0]
    if len(gx) > 5:
        gx_abs = gx + 200
        # Find clusters
        clusters = []
        curr = [gx_abs[0]]
        for i in range(1, len(gx_abs)):
            if gx_abs[i] - gx_abs[i-1] <= 2:
                curr.append(gx_abs[i])
            else:
                if len(curr) > 3:
                    clusters.append((min(curr), max(curr)))
                curr = [gx_abs[i]]
        if len(curr) > 3:
            clusters.append((min(curr), max(curr)))
        if clusters:
            print(f"  y={y}: clusters={clusters}")

# Also look for black "0" and "1" text
print("\nLooking for black text pixels (digits 0,1) in y=805-830, x=230-380:")
for y in range(805, 830):
    row = arr[y, 230:380, :]
    black = (row[:, 0] < 40) & (row[:, 1] < 40) & (row[:, 2] < 40)
    bx = np.where(black)[0]
    if len(bx) > 0:
        bx_abs = bx + 230
        print(f"  y={y}: black at x={list(bx_abs)}")

# Crop much tighter on just the buttons
tight = ss.crop((210, 795, 400, 840))
tight.save("artifacts/labview_calibration/buttons_tight.png")

# Also look at the red indicator
print("\nSearching for red indicator in bottom area:")
for y in range(850, 1000):
    row = arr[y, 550:750, :]
    red = (row[:, 0] > 180) & (row[:, 1] < 60) & (row[:, 2] < 60)
    rx = np.where(red)[0]
    if len(rx) > 0:
        rx_abs = rx + 550
        print(f"  y={y}: red at x={list(rx_abs)}")
