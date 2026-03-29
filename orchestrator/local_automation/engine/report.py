"""Run report builder and serializer.

Produces the standardized run.json artifact at the end of every run
(including aborted/failed runs).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from orchestrator.local_automation.steps.step_result import StepResult
from orchestrator.local_automation.engine.preflight import PreflightResult


@dataclass
class RunReport:
    """Complete structured report for a single automation run."""
    run_id: str = ""
    profile_name: str = ""
    product_model: str = ""
    band: str = ""
    channel: str = ""
    mode: str = ""
    started_at: str = ""
    finished_at: str = ""
    dry_run: bool = False
    overall_status: str = "pending"  # "pass", "fail", "aborted", "emergency_stop"
    failed_step: Optional[str] = None
    total_steps: int = 0
    completed_steps: int = 0
    retry_counts: dict[str, int] = field(default_factory=dict)
    steps: list[StepResult] = field(default_factory=list)
    preflight: Optional[PreflightResult] = None
    artifact_paths: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    finish_result: Optional[dict] = None
    errors: list[str] = field(default_factory=list)

    def mark_started(self) -> None:
        self.started_at = datetime.now(timezone.utc).isoformat()

    def mark_finished(self, status: str) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()
        self.overall_status = status
        self.completed_steps = sum(1 for s in self.steps if s.ok)

    def add_step(self, result: StepResult) -> None:
        self.steps.append(result)
        if result.attempts > 1:
            self.retry_counts[result.step_name] = result.attempts
        if not result.ok and self.failed_step is None:
            self.failed_step = result.step_name

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "profile_name": self.profile_name,
            "product_model": self.product_model,
            "band": self.band,
            "channel": self.channel,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "dry_run": self.dry_run,
            "overall_status": self.overall_status,
            "failed_step": self.failed_step,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "retry_counts": self.retry_counts,
            "steps": [s.to_dict() for s in self.steps],
            "preflight": self.preflight.to_dict() if self.preflight else None,
            "artifact_paths": self.artifact_paths,
            "config": self.config,
            "finish_result": self.finish_result,
            "errors": self.errors,
        }


def save_run_report(report: RunReport, artifacts_dir: str) -> str:
    """Write run.json to the artifacts directory.  Returns the file path."""
    os.makedirs(artifacts_dir, exist_ok=True)
    path = os.path.join(artifacts_dir, "run.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    return path
