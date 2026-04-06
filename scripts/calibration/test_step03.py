"""Test step 03 (test type dropdown) in isolation.

Runs steps 00-03, then stops to verify the dropdown selection
and screen transition worked.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from orchestrator.local_automation.labview_runner import (
    RunConfig, find_labview_window, _setup_vi, MAIN_WINDOW_SIZE,
    step_00_attach, step_01_click_throughput,
    step_02_login, step_03_test_type,
    _screenshot, _get_window_title, _find_active_vi,
    _POPUP_DISMISSED_HWNDS,
)

_POPUP_DISMISSED_HWNDS.clear()

AD = os.path.abspath("artifacts/labview/test_step03")
os.makedirs(AD, exist_ok=True)

cfg = RunConfig(
    band="2.4G",
    rf_channel_2g="10",
    rf_channel_5g="0",
    rf_channel_6g="0",
    user_information="2G test",
    mode="BW20",
    number_of_pairs="8",
)

print("=" * 60)
print("  Step 03 Isolated Test")
print("=" * 60)

hwnd = find_labview_window()
if not hwnd:
    print("FAIL: No LabVIEW window found")
    sys.exit(1)

print(f"\nFound LabVIEW: hwnd={hwnd} title={_get_window_title(hwnd)!r}")

steps = [
    ("00 attach", step_00_attach),
    ("01 throughput", step_01_click_throughput),
    ("02 login", step_02_login),
    ("03 test_type", step_03_test_type),
]

for label, fn in steps:
    print(f"\n--- Running: {label} ---")
    result = fn(hwnd, cfg, AD)
    status = "OK" if result.success else "FAIL"
    print(f"  Result: {status} ({result.elapsed_sec:.1f}s)")
    if result.screenshot:
        print(f"  Screenshot: {result.screenshot}")
    if result.error:
        print(f"  Error: {result.error}")
    if not result.success:
        print(f"\nSTOPPED at {label}")
        break

print(f"\n{'=' * 60}")
print(f"  Artifacts in: {AD}")

active = _find_active_vi()
if active:
    title = _get_window_title(active)
    print(f"  Current active VI: hwnd={active} title={title!r}")
    _screenshot(active, AD, 99, "final_state")

print(f"{'=' * 60}")
