"""Click Region dropdown precisely and select US."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        if 'REGION' in buf.value:
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

# The dropdown control is at y=488-489, x=[143,299]
# The down-arrow should be near the right edge
# Let me click on the dropdown body (not the text)
# From the data, the "Not Valid" text is centered around x=166, y=475
# The gray dropdown extends from x=143 to x=299, centered at y=488

# Try clicking the dropdown arrow area (right side)
print("Clicking dropdown arrow at (295, 488)...")
pyautogui.click(295, 488)
time.sleep(1.0)

# Screenshot
ss = pyautogui.screenshot()
ss.crop((80, 450, 400, 600)).save("artifacts/labview_calibration/region_after_click.png")
ss.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/region_full_click.png")

# Check if dropdown opened
print("Checking if dropdown opened...")
arr = np.array(ss)
# Look for white list items
for y in range(490, 650):
    row = arr[y, 100:350, :]
    white = (row[:, 0] > 230) & (row[:, 1] > 230) & (row[:, 2] > 230)
    wx = np.where(white)[0]
    if len(wx) > 30:
        wx_abs = wx + 100
        print(f"  y={y}: white area x=[{wx_abs.min()},{wx_abs.max()}]")
        break
else:
    print("  No dropdown list detected!")
    # Try clicking directly on the yellow "Not Valid" dropdown
    # The yellow dropdown is at center (599, 499) from earlier
    print("  Trying the yellow dropdown center...")
    pyautogui.click(599, 499)
    time.sleep(1.0)
    ss2 = pyautogui.screenshot()
    ss2.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/region_yellow_click.png")
