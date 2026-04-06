"""Simple clicks: [1] button then dropdown. Use pyautogui consistently in 2560x1440."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Dismiss any dialog
pyautogui.press('escape')
time.sleep(0.3)
pyautogui.press('escape')
time.sleep(0.3)

# Step 1: Take fresh screenshot and locate [1] button and dropdown precisely
ss = pyautogui.screenshot()
print(f"Screenshot: {ss.size}")

# Crop the DUT area to find [0] [1] buttons
# From previous screenshots: DUT AP with [0] [1] at bottom-left area
dut_crop = ss.crop((50, 525, 350, 570))
dut_crop.save("artifacts/labview_calibration/click_dut_area.png")

# Crop the dropdown area
dd_crop = ss.crop((320, 490, 660, 560))
dd_crop.save("artifacts/labview_calibration/click_dropdown_area.png")

print("Saved reference crops. Now clicking...")

# Step 2: Click [1] button next to DUT AP
# From the full screenshot, the [1] button is a small square next to "AP"
# Let me find it precisely - it's in the lower-left area
# DUT "AP" text + [0] [1] buttons
# From previous 2560x1440 screenshots: approximately x=228, y=537 for [1]
# Let me zoom in to find exact position

# Actually let me find the [0] and [1] by looking at the pixels
# The buttons are small white/gray squares
dut_wide = ss.crop((100, 530, 300, 550))
arr = np.array(dut_wide)
print(f"DUT buttons area pixels (y=10 center row):")
for x in range(0, arr.shape[1], 5):
    px = arr[10, x]
    if px[0] > 200 and px[1] > 200 and px[2] > 200:
        print(f"  x={100+x}: WHITE ({px[0]},{px[1]},{px[2]})")

# Take a tighter crop around [0] [1]
btn_crop = ss.crop((195, 530, 255, 548))
btn_crop.save("artifacts/labview_calibration/click_01_buttons.png")
print(f"[0][1] buttons crop: {btn_crop.size}")
