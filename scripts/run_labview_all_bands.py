"""Run the LabVIEW RvR throughput test for all three bands sequentially.

Usage:
    python scripts/run_labview_all_bands.py
    python scripts/run_labview_all_bands.py --bands 2.4G 5G
    python scripts/run_labview_all_bands.py --dry-run
    python scripts/run_labview_all_bands.py --config orchestrator/local_automation/ui_flow.yaml

Each band runs the full 19-step wizard, then waits for the test to finish
(detected when a new PDF appears in D:\\480\\LOG\\RBU, up to 4 hours).

After each test, LabVIEW returns to the main screen and the next band
starts from the beginning (click Throughput Testing -> login -> ...).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.local_automation.labview_runner import run_all_bands


def main():
    parser = argparse.ArgumentParser(
        description="Run LabVIEW RvR test for multiple bands sequentially")
    parser.add_argument(
        "--bands", nargs="*", default=["2.4G", "5G", "6G"],
        help="Bands to test (default: 2.4G 5G 6G)")
    parser.add_argument(
        "--config",
        default=os.path.join(
            os.path.dirname(__file__),
            "..", "orchestrator", "local_automation", "ui_flow.yaml"),
        help="Path to ui_flow.yaml config")
    parser.add_argument(
        "--artifacts", default="artifacts/labview",
        help="Base artifacts directory")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip actual UI automation, just log steps")
    args = parser.parse_args()

    print(f"Bands to test: {args.bands}")
    print(f"Config: {args.config}")
    print(f"Artifacts: {args.artifacts}")
    print(f"Dry run: {args.dry_run}")
    print()

    reports = run_all_bands(
        bands=args.bands,
        yaml_path=args.config,
        artifacts_base=args.artifacts,
        dry_run=args.dry_run,
    )

    print()
    print("=" * 60)
    print("  Multi-Band LabVIEW Test Results")
    print("=" * 60)
    passed = 0
    for r in reports:
        band = r.config.get("band", "?")
        mode = r.config.get("mode", "?")
        status = "PASS" if r.success else "FAIL"
        if r.success:
            passed += 1
        print(f"  {band} (mode={mode}): {status}")
        if r.error:
            print(f"    Error: {r.error}")
        if r.finish_result:
            fr = r.finish_result
            method = fr.get("method", "?")
            elapsed = fr.get("elapsed_sec", 0)
            print(f"    Finish: method={method}, elapsed={elapsed:.0f}s")
    print(f"\n  Overall: {passed}/{len(reports)} PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
