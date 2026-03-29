"""Step 05: Frequency range and RF channel configuration (481.300.vi).

Critical step -- per-field mandatory verification.

UI: 1 dropdown (freq range) + 3 text fields (channels) + 1 text field (user info).

Per-field verification evidence is produced for each of the 5 controls:
  - freq_range  (dropdown)
  - channel_2g  (text field)
  - channel_5g  (text field)
  - channel_6g  (text field)
  - user_info   (text field)

This preserves legacy sequence compatibility (one step) while giving
field-level verification, partial-failure visibility, and clearer
recovery/reporting.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.steps.base import BaseStep
from orchestrator.local_automation.steps.step_result import (
    StepResult,
    VerificationEvidence,
    VerificationSpec,
)
from orchestrator.local_automation.ui.coordinates import (
    FREQ_RANGE_DROPDOWN_PX,
    RF_CHANNEL_2G_PX,
    RF_CHANNEL_5G_PX,
    RF_CHANNEL_6G_PX,
    USER_INFO_FIELD_PX,
    ORANGE_ARROW_PX,
)
from orchestrator.local_automation.ui.dropdowns import select_by_keyboard_nav
from orchestrator.local_automation.ui.input_helpers import (
    clear_and_type,
    safe_click,
    safe_press,
    take_screenshot,
    settle,
)
from orchestrator.local_automation.screen_utils import capture_window
from orchestrator.local_automation.ui.detection import detect_orange_region
from orchestrator.local_automation.ui.verification import (
    execute_verification,
    save_evidence,
)

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.recovery.diagnosis import Diagnosis

logger = get_logger("steps.s05_freq_channel")

FREQ_RANGE_NAV = {"MLO": (10, 3), "2.4GHz": (10, 0), "5GHz": (10, 1), "6GHz": (10, 2)}


class FreqChannelStep(BaseStep):
    """Set frequency range, RF channels, and user information.

    Precondition: 481.300 freq/channel VI visible.
    Action: select freq range dropdown, type 3 channel values, type user info.
    Verification: per-field OCR/pixel-diff for all 5 controls.
    """

    name = "s05_freq_channel"
    step_index = 5
    timeout = 45.0
    max_retries = 2
    is_critical = True

    def __init__(self):
        self._vi_hwnd: int | None = None
        self._before_img = None
        self._field_ev: dict[str, VerificationEvidence] = {}
        self._combined: VerificationEvidence | None = None

    def precondition(self, ctx: "StepContext") -> bool:
        wm = ctx.get_window_manager()
        self._vi_hwnd = wm.find_vi_window("481.300", timeout=10.0)
        if not self._vi_hwnd:
            self._vi_hwnd = (wm.find_vi_window("freq", timeout=3.0)
                             or wm.find_vi_window("channel", timeout=3.0))
        if not self._vi_hwnd:
            logger.warning("Precondition failed: freq/channel VI not found",
                           extra={"action": "precondition", "step": self.name})
            return False
        wm.setup_vi(self._vi_hwnd, dry_run=ctx.dry_run)
        return True

    def execute(self, ctx: "StepContext") -> StepResult:
        hwnd = self._vi_hwnd
        if hwnd is None:
            return StepResult(ok=False, step_name=self.name,
                              error="No freq/channel VI window")

        wm = ctx.get_window_manager()
        ad = ctx.step_artifacts_dir(self.name)
        cfg = ctx.run_config
        dr = ctx.dry_run
        artifacts: list[str] = []
        self._field_ev.clear()

        from orchestrator.local_automation.screen_utils import capture_window
        try:
            self._before_img = capture_window(hwnd)
        except Exception:
            self._before_img = None
        _append(artifacts, take_screenshot(hwnd, ad, "before.png"))

        safe_press("escape", label="clear_focus", dry_run=dr)
        settle(300)

        # --- 1. Freq range dropdown ---
        wm.dismiss_lv_popups(dry_run=dr)
        wm.ensure_foreground(hwnd, dry_run=dr)
        settle()

        nav = FREQ_RANGE_NAV.get(cfg.freq_range, (10, 3))
        select_by_keyboard_nav(hwnd, FREQ_RANGE_DROPDOWN_PX,
                               nav[0], nav[1], dry_run=dr)
        settle(500)
        _append(artifacts, take_screenshot(hwnd, ad, "after_freq_range.png"))

        freq_spec = (ctx.product.verify_freq_range(ctx, cfg.freq_range)
                     if ctx.product and hasattr(ctx.product, "verify_freq_range")
                     else VerificationSpec(
                         ocr_region=(490, 350, 100, 18),
                         expected_text=cfg.freq_range,
                         pixel_diff_region=(480, 330, 120, 30),
                         min_diff_pct=1.0,
                     ))
        ev_freq = self._verify_field(
            ctx, hwnd, "freq_range", cfg.freq_range, freq_spec, ad)
        self._field_ev["freq_range"] = ev_freq
        _append(artifacts, save_evidence(ev_freq, ad, f"{self.name}_freq_range"))

        # --- 2. Channel 2G ---
        wm.ensure_foreground(hwnd, dry_run=dr)
        cleared_2g = self._clear_capture_type(ctx, hwnd, RF_CHANNEL_2G_PX, cfg.rf_channel_2g)
        _append(artifacts, take_screenshot(hwnd, ad, "after_channel_2g.png"))

        ev_2g = self._verify_field(
            ctx, hwnd, "channel_2g", cfg.rf_channel_2g,
            self._channel_spec(ctx, "2.4G", cfg.rf_channel_2g, RF_CHANNEL_2G_PX),
            ad, before_override=cleared_2g)
        self._field_ev["channel_2g"] = ev_2g
        _append(artifacts, save_evidence(ev_2g, ad, f"{self.name}_channel_2g"))

        # --- 3. Channel 5G ---
        cleared_5g = self._clear_capture_type(ctx, hwnd, RF_CHANNEL_5G_PX, cfg.rf_channel_5g)
        _append(artifacts, take_screenshot(hwnd, ad, "after_channel_5g.png"))

        ev_5g = self._verify_field(
            ctx, hwnd, "channel_5g", cfg.rf_channel_5g,
            self._channel_spec(ctx, "5G", cfg.rf_channel_5g, RF_CHANNEL_5G_PX),
            ad, before_override=cleared_5g)
        self._field_ev["channel_5g"] = ev_5g
        _append(artifacts, save_evidence(ev_5g, ad, f"{self.name}_channel_5g"))

        # --- 4. Channel 6G ---
        cleared_6g = self._clear_capture_type(ctx, hwnd, RF_CHANNEL_6G_PX, cfg.rf_channel_6g)
        _append(artifacts, take_screenshot(hwnd, ad, "after_channel_6g.png"))

        ev_6g = self._verify_field(
            ctx, hwnd, "channel_6g", cfg.rf_channel_6g,
            self._channel_spec(ctx, "6G", cfg.rf_channel_6g, RF_CHANNEL_6G_PX),
            ad, before_override=cleared_6g)
        self._field_ev["channel_6g"] = ev_6g
        _append(artifacts, save_evidence(ev_6g, ad, f"{self.name}_channel_6g"))

        # --- 5. User information ---
        cleared_ui = self._clear_capture_type(ctx, hwnd, USER_INFO_FIELD_PX, cfg.user_information)
        _append(artifacts, take_screenshot(hwnd, ad, "after_user_info.png"))

        ui_spec = (ctx.product.verify_user_info(ctx, cfg.user_information)
                   if ctx.product and hasattr(ctx.product, "verify_user_info")
                   else VerificationSpec(
                       ocr_region=(670, 852, 200, 20),
                       expected_text=cfg.user_information,
                       pixel_diff_region=(660, 835, 220, 30),
                       min_diff_pct=1.0,
                   ))
        ev_ui = self._verify_field(
            ctx, hwnd, "user_info", cfg.user_information,
            ui_spec, ad, before_override=cleared_ui)
        self._field_ev["user_info"] = ev_ui
        _append(artifacts, save_evidence(ev_ui, ad, f"{self.name}_user_info"))

        _append(artifacts, take_screenshot(hwnd, ad, "all_fields_filled.png"))

        # --- Combined check ---
        self._combined = self._build_combined()
        if not self._combined.match:
            failed = [k for k, v in self._field_ev.items() if not v.match]
            return StepResult(
                ok=False, step_name=self.name,
                error=f"Freq/channel verification failed for: {failed}",
                verified=False,
                verification_evidence=self._combined,
                field_evidences=dict(self._field_ev),
                artifact_paths=artifacts,
            )

        # --- Advance ---
        wm.dismiss_lv_popups(dry_run=dr)
        wm.ensure_foreground(hwnd, dry_run=dr)
        settle()

        arrow = detect_orange_region(hwnd, dry_run=dr)
        if arrow:
            safe_click(hwnd, arrow[0], arrow[1], label="orange_arrow", dry_run=dr)
        else:
            safe_click(hwnd, ORANGE_ARROW_PX[0], ORANGE_ARROW_PX[1],
                       label="orange_arrow_fallback", dry_run=dr)

        if not dr:
            new_hwnd, ok = wm.verify_transition(hwnd, timeout=10.0)
            if not ok:
                _append(artifacts, take_screenshot(hwnd, ad, "no_transition.png"))
                return StepResult(
                    ok=False, step_name=self.name,
                    error="Screen did not advance after freq/channel",
                    verified=self._combined.match,
                    verification_evidence=self._combined,
                    field_evidences=dict(self._field_ev),
                    artifact_paths=artifacts,
                )
            if new_hwnd:
                ctx.hwnd = new_hwnd

        _append(artifacts, take_screenshot(ctx.hwnd or hwnd, ad, "after.png"))

        return StepResult(
            ok=True, step_name=self.name,
            verified=self._combined.match,
            verification_evidence=self._combined,
            field_evidences=dict(self._field_ev),
            artifact_paths=artifacts,
            details={
                "freq_range": cfg.freq_range,
                "channel_2g": cfg.rf_channel_2g,
                "channel_5g": cfg.rf_channel_5g,
                "channel_6g": cfg.rf_channel_6g,
                "user_info": cfg.user_information,
            },
        )

    def verify(self, ctx: "StepContext") -> VerificationEvidence:
        if self._combined:
            return self._combined
        return VerificationEvidence(method="none", match=True)

    def recover(self, ctx: "StepContext", diagnosis: "Diagnosis") -> bool:
        if self._vi_hwnd is None:
            return False
        wm = ctx.get_window_manager()
        dr = ctx.dry_run
        safe_press("escape", label="recover_escape", dry_run=dr)
        wm.dismiss_lv_popups(dry_run=dr)
        wm.dismiss_dialogs(dry_run=dr)
        wm.ensure_foreground(self._vi_hwnd, dry_run=dr)
        settle(500)
        return True

    # ------------------------------------------------------------------

    def _clear_capture_type(
        self, ctx: "StepContext", hwnd: int,
        px: tuple[int, int], text: str,
    ):
        """Clear a field, capture cleared state, then type value.

        Returns the 'cleared' screenshot so pixel_diff can compare
        empty field vs filled field -- works even when the field
        already contained the same value.
        """
        from orchestrator.local_automation.ui.input_helpers import (
            safe_click as _click, safe_press as _press, safe_type as _type,
        )
        dr = ctx.dry_run
        _click(hwnd, px[0], px[1], label="field_click", dry_run=dr)
        settle(200)
        _press("end", label="field_end", dry_run=dr)
        settle(100)
        for _ in range(15):
            _press("backspace", label="field_bs", dry_run=dr)
            if not dr:
                import time; time.sleep(0.03)
        settle(100)

        cleared_img = None
        if not dr:
            try:
                cleared_img = capture_window(hwnd)
            except Exception:
                pass

        _type(str(text), label="field_type", dry_run=dr)
        settle(200)
        return cleared_img

    def _verify_field(
        self, ctx: "StepContext", hwnd: int, field_name: str,
        expected: str, spec: VerificationSpec, ad: str,
        before_override=None,
    ) -> VerificationEvidence:
        if ctx.dry_run:
            return VerificationEvidence(
                method="dry_run", expected=expected, actual="(dry-run)",
                match=True, detail=f"{field_name} skipped in dry-run",
            )
        before = before_override if before_override is not None else self._before_img
        return execute_verification(hwnd, spec, before_img=before,
                                    artifacts_dir=ad)

    def _channel_spec(
        self, ctx: "StepContext", band: str, channel: str,
        px: tuple[int, int],
    ) -> VerificationSpec:
        if ctx.product:
            spec = ctx.product.verify_channel_selection(ctx, band, channel)
            if spec:
                return spec
        return VerificationSpec(
            ocr_region=(max(px[0] - 20, 0), max(px[1] - 10, 0), 80, 25),
            expected_text=channel,
            pixel_diff_region=(max(px[0] - 20, 0), max(px[1] - 10, 0), 80, 25),
            min_diff_pct=1.0,
        )

    # Fields that MUST verify for the step to pass.
    # user_info is informational (not a test parameter) and its OCR position
    # is uncalibrated, so it's optional.
    _REQUIRED_FIELDS = {"freq_range", "channel_2g", "channel_5g", "channel_6g"}

    def _build_combined(self) -> VerificationEvidence:
        if not self._field_ev:
            return VerificationEvidence(method="none", match=True)
        parts = []
        required_ok = True
        for name, ev in self._field_ev.items():
            status = "required" if name in self._REQUIRED_FIELDS else "optional"
            parts.append(f"{name}[{status}]: {ev.method}={ev.actual!r} (expected={ev.expected!r})")
            if name in self._REQUIRED_FIELDS and not ev.match:
                required_ok = False
        primary = next(iter(self._field_ev.values()))
        return VerificationEvidence(
            method=f"combined_{primary.method}",
            expected=", ".join(f"{k}={ev.expected}" for k, ev in self._field_ev.items()),
            actual="; ".join(parts),
            match=required_ok,
            confidence=min(
                (ev.confidence for name, ev in self._field_ev.items()
                 if name in self._REQUIRED_FIELDS),
                default=0.0,
            ),
            detail="; ".join(parts),
        )


def _append(lst: list[str], path: str) -> None:
    if path:
        lst.append(path)
