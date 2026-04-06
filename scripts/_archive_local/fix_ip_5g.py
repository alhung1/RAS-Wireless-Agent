"""Set 5G/6G dropdown to 3, then try orange arrow."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.3)

# 5G/6G dropdown at x=820-1012, center=(916, 550)
print("Opening 5G/6G dropdown at (916, 550)...")
pyautogui.click(916, 550)
time.sleep(0.8)

# Take screenshot to see list
ss = pyautogui.screenshot()
list_crop = ss.crop((800, 540, 1050, 750))
list_crop.save("artifacts/labview_calibration/fix5g_list.png")

# "3" should be at similar position as 2G/MLO list
# In the 2G/MLO list, "3" was at y=575 when "2" was selected
# Let me find it precisely
arr = np.array(list_crop)
for y in range(arr.shape[0]):
    row = arr[y, :, :]
    black = ((row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] < 50)).sum()
    white = ((row[:, 0] > 230) & (row[:, 1] > 230) & (row[:, 2] > 230)).sum()
    if black > 3 and white > 50:
        scrn_y = 540 + y
        print(f"  Text at screen y={scrn_y}")

# Click "3" at approximately (870, 575)
print("\nClicking '3' for 5G/6G at (870, 575)...")
pyautogui.click(870, 575)
time.sleep(1.0)

# Check result
ss2 = pyautogui.screenshot(region=(810, 530, 220, 45))
ss2.save("artifacts/labview_calibration/fix5g_result.png")

# Now try the orange arrow!
# Orange arrow center at (1143, 857) from pixel analysis
print("\nFull state check...")
ss3 = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss3.save("artifacts/labview_calibration/fix5g_before_arrow.png")

# Check error indicators
bottom_crop = ss3.crop((200, 900, 900, 1000))
bottom_crop.save("artifacts/labview_calibration/fix5g_errors.png")

print("Clicking orange arrow at (1143, 857)...")
pyautogui.click(1143, 857)
time.sleep(2.0)

# Check if screen changed
buf = ctypes.create_unicode_buffer(256)
u.GetWindowTextW(hwnd, buf, 256)
print(f"Window title: '{buf.value}'")

ss4 = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss4.save("artifacts/labview_calibration/fix5g_after_arrow.png")

print("Done")
