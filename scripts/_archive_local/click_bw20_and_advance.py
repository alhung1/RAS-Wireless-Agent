"""BW20 is highlighted - click it, then advance with orange arrow."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# BW20 is highlighted in the dropdown. Click on it.
# From the screenshot, the blue highlight for BW20 is at approximately:
# y ~ 340, x ~ 80-280

# Find BW20 highlight precisely
ss = pyautogui.screenshot()
arr = np.array(ss)

# Search for blue highlight (R<100, G<100, B>150)
print("Finding blue highlight...")
for y in range(300, 450):
    row = arr[y, 50:300, :]
    blue = (row[:, 0] < 100) & (row[:, 1] < 100) & (row[:, 2] > 150)
    bx = np.where(blue)[0]
    if len(bx) > 10:
        bx_abs = bx + 50
        print(f"  y={y}: x=[{bx_abs.min()},{bx_abs.max()}] count={len(bx)}")

# Click on BW20 (the blue highlighted item)
# Based on visual: approximately (170, 340)
# Let me find it from the blue highlight

blue_rows = []
for y in range(300, 450):
    row = arr[y, 50:300, :]
    blue = (row[:, 0] < 100) & (row[:, 1] < 100) & (row[:, 2] > 150)
    bx = np.where(blue)[0]
    if len(bx) > 10:
        bx_abs = bx + 50
        blue_rows.append((y, bx_abs.min(), bx_abs.max()))

if blue_rows:
    y_min = min(r[0] for r in blue_rows)
    y_max = max(r[0] for r in blue_rows)
    x_min = min(r[1] for r in blue_rows)
    x_max = max(r[2] for r in blue_rows)
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    print(f"  BW20 highlight: center=({cx},{cy})")
    
    print(f"\nClicking BW20 at ({cx}, {cy})...")
    pyautogui.click(cx, cy)
    time.sleep(1.5)
else:
    # Fallback: just press Enter since BW20 was highlighted
    print("Blue highlight not found, pressing Enter...")
    pyautogui.press('enter')
    time.sleep(1.5)

# Screenshot to verify BW20 was selected
ss2 = pyautogui.screenshot()
ss2.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/mode_bw20_selected.png")

# Check if Mode Error is still red
arr2 = np.array(ss2)

# Now find and click orange arrow
pts = []
for y in range(850, 1100):
    if y >= arr2.shape[0]:
        break
    row = arr2[y, 800:1300, :]
    orange = (row[:, 0] > 200) & (row[:, 1] > 130) & (row[:, 1] < 190) & (row[:, 2] < 80)
    ox = np.where(orange)[0]
    if len(ox) > 3:
        pts.append((y, ox.min() + 800, ox.max() + 800))

if pts:
    acx = (min(p[1] for p in pts) + max(p[2] for p in pts)) // 2
    acy = (min(p[0] for p in pts) + max(p[0] for p in pts)) // 2
    print(f"Orange arrow at ({acx}, {acy})")
    
    print(f"Clicking orange arrow...")
    pyautogui.click(acx, acy)
    time.sleep(3.0)
    
    fg = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(fg, buf, 256)
    print(f"Current window: '{buf.value}'")
    
    ss3 = pyautogui.screenshot()
    ss3.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_mode_advance.png")
else:
    print("Orange arrow not found!")

print("Done")
