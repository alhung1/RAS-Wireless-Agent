"""Try mouse wheel on dropdown and clicking laptop images with correct physical coords."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

screen_w = u.GetSystemMetrics(0)
screen_h = u.GetSystemMetrics(1)
print(f"Screen: {screen_w}x{screen_h}")

# AttachThreadInput
tid = u.GetWindowThreadProcessId(hwnd, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, tid, True)
time.sleep(0.2)
u.SetForegroundWindow(hwnd)
time.sleep(0.2)
u.SetFocus(hwnd)
time.sleep(0.2)

try:
    # =========================================================
    # APPROACH 1: Try scroll wheel on "Not Valid" dropdown
    # =========================================================
    # Dropdown "2G/MLO to use (1..5)" "Not Valid" is at ~(460, 530) in 2560x1440
    print("Moving to dropdown at (460, 530)...")
    pyautogui.moveTo(460, 530)
    time.sleep(0.3)

    # Verify cursor position
    pt = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    print(f"Cursor at: ({pt.x}, {pt.y})")

    # Click to focus
    pyautogui.click()
    time.sleep(0.3)

    # Scroll up (positive delta = scroll up)
    print("Scrolling up on dropdown...")
    WHEEL_DELTA = 120
    for i in range(5):
        u.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_DELTA, 0)
        time.sleep(0.3)

    ss1 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss1.save("artifacts/labview_calibration/step12_wheel_up.png")

    # Scroll down
    print("Scrolling down on dropdown...")
    for i in range(3):
        u.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, ctypes.c_uint32(-WHEEL_DELTA).value, 0)
        time.sleep(0.3)

    ss2 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss2.save("artifacts/labview_calibration/step12_wheel_down.png")

    # =========================================================
    # APPROACH 2: Use pyautogui scroll
    # =========================================================
    print("pyautogui scroll on dropdown...")
    pyautogui.moveTo(460, 530)
    time.sleep(0.2)
    pyautogui.scroll(3)
    time.sleep(0.5)

    ss3 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss3.save("artifacts/labview_calibration/step12_pyautogui_scroll.png")

    # =========================================================
    # APPROACH 3: Click on laptop images (MLO Client 2) at correct physical coords
    # =========================================================
    # In 2560x1440 space, MLO Client 2 laptop center is at approximately (390, 160)
    print("\nClicking MLO Client 2 laptop at (390, 160)...")
    pyautogui.click(390, 160)
    time.sleep(1.0)

    ss4 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss4.save("artifacts/labview_calibration/step12_laptop2_click.png")

    # Check if JPEG dialog appeared again
    ss4f = pyautogui.screenshot(region=(0, 0, 1600, 1100))
    ss4f.save("artifacts/labview_calibration/step12_laptop2_full.png")

    # =========================================================
    # APPROACH 4: Double-click on laptop
    # =========================================================
    print("Double-clicking MLO Client 2...")
    pyautogui.doubleClick(390, 160)
    time.sleep(1.0)

    ss5f = pyautogui.screenshot(region=(0, 0, 1600, 1100))
    ss5f.save("artifacts/labview_calibration/step12_laptop2_dblclick.png")

finally:
    u.AttachThreadInput(my_tid, tid, False)

print("Done - check screenshots")
