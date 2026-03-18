"""Run the live 2.4G LabVIEW wizard flow (steps 00-18, no finish wait).

This script runs the full wizard but skips the multi-hour finish detection
so we can verify all 19 UI steps complete successfully.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.local_automation.labview_runner import (
    RunConfig, build_band_config, run_labview_flow,
)

yaml_path = os.path.join(
    os.path.dirname(__file__),
    "..", "orchestrator", "local_automation", "ui_flow.yaml")

cfg = build_band_config("2.4G", yaml_path=yaml_path)
cfg.finish_config = {}

print("=" * 60)
print("  Live 2.4G LabVIEW Wizard Test")
print(f"  mode={cfg.mode} pairs_2g={cfg.number_of_pairs}")
print(f"  rf_channels: 2g={cfg.rf_channel_2g} 5g={cfg.rf_channel_5g} 6g={cfg.rf_channel_6g}")
print(f"  user_info={cfg.user_information}")
print("=" * 60)
print()

report = run_labview_flow(cfg, artifacts_base="artifacts/labview")

print()
print("=" * 60)
status = "PASS" if report.success else "FAIL"
print(f"  Result: {status}")
print(f"  Steps completed: {len(report.steps)}/19")
for s in report.steps:
    ok = "OK" if s["success"] else "FAIL"
    elapsed = s.get("elapsed_sec", 0)
    err = f' - {s["error"]}' if s.get("error") else ""
    print(f"    [{ok}] {s['name']} ({elapsed:.1f}s){err}")
if report.error:
    print(f"\n  Error: {report.error}")
print("=" * 60)
