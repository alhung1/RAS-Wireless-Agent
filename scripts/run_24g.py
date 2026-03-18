"""Run the 2.4G LabVIEW automation flow.

Usage:
    python scripts/run_24g.py                         # LabVIEW only
    python scripts/run_24g.py --wifi-worker URL SSID PASS  # + WiFi connect after step 16
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.local_automation.labview_runner import (
    build_band_config,
    run_labview_flow,
    make_wifi_connect_hook,
    STEP_IDX_DESIGN_STAGE,
)

parser = argparse.ArgumentParser(description="Run 2.4G LabVIEW automation")
parser.add_argument("--wifi-worker", nargs=3, metavar=("URL", "SSID", "PASS"),
                    help="Connect WiFi worker after step 16 (URL SSID PASSWORD)")
args = parser.parse_args()

cfg = build_band_config(band="2.4G")
print("Config:")
print(f"  freq_range={cfg.freq_range}")
print(f"  rf_channel_2g={cfg.rf_channel_2g}")
print(f"  rf_channel_5g={cfg.rf_channel_5g}")
print(f"  rf_channel_6g={cfg.rf_channel_6g}")
print(f"  user_information={cfg.user_information}")
print(f"  mode={cfg.mode}")
print(f"  number_of_pairs={cfg.number_of_pairs}")
print(f"  number_of_pairs_5g6g={cfg.number_of_pairs_5g6g}")
print(f"  ap_name={cfg.ap_name}")
print(f"  client_name={cfg.client_name}")
print(f"  start_atten={cfg.start_atten}")
print(f"  step_size={cfg.step_size}")
print(f"  steps={cfg.steps}")
print(f"  design_stage={cfg.design_stage}")
print(f"  region={cfg.region}")

hooks = None
if args.wifi_worker:
    url, ssid, pw = args.wifi_worker
    print(f"\n  WiFi hook: connect {url} to SSID={ssid} after step 16")
    hooks = {
        STEP_IDX_DESIGN_STAGE: make_wifi_connect_hook(url, ssid, pw),
    }

print()
print("Starting 2.4G automation run...")
report = run_labview_flow(
    cfg, artifacts_base="artifacts/labview_24g", post_step_hooks=hooks,
)

print(f"\nResult: success={report.success}")
if report.error:
    print(f"Error: {report.error}")
for s in report.steps:
    status = "OK" if s["success"] else "FAIL"
    elapsed = s.get("elapsed_sec", 0)
    err = s.get("error", "")
    print(f"  {s['name']:20s} {status:4s} {elapsed:.1f}s {err}")
