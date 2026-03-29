"""Matrix runner -- execute multiple test profiles sequentially.

Loads a set of TestProfile entries, runs preflight + StepEngine for
each, and produces a matrix_summary.json with per-test results.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.engine.context import RunConfig, StepContext
from orchestrator.local_automation.engine.report import RunReport, save_run_report
from orchestrator.local_automation.engine.step_engine import (
    StepEngine,
    PreflightError,
    EmergencyStopError,
)
from orchestrator.local_automation.profiles.loader import (
    load_test_profile,
    load_product_profile,
    get_product_adapter,
    resolve_run_config,
    find_product_profile_path,
)
from orchestrator.local_automation.profiles.schema import TestProfile
from orchestrator.local_automation.steps.registry import build_default_sequence
from orchestrator.local_automation.ui.detection import ocr_available

logger = get_logger("matrix_runner")


@dataclass
class MatrixEntry:
    """Result for one test profile in the matrix."""
    profile_path: str = ""
    profile_name: str = ""
    product: str = ""
    band: str = ""
    mode: str = ""
    status: str = "pending"
    run_id: str = ""
    elapsed_sec: float = 0.0
    steps_completed: int = 0
    total_steps: int = 0
    failed_step: Optional[str] = None
    error: Optional[str] = None
    report_path: str = ""

    def to_dict(self) -> dict:
        d = {
            "profile_path": self.profile_path,
            "profile_name": self.profile_name,
            "product": self.product,
            "band": self.band,
            "mode": self.mode,
            "status": self.status,
            "run_id": self.run_id,
            "elapsed_sec": round(self.elapsed_sec, 1),
            "steps_completed": self.steps_completed,
            "total_steps": self.total_steps,
        }
        if self.failed_step:
            d["failed_step"] = self.failed_step
        if self.error:
            d["error"] = self.error
        if self.report_path:
            d["report_path"] = self.report_path
        return d


@dataclass
class MatrixSummary:
    """Top-level result for a matrix run."""
    started_at: str = ""
    finished_at: str = ""
    total_profiles: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    stop_on_failure: bool = True
    entries: list[MatrixEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_profiles": self.total_profiles,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "stop_on_failure": self.stop_on_failure,
            "entries": [e.to_dict() for e in self.entries],
        }


def run_matrix(
    profile_paths: list[str],
    artifacts_base: str = "artifacts/matrix",
    stop_on_failure: bool = True,
    dry_run: bool = False,
    stop_at_step: int = 18,
    profiles_root: str | None = None,
) -> MatrixSummary:
    """Run multiple test profiles sequentially.

    Each profile gets its own sub-directory under *artifacts_base*,
    its own StepContext, and its own RunReport.

    If *stop_on_failure* is True (default), the matrix stops after
    the first failed profile.  If False, failures are logged and
    the next profile runs.
    """
    summary = MatrixSummary(
        started_at=datetime.now(timezone.utc).isoformat(),
        total_profiles=len(profile_paths),
        stop_on_failure=stop_on_failure,
    )

    for idx, prof_path in enumerate(profile_paths):
        entry = MatrixEntry(profile_path=prof_path)
        t0 = time.monotonic()

        try:
            profile = load_test_profile(prof_path)
        except Exception as exc:
            entry.status = "error"
            entry.error = f"Failed to load profile: {exc}"
            summary.entries.append(entry)
            summary.failed += 1
            if stop_on_failure:
                break
            continue

        entry.profile_name = profile.name
        entry.band = profile.band
        entry.mode = profile.mode
        entry.product = profile.product

        product_adapter = get_product_adapter(profile.product)
        if not product_adapter:
            entry.status = "error"
            entry.error = f"Product adapter not found for {profile.product!r}"
            summary.entries.append(entry)
            summary.failed += 1
            if stop_on_failure:
                break
            continue

        pp_path = find_product_profile_path(profile.product, profiles_root)
        product_profile = None
        if pp_path:
            try:
                product_profile = load_product_profile(pp_path)
            except Exception:
                pass

        run_config = resolve_run_config(profile, product_profile, product_adapter)

        run_ad = os.path.join(
            os.path.abspath(artifacts_base),
            f"{idx:02d}_{profile.band.replace('.', '')}_{profile.mode}",
        )
        ctx = StepContext(
            run_config=run_config,
            product=product_adapter,
            artifacts_dir=run_ad,
            dry_run=dry_run,
            ocr_available=ocr_available(),
        )
        entry.run_id = ctx.run_id

        if not dry_run:
            from orchestrator.local_automation.ui.window_manager import WindowManager
            wm = WindowManager()
            main_hwnd = wm.find_window()
            if not main_hwnd:
                entry.status = "error"
                entry.error = "LabVIEW main window not found"
                summary.entries.append(entry)
                summary.failed += 1
                if stop_on_failure:
                    break
                continue
            ctx.hwnd = main_hwnd
            ctx._window_manager = wm

        steps = build_default_sequence()
        engine = StepEngine(steps, ctx)

        logger.info(
            "Matrix [%d/%d]: %s (band=%s mode=%s product=%s dry_run=%s)",
            idx + 1, len(profile_paths),
            profile.name, profile.band, profile.mode, profile.product, dry_run,
            extra={"action": "matrix", "step": "start"},
        )

        if dry_run:
            from orchestrator.local_automation.engine.preflight import run_preflight
            try:
                pf = run_preflight(run_config, product_adapter, ctx)
                entry.status = "pass (dry-run)" if pf.passed else "preflight_fail"
                entry.total_steps = len(steps)
                if not pf.passed:
                    entry.error = pf.summary()
            except Exception as exc:
                entry.status = "error"
                entry.error = str(exc)
        else:
            try:
                report = engine.run(
                    profile_name=profile.name,
                    start_from=0,
                )
                entry.status = report.overall_status
                entry.steps_completed = report.completed_steps
                entry.total_steps = report.total_steps
                entry.failed_step = report.failed_step
                if report.errors:
                    entry.error = "; ".join(report.errors)
                entry.report_path = os.path.join(run_ad, "run.json")

            except PreflightError as exc:
                entry.status = "preflight_fail"
                entry.error = str(exc)

            except EmergencyStopError:
                entry.status = "emergency_stop"
                entry.error = "Emergency stop triggered"

            except Exception as exc:
                entry.status = "error"
                entry.error = str(exc)

        entry.elapsed_sec = time.monotonic() - t0
        summary.entries.append(entry)

        if entry.status.startswith("pass"):
            summary.passed += 1
        else:
            summary.failed += 1

        logger.info(
            "Matrix [%d/%d]: %s -> %s (%.1fs)",
            idx + 1, len(profile_paths),
            profile.name, entry.status, entry.elapsed_sec,
            extra={"action": "matrix", "step": "done"},
        )

        if not entry.status.startswith("pass") and stop_on_failure:
            summary.skipped = len(profile_paths) - idx - 1
            break

    summary.finished_at = datetime.now(timezone.utc).isoformat()

    summary_path = os.path.join(os.path.abspath(artifacts_base), "matrix_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
    logger.info("Matrix summary: %s", summary_path,
                extra={"action": "matrix", "step": "summary"})

    return summary
