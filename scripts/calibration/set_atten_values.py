"""Set Start atten=0, Step Size=3, Steps=30 and advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

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
fg = u.GetForegroundWindow()
fg_tid = u.GetWindowThreadProcessId(fg, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, fg_tid, True)
u.ShowWindow(hwnd, 9)
u.BringWindowToTop(hwnd)
u.SetForegroundWindow(hwnd)
u.AttachThreadInput(my_tid, fg_tid, False)
time.sleep(0.8)

# First, find the Steps field (further right)
ss = pyautogui.screenshot()
arr = np.array(ss)

# Check wider x-range for the Steps field
print("Looking for Steps field (yellow, x>600):")
for y in [490, 496, 500]:
    row = arr[y, 600:900, :]
    non_cyan = ~((row[:, 0] < 30) & (row[:, 1] > 240) & (row[:, 2] > 240))
    nx = np.where(non_cyan)[0]
    if len(nx) > 0:
        nx_abs = nx + 600
        clusters = []
        curr = nx_abs[0]
        for i in range(1, len(nx_abs)):
            if nx_abs[i] - nx_abs[i-1] > 5:
                clusters.append((curr, nx_abs[i-1]))
                curr = nx_abs[i]
        clusters.append((curr, nx_abs[-1]))
        print(f"  y={y}: {clusters}")

# Crop wider for verification
ss.crop((80, 440, 900, 540)).save("artifacts/labview_calibration/atten_wide.png")

# From the analysis:
# Field 1: Start atten at center (153, 496) - need to set to 0
# Field 2: End atten at center (404, 496) - leave as is
# Field 3: Step Size at center (566, 496) - need to set to 3
# Field 4: Steps at center (?) - need to set to 30

def click_clear_type(x, y, value):
    """Click a field, clear it, type new value."""
    pyautogui.click(x, y)
    time.sleep(0.3)
    pyautogui.tripleClick(x, y)
    time.sleep(0.2)
    # Clear with backspace
    for _ in range(5):
        pyautogui.press('backspace')
        time.sleep(0.05)
    pyautogui.typewrite(str(value), interval=0.05)
    time.sleep(0.3)
    pyautogui.press('tab')
    time.sleep(0.5)

# Set Start atten = 0
print("\nSetting Start atten = 0 at (153, 496)...")
click_clear_type(153, 496, 0)

# Set Step Size = 3
print("Setting Step Size = 3 at (566, 496)...")
click_clear_type(566, 496, 3)

# Check for Steps field position
ss2 = pyautogui.screenshot()
arr2 = np.array(ss2)
for y in [490, 496, 500]:
    row = arr2[y, 650:850, :]
    yel = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 100)
    yx = np.where(yel)[0]
    if len(yx) > 3:
        yx_abs = yx + 650
        cx = int((yx_abs.min() + yx_abs.max()) // 2)
        print(f"  Steps yellow at y={y}: x=[{yx_abs.min()},{yx_abs.max()}] center={cx}")

# The Steps field should be the 4th cluster 
# From earlier: x=[693,699] - let me try looking wider
for y in [490, 496, 500]:
    row = arr2[y, 670:800, :]
    non_cyan = ~((row[:, 0] < 30) & (row[:, 1] > 240) & (row[:, 2] > 240))
    non_bg = non_cyan & (row[:, 0] != 23)
    nx = np.where(non_bg)[0]
    if len(nx) > 0:
        nx_abs = nx + 670
        print(f"  Steps non-cyan at y={y}: x range [{nx_abs.min()},{nx_abs.max()}]")

# Set Steps = 30 (try at ~700, 496)
print("\nSetting Steps = 30 at (700, 496)...")
click_clear_type(700, 496, 30)

# Verify and save screenshot
ss3 = pyautogui.screenshot()
ss3.crop((80, 440, 900, 540)).save("artifacts/labview_calibration/atten_values_done.png")
ss3.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/atten_full_done.png")

# Find and click orange arrow
arr3 = np.array(ss3)
pts = []
for y in range(850, 1100):
    if y >= arr3.shape[0]:
        break
    row = arr3[y, 800:1300, :]
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

    fg2 = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(fg2, buf, 256)
    print(f"New window: '{buf.value}'")

    ss4 = pyautogui.screenshot()
    ss4.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_atten_advance.png")

print("Done")
