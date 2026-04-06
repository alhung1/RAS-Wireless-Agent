"""Check current LabVIEW window state after restart."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

# Find LabVIEW windows
windows = []

@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_cb(hwnd, _):
    if u.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        if title and ("400" in title or "480" in title or "IP" in title or "LAN" in title or "v2.03" in title):
            rect = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(rect))
            windows.append((hwnd, title, rect.left, rect.top, rect.right, rect.bottom))
    return True

u.EnumWindows(enum_cb, 0)

print("LabVIEW windows found:")
for w in windows:
    sz = f"{w[4]-w[2]}x{w[5]-w[3]}"
    print(f"  hwnd={w[0]}: '{w[1]}' rect=({w[2]},{w[3]},{w[4]},{w[5]}) size={sz}")

if windows:
    main = windows[0]
    hwnd = main[0]
    u.SetForegroundWindow(hwnd)
    time.sleep(0.5)

    ss = pyautogui.screenshot()
    print(f"\nScreenshot: {ss.size}")

    # Save full and sections
    ss.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/fresh_full.png")
    ss.crop((0, 0, 800, 50)).save("artifacts/labview_calibration/fresh_title.png")
    ss.crop((0, 850, 1300, 1010)).save("artifacts/labview_calibration/fresh_bottom.png")

    print(f"\nMain window: hwnd={hwnd}, title='{main[1]}'")
else:
    print("No LabVIEW windows found!")
    ss = pyautogui.screenshot()
    ss.save("artifacts/labview_calibration/fresh_state_no_lv.png")
