"""3-stage health check for the orchestrator (Layer 5).

Check order matters -- control path first, then router, then WAN:

  Stage 1: 22.x control path -- orchestrator can reach 22.100        (hard gate)
  Stage 2: Router online -- router-control service reports router OK  (hard gate)
  Stage 3: WAN -- orchestrator still has internet                     (configurable)

If Stage 1 fails, everything stops immediately.
"""
from __future__ import annotations

import asyncio
import socket
import subprocess
from typing import Any, Literal, Optional

import httpx

from orchestrator.logging.json_logger import get_logger
from orchestrator.utils.timeouts import POLL_INTERVAL, POLL_BACKOFF

logger = get_logger("health")

PING_COUNT = 1
PING_TIMEOUT_SEC = 3
HTTP_TIMEOUT = 10.0
WAN_CHECK_HOST = "8.8.8.8"
WAN_DNS_HOST = "dns.google"
WAN_TCP_PORT = 443
WAN_TCP_TIMEOUT = 5

WanCheckMode = Literal["hard", "soft", "skip"]


def _ping(host: str, timeout: int = PING_TIMEOUT_SEC) -> bool:
    """Synchronous ICMP ping (single packet)."""
    try:
        r = subprocess.run(
            ["ping", "-n", str(PING_COUNT), "-w", str(timeout * 1000), host],
            capture_output=True, text=True,
            timeout=timeout + 5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _dns_resolve(hostname: str, timeout: float = WAN_TCP_TIMEOUT) -> Optional[str]:
    """Resolve hostname to IP.  Returns the first A-record or None."""
    try:
        socket.setdefaulttimeout(timeout)
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        if infos:
            return infos[0][4][0]
    except Exception:
        pass
    return None


def _tcp_connect(host: str, port: int, timeout: float = WAN_TCP_TIMEOUT) -> bool:
    """Attempt a TCP connect to host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


# ------------------------------------------------------------------
# Stage 1 -- 22.x control path
# ------------------------------------------------------------------

async def check_control_path(
    target_host: str = "192.168.22.100",
    timeout: float = PING_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Verify the orchestrator can reach the 22.x management target.

    This MUST pass before any dangerous operation.  If it fails, the
    orchestrator should abort -- the control path is broken.
    """
    loop = asyncio.get_event_loop()
    reachable = await loop.run_in_executor(None, _ping, target_host, int(timeout))

    result = {
        "stage": "control_path",
        "target": target_host,
        "reachable": reachable,
    }

    if reachable:
        logger.info(
            "Control path OK: %s reachable", target_host,
            extra={"action": "health", "step": "control_path_ok"},
        )
    else:
        logger.error(
            "CONTROL PATH DOWN: %s unreachable -- aborting", target_host,
            extra={"action": "health", "step": "control_path_fail"},
        )
    return result


# ------------------------------------------------------------------
# Stage 2 -- Router online (via router-control service)
# ------------------------------------------------------------------

async def check_router_via_service(
    router_control_url: str,
    timeout: float = 120.0,
    poll_interval: float = POLL_INTERVAL,
) -> dict[str, Any]:
    """Poll the router-control service's /health endpoint until the
    router is reported as reachable, or timeout.

    This runs AFTER Stage 1 passes -- we know the control path works.
    """
    url = f"{router_control_url.rstrip('/')}/health"
    elapsed = 0.0
    interval = poll_interval
    last_error: Optional[str] = None

    while elapsed < timeout:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("router_reachable"):
                    logger.info(
                        "Router online (via service, elapsed=%.1fs)", elapsed,
                        extra={"action": "health", "step": "router_online"},
                    )
                    return {"stage": "router", "online": True, "elapsed_sec": round(elapsed, 1)}
                last_error = "router not reachable yet"
        except Exception as exc:
            last_error = str(exc)

        logger.info(
            "Waiting for router (elapsed=%.1fs): %s", elapsed, last_error,
            extra={"action": "health", "step": "router_polling"},
        )
        await asyncio.sleep(interval)
        elapsed += interval
        interval = min(interval * POLL_BACKOFF, 15)

    logger.error(
        "Router did NOT recover within %.0fs", timeout,
        extra={"action": "health", "step": "router_timeout"},
    )
    return {
        "stage": "router",
        "online": False,
        "elapsed_sec": round(elapsed, 1),
        "error": last_error,
    }


async def check_router_status(
    router_control_url: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Read the current router configuration via GET /router/status.

    Returns the status dict on success, or an error dict.
    """
    url = f"{router_control_url.rstrip('/')}/router/status"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and data.get("bands"):
                return {"success": True, "bands": data["bands"]}
            return {"success": False, "error": data.get("error", "empty response")}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ------------------------------------------------------------------
# Stage 3 -- WAN connectivity (DNS + TCP + ICMP)
# ------------------------------------------------------------------

async def check_wan(
    host: str = WAN_CHECK_HOST,
    dns_host: str = WAN_DNS_HOST,
    tcp_port: int = WAN_TCP_PORT,
    timeout: float = PING_TIMEOUT_SEC,
    mode: WanCheckMode = "soft",
) -> dict[str, Any]:
    """Verify the orchestrator still has internet access.

    Performs three sub-checks:
      1. DNS resolution of *dns_host*
      2. TCP connect to resolved IP on *tcp_port*
      3. ICMP ping to *host*

    *mode* controls severity:
      - "hard": treat failure as an error (fail the workflow)
      - "soft": warn only (default), include result in report
      - "skip": return immediately with skipped=True
    """
    if mode == "skip":
        return {"stage": "wan", "skipped": True, "reachable": None}

    loop = asyncio.get_event_loop()

    dns_ip = await loop.run_in_executor(None, _dns_resolve, dns_host, WAN_TCP_TIMEOUT)
    tcp_ok = False
    if dns_ip:
        tcp_ok = await loop.run_in_executor(None, _tcp_connect, dns_ip, tcp_port, WAN_TCP_TIMEOUT)
    icmp_ok = await loop.run_in_executor(None, _ping, host, int(timeout))

    reachable = bool(dns_ip) and tcp_ok
    result: dict[str, Any] = {
        "stage": "wan",
        "target": host,
        "dns_host": dns_host,
        "dns_resolved": dns_ip,
        "tcp_connect": tcp_ok,
        "icmp_ping": icmp_ok,
        "reachable": reachable,
        "mode": mode,
    }

    if reachable:
        logger.info(
            "WAN OK: DNS=%s TCP=%s ICMP=%s", dns_ip, tcp_ok, icmp_ok,
            extra={"action": "health", "step": "wan_ok"},
        )
    else:
        log_fn = logger.error if mode == "hard" else logger.warning
        log_fn(
            "WAN %s: DNS=%s TCP=%s ICMP=%s",
            "FAIL" if mode == "hard" else "WARN",
            dns_ip, tcp_ok, icmp_ok,
            extra={"action": "health", "step": "wan_fail"},
        )
    return result


# ------------------------------------------------------------------
# Combined 3-stage check
# ------------------------------------------------------------------

async def full_health_check(
    control_target: str = "192.168.22.100",
    router_control_url: str = "http://192.168.22.100:8081",
    check_router: bool = True,
    router_timeout: float = 120.0,
    check_wan_connectivity: bool = True,
    wan_check_mode: WanCheckMode = "soft",
) -> dict[str, Any]:
    """Run the 3-stage health check in order.

    Returns a dict with ``healthy`` (bool) and per-stage results.
    ``healthy`` is True only if Stage 1 and Stage 2 pass.
    Stage 3 obeys *wan_check_mode*: "hard" makes it a gate, "soft"
    (default) makes it advisory, "skip" skips it entirely.
    """
    results: dict[str, Any] = {"healthy": False, "stages": {}}

    # Stage 1 -- hard gate
    stage1 = await check_control_path(control_target)
    results["stages"]["control_path"] = stage1
    if not stage1["reachable"]:
        return results

    # Stage 2 -- hard gate
    if check_router:
        stage2 = await check_router_via_service(router_control_url, timeout=router_timeout)
        results["stages"]["router"] = stage2
        if not stage2.get("online"):
            return results
    else:
        results["stages"]["router"] = {"stage": "router", "online": None, "skipped": True}

    # Stage 3 -- configurable
    if check_wan_connectivity:
        stage3 = await check_wan(mode=wan_check_mode)
        results["stages"]["wan"] = stage3
        if wan_check_mode == "hard" and not stage3.get("reachable"):
            return results
    else:
        results["stages"]["wan"] = {"stage": "wan", "reachable": None, "skipped": True}

    results["healthy"] = True
    return results


async def preflight_check(
    control_target: str = "192.168.22.100",
) -> bool:
    """Quick pre-flight: just verify the control path is alive.

    Call this before every dangerous operation.  Returns True if safe
    to proceed.
    """
    result = await check_control_path(control_target)
    return result["reachable"]
