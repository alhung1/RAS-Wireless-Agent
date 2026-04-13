# Design: finish detector + live matrix orchestration

## Implementation status

| Layer | Status | Location |
|-------|--------|----------|
| **ProfilePhase enum (10 states)** | **Implemented + tested** | `engine/handoff.py` |
| **HandoffResult dataclass** | **Implemented + tested** | `engine/handoff.py` |
| **FinishOutcome classification** | **Implemented + tested** | `engine/handoff.py` |
| **BetweenProfilesHook protocol** | **Implemented + tested** | `engine/handoff.py` |
| **3 hook implementations** (noop, assert_main_screen, restart) | **Implemented** (dry-run tested; live paths stubbed) | `engine/handoff.py` |
| **Escalation** (assert_main → restart) | **Implemented + tested** | `engine/handoff.py` |
| **run_finish_and_handoff() orchestration** | **Implemented + tested** | `engine/handoff.py` |
| **MatrixEntry.handoff field** | **Implemented** | `engine/matrix_runner.py` |
| **MatrixSummary extensions** (wait_for_finish, between_profiles, aborted) | **Implemented + tested** | `engine/matrix_runner.py` |
| **matrix_runner integration** (handoff after engine pass) | **Implemented** | `engine/matrix_runner.py` |
| **Unit tests** (42 tests) | **All passing** | `tests/test_handoff.py` |
| **Live wait_for_finish() call** | **Stubbed — requires Windows + LabVIEW** | `engine/handoff.py` (commented code) |
| **Live WindowManager.find_window()** | **Stubbed — requires Windows** | `engine/handoff.py` (commented code) |
| **Live subprocess restart** | **Stubbed — requires Windows** | `engine/handoff.py` (commented code) |
| **Real PDF/log/UI finish detection** | **Stubbed — requires D:\480\LOG\RBU** | `finish_detector.py` (existing, not modified) |

---

## Architecture

### State machine

```
PROFILE_STARTED
  → PROFILE_ENGINE_PASSED           engine.run() succeeded
    → WAITING_FOR_FINISH            if wait_for_finish enabled
      → FINISH_PASS                 finish detected (PDF/log/UI)
      → FINISH_TIMEOUT              timeout without detection
      → FINISH_ARTIFACTS_MISSING    finished but expected files absent
    → FINISH_PASS                   if wait_for_finish disabled
      → READY_FOR_NEXT_PROFILE      hook succeeded or last profile
      → RESTART_REQUIRED            hook failed, restart may help
        → READY_FOR_NEXT_PROFILE    restart succeeded
        → HANDOFF_FAILED            restart also failed
      → HANDOFF_FAILED              restart hook itself failed
    → MATRIX_ABORTED                unrecoverable; matrix should stop
```

### Components

**`engine/handoff.py`** — All handoff logic, no Windows imports at module level:

- `ProfilePhase` enum (10 states)
- `FinishOutcome` — portable finish result (avoids importing Windows-only `FinishResult`)
- `classify_finish_outcome()` — pure function mapping outcome → phase
- `HandoffResult` dataclass with `to_dict()` serialization
- `BetweenProfilesHook` protocol + 3 implementations
- `HOOK_REGISTRY` for name-based lookup
- `TERMINAL_FAILURE_PHASES` set for matrix abort logic
- `run_finish_and_handoff()` — main orchestration entry point

**`engine/matrix_runner.py`** — Extended with:

- `MatrixEntry.handoff` field (optional `HandoffResult`)
- `MatrixSummary.wait_for_finish`, `.between_profiles`, `.aborted`, `.abort_reason`
- `run_matrix(wait_for_finish=, between_profiles=)` parameters
- Post-engine handoff block with `MATRIX_ABORTED` escalation

### Hooks

| Hook | Dry-run | Live |
|------|---------|------|
| `noop` | Always succeeds | Always succeeds |
| `assert_main_screen` | Simulated success | `WindowManager.find_window()` |
| `restart` | Simulated success | `taskkill + Popen + find_window` |

**Escalation:** If `assert_main_screen` fails live, automatically retries with `restart`. If restart also fails → `HANDOFF_FAILED`.

### matrix_summary.json schema

```json
{
  "started_at": "2026-04-12T...",
  "finished_at": "2026-04-12T...",
  "total_profiles": 3,
  "passed": 2,
  "failed": 1,
  "skipped": 0,
  "stop_on_failure": true,
  "wait_for_finish": true,
  "between_profiles": "assert_main_screen",
  "aborted": true,
  "abort_reason": "Finish timed out for BE200 5G",
  "entries": [
    {
      "profile_name": "BE200 2.4G",
      "band": "2.4G",
      "mode": "BW20",
      "status": "pass (dry-run)",
      "handoff": {
        "phase": "ready_for_next_profile",
        "ready_for_next": true,
        "finish_method": "simulated",
        "finish_elapsed_sec": 0.0,
        "simulated": true
      }
    },
    {
      "profile_name": "BE200 5G",
      "status": "handoff_failed",
      "handoff": {
        "phase": "matrix_aborted",
        "ready_for_next": false,
        "finish_method": "timeout",
        "finish_elapsed_sec": 14400.0,
        "finish_timed_out": true,
        "error": "Cannot proceed to 'BE200 6G': finish phase was finish_timeout"
      }
    }
  ]
}
```

---

## What remains for live integration

The following items **cannot be completed from the repo alone** and require the live 22.8 Windows machine with LabVIEW running:

### Step 1: Wire wait_for_finish into handoff (on 22.8)

In `engine/handoff.py`, uncomment the `LIVE INTEGRATION` block in `run_finish_and_handoff()`:
- Import `wait_for_finish` from `finish_detector`
- Build `FinishConfig` from profile's `finish_detection` settings
- Convert `FinishResult` → `FinishOutcome`

### Step 2: Wire assert_main_screen hook (on 22.8)

In `assert_main_screen_hook()`, uncomment the `LIVE INTEGRATION` block:
- Import `WindowManager`
- Call `wm.find_window()`

### Step 3: Wire restart hook (on 22.8)

In `restart_labview_hook()`, uncomment the `LIVE INTEGRATION` block:
- `taskkill` the LabVIEW exe
- `Popen` to launch new instance
- `find_window` to verify

### Step 4: End-to-end matrix test (on 22.8)

Run a real 2-profile matrix with `wait_for_finish=True`:
```powershell
python scripts/run_matrix.py --dir profiles/test_matrix/ --wait-for-finish --between-profiles assert_main_screen
```

### Step 5: Verify matrix_summary.json output

Confirm that the live run produces correct handoff data, timing, and abort/continue behavior.

---

## Original design goals (reference)

1. **Optional per-profile finish wait** in matrix mode (config-driven, default off).
2. **Deterministic inter-profile state:** before starting profile *N+1*, ensure LabVIEW is ready for step 0.
3. **Reuse** existing `FinishConfig` / `wait_for_finish` (no duplicate detection logic).

### Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Restart kills in-flight UI | Only restart **after** finish success or explicit failure policy |
| `wait_for_finish` doubles wall time | Expected; matrix becomes **overnight/batch** tool |
| Different bands need different reset | Encode in profile or product adapter |

## Out of scope

- Changing `finish_detector` detection algorithms unless PDF correlation proves insufficient.
- Router / WiFi worker orchestration (stays in existing E2E actions).
- `operator_prompt` hook (deferred to future phase).
