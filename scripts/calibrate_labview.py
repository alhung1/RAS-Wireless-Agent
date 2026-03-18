"""Calibrate LabVIEW window coordinates for automation.

Brings the LabVIEW window to foreground, captures a screenshot,
draws a grid overlay, and saves coordinate reference images.

Usage:
    python scripts/calibrate_labview.py
    python scripts/calibrate_labview.py --grid-step 0.05
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.local_automation.screen_utils import (
    capture_window, save_screenshot, get_window_rect,
)
from scripts.inspect_labview_window import list_windows

ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "artifacts", "labview_calibration",
)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

user32 = ctypes.windll.user32


def bring_to_front(hwnd: int) -> None:
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.0)


def draw_grid(img: np.ndarray, step: float = 0.1) -> np.ndarray:
    """Draw a coordinate grid on the image with labels."""
    out = img.copy()
    h, w = out.shape[:2]
    color = (0, 255, 0)
    font = cv2.FONT_HERSHEY_SIMPLEX

    rx = 0.0
    while rx <= 1.001:
        x = int(w * rx)
        cv2.line(out, (x, 0), (x, h), color, 1)
        cv2.putText(out, f"{rx:.2f}", (x + 2, 14), font, 0.35, color, 1)
        rx += step

    ry = 0.0
    while ry <= 1.001:
        y = int(h * ry)
        cv2.line(out, (0, y), (w, y), color, 1)
        cv2.putText(out, f"{ry:.2f}", (2, y - 2), font, 0.35, color, 1)
        ry += step

    return out


def main():
    parser = argparse.ArgumentParser(description="Calibrate LabVIEW coordinates")
    parser.add_argument("--grid-step", type=float, default=0.05,
                        help="Grid step as fraction (default 0.05 = 5%%)")
    parser.add_argument("--title-filter", default="480")
    args = parser.parse_args()

    windows = list_windows(title_filter=args.title_filter)
    if not windows:
        print("No LabVIEW windows found. Is 480.000.v2.03.exe running?")
        return

    viable = [w for w in windows
              if (w["rect"]["right"] - w["rect"]["left"]) > 10]
    if not viable:
        print("Found windows but all have zero/tiny size:")
        for w in windows:
            print(f'  hwnd={w["hwnd"]} title="{w["title"]}" rect={w["rect"]}')
        return

    win = viable[0]
    hwnd = win["hwnd"]
    r = win["rect"]
    ww = r["right"] - r["left"]
    wh = r["bottom"] - r["top"]
    print(f'Target: hwnd={hwnd} "{win["title"]}" {ww}x{wh}')
    print(f'  rect: left={r["left"]} top={r["top"]} right={r["right"]} bottom={r["bottom"]}')

    print("\nBringing window to foreground...")
    bring_to_front(hwnd)

    print("Capturing screenshot...")
    img = capture_window(hwnd)
    raw_path = save_screenshot(img, ARTIFACTS_DIR, "raw_screenshot.png")
    print(f"  Raw: {raw_path}")

    print("Drawing coordinate grid...")
    grid_img = draw_grid(img, step=args.grid_step)
    grid_path = save_screenshot(grid_img, ARTIFACTS_DIR, "grid_screenshot.png")
    print(f"  Grid: {grid_path}")

    fine_img = draw_grid(img, step=0.01)
    fine_path = save_screenshot(fine_img, ARTIFACTS_DIR, "fine_grid_screenshot.png")
    print(f"  Fine grid (1%%): {fine_path}")

    print(f"\nWindow dimensions: {ww} x {wh} pixels")
    print(f"Open {grid_path} to identify relative coordinates for each UI element.")
    print("Use the grid labels to read (rx, ry) values for buttons and fields.")


if __name__ == "__main__":
    main()
