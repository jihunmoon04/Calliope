# Calliope

Calliope is an evidence-first chess commentary engine.

## Status: ground-up redesign in progress

Calliope is being rebuilt as composable blocks with one role each. The first block is the
**fact engine**: python-chess and Stockfish normalize a position and its lines into one tree of
frames that records facts only (rules, versioned definitions, attested engine reports), which
later blocks use without re-validation. Explanation blocks come after it.

| What | Where | Status |
| --- | --- | --- |
| Current design | [`docs/design/`](docs/design/README.md) | **current** |
| New code | `src/calliope/facts/` (from packet F1) | current |
| MVP implementation (P0–P12, G0, schema 0.2 / 0.3) | the rest of `src/calliope/`, `tests/`, `benchmarks/` | **legacy, frozen**; still runnable, removed once replaced |
| MVP documents | [`docs/legacy/`](docs/legacy/README.md) | **legacy, frozen**; reference only, never current requirements |

Rules for telling them apart: [`docs/README.md`](docs/README.md). The MVP state is preserved at
the git tag `legacy-mvp-g0`; the former README is
[`docs/legacy/mvp-readme.md`](docs/legacy/mvp-readme.md).
