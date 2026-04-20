"""Orchestrator workflow engine.

Reads a YAML workflow definition, executes steps sequentially, and writes
a final report to ``artifacts/final_report.json``.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import yaml
from dotenv import load_dotenv

from orchestrator.logging.json_logger import get_logger
from orchestrator.workflow_schema import Workflow, Step
from orchestrator.actions import wifi_remote
from orchestrator.actions.e2e_steps import (
    step_router_apply,
    step_wait_ssid_broadcast,
    step_connect_workers,
    step_ping_gate,
    step_run_automation,
    step_run_labview_profile,
    step_run_labview_test,
    build_final_report,
)
from orchestrator.utils.health import preflight_check
from orchestrator.workflow_schema import (
    PingGateConfig,
    ScanConfig,
    AutomationConfig,
    ConnectOptions,
    LabviewConfig,
    WorkerTarget,
)

logger = get_logger("orchestrator")


def load_workflow(path: str) -> Workflow:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Workflow(**data)


SAFE_ACTIONS = {"wait"}


def _select_workers(
    step: Step,
    workflow: Workflow,
) -> list[WorkerTarget]:
    """Resolve the effective worker list for a step.

    Priority:
      1. Inline ``step.workers``
      2. Workflow-level ``workers``
      3. Optional ``target_workers`` filter applied to the chosen list

    ``target_workers`` may contain worker URLs, names, or roles.
    """
    workers = list(step.workers or workflow.workers or [])
    if not workers or not step.target_workers:
        return workers

    selectors = {s.lower() for s in step.target_workers}
    selected: list[WorkerTarget] = []
    for worker in workers:
        candidates = {worker.url.lower()}
        if worker.name:
            candidates.add(worker.name.lower())
        if worker.role:
            candidates.add(worker.role.lower())
        if selectors & candidates:
            selected.append(worker)
    return selected


async def _execute_labview_step(
    cfg: LabviewConfig,
    artifacts_dir: str = "artifacts",
) -> dict[str, Any]:
    if cfg.profile:
        return await step_run_labview_profile(
            profile_path=cfg.profile,
            profiles_root=cfg.profiles_root,
            artifacts_dir=artifacts_dir,
        )

    if not cfg.band:
        return {
            "success": False,
            "error": "LabVIEW config requires either 'profile' or 'band'",
        }

    return await step_run_labview_test(
        band=cfg.band,
        rf_channels=cfg.rf_channels,
        user_information=cfg.user_information,
        timeout_seconds=cfg.timeout_seconds,
        finish_config=cfg.finish_config,
        artifacts_dir=artifacts_dir,
    )


async def execute_step(
    step: Step,
    workflow: Workflow,
    env: dict[str, str],
) -> dict[str, Any]:
    logger.info(
        "Executing step: %s (%s)", step.action, step.description or "",
        extra={"action": "execute_step", "step": step.action},
    )

    if step.action not in SAFE_ACTIONS:
        if not await preflight_check():
            logger.error(
                "Pre-flight FAILED before step %s — 22.x control path unreachable",
                step.action,
                extra={"action": "preflight", "step": step.action},
            )
            return {
                "success": False,
                "error": (
                    f"Pre-flight check failed before '{step.action}': "
                    "22.x control path is unreachable. Aborting."
                ),
            }

    # ------------------------------------------------------------------
    # router_apply -- via remote router-control service
    # ------------------------------------------------------------------
    if step.action == "router_apply":
        router_cfg = step.router or workflow.router
        if not router_cfg or not router_cfg.bands:
            return {"success": False, "error": "Missing router config or bands"}
        return await step_router_apply(
            router_cfg=router_cfg,
            router_user=env.get("ROUTER_USER", "admin"),
            router_pass=env.get("ROUTER_PASS", ""),
        )

    # ------------------------------------------------------------------
    # wait_ssid_broadcast -- scan workers until SSID visible
    # ------------------------------------------------------------------
    elif step.action == "wait_ssid_broadcast":
        workers = _select_workers(step, workflow)
        if not workers:
            return {"success": False, "error": "No workers configured"}
        scan_cfg = step.scan or ScanConfig(target_ssid="RFLabTest")
        return await step_wait_ssid_broadcast(workers, scan_cfg)

    # ------------------------------------------------------------------
    # wifi_connect_workers -- parallel Wi-Fi connect on all workers
    # ------------------------------------------------------------------
    elif step.action == "wifi_connect_workers":
        workers = _select_workers(step, workflow)
        router_cfg = step.router or workflow.router
        if not workers or not router_cfg:
            return {"success": False, "error": "Missing workers or router config"}
        band_key = step.connect_band or "2.4G"
        band = router_cfg.bands.get(band_key)
        if not band:
            return {"success": False, "error": f"Band {band_key} not in router config"}
        connect_options = step.connect_options or ConnectOptions(band=band_key)
        if not connect_options.band:
            connect_options.band = band_key
        return await step_connect_workers(
            workers=workers,
            ssid=band.ssid,
            password=band.password,
            security=band.security,
            connect_options=connect_options,
        )

    # ------------------------------------------------------------------
    # ping_gate -- all workers must reach target host
    # ------------------------------------------------------------------
    elif step.action == "ping_gate":
        workers = _select_workers(step, workflow)
        if not workers:
            return {"success": False, "error": "No workers configured"}
        ping_cfg = step.ping_gate or PingGateConfig()
        return await step_ping_gate(workers, ping_cfg)

    # ------------------------------------------------------------------
    # run_automation -- launch and poll automation jobs
    # ------------------------------------------------------------------
    elif step.action == "run_automation":
        workers = _select_workers(step, workflow)
        if not workers:
            return {"success": False, "error": "No workers configured"}
        auto_cfg = step.automation
        if not auto_cfg:
            return {"success": False, "error": "Missing automation config"}
        return await step_run_automation(workers, auto_cfg)

    # ------------------------------------------------------------------
    # LabVIEW local automation
    # ------------------------------------------------------------------
    elif step.action in {"labview_test", "run_labview_test"}:
        labview_cfg = step.labview or workflow.labview
        if not labview_cfg:
            return {"success": False, "error": "Missing LabVIEW config"}
        return await _execute_labview_step(
            labview_cfg,
            artifacts_dir=os.path.join("artifacts", "workflow_labview"),
        )

    # ------------------------------------------------------------------
    # Legacy: wifi_connect_remote
    # ------------------------------------------------------------------
    elif step.action == "wifi_connect_remote":
        wifi_cfg = step.wifi or workflow.wifi
        workers = _select_workers(step, workflow)
        if not wifi_cfg or not workers:
            return {"success": False, "error": "Missing wifi or workers config"}
        worker_urls = [w.url for w in workers]
        return await wifi_remote.connect_multiple(
            worker_urls, wifi_cfg.ssid, wifi_cfg.password, wifi_cfg.interface,
        )

    # ------------------------------------------------------------------
    # BLOCKED: wifi_connect_local -- topology safety guard
    # ------------------------------------------------------------------
    elif step.action == "wifi_connect_local":
        logger.error(
            "wifi_connect_local is DISABLED: orchestrator must never change "
            "its own Wi-Fi or routing table. Use worker endpoints instead.",
            extra={"action": "safety_block", "step": "wifi_connect_local"},
        )
        return {
            "success": False,
            "error": (
                "wifi_connect_local is disabled. The orchestrator must not "
                "alter its own network interfaces. All Wi-Fi operations must "
                "be performed on remote workers via their HTTP API."
            ),
        }

    # ------------------------------------------------------------------
    # wait -- simple delay
    # ------------------------------------------------------------------
    elif step.action == "wait":
        seconds = step.wait_seconds or 5
        logger.info("Waiting %.1f seconds", seconds, extra={"action": "wait", "step": "sleeping"})
        await asyncio.sleep(seconds)
        return {"success": True, "waited": seconds}

    else:
        return {"success": False, "error": f"Unknown action: {step.action}"}


async def run_workflow(workflow: Workflow) -> dict[str, Any]:
    load_dotenv()
    env = {
        "ROUTER_USER": os.environ.get("ROUTER_USER", "admin"),
        "ROUTER_PASS": os.environ.get("ROUTER_PASS", ""),
    }

    step_results: list[dict[str, Any]] = []
    overall_success = True

    for i, step in enumerate(workflow.steps):
        logger.info(
            "Step %d/%d: %s", i + 1, len(workflow.steps), step.action,
            extra={"action": "run_workflow", "step": f"step_{i + 1}"},
        )
        result = await execute_step(step, workflow, env)
        result["step_index"] = i
        result["action"] = step.action
        step_results.append(result)

        if not result.get("success", False) and step.action != "wait":
            overall_success = False
            logger.error(
                "Step %d (%s) failed, stopping workflow", i + 1, step.action,
                extra={"action": "run_workflow", "step": "abort"},
            )
            break

    workers = workflow.workers or []
    report = build_final_report(workflow.name, workers, step_results)
    return report


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m orchestrator.main <workflow.yaml>")
        sys.exit(1)

    workflow_path = sys.argv[1]
    workflow = load_workflow(workflow_path)
    report = asyncio.run(run_workflow(workflow))

    print(json.dumps(report, indent=2, default=str))
    sys.exit(0 if report.get("success") else 1)


if __name__ == "__main__":
    main()
