"""Find ALL yellow-green pixels in the full screenshot."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
u.SetForegroundWindow(468496)
time.sleep(1.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Search for yellow-green (like the "4" field) across ENTIRE image
# Yellow-green: R>150, G>200, B<100 OR R>200, G>200, B<50
print("=== Searching FULL 2560x1440 for yellow-green ===")
for y in range(0, 1440, 3):
    row = arr[y, :, :]
    yg = ((row[:, 0] > 150) & (row[:, 1] > 200) & (row[:, 2] < 80)) | \
         ((row[:, 0] > 200) & (row[:, 1] > 240) & (row[:, 2] < 50))
    yx = np.where(yg)[0]
    if len(yx) > 5:
        sample = arr[y, yx[0]]
        print(f"  y={y}: x=[{yx.min()},{yx.max()}] count={len(yx)} sample=R{sample[0]}G{sample[1]}B{sample[2]}")

# Also search for orange (arrow color)
print("\n=== Searching FULL image for orange (arrows) ===")
for y in range(0, 1440, 3):
    row = arr[y, :, :]
    orange = (row[:, 0] > 200) & (row[:, 1] > 130) & (row[:, 1] < 190) & (row[:, 2] < 80)
    ox = np.where(orange)[0]
    if len(ox) > 5:
        print(f"  y={y}: x=[{ox.min()},{ox.max()}] count={len(ox)}")
