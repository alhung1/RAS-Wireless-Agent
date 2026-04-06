"""Navigate to US in Region dropdown."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

# Go to top of list
print("Pressing Up multiple times to find US...")
for i in range(20):
    pyautogui.press('up')
    time.sleep(0.15)

# Take screenshot at top
ss = pyautogui.screenshot()
ss.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/region_list_navigated.png")
ss.crop((80, 400, 500, 700)).save("artifacts/labview_calibration/region_list_items.png")
