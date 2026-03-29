"""Native attach step (index 0) — minimal migration from legacy step_00_attach."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from orchestrator.local_automation.steps.base import BaseStep
from orchestrator.local_automation.steps.step_result import StepResult

if TYPE_CHECKING:
    from orchestrator.local_automation.engine.context import StepContext


class AttachStep(BaseStep):
    """Attach to the LabVIEW main window and capture a baseline screenshot.

    Mirrors ``labview_runner_legacy.step_00_attach`` behavior; kept native to
    validate the migration pattern for low-complexity steps.
    """

    name = "s00_attach"
    step_index = 0
    is_critical = False

    def execute(self, ctx: "StepContext") -> StepResult:
        from orchestrator.local_automation import labview_runner_legacy as lr

        t0 = time.monotonic()
        ad = ctx.step_artifacts_dir(self.name)
        if ctx.hwnd is None:
            return StepResult(
                ok=False,
                step_name=self.name,
                error="No LabVIEW window found",
            )
        ss = lr._screenshot(ctx.hwnd, ad, 0, "attach")
        paths = [ss] if ss else []
        return StepResult(
            ok=True,
            step_name=self.name,
            elapsed_sec=time.monotonic() - t0,
            artifact_paths=paths,
        )
