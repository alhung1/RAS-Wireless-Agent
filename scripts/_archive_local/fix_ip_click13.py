"""Open 2G/MLO dropdown and click '3', then fix 5G/6G."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Close any open dropdown first
pyautogui.press('escape')
time.sleep(0.5)

# =========================================================
# Step 1: Open and select from 2G/MLO dropdown
# =========================================================
# Dropdown control at x=505-697, y≈538-562 (from pixel analysis)
# Click center to open: (601, 550)
print("Opening 2G/MLO dropdown...")
pyautogui.click(601, 550)
time.sleep(0.8)

# Take screenshot immediately
ss = pyautogui.screenshot()

# Find the dropdown list popup
# Look for a block of white/near-white pixels that form the dropdown list
arr = np.array(ss)

# Scan for the list popup by finding white area below the dropdown
for y in range(550, 700):
    row = arr[y, 500:700, :]
    white = ((row[:, 0] > 230) & (row[:, 1] > 230) & (row[:, 2] > 230)).sum()
    if white > 50:
        print(f"  List white row at y={y}: {white} white pixels")
        break

# The list popup is below the dropdown button
# From the click8_center.png analysis, the list items at relative positions:
# The dropdown opened at y≈538. The list appears below starting at y≈560 (roughly)
# Each item is about 25-28 pixels tall
# List items: Not Valid, 1, 2, 3, 4, 5
# "3" is the 4th item

# Let me just find where "3" is by looking for specific text patterns
# Actually, let me take a crop and visually verify
list_crop = ss.crop((490, 540, 720, 750))
list_crop.save("artifacts/labview_calibration/click13_list.png")

# Find boundaries of list items
for y in range(list_crop.size[1]):
    row = np.array(list_crop)[y, :, :]
    black = ((row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] < 50)).sum()
    white = ((row[:, 0] > 230) & (row[:, 1] > 230) & (row[:, 2] > 230)).sum()
    if black > 5 and white > 50:
        scrn_y = 540 + y
        print(f"  Text row at screen y={scrn_y}: {black} black, {white} white")

# Based on the list from click8:
# Not Valid starts at list_top, then 1, 2, 3, 4, 5
# Each item ~28px. If list_top = 560:
#   Not Valid: 560-588
#   1: 588-616
#   2: 616-644
#   3: 644-672  (center at 658)
#   4: 672-700

# Click on "3" - estimate based on the list pattern
# x should be in the middle of the dropdown: (505+697)/2 = 601
# y should be at the 4th item: approximately 658

print("\nClicking '3' at (601, 658)...")
pyautogui.click(601, 658)
time.sleep(1.0)

# Check
ss2 = pyautogui.screenshot(region=(490, 530, 220, 45))
ss2.save("artifacts/labview_calibration/click13_2g_result.png")

# Full check
ss3 = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss3.save("artifacts/labview_calibration/click13_full.png")

print("Done")
