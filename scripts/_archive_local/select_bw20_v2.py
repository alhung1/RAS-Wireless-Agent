"""Select BW20 using keyboard navigation in the dropdown."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# First, close the dropdown by pressing Escape
print("Closing any open dropdown...")
pyautogui.press('escape')
time.sleep(0.5)

# Re-find MODE window
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

# Click the dropdown to open it
print("Opening mode dropdown...")
pyautogui.click(249, 757)
time.sleep(1.0)

# Take screenshot to see what's in the list
ss = pyautogui.screenshot()
ss.crop((50, 600, 500, 850)).save("artifacts/labview_calibration/mode_list_opened.png")

# Try pressing Home key to go to top of list, then Down to find BW20
print("Pressing Home to go to top of list...")
pyautogui.press('home')
time.sleep(0.3)

ss2 = pyautogui.screenshot()
ss2.crop((50, 600, 500, 850)).save("artifacts/labview_calibration/mode_list_home.png")

# Now press Down to navigate through items
# BW20 should be near the top. Let me try pressing down a few times
# and check after each
for i in range(8):
    pyautogui.press('down')
    time.sleep(0.3)
    ss3 = pyautogui.screenshot()
    arr3 = np.array(ss3)
    # Check what's highlighted (look for blue/highlighted selection)
    for y in range(700, 800):
        row = arr3[y, 100:400, :]
        blue = (row[:, 0] < 100) & (row[:, 1] < 100) & (row[:, 2] > 150)
        bx = np.where(blue)[0]
        if len(bx) > 10:
            bx_abs = bx + 100
            print(f"  Down {i+1}: Highlight at y={y}, x=[{bx_abs.min()},{bx_abs.max()}]")
            break
    ss3.crop((50, 680, 500, 800)).save(f"artifacts/labview_calibration/mode_down_{i+1}.png")

print("Done navigating. Check screenshots.")
