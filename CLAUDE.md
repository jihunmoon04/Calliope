# Calliope — working rules

- **Current vs legacy.** Only `docs/design/` states current requirements and decisions.
  `docs/legacy/` (banner `LEGACY — FROZEN`) and the MVP code outside `src/calliope/facts/` are
  frozen history (tag `legacy-mvp-g0`): use them as evidence, never as current authority, and do
  not edit them. Rules: `docs/README.md`.
- New design documents go to `docs/design/` and are listed in `docs/design/README.md`.
- `calliope.facts` (and later redesign packages) must not import legacy modules and vice versa;
  `tests/test_package_boundaries.py` enforces it.
- Work proceeds in reviewed packets: design document → independent review (READY or
  READY_WITH_CORRECTIONS) → implementation packet → review.
