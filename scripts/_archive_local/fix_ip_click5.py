"""Try clicking increment arrows on the dropdown, and precisely locate all buttons."""
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

# Take a very zoomed screenshot of just the dropdown arrow area
ss = pyautogui.screenshot()

# The dropdown "Not Valid" with arrow button is visible in the middle crop
# Let me crop the exact arrow button area
# From click4_dropdown_opened.png at offset (300, 470):
#   Arrow area is at approximately (540, 520) to (570, 548) in screen coords
arrow_zoom = ss.crop((530, 510, 580, 555))
arrow_zoom.save("artifacts/labview_calibration/click5_arrow_zoom.png")
arr = np.array(arrow_zoom)
print(f"Arrow zoom: {arrow_zoom.size}")
print("Arrow pixel dump:")
for y in range(arr.shape[0]):
    row = ""
    for x in range(arr.shape[1]):
        px = arr[y, x]
        if px[0] > 180 and px[1] > 180 and px[2] > 180:
            row += "G"  # Gray
        elif px[0] > 200 and px[1] > 200 and px[2] < 50:
            row += "Y"  # Yellow
        elif px[0] < 50 and px[1] > 200 and px[2] > 200:
            row += "C"  # Cyan
        elif px[0] < 50 and px[1] < 50 and px[2] < 50:
            row += "B"  # Black
        elif px[0] > 200 and px[1] > 200 and px[2] > 200:
            row += "W"  # White
        else:
            row += f"?"
    print(f"  y={y}: {row}  [{arr[y,0,0]},{arr[y,0,1]},{arr[y,0,2]}]...[{arr[y,-1,0]},{arr[y,-1,1]},{arr[y,-1,2]}]")

# Now try clicking at specific positions within the arrow area
# The arrow is likely at screen coordinates around (550, 525) for up-arrow
# and (550, 540) for down-arrow
positions = [
    (548, 520, "arrow_top"),
    (548, 525, "arrow_up_center"),
    (548, 530, "arrow_middle"),
    (548, 535, "arrow_down_center"),
    (548, 540, "arrow_bottom"),
    (540, 525, "arrow_left"),
    (555, 525, "arrow_right"),
]

for x, y, label in positions:
    print(f"\nClicking {label} at ({x}, {y})...")
    pyautogui.click(x, y)
    time.sleep(0.8)

    # Check if value changed
    check = pyautogui.screenshot(region=(380, 510, 200, 40))
    check_arr = np.array(check)
    # Look for text that's NOT "Not Valid" - check if pixels differ
    check.save(f"artifacts/labview_calibration/click5_{label}.png")

# Full screenshot at the end
ss_final = pyautogui.screenshot(region=(300, 470, 500, 150))
ss_final.save("artifacts/labview_calibration/click5_final.png")

print("\nDone")
