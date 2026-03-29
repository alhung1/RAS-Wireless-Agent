# v1.0.0-labview-refactor

## Summary

This release delivers the first production-ready milestone of the LabVIEW automation refactor.

The LabVIEW workflow has been moved from a single monolithic runner into a step-engine architecture with typed context, product adapters, reusable UI primitives, profile-driven execution, live-validated critical-step verification, and backward-compatible entry points.

In practical terms: the critical path is now native, evidence-based, and live-validated on the real LabVIEW system, while legacy usage patterns remain supported through a thin compatibility facade.

## Highlights

- Refactored the LabVIEW automation monolith into:
  - profiles
  - product adapters
  - step engine
  - native step implementations
  - reusable UI primitives
  - recovery / diagnosis helpers

- Completed native implementations for all critical workflow steps:
  - s05_freq_channel
  - s06_select_ap
  - s11_band_select
  - s14_mode
  - s15_attenuation

- Live-validated the mixed engine path through steps 0–15 on the real LabVIEW workflow with:
  - 0 failures
  - 0 retries
  - stable legacy/native transitions

- Added OCR-backed semantic verification for key fields on the live machine, including:
  - frequency range
  - channel values
  - mode
  - attenuation values

- Preserved backward compatibility by splitting:
  - labview_runner.py → thin facade
  - labview_runner_legacy.py → legacy implementation body

- Added matrix/profile execution support and new CLI entry points for profile-driven operation.

- Delivered a practical documentation set for operators, developers, and maintainers.

## What's New

### Native critical-step path
The highest-risk, highest-value workflow steps are now implemented as native BaseStep classes with explicit verification evidence and recovery hooks.

This replaces blind GUI execution on the critical path with step-level verification using OCR and calibrated pixel-diff where appropriate.

### OCR-backed live verification
Tesseract OCR is now integrated and calibrated for the LabVIEW workflow.
Verified live on the real machine:

- s05_freq_channel
  - freq_range
  - channel_2g
  - channel_5g
  - channel_6g
- s14_mode
- s15_attenuation

For s11_band_select, OCR is not practical because the LabVIEW dropdown display area is too small at the current resolution. This step uses calibrated pixel-diff by design.

### Popup / modal-state hardening
Resolved the Step 7 blocking issue caused by lingering AP/Client popup windows by:
- classifying popup-blocked transitions explicitly
- detecting AP/Client popup remnants
- adding popup-close verification after AP selection
- strengthening blocker hints and transition checks

### Thin compatibility facade
labview_runner.py now acts as a thin wrapper that preserves legacy entry points while delegating orchestration to the new architecture:
- config bridge
- product resolution
- preflight
- StepEngine
- dual report output
- optional finish detection

### Matrix runner and execution modes
Added support for:
- single-profile execution
- matrix dry-run execution
- profile validation
- resume-from-step
- single-step execution (engine path)

New entry points include:
- scripts/run_profile.py
- scripts/run_matrix.py
- scripts/validate_profiles.py

## Live-Validated Capabilities

The following have been validated on the live LabVIEW machine:
- continuous mixed-engine execution from step 0 through step 15
- native critical-step verification on the real UI
- OCR-backed semantic verification for calibrated fields
- popup-safe AP selection flow
- stable interoperability between native and legacy-wrapped steps

Notable live result:
- full 0–15 execution passed
- 16/16 steps passed
- 0 failures
- 0 retries

## Documentation Added

This release includes a full documentation set under docs/, including:
- docs/README.md
- docs/LABVIEW_RUNNER.md
- docs/ARCHITECTURE_SUMMARY.md
- docs/HOW_TO_RUN.md
- docs/HOW_TO_ADD_PRODUCT.md
- docs/KNOWN_LIMITATIONS.md
- docs/MIGRATION_STATUS.md

Additional milestone docs:
- docs/RELEASE_PROPOSAL.md
- docs/ACCOMPLISHMENT_ENGINEERING.md
- docs/ACCOMPLISHMENT_STAKEHOLDER.md
- docs/DESIGN_MATRIX_FINISH_ORCHESTRATION.md
- docs/MIGRATION_LEGACY_STEPS.md

Sample reports:
- docs/samples/example_run.json
- docs/samples/example_result.json

## Compatibility Notes

This release preserves the legacy workflow surface while changing the implementation underneath.

Supported now:
- legacy run_labview_flow
- legacy run_all_bands
- python -m orchestrator.local_automation.labview_runner
- YAML/profile-driven execution via run_profile.py
- matrix dry-run via run_matrix.py

Important compatibility notes:
- both run.json and result.json are written
- legacy scripts may now fail earlier because strict preflight is enforced
- native critical steps may fail verification even when legacy execution would have reported success
- per-step dry-run annotated PNG output from the old runner is not fully preserved on the engine path
- run_single_step.py still uses the legacy direct-call path

## Known Limitations

- s11_band_select uses calibrated pixel-diff verification by design; OCR is not reliable for that control at the current UI size
- user_info in s05_freq_channel remains optional because OCR positioning is not yet stable
- live sequential matrix execution still needs finish detection / restart orchestration between profiles
- remaining non-critical legacy steps are still wrapped, not fully migrated
- run_single_step.py has not yet been moved to StepEngine.run_single

## Deferred Work

The following are intentionally deferred beyond this milestone:
- finish detector integration for live multi-profile orchestration
- full live matrix handoff between profiles
- native conversion of the remaining legacy-wrapped non-critical steps
- parity migration for run_single_step.py
- optional restoration of old dry-run per-step annotated PNG behavior

## Why This Release Matters

Before this release, the LabVIEW automation was concentrated in a single large runner with shared global state, mixed responsibilities, and limited step-level verification.

After this release, the system has:
- a typed execution model
- clear separation between profiles, adapters, engine, steps, and UI primitives
- evidence-based verification on the critical path
- backward-compatible entry points
- operator and maintainer documentation
- a clear migration path for future products and remaining steps

This is the milestone where the refactor stops being a design exercise and becomes an operationally usable framework.

## Recommended Next Steps

1. Implement finish detection + live matrix orchestration between profiles
2. Continue incremental migration of the remaining legacy-wrapped steps
3. Consider moving run_single_step.py to StepEngine.run_single
4. Expand product support beyond BE200 using the adapter + profile model

## Tag

v1.0.0-labview-refactor
