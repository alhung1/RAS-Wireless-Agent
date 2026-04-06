"""Clean sequence: click [1] then orange arrow on fresh IP screen."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 794676
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Find [0][1] buttons - gray buttons near DUT AP
# Search for gray button clusters
print("Finding [0][1] buttons...")
for y in range(700, 950, 2):
    row = arr[y, :500, :]
    gray = ((row[:, 0] > 175) & (row[:, 0] < 215) &
            (row[:, 1] > 175) & (row[:, 1] < 215) &
            (row[:, 2] > 175) & (row[:, 2] < 215))
    gx = np.where(gray)[0]
    if len(gx) > 10:
        print(f"  y={y}: {len(gx)} gray, x=[{gx.min()},{gx.max()}]")
        break

# Find orange right arrow in bottom-right
print("\nFinding orange arrow...")
region = arr[800:1050, 800:1300, :]
orange = (region[:, :, 0] > 200) & (region[:, :, 1] > 130) & (region[:, :, 1] < 190) & (region[:, :, 2] < 80)
oy, ox = np.where(orange)
if len(oy) > 0:
    oy += 800
    ox += 800
    print(f"  Arrow: x=[{ox.min()},{ox.max()}] y=[{oy.min()},{oy.max()}]")
    arrow_cx = int((ox.min() + ox.max()) // 2)
    arrow_cy = int((oy.min() + oy.max()) // 2)
    print(f"  Arrow center: ({arrow_cx}, {arrow_cy})")

# Crop [0][1] buttons area for verification
btn_area = ss.crop((220, 790, 310, 830))
btn_area.save("artifacts/labview_calibration/advance_buttons.png")

# Step 1: Click [1]
# From the screenshot, buttons should be near x=260, y=810 area
# Let me find precisely
for y in range(790, 830):
    row = arr[y, 220:310, :]
    gray = ((row[:, 0] > 175) & (row[:, 0] < 215) &
            (row[:, 1] > 175) & (row[:, 1] < 215) &
            (row[:, 2] > 175) & (row[:, 2] < 215))
    gx = np.where(gray)[0]
    if len(gx) > 8:
        left_gx = gx + 220
        print(f"  Button row y={y}: gray at x=[{left_gx.min()},{left_gx.max()}]")

print("\n--- EXECUTING ---")
# Click [1] button
print("Step 1: Clicking [1]...")
pyautogui.click(265, 810)
time.sleep(1.5)

# Screenshot after [1]
ss2 = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss2.save("artifacts/labview_calibration/advance_after_1.png")

# Step 2: Click orange arrow
if 'arrow_cx' in dir():
    print(f"Step 2: Clicking orange arrow at ({arrow_cx}, {arrow_cy})...")
    pyautogui.click(arrow_cx, arrow_cy)
    time.sleep(3.0)

    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(hwnd, buf, 256)
    print(f"Window title: '{buf.value}'")

    ss3 = pyautogui.screenshot(region=(0, 0, 1400, 1100))
    ss3.save("artifacts/labview_calibration/advance_after_arrow.png")

print("Done")
