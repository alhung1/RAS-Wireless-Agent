"""Capture reference template images from a running LabVIEW window.

Usage:
    python scripts/capture_templates.py              # capture all
    python scripts/capture_templates.py --step 3     # capture step 3 only
    python scripts/capture_templates.py --list       # list needed templates

Run with LabVIEW open.  The script will guide you through positioning
the window on the correct screen before each capture.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cv2
import numpy as np

from orchestrator.local_automation.screen_utils import (
    capture_window,
    save_screenshot,
    get_window_rect,
    set_window_rect,
)
from orchestrator.local_automation.labview_runner import (
    find_labview_window,
    _force_fg,
    STEP_WINDOW_SIZE,
    MAIN_WINDOW_SIZE,
    ORANGE_ARROW_PX,
)

TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "orchestrator", "local_automation", "templates",
)

TEMPLATE_SPECS: list[dict] = [
    {
        "name": "orange_arrow.png",
        "description": "Right orange arrow (Next)",
        "region": (ORANGE_ARROW_PX[0] - 30, ORANGE_ARROW_PX[1] - 20, 60, 40),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "orange_arrow_left.png",
        "description": "Left orange arrow (Back)",
        "region": (30, ORANGE_ARROW_PX[1] - 20, 60, 40),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "throughput_tab.png",
        "description": "Throughput Testing tab on main screen",
        "region": (50, 200, 200, 80),
        "window_size": MAIN_WINDOW_SIZE,
    },
    {
        "name": "green_ok_button.png",
        "description": "Green OK button on login dialog",
        "region": (250, 140, 80, 50),
        "window_size": (356, 200),
    },
    {
        "name": "done_button.png",
        "description": "Done button in popup list dialogs",
        "region": None,
        "note": "Capture manually from AP/Client popup – button near bottom-right",
    },
    {
        "name": "test_type_screen.png",
        "description": "Test type selection screen header",
        "region": (50, 30, 400, 60),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "freq_channel_screen.png",
        "description": "Frequency/channel screen header (481.300)",
        "region": (50, 30, 400, 60),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "ip_address_screen.png",
        "description": "IP Address Dual LAN screen header",
        "region": (50, 30, 500, 60),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "mode_screen.png",
        "description": "MODE selection screen header",
        "region": (50, 30, 300, 60),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "atten_screen.png",
        "description": "Attenuation config screen header",
        "region": (50, 30, 400, 60),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "design_stage_screen.png",
        "description": "Design stage / Chariot screen header",
        "region": (50, 30, 400, 60),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "region_screen.png",
        "description": "Region selection screen header",
        "region": (50, 30, 400, 60),
        "window_size": STEP_WINDOW_SIZE,
    },
    {
        "name": "test_running.png",
        "description": "Test-is-running indicator",
        "region": None,
        "note": "Capture manually once a test is in progress",
    },
]


def _crop_region(img: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = region
    return img[y:y + h, x:x + w]


def capture_template(spec: dict, hwnd: int) -> str | None:
    region = spec.get("region")
    if region is None:
        print(f"  SKIP {spec['name']}: {spec.get('note', 'manual capture needed')}")
        return None

    window_size = spec.get("window_size", STEP_WINDOW_SIZE)
    set_window_rect(hwnd, 0, 0, *window_size)
    time.sleep(0.5)
    _force_fg(hwnd)
    time.sleep(0.3)

    img = capture_window(hwnd)
    cropped = _crop_region(img, region)

    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    path = os.path.join(TEMPLATES_DIR, spec["name"])
    cv2.imwrite(path, cropped)
    print(f"  Saved {spec['name']} ({cropped.shape[1]}x{cropped.shape[0]})")
    return path


def list_templates():
    print("Required templates:")
    for spec in TEMPLATE_SPECS:
        status = "AUTO" if spec.get("region") else "MANUAL"
        print(f"  [{status}] {spec['name']:30s} - {spec['description']}")


def main():
    parser = argparse.ArgumentParser(description="Capture LabVIEW reference templates")
    parser.add_argument("--step", type=int, default=None,
                        help="Capture a specific template by index")
    parser.add_argument("--list", action="store_true",
                        help="List required templates and exit")
    args = parser.parse_args()

    if args.list:
        list_templates()
        return

    hwnd = find_labview_window()
    if not hwnd:
        print("ERROR: LabVIEW window not found. Start LabVIEW first.")
        sys.exit(1)

    print(f"Found LabVIEW window (hwnd={hwnd})")
    print(f"Templates dir: {os.path.abspath(TEMPLATES_DIR)}")
    print()

    specs = TEMPLATE_SPECS
    if args.step is not None:
        if 0 <= args.step < len(specs):
            specs = [specs[args.step]]
        else:
            print(f"ERROR: step index {args.step} out of range (0-{len(TEMPLATE_SPECS)-1})")
            sys.exit(1)

    input("Position LabVIEW on the relevant screen, then press Enter...")

    for spec in specs:
        print(f"Capturing: {spec['description']}")
        capture_template(spec, hwnd)

    print("\nDone. Missing templates must be captured manually.")


if __name__ == "__main__":
    main()
