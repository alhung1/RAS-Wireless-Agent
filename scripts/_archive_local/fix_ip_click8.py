"""Click at CORRECT dropdown position: x=505-697, y=540-555."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

pyautogui.press('escape')
time.sleep(0.3)

# Exact positions from pixel analysis:
# "2G/MLO" dropdown: x=505 to x=697, y≈538 to y≈562
# Center of dropdown: (601, 550)
# Arrow button (right edge): approximately (685, 550)

# Step 1: Click [1] button at (265, 778)
print("Step 1: Click [1] button at (265, 778)...")
pyautogui.click(265, 778)
time.sleep(1.0)

# Step 2: Click the dropdown at its ACTUAL center
print("Step 2: Click dropdown center at (601, 550)...")
pyautogui.click(601, 550)
time.sleep(2.0)

# Take screenshot to see if list opened
ss1 = pyautogui.screenshot(region=(450, 500, 350, 200))
ss1.save("artifacts/labview_calibration/click8_center.png")
print("Saved after center click")

# If not, try the arrow at the right edge
print("Step 3: Click dropdown arrow at (690, 550)...")
pyautogui.click(690, 550)
time.sleep(2.0)

ss2 = pyautogui.screenshot(region=(450, 500, 350, 200))
ss2.save("artifacts/labview_calibration/click8_arrow.png")
print("Saved after arrow click")

# Full screenshot
ss_full = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss_full.save("artifacts/labview_calibration/click8_full.png")

print("Done")
