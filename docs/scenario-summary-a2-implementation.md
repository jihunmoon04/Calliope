# Internal scenario summary — A2 implementation evidence

Status: IMPLEMENTED_AWAITING_INDEPENDENT_A3_REVIEW.
Date: 2026-10-08 (Korea). A1 prerequisite: independent READY of PR #29
`c99d6a3`, supplied by the user. This document is authored implementation evidence,
not an independent implementation verdict.

## 1. Result and boundaries

`ScenarioLineAnalyzer.analyze(ScenarioRequest)` answers an EXCHANGE question about
a focus square in one supplied legal line. It retains all N+1 activity frames,
physical participants, capture/transition events, focus snapshots, relevant step
changes, separately selected endpoints and complete compressed feature tracks.
The internal English renderer emits source-linked, fixed observational sentences.

These are direct internal imports. Public schema 0.2, composition, facade,
P4-P12 and package exports are unchanged. No scenario record becomes a P10 claim
or public P12 commentary. No engine or LLM is called. Korean localization,
alternative-line comparison and verified positional hypotheses are later packets.

The A1 v2 JSON is unchanged: expectations were frozen before implementation.
Design and implementation have separate branches/PRs; A2 starts from c99d6a3.
Main remains dffd550 until the appropriate review/integration gates are resolved.

## 2. Source map

| Module | Responsibility |
| --- | --- |
| `domain/analysis/scenario.py` | Frozen request, closed enums, typed property/event/count keys and values, ten separate SourceRef variants, local shape/canonical checks, summary/report records |
| `services/position/scenario.py` | One ActivityLineAnalyzer invocation; retained P4/P5/activity/history reconciliation; shared enumeration/projection; private EXCHANGE policy; exact replay-free summary recomputation and reference resolution |
| `services/position/scenario_renderer.py` | Validates the entire summary before rendering; closed English value/event/count templates; digest + detail; resolves all sentence references without adapters |
| `errors.py` | Calliope-owned invalid-request and invalid-summary errors |

`selection_accounting` is an immutable ordered tuple of AccountingRow records,
grouped by the five closed Bucket values; each bucket/family row always exists,
including zero rows. `candidate_keys`, `included_keys`, `excluded_keys` are exact
canonical partitions. Counts are derived properties, preventing stale stored
lengths. Row type/family combinations are closed. The validator compares complete
records with a fresh projection, so equal counts with different keys cannot pass.

Fact values wrap identity-bearing observations explicitly. A PhysicalRay retains
the SliderRay plus its base source and near-to-far physical occupants. A history
run retains a Fact for every frame in the run: compression groups equal values
without dropping frame-specific provenance. Relevant step keys point back to the
selected changes and their reasons; contextual frames do not count as new selections.

The integrity boundary reuses the existing positional F1 correspondence check,
activity F1/F2 local records and move/capture binding checks; it reconciles exact
inverse identities and physical histories without a second board replay.
Source resolution distinguishes captured/empty/not-applicable from unknown selectors.

## 3. A1 review notes resolved in actual acceptance

- N1: 15 color/rank mirrors transform exact participant squares (then canonical
  sort), status, victim-type losses, material, included/excluded/absent keys,
  physical pin triples, ray directions, transient tracks and special-move context.
- N2: required_templates for E12/E15 are checked against the actual report;
  true/false observational pin sentences and rook-only castling context pass.
- E05: CAPTURE_EP is mandatory in digest with both landing and victim square,
  while participation/focus losses remain empty.
- E06: promotion/capture retains one physical pawn-to-queen history; captured
  queen losses remain distinct from the endpoint pawn count delta.
- E09: the report retains geometric knight attack and empty current legal
  capture list with explicit side-to-move labels.
- E12: pin [false,true,false,false,false] is one temporary track, with no
  endpoint pin candidate and no selected king MOVE.
- E15: only the participant rook transition is selected at castling; the actual
  parent UCI e1g1 is labelled move context and h1-to-f1 remains explicit.

## 4. Executed verification

Explicit worktree PYTHONPATH points at this checkout's src; Python runs in UTF-8
mode with bytecode/cacheprovider disabled. Editable installation source is not used.

- **88 A2 tests passed**: 30 frozen base/mirror acceptance cases and 58 request,
  mutation, integrity, no-extra-port-call, template/source/sentinel coverage and
  0/1/64/256-ply retention tests.
- **2,956 tests passed / 0 failed** across tests/unit, tests/golden,
  tests/integration/python_chess and tests/integration/test_analyze_move_slice.py.
- All 22 TemplateIds, all ten SourceKinds and all three sentinels are exercised
  by actual reports/summary tracks; caller SAN is neither identity nor rendered text.
- Mutation checks reject omissions, extra events, wrong endpoint/track membership,
  loss/material/status partitions, wrong versions, incomplete accounting and
  same-count wrong keys, missing mixed provenance, wrong values/anchors/reasons,
  physical-history/identity/activity corruption and inconsistent request bindings.
- A spy checks exactly one ActivityLineAnalyzer invocation; subsequent projection,
  validation, rendering and reference resolution pass with all rules-port methods
  replaced by failures.
- Changed Python Ruff check/format and git diff --check pass.

This run excludes real Stockfish integration. No full pytest, fuzz, CI run or
production performance guarantee is claimed. New modules introduce no engine path.

Reproduce correctness with PYTHONPATH=src and Python UTF-8 mode:

```text
python -X utf8 -m pytest -q -p no:cacheprovider tests/unit tests/golden tests/integration/python_chess tests/integration/test_analyze_move_slice.py
```

## 5. Separate projection/render cost smoke

Reproducer: `benchmarks/scenario_summary_smoke.py`.
Raw record: [scenario-summary-a2-cost-smoke.json](scenario-summary-a2-cost-smoke.json).
Windows 11, Python 3.12.14; three repetitions, median. A legal starting-position
knight repetition targets e4 and has no capture/participant. Board replay and
observation are outside BOTH measurements. Projection includes retained-record
validation, selection, accounting and compression. Rendering includes complete
summary recomputation and sentence source resolution, as well as template output.

| Plies | Projection ms | Render ms | Factual sentences |
| --- | ---: | ---: | ---: |
| 0 | 8.909 | 10.016 | 6 |
| 1 | 17.662 | 19.859 | 10 |
| 64 | 629.805 | 686.860 | 456 |
| 256 | 2748.502 | 2952.347 | 1800 |

This is a development smoke for one line shape, including the empty/max-budget
boundaries; it is not a worst-case benchmark. No sentence/track truncation or
validation shortcut was added. At 256 plies, retaining and revalidating all facts
has visible cost; interactive product integration needs its own latency budget.

## 6. A3 handoff and next priorities

Independent A3 review should inspect the complete selection/accounting equality,
absence/provenance boundary, run compression and every template's observational
semantics. Check E05/E06/E09/E12/E15 and the transformed expectations independently;
passing authored tests alone does not establish READY. Review cost limits before
public integration. Integrate the reviewed A1 prerequisite and retarget A2 to main
as needed; no merge is performed by this implementation packet.

After A3 READY, prioritize reviewed Korean presentation and a bounded supplied-line
comparison packet. Stronger claims about safety, forced loss or the quality of a
positional change require separately verified hypotheses; no engine score or
fluent wording substitutes for that evidence.
