"""Set Design cycle Stage to Beta, then advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# Find Chariot window
windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if 'Chariot' in buf.value:
            windows.append(hwnd)
    return True
u.EnumWindows(enum_cb, 0)

hwnd = windows[0]
fg = u.GetForegroundWindow()
fg_tid = u.GetWindowThreadProcessId(fg, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, fg_tid, True)
u.ShowWindow(hwnd, 9)
u.BringWindowToTop(hwnd)
u.SetForegroundWindow(hwnd)
u.AttachThreadInput(my_tid, fg_tid, False)
time.sleep(0.8)

ss = pyautogui.screenshot()
arr = np.array(ss)

# Find "Design cycle Stage" dropdown (yellow background)
print("Finding yellow dropdowns:")
for y in range(300, 700):
    row = arr[y, 400:800, :]
    yellow = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 80)
    yx = np.where(yellow)[0]
    if len(yx) > 15:
        yx_abs = yx + 400
        print(f"  y={y}: x=[{yx_abs.min()},{yx_abs.max()}] count={len(yx)}")

# The first large yellow region should be "Design cycle Stage"
yellow_rows = []
for y in range(300, 500):
    row = arr[y, 400:800, :]
    yellow = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 80)
    yx = np.where(yellow)[0]
    if len(yx) > 15:
        yx_abs = yx + 400
        yellow_rows.append((y, yx_abs.min(), yx_abs.max()))

if yellow_rows:
    y_min = min(r[0] for r in yellow_rows)
    y_max = max(r[0] for r in yellow_rows)
    x_min = min(r[1] for r in yellow_rows)
    x_max = max(r[2] for r in yellow_rows)
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    print(f"\nDesign cycle Stage dropdown: center=({cx},{cy})")
    
    # Click dropdown
    print(f"Clicking at ({cx}, {cy})...")
    pyautogui.click(cx, cy)
    time.sleep(1.0)
    
    # Screenshot list
    ss2 = pyautogui.screenshot()
    ss2.crop((400, cy-50, 800, cy+200)).save("artifacts/labview_calibration/stage_dropdown_list.png")
    
    # Press Home to go to top
    pyautogui.press('home')
    time.sleep(0.3)
    
    # Navigate to find "Beta"
    # Try pressing Down until we find Beta
    for i in range(15):
        pyautogui.press('up')
        time.sleep(0.2)
    
    # Now go down to find Beta
    ss3 = pyautogui.screenshot()
    ss3.crop((400, cy-100, 800, cy+250)).save("artifacts/labview_calibration/stage_list_top.png")
    ss3.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/stage_list_full.png")
