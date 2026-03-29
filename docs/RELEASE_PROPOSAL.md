# Milestone release / tag proposal

## Candidate tag names

| # | Tag | Rationale |
|---|-----|-----------|
| A | **`v1.0.0-labview-refactor`** | Clear semver + scope; signals first “complete” packaged state of the refactored LabVIEW stack (engine, profiles, matrix, thin facade, docs). |
| B | **`2026.03-labview-automation`** | Calver-style; easy to correlate with quarter/month without implying full repo 1.0. |
| C | **`ras-agent-0.9.0-labview`** | Pre-1.0 for the whole RAS Wireless Agent repo if other subsystems are not yet tagged 1.0. |

## Recommendation

**Use `v1.0.0-labview-refactor`** (candidate A).

- The milestone is **LabVIEW automation subsystem** completion (config-driven flow, verification, matrix runner, backward-compatible facade), not necessarily the entire monorepo.
- If you prefer **one global repo version** only, use candidate C until router/worker/orchestrator are jointly released.

## Finalized release notes

Authoritative milestone release notes (full text, ready to paste into GitHub Releases):

**[RELEASE_NOTES_v1.0.0-labview-refactor.md](RELEASE_NOTES_v1.0.0-labview-refactor.md)**

---

*Tag and publish when ready; suggested annotated tag: `v1.0.0-labview-refactor` (see release notes file).*
