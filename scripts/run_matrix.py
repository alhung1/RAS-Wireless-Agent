"""Run multiple test profiles sequentially (matrix runner).

Usage:
    python scripts/run_matrix.py profiles/test_matrix/be200_2g.yaml profiles/test_matrix/be200_5g.yaml
    python scripts/run_matrix.py profiles/test_matrix/*.yaml --continue-on-failure
    python scripts/run_matrix.py --dir profiles/test_matrix/ --dry-run
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.local_automation.engine.matrix_runner import run_matrix


def main():
    parser = argparse.ArgumentParser(description="Run test profile matrix")
    parser.add_argument("profiles", nargs="*", help="Profile YAML paths")
    parser.add_argument("--dir", default=None,
                        help="Directory of profile YAMLs (alternative to listing files)")
    parser.add_argument("--continue-on-failure", action="store_true",
                        help="Continue to next profile after failure")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wait-for-finish", action="store_true",
                        help="Wait for finish detection after each passing profile")
    parser.add_argument(
        "--between-profiles",
        choices=["noop", "assert_main_screen", "restart"],
        default="noop",
        help="How to prepare LabVIEW between passing profiles",
    )
    parser.add_argument("--artifacts", default="artifacts/matrix")
    parser.add_argument("--profiles-root", default=None)
    args = parser.parse_args()

    paths = list(args.profiles)
    if args.dir:
        paths.extend(sorted(glob.glob(os.path.join(args.dir, "*.yaml"))))
    if not paths:
        print("ERROR: No profiles specified. Use positional args or --dir.")
        return 1

    paths = [os.path.abspath(p) for p in paths]
    print(f"Matrix: {len(paths)} profiles")
    for p in paths:
        print(f"  {p}")
    print(f"Stop on failure: {not args.continue_on_failure}")
    print(f"Dry run: {args.dry_run}")
    print(f"Wait for finish: {args.wait_for_finish}")
    print(f"Between profiles: {args.between_profiles}")
    print()

    summary = run_matrix(
        profile_paths=paths,
        artifacts_base=args.artifacts,
        stop_on_failure=not args.continue_on_failure,
        dry_run=args.dry_run,
        profiles_root=args.profiles_root,
        wait_for_finish=args.wait_for_finish,
        between_profiles=args.between_profiles,
    )

    print()
    print("=" * 60)
    print(f"  Matrix Result: {summary.passed} passed, "
          f"{summary.failed} failed, {summary.skipped} skipped")
    print("=" * 60)
    for entry in summary.entries:
        tag = "PASS" if entry.status == "pass" else entry.status.upper()
        print(f"  [{tag:12s}] {entry.profile_name:30s} "
              f"band={entry.band:5s} mode={entry.mode:6s} "
              f"({entry.elapsed_sec:.1f}s)")
        if entry.error:
            print(f"               Error: {entry.error}")
    print("=" * 60)
    print(f"Summary: {os.path.join(os.path.abspath(args.artifacts), 'matrix_summary.json')}")

    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
