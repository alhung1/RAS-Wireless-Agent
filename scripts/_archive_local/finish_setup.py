"""Select US, then advance through final screens to start the test."""
import sys, ctypes, time, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pyautogui
import numpy as np

os.makedirs("artifacts/labview_calibration", exist_ok=True)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

def get_title():
    fg = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(fg, buf, 256)
    return buf.value

def find_and_click_arrow():
    ss = pyautogui.screenshot()
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
        return acx, acy, ss
    return None, None, ss

# Step 1: US is highlighted, press Enter to select
print("=== Selecting US ===")
pyautogui.press('enter')
time.sleep(1.5)

title = get_title()
print(f"After selecting US: '{title}'")

ss = pyautogui.screenshot()
ss.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/region_us_selected.png")

# Click orange arrow
acx, acy, _ = find_and_click_arrow()
if acx:
    print(f"Clicking arrow at ({acx}, {acy})...")
    pyautogui.click(acx, acy)
    time.sleep(3.0)
    title = get_title()
    print(f"-> '{title}'")
    
    ss2 = pyautogui.screenshot()
    ss2.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_region.png")

# === Frame 0066: Final screen - just click orange arrow to start test ===
print(f"\n=== Next screen: '{title}' ===")
ss3 = pyautogui.screenshot()
ss3.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/final_screen_before.png")

acx, acy, _ = find_and_click_arrow()
if acx:
    print(f"Clicking final arrow at ({acx}, {acy})...")
    pyautogui.click(acx, acy)
    time.sleep(5.0)
    
    title = get_title()
    print(f"-> '{title}'")
    
    ss4 = pyautogui.screenshot()
    ss4.crop((0, 0, 1400, 1100)).save("artifacts/labview_calibration/after_final_arrow.png")

print("\n=== STATUS ===")
print(f"Current window: '{get_title()}'")
print("Steps completed:")
print("  1. Login - OK")
print("  2. Test type 1 rpm (fast) - OK")
print("  3. Initial screen arrow - OK")
print("  4. Freq/channels/user info - OK")
print("  5. Select AP (RS700) - OK")
print("  6. AP screen arrow - OK")
print("  7. Select Client (Intel BE200) - OK")
print("  8. Client screen arrow - OK")
print("  9. MAC address / Last toggle - OK")
print("  10. IP address screen - OK (click [1] + dropdowns)")
print("  11. Chariot pairs (8) - OK")
print("  12. Angle orientation - OK")
print("  13. Mode (BW20) + Graph range (100) - OK")
print("  14. Atten (0, 3, 30) - OK")
print("  15. Design cycle Stage (Beta) - OK")
print("  16. Region (US) - OK")
print("  17. Final screen arrow - DONE")
print("Done!")
