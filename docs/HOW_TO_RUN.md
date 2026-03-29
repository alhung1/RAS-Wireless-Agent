# How to run LabVIEW automation

Assume repository root and venv activated. On Windows, use `.\.venv\Scripts\python.exe` if needed.

## Single profile (YAML → StepEngine)

Runs **`build_default_sequence()`** (19 steps) with preflight.

```powershell
cd "c:\Projects\RAS Wireless Agent"
python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml
```

**Dry-run (preflight only — no step execution, no LabVIEW required for steps):**

```powershell
python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --dry-run
```

**Custom artifacts directory:**

```powershell
python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --artifacts artifacts/my_run
```

Output: `artifacts/.../run.json` and per-step folders under `artifacts/.../steps/`.

## Matrix (multiple profiles)

**Dry-run entire matrix (preflight per profile, no GUI):**

```powershell
python scripts/run_matrix.py --dir profiles/test_matrix/ --dry-run
```

**Explicit YAML list:**

```powershell
python scripts/run_matrix.py profiles/test_matrix/be200_2g.yaml profiles/test_matrix/be200_5g.yaml profiles/test_matrix/be200_6g.yaml
```

**Continue after a failed profile:**

```powershell
python scripts/run_matrix.py --dir profiles/test_matrix/ --continue-on-failure
```

Summary written to `artifacts/matrix/` (default) as **`matrix_summary.json`** (override with `--artifacts`).

## Resume from step

**Profile runner** — run steps N–18:

```powershell
python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --start-from 5
```

## Single step

**Profile runner** — execute only step index **N** (0-based):

```powershell
python scripts/run_profile.py profiles/test_matrix/be200_2g.yaml --step 14
```

Requires LabVIEW/window state appropriate for that step.

## Validate profiles (no GUI)

```powershell
python scripts/validate_profiles.py profiles/test_matrix/be200_2g.yaml
python scripts/validate_profiles.py --dir profiles/test_matrix/
```

## Legacy-compatible entry points

**Module CLI (uses `ui_flow.yaml` defaults + argparse):**

```powershell
python -m orchestrator.local_automation.labview_runner --band 2.4G --dry-run
python -m orchestrator.local_automation.labview_runner --all-bands --dry-run
```

**Fast preflight-only check (skip all 19 steps):**

```powershell
python -m orchestrator.local_automation.labview_runner --dry-run --band 2.4G --skip-to 19
```

**Scripts:**

```powershell
python scripts/run_24g.py
python scripts/run_24g.py --wifi-worker http://192.168.22.203:8080 RS700_2G YourPassword
python scripts/run_labview_all_bands.py --dry-run
python scripts/run_labview_all_bands.py --bands 2.4G 5G --config orchestrator/local_automation/ui_flow.yaml
```

**`run_24g_live.py`:** runs immediately (full wizard, **no** finish wait); no CLI flags.

Legacy flows write **`result.json`** + **`run.json`** under `artifacts/labview/<timestamp>/` (or your `artifacts_base`). See [LABVIEW_RUNNER.md](LABVIEW_RUNNER.md).

## Compatibility smoke (CI-friendly)

```powershell
python scripts/smoke_labview_compat.py
```

Checks imports, `--help` on selected scripts, and module dry-run with `--skip-to 19`.

## Environment

- **`LV_PRODUCT`** — product adapter id for **`run_labview_flow`** (default `INTEL_BE200`). See [LABVIEW_RUNNER.md](LABVIEW_RUNNER.md).
- **`LV_STOP_FILE`** — emergency stop file path (see `labview_runner_legacy.STOP_FILE`).
- Secrets: use **environment variables** / `.env` per repo rules; never commit credentials.
