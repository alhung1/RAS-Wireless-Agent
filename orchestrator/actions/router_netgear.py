"""Orchestrator-facing router control — calls the remote router-control
service on 22.100 instead of running Playwright locally (Layer 4).

The orchestrator never touches the 192.168.1.x subnet.  All router
operations are proxied through the ``router_control_url`` HTTP API.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from orchestrator.logging.json_logger import get_logger
from orchestrator.utils.retry import retry_async
from router.netgear_nighthawk.selectors import BandConfig

logger = get_logger("router_netgear")

HTTP_TIMEOUT = 180.0
CONNECT_TIMEOUT = 10.0


async def detect_router_bands(
    router_control_url: str,
    router_base_url: str = "http://192.168.1.1",
    user: Optional[str] = None,
    password: Optional[str] = None,
    artifacts_dir: str = "artifacts",
) -> list[str]:
    """Ask the router-control service which bands the router supports.

    This is a read-only call -- no settings are changed.
    """
    if not router_control_url:
        raise ValueError(
            "router_control_url is required. The orchestrator must never "
            "run Playwright directly -- all router operations go through "
            "the remote router-control service."
        )
    url = f"{router_control_url.rstrip('/')}/router/detect-bands"
    payload = {"base_url": router_base_url}
    if user:
        payload["router_user"] = user
    if password:
        payload["router_pass"] = password

    async def _do():
        async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT, connect=CONNECT_TIMEOUT)) as client:
            resp = await client.post(url, params=payload)
            resp.raise_for_status()
            return resp.json()

    result = await retry_async(_do, max_retries=2, backoff=3.0, timeout=HTTP_TIMEOUT + 30)

    if not result.get("success"):
        raise RuntimeError(f"Band detection failed via service: {result.get('error')}")

    bands = result.get("bands", [])
    logger.info(
        "Router band detection via service: %s", bands,
        extra={"action": "detect_bands", "step": "done"},
    )
    return bands


async def apply_router_settings(
    router_control_url: str,
    router_base_url: str = "http://192.168.1.1",
    user: str = "admin",
    password: str = "",
    band_configs: dict[str, BandConfig] | None = None,
    artifacts_dir: str = "artifacts",
) -> dict[str, Any]:
    """Send router configuration to the router-control service on 22.100.

    The service runs Playwright locally against the router LAN.
    The orchestrator only sends HTTP over the safe 22.x network.
    """
    if not router_control_url:
        raise ValueError(
            "router_control_url is required. The orchestrator must never "
            "run Playwright directly -- all router operations go through "
            "the remote router-control service."
        )
    url = f"{router_control_url.rstrip('/')}/router/apply"

    bands_payload: dict[str, dict] = {}
    for band_key, cfg in (band_configs or {}).items():
        bands_payload[band_key] = {
            "ssid": cfg.ssid,
            "password": cfg.password,
            "channel": cfg.channel,
            "security": cfg.security,
        }

    payload = {
        "base_url": router_base_url,
        "bands": bands_payload,
        "router_user": user,
        "router_pass": password,
    }

    logger.info(
        "Sending router apply to service at %s", router_control_url,
        extra={"action": "apply_router", "step": "request"},
    )

    async def _do():
        async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT, connect=CONNECT_TIMEOUT)) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    try:
        result = await retry_async(_do, max_retries=2, backoff=5.0, timeout=HTTP_TIMEOUT + 60)
    except Exception as exc:
        logger.error("Router apply via service failed: %s", exc,
                     extra={"action": "apply_router", "step": "error"})
        return {"success": False, "step": "apply_router", "error": str(exc)}

    success = result.get("success", False)
    if success:
        logger.info("Router settings applied via service",
                     extra={"action": "apply_router", "step": "done"})
    else:
        logger.error("Router apply returned failure: %s", result.get("error"),
                     extra={"action": "apply_router", "step": "fail"})

    return {
        "success": success,
        "step": "apply_router",
        "detected_bands": result.get("detected_bands", []),
        "configured_bands": result.get("configured_bands", []),
        "error": result.get("error"),
    }
