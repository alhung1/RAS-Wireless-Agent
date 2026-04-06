"""Select BW20 from mode dropdown list - scroll up to find it."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# The dropdown is already open. Let me scroll up to find BW20.
# Scroll up in the dropdown
print("Scrolling up in dropdown...")
pyautogui.scroll(5, x=249, y=757)  # Scroll up
time.sleep(0.5)

ss = pyautogui.screenshot()
ss.crop((50, 700, 500, 950)).save("artifacts/labview_calibration/mode_scrolled_up.png")

# Check what's visible now
arr = np.array(ss)
# Look for dark text (dropdown items) in the white area
print("Checking dropdown items...")
for y in range(720, 800):
    row = arr[y, 100:400, :]
    dark = (row[:, 0] < 50) & (row[:, 1] < 50) & (row[:, 2] < 50)
    dx = np.where(dark)[0]
    if len(dx) > 0:
        dx_abs = dx + 100
        print(f"  y={y}: dark text at x={list(dx_abs[:20])}")
