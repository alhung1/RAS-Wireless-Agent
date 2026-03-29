# Design: finish detector + live matrix orchestration (next phase)

**Status:** Design only — describes how to extend **implemented** `matrix_runner.py` and `finish_detector.py` / `wait_for_finish` without rewriting unrelated code.

## Current implemented reality

| Component | Behavior today |
|-----------|----------------|
| **`run_labview_flow`** (thin facade) | After wizard success, calls **`wait_for_finish`** with `FinishConfig` from `RunConfig.finish_config` + initial PDF snapshot. |
| **`run_matrix` / `matrix_runner.run_matrix`** | For each profile: preflight + **`StepEngine.run(start_from=0)`** only. **No** `wait_for_finish`. Marks profile **pass** when `overall_status == "pass"` (wizard only). |
| **`finish_detector.py`** | `wait_for_finish(cfg, artifacts_dir, initial_files)` — PDF glob, optional log/UI, timeout, polling. |

**Gap:** A **live matrix** of real throughput tests expects each profile to include **hours of runtime** and a **new PDF** (or other finish signal). Today the matrix would start the next profile **immediately** after the wizard completes, while LabVIEW may still be running the previous test or sitting on a non-start screen.

## Goals

1. **Optional per-profile finish wait** in matrix mode (config-driven, default off or on per profile flag).
2. **Deterministic inter-profile state:** before starting profile *N+1*, ensure LabVIEW is in a state where **step 0** (attach) or **step 1** (main screen) is valid — either same process + known UI state, or **restart** executable.
3. **Reuse** existing `FinishConfig` / `wait_for_finish` and polling rules (no duplicate detection logic).

## Proposed architecture

### 1. Profile / config flags

Extend **`TestProfile`** (or matrix-only overlay) with optional:

- **`matrix_wait_for_finish: bool`** (default `false` for backward compatibility).
- **`matrix_finish_config: FinishDetectionConfig | null`** — override or inherit from `finish_detection` on the test profile.

When `matrix_wait_for_finish` is true and not `dry_run`, after `engine.run()` succeeds:

- Build `FinishConfig` + `initial_files` the same way **`_build_finish_config`** does in legacy (already mirrored in profile resolution).
- Call **`wait_for_finish`** into the **same** `artifacts_dir` as the profile run (or a subfolder `finish/`) and attach **`FinishResult`** to matrix `MatrixEntry` / `run.json`.

### 2. Inter-profile orchestration (pluggable)

Introduce a narrow interface, e.g. **`MatrixBetweenProfilesHook`** (callable or small class):

```text
def between_profiles(ctx_previous, ctx_next, summary_entry) -> None:
    """Ensure LabVIEW is ready for the next wizard from step 0."""
```

**Implementations (incremental):**

| Strategy | When to use | Action |
|----------|-------------|--------|
| **`noop`** | Dry-run, or single-profile | No-op |
| **`assert_main_screen`** | LabVIEW returns to `480 000.vi` reliably | `WindowManager.find_window` + optional template check; if fail → escalate |
| **`restart_labview_exe`** | No reliable return to main | `subprocess` kill + launch `RunConfig.exe_path` + poll `find_window` (reuse legacy `prepare_labview_session` patterns) |
| **`operator_prompt`** | Last resort | Log + optional GUI prompt / file gate for manual reset |

**Selection:** Matrix CLI flag or YAML **`matrix_between_profiles: restart | assert_main | noop`**.

### 3. Matrix runner flow (pseudocode)

```text
for each profile:
  resolve run_config, artifacts_dir, ctx, hwnd
  engine.run()
  if failed: handle stop_on_failure; continue/break
  if matrix_wait_for_finish and not dry_run:
      wait_for_finish(...)
      if timed_out: mark entry failed; break/continue per policy
  between_profiles_hook(previous_ctx, next_ctx, entry)
write matrix_summary.json
```

### 4. Finish detector enhancements (optional, later)

- **Correlate PDF to run:** If multiple PDFs appear, prefer naming/timestamp heuristics (product-specific adapter hook).
- **Shorter “wizard done” vs “test done”:** Already separated by calling `wait_for_finish` only after wizard `overall_status == pass`.

### 5. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Restart kills in-flight UI | Only restart **after** finish success or explicit failure policy |
| `wait_for_finish` doubles wall time | Expected; matrix becomes **overnight/batch** tool |
| Different bands need different reset | Encode in profile or product adapter |

### 6. Suggested implementation order

1. Add **`matrix_wait_for_finish`** + call **`wait_for_finish`** after successful `engine.run()` (no restart).
2. Add **`noop` / `assert_main_screen`** hook using existing `WindowManager`.
3. Add **`restart_labview_exe`** hook reusing **`prepare_labview_session`** from legacy (shared helper in `engine` or `ui` to avoid duplication).
4. Extend **`matrix_summary.json`** with `finish_result` / `finish_timed_out` per entry.

## Out of scope (this phase)

- Changing **`finish_detector`** detection algorithms unless PDF correlation proves insufficient.
- Router / WiFi worker orchestration (stays in existing E2E actions).
