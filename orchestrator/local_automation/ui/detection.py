"""Visual detection primitives -- screenshot regions, OCR, template match,
pixel diff.

Product-agnostic wrappers used by verification.py and step implementations.
All functions accept explicit parameters.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.screen_utils import (
    capture_window,
    save_screenshot,
    find_template_center,
    screen_contains,
    is_ocr_available,
    ocr_region,
    ocr_region_freeform,
    load_template,
    find_template,
)

logger = get_logger("ui.detection")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# ---------------------------------------------------------------------------
# Screenshot region
# ---------------------------------------------------------------------------

def capture_region(
    hwnd: int,
    x: int,
    y: int,
    w: int,
    h: int,
) -> np.ndarray:
    """Capture a rectangular region of a window as a BGR numpy array.

    Coordinates are window-relative.  Returns a cropped sub-image.
    """
    full = capture_window(hwnd)
    y2 = min(y + h, full.shape[0])
    x2 = min(x + w, full.shape[1])
    x1, y1 = max(x, 0), max(y, 0)
    region = full[y1:y2, x1:x2]
    if region.size == 0:
        raise ValueError(f"Empty region ({x},{y},{w},{h}) from {full.shape[1]}x{full.shape[0]} image")
    return region


def save_region(
    img: np.ndarray,
    artifacts_dir: str,
    name: str,
) -> str:
    """Save a BGR image to artifacts_dir/name.  Returns file path."""
    os.makedirs(artifacts_dir, exist_ok=True)
    path = os.path.join(artifacts_dir, name)
    cv2.imwrite(path, img)
    return path


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def ocr_available() -> bool:
    """Check whether pytesseract is installed and working."""
    return is_ocr_available()


def read_ocr(
    hwnd: int,
    x: int,
    y: int,
    w: int,
    h: int,
    preprocess: bool = True,
) -> str:
    """OCR a rectangular region of a window.  Returns extracted text.

    Returns empty string if OCR is unavailable or fails.
    """
    if not is_ocr_available():
        return ""
    try:
        img = capture_window(hwnd)
        return ocr_region(img, x, y, w, h, preprocess=preprocess)
    except Exception as exc:
        logger.warning("read_ocr at (%d,%d,%d,%d) failed: %s", x, y, w, h, exc)
        return ""


def read_ocr_from_image(
    img: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    preprocess: bool = True,
) -> str:
    """OCR a region from an already-captured image."""
    if not is_ocr_available():
        return ""
    return ocr_region(img, x, y, w, h, preprocess=preprocess)


def read_ocr_freeform(
    hwnd: int,
    x: int,
    y: int,
    w: int,
    h: int,
) -> str:
    """OCR a region with PSM 6 (block of text) for multi-line content."""
    if not is_ocr_available():
        return ""
    try:
        img = capture_window(hwnd)
        return ocr_region_freeform(img, x, y, w, h)
    except Exception as exc:
        logger.warning("read_ocr_freeform at (%d,%d,%d,%d) failed: %s",
                       x, y, w, h, exc)
        return ""


# ---------------------------------------------------------------------------
# Pixel diff
# ---------------------------------------------------------------------------

def pixel_diff(
    before: np.ndarray,
    after: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    threshold: int = 10,
) -> tuple[float, bool]:
    """Compare a rectangular region in two images.

    Returns (diff_pct, region_has_size_mismatch).
    *diff_pct* is the percentage of pixels that differ by more than
    *threshold* intensity.
    """
    r1 = before[max(y, 0):y + h, max(x, 0):x + w]
    r2 = after[max(y, 0):y + h, max(x, 0):x + w]
    if r1.shape != r2.shape:
        return 100.0, True
    diff = np.abs(r1.astype(float) - r2.astype(float))
    changed = int(np.sum(diff.mean(axis=2) > threshold))
    total = r1.shape[0] * r1.shape[1]
    if total == 0:
        return 0.0, False
    return (changed / total) * 100.0, False


def region_changed(
    before: np.ndarray,
    after: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    min_diff_pct: float = 1.0,
) -> bool:
    """Return True if the region changed by at least min_diff_pct percent."""
    pct, _ = pixel_diff(before, after, x, y, w, h)
    return pct >= min_diff_pct


# ---------------------------------------------------------------------------
# Template matching
# ---------------------------------------------------------------------------

def find_on_screen(
    hwnd: int,
    template_name: str,
    threshold: float = 0.80,
) -> tuple[int, int] | None:
    """Find a template on the current window screenshot.

    Returns (cx, cy) center of the match in window-relative coords,
    or None if not found.
    """
    return find_template_center(capture_window(hwnd), template_name, threshold)


def is_on_screen(
    hwnd: int,
    template_name: str,
    threshold: float = 0.80,
) -> bool:
    """Check if a template is visible on the window."""
    return screen_contains(capture_window(hwnd), template_name, threshold)


def template_match_score(
    img: np.ndarray,
    template_name: str,
) -> float:
    """Return the best match score (0..1) for a template on an image.

    Returns 0.0 if the template is not found or cannot be loaded.
    """
    tpl = load_template(template_name)
    if tpl is None:
        return 0.0
    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


# ---------------------------------------------------------------------------
# HSV color detection (for orange arrow)
# ---------------------------------------------------------------------------

def detect_orange_region(
    hwnd: int,
    hue_range: tuple[int, int] = (10, 25),
    sat_min: int = 150,
    val_min: int = 150,
    min_area: int = 200,
    dry_run: bool = False,
) -> tuple[int, int] | None:
    """Find the rightmost orange region via HSV thresholding.

    Returns (cx, cy) center in window-relative coords, or None.
    Returns None immediately in dry_run mode.
    """
    if dry_run:
        return None
    try:
        img = capture_window(hwnd)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower = np.array([hue_range[0], sat_min, val_min])
        upper = np.array([hue_range[1], 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue
            bx, by, bw, bh = cv2.boundingRect(c)
            cx, cy = bx + bw // 2, by + bh // 2
            if best is None or cx > best[0]:
                best = (cx, cy)
        return best
    except Exception as exc:
        logger.warning("detect_orange_region failed: %s", exc)
        return None
