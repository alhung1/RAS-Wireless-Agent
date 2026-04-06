"""Debug script to identify the 'Run Same' toggle position on the test type screen."""
import sys, os, time, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from orchestrator.local_automation.labview_runner import (
    RunConfig, find_labview_window, _setup_vi, MAIN_WINDOW_SIZE,
    step_00_attach, step_01_click_throughput, step_02_login,
    _find_vi_window, _screenshot, _get_window_title,
    _POPUP_DISMISSED_HWNDS,
)
from orchestrator.local_automation.screen_utils import capture_window, get_window_rect

_POPUP_DISMISSED_HWNDS.clear()

AD = os.path.abspath("artifacts/labview/debug_runsame")
os.makedirs(AD, exist_ok=True)

cfg = RunConfig(
    band="2.4G", rf_channel_2g="10", rf_channel_5g="0", rf_channel_6g="0",
    user_information="debug", mode="BW20", number_of_pairs="8",
)

hwnd = find_labview_window()
if not hwnd:
    print("No LabVIEW window"); sys.exit(1)

print(f"Found: hwnd={hwnd} title={_get_window_title(hwnd)!r}")

for label, fn in [("00", step_00_attach), ("01", step_01_click_throughput), ("02", step_02_login)]:
    r = fn(hwnd, cfg, AD)
    print(f"  Step {label}: {'OK' if r.success else 'FAIL'} ({r.elapsed_sec:.1f}s)")
    if not r.success:
        print(f"    Error: {r.error}"); sys.exit(1)

vi_hwnd = _find_vi_window("400 600 test", timeout=10.0)
if not vi_hwnd:
    print("FAIL: test type VI not found"); sys.exit(1)

_setup_vi(vi_hwnd)
img = capture_window(vi_hwnd)
rect = get_window_rect(vi_hwnd)
print(f"Test type VI: hwnd={vi_hwnd}, rect={rect}, img shape={img.shape}")

candidates = [
    (462, 537, "run_same_toggle_A"),
    (462, 540, "run_same_toggle_B"),
    (478, 505, "run_same_text"),
    (460, 530, "run_same_toggle_C"),
    (490, 537, "run_same_right"),
]

for cx, cy, label in candidates:
    marked = img.copy()
    cv2.line(marked, (cx - 20, cy), (cx + 20, cy), (0, 0, 255), 2)
    cv2.line(marked, (cx, cy - 20), (cx, cy + 20), (0, 0, 255), 2)
    cv2.putText(marked, f"({cx},{cy}) {label}", (cx + 5, cy - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    path = os.path.join(AD, f"crosshair_{label}.png")
    cv2.imwrite(path, marked)
    print(f"  Saved: {path}")

region = img[480:570, 420:530]
path = os.path.join(AD, "run_same_crop.png")
cv2.imwrite(path, region)
print(f"  Saved crop: {path}")

print("\nDone. Check artifacts/labview/debug_runsame/")
