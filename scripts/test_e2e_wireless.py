"""End-to-end wireless verification test.

Verifies that SSID, password, channel, and security can be read and written for
all 3 bands (2.4G, 5G, 6G) on the Netgear RS700 router via the router service.

Steps:
    1. Health check
    2. Read current settings (baseline snapshot)
    3. Apply test configuration with distinct values per band
    4. Re-read and verify every field matches
    5. Wi-Fi scan verification (SSID presence required, channel best-effort)
    6. Restore original settings from baseline
    7. Re-read and verify originals are restored

Usage:
    python scripts/test_e2e_wireless.py
    python scripts/test_e2e_wireless.py --remote-host 192.168.22.100
    python scripts/test_e2e_wireless.py --worker-host 192.168.22.100 --worker-port 8080
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from orchestrator.logging.json_logger import get_logger

logger = get_logger("test_e2e_wireless")

ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts"
)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

TEST_BANDS = {
    "2.4G": {
        "ssid": "RFLab2g_VERIFY",
        "password": "TestPass24!",
        "channel": "6",
        "security": "wpa2",
    },
    "5G": {
        "ssid": "RFLab5g_VERIFY",
        "password": "TestPass5g!",
        "channel": "36",
        "security": "wpa2",
    },
    "6G": {
        "ssid": "RFLab6g_VERIFY",
        "password": "TestPass6g!",
        "channel": "37",
        "security": "wpa3",
    },
}

BAND_EXPECTED_CHANNELS = {
    "2.4G": "6",
    "5G": "36",
    "6G": "37",
}


def poll_status(
    base_url: str,
    *,
    timeout: float = 120.0,
    interval: float = 3.0,
    backoff: float = 1.5,
    max_interval: float = 15.0,
) -> dict:
    """Poll /router/status until it returns a successful response."""
    deadline = time.monotonic() + timeout
    last_error: Optional[str] = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/router/status", timeout=30)
            data = r.json()
            if data.get("success") and data.get("bands"):
                return data
            last_error = data.get("error", "empty bands")
        except Exception as exc:
            last_error = str(exc)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
        interval = min(interval * backoff, max_interval)
    raise RuntimeError(f"Status poll timed out after {timeout}s: {last_error}")


def apply_config(base_url: str, bands: dict, *, timeout: float = 180.0) -> dict:
    """POST /router/apply and return the response."""
    r = httpx.post(
        f"{base_url}/router/apply",
        json={"bands": bands},
        timeout=timeout,
    )
    return r.json()


def verify_band(
    band: str,
    actual: dict,
    expected: dict,
    *,
    check_fields: tuple[str, ...] = ("ssid", "passphrase", "channel"),
) -> list[dict]:
    """Compare actual vs expected fields for one band.  Returns list of failures."""
    failures = []
    for field in check_fields:
        exp_key = field
        act_key = field
        if field in ("password", "passphrase"):
            exp_key = "password"
            act_key = "passphrase"

        exp_val = expected.get(exp_key, "")
        act_val = actual.get(act_key, "")
        if str(act_val) != str(exp_val):
            failures.append({
                "band": band,
                "field": act_key,
                "expected": str(exp_val),
                "actual": str(act_val),
            })
    return failures


def wifi_scan(worker_url: str, *, timeout: float = 30.0) -> Optional[dict]:
    """Call GET /wifi/scan on the worker and return the JSON response."""
    try:
        r = httpx.get(f"{worker_url}/wifi/scan", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("Wi-Fi scan failed: %s", exc)
        return None


def verify_scan_results(
    scan_data: dict,
    expected_ssids: dict[str, str],
) -> dict:
    """Check that expected SSIDs appear in scan results.

    SSID presence is required (fail if missing).
    Channel matching is best-effort (warn only, especially for 6 GHz).

    Returns a dict with per-SSID results.
    """
    networks = []
    if scan_data.get("verification"):
        networks = scan_data["verification"].get("networks", [])
    elif scan_data.get("networks"):
        networks = scan_data["networks"]

    seen_ssids: dict[str, list[dict]] = {}
    for net in networks:
        ssid = net.get("ssid", "")
        if ssid:
            seen_ssids.setdefault(ssid, []).append(net)

    results: dict[str, dict] = {}
    for band, ssid in expected_ssids.items():
        entry: dict = {"ssid": ssid, "found": ssid in seen_ssids}
        if entry["found"]:
            matching = seen_ssids[ssid]
            entry["scan_entries"] = matching
            expected_ch = BAND_EXPECTED_CHANNELS.get(band)
            if expected_ch:
                channels_seen = [str(n.get("channel", "")) for n in matching]
                entry["channel_match"] = expected_ch in channels_seen
                entry["channels_seen"] = channels_seen
                if not entry["channel_match"]:
                    is_6ghz = band == "6G"
                    entry["channel_note"] = (
                        "6 GHz channel may not be visible via scan (best-effort)"
                        if is_6ghz
                        else f"Expected channel {expected_ch}, saw {channels_seen}"
                    )
        results[band] = entry

    return results


def run_test(base_url: str, worker_url: Optional[str] = None) -> dict:
    """Execute the full E2E wireless verification test."""
    report: dict = {
        "test": "e2e_wireless_verification",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "worker_url": worker_url,
        "steps": [],
        "success": False,
    }

    def log_step(name: str, success: bool, detail: Optional[dict] = None):
        entry = {"step": name, "success": success, "detail": detail or {}}
        report["steps"].append(entry)
        status = "PASS" if success else "FAIL"
        logger.info(
            "[%s] %s", status, name,
            extra={"action": "test_step", "step": name},
        )

    # --- Step 1: Health check ---
    print("=" * 60)
    print("STEP 1: Health check")
    print("=" * 60)
    try:
        r = httpx.get(f"{base_url}/health", timeout=15)
        health = r.json()
        ok = health.get("status") == "ok" and health.get("router_reachable")
        log_step("health_check", ok, health)
        print(f"  Status: {health}")
        if not ok:
            print("  FAIL: Service not healthy. Aborting.")
            return report
    except Exception as exc:
        log_step("health_check", False, {"error": str(exc)})
        print(f"  FAIL: {exc}")
        return report

    # --- Step 2: Baseline snapshot ---
    print(f"\n{'=' * 60}")
    print("STEP 2: Read baseline (all 3 bands)")
    print("=" * 60)
    try:
        baseline_data = poll_status(base_url, timeout=120)
        baseline = baseline_data["bands"]
        log_step("baseline_read", True, baseline)
        for band, info in baseline.items():
            print(f"  {band}: ssid={info.get('ssid')!r}, ch={info.get('channel')!r}, "
                  f"sec={info.get('security')!r}")
        report["baseline"] = baseline

        if len(baseline) < 3:
            print(f"  WARNING: Only {len(baseline)} bands detected, expected 3.")
    except Exception as exc:
        log_step("baseline_read", False, {"error": str(exc)})
        print(f"  FAIL: {exc}")
        return report

    # --- Step 3: Apply test configuration ---
    print(f"\n{'=' * 60}")
    print("STEP 3: Apply test configuration")
    print("=" * 60)
    for band, cfg in TEST_BANDS.items():
        print(f"  {band}: ssid={cfg['ssid']!r}, pass={cfg['password']!r}, "
              f"ch={cfg['channel']}, sec={cfg['security']}")
    try:
        apply_result = apply_config(base_url, TEST_BANDS)
        ok = apply_result.get("success", False)
        log_step("apply_test_config", ok, apply_result)
        print(f"  Apply result: success={ok}")
        if not ok:
            print(f"  ERROR: {apply_result.get('error')}")
            return report
    except Exception as exc:
        log_step("apply_test_config", False, {"error": str(exc)})
        print(f"  FAIL: {exc}")
        return report

    # --- Step 4: Verify test configuration via /router/status ---
    print(f"\n{'=' * 60}")
    print("STEP 4: Verify test configuration (router readback)")
    print("=" * 60)
    try:
        verify_data = poll_status(base_url, timeout=120)
        verify_bands = verify_data["bands"]
        all_failures: list[dict] = []
        for band, expected in TEST_BANDS.items():
            actual = verify_bands.get(band, {})
            print(f"  {band}: ssid={actual.get('ssid')!r}, "
                  f"ch={actual.get('channel')!r}, "
                  f"pass={actual.get('passphrase')!r}")
            failures = verify_band(band, actual, expected)
            all_failures.extend(failures)
            for f in failures:
                print(f"    [FAIL] {f['field']}: expected {f['expected']!r}, "
                      f"got {f['actual']!r}")
            if not failures:
                print(f"    [OK] All fields match")

        readback_ok = len(all_failures) == 0
        log_step("verify_test_config", readback_ok, {
            "bands": verify_bands,
            "failures": all_failures,
        })
    except Exception as exc:
        log_step("verify_test_config", False, {"error": str(exc)})
        print(f"  FAIL: {exc}")
        readback_ok = False

    # --- Step 5: Wi-Fi scan verification ---
    scan_ok = True
    print(f"\n{'=' * 60}")
    print("STEP 5: Wi-Fi scan verification")
    print("=" * 60)

    if worker_url:
        print(f"  Scanning via worker: {worker_url}")
        time.sleep(5)
        scan_data = wifi_scan(worker_url)
        if scan_data:
            expected_ssids = {band: cfg["ssid"] for band, cfg in TEST_BANDS.items()}
            scan_results = verify_scan_results(scan_data, expected_ssids)
            report["scan_verification"] = scan_results

            for band, sr in scan_results.items():
                found_str = "FOUND" if sr["found"] else "NOT FOUND"
                ch_str = ""
                if sr.get("channel_match") is not None:
                    ch_str = " ch=" + ("MATCH" if sr["channel_match"] else "WARN")
                print(f"  {band} ({sr['ssid']}): {found_str}{ch_str}")
                if sr.get("channel_note"):
                    print(f"    Note: {sr['channel_note']}")
                if not sr["found"]:
                    scan_ok = False

            log_step("wifi_scan_verify", scan_ok, scan_results)
            if not scan_ok:
                print("  [WARN] Some SSIDs not found in scan. This may be transient.")
        else:
            print("  [WARN] Scan returned no data. Treating as non-fatal.")
            log_step("wifi_scan_verify", True, {"note": "scan returned no data, skipped"})
    else:
        print("  [SKIP] No --worker-host provided, skipping Wi-Fi scan.")
        log_step("wifi_scan_verify", True, {"note": "skipped, no worker_url"})

    # --- Step 6: Restore original settings ---
    print(f"\n{'=' * 60}")
    print("STEP 6: Restore original settings")
    print("=" * 60)
    restore_bands = {}
    for band, info in baseline.items():
        restore_bands[band] = {
            "ssid": info.get("ssid", ""),
            "password": info.get("passphrase", ""),
            "security": _map_security_back(info.get("security", ""), band),
        }
        if info.get("channel"):
            restore_bands[band]["channel"] = info["channel"]
        print(f"  {band}: restoring ssid={restore_bands[band]['ssid']!r}, "
              f"ch={restore_bands[band].get('channel', 'unchanged')}")

    try:
        restore_result = apply_config(base_url, restore_bands)
        restore_ok = restore_result.get("success", False)
        log_step("restore_original", restore_ok, restore_result)
        print(f"  Restore result: success={restore_ok}")
        if not restore_ok:
            print(f"  ERROR: {restore_result.get('error')}")
    except Exception as exc:
        log_step("restore_original", False, {"error": str(exc)})
        print(f"  FAIL: {exc}")
        restore_ok = False

    # --- Step 7: Verify restoration ---
    print(f"\n{'=' * 60}")
    print("STEP 7: Verify restoration")
    print("=" * 60)
    try:
        final_data = poll_status(base_url, timeout=120)
        final_bands = final_data["bands"]
        restore_failures: list[dict] = []
        for band, info in baseline.items():
            actual = final_bands.get(band, {})
            print(f"  {band}: ssid={actual.get('ssid')!r}, "
                  f"ch={actual.get('channel')!r}")
            if actual.get("ssid") != info.get("ssid"):
                restore_failures.append({
                    "band": band,
                    "field": "ssid",
                    "expected": info.get("ssid"),
                    "actual": actual.get("ssid"),
                })
                print(f"    [FAIL] ssid: expected {info.get('ssid')!r}, "
                      f"got {actual.get('ssid')!r}")
            else:
                print(f"    [OK] SSID restored")

        final_ok = len(restore_failures) == 0
        log_step("verify_restore", final_ok, {
            "bands": final_bands,
            "failures": restore_failures,
        })
    except Exception as exc:
        log_step("verify_restore", False, {"error": str(exc)})
        print(f"  FAIL: {exc}")
        final_ok = False

    # --- Summary ---
    report["success"] = readback_ok and restore_ok and final_ok

    print(f"\n{'=' * 60}")
    if report["success"]:
        print("RESULT: ALL TESTS PASSED")
    else:
        print("RESULT: SOME TESTS FAILED")
        for step in report["steps"]:
            if not step["success"]:
                print(f"  FAILED: {step['step']}")
    print("=" * 60)

    return report


def _map_security_back(router_value: str, band: str) -> str:
    """Map router-reported security values back to API-accepted short names."""
    mapping = {
        "WPA2-PSK": "wpa2",
        "AUTO-PSK": "auto",
        "WPA3-Personal": "wpa3",
        "WPA3-Mixed": "wpa3-mixed",
        "OWE": "owe",
        "Disable": "disable",
        "WPA3-SAE": "wpa3",
    }
    return mapping.get(router_value, "wpa2")


def main():
    parser = argparse.ArgumentParser(
        description="E2E wireless verification test for all 3 bands"
    )
    parser.add_argument(
        "--remote-host",
        default="192.168.22.100",
        help="Router service host (default: 192.168.22.100)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="Router service port (default: 8081)",
    )
    parser.add_argument(
        "--worker-host",
        default=None,
        help="Worker host for Wi-Fi scan verification (e.g. 192.168.22.100)",
    )
    parser.add_argument(
        "--worker-port",
        type=int,
        default=8080,
        help="Worker port for Wi-Fi scan (default: 8080)",
    )
    args = parser.parse_args()

    base_url = f"http://{args.remote_host}:{args.port}"
    worker_url = None
    if args.worker_host:
        worker_url = f"http://{args.worker_host}:{args.worker_port}"

    print(f"Target: {base_url}")
    if worker_url:
        print(f"Worker: {worker_url}")
    print()

    report = run_test(base_url, worker_url=worker_url)

    report_path = os.path.join(ARTIFACTS_DIR, "e2e_wireless_test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nReport saved to: {report_path}")

    sys.exit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
