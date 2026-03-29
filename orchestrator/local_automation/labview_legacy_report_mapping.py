"""
Explicit mapping: engine run.json / RunReport versus legacy result.json.

Single source of truth for translating EngineRunReport and StepResult rows into
the legacy RunReport shape written as result.json.

ROOT-LEVEL (legacy result.json versus engine run.json):
  success: from engine.overall_status == "pass" (finish detection may override).
  started_at: facade only (UTC %Y%m%d_%H%M%S), not copied from engine.
  finished_at: facade only after run plus optional wait_for_finish.
  steps: from apply_engine_run_to_legacy_report().
  finish_result: facade only (wait_for_finish asdict); engine usually None.
  config: asdict(legacy RunConfig) at start; engine.config is a separate dict.
  error: derive_legacy_error_message() or finish timeout string.

Engine-only root fields not copied to legacy: run_id, profile_name, product_model,
dry_run, total_steps, completed_steps, retry_counts, preflight, artifact_paths.

PER-STEP (legacy step dict versus engine StepResult):
  name: STEP_SEQUENCE[i].__name__.
  success: StepResult.ok.
  elapsed_sec: StepResult.elapsed_sec.
  screenshot: artifact_paths[0] or empty string.
  error: StepResult.error or empty string.
  detail: merges details, verification_evidence, field_evidences, attempts,
          step_name, verified, recovery_actions.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from orchestrator.local_automation.engine.report import RunReport as EngineRunReport
from orchestrator.local_automation.labview_runner_legacy import RunReport as LegacyRunReport
from orchestrator.local_automation.steps.step_result import StepResult as EngineStepResult


def engine_step_to_legacy_step_dict(
    engine_step: EngineStepResult,
    display_name: str,
) -> dict[str, Any]:
    screenshot = ""
    if engine_step.artifact_paths:
        screenshot = engine_step.artifact_paths[0]
    detail: dict[str, Any] = {}
    if engine_step.details:
        detail.update(engine_step.details)
    if engine_step.verification_evidence:
        detail["verification_evidence"] = engine_step.verification_evidence.to_dict()
    if engine_step.field_evidences:
        detail["field_evidences"] = {
            k: v.to_dict() for k, v in engine_step.field_evidences.items()
        }
    detail["attempts"] = engine_step.attempts
    detail["step_name"] = engine_step.step_name
    detail["verified"] = engine_step.verified
    if engine_step.recovery_actions:
        detail["recovery_actions"] = engine_step.recovery_actions
    return {
        "name": display_name,
        "success": engine_step.ok,
        "elapsed_sec": engine_step.elapsed_sec,
        "screenshot": screenshot,
        "error": engine_step.error or "",
        "detail": detail,
    }


def derive_legacy_error_message(engine_report: EngineRunReport) -> str:
    if engine_report.errors:
        return engine_report.errors[-1]
    for s in reversed(engine_report.steps):
        if not s.ok:
            return s.error or f"Step {s.step_name} failed"
    if engine_report.failed_step:
        return f"Step {engine_report.failed_step} failed"
    return "Run failed"


def apply_engine_run_to_legacy_report(
    engine_report: EngineRunReport,
    legacy_report: LegacyRunReport,
    start_from: int,
    step_sequence: Sequence[Callable[..., Any]],
) -> None:
    legacy_report.steps = []
    for j, sr in enumerate(engine_report.steps):
        idx = start_from + j
        if idx < len(step_sequence):
            display_name = step_sequence[idx].__name__
        else:
            display_name = sr.step_name
        legacy_report.steps.append(engine_step_to_legacy_step_dict(sr, display_name))

    if engine_report.overall_status == "pass":
        legacy_report.success = True
        legacy_report.error = ""
    else:
        legacy_report.success = False
        legacy_report.error = derive_legacy_error_message(engine_report)
