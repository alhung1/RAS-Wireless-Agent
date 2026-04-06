"""Set atten values using visual coordinates from screenshot."""
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

ss = pyautogui.screenshot()
arr = np.array(ss)

# Sample colors at the expected field locations
# From the screenshot, fields appear to be yellow with blue text
# at approximately y=380, x=120 (Start atten), x=420 (Step Size), x=545 (Steps)
print("Color sampling at expected field positions:")
test_points = [
    (120, 380), (130, 380), (140, 380),  # Start atten
    (410, 380), (420, 380), (430, 380),  # Step Size
    (540, 380), (550, 380), (560, 380),  # Steps
]
for x, y in test_points:
    c = arr[y, x]
    print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")

# Try DPI-adjusted coordinates (1.25x)
print("\nDPI-adjusted coordinates (1.25x):")
dpi_points = [
    (150, 475), (160, 475), (170, 475),  # Start atten * 1.25
    (525, 475), (535, 475), (545, 475),  # Step Size * 1.25
    (680, 475), (690, 475), (700, 475),  # Steps * 1.25
]
for x, y in dpi_points:
    c = arr[y, x]
    print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")

# Search for the actual "-1" blue text on yellow background
# Blue text: R<50, G<50, B>100
print("\nSearching for blue text in y=350-450, x=50-700:")
for y in range(350, 450):
    row = arr[y, 50:700, :]
    blue_text = (row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] > 100)
    bx = np.where(blue_text)[0]
    if len(bx) > 0:
        bx_abs = bx + 50
        print(f"  y={y}: blue_text at x={list(bx_abs)}")

# Also search for yellow background more broadly
print("\nSearching for any yellow (R>200,G>200,B<100) in y=300-500:")
for y in range(300, 500):
    row = arr[y, 50:700, :]
    yel = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 100)
    yx = np.where(yel)[0]
    if len(yx) > 3:
        yx_abs = yx + 50
        sample = arr[y, yx_abs[0]]
        print(f"  y={y}: x=[{yx_abs.min()},{yx_abs.max()}] R={sample[0]}G={sample[1]}B={sample[2]}")

# Save crops for visual inspection
ss.crop((50, 340, 700, 430)).save("artifacts/labview_calibration/atten_fields_area.png")
ss.crop((50, 430, 700, 520)).save("artifacts/labview_calibration/atten_fields_area2.png")
