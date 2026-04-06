"""Find mode dropdown precisely by scanning full image for yellow."""
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
time.sleep(1.5)

# Verify foreground
fg = u.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(256)
u.GetWindowTextW(fg, buf, 256)
print(f"Foreground: '{buf.value}' (hwnd={fg}, target={hwnd})")

ss = pyautogui.screenshot()
arr = np.array(ss)
print(f"Screenshot: {ss.size}")

# Full image search for yellow
# Try multiple yellow definitions
criteria = [
    ("strict_yellow", lambda r: (r[:, 0] > 200) & (r[:, 1] > 200) & (r[:, 2] < 50)),
    ("broad_yellow", lambda r: (r[:, 0] > 180) & (r[:, 1] > 180) & (r[:, 2] < 100)),
    ("warm_yellow", lambda r: (r[:, 0] > 220) & (r[:, 1] > 150) & (r[:, 2] < 60)),
    ("any_yellow", lambda r: (r[:, 0] > 150) & (r[:, 1] > 150) & (r[:, 2] < 80) & (r[:, 0].astype(int) + r[:, 1].astype(int) > 350)),
]

for name, fn in criteria:
    print(f"\n--- {name} ---")
    count = 0
    for y in range(0, 1440, 5):
        row = arr[y, :1300, :]
        mask = fn(row)
        mx = np.where(mask)[0]
        if len(mx) > 5:
            sample = arr[y, mx[0]]
            print(f"  y={y}: x=[{mx.min()},{mx.max()}] count={len(mx)} R={sample[0]}G={sample[1]}B={sample[2]}")
            count += 1
            if count > 5:
                break

# Direct color sampling at expected mode dropdown location
# Based on the screenshot, the dropdown appears at about x=100-300, y=680-720
# at 125% DPI, physical coordinates would be:
# x = 100*1.25=125 to 300*1.25=375
# y = 680*1.25=850 to 720*1.25=900
print("\nSampling at multiple potential locations:")
locs = [(190, 710), (190, 715), (190, 720), (190, 700), (190, 690),
        (240, 710), (240, 700), (150, 700),
        (190, 680), (190, 660), (190, 650),
        # Try 125% scaled coordinates
        (238, 888), (238, 850), (238, 900), (238, 870), (238, 860),
        (300, 850), (300, 870), (200, 870)]

for x, y in locs:
    if y < arr.shape[0] and x < arr.shape[1]:
        c = arr[y, x]
        print(f"  ({x},{y}): R={c[0]} G={c[1]} B={c[2]}")

# Save a wider crop for visual verification
ss.crop((0, 400, 600, 800)).save("artifacts/labview_calibration/mode_area_scan.png")
ss.crop((0, 650, 600, 950)).save("artifacts/labview_calibration/mode_dropdown_area.png")
