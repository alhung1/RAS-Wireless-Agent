# LabVIEW Automation Safety Guide

## Emergency Stop

### Stop File

Create the file `artifacts/STOP` (or the path set in the `LV_STOP_FILE`
environment variable) to halt the runner immediately.

**CLI shortcut:**

```bash
python -m orchestrator.local_automation.labview_runner --stop
```

The runner checks for this file:

- At the start of `run_labview_flow`
- Before every step iteration
- Before every mouse click, key press, and text input (`_safe_click`,
  `_safe_press`, `_safe_type`, `_safe_triple_click`, `_safe_hotkey`)

When the file is detected the runner raises `EmergencyStopError`, saves
the current run report to `artifacts/`, and exits without retrying.

**To resume** after a stop: delete the stop file, then re-launch.

### pyautogui Corner Failsafe

`pyautogui.FAILSAFE` is set to `True`. Moving the physical mouse to the
top-left corner of the screen `(0, 0)` during any pyautogui call will
raise `FailSafeException` and abort the current action.

---

## Dry-Run Mode

Launch with `--dry-run` to exercise the full step sequence **without any
mouse or keyboard input**.

```bash
python -m orchestrator.local_automation.labview_runner --dry-run
```

In dry-run mode every step:

1. Captures a screenshot of the current LabVIEW window (read-only).
2. Annotates it with red crosshairs and labels at each intended click
   target using OpenCV drawing primitives.
3. Logs every decision: click coordinates, key presses, text to type.
4. Saves the annotated screenshot to the artifacts directory
   (e.g. `step_06_step_06_select_ap_dryrun.png`).
5. Performs **zero** `pyautogui` calls (no clicks, no key presses,
   no typing, no clipboard writes).

Use dry-run to verify that template images are captured correctly and
that click targets are reasonable before committing to a live 4-hour
test run.

---

## Safety Layers

| Layer | What it does |
|---|---|
| Stop file check | Before every action, abort if `artifacts/STOP` exists |
| `pyautogui.FAILSAFE` | Mouse-to-corner abort |
| Bounds validation | Reject clicks whose absolute coordinates fall outside the LabVIEW window rect |
| Strict template mode | Critical steps (AP select, client select, band select, final start) refuse to blind-click when the template image is not found |
| No blind scroll | Steps 06 and 08 fail instead of blindly scrolling when OCR cannot find the target AP/client |
| Post-action OCR verify | After AP selection, client selection, and dropdown changes, OCR confirms the correct value is on screen |
| Pre-flight check | Step 18 OCR-verifies AP name and mode on the summary screen before clicking Start |
| Strict OCR mode | `_verify_typed_value` and `_verify_dropdown_selection` return `False` (not optimistic `True`) when OCR is unavailable and the step is critical |

---

## Operator Checklist (Before First Run)

1. **Capture template images.**
   Run `python scripts/capture_templates.py` with LabVIEW open on each
   wizard screen. Without templates, strict mode will fail every
   critical step. See `orchestrator/local_automation/templates/README.md`
   for the full list of required templates.

2. **Install Tesseract OCR.**
   Ensure `tesseract` is on the system PATH. Without it, OCR
   verification is unavailable and strict-mode steps will fail.

3. **Verify display settings.**
   The automation assumes a 2560x1440 display at 125% DPI scaling with
   the LabVIEW window at position (0, 0). If your setup differs, adjust
   the pixel coordinates in `orchestrator/local_automation/ui_flow.yaml`.

4. **Delete any stale stop file.**
   Remove `artifacts/STOP` if it exists from a previous run.

5. **Run a dry-run first.**
   Use `--dry-run` to confirm all click targets are correct before a
   live run. Inspect the annotated screenshots in the artifacts folder.

6. **Keep the mouse away from the automation area.**
   During a live run, avoid moving the mouse into the LabVIEW window
   area. The automation does not lock the pointer.

7. **Monitor the run.**
   Watch the JSON-line log output for `[DRY-RUN]` prefixes (in dry-run
   mode) or for `bounds_reject` / `strict_fail` / `ocr_fail_safe`
   messages during live runs. These indicate safety guards activated.

---

## Residual Risks

Even with all safety layers in place, the following risks remain:

### pyautogui is inherently system-wide

There is no Win32 API to send mouse clicks exclusively to a single
window. If LabVIEW loses focus in the milliseconds between the
`_force_fg()` call and the `pyautogui.click()`, input may land on
another application. The bounds check mitigates this (rejecting clicks
outside the window rect) but cannot fully eliminate the race window.

### Template images must be captured manually

Until `scripts/capture_templates.py` is run on the live machine, all
template matching returns `None` and strict mode causes every critical
step to fail. This is by design (fail-safe), but operators must be
aware that a fresh machine requires template capture.

### OCR accuracy depends on Tesseract and screen DPI

OCR on LabVIEW custom controls may misread characters (e.g. `0` vs
`O`, `1` vs `l`). Fuzzy matching is in place, but edge cases remain.
If OCR consistently misreads a specific control, consider adding a
template-based alternative for that field.

### LabVIEW version changes

Any LabVIEW update can move controls, rename VIs, or add new popup
windows. All hardcoded pixel coordinates and title hints become stale.
After a LabVIEW update, re-run `capture_templates.py` and verify with
`--dry-run` before live testing.

### Single-machine coupling

The automation assumes a specific display resolution (2560x1440) and
DPI scaling (125%). Running on a different machine requires:
- Re-calibration of all pixel coordinates in `ui_flow.yaml`
- Re-capture of all template images
- Verification via `--dry-run`

### Clipboard overwrite

The `type_via_clipboard()` function in `screen_utils.py` silently
overwrites the system clipboard contents. Avoid copying sensitive data
to the clipboard while the automation is running.

### No input locking

The automation cannot prevent the operator (or other software) from
moving the mouse or pressing keys during a run. Accidental human input
can derail the wizard mid-step. The retry logic will attempt recovery,
but the test configuration may be corrupted.

---

## File Reference

| File | Purpose |
|---|---|
| `orchestrator/local_automation/labview_runner.py` | Main runner with all safety wrappers and step functions |
| `orchestrator/local_automation/screen_utils.py` | Screenshot capture, template matching, OCR utilities |
| `orchestrator/local_automation/ui_flow.yaml` | Pixel coordinates and band-specific configuration |
| `orchestrator/local_automation/templates/` | Template images for visual element matching |
| `scripts/capture_templates.py` | Guided template capture from live LabVIEW |
| `artifacts/STOP` | Emergency stop file (create to halt, delete to resume) |
