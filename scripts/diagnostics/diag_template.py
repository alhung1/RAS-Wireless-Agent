"""Diagnostic: Check template matching for orange_arrow.png at different thresholds."""
import ctypes
import ctypes.wintypes
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from orchestrator.local_automation.screen_utils import (
    get_window_rect, set_window_rect, capture_window, _set_foreground,
    find_template_center,
)
import cv2
import numpy as np

user32 = ctypes.windll.user32
os.makedirs("artifacts/diag_template", exist_ok=True)


def _enum_lv_windows():
    results = []
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        if not title:
            return True
        title_l = title.lower()
        if any(k in title_l for k in ["480", "400 600", ".vi"]):
            r = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w = r.right - r.left
            h = r.bottom - r.top
            results.append((hwnd, title, w, h, (r.left, r.top, r.right, r.bottom)))
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))(cb), 0)
    return results


def main():
    wins = _enum_lv_windows()
    sub_vi = None
    for h, t, w, ht, r in wins:
        if "400 600" in t.lower():
            sub_vi = h
            break
    if not sub_vi:
        print("No sub-VI found")
        return

    hwnd = sub_vi
    print(f"Found: hwnd={hwnd}")

    # Resize to expected size
    set_window_rect(hwnd, 0, 0, 1288, 1040)
    time.sleep(0.5)
    wr = get_window_rect(hwnd)
    print(f"Window: {wr[2]-wr[0]}x{wr[3]-wr[1]}")

    img = capture_window(hwnd)
    cv2.imwrite("artifacts/diag_template/window.png", img)
    print(f"Screenshot: {img.shape[1]}x{img.shape[0]}")

    # Load template
    from pathlib import Path
    tpl_path = Path(__file__).parent.parent / "orchestrator" / "local_automation" / "templates" / "orange_arrow.png"
    tpl = cv2.imread(str(tpl_path))
    if tpl is None:
        print(f"Could not load template: {tpl_path}")
        return
    print(f"Template size: {tpl.shape[1]}x{tpl.shape[0]}")
    cv2.imwrite("artifacts/diag_template/template.png", tpl)

    # Raw template matching
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)

    result = cv2.matchTemplate(gray_img, gray_tpl, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    print(f"\nRaw match: max_val={max_val:.4f} at {max_loc}")
    print(f"  Template center would be at: ({max_loc[0] + tpl.shape[1]//2}, {max_loc[1] + tpl.shape[0]//2})")

    # Draw ALL matches above threshold 0.5
    annotated = img.copy()
    thresholds = [0.9, 0.8, 0.7, 0.6, 0.5]
    colors = [(0, 255, 0), (0, 200, 0), (0, 150, 255), (0, 100, 255), (0, 0, 255)]

    for thresh, color in zip(thresholds, colors):
        locs = np.where(result >= thresh)
        count = len(locs[0])
        print(f"  Threshold {thresh:.1f}: {count} matches")
        for pt in zip(*locs[::-1]):
            cv2.rectangle(annotated, pt, (pt[0] + tpl.shape[1], pt[1] + tpl.shape[0]), color, 2)
            cv2.putText(annotated, f"{thresh}", (pt[0], pt[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    # Mark the best match with a big circle
    best_center = (max_loc[0] + tpl.shape[1]//2, max_loc[1] + tpl.shape[0]//2)
    cv2.circle(annotated, best_center, 20, (0, 0, 255), 3)
    cv2.putText(annotated, f"BEST {max_val:.3f}", (best_center[0] + 25, best_center[1]),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imwrite("artifacts/diag_template/matches.png", annotated)

    # Check find_template_center at 0.70
    center = find_template_center(img, "orange_arrow.png", 0.70)
    print(f"\nfind_template_center(threshold=0.70) = {center}")

    # Check at lower threshold
    center2 = find_template_center(img, "orange_arrow.png", 0.50)
    print(f"find_template_center(threshold=0.50) = {center2}")

    print(f"\nDone. Check artifacts/diag_template/")


if __name__ == "__main__":
    main()
