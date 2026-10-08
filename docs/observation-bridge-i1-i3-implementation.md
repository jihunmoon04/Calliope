# Observation bridge I1–I3 — integrated implementation evidence

Status: **IMPLEMENTED / READY_FOR_INDEPENDENT_REVIEW** (authored evidence, not an independent verdict).
Date: 2026-10-08. Branch `implementation/i1-i3-observation-bridge`, base `bf43f27`
(PR #33 final head; PR #31 A0, PR #32 I1-D and PR #33 I2-D/I3-D independently READY, all unmerged).
Normative contracts: [A0](observation-commentary-bridge-design.md),
[I1-D](observation-i1d-played-transition-freeze.md),
[I2-D/I3-D](observation-bridge-i2i3-joint-design.md),
[handoff](observation-bridge-i1-i3-implementation-handoff.md). Frozen corpora were not edited.

## 1. Commits

| Commit | Scope |
| --- | --- |
| I1 `c8780c0` | `PLAYED_TRANSITION`, `PlayedMoveTarget`, `PlayedTransitionDetail`, closed kind/target/detail/version contract, effect-complete 21-row census, `PLAYED_CHANGE` reason, presentation ledger, `PLAYED_STATUS`/`PLAYED_CHANGE` rendering, D01–D20 and D17 byte oracle |
| I2 `dfc36eb` | `ExchangeObservationInput`/`LineOrigin`, `ExchangeObservationSelector` with tiers 0..7 (incl. 4.5), dependency closure, `EXCHANGE_OBS_CHANGE`, E01–E15 acceptance |
| I3 (this commit) | schema-0.3 DTOs, `ObservedMoveService`, `CalliopeEngine.analyze_move_with_observations`, composition reuse, closed `obs.v1` id and SourceRef projection, DTO golden, real-Stockfish gate, cost record |

## 2. Module map

| Module | Change |
| --- | --- |
| `domain/analysis/scenario.py` | additive enum members (kind, reason, templates), `is_canonical_uci`, PLAYED target/detail, ledger records (`PresentationCandidate`, two selections, `CompactObservation`), `ExchangeObservationInput`, public `candidate_index` alias |
| `services/position/scenario.py` | `properties(..., families)` parameter (EXCHANGE default unchanged), closed `_project` dispatch, `_build_played`, `material_count_facts`, kind-contract check before exact re-projection |
| `services/position/scenario_observation.py` (new) | both selectors, value grammar, compact sentences, PLAYED report, recompute-and-compare validators |
| `services/position/scenario_renderer.py` | one PLAYED dispatch branch before the untouched EXCHANGE body; `validate_rendered_report` |
| `contracts.py`, `errors.py`, `engine.py`, `composition.py`, `__init__.py` | additive v0.3 DTOs, `ObservationProjectionError`, opt-in facade method/use-case slot, observation graph over the shared rules/facts/delta, exports |
| `application/observe_move.py` (new) | preflight, sequential legality, legacy call, post-session observation, closed projection, atomic failure |

`AnalyzeMoveService.execute`, P4–P12 code, `AnalysisOptions`, `MoveAnalysisResult`,
`CommentaryView` and `PUBLIC_SCHEMA_VERSION = "0.2"` are unchanged.

## 3. Acceptance evidence (executed on this branch)

Environment: explicit `PYTHONPATH=<worktree>/src` (import path printed and verified), Python 3.12.3,
UTF-8 mode, bytecode and pytest cache disabled.

- **Corpus checkers:** both I1-D and joint checkers pass `--schema-only` and `--full`
  (also asserted by `tests/golden/test_observation_dto_golden.py`).
- **I1 D01–D20:** frozen participants (set semantics as in the corpus checker; canonical base
  order per the detail contract), critical keys, ledger dispositions, exact digest text, status
  provenance; D06-q/r/b/n and D13 complete census, ranked eligible order and every disposition;
  plus an independent python-chess census of *every* positive case (all changed facts, events,
  materials, then the frozen rank/cap/duplicate rules). D19 discovered pin/ray and D20 remote
  passed pawn are core-included. D14 variants reject with zero activity calls; D15 uses the
  existing legality error; D16's twelve mutations raise `InvalidScenarioSummaryError`.
- **D17:** `tests/golden/scenario_exchange_v1_baseline.json` was captured at `bf43f27` before any
  source edit; E01–E15 `ScenarioSummary`/`RenderedScenarioReport` `repr` hashes, digest pairs
  and detail text are identical.
- **I2 E01–E15:** selected keys, TemplateIds, exact English, status/count, first source kind,
  cap/context/duplicate dispositions, ledger == every core-included key, sources equal the
  underlying records. E06 = CAPTURE ply1 + PROMOTION ply1 (capture ply2 CAP_EXCEEDED); E08 =
  off-focus CAPTURE + FOCUS_OCCUPANT step (MATERIAL context-only).
- **I3:** the complete v0.3 DTO golden matches byte-for-byte under the frozen canonical
  serialization; unit tests cover nesting, both output modes, preflight (12 malformed shapes, zero
  work), illegal played/supplied moves before any legacy or engine call, rules work strictly
  outside the session, atomic failure, anchor mismatch, closed id/source grammar and that the
  legacy full-detail renderer is never reached.
- **D18 / real Stockfish (Stockfish 17, built from the official `sf_17` tag for aarch64):**
  the pre-change capture (`bf43f27`, 11 G0 fixtures × 2 modes) was reproduced byte-identically
  twice. On the final code, `analyze_move` and the nested `base_result` of the opt-in method are
  both **22/22 DTO-identical** with **identical engine/session sequences (100 vs 100 analyses)**.
  `tests/integration/stockfish/test_observed_move_public.py` (23 tests) passes: identical nested
  results and Stockfish call sequences, all engine calls inside sessions, every observation-side
  rules call outside them, illegal supplied line → zero engine calls.
- **Targeted totals:** `tests/unit tests/golden` 3163 passed. `tests/integration` with Stockfish:
  120 passed, 7 failed — the same 7 fail identically at `bf43f27` with this binary (G0
  `tested_material_threat`/`tested_mate_threat`/`multipv_one` P9 claims and two P2-C1 inversion
  fixtures are engine-build dependent); none involve changed code.
- Ruff check/format on changed Python files and `git diff --check` pass.

## 4. Cost record (PR #30 L4/L6 admission input; reviewer sign-off required)

Raw record: [observation-bridge-i1-i3-cost.json](observation-bridge-i1-i3-cost.json);
reproducer `benchmarks/observation_bridge_cost.py`. Host: aarch64 Linux, 2 logical CPUs, 11 GiB,
Python 3.12.3. Worst permitted request: played `f3e5` plus two explicit 8-ply capture-heavy
EXCHANGE lines from one Italian-game root, COMMENTARY, depth 12 / MultiPV 3. 3 warm-up then 20
measured repetitions; medians (p95):

| Component | played (1 ply) | line x0 (8) | line x1 (8) |
| --- | ---: | ---: | ---: |
| replay (ActivityLineAnalyzer) | 16.9 (18.4) | 85.3 (97.6) | 88.8 (104.4) |
| projection incl. retained-observation validation | 39.8 (53.9) | 193.8 (212.7) | 192.0 (215.5) |
| full summary re-validation | 49.9 (51.4) | 226.6 (257.3) | 221.1 (237.2) |
| ledger | 2.7 (2.9) | 6.6 (8.0) | 5.6 (6.9) |
| compact render incl. ledger + source resolution | 3.2 (3.6) | 7.9 (8.5) | 6.8 (7.4) |
| DTO projection | 0.04 | 0.05 | 0.05 |

Preflight (shape + full sequential legality): 4.4 ms (4.6). Observation-only total
(legacy result precomputed): 1151.9 ms median (1206.9 p95); cold first run 1172.0 ms.
Real Stockfish: legacy `analyze_move` 470.9 ms (537.8), opt-in 1625.9 ms (1658.4), paired delta
**1150.5 ms (1167.8)**; legacy cold 472.5 ms. Legacy full-detail renderer calls on the public
path: **0**. Internal EXCHANGE stress medians (projection / compact incl. validation, ms):
0 → 20 / 22, 1 → 42 / 45, 8 → 190 / 209, 16 → 378 / 388, 64 → 1445 / 1525, 256 → 6170 / 6422.

Interpretation: cost is dominated by complete integrity validation, which runs once inside
`ScenarioLineAnalyzer.analyze` and again inside `compact_observations` (required by I2-D/I3-D:
the compact path must fully re-validate). No validation was skipped or cached. Whether ~1.15 s
on this host is acceptable for public opt-in is the reviewer's L4 decision; any validated-summary
token or cache needs a separate design review.

**L6 ownership.** The new application module imports only public names
(`ScenarioLineAnalyzer`, `compact_observations`, domain records). `scenario_observation.py` uses
same-package private helpers (`_Projection`, `_refs`, renderer `_event`/`_count`/`_sentence`)
and one deferred import from the renderer to avoid a module cycle. The pre-existing PR #30 L6
cross-module imports in `scenario.py` are unchanged; no shared-helper refactor was done.

## 5. Design deviations and interpretations (for review)

1. `PresentationCandidate` stores `rank` (integer tuple; EXCHANGE tier 4.5 encoded as ordinal 5 of
   0..8), `frames`, `duplicate_of`; the I1-D `semantic_key` is not a stored field — duplicate
   identity is recomputed and recorded as the typed `duplicate_of` anchor.
2. The joint checker re-labels an already-selected promotion as CAP_EXCEEDED if it is met again
   after the cap fills; the implementation keeps it INCLUDE ("the selected block is never
   reordered"). No corpus case is affected.
3. Underspecified grammar resolved by reusing the closed EXCHANGE_OBS_CHANGE physical form:
   RAY_STATE occupants render as `{color} {type} on {square} (initially {base})`; the frozen
   label for a RayKey omits its direction (two rays of one piece differ only in state text).
4. `PlayedTransitionDetail` has no material field, so PLAYED MATERIAL_COUNTS sentences are rebuilt
   from the validated observed line (`material_count_facts`), identical to the census source.
5. Corpus participant lists are compared as sets (D04 lists mover first); the detail keeps the
   contract's canonical base-square order.
6. Supplied moves whose adapter-canonical UCI differs from the submitted string are refused as
   noncanonical aliases.
7. `CalliopeEngine` gains an optional `_observed_move_analysis` slot after `_close_hook`;
   without it the new method raises `FeatureUnavailableError`.
8. The existing legacy template-coverage test now excludes the three new non-legacy TemplateIds.

## 6. Review focus

Exactness of the PLAYED census and ranking (D06/D13/D19/D20), E06/E08 dependency closure,
D17/D18 byte evidence, the atomic/post-session ordering in `ObservedMoveService`, the closed
`obs.v1`/SourceRef grammar, the L4 cost above and the L6 helper ownership. Public Korean wording,
the EP duplicate-square English and the `[FAMILY]` labels remain I3 wording debt.
