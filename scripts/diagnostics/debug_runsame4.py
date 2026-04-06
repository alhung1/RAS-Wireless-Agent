"""Debug: target the capsule toggle for Run Same."""
import sys, os, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

AD = os.path.abspath("artifacts/labview/debug_runsame")

from orchestrator.local_automation.labview_runner import (
    _find_vi_window, _setup_vi,
)
from orchestrator.local_automation.screen_utils import capture_window

vi_hwnd = _find_vi_window("400 600 test", timeout=5.0)
if not vi_hwnd:
    print("Test type VI not found"); sys.exit(1)

img = capture_window(vi_hwnd)
print(f"shape: {img.shape}")

candidates = [
    (560, 690, "cap_560_690"),
    (570, 690, "cap_570_690"),
    (575, 695, "cap_575_695"),
    (480, 690, "cap_480_690"),
    (550, 685, "cap_550_685"),
]

for cx, cy, label in candidates:
    marked = img.copy()
    cv2.line(marked, (cx - 15, cy), (cx + 15, cy), (0, 0, 255), 2)
    cv2.line(marked, (cx, cy - 15), (cx, cy + 15), (0, 0, 255), 2)
    cv2.putText(marked, f"({cx},{cy})", (cx + 5, cy - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    cv2.imwrite(os.path.join(AD, f"cross4_{label}.png"), marked)

crop = img[660:720, 440:600]
cv2.imwrite(os.path.join(AD, "crop_toggle_zone.png"), crop)

print("Done")
