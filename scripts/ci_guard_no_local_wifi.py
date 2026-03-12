"""CI guard: ensure orchestrator code never uses local Wi-Fi commands.

Scans orchestrator/**/*.py and workflows/**/*.yaml for forbidden patterns
that indicate direct local Wi-Fi operations.  The orchestrator MUST proxy
all router and Wi-Fi operations through the remote worker/router-service.

Exit code 0 = clean, 1 = violations found.

Usage:
    python scripts/ci_guard_no_local_wifi.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_PATTERNS = [
    re.compile(r"wifi_connect_local", re.IGNORECASE),
    re.compile(r"netsh\s+wlan\s+connect", re.IGNORECASE),
    re.compile(r"netsh\s+wlan\s+disconnect", re.IGNORECASE),
    re.compile(r"netsh\s+wlan\s+add\s+profile", re.IGNORECASE),
]

SAFETY_GUARD_PATTERNS = [
    re.compile(r"#\s*(BLOCKED|DISABLED|safety)", re.IGNORECASE),
    re.compile(r"\"wifi_connect_local is (DISABLED|disabled|BLOCKED)", re.IGNORECASE),
    re.compile(r"safety_block", re.IGNORECASE),
    re.compile(r"blocked by location services", re.IGNORECASE),
    re.compile(r"step\.action\s*==\s*\"wifi_connect_local\"", re.IGNORECASE),
]

EXCLUDED_FILES = {
    "orchestrator/actions/wifi_local.py",
}

SCAN_DIRS: list[tuple[Path, str]] = [
    (PROJECT_ROOT / "orchestrator", "*.py"),
    (PROJECT_ROOT / "workflows", "*.yaml"),
]


def _is_safety_guard(line: str) -> bool:
    """Return True if the line is a known safety guard (false positive)."""
    return any(p.search(line) for p in SAFETY_GUARD_PATTERNS)


def scan_file(path: Path) -> list[dict]:
    """Return a list of violations found in *path*."""
    violations = []
    try:
        rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        rel = str(path)

    if rel in EXCLUDED_FILES:
        return violations

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return violations

    for line_no, line in enumerate(text.splitlines(), start=1):
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(line) and not _is_safety_guard(line):
                violations.append({
                    "file": rel,
                    "line": line_no,
                    "pattern": pat.pattern,
                    "content": line.strip()[:120],
                })
    return violations


def main() -> int:
    all_violations: list[dict] = []

    for scan_dir, glob in SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        for path in scan_dir.rglob(glob):
            if path.is_file():
                all_violations.extend(scan_file(path))

    if all_violations:
        print(f"CI GUARD FAILED: {len(all_violations)} violation(s) found:\n")
        for v in all_violations:
            print(f"  {v['file']}:{v['line']}  pattern={v['pattern']!r}")
            print(f"    {v['content']}")
        print(
            "\nThe orchestrator must NOT use local Wi-Fi commands. "
            "All Wi-Fi operations must go through the remote worker API."
        )
        return 1

    print("CI GUARD PASSED: no local Wi-Fi violations in orchestrator/ or workflows/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
