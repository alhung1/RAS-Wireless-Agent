"""E2E test: RS700 all bands (2.4G, 5G, 6G) -> Intel BE200 -> ping 192.168.1.100.

Tests each band sequentially: apply config, wait for radio restart, scan,
connect BE200, ping, then move to next band. Restores baseline at the end.

Wait rule: after router apply, wait 60s before first scan.  If SSID not found,
retry every 60s up to 3 minutes total.

Usage:
    python scripts/test_e2e_be200_all_bands.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts"
)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

ADAPTER_HINT = "Intel(R) Wi-Fi 7 BE200"
WORKER_STATIC_IP = "192.168.1.203"
WORKER_STATIC_MASK = "255.255.255.0"
PING_TARGET = "192.168.1.100"

BAND_TESTS = {
    "2.4G": {
        "ssid": "RFLab_2G_TEST",
        "password": "Test2G_Pass!",
        "channel": "6",
        "security": "wpa2",
    },
    "5G": {
        "ssid": "RFLab_5G_TEST",
        "password": "Test5G_Pass!",
        "channel": "44",
        "security": "wpa2",
    },
    "6G": {
        "ssid": "RFLab_6G_TEST",
        "password": "Test6G_Pass!",
        "channel": "37",
        "security": "wpa3",
    },
}

SCAN_INITIAL_WAIT = 60
SCAN_RETRY_INTERVAL = 60
SCAN_MAX_WAIT = 180


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _router_get(router_url: str, path: str, timeout: float = 30.0) -> dict:
    r = httpx.get(f"{router_url}{path}", timeout=timeout)
    return r.json()


def _router_post(router_url: str, path: str, payload: dict, timeout: float = 180.0) -> dict:
    r = httpx.post(f"{router_url}{path}", json=payload, timeout=timeout)
    return r.json()


def _worker_get(worker_url: str, path: str, timeout: float = 30.0) -> dict:
    r = httpx.get(f"{worker_url}{path}", timeout=timeout)
    return r.json()


def _worker_post(worker_url: str, path: str, payload: dict, timeout: float = 90.0) -> dict:
    r = httpx.post(f"{worker_url}{path}", json=payload, timeout=timeout)
    return r.json()


def _map_security_back(router_value: str) -> str:
    mapping = {
        "WPA2-PSK": "wpa2",
        "AUTO-PSK": "auto",
        "WPA3-Personal": "wpa3",
        "WPA3-SAE": "wpa3",
        "Disable": "disable",
    }
    return mapping.get(router_value, "wpa2")


def _scan_for_ssid(worker_url: str, target_ssid: str) -> tuple[bool, list[str]]:
    """Scan once and return (found, list_of_ssids)."""
    try:
        data = _worker_get(worker_url, "/wifi/scan")
        networks = (data.get("verification") or {}).get("networks", [])
        ssids = [n.get("ssid", "") for n in networks]
        return target_ssid in ssids, ssids
    except Exception as exc:
        return False, [f"error: {exc}"]


def test_single_band(
    band: str,
    config: dict,
    router_url: str,
    worker_url: str,
    adapter_hint: str,
    static_ip: str,
    static_mask: str,
    ping_target: str,
) -> dict:
    """Test one band: apply -> wait -> scan -> connect -> ping. Returns step results."""
    result: dict[str, Any] = {
        "band": band,
        "config": config,
        "steps": [],
        "success": False,
    }

    def step(name: str, ok: bool, detail: Any = None):
        entry = {"step": name, "success": ok, "timestamp": _ts(), "detail": detail or {}}
        result["steps"].append(entry)
        tag = "PASS" if ok else "FAIL"
        print(f"    [{tag}] {name}")
        return ok

    target_ssid = config["ssid"]

    # --- Apply ---
    print(f"  Applying {band}: ssid={target_ssid!r}, ch={config['channel']}, sec={config['security']}")
    try:
        apply_data = _router_post(router_url, "/router/apply", {
            "bands": {band: config}
        })
        ok = apply_data.get("success", False)
        step("apply", ok, apply_data)
        if not ok:
            print(f"    Apply failed: {apply_data.get('error')}")
            return result
    except Exception as exc:
        step("apply", False, {"error": str(exc)})
        return result

    # --- Wait + Scan (60s initial, retry every 60s, max 3 min) ---
    print(f"  Waiting {SCAN_INITIAL_WAIT}s for router radio restart...")
    time.sleep(SCAN_INITIAL_WAIT)
    elapsed_wait = SCAN_INITIAL_WAIT
    scan_found = False

    while elapsed_wait <= SCAN_MAX_WAIT:
        found, ssids = _scan_for_ssid(worker_url, target_ssid)
        print(f"    Scan @{elapsed_wait}s: SSIDs={ssids[:8]}, target={'FOUND' if found else 'NOT FOUND'}")
        if found:
            scan_found = True
            break
        if elapsed_wait + SCAN_RETRY_INTERVAL > SCAN_MAX_WAIT:
            break
        print(f"    Waiting {SCAN_RETRY_INTERVAL}s more...")
        time.sleep(SCAN_RETRY_INTERVAL)
        elapsed_wait += SCAN_RETRY_INTERVAL

    step("scan", scan_found, {"target_ssid": target_ssid, "found": scan_found, "waited_sec": elapsed_wait})
    if not scan_found:
        return result

    # --- Connect ---
    print(f"  Connecting BE200 to {target_ssid!r} (static_ip={static_ip})")
    try:
        conn_data = _worker_post(worker_url, "/wifi/connect", {
            "ssid": target_ssid,
            "password": config["password"],
            "security": config["security"],
            "band": band,
            "adapter_hint": adapter_hint,
            "static_ip": static_ip,
            "mask": static_mask,
        })
        v = conn_data.get("verification") or {}
        ssid_match = v.get("ssid_match", False)
        ip_ok = v.get("ipv4") == static_ip
        connect_ok = ssid_match and ip_ok
        step("connect", connect_ok, conn_data)
        if connect_ok:
            print(f"    Connected: ssid={v.get('connected_ssid')!r}, ip={v.get('ipv4')}, rssi={v.get('rssi')}")
        else:
            print(f"    Connect issue: ssid_match={ssid_match}, ip={v.get('ipv4')}, error={conn_data.get('error')}")
    except Exception as exc:
        step("connect", False, {"error": str(exc)})
        connect_ok = False

    if not connect_ok:
        return result

    # --- Ping ---
    print(f"  Pinging {ping_target}...")
    try:
        ping_data = _worker_post(worker_url, "/net/ping", {
            "host": ping_target,
            "count": 4,
            "timeout_sec": 5,
        })
        ping_ok = ping_data.get("success", False)
        step("ping", ping_ok, ping_data)
        print(f"    sent={ping_data.get('packets_sent')}, recv={ping_data.get('packets_received')}, "
              f"loss={ping_data.get('loss_percent')}%, avg={ping_data.get('avg_latency_ms')}ms")
    except Exception as exc:
        step("ping", False, {"error": str(exc)})
        ping_ok = False

    result["success"] = scan_found and connect_ok and ping_ok
    return result


def main():
    parser = argparse.ArgumentParser(description="E2E: RS700 all bands -> BE200 -> ping")
    parser.add_argument("--router-host", default="192.168.22.100")
    parser.add_argument("--router-port", type=int, default=8081)
    parser.add_argument("--worker-host", default="192.168.22.203")
    parser.add_argument("--worker-port", type=int, default=8080)
    parser.add_argument("--adapter-hint", default=ADAPTER_HINT)
    parser.add_argument("--static-ip", default=WORKER_STATIC_IP)
    parser.add_argument("--ping-target", default=PING_TARGET)
    args = parser.parse_args()

    router_url = f"http://{args.router_host}:{args.router_port}"
    worker_url = f"http://{args.worker_host}:{args.worker_port}"

    print(f"Router service: {router_url}")
    print(f"Worker (BE200): {worker_url}")
    print(f"Adapter hint:   {args.adapter_hint}")
    print(f"Ping target:    {args.ping_target}")

    # --- Worker health ---
    print(f"\n{'=' * 60}")
    print("PRE-CHECK: Worker health")
    print("=" * 60)
    try:
        wh = _worker_get(worker_url, "/health")
        print(f"  Worker: {wh}")
    except Exception as exc:
        print(f"  Cannot reach worker: {exc}")
        sys.exit(1)

    # --- Baseline ---
    print(f"\n{'=' * 60}")
    print("BASELINE: Capture current router config")
    print("=" * 60)
    try:
        status = _router_get(router_url, "/router/status")
        baseline = status["bands"]
        for band, info in baseline.items():
            print(f"  {band}: ssid={info.get('ssid')!r}, ch={info.get('channel')!r}, sec={info.get('security')!r}")
    except Exception as exc:
        print(f"  Cannot read baseline: {exc}")
        sys.exit(1)

    # --- Test each band ---
    report: dict[str, Any] = {
        "test": "e2e_be200_all_bands",
        "timestamp": _ts(),
        "router_url": router_url,
        "worker_url": worker_url,
        "baseline": baseline,
        "band_results": {},
        "success": False,
    }

    all_pass = True
    for band in ["2.4G", "5G", "6G"]:
        config = BAND_TESTS[band]
        print(f"\n{'=' * 60}")
        print(f"BAND TEST: {band}")
        print("=" * 60)

        band_result = test_single_band(
            band=band,
            config=config,
            router_url=router_url,
            worker_url=worker_url,
            adapter_hint=args.adapter_hint,
            static_ip=args.static_ip,
            static_mask=WORKER_STATIC_MASK,
            ping_target=args.ping_target,
        )
        report["band_results"][band] = band_result

        if band_result["success"]:
            print(f"  >> {band}: PASS")
        else:
            print(f"  >> {band}: FAIL")
            all_pass = False

    # --- Restore baseline ---
    print(f"\n{'=' * 60}")
    print("RESTORE: Baseline config for all bands")
    print("=" * 60)
    restore_bands = {}
    for band, bl in baseline.items():
        restore_bands[band] = {
            "ssid": bl.get("ssid", ""),
            "password": bl.get("passphrase", ""),
            "channel": bl.get("channel", ""),
            "security": _map_security_back(bl.get("security", "")),
        }
        print(f"  {band}: ssid={restore_bands[band]['ssid']!r}, ch={restore_bands[band]['channel']}")
    try:
        restore_data = _router_post(router_url, "/router/apply", {"bands": restore_bands})
        print(f"  Restore: {'OK' if restore_data.get('success') else 'FAILED'}")
        report["restore"] = restore_data
    except Exception as exc:
        print(f"  Restore error: {exc}")
        report["restore"] = {"error": str(exc)}

    # --- Summary ---
    report["success"] = all_pass
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    for band in ["2.4G", "5G", "6G"]:
        br = report["band_results"].get(band, {})
        tag = "PASS" if br.get("success") else "FAIL"
        print(f"  {band}: {tag}")
    print(f"\n  OVERALL: {'ALL BANDS PASSED' if all_pass else 'SOME BANDS FAILED'}")
    print("=" * 60)

    report_path = os.path.join(ARTIFACTS_DIR, "e2e_be200_all_bands_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nReport: {report_path}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
