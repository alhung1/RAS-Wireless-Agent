# Migration plan: remaining legacy-wrapped steps

**Implemented today:** `build_default_sequence()` uses **`LegacyStepWrapper`** for 13 indices and **native `BaseStep`** for **s00, s05, s06, s11, s14, s15**.

Legacy implementations remain in **`labview_runner_legacy.py`** and stay referenced by **`STEP_SEQUENCE`** for **`run_single_step.py`**.

## Principles

- One bucket at a time; **live-validate** after each bucket on real LabVIEW.
- Preserve **step index** and **`result.json` names** (`STEP_SEQUENCE[i].__name__` via mapping).
- Prefer **non-critical** steps first; add **`is_critical=True`** only when verification is reliable.
- Reuse **`labview_runner_legacy`** helpers (`_screenshot`, `_click_at`, …) from native steps to avoid duplicating coordinate logic until a later “pure ui/” extraction.

## Buckets

### Bucket 1 — **DONE** (low risk)

| Index | Step | Action |
|------:|------|--------|
| 0 | `s00_attach` | **Native `AttachStep`** in `steps/s00_attach.py` — same behavior as `step_00_attach` (hwnd check + screenshot). |

### Bucket 2 — Simple forward / pass-through (medium-low risk)

Single primary action, little branching; **non-critical** initially.

| Index | Legacy fn | Notes |
|------:|-----------|--------|
| 9 | `step_09_dut_ip` | Orange arrow / pass-through style |
| 13 | `step_13_pass_through` | Similar pattern |

**Migration approach:** Native step calls legacy helpers inside `execute()`; optional template-based `verify()` if stable.

### Bucket 3 — Wizard core (medium risk)

Login, throughput click, test type, table position; heavy popup logic.

| Indices | Functions |
|--------:|-----------|
| 1–4 | `step_01` … `step_04` |

**Do after** bucket 2 and improved shared **`WindowManager`** / popup contract tests.

### Bucket 4 — AP/DUT / Chariot / final (higher risk)

| Indices | Functions |
|--------:|-----------|
| 7–8, 10 | `step_07` … `step_10` |
| 12 | `step_12_chariot_pairs` |
| 16–18 | `step_16` … `step_18` |

Reason: listboxes, **Use Last** toggles, **final start** — historically failure-prone; migrate only with strong verification and live soak.

## Validation checklist (per bucket)

1. `python -m py_compile` + `scripts/smoke_labview_compat.py`
2. `run_profile.py --dry-run --skip-to 19` (preflight)
3. Live: `run_profile.py` or `run_labview_flow` from step 0 through first migrated index + one step beyond

## Registry maintenance

- Remove legacy key from **`_build_legacy_map()`** when native step replaces wrapper.
- Keep **`step_XX`** in **`STEP_SEQUENCE`** in **`labview_runner_legacy.py`** until **`run_single_step.py`** is switched to **`StepEngine.run_single`**.
