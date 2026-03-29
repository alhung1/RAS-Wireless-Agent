"""BaseStep -- abstract base class for all automation steps.

Every step (critical or non-critical) subclasses BaseStep and
implements at least execute().  Critical steps must also implement
verify() with concrete VerificationEvidence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext
    from orchestrator.local_automation.recovery.diagnosis import Diagnosis

from orchestrator.local_automation.steps.step_result import (
    StepResult,
    VerificationEvidence,
    VerificationSpec,
)


class BaseStep(ABC):
    """Abstract base for a single automation step.

    Lifecycle (executed by StepEngine):
        1. precondition(ctx) -- is the UI in the correct state?
        2. execute(ctx)      -- perform the action, return StepResult
        3. verify(ctx)       -- confirm the action succeeded (evidence)
        4. recover(ctx, d)   -- on failure, attempt recovery before retry

    Critical steps (is_critical=True) MUST return concrete
    VerificationEvidence from verify().  The engine refuses to
    advance if verify() returns match=False.
    """

    name: str = "unnamed"
    step_index: int = -1
    timeout: float = 30.0
    max_retries: int = 2
    is_critical: bool = False

    def precondition(self, ctx: "StepContext") -> bool:
        """Check that the UI is in the expected state before acting.

        Default implementation returns True (no precondition).
        Override to check window title, template presence, etc.
        """
        return True

    @abstractmethod
    def execute(self, ctx: "StepContext") -> StepResult:
        """Perform the UI action.  Must return a StepResult."""

    def verify(self, ctx: "StepContext") -> VerificationEvidence:
        """Confirm the action succeeded with concrete evidence.

        Critical steps MUST override this.  Non-critical steps can
        rely on the default which returns a "none" evidence (the
        engine accepts this only for non-critical steps).
        """
        return VerificationEvidence(method="none", match=True)

    def verification_spec(self, ctx: "StepContext") -> VerificationSpec | None:
        """Declare how success should be verified for this step.

        Returns None if the step has no declarative verification.
        Override in critical steps to return a concrete spec.
        """
        return None

    def recover(self, ctx: "StepContext", diagnosis: "Diagnosis") -> bool:
        """Attempt recovery after a failure.

        Called by the engine between retries.  Returns True if recovery
        succeeded and the step should be retried, False to give up.

        Default implementation dismisses popups and refocuses.
        """
        return False


class LegacyStepWrapper(BaseStep):
    """Wraps a legacy step_XX function as a BaseStep for the engine.

    Used during the transition (Phases B/C) so that non-refactored
    steps can run through the new StepEngine alongside new-style steps.

    Legacy functions have signature:
        (hwnd: int, cfg: RunConfig, ad: str) -> LegacyStepResult

    The new RunConfig is duck-type compatible (same field names), so
    we pass ctx.run_config directly.  The legacy StepResult is
    converted to the new StepResult format.
    """

    def __init__(
        self,
        name: str,
        step_index: int,
        legacy_fn=None,
        is_critical: bool = False,
    ):
        self.name = name
        self.step_index = step_index
        self.is_critical = is_critical
        self._legacy_fn = legacy_fn

    def execute(self, ctx: "StepContext") -> StepResult:
        if self._legacy_fn is None:
            return StepResult(
                ok=False, step_name=self.name,
                error=f"Legacy function not wired for {self.name}",
            )
        ad = ctx.step_artifacts_dir(self.name)
        legacy_result = self._legacy_fn(ctx.hwnd, ctx.run_config, ad)
        artifacts = []
        if hasattr(legacy_result, "screenshot") and legacy_result.screenshot:
            artifacts.append(legacy_result.screenshot)
        details = {}
        if hasattr(legacy_result, "detail") and isinstance(legacy_result.detail, dict):
            details = legacy_result.detail
        return StepResult(
            ok=legacy_result.success,
            step_name=self.name,
            elapsed_sec=legacy_result.elapsed_sec,
            error=legacy_result.error if hasattr(legacy_result, "error") else "",
            artifact_paths=artifacts,
            details=details,
        )
