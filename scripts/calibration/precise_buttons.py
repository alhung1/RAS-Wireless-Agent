"""Precisely locate [0][1] buttons and any error indicators."""
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

# Crop around DUT [0][1] area  
crop1 = ss.crop((80, 780, 400, 850))
crop1.save("artifacts/labview_calibration/dut_buttons_area.png")

# Crop the bottom area where error indicators might appear
crop2 = ss.crop((0, 830, 1300, 1020))
crop2.save("artifacts/labview_calibration/bottom_indicators.png")

# Crop the area between CLIENT IP rows and Freq Range
crop3 = ss.crop((550, 640, 950, 720))
crop3.save("artifacts/labview_calibration/error_area.png")

# Look for any red pixels that could indicate an error
region = arr[600:750, :1300, :]
red = (region[:, :, 0] > 180) & (region[:, :, 1] < 80) & (region[:, :, 2] < 80)
ry, rx = np.where(red)
if len(ry) > 0:
    ry += 600
    print(f"Red pixels found: x=[{rx.min()},{rx.max()}] y=[{ry.min()},{ry.max()}] count={len(ry)}")

# Scan for [0][1] - look for small box outlines near DUT
# The buttons have thin borders - look for black borders forming small squares
for y in range(795, 835):
    row = arr[y, 200:350, :]
    # Look for patterns that could be button borders (dark outline)
    dark = (row[:, 0] < 30) & (row[:, 1] < 30) & (row[:, 2] < 30)
    dx = np.where(dark)[0]
    if len(dx) > 3:
        print(f"Dark at y={y}: x_offsets={dx[:20]+200}")

# Also search for white/light gray buttons
for y in range(795, 835):
    row = arr[y, 220:290, :]
    light = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] > 200)
    lx = np.where(light)[0]
    if len(lx) > 3:
        print(f"Light at y={y}: x_offsets={lx+220}")
