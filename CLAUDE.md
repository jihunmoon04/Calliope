# Calliope — working rules

- **Current vs history.** Only `docs/design/` states current requirements and decisions. The MVP
  (code, tests, `benchmarks/`, `docs/legacy/`) is history at the tags `legacy-final` and
  `legacy-mvp-g0`: cite it as evidence by path and tag, never as current authority. A cited path
  under `docs/legacy/`, a removed `src/calliope/` module, `tests/unit/`, `tests/integration/`,
  `tests/golden/` or `benchmarks/` is read with `git show legacy-final:<path>`. Rules:
  `docs/README.md`.
- New design documents go to `docs/design/` and are listed in `docs/design/README.md`.
- `src/calliope/` holds only the redesign packages (`facts`, `reasoning`, `results`, `server`);
  their import rules are enforced by `tests/test_package_boundaries.py`.
- Work proceeds in reviewed packets: design document → independent review (READY or
  READY_WITH_CORRECTIONS) → implementation packet → review.
