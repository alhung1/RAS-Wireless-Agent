"""Inspect LabVIEW windows: list visible windows, capture screenshot, UIA dump.

Usage:
    python scripts/inspect_labview_window.py
    python scripts/inspect_labview_window.py --title-filter "480"
    python scripts/inspect_labview_window.py --pid 12345
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "artifacts", "labview_inspect",
)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def list_windows(title_filter: str = "", pid_filter: int = 0) -> list[dict]:
    """Enumerate all visible top-level windows."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    results = []

    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        tid, pid = wintypes.DWORD(), wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        if title_filter and title_filter.lower() not in title.lower():
            return True
        if pid_filter and pid.value != pid_filter:
            return True

        from orchestrator.local_automation.screen_utils import get_window_rect
        rect = get_window_rect(hwnd)

        results.append({
            "hwnd": hwnd,
            "title": title,
            "pid": pid.value,
            "rect": {"left": rect[0], "top": rect[1],
                     "right": rect[2], "bottom": rect[3]},
        })
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return results


def capture_screenshot(hwnd: int, name: str) -> str:
    from orchestrator.local_automation.screen_utils import capture_window, save_screenshot
    img = capture_window(hwnd)
    return save_screenshot(img, ARTIFACTS_DIR, name)


def try_uia_dump(hwnd: int) -> dict:
    """Attempt UIA element tree dump for the window."""
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        for win in desktop.windows():
            if win.handle == hwnd:
                dump = {"accessible": True, "children": []}
                try:
                    for child in win.children():
                        info = {
                            "control_type": child.element_info.control_type,
                            "name": child.element_info.name,
                            "automation_id": child.element_info.automation_id,
                            "class_name": child.element_info.class_name,
                        }
                        try:
                            r = child.element_info.rectangle
                            info["rect"] = {"left": r.left, "top": r.top,
                                            "right": r.right, "bottom": r.bottom}
                        except Exception:
                            pass
                        dump["children"].append(info)
                except Exception as exc:
                    dump["children_error"] = str(exc)
                return dump
        return {"accessible": False, "error": "Window not found in UIA desktop"}
    except Exception as exc:
        return {"accessible": False, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Inspect LabVIEW windows")
    parser.add_argument("--title-filter", default="480",
                        help="Filter windows by title substring (default: '480')")
    parser.add_argument("--pid", type=int, default=0,
                        help="Filter by process ID")
    parser.add_argument("--all", action="store_true",
                        help="List ALL visible windows (no filter)")
    args = parser.parse_args()

    filt = "" if args.all else args.title_filter
    windows = list_windows(title_filter=filt, pid_filter=args.pid)

    print(f"\nFound {len(windows)} window(s):\n")
    for w in windows:
        r = w["rect"]
        size = f'{r["right"] - r["left"]}x{r["bottom"] - r["top"]}'
        print(f'  hwnd={w["hwnd"]}  pid={w["pid"]}  {size}  "{w["title"]}"')

    report = {"timestamp": _ts(), "windows": []}

    for w in windows:
        entry = {**w}
        del entry["hwnd"]

        ts = _ts()
        try:
            ss_path = capture_screenshot(w["hwnd"], f"window_{w['pid']}_{ts}.png")
            entry["screenshot"] = ss_path
            print(f'\n  Screenshot: {ss_path}')
        except Exception as exc:
            entry["screenshot_error"] = str(exc)
            print(f'\n  Screenshot failed: {exc}')

        print(f'  Attempting UIA dump for "{w["title"]}"...')
        uia = try_uia_dump(w["hwnd"])
        entry["uia"] = uia
        if uia.get("accessible"):
            n = len(uia.get("children", []))
            print(f'  UIA: {n} children found')
            for child in uia.get("children", [])[:20]:
                name = child.get("name", "")
                ctype = child.get("control_type", "")
                aid = child.get("automation_id", "")
                if name or aid:
                    print(f'    [{ctype}] name={name!r} aid={aid!r}')
        else:
            print(f'  UIA not accessible: {uia.get("error", "unknown")}')

        report["windows"].append(entry)

    report_path = os.path.join(ARTIFACTS_DIR, f"inspect_{_ts()}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f'\nReport: {report_path}')


if __name__ == "__main__":
    main()
