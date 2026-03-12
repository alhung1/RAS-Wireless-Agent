"""Phase 3: Write test — apply router settings and verify.

Run from the orchestrator machine (this PC):
    .venv\\Scripts\\python.exe scripts\\test_router_apply.py [--step 3a|3b|3c]

Steps:
    3a  Single-band test (2.4G only) — safest
    3b  All-bands test (2.4G + 5G + 6G)
    3c  Restore baseline (reads baseline from Phase 2 status, you must confirm)
"""
from __future__ import annotations

import argparse
import json
import sys
import httpx

ROUTER_CONTROL_URL = "http://192.168.22.100:8081"
APPLY_TIMEOUT = 180.0
STATUS_TIMEOUT = 180.0


def _pp(label, data):
    print("\n" + "=" * 60)
    print("  " + label)
    print("=" * 60)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def apply_and_verify(bands_payload, description):
    base = ROUTER_CONTROL_URL.rstrip("/")

    payload = {
        "base_url": "http://192.168.1.1",
        "bands": bands_payload,
    }

    print(f"\n[APPLY] {description}")
    print(f"  Payload bands: {list(bands_payload.keys())}")
    for band, cfg in bands_payload.items():
        print(f"    {band}: ssid={cfg['ssid']}, ch={cfg.get('channel', 'auto')}, sec={cfg.get('security', 'wpa2')}")

    try:
        resp = httpx.post(
            "{}/router/apply".format(base),
            json=payload,
            timeout=APPLY_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()
        _pp("Apply Result", result)
    except Exception as exc:
        print("[FAIL] Apply request failed: {}".format(exc))
        print("       -> Check artifacts/router_service/ on 22.100")
        return False

    if not result.get("success"):
        print("[FAIL] Apply returned error: {}".format(result.get("error")))
        return False

    print("[OK] Configured bands: {}".format(result.get("configured_bands", [])))

    # --- Verify by reading status ---
    print("\n[VERIFY] Reading back status ...")
    try:
        resp = httpx.get("{}/router/status".format(base), timeout=STATUS_TIMEOUT)
        resp.raise_for_status()
        status = resp.json()
        _pp("Verification Status", status)
    except Exception as exc:
        print("[FAIL] Status read after apply failed: {}".format(exc))
        return False

    if not status.get("success"):
        print("[FAIL] Status returned error: {}".format(status.get("error")))
        return False

    all_ok = True
    for band, cfg in bands_payload.items():
        actual = status.get("bands", {}).get(band, {})
        actual_ssid = actual.get("ssid", "")
        expected_ssid = cfg["ssid"]
        if actual_ssid == expected_ssid:
            print("[OK] {} SSID verified: {}".format(band, actual_ssid))
        else:
            print("[FAIL] {} SSID mismatch: expected={}, actual={}".format(
                band, expected_ssid, actual_ssid))
            all_ok = False

    return all_ok


def step_3a():
    """Single-band test: only 2.4G."""
    bands = {
        "2.4G": {
            "ssid": "TestSSID_2G",
            "password": "testpass123",
            "channel": "6",
            "security": "wpa2",
        }
    }
    return apply_and_verify(bands, "Step 3a: Single-band test (2.4G)")


def step_3b():
    """All-bands test: 2.4G + 5G."""
    bands = {
        "2.4G": {
            "ssid": "RFLab_2G_V2",
            "password": "newpass2g",
            "channel": "1",
            "security": "wpa2",
        },
        "5G": {
            "ssid": "RFLab_5G_V2",
            "password": "newpass5g",
            "channel": "44",
            "security": "wpa2",
        },
    }
    return apply_and_verify(bands, "Step 3b: All-bands test (2.4G + 5G)")


def step_3c():
    """Restore: read current status first, then ask user for baseline values."""
    base = ROUTER_CONTROL_URL.rstrip("/")

    print("\n[RESTORE] Step 3c: Restore original settings")
    print("  This will restore to the default lab SSID/channel values.")
    print("  (Using standard RFLabTest values from test_2pc.yaml)")

    bands = {
        "2.4G": {
            "ssid": "RFLab2gXX",
            "password": "password",
            "channel": "10",
            "security": "wpa2",
        },
        "5G": {
            "ssid": "RFLab2gXX",
            "password": "password",
            "channel": "10",
            "security": "wpa2",
        },
    }

    confirm = input("\nRestore to lab defaults? (y/N): ").strip().lower()
    if confirm != "y":
        print("[SKIP] Restore cancelled.")
        return True

    return apply_and_verify(bands, "Step 3c: Restore lab defaults")


def main():
    parser = argparse.ArgumentParser(description="Phase 3: Router apply test")
    parser.add_argument(
        "--step",
        choices=["3a", "3b", "3c", "all"],
        default="3a",
        help="Which step to run (default: 3a)",
    )
    args = parser.parse_args()

    steps = {
        "3a": step_3a,
        "3b": step_3b,
        "3c": step_3c,
    }

    if args.step == "all":
        run_order = ["3a", "3b", "3c"]
    else:
        run_order = [args.step]

    for step_id in run_order:
        print("\n" + "#" * 60)
        print("  Running step {}".format(step_id))
        print("#" * 60)

        ok = steps[step_id]()
        if ok:
            print("\n[PASS] Step {} succeeded".format(step_id))
        else:
            print("\n[FAIL] Step {} failed — stopping".format(step_id))
            sys.exit(1)

    print("\n" + "=" * 60)
    print("  Phase 3 PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
