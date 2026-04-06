"""Find the DUT [0][1] buttons and dropdown - search the full lower half."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

pyautogui.press('escape')
time.sleep(0.3)

ss = pyautogui.screenshot()

# Full lower half of the LabVIEW window (the window goes up to ~1440 pixels)
lower_half = ss.crop((0, 600, 1300, 1000))
lower_half.save("artifacts/labview_calibration/click3_lower_half.png")

# Full middle section
middle = ss.crop((0, 400, 1300, 700))
middle.save("artifacts/labview_calibration/click3_middle.png")

# Full upper section
upper = ss.crop((0, 50, 1300, 400))
upper.save("artifacts/labview_calibration/click3_upper.png")

print("Saved three sections of the window")
