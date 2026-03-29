# Migration status and file summary

## Completed phases (as implemented)

| Phase | Scope | Status |
|-------|--------|--------|
| **Skeleton** | `StepContext`, engine `RunConfig`, `StepResult`, `VerificationSpec`, preflight, report, registry pattern | Done |
| **A.6** | `ui/` package: window manager, input, verification, coordinates, detection, dropdowns | Done |
| **B (incremental)** | Native critical steps: **s05, s06, s11, s14, s15** + per-field / adapter-owned verification | Done |
| **OCR** | Tesseract integration, LabVIEW-tuned preprocessing, digit normalization, BE200 region calibration | Done |
| **C** | `matrix_runner.py`, `run_profile.py`, `run_matrix.py`, `validate_profiles.py`, resume / single-step via `StepEngine` | Done |
| **D.2** | Thin **`labview_runner.py`**, **`labview_runner_legacy.py`**, **`labview_legacy_report_mapping.py`**, registry import fix | Done |
| **D.3** | Documentation under **`docs/`** (this set) | Done |

## Post-milestone follow-up (documentation + migration bucket 1)

- **Docs:** `RELEASE_PROPOSAL.md`, accomplishment summaries, `DESIGN_MATRIX_FINISH_ORCHESTRATION.md`, `MIGRATION_LEGACY_STEPS.md`, root `README.md` pointer to `docs/README.md`.
- **Code:** **`s00_attach`** migrated to native **`AttachStep`** (`steps/s00_attach.py`); registry updated; `step_00_attach` removed from `_build_legacy_map` (still in `STEP_SEQUENCE` for `run_single_step.py`).

## Deferred / not required for current milestone

- Convert remaining **12** legacy-wrapped steps to native `BaseStep` (per [MIGRATION_LEGACY_STEPS.md](MIGRATION_LEGACY_STEPS.md) buckets 2–4).
- Further slim **`labview_runner_legacy.py`** (optional cleanup only).
- Unify **`run_single_step.py`** with `StepEngine` (calibration script today).
- Automatic **LabVIEW restart** or **wizard reset** between matrix profiles (operational gap, not coded).
- Additional products beyond **BE200** (pattern documented in [HOW_TO_ADD_PRODUCT.md](HOW_TO_ADD_PRODUCT.md)).

## Recommended next engineering moves

1. **Operational hardening for matrix live runs** — document or automate “return to step 0” / restart between profiles if multi-profile live execution is required routinely.
2. **Optional dry-run artifact hook** — if teams still need annotated PNGs, add a **`post_step_hooks`-style** or engine callback without duplicating orchestration logic.
3. **Next native conversions** — only if a step needs richer verification/recovery than the legacy wrapper provides; prioritize by failure rate in production logs.
4. **Extend `smoke_labview_compat.py`** in CI (imports + fast `--skip-to 19` dry-run).

## Changed / added files summary (refactor + D.2 + D.3)

**Documentation (this deliverable)**

- `docs/README.md` (index)
- `docs/RELEASE_PROPOSAL.md`
- `docs/ACCOMPLISHMENT_ENGINEERING.md`
- `docs/ACCOMPLISHMENT_STAKEHOLDER.md`
- `docs/DESIGN_MATRIX_FINISH_ORCHESTRATION.md`
- `docs/MIGRATION_LEGACY_STEPS.md`
- `docs/LABVIEW_RUNNER.md`
- `docs/ARCHITECTURE_SUMMARY.md`
- `docs/HOW_TO_RUN.md`
- `docs/HOW_TO_ADD_PRODUCT.md`
- `docs/KNOWN_LIMITATIONS.md`
- `docs/MIGRATION_STATUS.md`
- `docs/samples/example_run.json`
- `docs/samples/example_result.json`

**Core automation (earlier + D.2)**

- `orchestrator/local_automation/labview_runner.py` (thin facade)
- `orchestrator/local_automation/labview_runner_legacy.py` (legacy implementation)
- `orchestrator/local_automation/labview_legacy_report_mapping.py`
- `orchestrator/local_automation/steps/registry.py` (legacy → `labview_runner_legacy`)
- `orchestrator/local_automation/engine/*` (step engine, matrix, preflight, report)
- `orchestrator/local_automation/steps/s05_*.py`, `s06_*.py`, `s11_*.py`, `s14_*.py`, `s15_*.py`
- `orchestrator/local_automation/ui/*`, `products/be200.py`, `profiles/*`
- `scripts/run_profile.py`, `run_matrix.py`, `validate_profiles.py`, `smoke_labview_compat.py`

## Remaining risks / TODOs

| Risk | Mitigation |
|------|------------|
| Matrix live runs without clean wizard reset | Runbook / future orchestration |
| `user_info` / s11 weak semantic proof | Accept or invest in UI/OCR calibration |
| `run_single_step` vs engine drift | Prefer `run_profile.py --step` for debugging |
| Template/path drift on new LabVIEW builds | Version templates per VI build; preflight warnings |
| Long finish timeout masking earlier failures | Monitor `run.json` `failed_step` and `errors` |

**Optional:** Add a one-line pointer from the repository root `README.md` to `docs/README.md` if you want a single discoverability path from the landing page.
