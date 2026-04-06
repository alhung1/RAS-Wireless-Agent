"""Robustly focus Chariot window, find field, set to 8, advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

hwnd = 468496

def force_foreground(hwnd):
    """Robustly bring window to foreground using AttachThreadInput."""
    fg = u.GetForegroundWindow()
    fg_tid = u.GetWindowThreadProcessId(fg, None)
    my_tid = k.GetCurrentThreadId()
    
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, True)
    
    u.ShowWindow(hwnd, 9)  # SW_RESTORE
    u.BringWindowToTop(hwnd)
    u.SetForegroundWindow(hwnd)
    
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, False)
    
    time.sleep(0.5)
    
    actual_fg = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(actual_fg, buf, 256)
    print(f"Foreground now: '{buf.value}' (hwnd={actual_fg}, target={hwnd})")
    return actual_fg == hwnd

if not force_foreground(hwnd):
    print("WARNING: Could not bring window to foreground!")

# Wait for rendering
time.sleep(1.0)

# Take screenshot
ss = pyautogui.screenshot()
arr = np.array(ss)
print(f"Screenshot: {ss.size}")

# Comprehensive search for the yellow-green "4" field
# LabVIEW numeric controls often use: RGB(255, 255, 0) or RGB(100, 255, 0) etc.
print("\nSearching for yellow/green-ish fields (various criteria):")

# Criterion 1: Classic yellow (R~255, G~255, B~0)
for y in range(0, 1440, 3):
    row = arr[y, :1300, :]
    yel = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 50)
    yx = np.where(yel)[0]
    if len(yx) > 3:
        print(f"  YELLOW y={y}: x=[{yx.min()},{yx.max()}] sample=R{arr[y,yx[0],0]}G{arr[y,yx[0],1]}B{arr[y,yx[0],2]}")

# Criterion 2: Green-yellow (R>100, G>200, B<50)
for y in range(0, 1440, 3):
    row = arr[y, :1300, :]
    gy = (row[:, 0] > 100) & (row[:, 0] < 200) & (row[:, 1] > 200) & (row[:, 2] < 50)
    yx = np.where(gy)[0]
    if len(yx) > 3:
        print(f"  GREEN-Y y={y}: x=[{yx.min()},{yx.max()}] sample=R{arr[y,yx[0],0]}G{arr[y,yx[0],1]}B{arr[y,yx[0],2]}")

# Save the screenshot
ss.crop((0, 0, 1300, 1050)).save("artifacts/labview_calibration/pairs_robust.png")

# Also check what's actually at the expected coordinates
print("\nColor grid at center of window area:")
for y in range(200, 800, 20):
    colors = []
    for x in range(200, 800, 20):
        c = arr[y, x]
        colors.append(f"({c[0]},{c[1]},{c[2]})")
    if any("255,0" not in c or "23,255,255" not in c for c in colors[:3]):
        pass  # Print interesting rows only
    row_summary = arr[y, 200:800:20, :]
    unique_colors = set(tuple(row_summary[i]) for i in range(row_summary.shape[0]))
    if len(unique_colors) > 2:
        print(f"  y={y}: {len(unique_colors)} unique colors")
        for uc in sorted(unique_colors):
            print(f"    R={uc[0]} G={uc[1]} B={uc[2]}")
