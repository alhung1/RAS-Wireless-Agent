"""Debug DPI coordinate mapping and interact with IP screen dropdowns."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
from ctypes import wintypes

u = ctypes.windll.user32

os.makedirs("artifacts/labview_calibration", exist_ok=True)

screen_w = u.GetSystemMetrics(0)
screen_h = u.GetSystemMetrics(1)
print(f"GetSystemMetrics: {screen_w}x{screen_h}")

ss = pyautogui.screenshot()
print(f"pyautogui.screenshot() size: {ss.size}")
img_w, img_h = ss.size

# DPI scale factor
scale_x = img_w / screen_w
scale_y = img_h / screen_h
print(f"Scale factor: {scale_x:.3f}x{scale_y:.3f}")

# The pyautogui screenshot is {img_w}x{img_h} (physical pixels)
# pyautogui.click() works in the pyautogui coordinate space
# Let's verify: move to a known position and check

# pyautogui.position() should return the same coordinates that pyautogui.click() uses
pos = pyautogui.position()
print(f"Current mouse pos via pyautogui: {pos}")

pt = wintypes.POINT()
u.GetCursorPos(ctypes.byref(pt))
print(f"Current mouse pos via GetCursorPos: ({pt.x}, {pt.y})")

# Move to (100, 100) via pyautogui
pyautogui.moveTo(100, 100)
time.sleep(0.1)
pos2 = pyautogui.position()
pt2 = wintypes.POINT()
u.GetCursorPos(ctypes.byref(pt2))
print(f"After moveTo(100,100): pyautogui={pos2}, Win32=({pt2.x},{pt2.y})")

# Move to (500, 500) via pyautogui
pyautogui.moveTo(500, 500)
time.sleep(0.1)
pos3 = pyautogui.position()
pt3 = wintypes.POINT()
u.GetCursorPos(ctypes.byref(pt3))
print(f"After moveTo(500,500): pyautogui={pos3}, Win32=({pt3.x},{pt3.y})")

# This tells us if pyautogui uses physical or logical coordinates
# If they match, pyautogui uses the same as GetCursorPos (which is logical for DPI-unaware)
# If different, pyautogui has its own DPI handling

# Now take a fresh full screenshot and mark the dropdown positions
ss = pyautogui.screenshot()
ss.save("artifacts/labview_calibration/step12_fresh_full.png")
print(f"Full screenshot saved: {ss.size}")

# Crop a section with the dropdowns visible
# In the physical pixel image, the dropdowns should be at:
# If the window is at logical (0,0,2048,1153) and scale is 1.25:
# Physical window would be (0,0,2560,1441)
# "2G/MLO to use" at logical ~(250,265) = physical ~(312,331)
crop = ss.crop((250, 300, 750, 500))
crop.save("artifacts/labview_calibration/step12_crop_dropdown_area.png")
print(f"Dropdown area crop: {crop.size}")
