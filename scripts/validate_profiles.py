"""Validate test profiles without running GUI automation.

Checks:
  - YAML schema validity
  - Product adapter existence
  - Band/channel/mode compatibility
  - Required fields

Usage:
    python scripts/validate_profiles.py profiles/test_matrix/be200_2g.yaml
    python scripts/validate_profiles.py --dir profiles/test_matrix/
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.local_automation.profiles.validator import (
    validate_test_profile,
    validate_compatibility,
)
from orchestrator.local_automation.profiles.loader import (
    load_test_profile,
    get_product_adapter,
)


def validate_one(path: str) -> bool:
    fname = os.path.basename(path)
    print(f"\n--- {fname} ---")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    schema_ok, schema_errors = validate_test_profile(raw)
    if not schema_ok:
        for e in schema_errors:
            print(f"  [SCHEMA FAIL] {e}")
        return False
    print(f"  [SCHEMA OK]")

    try:
        profile = load_test_profile(path)
    except Exception as exc:
        print(f"  [LOAD FAIL] {exc}")
        return False

    product = get_product_adapter(profile.product)
    if not product:
        print(f"  [PRODUCT FAIL] Adapter not found for {profile.product!r}")
        return False
    print(f"  [PRODUCT OK] {product.name}")

    compat_ok, compat_errors = validate_compatibility(profile, product)
    if not compat_ok:
        for e in compat_errors:
            print(f"  [COMPAT FAIL] {e}")
        return False
    print(f"  [COMPAT OK] band={profile.band} mode={profile.mode}")
    print(f"  VALID: {profile.name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Validate test profiles")
    parser.add_argument("profiles", nargs="*")
    parser.add_argument("--dir", default=None)
    args = parser.parse_args()

    paths = list(args.profiles)
    if args.dir:
        paths.extend(sorted(glob.glob(os.path.join(args.dir, "*.yaml"))))
    if not paths:
        print("No profiles to validate.")
        return 1

    passed = 0
    failed = 0
    for p in paths:
        if validate_one(os.path.abspath(p)):
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Validated: {passed} passed, {failed} failed")
    print(f"{'=' * 40}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
