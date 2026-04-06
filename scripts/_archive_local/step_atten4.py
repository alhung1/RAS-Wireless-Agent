"""Find and set the Start atten, Step Size, Steps fields."""
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

ss = pyautogui.screenshot()
arr = np.array(ss)

# Yellow region was found at y=494-499, x=[117,616]
# That spans the area where Start atten, Step Size, Steps should be
# Let me crop this area and examine
ss.crop((80, 440, 700, 540)).save("artifacts/labview_calibration/atten_yellow_region.png")

# Check for gaps in the yellow band (between fields)
print("Yellow band analysis at y=496:")
row = arr[496, 80:700, :]
yellow = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 100)
yx = np.where(yellow)[0]
yx_abs = yx + 80
print(f"  Yellow pixels: {len(yx)} at x=[{yx_abs.min()},{yx_abs.max()}]")

# Find gaps in the yellow pixels
if len(yx_abs) > 0:
    gaps = []
    for i in range(1, len(yx_abs)):
        if yx_abs[i] - yx_abs[i-1] > 5:
            gaps.append((yx_abs[i-1], yx_abs[i]))
    print(f"  Gaps: {gaps}")
    
    # Split into field segments
    segments = []
    start = yx_abs[0]
    for i in range(1, len(yx_abs)):
        if yx_abs[i] - yx_abs[i-1] > 5:
            segments.append((start, yx_abs[i-1]))
            start = yx_abs[i]
    segments.append((start, yx_abs[-1]))
    
    for idx, (s, e) in enumerate(segments):
        cx = (s + e) // 2
        print(f"  Segment {idx}: x=[{s},{e}] center_x={cx}")

# Also look at the broader area - find ALL colored/distinct regions
print("\nAll non-cyan pixels in y=450-520, x=50-700:")
for y in [460, 470, 480, 490, 496, 500, 510]:
    row = arr[y, 50:700, :]
    non_cyan = ~((row[:, 0] < 30) & (row[:, 1] > 240) & (row[:, 2] > 240))
    non_bg = non_cyan & ~((row[:, 0] == 23) & (row[:, 1] == 255) & (row[:, 2] == 255))
    nx = np.where(non_bg)[0]
    if len(nx) > 0:
        nx_abs = nx + 50
        # Show clusters
        clusters = []
        curr_start = nx_abs[0]
        for i in range(1, len(nx_abs)):
            if nx_abs[i] - nx_abs[i-1] > 5:
                clusters.append((curr_start, nx_abs[i-1]))
                curr_start = nx_abs[i]
        clusters.append((curr_start, nx_abs[-1]))
        print(f"  y={y}: {len(clusters)} clusters: {clusters[:10]}")
