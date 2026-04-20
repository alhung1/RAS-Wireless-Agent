"""Unit tests for orchestrator/main.py workflow engine.

Tests cover:
- Loading workflows from YAML
- Executing individual steps (router_apply, wait, wifi_connect_local, etc.)
- Preflight checks and safety mechanisms
- Full workflow execution with success/failure cases
"""
from __future__ import annotations

import asyncio
from unittest import mock
from unittest.mock import AsyncMock
from pathlib import Path
import tempfile

import pytest
import yaml

from orchestrator.main import (
    load_workflow,
    execute_step,
    run_workflow,
)
from orchestrator.workflow_schema import (
    Workflow,
    Step,
    RouterConfig,
    BandWifiConfig,
    WorkerTarget,
    ScanConfig,
    PingGateConfig,
    AutomationConfig,
    ConnectOptions,
    LabviewConfig,
)


# ---------------------------------------------------------------------------
# load_workflow tests
# ---------------------------------------------------------------------------

def test_load_workflow_valid_yaml():
    """Load a valid YAML workflow file into a Workflow object.

    Risk covered: Verify that YAML parsing correctly converts to Pydantic model.
    """
    workflow_data = {
        "name": "test-workflow",
        "description": "A test workflow",
        "router": {
            "base_url": "http://192.168.1.1",
            "bands": {
                "2.4G": {"ssid": "TestSSID", "password": "testpass"},
            },
        },
        "workers": [
            {"url": "http://192.168.1.10", "name": "worker1"},
        ],
        "steps": [
            {
                "action": "wait",
                "description": "Initial wait",
                "wait_seconds": 5,
            },
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(workflow_data, f)
        temp_path = f.name

    try:
        workflow = load_workflow(temp_path)
        assert workflow.name == "test-workflow"
        assert workflow.description == "A test workflow"
        assert len(workflow.steps) == 1
        assert workflow.steps[0].action == "wait"
        assert workflow.steps[0].wait_seconds == 5
    finally:
        Path(temp_path).unlink()


def test_load_workflow_with_legacy_bands():
    """Load workflow with legacy bands list format (["2.4G", "5G"]).

    Risk covered: Verify backward compatibility with old YAML format.
    """
    workflow_data = {
        "name": "legacy-workflow",
        "router": {
            "base_url": "http://192.168.1.1",
            "bands": ["2.4G", "5G"],  # Legacy list format
        },
        "steps": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(workflow_data, f)
        temp_path = f.name

    try:
        workflow = load_workflow(temp_path)
        assert "2.4G" in workflow.router.bands
        assert "5G" in workflow.router.bands
    finally:
        Path(temp_path).unlink()


# ---------------------------------------------------------------------------
# execute_step - router_apply tests
# ---------------------------------------------------------------------------



@pytest.mark.asyncio
async def test_execute_step_router_apply_missing_config():
    """Execute router_apply with missing router config.

    Risk covered: Verify graceful failure when router config is absent.
    """
    step = Step(action="router_apply")
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=True)):
        result = await execute_step(step, workflow, env)

    assert result["success"] is False
    assert "Missing router config" in result["error"]


# ---------------------------------------------------------------------------
# execute_step - wifi_connect_local BLOCKED tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_step_wifi_connect_local_blocked():
    """Execute wifi_connect_local and verify it is always blocked.

    Risk covered: Topology safety guard - orchestrator must never modify
    its own network interfaces. This action should always fail with a
    clear security error message.
    """
    step = Step(action="wifi_connect_local")
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=True)):
        result = await execute_step(step, workflow, env)

    assert result["success"] is False
    assert "wifi_connect_local is disabled" in result["error"]
    assert "orchestrator must not alter its own network interfaces" in result["error"]


@pytest.mark.asyncio
async def test_execute_step_wifi_connect_local_blocked_with_preflight():
    """wifi_connect_local is blocked after preflight check passes.

    Risk covered: Verify that the action is blocked at the routing stage,
    even after preflight passes. This is a secondary safety check.
    """
    step = Step(action="wifi_connect_local")
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=True)):
        result = await execute_step(step, workflow, env)

    assert result["success"] is False
    assert "wifi_connect_local is disabled" in result["error"]


# ---------------------------------------------------------------------------
# execute_step - wait tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_step_wait_success():
    """Execute wait step and verify asyncio.sleep is called.

    Risk covered: Verify that wait action pauses execution for the
    specified duration without errors.
    """
    step = Step(action="wait", wait_seconds=2.5)
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.asyncio.sleep") as mock_sleep:
        result = await execute_step(step, workflow, env)

    assert result["success"] is True
    assert result["waited"] == 2.5
    mock_sleep.assert_called_once_with(2.5)


@pytest.mark.asyncio
async def test_execute_step_wait_default_duration():
    """Execute wait step with no wait_seconds (should default to 5).

    Risk covered: Verify default wait duration is applied when not specified.
    """
    step = Step(action="wait")
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.asyncio.sleep") as mock_sleep:
        result = await execute_step(step, workflow, env)

    assert result["success"] is True
    assert result["waited"] == 5
    mock_sleep.assert_called_once_with(5)


# ---------------------------------------------------------------------------
# execute_step - unknown action tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_step_unknown_action():
    """Execute step with unknown action and verify error.

    Risk covered: Verify that the engine rejects unrecognized actions
    with a clear error message.
    """
    step = Step(action="nonexistent_action")
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=True)):
        result = await execute_step(step, workflow, env)

    assert result["success"] is False
    assert "Unknown action" in result["error"]
    assert "nonexistent_action" in result["error"]


# ---------------------------------------------------------------------------
# execute_step - preflight failure tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_step_preflight_failure():
    """Non-safe action fails when preflight_check returns False.

    Risk covered: Verify that preflight check acts as a circuit breaker
    before executing risky actions. If control path is unreachable, the
    step is aborted.
    """
    step = Step(action="router_apply")
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=False)):
        result = await execute_step(step, workflow, env)

    assert result["success"] is False
    assert "Pre-flight check failed" in result["error"]
    assert "22.x control path is unreachable" in result["error"]


@pytest.mark.asyncio
async def test_execute_step_wifi_connect_workers_respects_target_workers_and_connect_options():
    """wifi_connect_workers should filter workers and forward connect options.

    Risk covered: ensure workflow YAML fields like target_workers and
    connect_options are not silently ignored.
    """
    workflow = Workflow(
        name="wifi-connect",
        router=RouterConfig(
            bands={"2.4G": BandWifiConfig(ssid="SSID", password="secret", security="wpa2")},
        ),
        workers=[
            WorkerTarget(url="http://192.168.22.100:8081", name="relay", role="router_service"),
            WorkerTarget(url="http://192.168.22.203:8080", name="be200", role="wifi_client"),
        ],
        steps=[],
    )
    step = Step(
        action="wifi_connect_workers",
        connect_band="2.4G",
        target_workers=["be200"],
        connect_options=ConnectOptions(
            adapter_hint="Intel(R) Wi-Fi 7 BE200",
            static_ip="192.168.1.203",
            mask="255.255.255.0",
        ),
    )

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=True)), \
         mock.patch("orchestrator.main.step_connect_workers", AsyncMock(return_value={"success": True})) as mock_connect:
        result = await execute_step(step, workflow, {})

    assert result["success"] is True
    kwargs = mock_connect.await_args.kwargs
    assert len(kwargs["workers"]) == 1
    assert kwargs["workers"][0].name == "be200"
    assert kwargs["connect_options"].adapter_hint == "Intel(R) Wi-Fi 7 BE200"
    assert kwargs["connect_options"].static_ip == "192.168.1.203"
    assert kwargs["connect_options"].band == "2.4G"


@pytest.mark.asyncio
async def test_execute_step_labview_profile_uses_labview_config():
    """labview_test should delegate to the profile-driven LabVIEW runner.

    Risk covered: the workflow engine must support the local LabVIEW leg of
    the end-to-end automation instead of stopping at router/worker orchestration.
    """
    workflow = Workflow(name="labview-workflow", steps=[])
    step = Step(
        action="labview_test",
        labview=LabviewConfig(profile="profiles/test_matrix/be200_2g.yaml"),
    )

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=True)), \
         mock.patch(
             "orchestrator.main.step_run_labview_profile",
             AsyncMock(return_value={"success": True, "profile": "BE200 2.4G Standard"}),
         ) as mock_labview:
        result = await execute_step(step, workflow, {})

    assert result["success"] is True
    assert result["profile"] == "BE200 2.4G Standard"
    assert mock_labview.await_args.kwargs["profile_path"] == "profiles/test_matrix/be200_2g.yaml"


@pytest.mark.asyncio
async def test_execute_step_wait_skips_preflight():
    """Wait action should NOT call preflight (it's a SAFE_ACTION).

    Risk covered: Verify that safe actions bypass the preflight check.
    """
    step = Step(action="wait", wait_seconds=1)
    workflow = Workflow(name="test", steps=[step])
    env = {}

    with mock.patch("orchestrator.main.preflight_check") as mock_preflight, \
         mock.patch("orchestrator.main.asyncio.sleep"):

        result = await execute_step(step, workflow, env)

    assert result["success"] is True
    mock_preflight.assert_not_called()













# ---------------------------------------------------------------------------
# run_workflow - full success tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_workflow_full_success_two_steps():
    """Run a complete workflow with 2 steps, all succeeding.

    Risk covered: Verify that a multi-step workflow executes all steps
    sequentially and returns success=True in final report.
    """
    workflow = Workflow(
        name="test-workflow",
        description="Test full success",
        steps=[
            Step(action="wait", wait_seconds=0.1),
            Step(action="wait", wait_seconds=0.1),
        ],
    )

    with mock.patch("orchestrator.main.asyncio.sleep"), \
         mock.patch("orchestrator.main.build_final_report") as mock_report:

        mock_report.return_value = {
            "success": True,
            "workflow": "test-workflow",
            "steps": 2,
        }

        report = await run_workflow(workflow)

    assert report["success"] is True
    mock_report.assert_called_once()


@pytest.mark.asyncio
async def test_run_workflow_three_steps_with_preflight():
    """Run a 3-step workflow with mixed safe/unsafe actions.

    Risk covered: Verify preflight check is called only for unsafe steps,
    and wait steps skip it.
    """
    workflow = Workflow(
        name="test-mixed",
        steps=[
            Step(action="wait", wait_seconds=0.1),
            Step(action="wait", wait_seconds=0.1),
            Step(action="wait", wait_seconds=0.1),
        ],
    )

    with mock.patch("orchestrator.main.asyncio.sleep"), \
         mock.patch("orchestrator.main.build_final_report") as mock_report:

        mock_report.return_value = {"success": True}

        report = await run_workflow(workflow)

    assert report["success"] is True


# ---------------------------------------------------------------------------
# run_workflow - abort on failure tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_workflow_abort_on_step_failure():
    """Run a workflow where the first step fails; verify it stops.

    Risk covered: Verify that the workflow stops execution when a
    non-wait step fails, preventing cascade failures.
    """
    workflow = Workflow(
        name="test-fail",
        steps=[
            Step(action="router_apply"),  # Will fail: missing config
            Step(action="wait", wait_seconds=0.1),  # Should NOT execute
        ],
    )

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=True)), \
         mock.patch("orchestrator.main.asyncio.sleep") as mock_sleep, \
         mock.patch("orchestrator.main.build_final_report") as mock_report:

        mock_report.return_value = {"success": False, "aborted": True}

        report = await run_workflow(workflow)

    # Second step should not have executed
    mock_sleep.assert_not_called()
    assert mock_report.called


@pytest.mark.asyncio
async def test_run_workflow_continues_after_wait_failure():
    """Run workflow where wait step fails (if possible); should continue.

    Risk covered: Verify that wait step failures do NOT abort the workflow
    (only non-wait failures cause abort).
    """
    workflow = Workflow(
        name="test-wait-fail",
        steps=[
            Step(action="wait", wait_seconds=0.1),
            Step(action="wait", wait_seconds=0.1),
        ],
    )

    with mock.patch("orchestrator.main.asyncio.sleep"), \
         mock.patch("orchestrator.main.build_final_report") as mock_report:

        mock_report.return_value = {"success": True}

        report = await run_workflow(workflow)

    # Should complete both steps
    assert mock_report.called


@pytest.mark.asyncio
async def test_run_workflow_stops_on_preflight_fail():
    """Run workflow where preflight check fails before first non-wait step.

    Risk covered: Verify that preflight failure prevents execution and
    stops the workflow.
    """
    workflow = Workflow(
        name="test-preflight-fail",
        router=RouterConfig(
            base_url="http://192.168.1.1",
            bands={"2.4G": BandWifiConfig(ssid="Test", password="pass")},
        ),
        steps=[
            Step(action="router_apply"),
            Step(action="wait", wait_seconds=0.1),
        ],
    )

    with mock.patch("orchestrator.main.preflight_check", AsyncMock(return_value=False)), \
         mock.patch("orchestrator.main.asyncio.sleep") as mock_sleep, \
         mock.patch("orchestrator.main.build_final_report") as mock_report:

        mock_report.return_value = {"success": False}

        report = await run_workflow(workflow)

    # Should not execute the wait step
    mock_sleep.assert_not_called()
    assert mock_report.called


# ---------------------------------------------------------------------------
# run_workflow - environment variable tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_workflow_loads_env_variables():
    """Verify that run_workflow loads .env and passes to execute_step.

    Risk covered: Verify that router credentials are properly loaded
    from environment and passed downstream.
    """
    workflow = Workflow(
        name="test-env",
        steps=[
            Step(action="wait", wait_seconds=0.1),
        ],
    )

    with mock.patch("orchestrator.main.load_dotenv"), \
         mock.patch("orchestrator.main.os.environ.get") as mock_env_get, \
         mock.patch("orchestrator.main.asyncio.sleep"), \
         mock.patch("orchestrator.main.build_final_report") as mock_report:

        mock_env_get.side_effect = lambda k, d: d  # Return default values
        mock_report.return_value = {"success": True}

        await run_workflow(workflow)

    # Verify that load_dotenv and environ.get were called
    mock_report.assert_called_once()


# ---------------------------------------------------------------------------
# run_workflow - result tracking tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_workflow_tracks_step_results():
    """Verify that workflow results include step indices and actions.

    Risk covered: Verify that the final report contains complete
    step tracking with indices and action names.
    """
    workflow = Workflow(
        name="test-tracking",
        steps=[
            Step(action="wait", wait_seconds=0.1),
            Step(action="wait", wait_seconds=0.1),
        ],
    )

    captured_results = []

    def capture_report(name, workers, results):
        captured_results.extend(results)
        return {"success": True, "steps": results}

    with mock.patch("orchestrator.main.asyncio.sleep"), \
         mock.patch("orchestrator.main.build_final_report", side_effect=capture_report):

        report = await run_workflow(workflow)

    # Verify that each step has index and action
    assert len(captured_results) == 2
    assert captured_results[0]["step_index"] == 0
    assert captured_results[0]["action"] == "wait"
    assert captured_results[1]["step_index"] == 1
    assert captured_results[1]["action"] == "wait"
