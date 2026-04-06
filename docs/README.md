# LabVIEW automation documentation (Phase D.3)

Practical docs for the **refactored, config-driven** LabVIEW stack. Prefer these over outdated references to a single monolithic `labview_runner.py` file.

| Document | Purpose |
|----------|---------|
| [LABVIEW_RUNNER.md](LABVIEW_RUNNER.md) | Thin facade vs legacy, compatibility, `LV_PRODUCT`, `result.json` vs `run.json`, gaps |
| [ARCHITECTURE_SUMMARY.md](ARCHITECTURE_SUMMARY.md) | Implemented layers, native vs legacy steps, production status |
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | Commands: profile, matrix, resume, single-step, legacy entry points |
| [HOW_TO_ADD_PRODUCT.md](HOW_TO_ADD_PRODUCT.md) | New `ProductBase`, YAML, registration, verification calibration |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | s11 pixel diff, user_info, matrix/finish, dry-run screenshots, `run_single_step` |
| [MIGRATION_STATUS.md](MIGRATION_STATUS.md) | Phases done, deferred work, file list, risks |
| [RELEASE_NOTES_v1.0.0-labview-refactor.md](RELEASE_NOTES_v1.0.0-labview-refactor.md) | **Milestone release notes** (v1.0.0-labview-refactor) |
| [RELEASE_PROPOSAL.md](RELEASE_PROPOSAL.md) | Tag rationale + pointer to finalized notes |
| [ACCOMPLISHMENT_ENGINEERING.md](ACCOMPLISHMENT_ENGINEERING.md) | Technical handoff summary |
| [ACCOMPLISHMENT_STAKEHOLDER.md](ACCOMPLISHMENT_STAKEHOLDER.md) | Short stakeholder / deck summary |
| [DESIGN_MATRIX_FINISH_ORCHESTRATION.md](DESIGN_MATRIX_FINISH_ORCHESTRATION.md) | Next phase: matrix + finish + inter-profile reset |
| [MIGRATION_LEGACY_STEPS.md](MIGRATION_LEGACY_STEPS.md) | Legacy step buckets; bucket 1 implemented |

**Sample report shapes**

- [samples/example_run.json](samples/example_run.json) — engine `run.json` (abbreviated)
- [samples/example_result.json](samples/example_result.json) — legacy `result.json` (abbreviated)

**Local calibration / diagnostics scripts** (not primary docs): see [../scripts/README_LOCAL.md](../scripts/README_LOCAL.md).

Other files under `docs/` (e.g. worker deploy) are separate concerns.
