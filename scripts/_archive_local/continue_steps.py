"""Continue through remaining LabVIEW steps after Chariot pairs."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

def force_foreground(hwnd):
    fg = u.GetForegroundWindow()
    fg_tid = u.GetWindowThreadProcessId(fg, None)
    my_tid = k.GetCurrentThreadId()
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, True)
    u.ShowWindow(hwnd, 9)
    u.BringWindowToTop(hwnd)
    u.SetForegroundWindow(hwnd)
    if fg_tid != my_tid:
        u.AttachThreadInput(my_tid, fg_tid, False)
    time.sleep(0.5)

def find_labview_window():
    """Find the current LabVIEW window."""
    windows = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, buf, 256)
            t = buf.value
            if t and ('480' in t or '400' in t) and '.vi' in t.lower():
                rect = wintypes.RECT()
                u.GetWindowRect(hwnd, ctypes.byref(rect))
                windows.append((hwnd, t, rect.left, rect.top, rect.right, rect.bottom))
        return True
    u.EnumWindows(cb, 0)
    # Return topmost .vi window
    for w in windows:
        if w[1] not in ('480_214.vi', '480 000.vi'):
            return w
    return windows[0] if windows else None

def find_orange_arrow(arr, side='right'):
    """Find orange arrow position in screenshot."""
    if side == 'right':
        x_start, x_end = 800, 1300
    else:
        x_start, x_end = 0, 200
    
    pts = []
    for y in range(850, 1100):
        if y >= arr.shape[0]:
            break
        row = arr[y, x_start:x_end, :]
        orange = (row[:, 0] > 200) & (row[:, 1] > 130) & (row[:, 1] < 190) & (row[:, 2] < 80)
        ox = np.where(orange)[0]
        if len(ox) > 3:
            pts.append((y, ox.min() + x_start, ox.max() + x_start))
    
    if pts:
        cy = (min(p[0] for p in pts) + max(p[0] for p in pts)) // 2
        cx = (min(p[1] for p in pts) + max(p[2] for p in pts)) // 2
        return cx, cy
    return None

def get_title():
    fg = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(fg, buf, 256)
    return buf.value

def screenshot_and_advance(step_name, delay_after=3.0):
    """Take screenshot, find and click right orange arrow."""
    ss = pyautogui.screenshot()
    arr = np.array(ss)
    ss.crop((0, 0, 1400, 1100)).save(f"artifacts/labview_calibration/{step_name}_before.png")
    
    pos = find_orange_arrow(arr)
    if pos:
        print(f"  Arrow at ({pos[0]}, {pos[1]})")
        pyautogui.click(pos[0], pos[1])
        time.sleep(delay_after)
        title = get_title()
        print(f"  -> New title: '{title}'")
        
        ss2 = pyautogui.screenshot()
        ss2.crop((0, 0, 1400, 1100)).save(f"artifacts/labview_calibration/{step_name}_after.png")
        return title
    else:
        print("  Arrow NOT FOUND!")
        return None

# === Step 0047: angle orientation - just click arrow ===
print("=== Step: Angle Orientation (just click arrow) ===")
w = find_labview_window()
if w:
    force_foreground(w[0])
    title = screenshot_and_advance("step_angle")
else:
    print("No window found!")
    title = None

# === Step 0049: BW mode + graph range ===
if title and ('BW' in title.lower() or 'graph' in title.lower() or 'mode' in title.lower() or '480' in title or '400' in title):
    print(f"\n=== Step: BW/Graph ({title}) ===")
    w = find_labview_window()
    if w:
        force_foreground(w[0])
        # Take screenshot to analyze this screen
        ss = pyautogui.screenshot()
        ss.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/step_bw_current.png")
        print(f"  Current screen saved. Title: '{w[1]}'")
        print("  Need to analyze this screen for BW20 and graph range 100 settings")
