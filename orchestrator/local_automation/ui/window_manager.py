"""Window management -- find, focus, dismiss, and verify LabVIEW windows.

Wraps all Win32 window operations into a stateful WindowManager class
that replaces the module-level globals (LV_PID, popup tracking) in
the legacy code.

Product-agnostic: callers pass title hints and window handles.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Optional

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.screen_utils import (
    get_window_rect,
    set_window_rect,
    minimize_window,
)
from orchestrator.local_automation.ui.coordinates import (
    POPUP_TITLE_HINTS,
    BLOCKER_TITLE_HINTS,
    DEFAULT_LV_TITLE_HINTS,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
)
from orchestrator.local_automation.ui.input_helpers import (
    safe_click,
    safe_press,
)

logger = get_logger("ui.window_manager")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9
SW_MINIMIZE = 6
EXCLUDED_WINDOW_TITLE_SUBSTRINGS = (
    "crash reporter",
)


@dataclass
class WindowInfo:
    """Structured description of a discovered window."""
    hwnd: int
    title: str
    width: int
    height: int
    rect: tuple[int, int, int, int]


class WindowManager:
    """Stateful window manager for LabVIEW automation.

    Holds PID tracking and popup-dismiss cooldown state.
    Pass via StepContext so all steps share one instance.
    """

    def __init__(self) -> None:
        self.lv_pid: int | None = None
        self._popup_dismissed_hwnds: set[int] = set()
        self._popup_dismiss_times: dict[int, float] = {}
        self._popup_cooldown_sec: float = 3.0

    def reset(self) -> None:
        """Clear all cached state (call at start of a new run)."""
        self.lv_pid = None
        self._popup_dismissed_hwnds.clear()
        self._popup_dismiss_times.clear()

    # ------------------------------------------------------------------
    # Window title
    # ------------------------------------------------------------------

    @staticmethod
    def get_title(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value

    # ------------------------------------------------------------------
    # Window rect / size
    # ------------------------------------------------------------------

    @staticmethod
    def get_rect(hwnd: int) -> tuple[int, int, int, int]:
        return get_window_rect(hwnd)

    @staticmethod
    def set_rect(hwnd: int, left: int, top: int, width: int, height: int) -> None:
        set_window_rect(hwnd, left, top, width, height)

    # ------------------------------------------------------------------
    # Foreground / focus
    # ------------------------------------------------------------------

    @staticmethod
    def force_foreground(hwnd: int) -> None:
        """Robustly bring hwnd to foreground using AttachThreadInput."""
        fg = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        my_tid = kernel32.GetCurrentThreadId()
        if fg_tid != my_tid:
            user32.AttachThreadInput(my_tid, fg_tid, True)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if fg_tid != my_tid:
            user32.AttachThreadInput(my_tid, fg_tid, False)

    def ensure_foreground(self, hwnd: int, max_retries: int = 3,
                          dry_run: bool = False) -> bool:
        """Bring hwnd to foreground, minimizing blockers if needed.

        Returns True when GetForegroundWindow() matches hwnd.
        No-op in dry_run mode (returns True).
        """
        if dry_run:
            return True
        for attempt in range(max_retries):
            self.force_foreground(hwnd)
            time.sleep(0.15)
            fg = user32.GetForegroundWindow()
            if fg == hwnd:
                return True
            fg_title = self.get_title(fg)
            logger.warning(
                "Foreground is %r (hwnd=%d), expected hwnd=%d — "
                "minimizing blocker (attempt %d/%d)",
                fg_title, fg, hwnd, attempt + 1, max_retries,
                extra={"action": "ensure_foreground", "step": "minimize_blocker"},
            )
            user32.ShowWindow(fg, SW_MINIMIZE)
            time.sleep(0.3)
        return user32.GetForegroundWindow() == hwnd

    def verify_foreground(self, hwnd: int) -> bool:
        """Check (without acting) whether hwnd is the foreground window."""
        return user32.GetForegroundWindow() == hwnd

    # ------------------------------------------------------------------
    # Window enumeration
    # ------------------------------------------------------------------

    def _resolve_pid(self) -> int | None:
        if self.lv_pid:
            return self.lv_pid
        wins = self.enum_windows()
        for w in wins:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(w.hwnd, ctypes.byref(pid))
            self.lv_pid = pid.value
            return self.lv_pid
        return None

    def enum_windows(
        self,
        title_hints: list[str] | None = None,
    ) -> list[WindowInfo]:
        """Enumerate visible windows matching *title_hints*."""
        results: list[WindowInfo] = []
        hints = title_hints or DEFAULT_LV_TITLE_HINTS
        lv_pid = self.lv_pid

        def _cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value
            if not title:
                return True
            title_lower = title.lower()
            if any(bad in title_lower for bad in EXCLUDED_WINDOW_TITLE_SUBSTRINGS):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            match = False
            if lv_pid and pid.value == lv_pid:
                match = True
            elif any(h.lower() in title_lower for h in hints):
                match = True
            if match:
                r = get_window_rect(hwnd)
                w = r[2] - r[0]
                h = r[3] - r[1]
                if w > 10 and h > 10:
                    results.append(WindowInfo(hwnd, title, w, h, r))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        return results

    # ------------------------------------------------------------------
    # Find specific windows
    # ------------------------------------------------------------------

    def find_window(
        self,
        title_hints: list[str] | None = None,
    ) -> int | None:
        """Find the main LabVIEW window. Sets lv_pid as side effect."""
        hints = title_hints or ["480 000.vi", "480", "RvR"]
        wins = self.enum_windows(hints)
        for w in wins:
            if any(h.lower() in w.title.lower() for h in hints):
                logger.info("Found LabVIEW window: hwnd=%d title=%r",
                            w.hwnd, w.title,
                            extra={"action": "find_window", "step": "found"})
                if not self.lv_pid:
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(w.hwnd, ctypes.byref(pid))
                    self.lv_pid = pid.value
                return w.hwnd
        return None

    def find_vi_window(
        self,
        title_contains: str,
        timeout: float = 5.0,
    ) -> int | None:
        """Poll until a VI window whose title contains the string appears."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            wins = self.enum_windows(title_hints=[title_contains])
            for w in wins:
                if title_contains.lower() in w.title.lower():
                    return w.hwnd
            time.sleep(0.5)
        return None

    def find_active_vi(
        self,
        exclude_titles: list[str] | None = None,
    ) -> int | None:
        """Find the largest visible non-main window."""
        wins = self.enum_windows()
        exclude = set(t.lower() for t in (exclude_titles or ["480 000.vi"]))
        candidates = [
            w for w in wins
            if w.title.lower() not in exclude and w.width > 100 and w.height > 100
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda c: c.width * c.height)
        return best.hwnd

    def verify_window_exists(self, hwnd: int) -> bool:
        """Check whether a window handle is still valid and visible."""
        return bool(user32.IsWindowVisible(hwnd))

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup_vi(
        self,
        hwnd: int,
        width: int = WINDOW_WIDTH,
        height: int = WINDOW_HEIGHT,
        dry_run: bool = False,
    ) -> None:
        """Position window at (0,0), dismiss popups, bring to foreground.

        No-op in dry_run mode.
        """
        if dry_run:
            return
        self.dismiss_lv_popups()
        self.dismiss_dialogs()
        set_window_rect(hwnd, 0, 0, width, height)
        time.sleep(0.3)
        r = get_window_rect(hwnd)
        actual_w, actual_h = r[2] - r[0], r[3] - r[1]
        if actual_w != width or actual_h != height:
            logger.warning("Window resize to %dx%d produced %dx%d — retrying",
                           width, height, actual_w, actual_h,
                           extra={"action": "setup_vi", "step": "resize_mismatch"})
            set_window_rect(hwnd, 0, 0, width, height)
            time.sleep(0.5)
        self.ensure_foreground(hwnd)
        time.sleep(0.3)

    # ------------------------------------------------------------------
    # Popup / dialog dismissal
    # ------------------------------------------------------------------

    def dismiss_lv_popups(self, dry_run: bool = False) -> int:
        """Auto-dismiss known LabVIEW popup VIs.

        Blockers are minimized immediately.  Other popups get Enter/click
        first; if they persist, they are minimized.
        Returns the count of dismissed/minimized popups.
        No-op in dry_run mode (returns 0).
        """
        if dry_run:
            return 0
        dismissed = 0
        now = time.monotonic()

        for hint in BLOCKER_TITLE_HINTS:
            hwnd = self.find_vi_window(hint, timeout=0.3)
            if not hwnd:
                continue
            title = self.get_title(hwnd)
            logger.info("Minimizing blocker window: %r (hwnd=%d)", title, hwnd,
                        extra={"action": "dismiss_popup", "step": "minimize_blocker"})
            minimize_window(hwnd)
            time.sleep(0.3)
            dismissed += 1

        for hint in POPUP_TITLE_HINTS:
            hwnd = self.find_vi_window(hint, timeout=0.3)
            if not hwnd:
                continue
            last = self._popup_dismiss_times.get(hwnd, 0.0)
            if now - last < self._popup_cooldown_sec:
                continue
            already_tried = hwnd in self._popup_dismissed_hwnds
            self._popup_dismissed_hwnds.add(hwnd)
            self._popup_dismiss_times[hwnd] = now

            title = self.get_title(hwnd)
            if already_tried:
                logger.info("Minimizing persistent popup: %r (hwnd=%d)",
                            title, hwnd,
                            extra={"action": "dismiss_popup", "step": "minimize"})
                minimize_window(hwnd)
                time.sleep(0.3)
            else:
                logger.info("Auto-dismissing popup: %r (hwnd=%d)", title, hwnd,
                            extra={"action": "dismiss_popup", "step": "enter"})
                self.force_foreground(hwnd)
                time.sleep(0.3)
                r = get_window_rect(hwnd)
                w, h = r[2] - r[0], r[3] - r[1]
                safe_click(
                    hwnd,
                    w - 80,
                    h - 50,
                    label="dismiss_popup_click",
                    ensure_fg_fn=self.force_foreground,
                )
                time.sleep(0.5)
                safe_press("enter", label="dismiss_popup_enter")
                time.sleep(1.0)
            dismissed += 1
        return dismissed

    def dismiss_dialogs(self, dry_run: bool = False) -> int:
        """Find and dismiss small untitled LabVIEW dialog windows.

        No-op in dry_run mode (returns 0).
        """
        if dry_run:
            return 0
        pid = self._resolve_pid()
        if not pid:
            return 0
        dismissed = 0

        def _cb(hwnd, _):
            nonlocal dismissed
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value != pid or not user32.IsWindowVisible(hwnd):
                return True
            r = get_window_rect(hwnd)
            w, h = r[2] - r[0], r[3] - r[1]
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if 80 < w < 300 and 50 < h < 200 and not buf.value:
                safe_click(
                    hwnd,
                    50,
                    h - 30,
                    label="dismiss_dialog_click",
                    ensure_fg_fn=self.force_foreground,
                )
                time.sleep(0.5)
                dismissed += 1
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        if dismissed:
            logger.info("Dismissed %d dialog(s)", dismissed,
                        extra={"action": "dismiss_dialogs", "step": "done"})
        return dismissed

    # ------------------------------------------------------------------
    # Transition verification
    # ------------------------------------------------------------------

    def verify_transition(
        self,
        old_hwnd: int,
        expected_hint: str | None = None,
        timeout: float = 10.0,
    ) -> tuple[int | None, bool]:
        """Wait for the screen to change after clicking an arrow.

        Returns (new_hwnd, success).
        """
        old_title = self.get_title(old_hwnd)
        deadline = time.monotonic() + timeout

        popup_lower = [p.lower() for p in POPUP_TITLE_HINTS + BLOCKER_TITLE_HINTS]

        def _is_popup(title: str) -> bool:
            tl = title.lower()
            return any(p in tl for p in popup_lower)

        while time.monotonic() < deadline:
            self.dismiss_lv_popups()

            if expected_hint:
                for w in self.enum_windows():
                    if expected_hint.lower() in w.title.lower() and w.hwnd != old_hwnd:
                        return w.hwnd, True
            else:
                active = self.find_active_vi()
                if active and active != old_hwnd:
                    new_title = self.get_title(active)
                    if (new_title.lower() != old_title.lower()
                            and not _is_popup(new_title)):
                        return active, True

                cur_title = self.get_title(old_hwnd)
                if cur_title and cur_title.lower() != old_title.lower():
                    return old_hwnd, True

                if not user32.IsWindowVisible(old_hwnd):
                    new_vi = self.find_active_vi()
                    if new_vi and not _is_popup(self.get_title(new_vi)):
                        return new_vi, True

            time.sleep(0.5)

        logger.error("Transition FAILED: screen unchanged after %.1fs",
                     timeout,
                     extra={"action": "verify_transition", "step": "failed"})
        return None, False
