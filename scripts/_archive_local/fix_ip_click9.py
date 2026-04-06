"""Open dropdown and select 3 for 2G/MLO, then set 5G/6G too."""
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

# =========================================================
# Set 2G/MLO dropdown to "3"
# =========================================================

# Open the dropdown at (601, 550)
print("Opening 2G/MLO dropdown at (601, 550)...")
pyautogui.click(601, 550)
time.sleep(1.0)

# Take screenshot to see list positions
ss1 = pyautogui.screenshot(region=(450, 500, 350, 250))
ss1.save("artifacts/labview_calibration/click9_list_open.png")

# Find the position of "3" in the list
# From the dropdown, items appear to be:
#   Not Valid, 1, 2, 3, 4 (each ~28px tall)
# The list starts at approximately y=535 (screen)
# Item "3" would be at approximately y=535 + 28*3 = 619 (center of 4th item including header)
# x center of the list: approximately 580

# Let me find the exact "3" position by looking for the number
arr = np.array(ss1)
print(f"List screenshot: {arr.shape}")

# Find text rows by looking for black pixels on white/light gray background
for y in range(arr.shape[0]):
    row = arr[y, :, :]
    black_count = ((row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] < 50)).sum()
    white_count = ((row[:, 0] > 240) & (row[:, 1] > 240) & (row[:, 2] > 240)).sum()
    if black_count > 3 and white_count > 50:
        print(f"  y={y} (screen {500+y}): black={black_count}, white={white_count}")

# Click on "3" - approximately 4th item in the list
# Each item is about 26-28 pixels tall
# From the screenshot, the list starts at approximately y=38 in the crop = screen y=538
# Items: Not Valid (y≈38-60), 1 (y≈60-85), 2 (y≈85-110), 3 (y≈110-138), 4 (y≈138-165)
# "3" center: crop y≈124 → screen y = 500 + 124 = 624
# x center: approximately crop x=120 → screen x = 450 + 120 = 570

print("\nClicking '3' at (570, 624)...")
pyautogui.click(570, 624)
time.sleep(1.5)

# Check if it changed
ss2 = pyautogui.screenshot(region=(450, 500, 350, 100))
ss2.save("artifacts/labview_calibration/click9_after_select_3.png")

# =========================================================
# Now set 5G/6G dropdown too
# 5G/6G dropdown is at x=820 to x=1012 (from pixel analysis)
# Center: x = (820+1012)/2 = 916, y = 550
# =========================================================

# First check current state
ss_check = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss_check.save("artifacts/labview_calibration/click9_after_2g.png")

# Open 5G/6G dropdown
print("Opening 5G/6G dropdown at (916, 550)...")
pyautogui.click(916, 550)
time.sleep(1.0)

ss3 = pyautogui.screenshot(region=(770, 500, 350, 250))
ss3.save("artifacts/labview_calibration/click9_5g_list.png")

# Select "3" for 5G/6G too (same relative offset)
# List item "3": approximately at x=890, y=624
print("Clicking '3' for 5G/6G at (890, 624)...")
pyautogui.click(890, 624)
time.sleep(1.5)

# Final full screenshot
ss_final = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss_final.save("artifacts/labview_calibration/click9_final.png")

print("Done")
