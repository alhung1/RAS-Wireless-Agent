"""Find and click the Number of pairs 2G/MLO field, set to 8, advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

hwnd = 468496

def force_foreground(h):
    fg = u.GetForegroundWindow()
    fg_tid = u.GetWindowThreadProcessId(fg, None)
    my_tid = k.GetCurrentThreadId()
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, True)
    u.ShowWindow(h, 9)
    u.BringWindowToTop(h)
    u.SetForegroundWindow(h)
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, False)
    time.sleep(0.5)

force_foreground(hwnd)
time.sleep(0.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Find lime green (R=100, G=255, B=0) fields precisely
print("Finding lime green fields (Number of pairs):")
green_2g = []
green_5g = []
for y in range(300, 500):
    row = arr[y, :800, :]
    green = (row[:, 0] > 80) & (row[:, 0] < 130) & (row[:, 1] > 240) & (row[:, 2] < 20)
    gx = np.where(green)[0]
    if len(gx) > 3:
        green_2g.append((y, gx.min(), gx.max()))

for y in range(600, 800):
    row = arr[y, :800, :]
    green = (row[:, 0] > 80) & (row[:, 0] < 130) & (row[:, 1] > 240) & (row[:, 2] < 20)
    gx = np.where(green)[0]
    if len(gx) > 3:
        green_5g.append((y, gx.min(), gx.max()))

if green_2g:
    y_min = min(r[0] for r in green_2g)
    y_max = max(r[0] for r in green_2g)
    x_min = min(r[1] for r in green_2g)
    x_max = max(r[2] for r in green_2g)
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    print(f"  2G/MLO field: x=[{x_min},{x_max}] y=[{y_min},{y_max}] center=({cx},{cy})")
else:
    print("  2G/MLO field NOT FOUND!")

if green_5g:
    y_min = min(r[0] for r in green_5g)
    y_max = max(r[0] for r in green_5g)
    x_min = min(r[1] for r in green_5g)
    x_max = max(r[2] for r in green_5g)
    cx5 = (x_min + x_max) // 2
    cy5 = (y_min + y_max) // 2
    print(f"  5G/6G field:  x=[{x_min},{x_max}] y=[{y_min},{y_max}] center=({cx5},{cy5})")

# Also find orange right arrow
arrow_pts = []
for y in range(900, 1050):
    row = arr[y, 1100:1300, :]
    orange = (row[:, 0] > 200) & (row[:, 1] > 130) & (row[:, 1] < 190) & (row[:, 2] < 80)
    ox = np.where(orange)[0]
    if len(ox) > 3:
        arrow_pts.append((y, ox.min() + 1100, ox.max() + 1100))

if arrow_pts:
    ay_min = min(r[0] for r in arrow_pts)
    ay_max = max(r[0] for r in arrow_pts)
    ax_min = min(r[1] for r in arrow_pts)
    ax_max = max(r[2] for r in arrow_pts)
    acx = (ax_min + ax_max) // 2
    acy = (ay_min + ay_max) // 2
    print(f"  Right arrow: center=({acx},{acy})")

if not green_2g:
    print("Cannot proceed - field not found!")
    sys.exit(1)

# Click the 2G/MLO pairs field
print(f"\n--- STEP 1: Click 2G/MLO field at ({cx}, {cy}) ---")
pyautogui.click(cx, cy)
time.sleep(0.5)

# Triple click to select, then type 8
pyautogui.tripleClick(cx, cy)
time.sleep(0.3)
pyautogui.press('backspace')
time.sleep(0.2)
pyautogui.press('backspace')
time.sleep(0.2)
pyautogui.typewrite('8', interval=0.1)
time.sleep(0.3)

# Click elsewhere to confirm the value
pyautogui.press('tab')
time.sleep(1.0)

# Screenshot to verify
ss2 = pyautogui.screenshot()
ss2.crop((0, 0, 1300, 1050)).save("artifacts/labview_calibration/pairs_set_8.png")

# Verify the field now shows 8
arr2 = np.array(ss2)
print("Checking field value after input...")

# Step 2: Click orange arrow
print(f"\n--- STEP 2: Click orange arrow at ({acx}, {acy}) ---")
pyautogui.click(acx, acy)
time.sleep(3.0)

# Check result
fg = u.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(256)
u.GetWindowTextW(fg, buf, 256)
print(f"Current foreground: '{buf.value}'")

ss3 = pyautogui.screenshot()
ss3.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_pairs_advance.png")
print("Done")
