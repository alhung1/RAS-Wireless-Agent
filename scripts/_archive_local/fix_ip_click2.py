"""Find exact [0][1] button and dropdown positions, then click them."""
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

ss = pyautogui.screenshot()
print(f"Screenshot: {ss.size}")

# Wider crop around DUT area
dut_wide = ss.crop((40, 500, 300, 580))
dut_wide.save("artifacts/labview_calibration/click2_dut_wide.png")
print(f"DUT wide crop: {dut_wide.size}")

# Wider crop around dropdown area  
dd_wide = ss.crop((280, 470, 700, 570))
dd_wide.save("artifacts/labview_calibration/click2_dropdown_wide.png")
print(f"Dropdown wide crop: {dd_wide.size}")

# Bottom section showing error indicators
bottom = ss.crop((0, 560, 900, 650))
bottom.save("artifacts/labview_calibration/click2_bottom.png")
print(f"Bottom crop: {bottom.size}")
