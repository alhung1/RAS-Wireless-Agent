"""Step 15: Attenuation parameters (481.300 atten.vi).

Critical step -- mandatory per-field verification before advancing.

UI: 3 numeric text fields:
  - start_atten at START_ATTEN_FIELD_PX
  - step_size   at STEP_SIZE_FIELD_PX
  - steps       at STEPS_FIELD_PX

Verification: OCR each field value after typing; pixel-diff fallback.
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
    START_ATTEN_FIELD_PX,
    STEP_SIZE_FIELD_PX,
    STEPS_FIELD_PX,
    ORANGE_ARROW_PX,
)
from orchestrator.local_automation.ui.input_helpers import (
    type_in_field,
    take_screenshot,
    safe_click,
    safe_press,
    safe_type,
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

logger = get_logger("steps.s15_attenuation")

_FIELD_MAP: list[tuple[str, str, tuple[int, int]]] = [
    ("start_atten", "start_atten", START_ATTEN_FIELD_PX),
    ("step_size",   "step_size",   STEP_SIZE_FIELD_PX),
    ("steps",       "steps",       STEPS_FIELD_PX),
]


class AttenuationStep(BaseStep):
    """Set attenuation sweep parameters in 3 numeric fields.

    Precondition: attenuation VI visible (title contains "atten").
    Action: type values into all 3 fields.
    Verification: per-field OCR, pixel-diff fallback.
    """

    name = "s15_attenuation"
    step_index = 15
    timeout = 30.0
    max_retries = 2
    is_critical = True

    def __init__(self):
        self._vi_hwnd: int | None = None
        self._before_img = None
        self._field_ev: dict[str, VerificationEvidence] = {}
        self._combined: VerificationEvidence | None = None

    def precondition(self, ctx: "StepContext") -> bool:
        wm = ctx.get_window_manager()
        self._vi_hwnd = wm.find_vi_window("atten", timeout=10.0)
        if not self._vi_hwnd:
            logger.warning("Precondition failed: Attenuation VI not found",
                           extra={"action": "precondition", "step": self.name})
            return False
        wm.setup_vi(self._vi_hwnd, dry_run=ctx.dry_run)
        return True

    def execute(self, ctx: "StepContext") -> StepResult:
        hwnd = self._vi_hwnd
        if hwnd is None:
            return StepResult(ok=False, step_name=self.name,
                              error="No attenuation VI window")

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

        field_values = {
            "start_atten": cfg.start_atten,
            "step_size": cfg.step_size,
            "steps": cfg.steps,
        }

        for field_name, config_attr, px in _FIELD_MAP:
            value = field_values[config_attr]
            logger.info("Typing %s=%s at (%d,%d)", field_name, value, px[0], px[1],
                        extra={"action": "execute", "step": self.name})

            wm.ensure_foreground(hwnd, dry_run=dr)

            cleared_img = self._clear_capture_type(ctx, hwnd, px, value)

            _append(artifacts, take_screenshot(hwnd, ad, f"after_{field_name}.png"))

            ev = self._verify_field(ctx, hwnd, field_name, value, px, ad,
                                    before_override=cleared_img)
            self._field_ev[field_name] = ev
            _append(artifacts, save_evidence(ev, ad, f"{self.name}_{field_name}"))

        _append(artifacts, take_screenshot(hwnd, ad, "all_fields_filled.png"))

        self._combined = self._build_combined()
        if not self._combined.match:
            failed = [k for k, v in self._field_ev.items() if not v.match]
            return StepResult(
                ok=False, step_name=self.name,
                error=f"Attenuation verification failed for: {failed}",
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
            new_hwnd, ok = wm.verify_transition(
                hwnd, expected_hint="Chariot", timeout=10.0)
            if not ok:
                _append(artifacts, take_screenshot(hwnd, ad, "no_transition.png"))
                return StepResult(
                    ok=False, step_name=self.name,
                    error="Screen did not advance after attenuation",
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
            details={k: field_values[k] for k in field_values},
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
        """Clear field, capture cleared state, type value.

        Returns the cleared-field screenshot for pixel_diff verification.
        """
        dr = ctx.dry_run
        safe_click(hwnd, px[0], px[1], label="field_click", dry_run=dr)
        settle(200)
        safe_press("end", label="field_end", dry_run=dr)
        settle(100)
        for _ in range(15):
            safe_press("backspace", label="field_bs", dry_run=dr)
            if not dr:
                import time; time.sleep(0.03)
        settle(100)

        cleared_img = None
        if not dr:
            try:
                cleared_img = capture_window(hwnd)
            except Exception:
                pass

        safe_type(str(text), label="field_type", dry_run=dr)
        settle(200)
        return cleared_img

    def _verify_field(
        self, ctx: "StepContext", hwnd: int, field_name: str,
        expected: str, px: tuple[int, int], ad: str,
        before_override=None,
    ) -> VerificationEvidence:
        if ctx.dry_run:
            return VerificationEvidence(
                method="dry_run", expected=expected, actual="(dry-run)",
                match=True, detail=f"{field_name} skipped in dry-run",
            )
        spec = self._field_spec(ctx, field_name, expected, px)
        before = before_override if before_override is not None else self._before_img
        return execute_verification(hwnd, spec, before_img=before,
                                    artifacts_dir=ad)

    def _field_spec(
        self, ctx: "StepContext", field_name: str,
        expected: str, px: tuple[int, int],
    ) -> VerificationSpec:
        if ctx.product:
            spec = ctx.product.verify_attenuation(ctx, field_name, expected)
            if spec:
                return spec
        return VerificationSpec(
            ocr_region=(max(px[0] - 20, 0), max(px[1] - 10, 0), 100, 30),
            expected_text=expected,
            pixel_diff_region=(max(px[0] - 20, 0), max(px[1] - 10, 0), 100, 30),
            min_diff_pct=1.0,
        )

    def _build_combined(self) -> VerificationEvidence:
        if not self._field_ev:
            return VerificationEvidence(method="none", match=True)
        parts = []
        all_ok = True
        for name, ev in self._field_ev.items():
            parts.append(f"{name}: {ev.method}={ev.actual!r} (expected={ev.expected!r})")
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
