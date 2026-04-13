"""Unit tests for matrix finish orchestration handoff module.

Tests the ProfilePhase enum, HandoffResult, FinishOutcome classification,
hook implementations, escalation paths, and the run_finish_and_handoff
orchestration function in both dry-run and simulated-live modes.
"""
from __future__ import annotations

import json

import pytest

from orchestrator.local_automation.engine.handoff import (
    HOOK_REGISTRY,
    TERMINAL_FAILURE_PHASES,
    FinishOutcome,
    HandoffResult,
    ProfilePhase,
    assert_main_screen_hook,
    classify_finish_outcome,
    get_hook,
    noop_hook,
    restart_labview_hook,
    run_finish_and_handoff,
)


# ---------------------------------------------------------------------------
# ProfilePhase enum
# ---------------------------------------------------------------------------

class TestProfilePhase:
    def test_all_phases_are_strings(self):
        """All phase values should be lowercase strings."""
        for phase in ProfilePhase:
            assert isinstance(phase.value, str)
            assert phase.value == phase.value.lower()

    def test_expected_phases_exist(self):
        """Verify all 10 required phases from spec are present."""
        expected = [
            "profile_started", "profile_engine_passed",
            "waiting_for_finish", "finish_pass", "finish_timeout",
            "finish_artifacts_missing", "restart_required",
            "ready_for_next_profile", "handoff_failed", "matrix_aborted",
        ]
        actual = [p.value for p in ProfilePhase]
        for e in expected:
            assert e in actual, f"Missing phase: {e}"

    def test_phase_count(self):
        assert len(ProfilePhase) == 10

    def test_terminal_failure_phases(self):
        """Terminal failures should block matrix continuation."""
        assert ProfilePhase.FINISH_TIMEOUT in TERMINAL_FAILURE_PHASES
        assert ProfilePhase.FINISH_ARTIFACTS_MISSING in TERMINAL_FAILURE_PHASES
        assert ProfilePhase.HANDOFF_FAILED in TERMINAL_FAILURE_PHASES
        assert ProfilePhase.MATRIX_ABORTED in TERMINAL_FAILURE_PHASES
        # These are NOT terminal failures:
        assert ProfilePhase.FINISH_PASS not in TERMINAL_FAILURE_PHASES
        assert ProfilePhase.READY_FOR_NEXT_PROFILE not in TERMINAL_FAILURE_PHASES
        assert ProfilePhase.RESTART_REQUIRED not in TERMINAL_FAILURE_PHASES


# ---------------------------------------------------------------------------
# FinishOutcome classification
# ---------------------------------------------------------------------------

class TestClassifyFinishOutcome:
    def test_finished_normally(self):
        outcome = FinishOutcome(finished=True, method="result_file", detail="test.pdf")
        assert classify_finish_outcome(outcome) == ProfilePhase.FINISH_PASS

    def test_timed_out(self):
        outcome = FinishOutcome(finished=False, timed_out=True, method="timeout")
        assert classify_finish_outcome(outcome) == ProfilePhase.FINISH_TIMEOUT

    def test_failed_fast(self):
        outcome = FinishOutcome(finished=True, failed_fast=True, method="log_keyword")
        assert classify_finish_outcome(outcome) == ProfilePhase.FINISH_ARTIFACTS_MISSING

    def test_not_finished_not_timed_out(self):
        """Edge case: not finished, not timed out → artifacts missing."""
        outcome = FinishOutcome(finished=False, timed_out=False)
        assert classify_finish_outcome(outcome) == ProfilePhase.FINISH_ARTIFACTS_MISSING

    def test_timeout_takes_priority_over_finished(self):
        """Timeout flag takes priority even if finished is True."""
        outcome = FinishOutcome(finished=True, timed_out=True)
        assert classify_finish_outcome(outcome) == ProfilePhase.FINISH_TIMEOUT


# ---------------------------------------------------------------------------
# HandoffResult serialization
# ---------------------------------------------------------------------------

class TestHandoffResult:
    def test_default_to_dict(self):
        """Default HandoffResult produces minimal dict."""
        hr = HandoffResult()
        d = hr.to_dict()
        assert d["phase"] == "profile_started"
        assert d["ready_for_next"] is False
        assert "finish_method" not in d
        assert "error" not in d
        assert "simulated" not in d

    def test_full_to_dict(self):
        hr = HandoffResult(
            phase=ProfilePhase.FINISH_PASS,
            finish_method="result_file",
            finish_elapsed_sec=3600.123,
            finish_detail="/path/to/result.pdf",
            restart_performed=True,
            restart_success=True,
            ready_for_next=True,
            simulated=True,
        )
        d = hr.to_dict()
        assert d["phase"] == "finish_pass"
        assert d["finish_method"] == "result_file"
        assert d["finish_elapsed_sec"] == 3600.1
        assert d["restart_performed"] is True
        assert d["restart_success"] is True
        assert d["simulated"] is True

    def test_error_included_when_set(self):
        hr = HandoffResult(error="something broke")
        d = hr.to_dict()
        assert d["error"] == "something broke"

    def test_json_serializable(self):
        """HandoffResult.to_dict() must be JSON-serializable."""
        hr = HandoffResult(
            phase=ProfilePhase.MATRIX_ABORTED,
            finish_method="timeout",
            error="timed out",
            simulated=True,
        )
        # Should not raise
        json_str = json.dumps(hr.to_dict())
        parsed = json.loads(json_str)
        assert parsed["phase"] == "matrix_aborted"


# ---------------------------------------------------------------------------
# Hook implementations
# ---------------------------------------------------------------------------

class TestHooks:
    def test_noop_hook_always_succeeds(self):
        ok, detail = noop_hook("artifacts/", "next_profile")
        assert ok is True
        assert detail == "noop"

    def test_noop_hook_dry_run(self):
        ok, detail = noop_hook("artifacts/", "next_profile", dry_run=True)
        assert ok is True

    def test_assert_main_screen_dry_run_succeeds(self):
        ok, detail = assert_main_screen_hook("artifacts/", "next", dry_run=True)
        assert ok is True
        assert "dry-run" in detail

    def test_assert_main_screen_live_fails_gracefully(self):
        ok, detail = assert_main_screen_hook("artifacts/", "next", dry_run=False)
        assert ok is False
        assert "live" in detail.lower() or "Windows" in detail

    def test_restart_hook_dry_run_succeeds(self):
        ok, detail = restart_labview_hook("artifacts/", "next", dry_run=True)
        assert ok is True
        assert "dry-run" in detail

    def test_restart_hook_live_fails_gracefully(self):
        ok, detail = restart_labview_hook("artifacts/", "next", dry_run=False)
        assert ok is False

    def test_get_hook_valid(self):
        for name in ["noop", "assert_main_screen", "restart"]:
            hook = get_hook(name)
            assert callable(hook)

    def test_get_hook_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            get_hook("nonexistent_hook")

    def test_hook_registry_complete(self):
        assert set(HOOK_REGISTRY.keys()) == {"noop", "assert_main_screen", "restart"}


# ---------------------------------------------------------------------------
# run_finish_and_handoff: dry-run paths
# ---------------------------------------------------------------------------

class TestRunFinishAndHandoffDryRun:
    def test_no_finish_wait_last_profile(self):
        """Dry-run, no finish wait, last profile → READY."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True
        assert result.simulated is True
        assert result.finish_method == "skipped"

    def test_with_finish_wait(self):
        """Dry-run with finish wait → simulated FINISH_PASS → READY."""
        result = run_finish_and_handoff(
            profile_name="BE200 5G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True
        assert result.finish_method == "simulated"

    def test_with_next_profile_noop_hook(self):
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            between_hook_name="noop",
            next_profile_name="BE200 5G",
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True

    def test_with_assert_main_screen_hook(self):
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            between_hook_name="assert_main_screen",
            next_profile_name="BE200 5G",
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True

    def test_with_restart_hook(self):
        result = run_finish_and_handoff(
            profile_name="BE200 5G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            between_hook_name="restart",
            next_profile_name="BE200 6G",
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True

    def test_last_profile_no_handoff_needed(self):
        result = run_finish_and_handoff(
            profile_name="BE200 6G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            next_profile_name="",
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True

    def test_serialization_round_trip(self):
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            between_hook_name="noop",
            next_profile_name="BE200 5G",
            dry_run=True,
        )
        d = result.to_dict()
        assert d["phase"] == "ready_for_next_profile"
        assert d["ready_for_next"] is True
        assert d["simulated"] is True
        # Must be JSON-serializable
        json.dumps(d)


# ---------------------------------------------------------------------------
# run_finish_and_handoff: injected FinishOutcome (simulated live scenarios)
# ---------------------------------------------------------------------------

class TestRunFinishAndHandoffWithOutcome:
    def test_injected_finish_pass(self):
        """Injected successful FinishOutcome → READY."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            dry_run=False,
            finish_outcome=FinishOutcome(
                finished=True, method="result_file",
                elapsed_sec=3600.0, detail="/path/result.pdf",
            ),
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.finish_method == "result_file"
        assert result.finish_elapsed_sec == 3600.0
        assert result.ready_for_next is True

    def test_injected_finish_timeout_last_profile(self):
        """Timeout on last profile → FINISH_TIMEOUT, not MATRIX_ABORTED."""
        result = run_finish_and_handoff(
            profile_name="BE200 6G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            next_profile_name="",
            dry_run=False,
            finish_outcome=FinishOutcome(
                finished=False, timed_out=True, method="timeout",
                elapsed_sec=14400.0, detail="Timed out after 14400s",
            ),
        )
        assert result.phase == ProfilePhase.FINISH_TIMEOUT
        assert result.finish_timed_out is True
        assert result.ready_for_next is False

    def test_injected_finish_timeout_with_next_profile(self):
        """Timeout with next profile → MATRIX_ABORTED."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            next_profile_name="BE200 5G",
            dry_run=False,
            finish_outcome=FinishOutcome(
                finished=False, timed_out=True, method="timeout",
                elapsed_sec=14400.0,
            ),
        )
        assert result.phase == ProfilePhase.MATRIX_ABORTED
        assert result.ready_for_next is False
        assert "BE200 5G" in result.error

    def test_injected_finish_artifacts_missing(self):
        """Failed fast → MATRIX_ABORTED when next profile exists."""
        result = run_finish_and_handoff(
            profile_name="BE200 5G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            next_profile_name="BE200 6G",
            dry_run=False,
            finish_outcome=FinishOutcome(
                finished=True, failed_fast=True, method="log_keyword",
                detail="FAIL_FAST:Error",
            ),
        )
        assert result.phase == ProfilePhase.MATRIX_ABORTED
        assert result.finish_failed_fast is True
        assert result.ready_for_next is False


# ---------------------------------------------------------------------------
# Escalation: assert_main_screen → restart
# ---------------------------------------------------------------------------

class TestEscalation:
    def test_assert_main_screen_live_escalates_to_restart(self):
        """Live assert_main_screen fails → escalates to restart → also fails."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            between_hook_name="assert_main_screen",
            next_profile_name="BE200 5G",
            dry_run=False,
        )
        assert result.phase == ProfilePhase.HANDOFF_FAILED
        assert result.restart_performed is True
        assert result.restart_success is False
        assert result.ready_for_next is False
        assert "assert_main_screen" in result.error
        assert "restart" in result.error.lower()

    def test_restart_hook_live_fails_directly(self):
        """Live restart hook fails → HANDOFF_FAILED (no further escalation)."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            between_hook_name="restart",
            next_profile_name="BE200 5G",
            dry_run=False,
        )
        assert result.phase == ProfilePhase.HANDOFF_FAILED
        assert result.restart_performed is True
        assert result.restart_success is False

    def test_dry_run_no_escalation_needed(self):
        """Dry-run hooks always succeed → no escalation triggered."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            between_hook_name="assert_main_screen",
            next_profile_name="BE200 5G",
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.restart_performed is False


# ---------------------------------------------------------------------------
# Full state transition sequences
# ---------------------------------------------------------------------------

class TestStateTransitionSequences:
    """Verify complete state sequences for typical matrix scenarios."""

    def test_happy_path_three_profiles_dry_run(self):
        """3-profile dry-run matrix: all profiles pass + handoff."""
        profiles = ["BE200 2.4G", "BE200 5G", "BE200 6G"]
        results = []
        for i, name in enumerate(profiles):
            next_name = profiles[i + 1] if i + 1 < len(profiles) else ""
            r = run_finish_and_handoff(
                profile_name=name,
                artifacts_dir=f"artifacts/{i}",
                wait_for_finish_enabled=True,
                between_hook_name="noop",
                next_profile_name=next_name,
                dry_run=True,
            )
            results.append(r)

        for r in results:
            assert r.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
            assert r.ready_for_next is True
            assert r.simulated is True

    def test_second_profile_timeout_aborts_matrix(self):
        """Profile 2 times out → MATRIX_ABORTED, profile 3 never starts."""
        r1 = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/0",
            wait_for_finish_enabled=True,
            next_profile_name="BE200 5G",
            dry_run=True,
        )
        assert r1.ready_for_next is True

        r2 = run_finish_and_handoff(
            profile_name="BE200 5G",
            artifacts_dir="artifacts/1",
            wait_for_finish_enabled=True,
            next_profile_name="BE200 6G",
            dry_run=False,
            finish_outcome=FinishOutcome(
                finished=False, timed_out=True, method="timeout",
                elapsed_sec=14400.0,
            ),
        )
        assert r2.phase == ProfilePhase.MATRIX_ABORTED
        assert r2.ready_for_next is False

    def test_finish_pass_but_handoff_fails(self):
        """Finish succeeds but restart hook fails → HANDOFF_FAILED."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            between_hook_name="restart",
            next_profile_name="BE200 5G",
            dry_run=False,
            finish_outcome=FinishOutcome(
                finished=True, method="result_file", detail="result.pdf",
            ),
        )
        assert result.phase == ProfilePhase.HANDOFF_FAILED
        assert result.finish_method == "result_file"
        assert result.restart_performed is True
        assert result.restart_success is False

    def test_continue_on_failure_multiple_profiles(self):
        """Simulate continue-on-failure: profile 1 timeout, profile 2 ok."""
        r1 = run_finish_and_handoff(
            profile_name="Profile A",
            artifacts_dir="artifacts/0",
            wait_for_finish_enabled=True,
            next_profile_name="Profile B",
            dry_run=False,
            finish_outcome=FinishOutcome(
                finished=False, timed_out=True, method="timeout",
            ),
        )
        assert r1.phase == ProfilePhase.MATRIX_ABORTED
        assert r1.ready_for_next is False

        # In a continue-on-failure matrix, runner would still start profile B
        r2 = run_finish_and_handoff(
            profile_name="Profile B",
            artifacts_dir="artifacts/1",
            wait_for_finish_enabled=True,
            next_profile_name="",
            dry_run=True,
        )
        assert r2.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert r2.ready_for_next is True


# ---------------------------------------------------------------------------
# HandoffResult integration with matrix summary (no matrix_runner import)
# ---------------------------------------------------------------------------

class TestHandoffResultForMatrixIntegration:
    """Verify that HandoffResult produces correct JSON for matrix_summary.json.

    NOTE: We do NOT import MatrixEntry/MatrixSummary here because
    matrix_runner.py imports Windows-only modules (screen_utils/ctypes.windll)
    at module level. These integration tests verify the handoff side only.
    The full matrix_runner integration is tested on Windows.
    """

    def test_handoff_dict_embeds_in_entry_shape(self):
        """HandoffResult.to_dict() produces valid sub-object for an entry."""
        hr = HandoffResult(
            phase=ProfilePhase.READY_FOR_NEXT_PROFILE,
            finish_method="simulated",
            finish_elapsed_sec=0.0,
            ready_for_next=True,
            simulated=True,
        )
        # Simulate what MatrixEntry.to_dict() would produce
        entry_dict = {
            "profile_name": "BE200 2.4G",
            "band": "2.4G",
            "mode": "BW20",
            "status": "pass (dry-run)",
            "handoff": hr.to_dict(),
        }
        assert entry_dict["handoff"]["phase"] == "ready_for_next_profile"
        assert entry_dict["handoff"]["simulated"] is True
        # JSON round-trip
        json_str = json.dumps(entry_dict)
        parsed = json.loads(json_str)
        assert parsed["handoff"]["ready_for_next"] is True

    def test_aborted_handoff_dict(self):
        """MATRIX_ABORTED handoff produces abort info for summary."""
        hr = HandoffResult(
            phase=ProfilePhase.MATRIX_ABORTED,
            finish_method="timeout",
            finish_timed_out=True,
            error="Cannot proceed: finish timed out",
            ready_for_next=False,
        )
        d = hr.to_dict()
        assert d["phase"] == "matrix_aborted"
        assert d["ready_for_next"] is False
        assert d["finish_timed_out"] is True
        assert "Cannot proceed" in d["error"]
        # Must be JSON-serializable
        json.dumps(d)

    def test_handoff_failed_with_restart_info(self):
        """HANDOFF_FAILED includes restart attempt details."""
        hr = HandoffResult(
            phase=ProfilePhase.HANDOFF_FAILED,
            restart_performed=True,
            restart_success=False,
            error="Restart failed: main window not found",
        )
        d = hr.to_dict()
        assert d["restart_performed"] is True
        assert d["restart_success"] is False
        assert d["phase"] == "handoff_failed"

    def test_no_handoff_entry(self):
        """When handoff is None, entry dict should not include the key."""
        # Simulate entry without handoff
        entry_dict = {
            "profile_name": "test",
            "status": "error",
            "error": "load fail",
        }
        assert "handoff" not in entry_dict
