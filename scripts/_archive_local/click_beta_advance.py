"""Click Beta, then advance through remaining screens."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# Alpha is highlighted. Press Down once to get to Beta, then Enter.
print("Pressing Down to highlight Beta...")
pyautogui.press('down')
time.sleep(0.3)

# Press Enter to select
print("Pressing Enter to select Beta...")
pyautogui.press('enter')
time.sleep(1.5)

# Screenshot to verify
ss = pyautogui.screenshot()
ss.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/stage_beta_selected.png")

# Now click orange arrow
arr = np.array(ss)
pts = []
for y in range(850, 1100):
    if y >= arr.shape[0]:
        break
    row = arr[y, 800:1300, :]
    orange = (row[:, 0] > 200) & (row[:, 1] > 130) & (row[:, 1] < 190) & (row[:, 2] < 80)
    ox = np.where(orange)[0]
    if len(ox) > 3:
        pts.append((y, ox.min() + 800, ox.max() + 800))

if pts:
    acx = (min(p[1] for p in pts) + max(p[2] for p in pts)) // 2
    acy = (min(p[0] for p in pts) + max(p[0] for p in pts)) // 2
    print(f"Clicking orange arrow at ({acx}, {acy})...")
    pyautogui.click(acx, acy)
    time.sleep(3.0)
    
    fg = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(fg, buf, 256)
    print(f"New window: '{buf.value}'")
    
    ss2 = pyautogui.screenshot()
    ss2.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_beta_advance.png")

# === Frame 0060: Region select US ===
fg = u.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(256)
u.GetWindowTextW(fg, buf, 256)
title = buf.value
print(f"\nCurrent screen: '{title}'")

if 'egion' in title.lower() or '400' in title or '480' in title:
    # Find dropdown (yellow) for Region
    ss3 = pyautogui.screenshot()
    arr3 = np.array(ss3)
    
    # Search for yellow dropdowns
    print("Finding Region dropdown (yellow):")
    yellow_rows = []
    for y in range(300, 700):
        row = arr3[y, 300:900, :]
        yellow = (row[:, 0] > 200) & (row[:, 1] > 200) & (row[:, 2] < 80)
        yx = np.where(yellow)[0]
        if len(yx) > 15:
            yx_abs = yx + 300
            yellow_rows.append((y, yx_abs.min(), yx_abs.max()))
    
    if yellow_rows:
        y_min = min(r[0] for r in yellow_rows)
        y_max = max(r[0] for r in yellow_rows)
        x_min = min(r[1] for r in yellow_rows)
        x_max = max(r[2] for r in yellow_rows)
        cx = (x_min + x_max) // 2
        cy = (y_min + y_max) // 2
        print(f"  Dropdown: center=({cx},{cy})")
        
        # Click it
        print(f"  Clicking dropdown...")
        pyautogui.click(cx, cy)
        time.sleep(1.0)
        
        # Screenshot dropdown list
        ss4 = pyautogui.screenshot()
        ss4.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/region_dropdown_list.png")
        
        # Navigate to top and find US
        for i in range(15):
            pyautogui.press('up')
            time.sleep(0.1)
        
        ss5 = pyautogui.screenshot()
        ss5.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/region_list_top.png")

print("Done")
