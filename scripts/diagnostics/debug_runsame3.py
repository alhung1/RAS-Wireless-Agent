"""Debug: precise crosshairs on Run Same icon area."""
import sys, os, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

AD = os.path.abspath("artifacts/labview/debug_runsame")

from orchestrator.local_automation.labview_runner import (
    _find_vi_window, _setup_vi, _POPUP_DISMISSED_HWNDS,
)
from orchestrator.local_automation.screen_utils import capture_window, get_window_rect

vi_hwnd = _find_vi_window("400 600 test", timeout=5.0)
if not vi_hwnd:
    print("Test type VI not found"); sys.exit(1)

img = capture_window(vi_hwnd)
rect = get_window_rect(vi_hwnd)
print(f"Window: {rect}, shape: {img.shape}")

candidates = [
    (462, 685, "toggle_685"),
    (462, 695, "toggle_695"),
    (480, 685, "toggle_r685"),
    (500, 680, "toggle_500_680"),
    (475, 695, "toggle_475_695"),
]

for cx, cy, label in candidates:
    marked = img.copy()
    cv2.line(marked, (cx - 20, cy), (cx + 20, cy), (0, 0, 255), 2)
    cv2.line(marked, (cx, cy - 20), (cx, cy + 20), (0, 0, 255), 2)
    cv2.putText(marked, f"({cx},{cy})", (cx + 5, cy - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    path = os.path.join(AD, f"cross3_{label}.png")
    cv2.imwrite(path, marked)

crop = img[590:720, 420:600]
path = os.path.join(AD, "crop_wide_runsame.png")
cv2.imwrite(path, crop)

crop2 = img[600:700, 440:520]
path2 = os.path.join(AD, "crop_tight_runsame.png")
cv2.imwrite(path2, crop2)

print("Done. Check cross3_* and crop_*_runsame.png")
