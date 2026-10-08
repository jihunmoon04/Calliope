# Calliope documentation

Calliope is being rebuilt from the ground up as composable blocks with one role each. The
documentation is split into two areas that must never be mixed:

| Area | Status | What it contains |
| --- | --- | --- |
| [`design/`](design/README.md) | **CURRENT** | Design packets of the redesign. These are the only documents that state current requirements and decisions. |
| [`legacy/`](legacy/README.md) | **LEGACY — FROZEN** | Documents of the MVP-era implementation (P0–P12, G0, positional / scenario / observation work). Historical reference only. |

## Rules

1. **Only `design/` is current.** A statement in `legacy/` is never a requirement, decision or
   contract of the redesign, even when it is correct and even when no current document says
   otherwise. If a legacy idea is still wanted, a `design/` document must restate it.
2. **Legacy documents are frozen.** They are not edited, except for the legacy banner and path
   fixes from moving them. Every legacy document starts with a `LEGACY — FROZEN` banner.
3. **Citing legacy.** A current document may cite a legacy document as *evidence* (for example a
   problem found in the MVP), always with its `docs/legacy/...` path, never as authority.
4. **New documents go to `design/`** and are listed in [`design/README.md`](design/README.md) with
   their status.

## Code

| Code | Status |
| --- | --- |
| `src/calliope/facts/` and later redesign packages (when they exist) | current, described by `design/` |
| everything else under `src/calliope/` (`adapters`, `application`, `domain`, `services`, `composition.py`, `contracts.py`, `engine.py`, `errors.py`) | legacy MVP, frozen; kept runnable until the redesign replaces it, then removed |

The legacy implementation and its documents are preserved at the git tag `legacy-mvp-g0`.
Abandoned design directions are preserved as tags `abandoned/*` (for example
`abandoned/analysis-trace-a0`, `abandoned/analysis-trace-r1d`); they are neither current nor
legacy implementation documents.
