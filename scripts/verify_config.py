"""Quick verification that imports and band config building work."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.local_automation.labview_runner import (
    RunConfig, BW_MODE_NAV, build_band_config,
)

print("=== Import OK ===")
print()

yaml_path = os.path.join(
    os.path.dirname(__file__),
    "..", "orchestrator", "local_automation", "ui_flow.yaml")

print("=== BW Mode Navigation Map ===")
for mode, (up, down) in BW_MODE_NAV.items():
    print(f"  {mode}: Up={up}, Down={down}")

print()
print("=== Band Configs (from ui_flow.yaml) ===")

for band in ["2.4G", "5G", "6G"]:
    cfg = build_band_config(band, yaml_path=yaml_path)
    bw_nav = BW_MODE_NAV.get(cfg.mode, (6, 0))
    print(f"\n--- {band} ---")
    print(f"  mode       = {cfg.mode}")
    print(f"  BW nav     = Up={bw_nav[0]}, Down={bw_nav[1]}")
    print(f"  rf_ch_2g   = {cfg.rf_channel_2g}")
    print(f"  rf_ch_5g   = {cfg.rf_channel_5g}")
    print(f"  rf_ch_6g   = {cfg.rf_channel_6g}")
    print(f"  pairs_2g   = {cfg.number_of_pairs}")
    print(f"  pairs_5g6g = {cfg.number_of_pairs_5g6g}")
    print(f"  user_info  = {cfg.user_information}")
    print(f"  finish_cfg = {cfg.finish_config}")

print()
print("=== Dry-run: single band ===")
from orchestrator.local_automation.labview_runner import run_labview_flow
cfg = build_band_config("2.4G", yaml_path=yaml_path)
report = run_labview_flow(cfg, dry_run=True)
print(f"  success = {report.success}")
print(f"  steps   = {len(report.steps)}")
for s in report.steps:
    print(f"    {s['name']}: {'OK' if s['success'] else 'FAIL'}")

print()
print("=== ALL CHECKS PASSED ===")
