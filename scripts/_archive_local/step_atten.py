"""Step: Set Start atten=0, Step Size=3, Steps=30, then advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

def force_foreground(hwnd):
    fg = u.GetForegroundWindow()
    fg_tid = u.GetWindowThreadProcessId(fg, None)
    my_tid = k.GetCurrentThreadId()
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, True)
    u.ShowWindow(hwnd, 9)
    u.BringWindowToTop(hwnd)
    u.SetForegroundWindow(hwnd)
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, False)
    time.sleep(0.5)

# Find atten window
windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if 'atten' in buf.value.lower():
            windows.append(hwnd)
    return True
u.EnumWindows(enum_cb, 0)

hwnd = windows[0]
force_foreground(hwnd)
time.sleep(0.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Find yellow fields (Start atten, Step Size, Steps)
# Yellow: R>200, G>200, B<80 or lime green R~100,G~255,B~0
print("Finding yellow fields in atten screen...")
yellow_fields = []
for y in range(300, 500):
    row = arr[y, 50:700, :]
    yellow = ((row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 80)) | \
             ((row[:, 0] > 80) & (row[:, 0] < 130) & (row[:, 1] > 240) & (row[:, 2] < 20))
    yx = np.where(yellow)[0]
    if len(yx) > 3:
        yx_abs = yx + 50
        yellow_fields.append((y, yx_abs.min(), yx_abs.max()))

# Group by x-position clusters
if yellow_fields:
    # Separate into distinct field groups by x-position
    all_x_ranges = set()
    for _, xmin, xmax in yellow_fields:
        all_x_ranges.add((xmin, xmax))
    
    # Find unique field positions
    print(f"  Found {len(yellow_fields)} yellow rows")
    
    # Group by continuous x-ranges
    from collections import defaultdict
    x_groups = defaultdict(list)
    for y, xmin, xmax in yellow_fields:
        matched = False
        for key in list(x_groups.keys()):
            if abs(xmin - key[0]) < 30:
                x_groups[key].append((y, xmin, xmax))
                matched = True
                break
        if not matched:
            x_groups[(xmin, xmax)].append((y, xmin, xmax))
    
    fields = []
    for key, rows in sorted(x_groups.items()):
        y_min = min(r[0] for r in rows)
        y_max = max(r[0] for r in rows)
        x_min = min(r[1] for r in rows)
        x_max = max(r[2] for r in rows)
        cx = (x_min + x_max) // 2
        cy = (y_min + y_max) // 2
        fields.append((cx, cy, x_min, x_max, y_min, y_max))
        print(f"  Field: x=[{x_min},{x_max}] y=[{y_min},{y_max}] center=({cx},{cy})")

# The three yellow fields should be: Start atten, Step Size, Steps
# From the screenshot they appear left to right
if len(fields) >= 3:
    # Sort by x position
    fields.sort(key=lambda f: f[0])
    
    configs = [
        ("Start atten", fields[0], "0"),
        ("Step Size", fields[1], "3"),
        ("Steps", fields[2], "30"),
    ]
    
    for name, (cx, cy, *_), value in configs:
        print(f"\nSetting {name} to {value} at ({cx}, {cy})...")
        pyautogui.click(cx, cy)
        time.sleep(0.3)
        pyautogui.tripleClick(cx, cy)
        time.sleep(0.2)
        pyautogui.press('backspace')
        time.sleep(0.1)
        pyautogui.press('backspace')
        time.sleep(0.1)
        pyautogui.press('backspace')
        time.sleep(0.1)
        pyautogui.typewrite(value, interval=0.05)
        time.sleep(0.3)
        pyautogui.press('tab')
        time.sleep(0.5)
    
    # Screenshot to verify
    ss2 = pyautogui.screenshot()
    ss2.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/atten_values_set.png")
    
    # Find and click orange arrow
    arr2 = np.array(ss2)
    pts = []
    for y in range(850, 1100):
        if y >= arr2.shape[0]:
            break
        row = arr2[y, 800:1300, :]
        orange = (row[:, 0] > 200) & (row[:, 1] > 130) & (row[:, 1] < 190) & (row[:, 2] < 80)
        ox = np.where(orange)[0]
        if len(ox) > 3:
            pts.append((y, ox.min() + 800, ox.max() + 800))
    
    if pts:
        acx = (min(p[1] for p in pts) + max(p[2] for p in pts)) // 2
        acy = (min(p[0] for p in pts) + max(p[0] for p in pts)) // 2
        print(f"\nClicking orange arrow at ({acx}, {acy})...")
        pyautogui.click(acx, acy)
        time.sleep(3.0)
        
        fg = u.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(fg, buf, 256)
        print(f"Current window: '{buf.value}'")
        
        ss3 = pyautogui.screenshot()
        ss3.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_atten_advance.png")
else:
    print(f"  Expected 3 fields, found {len(fields) if 'fields' in dir() else 0}")
    # Fallback: try manual coordinates based on the screenshot
    print("  Trying manual coordinates...")

print("Done")
