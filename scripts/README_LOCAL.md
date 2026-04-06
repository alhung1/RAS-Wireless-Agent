# Local / auxiliary scripts layout

Untracked one-off LabVIEW debug and calibration scripts were grouped (nothing deleted).

| Directory | Purpose |
|-----------|---------|
| [calibration/](calibration/) | Reusable position/UI discovery and step-focused calibration helpers |
| [diagnostics/](diagnostics/) | Click/template/dropdown diagnostics and `debug_runsame*` probes |
| [dev/](dev/) | Small reusable utilities (e.g. live validation harness, login helper, state checks) |
| [_archive_local/](_archive_local/) | Iteration artifacts: numbered `fix_ip_*`, `step_*` variants, one-shot wizard clicks |

**Tracked** entry points stay in `scripts/` root (`run_profile.py`, `run_matrix.py`, `smoke_labview_compat.py`, `calibrate_labview.py`, E2E scripts, etc.).

## Update paths when running

Use repo root as cwd, for example:

```text
python scripts/dev/live_validate_b2.py
python scripts/diagnostics/diag_click.py
python scripts/calibration/calibrate_step03.py
```

## Candidates for deletion (after manual review)

Everything under **`scripts/_archive_local/`** was kept for history but is redundant with the step engine and profiles. Safe to delete in bulk **only after** you confirm no private tweaks you still need:

- All `fix_ip_click*.py`, `fix_ip_screen*.py`, `fix_ip_address.py`, `fix_ip_5g.py`
- Numbered `step_atten*.py`, `step_pairs*.py`, `select_bw20*.py`, `click_*` one-shots, `continue_steps.py`, `finish_setup.py`, `advance_ip.py`, `region_click.py`, `select_us_region.py`, `test_elevated_click.py`

Optional: trim `debug_runsame*.py` in `diagnostics/` if Run Same UI no longer needs investigation.

## `.gitignore`

To keep the archive **only on this machine**, uncomment the line in the repo root `.gitignore` (see comment block there).
