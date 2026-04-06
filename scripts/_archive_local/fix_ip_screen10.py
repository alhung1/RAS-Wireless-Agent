"""Click at correct positions: dropdown at precise coords, orange arrow at (1143, 857)."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Dismiss JPEG dialog
u.keybd_event(0x1B, 0, 0, 0)
time.sleep(0.05)
u.keybd_event(0x1B, 0, 0x0002, 0)
time.sleep(0.5)

# Take screenshot and crop just the 2G/MLO dropdown for precise measurement
ss = pyautogui.screenshot()
# Crop tight around "2G/MLO to use (1..5)" label and dropdown
# From mid_wide crop at (200, 400): the section is around (250, 80) to (470, 170)
# Screen: (450, 480) to (670, 570)
tight_crop = ss.crop((380, 480, 700, 600))
tight_crop.save("artifacts/labview_calibration/step12_tight_dropdown.png")
print(f"Tight dropdown crop: {tight_crop.size}")

# Find the gray arrow triangle pixel position
arr = np.array(tight_crop)
# Gray pixels: R,G,B all between 150-210
gray_mask = (arr[:, :, 0] > 150) & (arr[:, :, 0] < 220) & \
            (arr[:, :, 1] > 150) & (arr[:, :, 1] < 220) & \
            (arr[:, :, 2] > 150) & (arr[:, :, 2] < 220)
gray_pixels = np.where(gray_mask)
if len(gray_pixels[0]) > 0:
    # Find the gray cluster that is the arrow button
    # It should be on the right side of the "Not Valid" text
    gy = gray_pixels[0]
    gx = gray_pixels[1]
    # Filter for right half of the crop
    right = gx > tight_crop.size[0] // 2
    if right.any():
        print(f"Gray pixels (right half): x=[{gx[right].min()}, {gx[right].max()}], y=[{gy[right].min()}, {gy[right].max()}]")
        # Center of gray arrow button
        arrow_cx = (gx[right].min() + gx[right].max()) // 2
        arrow_cy = (gy[right].min() + gy[right].max()) // 2
        # Convert back to screen coordinates
        screen_arrow_x = 380 + arrow_cx
        screen_arrow_y = 480 + arrow_cy
        print(f"Dropdown arrow center (screen): ({screen_arrow_x}, {screen_arrow_y})")

# Attach thread
tid = u.GetWindowThreadProcessId(hwnd, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, tid, True)
time.sleep(0.2)
u.SetForegroundWindow(hwnd)
time.sleep(0.2)
u.SetFocus(hwnd)
time.sleep(0.2)

try:
    # =========================================================
    # Try clicking on the precise gray arrow button
    # =========================================================
    if 'screen_arrow_x' in dir():
        print(f"\nClicking dropdown arrow at ({screen_arrow_x}, {screen_arrow_y})...")
        pyautogui.click(screen_arrow_x, screen_arrow_y)
        time.sleep(1.0)

        ss2 = pyautogui.screenshot(region=(380, 480, 320, 200))
        ss2.save("artifacts/labview_calibration/step12_dropdown_clicked.png")

        # Check if it opened
        # Try scrolling if something opened
        pyautogui.scroll(3)
        time.sleep(0.5)

        ss3 = pyautogui.screenshot(region=(380, 480, 320, 200))
        ss3.save("artifacts/labview_calibration/step12_dropdown_scrolled.png")

    # =========================================================
    # Try clicking the orange right arrow at correct position
    # =========================================================
    print("\nClicking orange right arrow at (1143, 857)...")
    pyautogui.click(1143, 857)
    time.sleep(2.0)

    # Check if screen changed
    ss4 = pyautogui.screenshot()
    # Check window title
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(hwnd, buf, 256)
    print(f"Window title after arrow click: '{buf.value}'")

    # Crop the title area
    title_crop = ss4.crop((0, 0, 800, 30))
    title_crop.save("artifacts/labview_calibration/step12_after_correct_arrow.png")

    # Full screenshot
    ss4_full = ss4.crop((0, 0, 1600, 1100))
    ss4_full.save("artifacts/labview_calibration/step12_full_after_arrow.png")

finally:
    u.AttachThreadInput(my_tid, tid, False)

print("Done")
