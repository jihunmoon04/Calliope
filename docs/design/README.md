# Current design (redesign)

These documents are the **only current** design documents of Calliope. The MVP's documents
(`docs/legacy/`) are history at tag `legacy-final` and never a requirement here (see
[`docs/README.md`](../README.md#history)).

## Direction

Calliope is rebuilt as composable blocks with one role each. Each block is designed in a packet
(design document → independent review READY or READY_WITH_CORRECTIONS → implementation packets,
each reviewed).

## Status and roadmap

[`redesign-status-and-roadmap.md`](redesign-status-and-roadmap.md) — what has been decided and
delivered so far, and the packets that come next. Start here.

## Packets

| Block | Document | Status |
| --- | --- | --- |
| Fact engine | [`fact-engine-a0-design.md`](fact-engine-a0-design.md) | F0 design; A0 review READY_WITH_CORRECTIONS applied (rev. 4) |
| Fact engine F1 | [`fact-engine-f1-implementation.md`](fact-engine-f1-implementation.md) | implemented; independent F1 re-review READY |
| Fact engine F2-D | [`fact-engine-f2-design.md`](fact-engine-f2-design.md) | rev. 2; independent F2-D review READY_WITH_CORRECTIONS applied; merged (#41) |
| Fact engine F2 | [`fact-engine-f2-implementation.md`](fact-engine-f2-implementation.md) | rev. 2; independent F2 review READY_WITH_CORRECTIONS applied; merged (#43) |
| Fact engine F3-D | [`fact-engine-f3-design.md`](fact-engine-f3-design.md) | rev. 2 + errata; independent F3-D review READY_WITH_CORRECTIONS applied; merged (#44) |
| Fact engine F3 | [`fact-engine-f3-implementation.md`](fact-engine-f3-implementation.md) | rev. 2; independent F3 review READY_WITH_CORRECTIONS applied; merged (#45) |
| Fact engine F4-D | [`fact-engine-f4-design.md`](fact-engine-f4-design.md) | rev. 3; independent F4-D review NOT_READY → re-review READY_WITH_CORRECTIONS applied; merged (#47) |
| Fact engine F4a | [`fact-engine-f4a-implementation.md`](fact-engine-f4a-implementation.md) | rev. 2; independent F4a review READY_WITH_CORRECTIONS applied; merged (#48) |
| Fact engine F4b | [`fact-engine-f4b-implementation.md`](fact-engine-f4b-implementation.md) | rev. 2; independent F4b review READY_WITH_CORRECTIONS applied; merged (#50) |
| Fact engine F5-D | [`fact-engine-f5-design.md`](fact-engine-f5-design.md) | rev. 3; independent F5-D review NOT_READY → re-review READY_WITH_CORRECTIONS applied; merged (#52) |
| Fact engine F5 | [`fact-engine-f5-implementation.md`](fact-engine-f5-implementation.md) | rev. 2; independent F5 review READY_WITH_CORRECTIONS applied; merged (#53) |
| Fact engine F6-D (`exchange` family: static exchange evaluation `see_v1`) | [`fact-engine-f6-design.md`](fact-engine-f6-design.md) | rev. 3; independent review NOT_READY → re-review READY_WITH_CORRECTIONS applied; merged (#67) |
| Fact engine F6 (`exchange` family, on-request families) | [`fact-engine-f6-implementation.md`](fact-engine-f6-implementation.md) | rev. 2; independent F6 review READY_WITH_CORRECTIONS applied |
| Reasoning R0-D (contracts: controller, observer, hypotheses, verification, claim graph, planner, renderer) | [`reasoning-r0-design.md`](reasoning-r0-design.md) | rev. 10; merged (#55); amended by R1 (§27) and R2b (§29); BRILLIANT deferred (§28) |
| Reasoning R2-D (observations v1, hypothesis templates v1) | [`reasoning-r2-design.md`](reasoning-r2-design.md) | rev. 11; merged (#56); fifth and sixth independent reviews and their re-checks applied (#58); BRILLIANT deferred (E10); amended by R2b (§12) |
| Reasoning R1 (foundation, round 0, `quality_v1`, facts additions) | [`reasoning-r1-implementation.md`](reasoning-r1-implementation.md) | rev. 2; independent R1 review READY_WITH_CORRECTIONS applied; merged (#57) |
| Reasoning R2a (hypotheses, verification, rounds, claim graph) | [`reasoning-r2a-implementation.md`](reasoning-r2a-implementation.md) | rev. 2; independent R2a review READY_WITH_CORRECTIONS applied; merged (#59) |
| Reasoning R2b (catalogue v1: 21 templates, `line_material`, `played_edge`, `label_v1`) | [`reasoning-r2b-implementation.md`](reasoning-r2b-implementation.md) | rev. 3; independent R2b review NOT_READY applied; re-review READY_WITH_CORRECTIONS applied |
| Reasoning Q-D (rating-aware grade `quality_v2`, curve table and calibration) | [`reasoning-quality-v2-design.md`](reasoning-quality-v2-design.md) | rev. 5; independent Q-D review NOT_READY → two re-reviews NOT_READY → third re-review READY_WITH_CORRECTIONS applied; merged (#62); amended by QM-D (§16) |
| Reasoning Q1 (runtime `quality_v2`: `GradingSpec`, resolution, integer curve, grading through observer and catalogue) | [`reasoning-q1-implementation.md`](reasoning-q1-implementation.md) | rev. 2; independent Q1 review NOT_READY applied; merged (#63) |
| Reasoning QM-D (monotone curve table for `quality_v2`; Q2 tool corrections) | [`reasoning-quality-v2-monotone-design.md`](reasoning-quality-v2-monotone-design.md) | rev. 3; independent QM-D review NOT_READY → re-review NOT_READY applied; merged (#64) |
| Reasoning Q2 (calibration tool, monotone runtime, table `human_lichess_2026_08_v2`, chess.com conversion) | [`reasoning-q2-implementation.md`](reasoning-q2-implementation.md) | rev. 2; independent Q2 review READY_WITH_CORRECTIONS applied; merged (#65) |
| Reasoning Q3 (chess.com acceptance tool; running monitor) | [`reasoning-q3-implementation.md`](reasoning-q3-implementation.md) | rev. 5; grading frozen (owner), Q3 a running monitor; review READY_WITH_CORRECTIONS applied; monitor entries of 2026-10-11 and an engine-depth measurement (§6) |
| Reasoning LV-D (`label_v2`: FORCED, narrower GREAT, provisional BRILLIANT) | [`reasoning-label-v2-design.md`](reasoning-label-v2-design.md) | rev. 5; independent review NOT_READY → re-review READY_WITH_CORRECTIONS applied; merged (#68); amended by LV1 (§15: `brilliant_p2`, `piece_offer_v1`) |
| Reasoning LV1 (`label_v2`: FORCED, GREAT without routine replies, provisional BRILLIANT; label benchmark) | [`reasoning-lv1-implementation.md`](reasoning-lv1-implementation.md) | rev. 3; independent LV1 review NOT_READY applied; re-review READY_WITH_CORRECTIONS applied; merged (#70) |
| Reasoning MV-D (MISS v2: provisional `miss_p2` by expected points, claim `missed_gain_v1`) | [`reasoning-miss-v2-design.md`](reasoning-miss-v2-design.md) | rev. 2; independent review NOT_READY applied; re-review READY; merged (#72) |
| Reasoning MV1 (`miss_p2`, `missed_gain_v1`, the Q3 label table by chess.com mark) | [`reasoning-mv1-implementation.md`](reasoning-mv1-implementation.md) | rev. 1; independent MV1 review READY; merged (#73) |
| Reasoning R3-D (explanation plan `selection_v1`, phrasebook `phrases_en_v1`, renderer, guard) | [`reasoning-r3-design.md`](reasoning-r3-design.md) | rev. 5 (English first, owner decision; rebased on `quality_v2`, `label_v2`, MISS v2); reviews NOT_READY applied; re-review READY; merged (#61); amended by R3 (§16) and A2 (§17), owner |
| Reasoning R3 (planner `selection_v1`, `phrases_en_v1`, guarded renderer, `explain`) | [`reasoning-r3-implementation.md`](reasoning-r3-implementation.md) | rev. 2; independent R3 review NOT_READY applied; re-review READY; merged (#74) |
| Reasoning R4-D (`claim_graph_v1` storage and replay, build identity, acceptance corpus, `tools/explain_game`) | [`reasoning-r4-design.md`](reasoning-r4-design.md) | rev. 3; reviews NOT_READY applied; final re-review READY; merged (#75) |
| Reasoning R4 (`claim_graph_v1` save/load with replay, `FactEngine.normalize`, the acceptance corpus, `tools/explain_game`) | [`reasoning-r4-implementation.md`](reasoning-r4-implementation.md) | rev. 3; independent R4 review and re-review NOT_READY applied; re-review READY; merged (#76) |
| Application AR-D (game result schema `calliope_result_v1`, `calliope.results`) | [`application-result-design.md`](application-result-design.md) | rev. 4; reviews NOT_READY applied; final re-review READY_WITH_CORRECTIONS applied; merged (#79) |
| Application AR1 (`calliope.results`, `render.trace`, schema file, `tools/explain_game --json`) | [`application-ar1-implementation.md`](application-ar1-implementation.md) | rev. 2; independent AR1 review NOT_READY applied; re-review READY; merged (#80) |
| Application AS-D (local analysis server: game pipeline, ply cache, jobs, HTTP API, viewer analyse panel) | [`application-server-design.md`](application-server-design.md) | rev. 3; independent review NOT_READY applied; re-review READY_WITH_CORRECTIONS applied; final re-review READY; amended by AS1 (§15) |
| Application AS1 (`calliope.server`: pipeline, ply cache, jobs, HTTP API; `tools/serve`) | [`application-as1-implementation.md`](application-as1-implementation.md) | rev. 3; independent review NOT_READY applied; re-review NOT_READY applied; final re-review READY |
| Legacy removal LR-D (remove the MVP code, tests, `benchmarks/`, `docs/legacy/`; tag `legacy-final`) | [`legacy-removal-design.md`](legacy-removal-design.md) | rev. 2; independent review READY_WITH_CORRECTIONS applied; owner decisions recorded (§9); merged (#85) |
| Legacy removal LR1 (the removal, tag `legacy-final`) | [`legacy-removal-lr1-implementation.md`](legacy-removal-lr1-implementation.md) | rev. 1; awaiting independent review |

Later blocks (explanation and others) are not designed yet.
