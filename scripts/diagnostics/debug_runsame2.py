"""Debug: draw crosshairs on the Run Same area with corrected coordinates."""
import sys, os, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

AD = os.path.abspath("artifacts/labview/debug_runsame")
src = os.path.join(AD, "crosshair_run_same_toggle_A.png")
img_raw = cv2.imread(src.replace("crosshair_run_same_toggle_A.png",
                                  "crosshair_run_same_toggle_A.png"))
# Re-capture from the original (no crosshairs)
from orchestrator.local_automation.labview_runner import (
    _find_vi_window, _setup_vi, _POPUP_DISMISSED_HWNDS,
)
from orchestrator.local_automation.screen_utils import capture_window, get_window_rect

_POPUP_DISMISSED_HWNDS.clear()

vi_hwnd = _find_vi_window("400 600 test", timeout=5.0)
if not vi_hwnd:
    print("Test type VI not found - maybe need to navigate there first")
    sys.exit(1)

_setup_vi(vi_hwnd)
img = capture_window(vi_hwnd)
rect = get_window_rect(vi_hwnd)
print(f"Window rect: {rect}, image shape: {img.shape}")

candidates = [
    (465, 650, "runsame_650"),
    (465, 665, "runsame_665"),
    (465, 680, "runsame_680"),
    (490, 660, "runsame_right_660"),
    (460, 670, "runsame_left_670"),
]

for cx, cy, label in candidates:
    marked = img.copy()
    cv2.line(marked, (cx - 25, cy), (cx + 25, cy), (0, 0, 255), 2)
    cv2.line(marked, (cx, cy - 25), (cx, cy + 25), (0, 0, 255), 2)
    cv2.putText(marked, f"({cx},{cy})", (cx + 8, cy - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    path = os.path.join(AD, f"cross2_{label}.png")
    cv2.imwrite(path, marked)
    print(f"  Saved: {path}")

crop = img[580:710, 40:550]
path = os.path.join(AD, "crop_table_meters_runsame.png")
cv2.imwrite(path, crop)
print(f"  Saved crop: {path}")

crop2 = img[440:520, 40:400]
path2 = os.path.join(AD, "crop_dropdown.png")
cv2.imwrite(path2, crop2)
print(f"  Saved dropdown crop: {path2}")

print("Done")
