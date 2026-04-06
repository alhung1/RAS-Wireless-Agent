"""Click '3' in the currently open 2G/MLO list, then fix 5G/6G to 3."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.3)

# The 2G/MLO list is currently open. Let me find the exact "3" position.
ss = pyautogui.screenshot()

# Crop the visible list area
list_crop = ss.crop((340, 340, 530, 570))
list_crop.save("artifacts/labview_calibration/click12_2g_list_open.png")

# Find text rows
arr = np.array(list_crop)
print("Text rows in 2G/MLO list:")
for y in range(arr.shape[0]):
    row = arr[y, :, :]
    black = ((row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] < 50)).sum()
    if black > 2:
        scrn_y = 340 + y
        # Check the actual character by looking at x positions of black pixels
        black_x = np.where((row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] < 50))[0]
        print(f"  crop_y={y} (screen_y={scrn_y}): {black} black px at x={black_x.tolist()[:8]}")
