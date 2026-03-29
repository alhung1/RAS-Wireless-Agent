"""Compatibility smoke: imports, --help, dry-run CLI (no full live wizard)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def main() -> int:
    # 1) Core imports
    sys.path.insert(0, str(ROOT))
    from orchestrator.local_automation import labview_runner as lv  # noqa: F401
    from orchestrator.local_automation.labview_legacy_report_mapping import (  # noqa: F401
        apply_engine_run_to_legacy_report,
    )

    # 2) Help / argv paths (no side effects)
    for script in ("scripts/run_24g.py", "scripts/run_labview_all_bands.py"):
        r = subprocess.run(
            [PY, str(ROOT / script), "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            print("FAIL", script, r.stderr)
            return 1
        print("OK --help", script)

    # 3) Module -m: dry-run + skip all steps (preflight + facade only; fast)
    r = subprocess.run(
        [
            PY,
            "-m",
            "orchestrator.local_automation.labview_runner",
            "--dry-run",
            "--band",
            "2.4G",
            "--skip-to",
            "19",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        print("FAIL module dry-run", r.stderr)
        return 1
    print("module dry-run exit", r.returncode)
    if r.stdout:
        print(r.stdout[-2000:] if len(r.stdout) > 2000 else r.stdout)
    if r.stderr:
        print("stderr:", r.stderr[-1500:] if len(r.stderr) > 1500 else r.stderr)

    # 4) run_24g_live is compile-only (runs at import if executed)
    compile(open(ROOT / "scripts/run_24g_live.py", encoding="utf-8").read(), "run_24g_live.py", "exec")
    print("OK compile run_24g_live.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())