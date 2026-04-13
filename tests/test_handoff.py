"""Unit tests for matrix finish orchestration handoff module.

Tests the ProfilePhase enum, HandoffResult, hook implementations,
and the run_finish_and_handoff orchestration function in dry-run mode.
"""
from __future__ import annotations

import pytest

from orchestrator.local_automation.engine.handoff import (
    HOOK_REGISTRY,
    HandoffResult,
    ProfilePhase,
    assert_main_screen_hook,
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
        """Verify all required phases from spec are present."""
        expected = [
            "profile_started", "profile_engine_passed",
            "waiting_for_finish", "finish_pass", "finish_timeout",
            "finish_artifacts_missing", "restart_required",
            "ready_for_next_profile", "handoff_failed", "matrix_aborted",
        ]
        actual = [p.value for p in ProfilePhase]
        for e in expected:
            assert e in actual, f"Missing phase: {e}"


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

    def test_full_to_dict(self):
        """HandoffResult with all fields populated."""
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
        assert d["simulated"] is True

    def test_error_included_when_set(self):
        hr = HandoffResult(error="something broke")
        d = hr.to_dict()
        assert d["error"] == "something broke"


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
        """Without Windows/LabVIEW, live mode returns failure (not crash)."""
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
# run_finish_and_handoff orchestration
# ---------------------------------------------------------------------------

class TestRunFinishAndHandoff:
    def test_dry_run_no_finish_wait(self):
        """Dry-run without finish wait → immediate READY_FOR_NEXT_PROFILE."""
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

    def test_dry_run_with_finish_wait(self):
        """Dry-run with finish wait → simulated FINISH_PASS."""
        result = run_finish_and_handoff(
            profile_name="BE200 5G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True
        assert result.finish_method == "simulated"

    def test_dry_run_with_next_profile_noop_hook(self):
        """Dry-run with next profile → noop hook succeeds."""
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

    def test_dry_run_with_assert_main_screen_hook(self):
        """Dry-run with assert_main_screen hook → succeeds (simulated)."""
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

    def test_dry_run_with_restart_hook(self):
        """Dry-run with restart hook → succeeds (simulated)."""
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
        """Last profile (no next) → ready_for_next without hook call."""
        result = run_finish_and_handoff(
            profile_name="BE200 6G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            next_profile_name="",
            dry_run=True,
        )
        assert result.phase == ProfilePhase.READY_FOR_NEXT_PROFILE
        assert result.ready_for_next is True

    def test_handoff_result_serialization(self):
        """Verify the full round-trip of HandoffResult.to_dict()."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=True,
            between_hook_name="noop",
            next_profile_name="BE200 5G",
            dry_run=True,
        )
        d = result.to_dict()
        assert "phase" in d
        assert "ready_for_next" in d
        assert d["simulated"] is True

    def test_live_assert_main_screen_fails_gracefully(self):
        """Live mode with assert_main_screen → fails but doesn't crash."""
        result = run_finish_and_handoff(
            profile_name="BE200 2.4G",
            artifacts_dir="artifacts/test",
            wait_for_finish_enabled=False,
            between_hook_name="assert_main_screen",
            next_profile_name="BE200 5G",
            dry_run=False,
        )
        # On Linux, assert_main_screen fails → RESTART_REQUIRED
        assert result.phase == ProfilePhase.RESTART_REQUIRED
        assert result.ready_for_next is False
