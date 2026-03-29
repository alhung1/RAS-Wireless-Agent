# Architecture summary (as implemented)

This describes the **current** LabVIEW automation stack, not the original design doc alone.

## Layer overview

```text
profiles/ (YAML)          Test + product data, Pydantic schema
        ↓
profiles/loader.py        resolve_run_config, get_product_adapter, register_product
        ↓
products/ (ProductBase)   BE200Adapter: bands, channels, modes, paths, VerificationSpecs
        ↓
engine/context.py         StepContext, engine RunConfig
engine/step_engine.py     Preflight, execute_step (precondition → execute → verify → recover)
engine/preflight.py       Static checks (product, band, mode, channel, templates, paths, OCR)
engine/report.py          Engine RunReport → run.json
engine/matrix_runner.py   Sequential multi-profile runs → matrix_summary.json
        ↓
steps/registry.py         Ordered list: native BaseStep + LegacyStepWrapper
steps/base.py             BaseStep, LegacyStepWrapper (legacy fn → StepResult)
steps/s*.py               Native step implementations + verification
        ↓
ui/                       window_manager, input_helpers, verification (OCR, pixel_diff), coordinates
recovery/                 Diagnosis types used by engine recover hooks
        ↓
labview_runner_legacy.py  Legacy step_* functions, globals, STEP_SEQUENCE, prepare_labview_session
labview_runner.py         Thin facade: bridge to StepEngine + result.json + wait_for_finish
```

## Profiles and adapters

- **Test profiles:** `profiles/test_matrix/*.yaml` (e.g. `be200_2g.yaml`) — band, channels, mode, attenuation, finish detection, etc.
- **Product profiles:** `profiles/products/be200.yaml` — optional merged defaults.
- **Adapters:** `products/be200.py` implements **`ProductBase`**: `supported_bands`, `valid_channels`, `valid_modes`, `verify_*` specs for OCR/pixel regions calibrated for BE200 + LabVIEW layout.

## Step engine

- **`StepEngine.run(start_from=N)`** — full sequence or resume.
- **`StepEngine.run_single(i)`** — one step (used by `run_profile.py --step`).
- **Critical steps** (`is_critical=True`) must pass **verification** evidence or the step is marked failed.

## UI and verification

- **OCR:** Tesseract via `pytesseract`; LabVIEW-tuned preprocessing in `ui/verification.py` (scale, threshold, invert, digit normalization).
- **Pixel diff:** Fallback or primary where OCR is unreliable; can report `pixel_diff_inconclusive` when pixels do not change but semantics are unclear.

## Recovery

- **Between retries:** `BaseStep.recover(ctx, diagnosis)`; legacy wrappers use default/light recovery.
- **Legacy module** still contains popup dismissal and window helpers used inside `step_*` and native steps.

## Migration status (native vs legacy)

**Native `BaseStep` implementations** (mixed into the same 19-step index as legacy):

| Index | Step id | Notes |
|------:|---------|--------|
| 0 | `s00_attach` | Window attach + baseline screenshot (`AttachStep`) |
| 5 | `s05_freq_channel` | Per-field verification; `user_info` optional for overall pass |
| 6 | `s06_select_ap` | Folder navigation + popup closure checks + AP OCR |
| 11 | `s11_band_select` | Pixel-diff-first for tiny dropdown (see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)) |
| 14 | `s14_mode` | |
| 15 | `s15_attenuation` | |

**Still `LegacyStepWrapper`** (call `labview_runner_legacy.step_*`): **1–4, 7–10, 12–13, 16–18** (13 steps).

**Live validation (project milestone):** Critical native steps and continuous **0–15** mixed-engine flow were live-validated on the reference LabVIEW machine with OCR and popup handling; full **0–18** including long **finish detection** is environment-dependent.

## Production vs deferred

| Area | Status |
|------|--------|
| Profile load + preflight + StepEngine + matrix runner | **In use** |
| BE200 adapter + YAML profiles | **In use** |
| Legacy facade + `result.json` | **In use** (backward compatibility) |
| Remaining steps as native `BaseStep` | **Deferred** (wrappers sufficient for stability) |
| `labview_runner.py` slim further / remove legacy module | **Not required** for current milestone |
