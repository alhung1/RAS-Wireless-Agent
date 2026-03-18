"""E2E test: RS700 2.4G -> Intel BE200 on 22.203 -> ping 192.168.1.100.

Phase 1 acceptance test. Only touches the 2.4G band; 5G/6G are left untouched.

Flow:
    1. Baseline snapshot  (GET  /router/status via 22.100:8081)
    2. Apply 2.4G config  (POST /router/apply  via 22.100:8081)
    3. Scan verification   (GET  /wifi/scan     via 22.203:8080)
    4. Connect BE200       (POST /wifi/connect  via 22.203:8080)
    5. Ping 192.168.1.100  (POST /net/ping      via 22.203:8080)
    6. Restore baseline    (POST /router/apply  via 22.100:8081)
    7. Write report        (artifacts/e2e_be200_2g_report.json)

Usage:
    python scripts/test_e2e_be200_2g.py
    python scripts/test_e2e_be200_2g.py --router-host 192.168.22.100 --worker-host 192.168.22.203
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

from orchestrator.logging.json_logger import get_logger

logger = get_logger("test_e2e_be200_2g")

ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts"
)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

TEST_CONFIG_24G = {
    "ssid": "RFLab2g_BE200",
    "password": "TestPassBE200!",
    "channel": "6",
    "security": "wpa2",
}

ADAPTER_HINT = "Intel(R) Wi-Fi 7 BE200"
WORKER_STATIC_IP = "192.168.1.203"
WORKER_STATIC_MASK = "255.255.255.0"
PING_TARGET = "192.168.1.100"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _poll_status(router_url: str, timeout: float = 120.0) -> dict:
    """Poll /router/status until success."""
    deadline = time.monotonic() + timeout
    interval = 3.0
    last_err: Optional[str] = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{router_url}/router/status", timeout=30)
            data = r.json()
            if data.get("success") and data.get("bands"):
                return data
            last_err = data.get("error", "empty")
        except Exception as exc:
            last_err = str(exc)
        time.sleep(min(interval, deadline - time.monotonic()))
        interval = min(interval * 1.5, 15.0)
    raise RuntimeError(f"Status poll timed out: {last_err}")


def _apply_router(router_url: str, bands: dict, timeout: float = 180.0) -> dict:
    r = httpx.post(f"{router_url}/router/apply", json={"bands": bands}, timeout=timeout)
    return r.json()


def _worker_get(worker_url: str, path: str, timeout: float = 30.0) -> dict:
    r = httpx.get(f"{worker_url}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _worker_post(worker_url: str, path: str, payload: dict, timeout: float = 60.0) -> dict:
    r = httpx.post(f"{worker_url}{path}", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _collect_failure_artifacts(worker_url: str) -> dict:
    """Collect diagnostic info when a step fails."""
    diag: dict[str, Any] = {}
    try:
        diag["wifi_status"] = _worker_get(worker_url, "/wifi/status")
    except Exception as exc:
        diag["wifi_status_error"] = str(exc)
    try:
        diag["wifi_scan"] = _worker_get(worker_url, "/wifi/scan")
    except Exception as exc:
        diag["wifi_scan_error"] = str(exc)
    return diag


def run_test(
    router_url: str,
    worker_url: str,
    test_config: dict,
    adapter_hint: str,
    static_ip: str,
    static_mask: str,
    ping_target: str,
) -> dict:
    report: dict[str, Any] = {
        "test": "e2e_be200_2g",
        "timestamp": _ts(),
        "router_url": router_url,
        "worker_url": worker_url,
        "test_config": test_config,
        "steps": [],
        "success": False,
    }

    def step(name: str, ok: bool, detail: Any = None):
        entry = {"step": name, "success": ok, "timestamp": _ts(), "detail": detail or {}}
        report["steps"].append(entry)
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {name}")
        return ok

    # --- Step 0: Worker health ---
    print("=" * 60)
    print("STEP 0: Worker health check")
    print("=" * 60)
    try:
        wh = _worker_get(worker_url, "/health")
        step("worker_health", wh.get("status") == "ok", wh)
    except Exception as exc:
        step("worker_health", False, {"error": str(exc)})
        print(f"  Cannot reach worker at {worker_url}. Aborting.")
        return report

    # --- Step 1: Baseline snapshot ---
    print(f"\n{'=' * 60}")
    print("STEP 1: Baseline snapshot (all bands)")
    print("=" * 60)
    try:
        baseline_data = _poll_status(router_url)
        baseline = baseline_data["bands"]
        step("baseline_read", True, baseline)
        for band, info in baseline.items():
            print(f"  {band}: ssid={info.get('ssid')!r}, ch={info.get('channel')!r}")
        report["baseline"] = baseline
    except Exception as exc:
        step("baseline_read", False, {"error": str(exc)})
        print(f"  FAIL: {exc}")
        return report

    # --- Step 2: Apply 2.4G config ---
    print(f"\n{'=' * 60}")
    print("STEP 2: Apply 2.4G test config")
    print("=" * 60)
    apply_bands = {"2.4G": test_config}
    print(f"  2.4G: ssid={test_config['ssid']!r}, ch={test_config['channel']}, sec={test_config['security']}")
    try:
        apply_result = _apply_router(router_url, apply_bands)
        ok = apply_result.get("success", False)
        step("apply_2g", ok, apply_result)
        if not ok:
            print(f"  ERROR: {apply_result.get('error')}")
            return report
    except Exception as exc:
        step("apply_2g", False, {"error": str(exc)})
        return report

    # --- Step 3: Scan verification on 22.203 ---
    print(f"\n{'=' * 60}")
    print("STEP 3: Wi-Fi scan on worker (expect SSID)")
    print("=" * 60)
    target_ssid = test_config["ssid"]
    scan_found = False
    print("  Waiting 20s for router radio restart...")
    time.sleep(20)
    for attempt in range(1, 13):
        time.sleep(5)
        try:
            scan_data = _worker_get(worker_url, "/wifi/scan")
            networks = (scan_data.get("verification") or {}).get("networks", [])
            ssids = [n.get("ssid", "") for n in networks]
            print(f"  Attempt {attempt}: {len(networks)} networks, SSIDs={ssids[:10]}")
            if target_ssid in ssids:
                scan_found = True
                break
        except Exception as exc:
            print(f"  Attempt {attempt}: error={exc}")

    step("scan_verify", scan_found, {
        "target_ssid": target_ssid,
        "found": scan_found,
        "attempts": attempt,
    })
    if not scan_found:
        print(f"  SSID {target_ssid!r} not seen after {attempt} scans.")
        report["failure_diag"] = _collect_failure_artifacts(worker_url)

    # --- Step 4: Connect BE200 ---
    print(f"\n{'=' * 60}")
    print("STEP 4: Connect Intel BE200 to 2.4G SSID")
    print("=" * 60)
    connect_payload = {
        "ssid": target_ssid,
        "password": test_config["password"],
        "security": test_config["security"],
        "band": "2.4G",
        "adapter_hint": adapter_hint,
        "static_ip": static_ip,
        "mask": static_mask,
    }
    print(f"  adapter_hint={adapter_hint!r}")
    print(f"  static_ip={static_ip}, ssid={target_ssid!r}")
    try:
        connect_result = _worker_post(worker_url, "/wifi/connect", connect_payload, timeout=90)
        v = connect_result.get("verification") or {}
        ssid_match = v.get("ssid_match", False)
        ip_set = v.get("ipv4") == static_ip if static_ip else bool(v.get("ipv4"))
        connect_ok = ssid_match and ip_set
        step("connect_be200", connect_ok, connect_result)
        if connect_ok:
            print(f"  Connected: ssid={v.get('connected_ssid')!r}, ip={v.get('ipv4')}, rssi={v.get('rssi')}")
            if not connect_result.get("success"):
                print(f"  Note: verify timed out (no gateway for ping), but SSID+IP OK")
        else:
            print(f"  ERROR: ssid_match={ssid_match}, ip_set={ip_set}, error={connect_result.get('error')}")
            report["failure_diag"] = _collect_failure_artifacts(worker_url)
    except Exception as exc:
        step("connect_be200", False, {"error": str(exc)})
        connect_ok = False
        report["failure_diag"] = _collect_failure_artifacts(worker_url)

    # --- Step 5: Ping 192.168.1.100 from 22.203 ---
    print(f"\n{'=' * 60}")
    print(f"STEP 5: Ping {ping_target} from worker")
    print("=" * 60)
    ping_ok = False
    if connect_ok:
        try:
            ping_result = _worker_post(worker_url, "/net/ping", {
                "host": ping_target,
                "count": 4,
                "timeout_sec": 5,
            })
            ping_ok = ping_result.get("success", False)
            step("ping_gateway", ping_ok, ping_result)
            print(f"  sent={ping_result.get('packets_sent')}, "
                  f"recv={ping_result.get('packets_received')}, "
                  f"loss={ping_result.get('loss_percent')}%, "
                  f"avg={ping_result.get('avg_latency_ms')}ms")
        except Exception as exc:
            step("ping_gateway", False, {"error": str(exc)})
    else:
        step("ping_gateway", False, {"error": "skipped, connect failed"})
        print("  Skipped (connect failed)")

    # --- Step 6: Restore baseline 2.4G ---
    print(f"\n{'=' * 60}")
    print("STEP 6: Restore baseline 2.4G")
    print("=" * 60)
    restore_ok = False
    if "2.4G" in baseline:
        bl = baseline["2.4G"]
        restore_bands = {
            "2.4G": {
                "ssid": bl.get("ssid", ""),
                "password": bl.get("passphrase", ""),
                "channel": bl.get("channel", ""),
                "security": _map_security(bl.get("security", "")),
            }
        }
        print(f"  Restoring: ssid={restore_bands['2.4G']['ssid']!r}, ch={restore_bands['2.4G']['channel']}")
        try:
            restore_result = _apply_router(router_url, restore_bands)
            restore_ok = restore_result.get("success", False)
            step("restore_baseline", restore_ok, restore_result)
        except Exception as exc:
            step("restore_baseline", False, {"error": str(exc)})
    else:
        step("restore_baseline", False, {"error": "no 2.4G in baseline"})

    # --- Summary ---
    report["success"] = scan_found and connect_ok and ping_ok
    print(f"\n{'=' * 60}")
    if report["success"]:
        print("RESULT: PHASE 1 PASSED -- BE200 connected, ping OK")
    else:
        print("RESULT: PHASE 1 FAILED")
        for s in report["steps"]:
            if not s["success"]:
                print(f"  FAILED: {s['step']}")
    print("=" * 60)

    return report


def _map_security(router_value: str) -> str:
    mapping = {
        "WPA2-PSK": "wpa2",
        "AUTO-PSK": "auto",
        "WPA3-Personal": "wpa3",
        "WPA3-SAE": "wpa3",
        "Disable": "disable",
    }
    return mapping.get(router_value, "wpa2")


def main():
    parser = argparse.ArgumentParser(description="E2E: RS700 2.4G -> BE200 -> ping")
    parser.add_argument("--router-host", default="192.168.22.100")
    parser.add_argument("--router-port", type=int, default=8081)
    parser.add_argument("--worker-host", default="192.168.22.203")
    parser.add_argument("--worker-port", type=int, default=8080)
    parser.add_argument("--ssid", default=TEST_CONFIG_24G["ssid"])
    parser.add_argument("--password", default=TEST_CONFIG_24G["password"])
    parser.add_argument("--channel", default=TEST_CONFIG_24G["channel"])
    parser.add_argument("--security", default=TEST_CONFIG_24G["security"])
    parser.add_argument("--adapter-hint", default=ADAPTER_HINT)
    parser.add_argument("--static-ip", default=WORKER_STATIC_IP)
    parser.add_argument("--ping-target", default=PING_TARGET)
    args = parser.parse_args()

    router_url = f"http://{args.router_host}:{args.router_port}"
    worker_url = f"http://{args.worker_host}:{args.worker_port}"

    test_config = {
        "ssid": args.ssid,
        "password": args.password,
        "channel": args.channel,
        "security": args.security,
    }

    print(f"Router service: {router_url}")
    print(f"Worker (BE200): {worker_url}")
    print(f"Test SSID:      {test_config['ssid']}")
    print(f"Adapter hint:   {args.adapter_hint}")
    print(f"Static IP:      {args.static_ip}")
    print(f"Ping target:    {args.ping_target}")
    print()

    report = run_test(
        router_url=router_url,
        worker_url=worker_url,
        test_config=test_config,
        adapter_hint=args.adapter_hint,
        static_ip=args.static_ip,
        static_mask=WORKER_STATIC_MASK,
        ping_target=args.ping_target,
    )

    report_path = os.path.join(ARTIFACTS_DIR, "e2e_be200_2g_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nReport: {report_path}")

    sys.exit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
