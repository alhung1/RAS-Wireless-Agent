"""Click '3' in 5G/6G dropdown, then fix 2G/MLO to 3."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.3)

# Click "3" in the 5G/6G dropdown list at screen (870, 555)
print("Clicking '3' in 5G/6G dropdown at (870, 555)...")
pyautogui.click(870, 555)
time.sleep(1.5)

# Check result
ss1 = pyautogui.screenshot(region=(750, 500, 350, 70))
ss1.save("artifacts/labview_calibration/click11_5g_after.png")
print("5G/6G dropdown result saved")

# Now fix 2G/MLO: change from "2" to "3"
# 2G/MLO dropdown center: x=601, y=550
print("\nOpening 2G/MLO dropdown at (601, 550)...")
pyautogui.click(601, 550)
time.sleep(1.0)

# Take screenshot to see list
ss2 = pyautogui.screenshot(region=(450, 500, 350, 250))
ss2.save("artifacts/labview_calibration/click11_2g_list.png")

# Click "3" in the 2G/MLO dropdown
# From the previous list image (click9_list_open.png), items were:
#   Not Valid at y≈37, 1 at y≈65, 2 at y≈95, 3 at y≈120, 4 at y≈150, 5 at y≈180
# Screen positions: each item at approximately 500 + y_offset
# Let me calculate: "3" is the 4th item (after Not Valid, 1, 2)
# Each item about 28 pixels tall, list starts at y≈535
# "3" at y = 535 + 28*3 = 619
# But I accidentally selected "2" before at y=624, so "3" should be higher
# From the click9 list image: "2" row starts at about crop y=80 (screen 580)
# "3" row starts at about crop y=110 (screen 610)
# Let me be precise: click at x=570, y=610

print("Clicking '3' in 2G/MLO at (570, 610)...")
pyautogui.click(570, 610)
time.sleep(1.5)

# Check result
ss3 = pyautogui.screenshot(region=(450, 500, 350, 70))
ss3.save("artifacts/labview_calibration/click11_2g_after.png")

# Full screenshot
ss_full = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss_full.save("artifacts/labview_calibration/click11_final.png")

print("Done")
