"""Select US from Region dropdown, then advance through final screens."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

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

ss = pyautogui.screenshot()
arr = np.array(ss)

# Find the small yellow Region dropdown (the one with "Not Valid" text)
# It appears to be a smaller dropdown on the left side
# Search for gray dropdown control (not the big yellow NOT VALID area)
print("Finding Region dropdown (gray/white dropdown):")

# The dropdown shows "Not Valid" text in a small box
# From the screenshot it's at approximately x=110-240, y=470-490
# Let me search for gray controls
for y in range(450, 520):
    row = arr[y, 80:300, :]
    gray = (row[:, 0] > 200) & (row[:, 0] < 240) & (row[:, 1] > 200) & (row[:, 1] < 240) & (row[:, 2] > 200) & (row[:, 2] < 240)
    gx = np.where(gray)[0]
    if len(gx) > 10:
        gx_abs = gx + 80
        print(f"  y={y}: gray x=[{gx_abs.min()},{gx_abs.max()}] count={len(gx)}")

# Also look for the "Not Valid" text in the dropdown
# It should be dark text on a white/gray background
for y in range(450, 520):
    row = arr[y, 80:300, :]
    dark = (row[:, 0] < 60) & (row[:, 1] < 60) & (row[:, 2] < 60)
    dx = np.where(dark)[0]
    if len(dx) > 0:
        dx_abs = dx + 80
        print(f"  y={y}: dark text at x={list(dx_abs)}")

# Crop the Region dropdown area
ss.crop((60, 440, 350, 520)).save("artifacts/labview_calibration/region_dropdown_area.png")

# Click the dropdown to open it
# From the screenshot, the dropdown appears at approximately x=180, y=480
print("\nClicking Region dropdown at (180, 480)...")
pyautogui.click(180, 480)
time.sleep(1.0)

# Screenshot
ss2 = pyautogui.screenshot()
ss2.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/region_dropdown_opened.png")
