"""Unit tests for health gating and rollback in step_router_apply.

Uses mocking to simulate service endpoints without real network access.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest import mock

import pytest

from orchestrator.utils.health import full_health_check, check_wan


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_health_check_stage1_fail():
    """If Stage 1 (control path) fails, healthy=False and we stop early."""
    with mock.patch("orchestrator.utils.health._ping", return_value=False):
        result = await full_health_check(
            control_target="192.168.22.100",
            router_control_url="http://192.168.22.100:8081",
            check_router=False,
            check_wan_connectivity=False,
        )
    assert result["healthy"] is False
    assert result["stages"]["control_path"]["reachable"] is False


@pytest.mark.asyncio
async def test_full_health_check_wan_soft_mode():
    """In soft mode, WAN failure does not block healthy=True."""
    with mock.patch("orchestrator.utils.health._ping", return_value=True), \
         mock.patch("orchestrator.utils.health._dns_resolve", return_value=None), \
         mock.patch("orchestrator.utils.health._tcp_connect", return_value=False):

        result = await full_health_check(
            control_target="192.168.22.100",
            router_control_url="http://192.168.22.100:8081",
            check_router=False,
            check_wan_connectivity=True,
            wan_check_mode="soft",
        )
    assert result["healthy"] is True
    assert result["stages"]["wan"]["reachable"] is False
    assert result["stages"]["wan"]["mode"] == "soft"


@pytest.mark.asyncio
async def test_full_health_check_wan_hard_mode():
    """In hard mode, WAN failure blocks healthy=True."""
    with mock.patch("orchestrator.utils.health._ping", return_value=True), \
         mock.patch("orchestrator.utils.health._dns_resolve", return_value=None), \
         mock.patch("orchestrator.utils.health._tcp_connect", return_value=False):

        result = await full_health_check(
            control_target="192.168.22.100",
            router_control_url="http://192.168.22.100:8081",
            check_router=False,
            check_wan_connectivity=True,
            wan_check_mode="hard",
        )
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_check_wan_skip_mode():
    """Skip mode returns immediately with no checks."""
    result = await check_wan(mode="skip")
    assert result["skipped"] is True
    assert result["reachable"] is None


# ---------------------------------------------------------------------------
# Rollback behavior tests (step_router_apply)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_router_apply_rollback_on_health_fail():
    """Verify that step_router_apply triggers rollback when post-flight fails."""
    from orchestrator.actions.e2e_steps import step_router_apply
    from orchestrator.workflow_schema import RouterConfig, BandWifiConfig

    baseline_bands = {
        "2.4G": {"ssid": "Original2G", "passphrase": "pass2g", "channel": "1", "security": "WPA2-PSK"},
        "5G": {"ssid": "Original5G", "passphrase": "pass5g", "channel": "36", "security": "WPA2-PSK"},
    }

    router_cfg = RouterConfig(
        base_url="http://192.168.1.1",
        router_control_url="http://192.168.22.100:8081",
        bands={
            "2.4G": BandWifiConfig(ssid="Test2G", password="test2g"),
            "5G": BandWifiConfig(ssid="Test5G", password="test5g"),
        },
    )

    async def fake_apply(*args, **kwargs):
        return {"success": True, "configured_bands": ["2.4G", "5G"]}

    health_fail = {
        "healthy": False,
        "stages": {
            "control_path": {"reachable": True},
            "router": {"online": False, "error": "timeout"},
        },
    }
    baseline_result = {"success": True, "bands": baseline_bands}

    with mock.patch("orchestrator.actions.e2e_steps.preflight_check", return_value=True), \
         mock.patch("orchestrator.actions.e2e_steps.check_router_status", return_value=baseline_result), \
         mock.patch("orchestrator.actions.e2e_steps.apply_router_settings", side_effect=fake_apply) as mock_apply, \
         mock.patch("orchestrator.actions.e2e_steps.full_health_check", return_value=health_fail), \
         mock.patch("orchestrator.actions.e2e_steps._save_artifact"):

        result = await step_router_apply(router_cfg, "admin", "pass")

    assert result["success"] is False
    assert "rollback" in result
    assert result["rollback"]["success"] is True
    assert mock_apply.call_count == 2


@pytest.mark.asyncio
async def test_step_router_apply_no_rollback_on_success():
    """Verify that successful apply does NOT trigger rollback."""
    from orchestrator.actions.e2e_steps import step_router_apply
    from orchestrator.workflow_schema import RouterConfig, BandWifiConfig

    baseline_bands = {
        "2.4G": {"ssid": "Original2G", "passphrase": "pass2g", "channel": "1", "security": "WPA2-PSK"},
    }

    router_cfg = RouterConfig(
        base_url="http://192.168.1.1",
        router_control_url="http://192.168.22.100:8081",
        bands={"2.4G": BandWifiConfig(ssid="Test2G", password="test2g")},
    )

    async def fake_apply(*args, **kwargs):
        return {"success": True, "configured_bands": ["2.4G"]}

    health_ok = {
        "healthy": True,
        "stages": {
            "control_path": {"reachable": True},
            "router": {"online": True},
            "wan": {"reachable": True},
        },
    }
    baseline_result = {"success": True, "bands": baseline_bands}

    with mock.patch("orchestrator.actions.e2e_steps.preflight_check", return_value=True), \
         mock.patch("orchestrator.actions.e2e_steps.check_router_status", return_value=baseline_result), \
         mock.patch("orchestrator.actions.e2e_steps.apply_router_settings", side_effect=fake_apply) as mock_apply, \
         mock.patch("orchestrator.actions.e2e_steps.full_health_check", return_value=health_ok), \
         mock.patch("orchestrator.actions.e2e_steps._save_artifact"):

        result = await step_router_apply(router_cfg, "admin", "pass")

    assert result["success"] is True
    assert "rollback" not in result
    assert mock_apply.call_count == 1
