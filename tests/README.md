# Tests

Planned layers:

- `unit/`: pure domain and deterministic service tests
- `integration/`: python-chess and real Stockfish adapter tests
- `golden/`: curated positions with expected/forbidden claims
- `adversarial/`: unsupported-claim and LLM-verbalization tests

The primary correctness oracle is the set of evidence-backed chess claims, not exact generated wording.
