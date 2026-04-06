"""Precise dropdown interaction: zoom in on arrow, try grid clicks."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

KEYEVENTF_KEYUP = 0x0002
VK_ESCAPE = 0x1B

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Dismiss JPEG dialog
u.keybd_event(VK_ESCAPE, 0, 0, 0)
time.sleep(0.05)
u.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
time.sleep(0.5)

# Take a very tight screenshot of just the 2G/MLO dropdown button
# Including the arrow triangle on the right
ss = pyautogui.screenshot()

# Crop even tighter: just the "Not Valid ▼" part
# The dropdown with arrow is approximately (400, 515) to (570, 545) in 2560x1440
dropdown_crop = ss.crop((400, 510, 580, 555))
dropdown_crop.save("artifacts/labview_calibration/step12_dropdown_zoom.png")
print(f"Dropdown zoom: {dropdown_crop.size}")

# Also crop the LabVIEW toolbar area to check if it's in Run or Edit mode
toolbar_crop = ss.crop((0, 30, 300, 65))
toolbar_crop.save("artifacts/labview_calibration/step12_toolbar.png")

# Save the dropdown area as numpy array to find the arrow button
arr = np.array(dropdown_crop)
print(f"Dropdown image shape: {arr.shape}")

# Print pixel values along the right edge where the arrow should be
print("\nPixels along right portion of dropdown (x from 130 to 179):")
for y in range(0, arr.shape[0], 5):
    row_px = [f"({arr[y,x,0]},{arr[y,x,1]},{arr[y,x,2]})" for x in range(130, min(180, arr.shape[1]), 10)]
    print(f"  y={y}: {' '.join(row_px)}")

# Attach thread input
tid = u.GetWindowThreadProcessId(hwnd, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, tid, True)
time.sleep(0.2)
u.SetForegroundWindow(hwnd)
time.sleep(0.2)
u.SetFocus(hwnd)
time.sleep(0.2)

try:
    # Grid of clicks across the dropdown area
    # Start from the yellow "Not Valid" text and go to the gray arrow
    test_positions = [
        (440, 525, "yellow_text_left"),
        (480, 525, "yellow_text_center"),
        (520, 525, "yellow_text_right"),
        (550, 525, "arrow_left"),
        (565, 525, "arrow_center"),
        (570, 525, "arrow_right"),
        (555, 518, "arrow_top"),
        (555, 535, "arrow_bottom"),
    ]

    for x, y, label in test_positions:
        print(f"\nClicking {label} at ({x}, {y})...")
        pyautogui.click(x, y)
        time.sleep(0.5)

        # Check if dropdown opened or value changed
        check = pyautogui.screenshot(region=(400, 500, 250, 100))
        # Compare to see if "Not Valid" changed
        check_arr = np.array(check)
        # Check for non-yellow, non-cyan colors (which would indicate a dropdown opened)
        not_standard = ~((check_arr[:, :, 0] > 200) & (check_arr[:, :, 1] > 200) & (check_arr[:, :, 2] < 100)) & \
                       ~((check_arr[:, :, 0] < 50) & (check_arr[:, :, 1] > 200) & (check_arr[:, :, 2] > 200)) & \
                       ~((check_arr[:, :, 0] > 150) & (check_arr[:, :, 1] > 150) & (check_arr[:, :, 2] > 150))
        unusual_pct = not_standard.sum() / not_standard.size * 100
        if unusual_pct > 5:
            print(f"  ** Unusual pixels detected ({unusual_pct:.1f}%) - dropdown might have opened!")
            check.save(f"artifacts/labview_calibration/step12_grid_{label}.png")

    # Also try using LabVIEW's Edit menu
    print("\n\nTrying LabVIEW Edit menu...")
    # The Edit menu should be at the top of the window
    # Edit menu position: approximately x=33, y=23 (second menu after File)
    pyautogui.click(42, 25)  # File menu
    time.sleep(0.5)
    menu_ss = pyautogui.screenshot(region=(0, 0, 300, 400))
    menu_ss.save("artifacts/labview_calibration/step12_file_menu.png")
    
    # Press Escape to close menu
    pyautogui.press('escape')
    time.sleep(0.3)

    # Try Operate menu
    pyautogui.click(127, 25)  # Operate menu (estimate)
    time.sleep(0.5)
    op_ss = pyautogui.screenshot(region=(0, 0, 400, 400))
    op_ss.save("artifacts/labview_calibration/step12_operate_menu.png")
    
    pyautogui.press('escape')
    time.sleep(0.3)

    # Full screenshot
    full_ss = pyautogui.screenshot(region=(0, 0, 1600, 1100))
    full_ss.save("artifacts/labview_calibration/step12_grid_final.png")

finally:
    u.AttachThreadInput(my_tid, tid, False)

print("\nDone")
