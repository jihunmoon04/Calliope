> **Legacy note.** `unit/`, `integration/` and `golden/` test the MVP-era implementation, which is frozen (tag `legacy-mvp-g0`); the layer plan below is MVP-era and not current. Tests of the redesign live under `tests/facts/` (and later one directory per block). `test_package_boundaries.py` keeps the redesign and the legacy code from importing each other. See [`docs/README.md`](../docs/README.md).

# Tests

Planned layers:

- `unit/`: pure domain and deterministic service tests
- `integration/`: python-chess and real Stockfish adapter tests
- `golden/`: curated positions with expected/forbidden claims
- `adversarial/`: unsupported-claim and LLM-verbalization tests

The primary correctness oracle is the set of evidence-backed chess claims, not exact generated wording.
