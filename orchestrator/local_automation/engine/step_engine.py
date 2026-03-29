"""StepEngine -- execute a sequence of steps with retry, verification,
recovery, and structured reporting.

This is the core orchestration loop.  It replaces the inline for-loop
in the legacy run_labview_flow().
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.engine.context import StepContext
from orchestrator.local_automation.engine.preflight import (
    PreflightResult,
    run_preflight,
)
from orchestrator.local_automation.engine.report import RunReport, save_run_report
from orchestrator.local_automation.recovery.diagnosis import Diagnosis
from orchestrator.local_automation.steps.base import BaseStep
from orchestrator.local_automation.steps.step_result import StepResult

logger = get_logger("step_engine")


class PreflightError(Exception):
    """Raised when preflight validation fails."""

    def __init__(self, result: PreflightResult):
        self.result = result
        super().__init__(result.summary())


class EmergencyStopError(Exception):
    """Raised when the operator creates the stop file."""


class StepEngine:
    """Executes a sequence of BaseStep instances with full lifecycle."""

    def __init__(
        self,
        steps: list[BaseStep],
        ctx: StepContext,
        post_step_hooks: Optional[dict[int, Callable]] = None,
    ):
        self.steps = steps
        self.ctx = ctx
        self.post_step_hooks = post_step_hooks or {}
        self.report = RunReport(
            run_id=ctx.run_id,
            total_steps=len(steps),
            dry_run=ctx.dry_run,
            config=ctx.run_config.to_dict(),
        )
        if ctx.product:
            self.report.product_model = ctx.product.name
        self.report.band = ctx.run_config.band
        self.report.mode = ctx.run_config.mode

    def _check_stop(self) -> None:
        if os.path.isfile(self.ctx.emergency_stop_file):
            raise EmergencyStopError(
                f"Emergency stop: {self.ctx.emergency_stop_file!r} exists"
            )

    def run_preflight(self) -> PreflightResult:
        """Execute preflight checks.  Raises PreflightError on failure."""
        result = run_preflight(self.ctx.run_config, self.ctx.product, self.ctx)
        self.report.preflight = result
        if not result.passed:
            raise PreflightError(result)
        return result

    def execute_step(self, step: BaseStep) -> StepResult:
        """Execute a single step through the full lifecycle:
        precondition -> execute -> verify -> (retry on failure).
        """
        self._check_stop()
        step_ad = self.ctx.step_artifacts_dir(step.name)

        last_result: Optional[StepResult] = None

        for attempt in range(step.max_retries + 1):
            self._check_stop()

            # 1. Precondition
            if not step.precondition(self.ctx):
                logger.warning(
                    "Precondition failed for %s (attempt %d/%d)",
                    step.name, attempt + 1, step.max_retries + 1,
                    extra={"action": "step_engine", "step": step.name},
                )
                if attempt < step.max_retries:
                    time.sleep(1.0)
                    continue
                last_result = StepResult(
                    ok=False, step_name=step.name,
                    attempts=attempt + 1,
                    error="Precondition failed after all retries",
                )
                break

            # 2. Execute
            t0 = time.monotonic()
            try:
                result = step.execute(self.ctx)
            except Exception as exc:
                result = StepResult(
                    ok=False, step_name=step.name,
                    error=str(exc),
                )
            result.elapsed_sec = time.monotonic() - t0
            result.attempts = attempt + 1

            # 3. Verify (critical steps must produce evidence)
            if result.ok:
                evidence = step.verify(self.ctx)
                result.verification_evidence = evidence
                if step.is_critical and not evidence.match:
                    logger.warning(
                        "Verification FAILED for critical step %s: %s",
                        step.name, evidence.detail or evidence.actual,
                        extra={"action": "verify", "step": step.name},
                    )
                    result.ok = False
                    result.verified = False
                    result.error = (
                        f"Verification failed: expected={evidence.expected!r}, "
                        f"actual={evidence.actual!r}, method={evidence.method}"
                    )
                else:
                    result.verified = evidence.match

            last_result = result

            if result.ok:
                break

            # 4. Recovery before retry
            if attempt < step.max_retries:
                logger.info(
                    "Step %s failed (attempt %d/%d), attempting recovery...",
                    step.name, attempt + 1, step.max_retries + 1,
                    extra={"action": "retry", "step": step.name},
                )
                diagnosis = Diagnosis(step_name=step.name, issues=["step_failed"])
                step.recover(self.ctx, diagnosis)
                time.sleep(1.0 * (attempt + 1))

        # Save verification evidence as JSON
        if last_result and last_result.verification_evidence:
            ev_path = os.path.join(step_ad, f"verify_{step.name}.json")
            try:
                with open(ev_path, "w", encoding="utf-8") as f:
                    json.dump(last_result.verification_evidence.to_dict(), f, indent=2)
                last_result.artifact_paths.append(ev_path)
            except Exception:
                pass

        return last_result or StepResult(ok=False, step_name=step.name, error="No result")

    def run(
        self,
        start_from: int = 0,
        profile_name: str = "",
    ) -> RunReport:
        """Execute the full step sequence (or resume from *start_from*).

        Returns the completed RunReport.
        """
        self.report.profile_name = profile_name
        self.report.mark_started()

        try:
            self.run_preflight()
        except PreflightError as exc:
            self.report.mark_finished("fail")
            self.report.errors.append(str(exc))
            save_run_report(self.report, self.ctx.artifacts_dir)
            raise

        for i, step in enumerate(self.steps):
            if i < start_from:
                continue

            self._check_stop()

            logger.info(
                "Step %d/%d: %s (critical=%s)",
                i, len(self.steps) - 1, step.name, step.is_critical,
                extra={"action": "step_engine", "step": step.name},
            )

            result = self.execute_step(step)
            self.report.add_step(result)

            logger.info(
                "Step %d %s: ok=%s verified=%s (%.1fs, %d attempts)",
                i, step.name, result.ok, result.verified,
                result.elapsed_sec, result.attempts,
                extra={"action": "step_result", "step": step.name},
            )

            # Post-step hooks
            if result.ok and i in self.post_step_hooks:
                try:
                    self.post_step_hooks[i](self.ctx.run_config, self.ctx.artifacts_dir)
                except Exception as exc:
                    logger.error(
                        "Post-step hook for step %d failed: %s", i, exc,
                        extra={"action": "post_hook", "step": step.name},
                    )

            if not result.ok:
                self.report.mark_finished("fail")
                break
        else:
            self.report.mark_finished("pass")

        save_run_report(self.report, self.ctx.artifacts_dir)
        return self.report

    def run_single(self, step_index: int) -> StepResult:
        """Execute a single step by index (for debugging)."""
        if step_index < 0 or step_index >= len(self.steps):
            return StepResult(
                ok=False, step_name=f"step_{step_index}",
                error=f"Step index {step_index} out of range (0-{len(self.steps)-1})",
            )
        return self.execute_step(self.steps[step_index])
