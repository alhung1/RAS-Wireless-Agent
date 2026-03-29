"""Run a single test profile through the step engine.

Usage:
    python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml
    python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --dry-run
    python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --start-from 5
    python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --step 14
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.local_automation.engine.context import StepContext
from orchestrator.local_automation.engine.step_engine import StepEngine, PreflightError
from orchestrator.local_automation.engine.report import save_run_report
from orchestrator.local_automation.profiles.loader import (
    load_test_profile,
    load_product_profile,
    get_product_adapter,
    resolve_run_config,
    find_product_profile_path,
)
from orchestrator.local_automation.steps.registry import build_default_sequence
from orchestrator.local_automation.ui.detection import ocr_available


def main():
    parser = argparse.ArgumentParser(description="Run a single test profile")
    parser.add_argument("profile", help="Path to test profile YAML")
    parser.add_argument("--dry-run", action="store_true",
                        help="Dry-run (preflight only, no step execution)")
    parser.add_argument("--start-from", type=int, default=0,
                        help="Resume from step N")
    parser.add_argument("--step", type=int, default=None,
                        help="Run only step N (single-step mode)")
    parser.add_argument("--artifacts", default="artifacts/profile_run")
    parser.add_argument("--profiles-root", default=None)
    args = parser.parse_args()

    profile = load_test_profile(args.profile)
    print(f"Profile: {profile.name}")
    print(f"Product: {profile.product}, Band: {profile.band}, Mode: {profile.mode}")

    product = get_product_adapter(profile.product)
    if not product:
        print(f"ERROR: Product adapter not found for {profile.product!r}")
        return 1

    pp_path = find_product_profile_path(profile.product, args.profiles_root)
    pp = load_product_profile(pp_path) if pp_path else None
    cfg = resolve_run_config(profile, pp, product)

    ctx = StepContext(
        run_config=cfg, product=product,
        artifacts_dir=os.path.abspath(args.artifacts),
        dry_run=args.dry_run, ocr_available=ocr_available(),
    )

    if args.dry_run:
        from orchestrator.local_automation.engine.preflight import run_preflight
        pf = run_preflight(cfg, product, ctx)
        print(f"\nPreflight: {'PASS' if pf.passed else 'FAIL'}")
        print(pf.summary())
        return 0 if pf.passed else 1

    from orchestrator.local_automation.ui.window_manager import WindowManager
    wm = WindowManager()
    ctx.hwnd = wm.find_window()
    ctx._window_manager = wm
    if not ctx.hwnd:
        print("ERROR: LabVIEW window not found")
        return 1

    steps = build_default_sequence()
    engine = StepEngine(steps, ctx)

    if args.step is not None:
        print(f"Single-step mode: step {args.step}")
        result = engine.run_single(args.step)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.ok else 1

    print(f"Running steps {args.start_from}-{len(steps)-1}")
    try:
        report = engine.run(start_from=args.start_from, profile_name=profile.name)
    except PreflightError as exc:
        print(f"Preflight FAILED:\n{exc}")
        return 1

    print(f"\nResult: {report.overall_status}")
    print(f"Steps: {report.completed_steps}/{report.total_steps}")
    if report.failed_step:
        print(f"Failed: {report.failed_step}")
    print(f"Report: {os.path.join(ctx.artifacts_dir, 'run.json')}")
    return 0 if report.overall_status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
