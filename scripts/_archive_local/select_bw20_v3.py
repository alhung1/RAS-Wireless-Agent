"""Scroll up in mode dropdown to find and click BW20."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# Close any open dropdown
pyautogui.press('escape')
time.sleep(0.5)

# Find and activate MODE window
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

# Click dropdown to open
print("Opening mode dropdown...")
pyautogui.click(249, 757)
time.sleep(1.0)

# Now scroll UP with mouse wheel while positioned on the dropdown list
# The list should be around x=200, y=730-770
print("Scrolling up with mouse wheel...")
for i in range(5):
    pyautogui.scroll(3, x=200, y=730)
    time.sleep(0.3)
    ss = pyautogui.screenshot()
    ss.crop((50, 680, 500, 810)).save(f"artifacts/labview_calibration/mode_scroll_up_{i+1}.png")

# Check what's visible now
ss_final = pyautogui.screenshot()
ss_final.crop((50, 680, 500, 810)).save("artifacts/labview_calibration/mode_scroll_final.png")

# If scroll didn't work, try pressing Up arrow many times
print("Trying Up arrow keys...")
pyautogui.press('up')
time.sleep(0.3)
pyautogui.press('up')
time.sleep(0.3)
pyautogui.press('up')
time.sleep(0.3)
pyautogui.press('up')
time.sleep(0.3)
pyautogui.press('up')
time.sleep(0.3)
pyautogui.press('up')
time.sleep(0.3)

ss_up = pyautogui.screenshot()
ss_up.crop((50, 680, 500, 810)).save("artifacts/labview_calibration/mode_after_up.png")

# Also save full view
ss_up.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/mode_full_after_nav.png")
