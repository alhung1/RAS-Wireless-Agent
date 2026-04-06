"""Click [1] button next to DUT AP, then orange arrow."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# First, find the exact [0] [1] button position
ss = pyautogui.screenshot()
print(f"Screenshot: {ss.size}")

# The DUT area with [0] [1] is in the lower section
# From the user's image: "DUT" label, "AP" green box, then [0] [1] buttons
# Let me scan for the gray button pixels in the DUT area
arr = np.array(ss)

# The [0] [1] buttons are small gray 3D buttons
# From the fix5g_after_arrow.png (1400x1100 crop at 0,0):
#   DUT "AP" at approximately y=610, [0] at x=243, [1] at x=262
# But these were from a cropped screenshot. In the full 2560x1440:
#   Let me search for "DUT" text area and buttons

# The DUT section should be around y=600-620 in the 1400-wide crop
# In 2560x1440 full screenshot, it should be at similar absolute position
# since the crop was at (0,0)

# Let me crop the DUT area wider
dut_area = ss.crop((50, 590, 350, 640))
dut_area.save("artifacts/labview_calibration/dut_buttons_find.png")

# Find gray button pixels (the [0] and [1] buttons are 3D gray)
dut_arr = np.array(dut_area)
print(f"DUT area: {dut_area.size}")

# Gray pixels that could be buttons: RGB around (190-210, 190-210, 190-210)
for y in range(dut_arr.shape[0]):
    row = dut_arr[y, :, :]
    gray_btn = ((row[:, 0] > 170) & (row[:, 0] < 220) & 
                (row[:, 1] > 170) & (row[:, 1] < 220) & 
                (row[:, 2] > 170) & (row[:, 2] < 220)).sum()
    if gray_btn > 5:
        scrn_y = 590 + y
        gray_x = np.where((row[:, 0] > 170) & (row[:, 0] < 220) & 
                          (row[:, 1] > 170) & (row[:, 1] < 220) & 
                          (row[:, 2] > 170) & (row[:, 2] < 220))[0]
        print(f"  y={scrn_y}: {gray_btn} gray px, x=[{gray_x.min()+50},{gray_x.max()+50}]")
