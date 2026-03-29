"""LabVIEW RvR automation — thin compatibility facade (Phase D.2).

Delegates orchestration to StepEngine; implementations live in labview_runner_legacy.
Report translation: labview_legacy_report_mapping.

BACKWARD-COMPATIBILITY SURFACE (supported):
  run_labview_flow, run_all_bands, build_band_config, make_wifi_connect_hook,
  STEP_IDX_DESIGN_STAGE, RunConfig, RunReport, legacy StepResult, STEP_SEQUENCE,
  BW_MODE_NAV, window constants, find_labview_window, step_XX_* , underscored
  helpers used by scripts (_refresh_hwnd, _setup_vi, ...).

CLI: --band, --rf-* , --user-info, --username, --password, --mode, --pairs-* ,
  --skip-to, --dry-run, --config, --all-bands, --bands, --stop.

Outputs: per-run folder with result.json (legacy) and run.json (engine);
  multi_band_summary_*.json under artifacts_base.

Gaps: engine path does not emit per-step dry-run annotated PNGs; preflight is stricter.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from datetime import datetime, timezone
from typing import Any, Callable

from orchestrator.logging.json_logger import get_logger
from orchestrator.local_automation.labview_runner_legacy import *  # noqa: F403,F405
from orchestrator.local_automation.labview_runner_legacy import (  # noqa: F401
    _enum_lv_windows,
    _find_vi_window,
    _force_fg,
    _get_window_title,
    _POPUP_DISMISSED_HWNDS,
    _refresh_hwnd,
    _screenshot,
    _setup_vi,
)
from orchestrator.local_automation.engine.context import RunConfig as EngineRunConfig
from orchestrator.local_automation.engine.context import StepContext
from orchestrator.local_automation.engine.step_engine import EmergencyStopError as EngineEmergencyStopError
from orchestrator.local_automation.engine.step_engine import PreflightError, StepEngine
from orchestrator.local_automation.labview_legacy_report_mapping import apply_engine_run_to_legacy_report
from orchestrator.local_automation.profiles.loader import get_product_adapter
from orchestrator.local_automation.steps.registry import build_default_sequence
from orchestrator.local_automation.ui.detection import ocr_available
from orchestrator.local_automation.ui.window_manager import WindowManager

logger = get_logger("labview_runner")


def _legacy_run_config_to_engine(cfg: RunConfig) -> EngineRunConfig:  # noqa: F405
    """Map legacy RunConfig to engine RunConfig (field intersection)."""
    d = asdict(cfg)
    names = {f.name for f in fields(EngineRunConfig)}
    kwargs = {k: v for k, v in d.items() if k in names}
    if not kwargs.get("firmware_rev"):
        kwargs["firmware_rev"] = "V1.0.10.8"
    return EngineRunConfig(**kwargs)


def run_labview_flow(
    cfg: RunConfig,  # noqa: F405
    artifacts_base: str = "artifacts/labview",
    skip_to_step: int = 0,
    dry_run: bool = False,
    post_step_hooks: dict[int, Callable[..., Any]] | None = None,
) -> RunReport:  # noqa: F405
    """Run via StepEngine; preserve legacy RunReport / result.json."""
    import orchestrator.local_automation.labview_runner_legacy as lr

    lr._DRY_RUN = dry_run
    lr._DRY_RUN_IMG = None
    lr._DRY_RUN_HWND = None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ad = os.path.abspath(os.path.join(artifacts_base, ts))
    os.makedirs(ad, exist_ok=True)

    report = lr.RunReport(started_at=ts, config=asdict(cfg))

    logger.info(
        "LabVIEW runner started (band=%s, mode=%s, user_info=%s, dry_run=%s)",
        cfg.band, cfg.mode, cfg.user_information, dry_run,
        extra={"action": "labview_runner", "step": "start"},
    )

    try:
        lr._check_stop()
    except lr.EmergencyStopError:
        report.error = "Emergency stop triggered"
        report.finished_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        lr._save_report(report, ad)
        lr._DRY_RUN = False
        return report

    hwnd = lr.prepare_labview_session(cfg, dry_run)

    if hwnd is None and not dry_run:
        report.error = "Could not find or launch LabVIEW window"
        report.finished_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        lr._save_report(report, ad)
        lr._DRY_RUN = False
        return report

    fcfg, initial_files = lr._build_finish_config(cfg)

    product_id = os.environ.get("LV_PRODUCT", "INTEL_BE200")
    product = get_product_adapter(product_id)
    if not product:
        report.error = f"No product adapter for {product_id!r}"
        report.finished_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        lr._save_report(report, ad)
        lr._DRY_RUN = False
        return report

    engine_cfg = _legacy_run_config_to_engine(cfg)
    ctx = StepContext(
        run_config=engine_cfg,
        product=product,
        artifacts_dir=ad,
        dry_run=dry_run,
        ocr_available=ocr_available(),
        emergency_stop_file=lr.STOP_FILE,
        hwnd=hwnd,
    )
    wm = WindowManager()
    ctx._window_manager = wm

    steps = build_default_sequence()
    engine = StepEngine(steps, ctx, post_step_hooks=post_step_hooks or {})

    try:
        er = engine.run(start_from=skip_to_step, profile_name="legacy_ui_flow")
    except PreflightError as exc:
        report.error = str(exc)
        report.success = False
        report.finished_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        lr._save_report(report, ad)
        lr._DRY_RUN = False
        lr._DRY_RUN_IMG = None
        return report
    except EngineEmergencyStopError:
        report.error = "Emergency stop triggered"
        report.success = False
        report.finished_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        lr._save_report(report, ad)
        lr._DRY_RUN = False
        lr._DRY_RUN_IMG = None
        return report

    apply_engine_run_to_legacy_report(er, report, skip_to_step, lr.STEP_SEQUENCE)

    if not report.error and report.success:
        logger.info(
            "All wizard steps completed - test is starting",
            extra={"action": "labview_runner", "step": "wizard_done"},
        )
        if dry_run:
            logger.info(
                "Dry-run complete (engine path; per-step annotated PNGs not generated)",
                extra={"action": "labview_runner", "step": "dry_run_done"},
            )
        else:
            if fcfg.ui_hwnd == 0:
                fcfg.ui_hwnd = lr._find_active_vi() or hwnd or 0
            fr = lr.wait_for_finish(fcfg, artifacts_dir=ad, initial_files=initial_files)
            report.finish_result = asdict(fr)
            if fr.timed_out:
                report.error = "Test timed out"
                report.success = False
            elif fr.finished:
                logger.info(
                    "Test finished: method=%s detail=%s",
                    fr.method, fr.detail,
                    extra={"action": "labview_runner", "step": "test_done"},
                )

    lr._DRY_RUN = False
    lr._DRY_RUN_IMG = None

    report.finished_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    lr._save_report(report, ad)
    return report


def run_all_bands(
    bands: list[str] | None = None,
    yaml_path: str | None = None,
    artifacts_base: str = "artifacts/labview",
    dry_run: bool = False,
    post_step_hooks: dict[int, Callable[..., Any]] | None = None,
) -> list[RunReport]:  # noqa: F405
    """Run each band sequentially (legacy API)."""
    import orchestrator.local_automation.labview_runner_legacy as lr

    if yaml_path is None:
        yaml_path = os.path.join(os.path.dirname(__file__), "ui_flow.yaml")

    bands = bands or ["2.4G", "5G", "6G"]
    reports: list[RunReport] = []  # noqa: F405

    for idx, band in enumerate(bands):
        logger.info(
            "=== Multi-band: starting band %d/%d: %s ===",
            idx + 1, len(bands), band,
            extra={"action": "multi_band", "step": "band_start"},
        )

        cfg = lr.build_band_config(band, yaml_path=yaml_path)
        report = run_labview_flow(
            cfg,
            artifacts_base=artifacts_base,
            dry_run=dry_run,
            post_step_hooks=post_step_hooks,
        )
        reports.append(report)

        if not report.success:
            logger.error(
                "Band %s FAILED: %s", band, report.error,
                extra={"action": "multi_band", "step": "band_fail"},
            )
            break

        logger.info(
            "Band %s completed successfully", band,
            extra={"action": "multi_band", "step": "band_done"},
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary = {
        "timestamp": ts,
        "bands_requested": bands,
        "bands_completed": [r.config.get("band", "?") for r in reports if r.success],
        "bands_failed": [r.config.get("band", "?") for r in reports if not r.success],
        "reports": [asdict(r) for r in reports],
    }
    summary_path = os.path.join(artifacts_base, f"multi_band_summary_{ts}.json")
    os.makedirs(os.path.dirname(summary_path) or ".", exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info(
        "Multi-band run complete: %d/%d passed",
        len(summary["bands_completed"]), len(bands),
        extra={"action": "multi_band", "step": "done"},
    )

    return reports


def main() -> None:
    import argparse

    import orchestrator.local_automation.labview_runner_legacy as lr

    parser = argparse.ArgumentParser(description="LabVIEW RvR automation runner")
    parser.add_argument("--band", default="2.4G")
    parser.add_argument("--rf-2g", default="10")
    parser.add_argument("--rf-5g", default="44")
    parser.add_argument("--rf-6g", default="69")
    parser.add_argument("--user-info", default="2G test")
    parser.add_argument("--username", default="Alex")
    parser.add_argument("--password", default="123")
    parser.add_argument("--mode", default="BW20", choices=list(lr.BW_MODE_NAV.keys()))
    parser.add_argument("--pairs-2g", default="8")
    parser.add_argument("--pairs-5g6g", default="0")
    parser.add_argument("--skip-to", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", help="YAML config file (ui_flow.yaml)")
    parser.add_argument("--all-bands", action="store_true",
                        help="Run all three bands (2.4G, 5G, 6G) sequentially")
    parser.add_argument("--bands", nargs="*", default=None,
                        help="Specific bands to run (e.g. 2.4G 5G)")
    parser.add_argument("--stop", action="store_true",
                        help="Create the emergency stop file and exit")
    args = parser.parse_args()

    if args.stop:
        os.makedirs(os.path.dirname(lr.STOP_FILE) or ".", exist_ok=True)
        with open(lr.STOP_FILE, "w") as f:
            f.write(f"stop requested at {datetime.now(timezone.utc).isoformat()}\n")
        print(f"Emergency stop file created: {lr.STOP_FILE}")
        return

    if args.all_bands or args.bands:
        bands = args.bands or ["2.4G", "5G", "6G"]
        yaml_path = args.config or os.path.join(
            os.path.dirname(__file__), "ui_flow.yaml")
        reports = run_all_bands(
            bands=bands, yaml_path=yaml_path, dry_run=args.dry_run)
        passed = sum(1 for r in reports if r.success)
        print(f"\n{'=' * 50}")
        print(f"  Multi-Band Run: {passed}/{len(reports)} PASSED")
        for r in reports:
            band = r.config.get("band", "?")
            status = "PASS" if r.success else "FAIL"
            print(f"    {band}: {status}")
            if r.error:
                print(f"      Error: {r.error}")
        print(f"{'=' * 50}")
        return

    cfg = lr.RunConfig(
        band=args.band,
        rf_channel_2g=args.rf_2g,
        rf_channel_5g=args.rf_5g,
        rf_channel_6g=args.rf_6g,
        user_information=args.user_info,
        username=args.username,
        password=args.password,
        mode=args.mode,
        number_of_pairs=args.pairs_2g,
        number_of_pairs_5g6g=args.pairs_5g6g,
    )

    if args.config:
        import yaml
        with open(args.config, "r") as f:
            overrides = yaml.safe_load(f) or {}
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)

    report = run_labview_flow(cfg, skip_to_step=args.skip_to, dry_run=args.dry_run)

    status = "PASS" if report.success else "FAIL"
    print(f"\n{'=' * 50}")
    print(f"  LabVIEW Runner: {status}")
    print(f"  Steps: {len(report.steps)}")
    if report.error:
        print(f"  Error: {report.error}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
