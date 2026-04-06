"""Click [1] button then dropdown. Simple single clicks."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Dismiss any dialog
pyautogui.press('escape')
time.sleep(0.3)

# Step 1: Click [1] button next to DUT AP
# From the lower_half crop at offset (0, 600):
#   [0] is at approximately crop_x=246, crop_y=178
#   [1] is at approximately crop_x=265, crop_y=178
#   Screen: [1] at (265, 778)
print("Step 1: Clicking [1] button at (265, 778)...")
pyautogui.click(265, 778)
time.sleep(1.0)

# Take screenshot to verify
ss1 = pyautogui.screenshot(region=(0, 600, 1300, 400))
ss1.save("artifacts/labview_calibration/click4_after_1.png")
print("After clicking [1] - saved screenshot")

# Step 2: Click the "Not Valid" dropdown for 2G/MLO
# From the middle crop at offset (0, 400):
#   "Not Valid" center at approximately crop (460, 120) → screen (460, 520)
#   Dropdown arrow at approximately crop (545, 118) → screen (545, 518)
print("Step 2: Clicking 'Not Valid' dropdown at (460, 520)...")
pyautogui.click(460, 520)
time.sleep(1.5)

# Take screenshot to see if dropdown opened
ss2 = pyautogui.screenshot(region=(300, 470, 500, 250))
ss2.save("artifacts/labview_calibration/click4_dropdown_opened.png")

# Also full screenshot
ss2_full = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss2_full.save("artifacts/labview_calibration/click4_full.png")

print("Done - check if dropdown opened")
