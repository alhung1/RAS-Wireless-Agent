"""Orchestrator step implementations for the Phase 2.5 E2E lab workflow.

Each ``step_*`` function is self-contained: it takes structured config,
calls worker HTTP endpoints in parallel where applicable, saves per-step
artifacts, and returns a result dict with ``success`` and details.

All step functions accept an optional *artifacts_dir* parameter so the
sweep runner (Phase 3) can redirect output to per-iteration directories.
When ``None``, the module-level ``ARTIFACTS_DIR`` is used.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import time
from dataclasses import asdict, fields
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from orchestrator.logging.json_logger import get_logger
from orchestrator.utils.retry import retry_async
from orchestrator.actions.router_netgear import apply_router_settings
from orchestrator.utils.health import (
    preflight_check,
    full_health_check,
    check_router_status,
)
from orchestrator.workflow_schema import (
    ConnectOptions,
    BandWifiConfig,
    RouterConfig,
    WorkerTarget,
    ScanConfig,
    PingGateConfig,
    AutomationConfig,
)
from router.netgear_nighthawk.selectors import BandConfig

DEFAULT_ROUTER_CONTROL_URL = "http://192.168.22.100:8081"

logger = get_logger("e2e_steps")

ARTIFACTS_DIR = os.path.join(os.path.abspath("."), "artifacts")
HTTP_TIMEOUT = 120.0
RETRY_MAX = 3
RETRY_BACKOFF = 3.0


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _resolve_artifacts(artifacts_dir: Optional[str] = None) -> str:
    d = artifacts_dir or ARTIFACTS_DIR
    os.makedirs(d, exist_ok=True)
    return d


def _save_artifact(
    filename: str,
    data: Any,
    artifacts_dir: Optional[str] = None,
) -> str:
    """Write *data* as JSON and return the path."""
    d = _resolve_artifacts(artifacts_dir)
    path = os.path.join(d, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return path


def _worker_label(w: WorkerTarget) -> str:
    return w.name or w.url


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

CONNECT_TIMEOUT = 5.0


async def _call_worker(
    method: str,
    worker: WorkerTarget,
    path: str,
    payload: Optional[dict] = None,
    timeout: float = HTTP_TIMEOUT,
) -> dict[str, Any]:
    """HTTP call to a single worker with retry."""
    url = f"{worker.url.rstrip('/')}{path}"
    timeouts = httpx.Timeout(timeout, connect=CONNECT_TIMEOUT)

    async def _do():
        async with httpx.AsyncClient(timeout=timeouts) as client:
            if method.upper() == "GET":
                resp = await client.get(url, params=payload)
            else:
                resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    try:
        return await retry_async(_do, max_retries=RETRY_MAX, backoff=RETRY_BACKOFF, timeout=timeout + 30)
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Step 1: Router apply
# ---------------------------------------------------------------------------

async def step_router_apply(
    router_cfg: RouterConfig,
    router_user: str,
    router_pass: str,
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Configure router via the remote router-control service on 22.100.

    The orchestrator never touches 192.168.1.x directly.  All Playwright
    automation runs on the machine hosting the router-control service.

    Layer 5 safety:
      - Pre-flight: verify 22.x control path is alive
      - Baseline: snapshot current config via /router/status
      - Post-flight: 3-stage health check (control path, router, WAN)
      - Rollback: if Stage 2 fails, restore baseline via /router/apply
    """
    adir = _resolve_artifacts(artifacts_dir)
    control_url = router_cfg.router_control_url or DEFAULT_ROUTER_CONTROL_URL

    # --- Pre-flight: control path must be alive ---
    if not await preflight_check():
        return {
            "success": False,
            "step": "apply_router",
            "error": "PRE-FLIGHT FAILED: 22.x control path unreachable. Aborting to prevent outage.",
        }

    # --- Baseline snapshot ---
    baseline = await check_router_status(control_url)
    baseline_bands: Optional[dict] = None
    if baseline.get("success") and baseline.get("bands"):
        baseline_bands = baseline["bands"]
        _save_artifact(f"baseline_{_ts()}.json", baseline_bands, adir)
        logger.info(
            "Baseline captured: %s",
            list(baseline_bands.keys()),
            extra={"action": "apply_router", "step": "baseline_saved"},
        )
    else:
        logger.warning(
            "Could not capture baseline: %s", baseline.get("error"),
            extra={"action": "apply_router", "step": "baseline_fail"},
        )

    band_configs: dict[str, BandConfig] = {}
    for band_key, bwc in router_cfg.bands.items():
        band_configs[band_key] = BandConfig(
            ssid=bwc.ssid,
            password=bwc.password,
            channel=bwc.channel,
            security=bwc.security,
        )

    result = await apply_router_settings(
        router_control_url=control_url,
        router_base_url=router_cfg.base_url,
        user=router_user,
        password=router_pass,
        band_configs=band_configs,
        artifacts_dir=adir,
    )
    result["baseline"] = baseline_bands

    # --- Post-flight: 3-stage health check ---
    health = await full_health_check(
        router_control_url=control_url,
        router_timeout=120.0,
    )
    result["health_check"] = health
    if not health["healthy"]:
        logger.error(
            "POST-FLIGHT FAILED: health check failed after router apply!",
            extra={"action": "apply_router", "step": "health_fail"},
        )
        result["success"] = False
        result["error"] = "Post-flight health check failed"

        # --- Rollback to baseline ---
        if baseline_bands:
            logger.warning(
                "Attempting rollback to baseline...",
                extra={"action": "apply_router", "step": "rollback_start"},
            )
            rollback_configs: dict[str, BandConfig] = {}
            for bk, binfo in baseline_bands.items():
                rollback_configs[bk] = BandConfig(
                    ssid=binfo.get("ssid", ""),
                    password=binfo.get("passphrase", ""),
                    channel=binfo.get("channel"),
                    security=binfo.get("security"),
                )
            try:
                rollback_result = await apply_router_settings(
                    router_control_url=control_url,
                    router_base_url=router_cfg.base_url,
                    user=router_user,
                    password=router_pass,
                    band_configs=rollback_configs,
                    artifacts_dir=adir,
                )
                result["rollback"] = rollback_result
                if rollback_result.get("success"):
                    logger.info(
                        "Rollback succeeded",
                        extra={"action": "apply_router", "step": "rollback_ok"},
                    )
                else:
                    logger.error(
                        "Rollback failed: %s", rollback_result.get("error"),
                        extra={"action": "apply_router", "step": "rollback_fail"},
                    )
            except Exception as exc:
                logger.error(
                    "Rollback exception: %s", exc,
                    extra={"action": "apply_router", "step": "rollback_error"},
                )
                result["rollback"] = {"success": False, "error": str(exc)}

    _save_artifact(f"step_router_apply_{_ts()}.json", result, adir)
    return result


# ---------------------------------------------------------------------------
# Step 2: Wait for SSID broadcast (scan)
# ---------------------------------------------------------------------------

async def step_wait_ssid_broadcast(
    workers: list[WorkerTarget],
    scan_cfg: ScanConfig,
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Poll ``GET /wifi/scan`` on all workers until every one sees *target_ssid*."""
    adir = _resolve_artifacts(artifacts_dir)
    target = scan_cfg.target_ssid.lower()
    deadline = time.monotonic() + scan_cfg.timeout_sec
    interval = scan_cfg.poll_interval_sec
    per_worker: dict[str, dict] = {_worker_label(w): {"found": False} for w in workers}

    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        pending = [w for w in workers if not per_worker[_worker_label(w)]["found"]]
        if not pending:
            break

        logger.info(
            "SSID scan attempt %d – %d workers pending", attempt, len(pending),
            extra={"action": "wait_ssid", "step": "poll"},
        )

        tasks = [_call_worker("GET", w, "/wifi/scan") for w in pending]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for w, res in zip(pending, results):
            label = _worker_label(w)
            if isinstance(res, Exception):
                per_worker[label]["last_error"] = str(res)
                continue
            per_worker[label]["last_scan"] = res
            networks = (res.get("verification") or {}).get("networks", [])
            for net in networks:
                if (net.get("ssid") or "").lower() == target:
                    per_worker[label]["found"] = True
                    break

        if all(pw["found"] for pw in per_worker.values()):
            break
        await asyncio.sleep(interval)

    success = all(pw["found"] for pw in per_worker.values())
    result = {"success": success, "target_ssid": scan_cfg.target_ssid, "workers": per_worker}
    _save_artifact(f"step_wait_ssid_{_ts()}.json", result, adir)

    if not success:
        missing = [k for k, v in per_worker.items() if not v["found"]]
        logger.error(
            "SSID %s not seen by: %s", scan_cfg.target_ssid, missing,
            extra={"action": "wait_ssid", "step": "timeout"},
        )
    else:
        logger.info(
            "All workers see SSID %s", scan_cfg.target_ssid,
            extra={"action": "wait_ssid", "step": "done"},
        )
    return result


# ---------------------------------------------------------------------------
# Step 3: Connect workers to Wi-Fi
# ---------------------------------------------------------------------------

SECURITY_TO_AUTH: dict[str, tuple[str, str]] = {
    "wpa2": ("WPA2PSK", "AES"),
    "auto": ("WPA2PSK", "AES"),
    "wpa3": ("WPA3SAE", "AES"),
    "auto-wpa3": ("WPA3SAE", "AES"),
    "disable": ("open", "none"),
    "open": ("open", "none"),
}


async def step_connect_workers(
    workers: list[WorkerTarget],
    ssid: str,
    password: str,
    interface: Optional[str] = None,
    security: str = "wpa2",
    connect_options: Optional[ConnectOptions] = None,
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """POST /wifi/connect on all workers in parallel."""
    adir = _resolve_artifacts(artifacts_dir)
    connect_options = connect_options or ConnectOptions()
    auth, cipher = SECURITY_TO_AUTH.get(security, ("WPA2PSK", "AES"))
    if connect_options.auth:
        auth = connect_options.auth
    if connect_options.cipher:
        cipher = connect_options.cipher
    payload: dict[str, Any] = {
        "ssid": ssid,
        "password": password,
        "auth": auth,
        "cipher": cipher,
    }
    if connect_options.interface or interface:
        payload["interface"] = connect_options.interface or interface
    if connect_options.adapter_hint:
        payload["adapter_hint"] = connect_options.adapter_hint
    if connect_options.static_ip:
        payload["static_ip"] = connect_options.static_ip
        payload["mask"] = connect_options.mask
    if connect_options.band:
        payload["band"] = connect_options.band

    tasks = [_call_worker("POST", w, "/wifi/connect", payload) for w in workers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    per_worker: dict[str, dict] = {}
    all_ok = True
    for w, res in zip(workers, results):
        label = _worker_label(w)
        if isinstance(res, Exception):
            per_worker[label] = {"success": False, "error": str(res)}
            all_ok = False
        else:
            per_worker[label] = res
            if not res.get("success", False):
                all_ok = False

    result = {"success": all_ok, "workers": per_worker}
    _save_artifact(f"step_connect_workers_{_ts()}.json", result, adir)

    if all_ok:
        logger.info("All workers connected", extra={"action": "connect_workers", "step": "done"})
    else:
        failed = [k for k, v in per_worker.items() if not v.get("success")]
        logger.error(
            "Workers failed to connect: %s", failed,
            extra={"action": "connect_workers", "step": "fail"},
        )
    return result


def _snapshot_finish_files(finish_cfg: Any) -> set[str]:
    if not getattr(finish_cfg, "result_file_dir", "") or not os.path.isdir(finish_cfg.result_file_dir):
        return set()
    pattern = os.path.join(finish_cfg.result_file_dir, finish_cfg.result_file_glob)
    return set(glob.glob(pattern))


# ---------------------------------------------------------------------------
# Step 4: Ping gate
# ---------------------------------------------------------------------------

async def step_ping_gate(
    workers: list[WorkerTarget],
    ping_cfg: PingGateConfig,
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """POST /net/ping on all workers. Gate passes only if ALL succeed."""
    adir = _resolve_artifacts(artifacts_dir)
    payload = {
        "host": ping_cfg.host,
        "count": ping_cfg.count,
        "timeout_sec": ping_cfg.timeout_sec,
    }

    tasks = [_call_worker("POST", w, "/net/ping", payload) for w in workers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    per_worker: dict[str, dict] = {}
    all_ok = True
    for w, res in zip(workers, results):
        label = _worker_label(w)
        if isinstance(res, Exception):
            per_worker[label] = {"success": False, "error": str(res)}
            all_ok = False
        else:
            per_worker[label] = res
            if not res.get("success", False):
                all_ok = False

    result = {
        "success": all_ok,
        "gate_host": ping_cfg.host,
        "workers": per_worker,
    }
    _save_artifact(f"step_ping_gate_{_ts()}.json", result, adir)

    if all_ok:
        logger.info(
            "Ping gate PASSED (all workers reached %s)", ping_cfg.host,
            extra={"action": "ping_gate", "step": "pass"},
        )
    else:
        failed = [k for k, v in per_worker.items() if not v.get("success")]
        logger.error(
            "Ping gate FAILED – workers unable to reach %s: %s", ping_cfg.host, failed,
            extra={"action": "ping_gate", "step": "fail"},
        )
    return result


# ---------------------------------------------------------------------------
# Step 5: Run automation
# ---------------------------------------------------------------------------

async def step_run_automation(
    workers: list[WorkerTarget],
    auto_cfg: AutomationConfig,
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """POST /automation/run on target workers, then poll until all complete."""
    adir = _resolve_artifacts(artifacts_dir)

    target_urls = set(auto_cfg.target_workers) if auto_cfg.target_workers else None
    targets = [w for w in workers if target_urls is None or w.url in target_urls]

    payload = {
        "command": auto_cfg.command,
        "args": auto_cfg.args,
        "cwd": auto_cfg.cwd,
        "timeout_sec": auto_cfg.timeout_sec,
    }

    launch_tasks = [_call_worker("POST", w, "/automation/run", payload) for w in targets]
    launch_results = await asyncio.gather(*launch_tasks, return_exceptions=True)

    job_map: dict[str, dict] = {}
    per_worker: dict[str, dict] = {}

    for w, res in zip(targets, launch_results):
        label = _worker_label(w)
        if isinstance(res, Exception):
            per_worker[label] = {"success": False, "error": str(res)}
            continue
        job_id = res.get("job_id")
        if not job_id:
            per_worker[label] = {"success": False, "error": "No job_id returned", "raw": res}
            continue
        job_map[label] = {"worker": w, "job_id": job_id}
        per_worker[label] = {"job_id": job_id, "status": "running"}

    poll_timeout = auto_cfg.timeout_sec + 60
    poll_deadline = time.monotonic() + poll_timeout
    poll_interval = 3.0

    while time.monotonic() < poll_deadline:
        pending = {lbl: info for lbl, info in job_map.items()
                   if per_worker[lbl].get("status") == "running"}
        if not pending:
            break

        poll_tasks = [
            _call_worker("GET", info["worker"], "/automation/status",
                         {"job_id": info["job_id"]})
            for info in pending.values()
        ]
        poll_results = await asyncio.gather(*poll_tasks, return_exceptions=True)

        for (lbl, info), res in zip(pending.items(), poll_results):
            if isinstance(res, Exception):
                continue
            status = res.get("status", "running")
            if status in ("completed", "failed"):
                per_worker[lbl] = res

        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 15)

    for lbl in job_map:
        if per_worker[lbl].get("status") == "running":
            per_worker[lbl]["status"] = "timeout"
            per_worker[lbl]["success"] = False

    all_ok = all(
        pw.get("status") == "completed" and pw.get("exit_code", -1) == 0
        for pw in per_worker.values()
    )

    result = {"success": all_ok, "workers": per_worker}
    _save_artifact(f"step_automation_{_ts()}.json", result, adir)

    if all_ok:
        logger.info("All automation jobs completed successfully",
                     extra={"action": "run_automation", "step": "done"})
    else:
        failed = [k for k, v in per_worker.items()
                  if v.get("status") != "completed" or v.get("exit_code", -1) != 0]
        logger.error("Automation failed on: %s", failed,
                      extra={"action": "run_automation", "step": "fail"})
    return result


# ---------------------------------------------------------------------------
# Step 5b: Automation noop (placeholder when automation is disabled)
# ---------------------------------------------------------------------------

async def step_run_automation_noop(
    workers: list[WorkerTarget],
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Return a ``status: skipped`` result with the expected field structure.

    This keeps the per-iteration ``final_report.json`` schema identical
    regardless of whether real automation is enabled.
    """
    adir = _resolve_artifacts(artifacts_dir)
    per_worker: dict[str, dict] = {}
    for w in workers:
        per_worker[_worker_label(w)] = {
            "status": "skipped",
            "exit_code": None,
            "log_path": None,
            "elapsed_sec": None,
            "error": None,
        }

    result = {"success": True, "workers": per_worker}
    _save_artifact(f"step_automation_noop_{_ts()}.json", result, adir)
    logger.info("Automation step skipped (noop)", extra={"action": "run_automation", "step": "noop"})
    return result


# ---------------------------------------------------------------------------
# Final report builder
# ---------------------------------------------------------------------------

def build_final_report(
    workflow_name: str,
    workers: list[WorkerTarget],
    step_results: list[dict[str, Any]],
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Assemble ``final_report.json`` from collected step results."""
    adir = _resolve_artifacts(artifacts_dir)

    overall_success = all(r.get("success", False) for r in step_results)

    worker_summary: dict[str, dict] = {}
    for w in workers:
        label = _worker_label(w)
        worker_summary[label] = {}

    for sr in step_results:
        action = sr.get("action", "")
        workers_data = sr.get("workers", {})
        for label, data in workers_data.items():
            if label not in worker_summary:
                worker_summary[label] = {}
            if action == "wait_ssid_broadcast":
                worker_summary[label]["scan_ssid_found"] = data.get("found", False)
            elif action == "wifi_connect_workers":
                worker_summary[label]["connect"] = data
            elif action == "ping_gate":
                worker_summary[label]["ping"] = {
                    k: data.get(k)
                    for k in ("success", "loss_percent", "avg_latency_ms", "host", "error")
                    if data.get(k) is not None
                }
            elif action == "run_automation":
                worker_summary[label]["automation"] = {
                    k: data.get(k)
                    for k in ("status", "exit_code", "log_path", "elapsed_sec", "error")
                    if data.get(k) is not None
                }

    failed_step = None
    for i, sr in enumerate(step_results):
        if not sr.get("success", False):
            failed_step = {
                "step_index": i,
                "action": sr.get("action", ""),
                "error": sr.get("error"),
            }
            break

    artifacts_list: list[str] = []
    try:
        for fname in os.listdir(adir):
            artifacts_list.append(os.path.join(adir, fname))
    except FileNotFoundError:
        pass

    router_result = None
    labview_result = None
    for sr in step_results:
        if sr.get("action") == "router_apply":
            router_result = {
                k: sr.get(k)
                for k in ("detected_bands", "configured_bands", "error")
                if sr.get(k) is not None
            }
        elif sr.get("action") in {"labview_test", "run_labview_test"}:
            labview_result = {
                k: sr.get(k)
                for k in ("success", "profile", "band", "mode", "steps_completed", "error", "artifacts_dir", "finish")
                if sr.get(k) is not None
            }

    report = {
        "workflow": workflow_name,
        "success": overall_success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "router_apply": router_result,
        "labview": labview_result,
        "workers": worker_summary,
        "failed_step": failed_step,
        "steps": step_results,
        "artifacts": sorted(artifacts_list),
    }

    path = _save_artifact("final_report.json", report, adir)
    logger.info("Final report written to %s", path, extra={"action": "report", "step": "done"})
    return report


# ---------------------------------------------------------------------------
# LabVIEW local automation step
# ---------------------------------------------------------------------------

async def step_run_labview_test(
    band: str,
    rf_channels: dict[str, str],
    user_information: str = "",
    timeout_seconds: int = 14400,
    finish_config: Optional[dict] = None,
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Run the LabVIEW RvR throughput test via local GUI automation.

    This step drives the already-running LabVIEW 480.000.v2.03.exe through
    its wizard flow and then waits for the test to complete.

    Parameters:
        band: "2.4G", "5G", "6G", or "MLO"
        rf_channels: {"2g": "10", "5g": "44", "6g": "69"}
        user_information: free text shown in LabVIEW (e.g. "2G test")
        timeout_seconds: max wait for test completion (default 4h)
        finish_config: dict of FinishConfig fields (result_file_dir, etc.)
        artifacts_dir: where to save screenshots and logs
    """
    adir = _resolve_artifacts(artifacts_dir)

    logger.info(
        "step_run_labview_test: band=%s channels=%s",
        band, rf_channels,
        extra={"action": "labview_test", "step": "start"},
    )

    try:
        from orchestrator.local_automation.labview_runner import (
            RunConfig, run_labview_flow,
        )
    except ImportError as exc:
        return {
            "success": False,
            "error": f"labview_runner not available: {exc}",
        }

    mode_map = {"2.4G": "BW20", "5G": "BW160", "6G": "BW320"}
    pairs_map = {"2.4G": ("8", "0"), "5G": ("0", "16"), "6G": ("0", "20")}
    pairs_2g, pairs_5g6g = pairs_map.get(band, ("8", "0"))

    fc = finish_config or {
        "result_file_dir": r"D:\480\LOG\RBU",
        "result_file_glob": "*.pdf",
        "timeout_sec": timeout_seconds,
        "poll_interval_sec": 30,
    }

    cfg = RunConfig(
        band=band,
        rf_channel_2g=rf_channels.get("2g", "0"),
        rf_channel_5g=rf_channels.get("5g", "0"),
        rf_channel_6g=rf_channels.get("6g", "0"),
        user_information=user_information or f"{band} test",
        mode=mode_map.get(band, "BW20"),
        number_of_pairs=pairs_2g,
        number_of_pairs_5g6g=pairs_5g6g,
        timeout_seconds=timeout_seconds,
        finish_config=fc,
    )

    report = await asyncio.to_thread(
        run_labview_flow, cfg, os.path.join(adir, "labview"),
    )

    result = {
        "success": report.success,
        "band": band,
        "steps_completed": len(report.steps),
        "error": report.error,
        "artifacts_dir": os.path.join(adir, "labview"),
    }
    if report.finish_result:
        result["finish"] = report.finish_result

    _save_artifact(f"labview_{band}_result.json", result, adir)
    return result


async def step_run_labview_profile(
    profile_path: str,
    profiles_root: Optional[str] = None,
    artifacts_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Run a LabVIEW profile YAML through the compatibility facade.

    This bridges workflow YAML orchestration with the profile-driven LabVIEW
    runner so the full router -> worker -> LabVIEW flow can live in a single
    workflow definition.
    """
    adir = _resolve_artifacts(artifacts_dir)

    try:
        from orchestrator.local_automation.labview_runner import RunConfig as LegacyRunConfig
        from orchestrator.local_automation.labview_runner import run_labview_flow
        from orchestrator.local_automation.profiles.loader import (
            find_product_profile_path,
            get_product_adapter,
            load_product_profile,
            load_test_profile,
            resolve_run_config,
        )
    except ImportError as exc:
        return {"success": False, "error": f"labview profile runner not available: {exc}"}

    try:
        profile = load_test_profile(profile_path)
    except Exception as exc:
        return {"success": False, "error": f"Failed to load profile {profile_path!r}: {exc}"}

    product = get_product_adapter(profile.product)
    if not product:
        return {
            "success": False,
            "error": f"Product adapter not found for profile product {profile.product!r}",
        }

    product_profile = None
    pp_path = find_product_profile_path(profile.product, profiles_root)
    if pp_path:
        try:
            product_profile = load_product_profile(pp_path)
        except Exception as exc:
            return {
                "success": False,
                "error": f"Failed to load product profile {pp_path!r}: {exc}",
            }

    engine_cfg = resolve_run_config(profile, product_profile, product)
    legacy_fields = {f.name for f in fields(LegacyRunConfig)}
    legacy_kwargs = {
        k: v for k, v in asdict(engine_cfg).items()
        if k in legacy_fields
    }
    legacy_cfg = LegacyRunConfig(**legacy_kwargs)

    run_base = os.path.join(adir, "labview")
    os.makedirs(run_base, exist_ok=True)
    before_entries = set(os.listdir(run_base))

    report = await asyncio.to_thread(run_labview_flow, legacy_cfg, run_base)

    after_entries = set(os.listdir(run_base))
    new_entries = sorted(after_entries - before_entries)
    run_dir = os.path.join(run_base, new_entries[-1]) if new_entries else run_base

    result = {
        "success": report.success,
        "profile": profile.name,
        "product": profile.product,
        "band": profile.band,
        "mode": profile.mode,
        "steps_completed": len(report.steps),
        "error": report.error,
        "artifacts_dir": run_dir,
    }
    if report.finish_result:
        result["finish"] = report.finish_result

    _save_artifact(f"labview_profile_{profile.band}_{_ts()}.json", result, adir)
    return result
