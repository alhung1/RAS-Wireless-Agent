# Known limitations

Operational and technical constraints of the **current** implementation. Use this for triage and roadmap prioritization.

## s11 band select: pixel-diff-first by design

**`BandSelectStep` (`s11`)** uses **pixel diff** on small dropdown regions because LabVIEW’s rendered text is often too small for reliable OCR. The BE200 adapter exposes distinct regions per **`dropdown_id`** (2G vs 5G).

- **Implication:** Evidence may be **`pixel_diff_inconclusive`** when the UI does not change (e.g. value already correct) — the report is honest about limited semantic proof.
- **Not a bug:** Moving to OCR would require display/capture changes or different UI hooks.

## `user_info` (s05): optional for overall step pass

In **`FreqChannelStep`**, **`user_info`** is treated as **optional** for aggregate success: OCR alignment for that free-text field is difficult; the step can pass while **`user_info`** field evidence is weak or skipped from blocking logic.

- **Implication:** Do not rely on **`user_info`** verification alone for compliance-critical strings without further calibration.

## Live matrix: finish detection and LabVIEW restart

**`run_matrix.py`** runs profiles **sequentially**. Each profile run that goes through the full wizard may invoke **finish detection** (PDF / file poll) where configured.

- **Implication:** Multi-band or multi-profile **live** runs require a **known-good LabVIEW return path** to the start screen (or process restart) between profiles. The matrix runner does **not** automatically restart LabVIEW between entries.
- **Mitigation:** Operational playbook (restart VI or exe), or keep matrix to **dry-run** for CI, or single-profile live runs until orchestration is extended.

## Dry-run screenshot difference (legacy facade)

**`run_labview_flow(..., dry_run=True)`** via the **StepEngine** path does **not** emit the historical **per-step annotated dry-run PNGs** from the old inline loop.

- **Implication:** Operators who relied on those artifacts should use **live logging**, **`run.json`** step entries, or reintroduce a dedicated hook if needed.

## `run_single_step.py`: still direct-call

**`run_single_step.py`** imports **`STEP_SEQUENCE`** and invokes **`step_fn(hwnd, cfg, ad)`** directly — **not** `StepEngine`.

- **Implication:** Behavior can **diverge** from production (no engine retry/verify/recover, different dry-run globals). Use for **calibration** with awareness; prefer **`run_profile.py --step N`** for engine parity when debugging the real path.

## Preflight vs old scripts

Facade-driven runs always run **preflight** (templates optional, paths/exe/band/mode/channel enforced as coded). Older mental models of “skip checks and hit UI” may see **earlier failures** — usually desirable.

## Coordinate / template coupling

Legacy and native steps still depend on **fixed VI size**, **template assets** under `orchestrator/local_automation/templates/`, and **absolute coordinates** in legacy code. Resolution or theme changes break automation until recalibrated.

## OCR environment

Tesseract must be installed and discoverable (see `screen_utils` / env). Missing OCR downgrades verification behavior (warnings in preflight); some paths fall back to pixel diff.
