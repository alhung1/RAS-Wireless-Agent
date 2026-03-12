"""Phase 2: Read-only router verification — detect bands + read status.

Run from the orchestrator machine (this PC):
    .venv\\Scripts\\python.exe scripts\\test_router_read.py
"""
from __future__ import annotations

import json
import sys
import httpx

ROUTER_CONTROL_URL = "http://192.168.22.100:8081"
TIMEOUT = 30.0


def _pp(label, data):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    base = ROUTER_CONTROL_URL.rstrip("/")

    # --- Step 1: Health check ---
    print("[1/3] Health check ...")
    try:
        resp = httpx.get(f"{base}/health", timeout=TIMEOUT)
        resp.raise_for_status()
        health = resp.json()
        _pp("Health", health)
    except Exception as exc:
        print(f"[FAIL] Health check failed: {exc}")
        print("       -> Is router_service running on 22.100?")
        print(f"       -> Try: curl {base}/health")
        sys.exit(1)

    if not health.get("router_reachable"):
        print("[WARN] router_reachable=false — 22.100 cannot reach 192.168.1.1")
        print("       -> Check 22.100 router NIC (192.168.1.50)")

    # --- Step 2: Detect bands ---
    print("\n[2/3] Detect bands ...")
    try:
        resp = httpx.post(
            f"{base}/router/detect-bands",
            params={"base_url": "http://192.168.1.1"},
            timeout=180.0,
        )
        resp.raise_for_status()
        bands_result = resp.json()
        _pp("Detect Bands", bands_result)
    except Exception as exc:
        print(f"[FAIL] Band detection failed: {exc}")
        print("       -> Check artifacts/router_service/ on 22.100 for screenshots")
        sys.exit(1)

    if not bands_result.get("success"):
        print(f"[FAIL] Band detection returned error: {bands_result.get('error')}")
        sys.exit(1)

    bands = bands_result.get("bands", [])
    print(f"\n[OK] Detected bands: {bands}")

    # --- Step 3: Read current status ---
    print("\n[3/3] Read current status ...")
    try:
        resp = httpx.get(f"{base}/router/status", timeout=180.0)
        resp.raise_for_status()
        status = resp.json()
        _pp("Router Status (baseline)", status)
    except Exception as exc:
        print(f"[FAIL] Status read failed: {exc}")
        sys.exit(1)

    if status.get("success"):
        print("\n[OK] Baseline recorded. Current settings per band:")
        for band, info in status.get("bands", {}).items():
            print(f"  {band}: SSID={info.get('ssid')}, Channel={info.get('channel')}")
    else:
        print(f"[FAIL] Status returned error: {status.get('error')}")
        sys.exit(1)

    print("\n" + "="*60)
    print("  Phase 2 PASSED — Read-only test complete")
    print("="*60)


if __name__ == "__main__":
    main()
