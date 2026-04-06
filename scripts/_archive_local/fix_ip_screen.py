"""Fix the IP address Dual LAN screen: close JPEG dialog, set dropdown values."""
import sys, ctypes, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
from ctypes import wintypes
import os

u = ctypes.windll.user32
k = ctypes.windll.kernel32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D

screen_w = u.GetSystemMetrics(0)
screen_h = u.GetSystemMetrics(1)
print(f"Screen: {screen_w}x{screen_h}")


def click_at(x, y, clicks=1):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    for _ in range(clicks):
        u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.15)


def raw_key(vk):
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)


# Find LabVIEW process windows
hwnd_main = 75188
pid_ptr = wintypes.DWORD()
u.GetWindowThreadProcessId(hwnd_main, ctypes.byref(pid_ptr))
lv_pid = pid_ptr.value
print(f"LabVIEW PID: {lv_pid}")

# Enumerate all visible windows for this PID
windows = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
def enum_callback(hwnd, lparam):
    if u.IsWindowVisible(hwnd):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == lv_pid:
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, buf, 256)
            rect = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(rect))
            windows.append((hwnd, buf.value, rect.left, rect.top, rect.right, rect.bottom))
    return True

u.EnumWindows(enum_callback, 0)

print(f"\nFound {len(windows)} LabVIEW windows:")
for w in windows:
    width = w[4] - w[2]
    height = w[5] - w[3]
    print(f"  hwnd={w[0]}, title='{w[1]}', rect=({w[2]},{w[3]},{w[4]},{w[5]}) size={width}x{height}")
    if w[0] != hwnd_main and width < 800 and height < 600:
        print(f"  >> Candidate dialog window")

print("\nTaking full screenshot...")
ss = pyautogui.screenshot()
print(f"Screenshot size: {ss.size}")
ss.save("artifacts/labview_calibration/step12_diag.png")
