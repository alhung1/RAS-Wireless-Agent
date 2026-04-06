"""Fill in the AP IP address field and try to advance."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# The "Input the I.P. address of the AP" yellow box
# From the ip_fields crop at (50, 350): the yellow box is at approximately:
#   crop (0, 140) to (260, 160) → screen (50, 490) to (310, 510)
# Let me find it precisely
ss = pyautogui.screenshot()

# Find the yellow "Input" box by scanning for yellow at the expected position
arr = np.array(ss)
print("Scanning for yellow box in IP input area:")
for y in range(370, 420):
    row = arr[y, 60:350, :]
    yellow = ((row[:, 0] > 240) & (row[:, 1] > 240) & (row[:, 2] < 30)).sum()
    if yellow > 100:
        print(f"  y={y}: {yellow} yellow pixels")

# Also check the "IP address AP" field lower down
for y in range(540, 580):
    row = arr[y, 60:250, :]
    white = ((row[:, 0] > 230) & (row[:, 1] > 230) & (row[:, 2] > 230)).sum()
    if white > 30:
        print(f"  IP AP field white at y={y}: {white} pixels")

# Click on the yellow input box for "Input the I.P. address of the AP"
# Center: approximately (180, 395)
print("\nClicking yellow AP IP input box at (180, 395)...")
pyautogui.click(180, 395)
time.sleep(0.5)

# Take screenshot to verify we clicked the right thing
ss2 = pyautogui.screenshot(region=(40, 370, 350, 50))
ss2.save("artifacts/labview_calibration/fix_ip_clicked_box.png")

# Try typing an IP address (the last octet, since it shows "..." prefix)
# The field might expect just the last octet or the full IP
# Let me try clearing and typing
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.2)
pyautogui.typewrite('192.168.1.1', interval=0.05)
time.sleep(0.5)

ss3 = pyautogui.screenshot(region=(40, 370, 350, 50))
ss3.save("artifacts/labview_calibration/fix_ip_after_type.png")

# Check full state
ss4 = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss4.save("artifacts/labview_calibration/fix_ip_full.png")

# Try orange arrow
print("Clicking orange arrow at (1143, 857)...")
pyautogui.click(1143, 857)
time.sleep(2.0)

buf = ctypes.create_unicode_buffer(256)
u.GetWindowTextW(hwnd, buf, 256)
print(f"Window title: '{buf.value}'")

ss5 = pyautogui.screenshot(region=(0, 0, 1400, 1100))
ss5.save("artifacts/labview_calibration/fix_ip_after_arrow.png")

print("Done")
