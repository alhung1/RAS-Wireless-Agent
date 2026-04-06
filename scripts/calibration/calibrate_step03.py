"""Calibrate step 3 (test type selection) positions."""
import sys, os, ctypes, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pyautogui
pyautogui.FAILSAFE = False

import cv2
import numpy as np
from collections import defaultdict
from orchestrator.local_automation.screen_utils import (
    capture_window, save_screenshot, get_window_rect, set_window_rect,
)

ARTS = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')),
    'artifacts',
    'labview_calibration',
)
os.makedirs(ARTS, exist_ok=True)

u = ctypes.windll.user32
hwnd = 2430198

set_window_rect(hwnd, 0, 0, 1260, 950)
time.sleep(0.3)
u.SetForegroundWindow(hwnd)
time.sleep(0.5)

img = capture_window(hwnd)
h, w = img.shape[:2]
save_screenshot(img, ARTS, "step03_fixed_size.png")
print(f"Step03 at {w}x{h}")

orange_px = []
for y in range(0, h):
    for x in range(0, w):
        b, g, r = int(img[y, x, 0]), int(img[y, x, 1]), int(img[y, x, 2])
        if r > 180 and 80 < g < 200 and b < 100:
            orange_px.append((x, y))

if orange_px:
    buckets = defaultdict(list)
    for x, y in orange_px:
        buckets[(x // 50, y // 50)].append((x, y))

    clusters = []
    for key, pts in buckets.items():
        if len(pts) > 5:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            clusters.append(((min(xs) + max(xs)) // 2,
                             (min(ys) + max(ys)) // 2,
                             len(pts)))

    clusters.sort(key=lambda c: -c[2])
    print(f"Orange clusters ({len(clusters)}):")
    for cx, cy, n in clusters[:6]:
        print(f"  center=({cx},{cy}) size={n}")

yellow_px = []
for y in range(200, 450):
    for x in range(0, 500):
        b, g, r = int(img[y, x, 0]), int(img[y, x, 1]), int(img[y, x, 2])
        if r > 230 and g > 230 and b < 80:
            yellow_px.append((x, y))
if yellow_px:
    xs = [p[0] for p in yellow_px]
    ys = [p[1] for p in yellow_px]
    cx = (min(xs) + max(xs)) // 2
    cy = (min(ys) + max(ys)) // 2
    print(f"Yellow dropdown: x=[{min(xs)},{max(xs)}] y=[{min(ys)},{max(ys)}] center=({cx},{cy})")
