"""Matrix inter-profile handoff: finish detection + readiness for next profile.

This module provides:
  - ProfilePhase enum for fine-grained matrix orchestration states
  - HandoffResult dataclass capturing finish + readiness outcome
  - BetweenProfilesHook protocol and implementations (noop, assert_main, restart)
  - run_finish_and_handoff() orchestration function

**Skeleton status:** The orchestration flow and data structures are complete.
Live integration (actual wait_for_finish, WindowManager, subprocess restart)
requires a Windows environment with LabVIEW. Each hook's live code path is
clearly marked with ``# LIVE INTEGRATION`` comments.
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from orchestrator.logging.json_logger import get_logger

logger = get_logger("handoff")


class ProfilePhase(str, enum.Enum):
    """Fine-grained phase tracking for each profile in a matrix run.

    These phases represent the lifecycle of a single profile within
    the matrix, from start to readiness for the next profile.
    """
    PROFILE_STARTED = "profile_started"
    PROFILE_ENGINE_PASSED = "profile_engine_passed"
    WAITING_FOR_FINISH = "waiting_for_finish"
    FINISH_PASS = "finish_pass"
    FINISH_TIMEOUT = "finish_timeout"
    FINISH_ARTIFACTS_MISSING = "finish_artifacts_missing"
    RESTART_REQUIRED = "restart_required"
    READY_FOR_NEXT_PROFILE = "ready_for_next_profile"
    HANDOFF_FAILED = "handoff_failed"
    MATRIX_ABORTED = "matrix_aborted"


@dataclass
class HandoffResult:
    """Outcome of the finish-wait + between-profiles handoff for one profile."""
    phase: ProfilePhase = ProfilePhase.PROFILE_STARTED
    finish_method: str = ""
    finish_elapsed_sec: float = 0.0
    finish_detail: str = ""
    finish_timed_out: bool = False
    finish_failed_fast: bool = False
    restart_performed: bool = False
    restart_success: bool = False
    ready_for_next: bool = False
    error: str = ""
    simulated: bool = False

    def to_dict(self) -> dict:
        d = {
            "phase": self.phase.value,
            "ready_for_next": self.ready_for_next,
        }
        if self.finish_method:
            d["finish_method"] = self.finish_method
            d["finish_elapsed_sec"] = round(self.finish_elapsed_sec, 1)
        if self.finish_detail:
            d["finish_detail"] = self.finish_detail
        if self.finish_timed_out:
            d["finish_timed_out"] = True
        if self.finish_failed_fast:
            d["finish_failed_fast"] = True
        if self.restart_performed:
            d["restart_performed"] = True
            d["restart_success"] = self.restart_success
        if self.error:
            d["error"] = self.error
        if self.simulated:
            d["simulated"] = True
        return d


# ---------------------------------------------------------------------------
# Between-profiles hook protocol and implementations
# ---------------------------------------------------------------------------

class BetweenProfilesHook(Protocol):
    """Callable that ensures LabVIEW is ready for the next profile."""

    def __call__(
        self,
        previous_artifacts_dir: str,
        next_profile_name: str,
        dry_run: bool = False,
    ) -> tuple[bool, str]:
        """Return (success, detail_message)."""
        ...


def noop_hook(
    previous_artifacts_dir: str,
    next_profile_name: str,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """No-op hook — always reports ready. Use for dry-run or single-profile."""
    return True, "noop"


def assert_main_screen_hook(
    previous_artifacts_dir: str,
    next_profile_name: str,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Check that LabVIEW is on the main screen (480 000.vi).

    In dry-run mode, returns simulated success.

    LIVE INTEGRATION: requires WindowManager.find_window() on Windows.
    """
    if dry_run:
        return True, "simulated: main screen check skipped (dry-run)"

    # LIVE INTEGRATION -- uncomment when running on 22.8 with LabVIEW:
    # from orchestrator.local_automation.ui.window_manager import WindowManager
    # wm = WindowManager()
    # hwnd = wm.find_window()
    # if hwnd:
    #     return True, f"main screen found (hwnd={hwnd})"
    # return False, "main screen not found"

    return False, "assert_main_screen requires live Windows environment"


def restart_labview_hook(
    previous_artifacts_dir: str,
    next_profile_name: str,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Kill and restart the LabVIEW executable, then verify main screen.

    In dry-run mode, returns simulated success.

    LIVE INTEGRATION: requires subprocess + WindowManager on Windows.
    """
    if dry_run:
        return True, "simulated: restart skipped (dry-run)"

    # LIVE INTEGRATION -- uncomment when running on 22.8:
    # import subprocess
    # from orchestrator.local_automation.ui.window_manager import WindowManager
    #
    # # Kill existing LabVIEW
    # subprocess.run(["taskkill", "/f", "/im", "480.000.v2.03.exe"],
    #                capture_output=True)
    # time.sleep(3)
    #
    # # Launch new instance
    # subprocess.Popen([run_config.exe_path], shell=False)
    # time.sleep(10)
    #
    # # Verify main window
    # wm = WindowManager()
    # hwnd = wm.find_window(retries=5, interval=3)
    # if hwnd:
    #     return True, f"restart OK (hwnd={hwnd})"
    # return False, "restart failed: main window not found"

    return False, "restart_labview requires live Windows environment"


# Hook registry
HOOK_REGISTRY: dict[str, BetweenProfilesHook] = {
    "noop": noop_hook,
    "assert_main_screen": assert_main_screen_hook,
    "restart": restart_labview_hook,
}


def get_hook(name: str) -> BetweenProfilesHook:
    """Look up a between-profiles hook by name."""
    if name not in HOOK_REGISTRY:
        raise ValueError(
            f"Unknown between_profiles hook: {name!r} "
            f"(available: {list(HOOK_REGISTRY.keys())})"
        )
    return HOOK_REGISTRY[name]


# ---------------------------------------------------------------------------
# Orchestration: finish wait + handoff
# ---------------------------------------------------------------------------

def run_finish_and_handoff(
    *,
    profile_name: str,
    artifacts_dir: str,
    wait_for_finish_enabled: bool,
    finish_config: Any = None,
    initial_files: Optional[set[str]] = None,
    between_hook_name: str = "noop",
    next_profile_name: str = "",
    dry_run: bool = False,
) -> HandoffResult:
    """Run the finish-wait + between-profiles handoff for one profile.

    This is the main entry point called by matrix_runner after engine.run()
    succeeds for a given profile.

    Args:
        profile_name: Current profile being finished.
        artifacts_dir: Artifact directory for this profile run.
        wait_for_finish_enabled: Whether to call wait_for_finish.
        finish_config: FinishConfig instance (from finish_detector module).
        initial_files: Files present before the test started.
        between_hook_name: Hook name from HOOK_REGISTRY.
        next_profile_name: Name of the next profile (empty if last).
        dry_run: If True, simulate all steps.

    Returns:
        HandoffResult with final phase and details.
    """
    result = HandoffResult()

    if dry_run:
        result.simulated = True

    # Phase 1: Engine already passed (caller responsibility)
    result.phase = ProfilePhase.PROFILE_ENGINE_PASSED

    # Phase 2: Wait for finish (if enabled)
    if wait_for_finish_enabled:
        result.phase = ProfilePhase.WAITING_FOR_FINISH
        logger.info(
            "Waiting for finish: %s (dry_run=%s)",
            profile_name, dry_run,
            extra={"action": "handoff", "step": "finish_wait"},
        )

        if dry_run:
            result.phase = ProfilePhase.FINISH_PASS
            result.finish_method = "simulated"
            result.finish_detail = "dry-run: finish wait skipped"
            result.finish_elapsed_sec = 0.0
        else:
            # LIVE INTEGRATION:
            # from orchestrator.local_automation.finish_detector import (
            #     wait_for_finish, FinishConfig,
            # )
            # finish_result = wait_for_finish(finish_config, artifacts_dir, initial_files)
            #
            # result.finish_method = finish_result.method
            # result.finish_elapsed_sec = finish_result.elapsed_sec
            # result.finish_detail = finish_result.detail
            # result.finish_timed_out = finish_result.timed_out
            # result.finish_failed_fast = finish_result.failed_fast
            #
            # if finish_result.timed_out:
            #     result.phase = ProfilePhase.FINISH_TIMEOUT
            # elif finish_result.finished:
            #     result.phase = ProfilePhase.FINISH_PASS
            # else:
            #     result.phase = ProfilePhase.FINISH_ARTIFACTS_MISSING

            result.phase = ProfilePhase.FINISH_PASS
            result.finish_method = "not_integrated"
            result.finish_detail = "live finish detection not yet integrated"
    else:
        # No finish wait requested — treat engine pass as finish pass
        result.phase = ProfilePhase.FINISH_PASS
        result.finish_method = "skipped"
        result.finish_detail = "finish wait not enabled for this profile"

    # Phase 3: Between-profiles hook (if there's a next profile)
    if next_profile_name and result.phase == ProfilePhase.FINISH_PASS:
        hook = get_hook(between_hook_name)
        logger.info(
            "Between-profiles hook '%s': %s -> %s",
            between_hook_name, profile_name, next_profile_name,
            extra={"action": "handoff", "step": "between_hook"},
        )

        hook_ok, hook_detail = hook(artifacts_dir, next_profile_name, dry_run=dry_run)
        if hook_ok:
            result.phase = ProfilePhase.READY_FOR_NEXT_PROFILE
            result.ready_for_next = True
        else:
            # Hook failed — may need restart
            if between_hook_name != "restart":
                result.phase = ProfilePhase.RESTART_REQUIRED
                result.error = f"Hook '{between_hook_name}' failed: {hook_detail}"
            else:
                result.phase = ProfilePhase.HANDOFF_FAILED
                result.restart_performed = True
                result.restart_success = False
                result.error = f"Restart failed: {hook_detail}"
    elif result.phase == ProfilePhase.FINISH_PASS:
        # Last profile — no handoff needed
        result.phase = ProfilePhase.READY_FOR_NEXT_PROFILE
        result.ready_for_next = True
    else:
        # Finish failed — abort
        if result.finish_timed_out:
            result.error = f"Finish timed out for {profile_name}"
        result.ready_for_next = False

    logger.info(
        "Handoff complete: %s -> phase=%s ready=%s",
        profile_name, result.phase.value, result.ready_for_next,
        extra={"action": "handoff", "step": "done"},
    )

    return result
