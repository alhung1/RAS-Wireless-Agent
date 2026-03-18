"""Run a single LabVIEW automation step for calibration/testing.

Usage:
    python scripts/run_single_step.py --step 1
    python scripts/run_single_step.py --step 1 --capture-only
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.local_automation.labview_runner import (
    RunConfig, STEP_SEQUENCE, find_labview_window, _refresh_hwnd,
    WINDOW_WIDTH, WINDOW_HEIGHT,
)
from orchestrator.local_automation.screen_utils import (
    capture_window, save_screenshot, get_window_rect,
    ensure_window_size, set_target_window_size,
)

ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "artifacts", "labview_calibration",
)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Run single LabVIEW step")
    parser.add_argument("--step", type=int, required=True, help="Step number (0-18)")
    parser.add_argument("--capture-only", action="store_true",
                        help="Only capture screenshot, don't execute the step")
    parser.add_argument("--band", default="2.4G")
    parser.add_argument("--rf-2g", default="10")
    parser.add_argument("--rf-5g", default="44")
    parser.add_argument("--rf-6g", default="69")
    parser.add_argument("--user-info", default="2G test")
    args = parser.parse_args()

    if args.step < 0 or args.step >= len(STEP_SEQUENCE):
        print(f"Invalid step {args.step}. Valid: 0-{len(STEP_SEQUENCE)-1}")
        return

    set_target_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
    hwnd = find_labview_window()
    if not hwnd:
        print("No LabVIEW window found!")
        return

    ensure_window_size(hwnd, WINDOW_WIDTH, WINDOW_HEIGHT)
    rect = get_window_rect(hwnd)
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]
    print(f"Window: hwnd={hwnd} {w}x{h} at ({rect[0]},{rect[1]})")

    img_before = capture_window(hwnd)
    before_path = save_screenshot(
        img_before, ARTIFACTS_DIR,
        f"step_{args.step:02d}_BEFORE.png",
    )
    print(f"Before: {before_path}")

    if args.capture_only:
        print("Capture-only mode. Not executing step.")
        return

    cfg = RunConfig(
        band=args.band,
        rf_channel_2g=args.rf_2g,
        rf_channel_5g=args.rf_5g,
        rf_channel_6g=args.rf_6g,
        user_information=args.user_info,
    )

    step_fn = STEP_SEQUENCE[args.step]
    print(f"\nExecuting step {args.step}: {step_fn.__name__} ...")
    result = step_fn(hwnd, cfg, ARTIFACTS_DIR)
    print(f"Result: success={result.success} elapsed={result.elapsed_sec:.1f}s")
    if result.error:
        print(f"Error: {result.error}")

    time.sleep(1.0)
    hwnd2 = _refresh_hwnd() or hwnd
    img_after = capture_window(hwnd2)
    after_path = save_screenshot(
        img_after, ARTIFACTS_DIR,
        f"step_{args.step:02d}_AFTER.png",
    )
    print(f"After: {after_path}")


if __name__ == "__main__":
    main()
