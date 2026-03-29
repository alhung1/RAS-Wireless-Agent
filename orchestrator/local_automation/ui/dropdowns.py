"""Generic dropdown and listbox interaction primitives.

Product-agnostic: these work with any LabVIEW dropdown or listbox.
Callers pass coordinates and navigation counts.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.screen_utils import capture_window
from orchestrator.local_automation.ui.input_helpers import (
    safe_click,
    safe_press,
    safe_type,
    settle,
)
from orchestrator.local_automation.ui.detection import (
    read_ocr,
    pixel_diff,
    capture_region,
)

logger = get_logger("ui.dropdowns")


# ---------------------------------------------------------------------------
# Bandwidth mode navigation map (LabVIEW v2.03)
# List order: BW20, BW40, BW80, BW160, BW240, BW320, Not Valid
# (up_count, down_count) from any position
# ---------------------------------------------------------------------------

BW_MODE_NAV: dict[str, tuple[int, int]] = {
    "BW20":  (6, 0),
    "BW40":  (6, 1),
    "BW80":  (6, 2),
    "BW160": (6, 3),
    "BW240": (6, 4),
    "BW320": (6, 5),
}


# ---------------------------------------------------------------------------
# Dropdown primitives
# ---------------------------------------------------------------------------

def open_dropdown(
    hwnd: int,
    px: int,
    py: int,
    *,
    dry_run: bool = False,
    ensure_fg_fn=None,
) -> bool:
    """Click a dropdown to open it.  Returns True if click succeeded."""
    clicked = safe_click(hwnd, px, py, label="dropdown_open",
                         dry_run=dry_run, ensure_fg_fn=ensure_fg_fn)
    if clicked and not dry_run:
        time.sleep(1.0)
    return clicked


def select_by_keyboard_nav(
    hwnd: int,
    dropdown_px: tuple[int, int],
    up_presses: int,
    down_presses: int = 0,
    *,
    dry_run: bool = False,
    ensure_fg_fn=None,
) -> None:
    """Open a dropdown and navigate to an item via Up/Down keys.

    Strategy: click dropdown, press Up N times to reach the top,
    then Down M times to the target, then Enter to confirm.
    """
    open_dropdown(hwnd, dropdown_px[0], dropdown_px[1],
                  dry_run=dry_run, ensure_fg_fn=ensure_fg_fn)
    for _ in range(up_presses):
        safe_press("up", label="dropdown_nav", dry_run=dry_run)
        if not dry_run:
            time.sleep(0.15)
    for _ in range(down_presses):
        safe_press("down", label="dropdown_nav", dry_run=dry_run)
        if not dry_run:
            time.sleep(0.15)
    safe_press("enter", label="dropdown_confirm", dry_run=dry_run)
    if not dry_run:
        time.sleep(1.0)


def close_dropdown(
    hwnd: int,
    neutral_px: tuple[int, int] = (400, 300),
    *,
    dry_run: bool = False,
) -> None:
    """Close any open dropdown by pressing Escape + clicking neutral area."""
    safe_press("escape", label="close_dropdown_esc", dry_run=dry_run)
    if not dry_run:
        time.sleep(0.3)
    safe_click(hwnd, neutral_px[0], neutral_px[1],
               label="close_dropdown_neutral", dry_run=dry_run)
    if not dry_run:
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Dropdown state detection
# ---------------------------------------------------------------------------

def detect_dropdown_open(
    hwnd: int,
    dropdown_region: tuple[int, int, int, int],
    before_img=None,
) -> bool:
    """Heuristic: detect whether a dropdown is open by checking if
    the region around it changed significantly.

    *dropdown_region* is (x, y, w, h) around the dropdown.
    *before_img* is the screenshot before the click.
    If before_img is None, returns True (assume it opened).
    """
    if before_img is None:
        return True
    try:
        after_img = capture_window(hwnd)
        x, y, w, h = dropdown_region
        expand_h = min(h * 3, after_img.shape[0] - y)
        pct, _ = pixel_diff(before_img, after_img, x, y, w, expand_h)
        opened = pct > 2.0
        if not opened:
            logger.warning(
                "Dropdown at (%d,%d) may not have opened (%.1f%% diff)",
                x, y, pct,
                extra={"action": "detect_dropdown", "step": "not_open"})
        return opened
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Dropdown retry / reopen
# ---------------------------------------------------------------------------

def select_with_retry(
    hwnd: int,
    dropdown_px: tuple[int, int],
    up_presses: int,
    down_presses: int = 0,
    max_retries: int = 2,
    *,
    dry_run: bool = False,
    ensure_fg_fn=None,
) -> int:
    """Select a dropdown item with retry on failure.

    Returns the number of attempts used (1 = first try succeeded).
    """
    for attempt in range(1, max_retries + 1):
        before_img = None
        if not dry_run:
            try:
                before_img = capture_window(hwnd)
            except Exception:
                pass

        select_by_keyboard_nav(
            hwnd, dropdown_px, up_presses, down_presses,
            dry_run=dry_run, ensure_fg_fn=ensure_fg_fn,
        )

        if dry_run:
            return attempt

        dropdown_region = (
            max(dropdown_px[0] - 20, 0),
            max(dropdown_px[1] - 10, 0),
            200, 40,
        )
        if detect_dropdown_open(hwnd, dropdown_region, before_img):
            return attempt

        logger.info("Dropdown retry %d/%d at (%d,%d)",
                    attempt, max_retries, dropdown_px[0], dropdown_px[1],
                    extra={"action": "dropdown_retry", "step": "reopen"})
        close_dropdown(hwnd, dry_run=dry_run)

    return max_retries


# ---------------------------------------------------------------------------
# Listbox navigation (for AP/Client popup lists)
# ---------------------------------------------------------------------------

def build_listbox_items(
    folder_path: str,
    exclude: set[str] | None = None,
) -> list[str]:
    """Read .txt stems from *folder_path*, uppercase, sort, filter.

    Returns the sorted list matching LabVIEW's listbox order.
    """
    exclude = exclude or set()
    items = []
    try:
        for f in os.listdir(folder_path):
            if not f.lower().endswith(".txt"):
                continue
            stem = f[:-4].upper()
            if stem in exclude:
                continue
            items.append(stem)
    except FileNotFoundError:
        logger.warning("Listbox folder not found: %s", folder_path)
    items.sort()
    return items


def navigate_listbox_to_item(
    popup_hwnd: int,
    folder_path: str,
    target_name: str,
    calibration_offset: int = 0,
    *,
    dry_run: bool = False,
) -> bool:
    """Navigate a LabVIEW listbox to *target_name* using Home + Down(N).

    Reads .txt files in *folder_path* to compute the index.
    Returns True if the target was found and navigated to.
    """
    import pyautogui

    items = build_listbox_items(folder_path)
    target_upper = target_name.upper()
    if target_upper not in items:
        logger.error("Target %r not in %s (%d items)",
                     target_name, folder_path, len(items),
                     extra={"action": "listbox_nav", "step": "not_found"})
        return False

    target_idx = items.index(target_upper) + calibration_offset
    target_idx = max(0, min(target_idx, len(items) - 1))
    logger.info("Navigating to %r: Home + Down(%d) in %s (%d items)",
                target_name, target_idx, folder_path, len(items),
                extra={"action": "listbox_nav", "step": "folder_nav"})

    if dry_run:
        return True

    from orchestrator.local_automation.ui.window_manager import WindowManager
    wm = WindowManager()
    wm.force_foreground(popup_hwnd)
    time.sleep(0.5)

    rect = wm.get_rect(popup_hwnd)
    abs_x = rect[0] + 120
    abs_y = rect[1] + 300
    pyautogui.click(abs_x, abs_y)
    time.sleep(0.3)

    pyautogui.press("home")
    time.sleep(0.4)

    for _ in range(target_idx):
        pyautogui.press("down")
        time.sleep(0.02)
    time.sleep(0.4)

    return True
