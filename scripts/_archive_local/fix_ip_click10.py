"""Select 3 from open 5G/6G dropdown, then fix 2G/MLO to 3."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.3)

# The 5G/6G dropdown is currently open
# From the final screenshot (1400x1100 crop at 0,0):
# The list items and their approximate screen y positions:
#   Not Valid: y≈377
#   1: y≈403
#   ✓ 2: y≈425
#   3: y≈449
#   4: y≈474
#   5: y≈497
# The x center of list items: approximately x≈660

# But wait - the screenshot was a 1400x1100 crop at (0,0) which might
# not match the 2560x1440 screen coordinates directly.
# Let me take a fresh screenshot to find exact positions.

ss = pyautogui.screenshot()

# The 5G/6G dropdown list should still be open
# Let me find it by looking for white/light gray area with text
# The list overlay is in the right-center area

# Crop the area where the dropdown list should be
list_area = ss.crop((700, 430, 1050, 750))
list_area.save("artifacts/labview_calibration/click10_5g_list.png")
print(f"5G/6G list area: {list_area.size}")

# Find "3" in the list by looking for black text pixels
arr = np.array(list_area)
for y in range(arr.shape[0]):
    row = arr[y, :, :]
    # White background with some black text
    black_count = ((row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] < 50)).sum()
    if black_count > 2:
        scrn_y = 430 + y
        print(f"  Text at crop y={y} (screen {scrn_y}): {black_count} black pixels")
