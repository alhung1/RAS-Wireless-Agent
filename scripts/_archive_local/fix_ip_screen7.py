"""Try keyboard navigation to change dropdown, and check for E: drive JPEG files."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
from ctypes import wintypes

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

KEYEVENTF_KEYUP = 0x0002
VK_TAB = 0x09
VK_UP = 0x26
VK_DOWN = 0x28
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D


def raw_key(vk, count=1):
    for _ in range(count):
        u.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)


hwnd = 75188

# First check if E:\RF_Pic exists
print("Checking for E:\\RF_Pic directory...")
if os.path.exists("E:\\RF_Pic"):
    print("  E:\\RF_Pic EXISTS")
    files = os.listdir("E:\\RF_Pic")
    print(f"  Files: {files[:20]}")
else:
    print("  E:\\RF_Pic does NOT exist")
    if os.path.exists("E:\\"):
        print("  E: drive exists")
    else:
        print("  E: drive does NOT exist")

# Check C:\480.builds directory for any RF_Pic references
print("\nChecking C:\\480.builds...")
if os.path.exists("C:\\480.builds"):
    for root, dirs, files in os.walk("C:\\480.builds"):
        for d in dirs:
            if "pic" in d.lower() or "rf" in d.lower():
                print(f"  Found dir: {os.path.join(root, d)}")
        for f in files:
            if "laptop" in f.lower() or "rf_pic" in f.lower():
                print(f"  Found file: {os.path.join(root, f)}")
        if root.count(os.sep) > 3:
            break

# Dismiss JPEG dialog first
u.SetForegroundWindow(hwnd)
time.sleep(0.3)
raw_key(VK_ESCAPE, 3)
time.sleep(0.5)

# Now try Tab key to cycle through controls
# Then use arrow keys to change value
tid = u.GetWindowThreadProcessId(hwnd, None)
my_tid = k.GetCurrentThreadId()
u.AttachThreadInput(my_tid, tid, True)
time.sleep(0.2)
u.SetForegroundWindow(hwnd)
time.sleep(0.2)
u.SetFocus(hwnd)
time.sleep(0.2)

try:
    # First click on the "Not Valid" dropdown area to try to focus it
    print("\nClicking on dropdown area and trying Tab+Arrow...")
    pyautogui.click(460, 530)
    time.sleep(0.3)

    # Try down arrow
    print("Pressing Down arrow...")
    raw_key(VK_DOWN, 3)
    time.sleep(0.5)

    ss1 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss1.save("artifacts/labview_calibration/step12_arrow_down.png")

    # Try up arrow
    print("Pressing Up arrow...")
    raw_key(VK_UP, 3)
    time.sleep(0.5)

    ss2 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss2.save("artifacts/labview_calibration/step12_arrow_up.png")

    # Try Tab key multiple times to navigate to dropdown
    print("Pressing Tab to cycle controls...")
    for i in range(10):
        raw_key(VK_TAB)
        time.sleep(0.3)

        # Take a small screenshot each time to see which control is focused
        if i % 3 == 0:
            ss = pyautogui.screenshot(region=(300, 480, 350, 100))
            ss.save(f"artifacts/labview_calibration/step12_tab_{i}.png")
            print(f"  Tab {i} - saved screenshot")

    # After tabbing, try down arrow
    print("After tabbing, pressing Down arrow...")
    raw_key(VK_DOWN, 2)
    time.sleep(0.5)

    ss3 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss3.save("artifacts/labview_calibration/step12_tab_then_down.png")

    # Try typing "2" (numeric value)
    print("Typing '2'...")
    pyautogui.typewrite("2", interval=0.1)
    time.sleep(0.5)

    ss4 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss4.save("artifacts/labview_calibration/step12_type_2.png")

    # Full screenshot
    ss_full = pyautogui.screenshot(region=(0, 0, 1600, 1100))
    ss_full.save("artifacts/labview_calibration/step12_keyboard_final.png")

finally:
    u.AttachThreadInput(my_tid, tid, False)

print("Done")
