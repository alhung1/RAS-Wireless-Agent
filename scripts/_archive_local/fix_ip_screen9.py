"""Find exact orange arrow position and try to interact with dropdown via pywinauto."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from PIL import Image
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Take full screenshot
ss = pyautogui.screenshot()
print(f"Full screenshot: {ss.size}")
arr = np.array(ss)

# Find orange pixels (the arrow is orange/tan colored)
# Orange typically: R > 200, G > 140, B < 100
orange_mask = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 140) & (arr[:, :, 1] < 200) & (arr[:, :, 2] < 100)
orange_pixels = np.where(orange_mask)

if len(orange_pixels[0]) > 0:
    # Find clusters of orange pixels
    y_coords = orange_pixels[0]
    x_coords = orange_pixels[1]

    # Bottom-right orange arrow: filter for bottom half and right half
    bottom_right = (y_coords > ss.size[1] // 2) & (x_coords > ss.size[0] // 4)
    br_y = y_coords[bottom_right]
    br_x = x_coords[bottom_right]

    if len(br_y) > 0:
        print(f"Bottom-right orange pixel range: x=[{br_x.min()}, {br_x.max()}], y=[{br_y.min()}, {br_y.max()}]")
        center_x = (br_x.min() + br_x.max()) // 2
        center_y = (br_y.min() + br_y.max()) // 2
        print(f"Orange arrow center: ({center_x}, {center_y})")

    # Also find bottom-left orange (back arrow)
    bottom_left = (y_coords > ss.size[1] // 2) & (x_coords < ss.size[0] // 4)
    bl_y = y_coords[bottom_left]
    bl_x = x_coords[bottom_left]

    if len(bl_y) > 0:
        print(f"Bottom-left orange pixel range: x=[{bl_x.min()}, {bl_x.max()}], y=[{bl_y.min()}, {bl_y.max()}]")
else:
    print("No orange pixels found!")

# Let me also look at the area around (765, 600) in the screenshot
print("\nSampling pixels around previous click target (765, 608):")
for dy in range(-5, 6, 5):
    for dx in range(-5, 6, 5):
        px = arr[608 + dy, 765 + dx]
        print(f"  ({765+dx}, {608+dy}): RGB=({px[0]}, {px[1]}, {px[2]})")

# Crop the bottom section (full width)
bottom_full = ss.crop((0, 800, 2560, 1440))
bottom_full.save("artifacts/labview_calibration/step12_bottom_full_2560.png")
print(f"\nFull bottom crop saved: {bottom_full.size}")

# Also try pywinauto to inspect controls
try:
    from pywinauto import Application
    print("\nAttempting pywinauto UIA inspection...")
    app = Application(backend="uia").connect(handle=hwnd)
    win = app.window(handle=hwnd)

    # Try to dump the control tree
    controls = []
    try:
        for ctrl in win.descendants():
            name = ctrl.element_info.name or ""
            ctrl_type = ctrl.element_info.control_type or ""
            rect = ctrl.element_info.rectangle
            if name or ctrl_type:
                controls.append(f"  {ctrl_type}: '{name}' at ({rect.left},{rect.top},{rect.right},{rect.bottom})")
    except Exception as e:
        print(f"  Error iterating: {e}")

    if controls:
        print(f"Found {len(controls)} controls:")
        for c in controls[:30]:
            print(c)
    else:
        print("  No controls found via UIA")

except ImportError:
    print("\npywinauto not installed, skipping UIA inspection")
except Exception as e:
    print(f"\npywinauto error: {e}")

print("\nDone")
