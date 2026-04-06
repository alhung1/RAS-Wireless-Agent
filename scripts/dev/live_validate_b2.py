"""Live validation for Phase B native critical steps.

Runs the full 19-step sequence using the mixed registry (legacy + native).
Stops on first failure, captures all artifacts and evidence.

Usage: python scripts/dev/live_validate_b2.py
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from orchestrator.local_automation.engine.context import RunConfig, StepContext
from orchestrator.local_automation.engine.preflight import run_preflight
from orchestrator.local_automation.engine.report import RunReport, save_run_report
from orchestrator.local_automation.products.be200 import BE200Adapter
from orchestrator.local_automation.steps.registry import build_default_sequence
from orchestrator.local_automation.ui.window_manager import WindowManager
from orchestrator.local_automation.ui.detection import ocr_available

ARTIFACTS_DIR = "artifacts/live_validation"
START_AT_STEP = int(os.environ.get("LV_START", "0"))
STOP_AT_STEP = int(os.environ.get("LV_STOP", "15"))


def main():
    wm = WindowManager()
    main_hwnd = wm.find_window()
    if not main_hwnd:
        print("ABORT: LabVIEW main window not found")
        return 1

    print(f"LabVIEW hwnd={main_hwnd} title={wm.get_title(main_hwnd)!r}")
    print(f"PID={wm.lv_pid}")

    product = BE200Adapter()
    cfg = RunConfig(
        band="2.4G", mode="BW20", freq_range="MLO",
        rf_channel_2g="10", rf_channel_5g="44", rf_channel_6g="69",
        user_information="2G test", ip_dropdown_2g="3", ip_dropdown_5g6g="3",
        start_atten="0", step_size="3", steps="30",
    )
    ctx = StepContext(
        hwnd=main_hwnd, run_config=cfg, product=product,
        artifacts_dir=os.path.abspath(ARTIFACTS_DIR),
        dry_run=False, ocr_available=ocr_available(),
    )
    ctx._window_manager = wm

    pf = run_preflight(cfg, product, ctx)
    print(f"\nPreflight: {'PASS' if pf.passed else 'FAIL'}")
    if not pf.passed:
        print(pf.summary())
        return 1

    steps = build_default_sequence()
    report = RunReport(
        run_id=ctx.run_id, product_model=product.name,
        band=cfg.band, mode=cfg.mode, total_steps=len(steps),
        config=cfg.to_dict(), preflight=pf, dry_run=False,
    )
    report.mark_started()
    print(f"\nRun ID: {ctx.run_id}")
    print(f"Artifacts: {ctx.artifacts_dir}")
    print(f"Steps: {START_AT_STEP}-{STOP_AT_STEP}")
    print("=" * 60)

    for i, step in enumerate(steps):
        if i < START_AT_STEP:
            continue
        if i > STOP_AT_STEP:
            break

        kind = type(step).__name__
        crit = " [CRITICAL]" if step.is_critical else ""
        print(f"\n--- Step {i}: {step.name} ({kind}{crit}) ---")

        t0 = time.monotonic()

        try:
            pre_ok = step.precondition(ctx)
        except Exception as exc:
            print(f"  PRECONDITION EXCEPTION: {exc}")
            pre_ok = False

        if not pre_ok:
            print(f"  Precondition FAILED")
            from orchestrator.local_automation.steps.step_result import StepResult
            result = StepResult(ok=False, step_name=step.name,
                                error="Precondition failed")
            result.elapsed_sec = time.monotonic() - t0
            report.add_step(result)
            report.mark_finished("fail")
            break

        try:
            result = step.execute(ctx)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            from orchestrator.local_automation.steps.step_result import StepResult
            result = StepResult(ok=False, step_name=step.name, error=str(exc))

        result.elapsed_sec = time.monotonic() - t0

        if result.ok and step.is_critical:
            ev = step.verify(ctx)
            result.verification_evidence = ev
            if not ev.match:
                result.ok = False
                result.verified = False
                result.error = f"Verification failed: {ev.detail}"
            else:
                result.verified = True

        report.add_step(result)

        status = "OK" if result.ok else "FAIL"
        v_tag = f" verified={result.verified}" if step.is_critical else ""
        print(f"  Result: {status} ({result.elapsed_sec:.1f}s){v_tag}")

        if result.field_evidences:
            for fn, ev in result.field_evidences.items():
                m = "PASS" if ev.match else "FAIL"
                print(f"    {fn}: [{m}] method={ev.method} expected={ev.expected!r} actual={ev.actual!r}")
        elif result.verification_evidence:
            ev = result.verification_evidence
            m = "PASS" if ev.match else "FAIL"
            print(f"    verify: [{m}] method={ev.method} expected={ev.expected!r} actual={ev.actual!r}")

        if result.error:
            print(f"  Error: {result.error}")
        if result.artifact_paths:
            print(f"  Artifacts: {len(result.artifact_paths)} files")

        if not result.ok:
            print(f"\n  STOPPING: step {step.name} failed")
            report.mark_finished("fail")
            break
    else:
        report.mark_finished("pass")

    report_path = save_run_report(report, ctx.artifacts_dir)
    print(f"\n{'=' * 60}")
    print(f"Run complete: {report.overall_status}")
    print(f"Steps: {report.completed_steps}/{report.total_steps}")
    if report.failed_step:
        print(f"Failed at: {report.failed_step}")
    print(f"Report: {report_path}")
    print("=" * 60)
    return 0 if report.overall_status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
