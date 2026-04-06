"""Click mode dropdown, select BW20, then advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# Force foreground
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

# Step 1: Click the mode dropdown at (249, 757)
print("Clicking mode dropdown at (249, 757)...")
pyautogui.click(249, 757)
time.sleep(1.5)

# Screenshot to see dropdown list
ss = pyautogui.screenshot()
ss.crop((50, 700, 500, 950)).save("artifacts/labview_calibration/mode_dropdown_list.png")
arr = np.array(ss)
print(f"Screenshot taken")

# Save wider view
ss.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/mode_list_full.png")

# Analyze the dropdown list area for white/light items
print("Analyzing dropdown list area (y=770-900, x=100-400):")
for y in range(760, 900, 3):
    row = arr[y, 100:400, :]
    white = (row[:, 0] > 230) & (row[:, 1] > 230) & (row[:, 2] > 230)
    wx = np.where(white)[0]
    if len(wx) > 20:
        wx_abs = wx + 100
        print(f"  y={y}: white x=[{wx_abs.min()},{wx_abs.max()}] count={len(wx)}")
