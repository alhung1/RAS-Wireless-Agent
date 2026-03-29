# Technical milestone summary — engineering handoff

**Scope:** LabVIEW RvR wizard automation on orchestrator host (22.8-class), as **implemented** in this repository (not the original design doc only).

## What was built

1. **Layered architecture (live)**
   - **Profiles:** Pydantic `TestProfile` / `ProductProfileData`, YAML under `profiles/`.
   - **Product adapters:** `ProductBase` + `BE200Adapter` — bands, channels, modes, AP/client paths, **`VerificationSpec`** per field/step.
   - **Engine:** `StepContext`, `StepEngine` (precondition → execute → verify → recover), `PreflightError` / `EmergencyStopError`.
   - **Steps:** `BaseStep` + **`LegacyStepWrapper`**; six native steps (**s00, s05, s06, s11, s14, s15**) with structured `StepResult` and evidence JSON.
   - **UI:** `ui/` — `WindowManager`, input helpers, `verification.py` (OCR pipeline, pixel diff, inconclusive handling), coordinates, detection.
   - **Matrix:** `matrix_runner.run_matrix` → per-profile `run.json` + `matrix_summary.json`.

2. **Backward compatibility (Phase D.2)**
   - **`labview_runner.py`** thin facade delegates to `StepEngine`, maps reports to legacy **`result.json`**, keeps **`wait_for_finish`**.
   - **`labview_runner_legacy.py`** holds all legacy `step_*` implementations and globals.
   - **`labview_legacy_report_mapping.py`** owns **`result.json` ↔ `run.json`** field rules.

3. **OCR & verification**
   - Tesseract + `pytesseract`; LabVIEW-specific scaling/threshold/invert; digit normalization with ambiguity resolution against expected values.
   - Per-field evidence for native multi-control steps (e.g. s05, s15).

4. **Reliability fixes**
   - Blocker hints / popup handling for **8002 Select AP/Client** and post-step-6 closure checks to unblock step 7.

5. **Documentation (Phase D.3 + follow-up)**
   - `docs/README.md` index, runbooks, limitations, migration status, release proposal, orchestration design, **legacy step migration plan**.

## Production readiness

| Area | Status |
|------|--------|
| Single profile YAML + `run_profile.py` | Ready (live depends on LabVIEW + paths) |
| Matrix dry-run / preflight | Ready |
| Matrix live, multi-hour finish, chained profiles | **Not fully orchestrated** — design doc only |
| Legacy `run_labview_flow` / scripts | Ready; stricter preflight |
| `run_single_step.py` | Still direct `STEP_SEQUENCE`; not engine-parity |

## Key file map

- Facade: `orchestrator/local_automation/labview_runner.py`
- Legacy impl: `orchestrator/local_automation/labview_runner_legacy.py`
- Report mapping: `orchestrator/local_automation/labview_legacy_report_mapping.py`
- Engine: `orchestrator/local_automation/engine/`
- Native steps: `orchestrator/local_automation/steps/s00_attach.py`, `s05_*`, `s06_*`, `s11_*`, `s14_*`, `s15_*`
- Registry: `orchestrator/local_automation/steps/registry.py`

## Next engineering priorities

1. **Matrix + finish orchestration** — see `DESIGN_MATRIX_FINISH_ORCHESTRATION.md`.
2. **Remaining legacy → native** — see `MIGRATION_LEGACY_STEPS.md` (bucket 1: **s00** done).
3. Optional: align `run_single_step.py` with `StepEngine` for calibration parity.
