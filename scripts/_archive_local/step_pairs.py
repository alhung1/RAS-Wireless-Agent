"""Step 13: Set Number of pairs 2G/MLO to 8, then advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

# Find the Chariot pairs window
windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if 'Chariot pairs' in buf.value:
            rect = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(rect))
            windows.append((hwnd, buf.value, rect.left, rect.top, rect.right, rect.bottom))
    return True
u.EnumWindows(enum_cb, 0)

if windows:
    hwnd = windows[0][0]
    print(f"Window: '{windows[0][1]}' rect=({windows[0][2]},{windows[0][3]},{windows[0][4]},{windows[0][5]})")
else:
    print("Chariot pairs window not found!")
    sys.exit(1)

u.SetForegroundWindow(hwnd)
time.sleep(0.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Find yellow fields (Number of pairs 2G/MLO and 5G/6G)
print("Searching for yellow fields...")
yellow_regions = []
for y in range(200, 700):
    row = arr[y, 300:600, :]
    yellow = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 100)
    yx = np.where(yellow)[0]
    if len(yx) > 20:
        yx_abs = yx + 300
        yellow_regions.append((y, yx_abs.min(), yx_abs.max()))

if yellow_regions:
    # Group by continuous y-ranges
    groups = []
    curr = [yellow_regions[0]]
    for i in range(1, len(yellow_regions)):
        if yellow_regions[i][0] - yellow_regions[i-1][0] <= 2:
            curr.append(yellow_regions[i])
        else:
            groups.append(curr)
            curr = [yellow_regions[i]]
    groups.append(curr)
    
    for idx, g in enumerate(groups):
        y_min = g[0][0]
        y_max = g[-1][0]
        x_min = min(r[1] for r in g)
        x_max = max(r[2] for r in g)
        cx = (x_min + x_max) // 2
        cy = (y_min + y_max) // 2
        print(f"  Yellow field {idx}: y=[{y_min},{y_max}] x=[{x_min},{x_max}] center=({cx},{cy})")

# The first yellow field should be "Number of pairs 2G/MLO"
# Click it, clear, type 8
if groups:
    g = groups[0]
    cx = (min(r[1] for r in g) + max(r[2] for r in g)) // 2
    cy = (g[0][0] + g[-1][0]) // 2
    
    print(f"\nClicking 2G/MLO pairs field at ({cx}, {cy})...")
    pyautogui.click(cx, cy)
    time.sleep(0.5)
    
    # Triple-click to select all, then type
    pyautogui.tripleClick(cx, cy)
    time.sleep(0.3)
    pyautogui.press('delete')
    time.sleep(0.2)
    pyautogui.typewrite('8', interval=0.1)
    time.sleep(0.5)
    
    # Click elsewhere to confirm
    pyautogui.click(cx + 100, cy)
    time.sleep(1.0)
    
    ss2 = pyautogui.screenshot()
    ss2.crop((0, 0, 1400, 800)).save("artifacts/labview_calibration/pairs_after_8.png")
    
    # Find and click orange arrow
    arr2 = np.array(ss2)
    region = arr2[850:1050, 1050:1300, :]
    orange = (region[:, :, 0] > 200) & (region[:, :, 1] > 130) & (region[:, :, 1] < 190) & (region[:, :, 2] < 80)
    oy, ox = np.where(orange)
    if len(oy) > 0:
        acx = int(ox.mean()) + 1050
        acy = int(oy.mean()) + 850
        print(f"Orange arrow at ({acx}, {acy})")
        
        print("Clicking orange arrow...")
        pyautogui.click(acx, acy)
        time.sleep(3.0)
        
        buf = ctypes.create_unicode_buffer(256)
        fg = u.GetForegroundWindow()
        u.GetWindowTextW(fg, buf, 256)
        print(f"Current foreground: '{buf.value}'")
        
        ss3 = pyautogui.screenshot()
        ss3.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_pairs_arrow.png")
    else:
        print("Orange arrow not found!")

print("Done")
