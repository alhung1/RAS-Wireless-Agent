"""Step: Set mode to BW20, Graph Range already 100, then advance."""
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

# Find MODE window
windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if 'MODE' in buf.value:
            windows.append(hwnd)
    return True
u.EnumWindows(enum_cb, 0)

hwnd = windows[0] if windows else None
if not hwnd:
    print("MODE window not found!")
    sys.exit(1)

force_foreground(hwnd)
time.sleep(0.5)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Find the yellow "Not Valid" / mode dropdown
# Yellow: R>200, G>200, B<80 in the lower portion
print("Finding mode dropdown (yellow):")
for y in range(400, 700):
    row = arr[y, 50:400, :]
    yellow = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 80)
    yx = np.where(yellow)[0]
    if len(yx) > 15:
        yx_abs = yx + 50
        print(f"  y={y}: x=[{yx_abs.min()},{yx_abs.max()}] count={len(yx)}")

# From the screenshot, the mode dropdown appears at approximately:
# x ~ 100-280, y ~ 560 (in the lower portion of the window)
# Let me find it precisely
yellow_rows = []
for y in range(500, 650):
    row = arr[y, 50:400, :]
    yellow = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 80)
    yx = np.where(yellow)[0]
    if len(yx) > 15:
        yx_abs = yx + 50
        yellow_rows.append((y, yx_abs.min(), yx_abs.max()))

if yellow_rows:
    y_min = min(r[0] for r in yellow_rows)
    y_max = max(r[0] for r in yellow_rows)
    x_min = min(r[1] for r in yellow_rows)
    x_max = max(r[2] for r in yellow_rows)
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    print(f"  Mode dropdown: x=[{x_min},{x_max}] y=[{y_min},{y_max}] center=({cx},{cy})")
    
    # Click the dropdown
    print(f"\nClicking mode dropdown at ({cx}, {cy})...")
    pyautogui.click(cx, cy)
    time.sleep(1.0)
    
    # Screenshot to see dropdown options
    ss2 = pyautogui.screenshot()
    ss2.crop((50, cy-50, 500, cy+200)).save("artifacts/labview_calibration/mode_dropdown_open.png")
    
    # Look for BW20 in the dropdown list
    # The dropdown list should have appeared below the dropdown
    # Search for the text or just click the right option
    arr2 = np.array(ss2)
    print("Dropdown screenshot saved. Looking for list items...")
    
    # The dropdown items will be white/gray text on white/gray background
    # BW20 should be one of the items. Let's click on the dropdown arrow first
    # Actually, let me check if a list appeared
    
else:
    print("  Mode dropdown NOT FOUND with yellow search!")
    # Try broader: the dropdown has a gray dropdown arrow
    # Search for it in the lower-left
    print("  Trying alternative search...")
