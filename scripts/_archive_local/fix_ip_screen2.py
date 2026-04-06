"""Fix the IP address Dual LAN screen dropdowns and advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Force DPI-unaware so coordinates match logical pixel space
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(0)
except Exception:
    pass

import pyautogui
from ctypes import wintypes

u = ctypes.windll.user32
k = ctypes.windll.kernel32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
KEYEVENTF_KEYUP = 0x0002
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D

screen_w = u.GetSystemMetrics(0)
screen_h = u.GetSystemMetrics(1)
print(f"Screen: {screen_w}x{screen_h}")

os.makedirs("artifacts/labview_calibration", exist_ok=True)


def raw_click(sx, sy, clicks=1):
    ax = int(sx * 65535 / screen_w)
    ay = int(sy * 65535 / screen_h)
    for _ in range(clicks):
        u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE, ax, ay, 0, 0)
        time.sleep(0.05)
        u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN, ax, ay, 0, 0)
        time.sleep(0.05)
        u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP, ax, ay, 0, 0)
        time.sleep(0.15)


def raw_key(vk):
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)


hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.3)

# Take baseline screenshot to see current state in logical pixel space
ss = pyautogui.screenshot()
print(f"Screenshot size: {ss.size}")
ss.save("artifacts/labview_calibration/step12_logical.png")

# Now try to close the JPEG dialog if visible
# Press Escape a few times
for i in range(3):
    raw_key(VK_ESCAPE)
    time.sleep(0.3)

ss2 = pyautogui.screenshot()
ss2.save("artifacts/labview_calibration/step12_after_esc2.png")

# AttachThreadInput with the LabVIEW window to get better input handling
tid = u.GetWindowThreadProcessId(hwnd, None)
my_tid = k.GetCurrentThreadId()
print(f"Attaching threads: mine={my_tid} -> lv={tid}")
u.AttachThreadInput(my_tid, tid, True)
time.sleep(0.2)

try:
    u.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    u.SetFocus(hwnd)
    time.sleep(0.3)

    # Try clicking the "2G/MLO to use (1..5)" dropdown
    # In the logical pixel space (2048x1153):
    # The dropdown "Not Valid" appears at approximately x=310, y=277
    # The dropdown arrow is at approximately x=360, y=277

    # First, let me try clicking on the dropdown arrow
    print("Clicking 2G/MLO dropdown arrow (360, 277)...")
    raw_click(360, 277)
    time.sleep(1.0)

    ss3 = pyautogui.screenshot(region=(200, 250, 300, 200))
    ss3.save("artifacts/labview_calibration/step12_dropdown_attempt.png")

    # Try double-clicking
    print("Double-clicking dropdown (310, 277)...")
    raw_click(310, 277, clicks=2)
    time.sleep(1.0)

    ss4 = pyautogui.screenshot(region=(200, 250, 300, 200))
    ss4.save("artifacts/labview_calibration/step12_dropdown_dblclick.png")

    # Try pyautogui click
    print("pyautogui click on dropdown (310, 277)...")
    pyautogui.click(310, 277)
    time.sleep(1.0)

    ss5 = pyautogui.screenshot(region=(200, 250, 300, 200))
    ss5.save("artifacts/labview_calibration/step12_dropdown_pyautogui.png")

    # Try right-clicking to see context menu
    print("Right-clicking dropdown...")
    pyautogui.rightClick(310, 277)
    time.sleep(1.0)

    ss6 = pyautogui.screenshot(region=(200, 250, 400, 200))
    ss6.save("artifacts/labview_calibration/step12_dropdown_rightclick.png")

finally:
    u.AttachThreadInput(my_tid, tid, False)

print("Done - check screenshots")
