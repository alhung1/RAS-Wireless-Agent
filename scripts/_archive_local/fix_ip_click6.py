"""Click at CORRECT dropdown position - it's lower than expected."""
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

# First, take a very precise crop of the dropdown "Not Valid" area
ss = pyautogui.screenshot()

# Based on pixel analysis, the dropdown control (yellow "Not Valid") starts at y~537
# Let me crop from y=530 to y=560 across the dropdown area
precise_crop = ss.crop((360, 530, 600, 565))
precise_crop.save("artifacts/labview_calibration/click6_precise.png")
arr = np.array(precise_crop)

# Print the pixel pattern to see the exact dropdown boundaries
print("Precise dropdown area pixel dump (screen 360,530 to 600,565):")
for y in range(arr.shape[0]):
    row = ""
    for x in range(0, arr.shape[1], 3):
        px = arr[y, x]
        if px[0] > 240 and px[1] > 240 and px[2] < 30:
            row += "Y"
        elif px[0] < 40 and px[1] > 240 and px[2] > 240:
            row += "C"
        elif px[0] > 180 and px[1] > 180 and px[2] > 180:
            row += "G"
        elif px[0] < 30 and px[1] < 30 and px[2] < 30:
            row += "B"
        else:
            row += "."
    scrn_y = 530 + y
    print(f"  y={scrn_y}: {row}")

# Step 1: Click [1] button
# From the analysis, [1] is at approximately (265, 778) in screen coords
print("\nStep 1: Clicking [1] at (265, 778)...")
pyautogui.click(265, 778)
time.sleep(1.0)

# Step 2: Now click on the "Not Valid" dropdown at the CORRECT y position
# The yellow area starts at y≈538, center at y≈545
# The gray arrow button is to the right, at approximately x=550-570, y=545
print("Step 2: Clicking dropdown 'Not Valid' at (460, 545)...")
pyautogui.click(460, 545)
time.sleep(1.5)

# Screenshot immediately to check
ss2 = pyautogui.screenshot(region=(300, 480, 500, 300))
ss2.save("artifacts/labview_calibration/click6_after_dropdown.png")

print("Checking if list opened...")

# If still not open, try the arrow button
ss2_arr = np.array(ss2)
# Check if there's a white/gray popup list (non-cyan, non-yellow region below the dropdown)
new_region = ss2.crop((0, 80, 500, 200))
new_arr = np.array(new_region)
white_pct = ((new_arr[:,:,0] > 230) & (new_arr[:,:,1] > 230) & (new_arr[:,:,2] > 230)).sum() / new_arr.size * 100
print(f"White pixels in area below dropdown: {white_pct:.1f}%")

# Try clicking the arrow specifically
print("Step 3: Clicking dropdown arrow at (555, 545)...")
pyautogui.click(555, 545)
time.sleep(1.5)

ss3 = pyautogui.screenshot(region=(300, 480, 500, 300))
ss3.save("artifacts/labview_calibration/click6_after_arrow.png")

# Full screenshot
ss_full = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss_full.save("artifacts/labview_calibration/click6_full.png")

print("Done")
