"""Click [1] button at correct location, verify, then click orange arrow."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
hwnd = 794676
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Step 1: Click [1] button at (360, 832)
print("Clicking [1] button at (360, 832)...")
pyautogui.click(360, 832)
time.sleep(2.0)

# Screenshot after clicking [1]
ss = pyautogui.screenshot()
arr = np.array(ss)
ss.crop((0, 0, 1300, 1050)).save("artifacts/labview_calibration/after_1_correct.png")
ss.crop((80, 780, 400, 850)).save("artifacts/labview_calibration/after_1_dut.png")
ss.crop((550, 840, 750, 900)).save("artifacts/labview_calibration/after_1_indicator.png")

# Check for any red error indicators
print("Checking for red error indicators...")
for y in range(600, 1000):
    row = arr[y, :1300, :]
    red = (row[:, 0] > 180) & (row[:, 1] < 60) & (row[:, 2] < 60)
    rx = np.where(red)[0]
    if len(rx) > 2:
        print(f"  RED at y={y}: x={list(rx[:10])}")

# Check for orange arrow
region = arr[850:1000, 1100:1250, :]
orange = (region[:, :, 0] > 200) & (region[:, :, 1] > 130) & (region[:, :, 1] < 190) & (region[:, :, 2] < 80)
oy, ox = np.where(orange)
if len(oy) > 0:
    arrow_cx = int(ox.mean()) + 1100
    arrow_cy = int(oy.mean()) + 850
    print(f"Orange arrow at ({arrow_cx}, {arrow_cy})")

# Step 2: Click orange arrow
print(f"\nClicking orange arrow at ({arrow_cx}, {arrow_cy})...")
pyautogui.click(arrow_cx, arrow_cy)
time.sleep(3.0)

# Check new window title
buf = ctypes.create_unicode_buffer(256)
fg = u.GetForegroundWindow()
u.GetWindowTextW(fg, buf, 256)
print(f"Current foreground: '{buf.value}'")
u.GetWindowTextW(hwnd, buf, 256)
print(f"LabVIEW window: '{buf.value}'")

# Screenshot after arrow
ss2 = pyautogui.screenshot()
ss2.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_arrow_correct.png")
ss2.crop((0, 0, 600, 50)).save("artifacts/labview_calibration/after_arrow_title.png")

print("Done")
