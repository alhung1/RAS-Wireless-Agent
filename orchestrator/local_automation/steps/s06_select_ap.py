"""Step 06: Select AP from popup list (400 600 AP.vi).

Critical step -- mandatory verification that AP name appears on screen
after selection.

Strategy:
  1. Click AP icon to open popup
  2. Use folder-index navigation (Home + Down(N)) as PRIMARY
     (OCR popup search is unreliable on LabVIEW list font)
  3. Click Done to close popup
  4. Verify popup is actually closed (prevent step 7 blocking)
  5. Wait for AP info to load (orange arrow polling)
  6. Verify AP name appears on the main AP screen via OCR

Does NOT click the orange arrow -- that is deferred to step 07
(use_last_ap) which handles the firmware field and Use-Last toggle.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.steps.base import BaseStep
from orchestrator.local_automation.steps.step_result import (
    StepResult,
    VerificationEvidence,
    VerificationSpec,
)
from orchestrator.local_automation.ui.coordinates import (
    AP_ICON_CLICK_PX,
    POPUP_SIZE,
    AP_FOLDER,
)
from orchestrator.local_automation.ui.input_helpers import (
    safe_click,
    take_screenshot,
    settle,
)
from orchestrator.local_automation.ui.dropdowns import (
    navigate_listbox_to_item,
)
from orchestrator.local_automation.ui.detection import (
    detect_orange_region,
    find_on_screen,
)
from orchestrator.local_automation.ui.verification import (
    execute_verification,
    save_evidence,
    poll_until,
    poll_for_window,
)

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.recovery.diagnosis import Diagnosis

logger = get_logger("steps.s06_select_ap")

_POPUP_HINTS = ["list in folder", "8002"]
_AP_VI_HINT = "400 600 AP"
_AP_INFO_TIMEOUT = 120.0


class SelectAPStep(BaseStep):
    """Select Access Point from a popup listbox.

    Precondition: an AP-related VI is visible (after step 05 transition).
    Action: open popup, navigate to AP via folder-index, click Done.
    Verification: OCR full-screen for AP name on the AP configuration screen.
    """

    name = "s06_select_ap"
    step_index = 6
    timeout = 240.0
    max_retries = 2
    is_critical = True

    def __init__(self):
        self._vi_hwnd: int | None = None
        self._evidence: VerificationEvidence | None = None

    def precondition(self, ctx: "StepContext") -> bool:
        wm = ctx.get_window_manager()
        self._vi_hwnd = wm.find_active_vi()
        if not self._vi_hwnd:
            poll_until(lambda: wm.find_active_vi() is not None,
                       timeout=5.0, desc="AP selection VI")
            self._vi_hwnd = wm.find_active_vi()
        if not self._vi_hwnd:
            logger.warning("Precondition failed: no VI for AP selection",
                           extra={"action": "precondition", "step": self.name})
            return False
        wm.setup_vi(self._vi_hwnd, dry_run=ctx.dry_run)
        return True

    def execute(self, ctx: "StepContext") -> StepResult:
        hwnd = self._vi_hwnd
        if hwnd is None:
            return StepResult(ok=False, step_name=self.name,
                              error="No VI window for AP selection")

        wm = ctx.get_window_manager()
        ad = ctx.step_artifacts_dir(self.name)
        ap_name = ctx.run_config.ap_name
        dr = ctx.dry_run
        artifacts: list[str] = []

        _a(artifacts, take_screenshot(hwnd, ad, "before.png"))

        # --- 1. Click AP icon to open popup ---
        wm.dismiss_lv_popups(dry_run=dr)
        wm.ensure_foreground(hwnd, dry_run=dr)
        safe_click(hwnd, AP_ICON_CLICK_PX[0], AP_ICON_CLICK_PX[1],
                   label="ap_icon", dry_run=dr)

        # --- 2. Wait for popup to appear ---
        popup_hwnd = None
        if not dr:
            for hint in _POPUP_HINTS:
                popup_hwnd = poll_for_window(wm, hint, timeout=5.0)
                if popup_hwnd:
                    break

        if popup_hwnd:
            from orchestrator.local_automation.screen_utils import set_window_rect
            set_window_rect(popup_hwnd, 0, 0, *POPUP_SIZE)
            settle(500)
            wm.ensure_foreground(popup_hwnd)
            settle(300)
            _a(artifacts, take_screenshot(popup_hwnd, ad, "popup_open.png"))

            # --- 3. Navigate to AP via folder-index (PRIMARY) ---
            logger.info("Using folder-index nav for AP %r (primary strategy)",
                        ap_name,
                        extra={"action": "execute", "step": self.name})
            nav_ok = navigate_listbox_to_item(
                popup_hwnd, AP_FOLDER, ap_name, dry_run=dr)
            if not nav_ok:
                _a(artifacts, take_screenshot(popup_hwnd, ad, "nav_failed.png"))
                return StepResult(
                    ok=False, step_name=self.name,
                    error=f"AP {ap_name!r} not found in {AP_FOLDER}",
                    artifact_paths=artifacts,
                )
            _a(artifacts, take_screenshot(popup_hwnd, ad, "after_nav.png"))

            # --- 4. Click Done button ---
            from orchestrator.local_automation.ui.detection import find_on_screen
            done_center = None
            if not dr:
                try:
                    from orchestrator.local_automation.screen_utils import capture_window
                    popup_img = capture_window(popup_hwnd)
                    from orchestrator.local_automation.screen_utils import find_template_center as _ftc
                    done_center = _ftc(popup_img, "done_button.png", 0.70)
                except Exception:
                    pass
            if done_center:
                safe_click(popup_hwnd, done_center[0], done_center[1],
                           label="done_button_template", dry_run=dr)
            else:
                from orchestrator.local_automation.ui.coordinates import DONE_BUTTON_FALLBACK_PX
                safe_click(popup_hwnd, DONE_BUTTON_FALLBACK_PX[0],
                           DONE_BUTTON_FALLBACK_PX[1],
                           label="done_button_fallback", dry_run=dr)
            settle(1500)

            # --- 5. Verify popup is closed ---
            if not dr:
                popup_clear = self._verify_popups_closed(wm, ad)
                if not popup_clear:
                    _a(artifacts, take_screenshot(hwnd, ad, "popup_stuck.png"))
                    return StepResult(
                        ok=False, step_name=self.name,
                        error="popup_not_closed: AP/Client popup still open after Done",
                        artifact_paths=artifacts,
                    )
        elif not dr:
            logger.warning("AP popup did not appear after icon click",
                           extra={"action": "execute", "step": "no_popup"})
            _a(artifacts, take_screenshot(hwnd, ad, "no_popup.png"))

        # --- 6. Find the AP configuration screen ---
        if not dr:
            ap_vi = wm.find_vi_window(_AP_VI_HINT, timeout=10.0)
            if not ap_vi:
                ap_vi = wm.find_active_vi()
            if not ap_vi:
                return StepResult(
                    ok=False, step_name=self.name,
                    error=f"{_AP_VI_HINT} not found after popup",
                    artifact_paths=artifacts,
                )
            wm.setup_vi(ap_vi, dry_run=dr)
            self._vi_hwnd = ap_vi
            settle(1000)
        else:
            ap_vi = hwnd

        # --- 7. Wait for AP info to load (orange arrow polling) ---
        if not dr:
            logger.info("Waiting for AP info (orange arrow, up to %.0fs)...",
                        _AP_INFO_TIMEOUT,
                        extra={"action": "execute", "step": "wait_ap_info"})
            arrow_found = poll_until(
                lambda: detect_orange_region(ap_vi) is not None,
                timeout=_AP_INFO_TIMEOUT, interval=3.0,
                desc="orange arrow on AP screen",
            )
            if not arrow_found:
                logger.warning(
                    "Orange arrow not detected after %.0fs — continuing",
                    _AP_INFO_TIMEOUT,
                    extra={"action": "execute", "step": "ap_info_timeout"})

        _a(artifacts, take_screenshot(ap_vi, ad, "ap_screen.png"))

        # --- 8. Verify AP name on screen ---
        self._evidence = self._run_verification(ctx, ap_vi, ap_name, ad)
        if self._evidence:
            _a(artifacts, save_evidence(self._evidence, ad, self.name))

        if self._evidence and not self._evidence.match:
            return StepResult(
                ok=False, step_name=self.name,
                error=f"AP {ap_name!r} not confirmed on screen after selection",
                verified=False,
                verification_evidence=self._evidence,
                artifact_paths=artifacts,
            )

        # NOTE: orange arrow click is deferred to step_07 (use_last_ap)
        logger.info("AP selection complete — arrow deferred to step_07",
                    extra={"action": "execute", "step": "done"})

        return StepResult(
            ok=True, step_name=self.name,
            verified=self._evidence.match if self._evidence else False,
            verification_evidence=self._evidence,
            artifact_paths=artifacts,
            details={"ap_name": ap_name, "strategy": "folder_index"},
        )

    def verify(self, ctx: "StepContext") -> VerificationEvidence:
        if self._evidence:
            return self._evidence
        return VerificationEvidence(method="none", match=True,
                                    detail="No evidence collected")

    def recover(self, ctx: "StepContext", diagnosis: "Diagnosis") -> bool:
        wm = ctx.get_window_manager()
        dr = ctx.dry_run
        self._close_all_popups(wm, dr)
        wm.dismiss_lv_popups(dry_run=dr)
        wm.dismiss_dialogs(dry_run=dr)
        if self._vi_hwnd:
            wm.ensure_foreground(self._vi_hwnd, dry_run=dr)
        settle(500)
        return True

    # ------------------------------------------------------------------

    def _verify_popups_closed(self, wm, ad: str, max_attempts: int = 3) -> bool:
        """Ensure all AP/Client popup windows are gone."""
        for attempt in range(max_attempts):
            popups = self._find_popups(wm)
            if not popups:
                return True
            logger.warning(
                "%d AP/Client popup(s) still open (attempt %d/%d): %s",
                len(popups), attempt + 1, max_attempts,
                [(h, t) for h, t in popups],
                extra={"action": "popup_check", "step": self.name})
            for p_hwnd, _ in popups:
                from orchestrator.local_automation.screen_utils import minimize_window
                minimize_window(p_hwnd)
                time.sleep(0.5)
            wm.dismiss_lv_popups()
            time.sleep(1.0)

        remaining = self._find_popups(wm)
        if remaining:
            logger.error("POPUP BLOCKED: %d popup(s) after %d attempts",
                         len(remaining), max_attempts,
                         extra={"action": "popup_blocked", "step": self.name})
            return False
        return True

    def _find_popups(self, wm) -> list[tuple[int, str]]:
        found = []
        for w in wm.enum_windows(title_hints=_POPUP_HINTS):
            tl = w.title.lower()
            if any(h in tl for h in ["8002", "list in folder"]):
                found.append((w.hwnd, w.title))
        return found

    def _close_all_popups(self, wm, dry_run: bool) -> None:
        if dry_run:
            return
        for p_hwnd, p_title in self._find_popups(wm):
            logger.info("Recovery: minimizing popup %r (hwnd=%d)",
                        p_title, p_hwnd,
                        extra={"action": "recover", "step": self.name})
            from orchestrator.local_automation.screen_utils import minimize_window
            minimize_window(p_hwnd)
            time.sleep(0.3)

    def _run_verification(
        self, ctx: "StepContext", hwnd: int, ap_name: str, ad: str,
    ) -> VerificationEvidence:
        if ctx.dry_run:
            return VerificationEvidence(
                method="dry_run", expected=ap_name, actual="(dry-run)",
                match=True, detail="AP verification skipped in dry-run",
            )
        spec = None
        if ctx.product:
            spec = ctx.product.verify_ap_selection(ctx, ap_name)
        if not spec:
            spec = VerificationSpec(
                ocr_region=(0, 0, 1288, 1040),
                expected_text=ap_name,
                title_hint=_AP_VI_HINT,
                ocr_psm=6,
                ocr_scale_factor=1,
                ocr_invert=False,
            )
        return execute_verification(hwnd, spec, artifacts_dir=ad)


def _a(lst: list[str], path: str) -> None:
    if path:
        lst.append(path)
