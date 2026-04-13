"""Validate test profiles and product profiles without running GUI automation.

Checks:
  - YAML schema validity (TestProfile or ProductProfileData)
  - Product adapter existence
  - Band/channel/mode compatibility (test profiles only)
  - Required fields

Usage:
    python scripts/validate_profiles.py profiles/test_matrix/be200_2g.yaml
    python scripts/validate_profiles.py --dir profiles/test_matrix/
    python scripts/validate_profiles.py --dir profiles/products/ --type product
    python scripts/validate_profiles.py --all
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
    validate_product_profile,
    validate_compatibility,
)
from orchestrator.local_automation.profiles.loader import (
    load_test_profile,
    load_product_profile,
    get_product_adapter,
)


def validate_one_test(path: str) -> bool:
    """Validate a single test profile YAML."""
    fname = os.path.basename(path)
    print(f"\n--- {fname} (test profile) ---")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    schema_ok, schema_errors = validate_test_profile(raw)
    if not schema_ok:
        for e in schema_errors:
            print(f"  [SCHEMA FAIL] {e}")
        return False
    print("  [SCHEMA OK]")

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


def validate_one_product(path: str) -> bool:
    """Validate a single product profile YAML."""
    fname = os.path.basename(path)
    print(f"\n--- {fname} (product profile) ---")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    schema_ok, schema_errors = validate_product_profile(raw)
    if not schema_ok:
        for e in schema_errors:
            print(f"  [SCHEMA FAIL] {e}")
        return False
    print("  [SCHEMA OK]")

    try:
        pp = load_product_profile(path)
    except Exception as exc:
        print(f"  [LOAD FAIL] {exc}")
        return False

    adapter = get_product_adapter(pp.product)
    if not adapter:
        print(f"  [ADAPTER WARN] No adapter registered for {pp.product!r} (profile is schema-valid)")
    else:
        print(f"  [ADAPTER OK] {adapter.name}")

    print(f"  VALID: {pp.display_name or pp.product}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Validate test profiles and/or product profiles"
    )
    parser.add_argument("profiles", nargs="*", help="Individual YAML files to validate")
    parser.add_argument("--dir", default=None, help="Directory containing YAML profiles")
    parser.add_argument(
        "--type",
        choices=["test", "product", "auto"],
        default="auto",
        help="Profile type: test, product, or auto-detect (default: auto)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate both profiles/test_matrix/ and profiles/products/",
    )
    args = parser.parse_args()

    if args.all:
        # Run both directories
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        test_dir = os.path.join(repo_root, "profiles", "test_matrix")
        prod_dir = os.path.join(repo_root, "profiles", "products")

        total_passed = 0
        total_failed = 0

        for label, directory, ptype in [
            ("Test Profiles", test_dir, "test"),
            ("Product Profiles", prod_dir, "product"),
        ]:
            paths = sorted(glob.glob(os.path.join(directory, "*.yaml")))
            print(f"\n{'=' * 40}")
            print(f"  {label} ({directory})")
            print(f"{'=' * 40}")
            if not paths:
                print(f"  No YAML files found in {directory}")
                continue
            for p in paths:
                validator = validate_one_test if ptype == "test" else validate_one_product
                if validator(os.path.abspath(p)):
                    total_passed += 1
                else:
                    total_failed += 1

        print(f"\n{'=' * 40}")
        print(f"Total: {total_passed} passed, {total_failed} failed")
        print(f"{'=' * 40}")
        return 0 if total_failed == 0 else 1

    # Single-dir or individual file mode
    paths = list(args.profiles)
    if args.dir:
        paths.extend(sorted(glob.glob(os.path.join(args.dir, "*.yaml"))))
    if not paths:
        print("No profiles to validate. Use --dir <path> or --all, or pass file paths.")
        return 1

    profile_type = args.type

    passed = 0
    failed = 0
    for p in paths:
        abspath = os.path.abspath(p)

        if profile_type == "auto":
            # Auto-detect: if path contains "products" → product, else test
            ptype = "product" if "products" in p else "test"
        else:
            ptype = profile_type

        validator = validate_one_test if ptype == "test" else validate_one_product
        if validator(abspath):
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Validated: {passed} passed, {failed} failed")
    print(f"{'=' * 40}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
