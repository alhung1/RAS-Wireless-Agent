"""Systematic approach: Tab to find dropdown, try pywinauto inspection, or just advance."""
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
VK_SHIFT = 0x10


def raw_key(vk, count=1):
    for _ in range(count):
        u.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)


hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Dismiss JPEG dialog
raw_key(VK_ESCAPE, 3)
time.sleep(0.5)

# Attach thread input
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
    # APPROACH: Use Shift+Tab to go backward, systematically finding controls
    # Click on the "Not Valid" text area first, then Tab forward/backward
    # =========================================================

    # Click on the dropdown area
    print("Clicking on 2G/MLO dropdown area...")
    pyautogui.click(400, 530)
    time.sleep(0.3)

    # Try increment: Ctrl+Up might work on LabVIEW ring controls
    print("Trying Ctrl+Up...")
    u.keybd_event(0x11, 0, 0, 0)  # Ctrl down
    time.sleep(0.05)
    raw_key(VK_UP, 3)
    u.keybd_event(0x11, 0, KEYEVENTF_KEYUP, 0)  # Ctrl up
    time.sleep(0.5)

    ss1 = pyautogui.screenshot(region=(300, 480, 350, 100))
    ss1.save("artifacts/labview_calibration/step12_ctrl_up.png")

    # Check if value changed
    # Try using pyautogui to click on the very small down-arrow triangle
    # The triangle is at the right edge of the dropdown
    # In 2560x1440: the arrow is at approximately (445, 530)
    # Let me click precisely on it
    print("Clicking dropdown arrow precisely at (443, 527)...")
    pyautogui.click(443, 527)
    time.sleep(1.0)

    ss2 = pyautogui.screenshot(region=(250, 450, 500, 200))
    ss2.save("artifacts/labview_calibration/step12_precise_arrow.png")

    # Try right-click on the dropdown
    print("Right-clicking dropdown for context menu...")
    pyautogui.rightClick(400, 530)
    time.sleep(1.0)

    ss3 = pyautogui.screenshot(region=(250, 450, 500, 300))
    ss3.save("artifacts/labview_calibration/step12_rightclick.png")

    # Dismiss any context menu
    raw_key(VK_ESCAPE)
    time.sleep(0.3)

    # =========================================================
    # Let me try the orange right arrow anyway to see what happens
    # The orange arrow is at bottom-right: approximately (770, 608) in 2560x1440
    # Wait, from the full screenshot the arrow is at approximately (765, 600-620)
    # Let me get exact position
    # =========================================================
    print("\n--- Trying to advance via orange arrow ---")
    # From the 1600x1100 screenshot, the orange arrow was at approx (765, 610)
    # At full 2560x1440: the window fills 0-2048 logical → 0-2560 physical
    # Orange arrow bottom-right corner of the LabVIEW area
    # From the bottom crop (0,700,1400,1000): the arrow was at about x=1330, y=970 in full image
    # Wait let me re-measure from the step12_keyboard_final.png (1600x1100 crop)
    # The orange arrow is at bottom-right: approximately x=770, y=605

    # Actually, from the full 2560x1440 screenshot, the LabVIEW window goes from 0 to ~1640
    # (2048 logical * ? physical mapping)
    # The orange arrow is at the bottom-right of the cyan area
    # Let me just crop the bottom-right corner to find it

    ss_br = pyautogui.screenshot(region=(600, 550, 300, 100))
    ss_br.save("artifacts/labview_calibration/step12_bottom_right.png")

    # Click where the orange arrow should be
    print("Clicking orange arrow at (765, 608)...")
    pyautogui.click(765, 608)
    time.sleep(1.5)

    # Check if screen changed
    ss4 = pyautogui.screenshot(region=(0, 0, 1600, 1100))
    ss4.save("artifacts/labview_calibration/step12_after_arrow.png")

finally:
    u.AttachThreadInput(my_tid, tid, False)

print("Done")
