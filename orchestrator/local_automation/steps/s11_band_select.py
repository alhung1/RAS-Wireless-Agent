"""Step 11: Band / IP address selection (400 600 IP address Dual LAN.vi).

Critical step -- mandatory verification before advancing.

UI: click "1" button, set 2G dropdown to ip_dropdown_2g value,
set 5G dropdown to ip_dropdown_5g6g value, then advance.

Verification: per-field OCR of both dropdown display areas;
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
    IP_BUTTON_1_PX,
    IP_2G_DROPDOWN_PX,
    IP_2G_ITEM_3_PX,
    IP_5G_DROPDOWN_PX,
    IP_5G_ITEM_3_PX,
    NEUTRAL_CLICK_PX,
    ORANGE_ARROW_PX,
)
from orchestrator.local_automation.ui.dropdowns import close_dropdown
from orchestrator.local_automation.ui.input_helpers import (
    safe_click,
    take_screenshot,
    settle,
)
from orchestrator.local_automation.ui.detection import detect_orange_region
from orchestrator.local_automation.ui.verification import (
    execute_verification,
    save_evidence,
)

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.recovery.diagnosis import Diagnosis

logger = get_logger("steps.s11_band_select")


class BandSelectStep(BaseStep):
    """IP address Dual LAN screen: click [1], set 2G/5G dropdowns.

    Precondition: "IP address" VI window visible.
    Action: click laptop-1 button, open/select both dropdowns.
    Verification: per-field OCR of each dropdown, pixel-diff fallback.
    """

    name = "s11_band_select"
    step_index = 11
    timeout = 40.0
    max_retries = 2
    is_critical = True

    def __init__(self):
        self._vi_hwnd: int | None = None
        self._before_img = None
        self._field_ev: dict[str, VerificationEvidence] = {}
        self._combined: VerificationEvidence | None = None

    def precondition(self, ctx: "StepContext") -> bool:
        wm = ctx.get_window_manager()
        self._vi_hwnd = wm.find_vi_window("IP address", timeout=10.0)
        if not self._vi_hwnd:
            self._vi_hwnd = wm.find_vi_window("Dual LAN", timeout=3.0)
        if not self._vi_hwnd:
            logger.warning("Precondition failed: IP address VI not found",
                           extra={"action": "precondition", "step": self.name})
            return False
        wm.setup_vi(self._vi_hwnd, dry_run=ctx.dry_run)
        return True

    def execute(self, ctx: "StepContext") -> StepResult:
        hwnd = self._vi_hwnd
        if hwnd is None:
            return StepResult(ok=False, step_name=self.name,
                              error="No IP address VI window")

        wm = ctx.get_window_manager()
        ad = ctx.step_artifacts_dir(self.name)
        cfg = ctx.run_config
        dr = ctx.dry_run
        artifacts: list[str] = []
        self._field_ev.clear()

        # --- Screenshot before ---
        from orchestrator.local_automation.screen_utils import capture_window
        try:
            self._before_img = capture_window(hwnd)
        except Exception:
            self._before_img = None
        _append(artifacts, take_screenshot(hwnd, ad, "before.png"))

        # --- Click "1" button ---
        wm.dismiss_lv_popups(dry_run=dr)
        wm.ensure_foreground(hwnd, dry_run=dr)
        safe_click(hwnd, IP_BUTTON_1_PX[0], IP_BUTTON_1_PX[1],
                   label="ip_button_1", dry_run=dr)
        if not dr:
            time.sleep(2.0)
        _append(artifacts, take_screenshot(hwnd, ad, "after_click_1.png"))

        # --- 2G dropdown ---
        wm.ensure_foreground(hwnd, dry_run=dr)
        safe_click(hwnd, IP_2G_DROPDOWN_PX[0], IP_2G_DROPDOWN_PX[1],
                   label="2g_dropdown_open", dry_run=dr)
        if not dr:
            time.sleep(1.0)
        _append(artifacts, take_screenshot(hwnd, ad, "2g_dropdown_open.png"))

        safe_click(hwnd, IP_2G_ITEM_3_PX[0], IP_2G_ITEM_3_PX[1],
                   label="2g_item_select", dry_run=dr)
        settle(500)
        _append(artifacts, take_screenshot(hwnd, ad, "after_2g_select.png"))

        ev_2g = self._verify_field(ctx, hwnd, "ip_dropdown_2g",
                                   cfg.ip_dropdown_2g, IP_2G_DROPDOWN_PX, ad)
        self._field_ev["ip_dropdown_2g"] = ev_2g
        _append(artifacts, save_evidence(ev_2g, ad, f"{self.name}_2g"))

        # --- 5G dropdown ---
        wm.ensure_foreground(hwnd, dry_run=dr)
        safe_click(hwnd, IP_5G_DROPDOWN_PX[0], IP_5G_DROPDOWN_PX[1],
                   label="5g_dropdown_open", dry_run=dr)
        if not dr:
            time.sleep(1.0)
        _append(artifacts, take_screenshot(hwnd, ad, "5g_dropdown_open.png"))

        safe_click(hwnd, IP_5G_ITEM_3_PX[0], IP_5G_ITEM_3_PX[1],
                   label="5g_item_select", dry_run=dr)
        settle(500)
        _append(artifacts, take_screenshot(hwnd, ad, "after_5g_select.png"))

        ev_5g = self._verify_field(ctx, hwnd, "ip_dropdown_5g6g",
                                   cfg.ip_dropdown_5g6g, IP_5G_DROPDOWN_PX, ad)
        self._field_ev["ip_dropdown_5g6g"] = ev_5g
        _append(artifacts, save_evidence(ev_5g, ad, f"{self.name}_5g"))

        # --- Combined check ---
        self._combined = self._build_combined()
        if not self._combined.match:
            return StepResult(
                ok=False, step_name=self.name,
                error=f"Band verification failed: {self._combined.detail}",
                verified=False,
                verification_evidence=self._combined,
                field_evidences=dict(self._field_ev),
                artifact_paths=artifacts,
            )

        # --- Close dropdown modal + advance ---
        close_dropdown(hwnd, NEUTRAL_CLICK_PX, dry_run=dr)
        wm.dismiss_lv_popups(dry_run=dr)
        wm.ensure_foreground(hwnd, dry_run=dr)
        settle()

        arrow = detect_orange_region(hwnd, dry_run=dr)
        if arrow:
            safe_click(hwnd, arrow[0], arrow[1], label="orange_arrow", dry_run=dr)
        else:
            safe_click(hwnd, ORANGE_ARROW_PX[0], ORANGE_ARROW_PX[1],
                       label="orange_arrow_fallback", dry_run=dr)

        # --- Verify transition ---
        if not dr:
            new_hwnd, ok = wm.verify_transition(hwnd, timeout=10.0)
            if not ok:
                _append(artifacts, take_screenshot(hwnd, ad, "no_transition.png"))
                return StepResult(
                    ok=False, step_name=self.name,
                    error="Screen did not advance after band_select",
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
            details={"ip_dropdown_2g": cfg.ip_dropdown_2g,
                     "ip_dropdown_5g6g": cfg.ip_dropdown_5g6g},
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
        close_dropdown(self._vi_hwnd, NEUTRAL_CLICK_PX, dry_run=dr)
        wm.dismiss_lv_popups(dry_run=dr)
        wm.dismiss_dialogs(dry_run=dr)
        wm.ensure_foreground(self._vi_hwnd, dry_run=dr)
        settle(500)
        return True

    # ------------------------------------------------------------------

    def _verify_field(
        self, ctx: "StepContext", hwnd: int, field_name: str,
        expected: str, dropdown_px: tuple[int, int], ad: str,
    ) -> VerificationEvidence:
        if ctx.dry_run:
            return VerificationEvidence(
                method="dry_run", expected=expected, actual="(dry-run)",
                match=True, detail=f"{field_name} skipped in dry-run",
            )
        spec = self._field_spec(ctx, field_name, expected, dropdown_px)
        return execute_verification(hwnd, spec, before_img=self._before_img,
                                    artifacts_dir=ad)

    def _field_spec(
        self, ctx: "StepContext", field_name: str,
        expected: str, dropdown_px: tuple[int, int],
    ) -> VerificationSpec:
        if ctx.product:
            dd_id = "2g" if "2g" in field_name else "5g"
            spec = ctx.product.verify_band_selection(
                ctx, ctx.run_config.band, dropdown_id=dd_id)
            if spec:
                return spec
        ocr_x = max(dropdown_px[0] - 30, 0)
        ocr_y = max(dropdown_px[1] - 10, 0)
        return VerificationSpec(
            ocr_region=(ocr_x, ocr_y, 80, 30),
            expected_text=expected,
            pixel_diff_region=(ocr_x, ocr_y, 80, 30),
            min_diff_pct=1.0,
        )

    def _build_combined(self) -> VerificationEvidence:
        if not self._field_ev:
            return VerificationEvidence(method="none", match=True)
        parts = []
        all_ok = True
        for name, ev in self._field_ev.items():
            parts.append(f"{name}: {ev.method}={ev.actual!r} "
                         f"(expected={ev.expected!r}, match={ev.match})")
            if not ev.match:
                all_ok = False
        primary = next(iter(self._field_ev.values()))
        return VerificationEvidence(
            method=f"combined_{primary.method}",
            expected=", ".join(f"{k}={ev.expected}" for k, ev in self._field_ev.items()),
            actual="; ".join(parts),
            match=all_ok,
            confidence=min(ev.confidence for ev in self._field_ev.values()),
            detail="; ".join(parts),
        )


def _append(lst: list[str], path: str) -> None:
    if path:
        lst.append(path)
