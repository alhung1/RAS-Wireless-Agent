"""Step 14: Mode selection (BW20/BW40/.../BW320).

Critical step -- mandatory verification before advancing.

UI: dropdown at MODE_DROPDOWN_PX on the 400 600 MODE.vi screen.
Verification: OCR the dropdown display area for the mode name;
pixel-diff fallback if OCR unavailable.
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
    MODE_DROPDOWN_PX,
    NEUTRAL_CLICK_PX,
)
from orchestrator.local_automation.ui.dropdowns import (
    BW_MODE_NAV,
    select_by_keyboard_nav,
    close_dropdown,
)
from orchestrator.local_automation.ui.input_helpers import (
    safe_click,
    safe_press,
    take_screenshot,
    settle,
)
from orchestrator.local_automation.ui.detection import detect_orange_region
from orchestrator.local_automation.ui.verification import (
    execute_verification,
    save_evidence,
    poll_until,
)

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.recovery.diagnosis import Diagnosis

logger = get_logger("steps.s14_mode")


class ModeStep(BaseStep):
    """Select bandwidth mode via dropdown navigation.

    Precondition: MODE VI window visible.
    Action: navigate dropdown to target mode, verify, advance.
    Verification: OCR dropdown display, pixel-diff fallback.
    """

    name = "s14_mode"
    step_index = 14
    timeout = 30.0
    max_retries = 2
    is_critical = True

    def __init__(self):
        self._vi_hwnd: int | None = None
        self._before_img = None
        self._evidence: VerificationEvidence | None = None

    def precondition(self, ctx: "StepContext") -> bool:
        """MODE VI must be visible."""
        wm = ctx.get_window_manager()
        self._vi_hwnd = wm.find_vi_window("MODE", timeout=10.0)
        if not self._vi_hwnd:
            logger.warning("Precondition failed: MODE VI not found",
                           extra={"action": "precondition", "step": self.name})
            return False
        wm.setup_vi(self._vi_hwnd, dry_run=ctx.dry_run)
        return True

    def execute(self, ctx: "StepContext") -> StepResult:
        hwnd = self._vi_hwnd
        if hwnd is None:
            return StepResult(ok=False, step_name=self.name,
                              error="No MODE VI window (precondition should have caught this)")

        wm = ctx.get_window_manager()
        ad = ctx.step_artifacts_dir(self.name)
        mode = ctx.run_config.mode
        artifacts: list[str] = []

        # --- Screenshot before ---
        from orchestrator.local_automation.screen_utils import capture_window
        try:
            self._before_img = capture_window(hwnd)
        except Exception:
            self._before_img = None
        before_path = take_screenshot(hwnd, ad, "before.png")
        if before_path:
            artifacts.append(before_path)

        # --- Navigate dropdown ---
        nav = BW_MODE_NAV.get(mode, (6, 0))
        up_count, down_count = nav
        logger.info("Setting mode to %s (Up=%d, Down=%d)",
                    mode, up_count, down_count,
                    extra={"action": "execute", "step": self.name})

        wm.dismiss_lv_popups(dry_run=ctx.dry_run)
        wm.ensure_foreground(hwnd, dry_run=ctx.dry_run)
        settle()

        select_by_keyboard_nav(
            hwnd, MODE_DROPDOWN_PX, up_count, down_count,
            dry_run=ctx.dry_run,
            ensure_fg_fn=wm.ensure_foreground,
        )
        settle(500)

        # --- Screenshot after selection ---
        after_sel_path = take_screenshot(hwnd, ad, "after_select.png")
        if after_sel_path:
            artifacts.append(after_sel_path)

        # --- Verify selection (before advancing) ---
        self._evidence = self._run_verification(ctx, hwnd, mode, ad)
        if self._evidence and not self._evidence.match:
            ev_path = save_evidence(self._evidence, ad, self.name)
            artifacts.append(ev_path)
            return StepResult(
                ok=False, step_name=self.name,
                error=f"Mode verification failed: expected={mode!r}, "
                      f"actual={self._evidence.actual!r}, "
                      f"method={self._evidence.method}",
                verified=False,
                verification_evidence=self._evidence,
                artifact_paths=artifacts,
            )

        if self._evidence:
            ev_path = save_evidence(self._evidence, ad, self.name)
            artifacts.append(ev_path)

        # --- Click orange arrow to advance ---
        wm.dismiss_lv_popups(dry_run=ctx.dry_run)
        wm.ensure_foreground(hwnd, dry_run=ctx.dry_run)
        settle()

        arrow = detect_orange_region(hwnd, dry_run=ctx.dry_run)
        if arrow:
            safe_click(hwnd, arrow[0], arrow[1], label="orange_arrow",
                       dry_run=ctx.dry_run, ensure_fg_fn=wm.ensure_foreground)
        else:
            from orchestrator.local_automation.ui.coordinates import ORANGE_ARROW_PX
            safe_click(hwnd, ORANGE_ARROW_PX[0], ORANGE_ARROW_PX[1],
                       label="orange_arrow_fallback", dry_run=ctx.dry_run,
                       ensure_fg_fn=wm.ensure_foreground)

        # --- Verify transition to attenuation screen ---
        if not ctx.dry_run:
            new_hwnd, transitioned = wm.verify_transition(
                hwnd, expected_hint="atten", timeout=10.0)
            if not transitioned:
                fail_path = take_screenshot(hwnd, ad, "no_transition.png")
                if fail_path:
                    artifacts.append(fail_path)
                return StepResult(
                    ok=False, step_name=self.name,
                    error="Screen did not advance to attenuation after mode selection",
                    verified=self._evidence.match if self._evidence else False,
                    verification_evidence=self._evidence,
                    artifact_paths=artifacts,
                )
            if new_hwnd:
                ctx.hwnd = new_hwnd

        # --- Screenshot after transition ---
        target = ctx.hwnd or hwnd
        after_path = take_screenshot(target, ad, "after.png")
        if after_path:
            artifacts.append(after_path)

        return StepResult(
            ok=True, step_name=self.name,
            verified=self._evidence.match if self._evidence else False,
            verification_evidence=self._evidence,
            artifact_paths=artifacts,
            details={"mode": mode, "nav": list(nav)},
        )

    def verify(self, ctx: "StepContext") -> VerificationEvidence:
        """Return the evidence collected during execute()."""
        if self._evidence:
            return self._evidence
        return VerificationEvidence(method="none", match=True,
                                    detail="No evidence collected (dry-run or precondition fail)")

    def verification_spec(self, ctx: "StepContext") -> VerificationSpec | None:
        if ctx.product:
            return ctx.product.verify_mode_selection(ctx, ctx.run_config.mode)
        return VerificationSpec(
            ocr_region=(200, 745, 200, 30),
            expected_text=ctx.run_config.mode,
            pixel_diff_region=(200, 740, 200, 40),
            min_diff_pct=1.0,
        )

    def recover(self, ctx: "StepContext", diagnosis: "Diagnosis") -> bool:
        """Close any stuck dropdown, dismiss popups, refocus."""
        if self._vi_hwnd is None:
            return False
        wm = ctx.get_window_manager()
        close_dropdown(self._vi_hwnd, dry_run=ctx.dry_run)
        wm.dismiss_lv_popups(dry_run=ctx.dry_run)
        wm.dismiss_dialogs(dry_run=ctx.dry_run)
        if self._vi_hwnd:
            wm.ensure_foreground(self._vi_hwnd, dry_run=ctx.dry_run)
        settle(500)
        logger.info("Recovery completed for %s", self.name,
                    extra={"action": "recover", "step": self.name})
        return True

    # ------------------------------------------------------------------

    def _run_verification(
        self,
        ctx: "StepContext",
        hwnd: int,
        mode: str,
        ad: str,
    ) -> VerificationEvidence:
        """Execute verification pipeline for mode selection."""
        if ctx.dry_run:
            return VerificationEvidence(
                method="dry_run", expected=mode, actual="(dry-run)",
                match=True, detail="Verification skipped in dry-run mode",
            )

        spec = self.verification_spec(ctx)
        if spec:
            return execute_verification(
                hwnd, spec,
                before_img=self._before_img,
                artifacts_dir=ad,
            )

        return VerificationEvidence(
            method="none", match=True,
            detail="No verification spec available",
        )
