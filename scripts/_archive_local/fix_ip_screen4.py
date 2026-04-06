"""Take precise crops of the IP screen to identify dropdown coordinates."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32

hwnd = 75188
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Full window screenshot in physical pixels
ss = pyautogui.screenshot()
print(f"Screenshot: {ss.size}")

# The LabVIEW window fills the screen at 2560x1440
# Take various crops to locate exact positions

# Middle section with dropdowns (wider area)
crop1 = ss.crop((200, 400, 1200, 700))
crop1.save("artifacts/labview_calibration/step12_mid_wide.png")
print(f"Mid wide crop (200,400,1200,700): {crop1.size}")

# Bottom section with DUT, arrows, Freq Range
crop2 = ss.crop((0, 700, 1400, 1000))
crop2.save("artifacts/labview_calibration/step12_bottom.png")
print(f"Bottom crop (0,700,1400,1000): {crop2.size}")

# Right side where the JPEG dialog was
crop3 = ss.crop((1300, 200, 2200, 700))
crop3.save("artifacts/labview_calibration/step12_right_panel.png")
print(f"Right panel crop (1300,200,2200,700): {crop3.size}")

# Full IP address area
crop4 = ss.crop((200, 500, 1300, 900))
crop4.save("artifacts/labview_calibration/step12_ip_area.png")
print(f"IP area crop (200,500,1300,900): {crop4.size}")

# Top laptop row
crop5 = ss.crop((100, 50, 1400, 350))
crop5.save("artifacts/labview_calibration/step12_laptop_row.png")
print(f"Laptop row crop (100,50,1400,350): {crop5.size}")

print("Done")
