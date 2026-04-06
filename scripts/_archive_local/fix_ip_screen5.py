"""Interact with 2G/MLO dropdown on IP screen using correct 2560x1440 coordinates."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

KEYEVENTF_KEYUP = 0x0002
VK_ESCAPE = 0x1B

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Dismiss any lingering state - press Escape
u.keybd_event(VK_ESCAPE, 0, 0, 0)
time.sleep(0.05)
u.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
time.sleep(0.5)

# "2G/MLO to use (1..5)" dropdown arrow position (2560x1440 physical space):
# From the mid-wide crop at offset (200, 400):
#   The dropdown arrow triangle is at approximately crop_x=350, crop_y=130
#   Screen position: (200+350, 400+130) = (550, 530)

# The "Not Valid" text center is at approximately (460, 530)

# Method 1: pyautogui.click on the dropdown arrow
print("Method 1: pyautogui.click on dropdown arrow at (550, 530)...")
pyautogui.click(550, 530)
time.sleep(1.0)

ss1 = pyautogui.screenshot(region=(300, 480, 350, 200))
ss1.save("artifacts/labview_calibration/step12_m1_after.png")

# Method 2: Try clicking on the "Not Valid" text itself
print("Method 2: pyautogui.click on 'Not Valid' text at (460, 530)...")
pyautogui.click(460, 530)
time.sleep(1.0)

ss2 = pyautogui.screenshot(region=(300, 480, 350, 200))
ss2.save("artifacts/labview_calibration/step12_m2_after.png")

# Method 3: Use AttachThreadInput + raw mouse_event in physical space
tid = u.GetWindowThreadProcessId(hwnd, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, tid, True)
time.sleep(0.2)
u.SetForegroundWindow(hwnd)
time.sleep(0.2)
u.SetFocus(hwnd)
time.sleep(0.2)

screen_w = u.GetSystemMetrics(0)
screen_h = u.GetSystemMetrics(1)
print(f"Screen metrics: {screen_w}x{screen_h}")

MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def raw_click_abs(sx, sy, clicks=1):
    """Click at physical pixel coordinates using MOUSEEVENTF_ABSOLUTE."""
    ax = int(sx * 65535 / screen_w)
    ay = int(sy * 65535 / screen_h)
    for _ in range(clicks):
        u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE, ax, ay, 0, 0)
        time.sleep(0.05)
        u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN, ax, ay, 0, 0)
        time.sleep(0.05)
        u.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP, ax, ay, 0, 0)
        time.sleep(0.15)


print("Method 3: raw_click_abs on dropdown arrow at (550, 530)...")
raw_click_abs(550, 530)
time.sleep(1.0)

ss3 = pyautogui.screenshot(region=(300, 480, 350, 200))
ss3.save("artifacts/labview_calibration/step12_m3_after.png")

# Method 4: Try SendMessage WM_LBUTTONDOWN/UP
# The dropdown is inside the main window at a relative position
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

# Relative position within window: dropdown is at window coordinates
# Window starts at (0,0), so the relative position = screen position
# But we need to handle the DPI-virtualized window rect
rect = wintypes.RECT()
u.GetWindowRect(hwnd, ctypes.byref(rect))
print(f"Window rect: ({rect.left},{rect.top},{rect.right},{rect.bottom})")

# Calculate position relative to window
rx = 550 - rect.left
ry = 530 - rect.top
print(f"Relative position: ({rx}, {ry})")

lparam = (ry << 16) | (rx & 0xFFFF)
print(f"Method 4: SendMessage WM_LBUTTONDOWN/UP at ({rx},{ry})...")
u.SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
time.sleep(0.05)
u.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
time.sleep(1.0)

ss4 = pyautogui.screenshot(region=(300, 480, 350, 200))
ss4.save("artifacts/labview_calibration/step12_m4_after.png")

u.AttachThreadInput(my_tid, tid, False)

# Take full screenshot to see final state
ss_full = pyautogui.screenshot(region=(0, 0, 1600, 1100))
ss_full.save("artifacts/labview_calibration/step12_all_methods.png")

print("Done - check all method screenshots")
