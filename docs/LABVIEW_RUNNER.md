# LabVIEW runner: compatibility and thin facade

This document describes **`orchestrator/local_automation/labview_runner.py`** (thin facade) and **`labview_runner_legacy.py`** (implementation), as implemented after Phase D.2.

## Thin facade vs legacy split

| Module | Role |
|--------|------|
| **`labview_runner.py`** | Public entry API and CLI. Maps legacy `RunConfig` → engine `RunConfig`, resolves product adapter, builds `StepContext`, runs **`StepEngine`**, translates engine report → legacy `RunReport`, runs **`wait_for_finish`**, writes **`result.json`**. |
| **`labview_runner_legacy.py`** | Step functions (`step_00_attach` … `step_18_final_start`), pyautogui helpers, dry-run globals, window discovery, **`STEP_SEQUENCE`**, **`prepare_labview_session`**, **`build_band_config`**, **`_build_finish_config`**, **`_save_report`**, templates, coordinates. |
| **`labview_legacy_report_mapping.py`** | Single source of truth for **legacy `result.json` step rows** vs engine **`StepResult`** (see field table below). |

Orchestration (retry, verify, preflight) is **not** duplicated in the facade: it lives in **`StepEngine`**.

## Compatibility surface (supported)

**Flow API**

- `run_labview_flow`, `run_all_bands`, `build_band_config`, `make_wifi_connect_hook`, `STEP_IDX_DESIGN_STAGE`

**Types / constants**

- `RunConfig`, `RunReport`, `StepResult` (legacy dataclass), `EmergencyStopError`, `STOP_FILE`
- `STEP_SEQUENCE`, `BW_MODE_NAV`, window sizing constants (`WINDOW_WIDTH`, `MAIN_WINDOW_SIZE`, …)
- All **`step_XX_*`** callables

**Underscored helpers** (used by calibration / debug scripts; re-exported from facade)

- `_refresh_hwnd`, `_setup_vi`, `_find_vi_window`, `_enum_lv_windows`, `_force_fg`, `_screenshot`, `_get_window_title`, `_POPUP_DISMISSED_HWNDS`

**CLI** (`python -m orchestrator.local_automation.labview_runner`)

- `--band`, `--rf-2g`, `--rf-5g`, `--rf-6g`, `--user-info`, `--username`, `--password`, `--mode`, `--pairs-2g`, `--pairs-5g6g`, `--skip-to`, `--dry-run`, `--config`, `--all-bands`, `--bands`, `--stop`

## Supported entry points (summary)

| Entry | Purpose |
|-------|---------|
| Module CLI above | Single band or multi-band via YAML defaults (`ui_flow.yaml`). |
| `scripts/run_24g.py` | 2.4G preset + optional WiFi hook after design stage. |
| `scripts/run_labview_all_bands.py` | Multi-band wrapper around `run_all_bands`. |
| `scripts/run_24g_live.py` | Full wizard, **no finish wait** (script body runs immediately; no `--help`). |
| `orchestrator/actions/e2e_steps.py` | Async wrapper calling `run_labview_flow`. |
| Import `run_labview_flow` / `build_band_config` | Programmatic use (same as before). |

Profile-driven runs use **`scripts/run_profile.py`** / **`scripts/run_matrix.py`** (see [HOW_TO_RUN.md](HOW_TO_RUN.md)); they do not replace the legacy API but are the preferred path for YAML-defined tests.

## `LV_PRODUCT` default behavior

Legacy-compatible flows resolve the product adapter with:

```text
os.environ.get("LV_PRODUCT", "INTEL_BE200")
```

The loader uppercases the ID and looks up **`register_product("INTEL_BE200", BE200Adapter)`** in `profiles/loader.py`.

- **Default:** `INTEL_BE200` (Intel BE200 adapter).
- **Override:** set `LV_PRODUCT` to another registered ID when additional products exist.

Preflight (band, mode, channel, required fields) runs **before** steps for facade-driven runs.

## `result.json` vs `run.json`

Every **`run_labview_flow`** (and thus legacy entry points that call it) writes artifacts under `artifacts_base/<UTC_ts>/`:

| File | Producer | Audience |
|------|----------|----------|
| **`run.json`** | `StepEngine` / `save_run_report` | New stack: `run_id`, ISO timestamps, `overall_status`, `preflight`, engine `steps[]` with `ok`, `step_name`, `verification_evidence`, etc. |
| **`result.json`** | `labview_runner_legacy._save_report` after mapping | Legacy consumers: `success`, compact `started_at`/`finished_at`, `steps[]` with `name` = `STEP_SEQUENCE[i].__name__`, `screenshot`, `detail` blob. |

**Mapping rules** are documented in code in `labview_legacy_report_mapping.py` (module docstring + functions). Do not re-derive mapping in other modules.

**Example fixtures:** [samples/example_run.json](samples/example_run.json), [samples/example_result.json](samples/example_result.json).

## Known compatibility gaps

1. **Dry-run annotated PNGs** — The pre-refactor loop saved per-step `_dryrun.png` annotations. The engine path does **not** recreate those files (log line notes this).
2. **Preflight** — Engine enforces preflight before steps; the old monolithic loop did not (may fail earlier with clearer errors).
3. **Retry / recovery** — `StepEngine` uses per-step `recover()`; legacy used `_diagnose_failure` / `_recover_from_failure` around raw functions (behavior differs).
4. **Critical native steps** may fail **verification** after a nominally successful `execute` (stricter than legacy success-only).
5. **`run_single_step.py`** still calls **`STEP_SEQUENCE[i](hwnd, cfg, ad)`** directly — **not** `StepEngine` (calibration path unchanged).

## Production usability

- **Production-usable now:** YAML profiles + `run_profile.py` / `run_matrix.py`, and legacy `run_labview_flow` / `run_all_bands` on machines where LabVIEW, templates, and product paths match preflight.
- **Deferred:** Full conversion of remaining legacy-wrapped steps; parity tooling for `run_single_step` vs engine (see [MIGRATION_STATUS.md](MIGRATION_STATUS.md)).
