# Current design (redesign)

These documents are the **only current** design documents of Calliope. Anything under
[`docs/legacy/`](../legacy/README.md) is frozen history and is never a requirement here
(see [`docs/README.md`](../README.md)).

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
| Reasoning R0-D (contracts: controller, observer, hypotheses, verification, claim graph, planner, renderer) | [`reasoning-r0-design.md`](reasoning-r0-design.md) | rev. 10; merged (#55); amended by R1 (§27) and R2b (§29); BRILLIANT deferred (§28) |
| Reasoning R2-D (observations v1, hypothesis templates v1) | [`reasoning-r2-design.md`](reasoning-r2-design.md) | rev. 11; merged (#56); fifth and sixth independent reviews and their re-checks applied (#58); BRILLIANT deferred (E10); amended by R2b (§12) |
| Reasoning R1 (foundation, round 0, `quality_v1`, facts additions) | [`reasoning-r1-implementation.md`](reasoning-r1-implementation.md) | rev. 2; independent R1 review READY_WITH_CORRECTIONS applied; merged (#57) |
| Reasoning R2a (hypotheses, verification, rounds, claim graph) | [`reasoning-r2a-implementation.md`](reasoning-r2a-implementation.md) | rev. 2; independent R2a review READY_WITH_CORRECTIONS applied; merged (#59) |
| Reasoning R2b (catalogue v1: 21 templates, `line_material`, `played_edge`, `label_v1`) | [`reasoning-r2b-implementation.md`](reasoning-r2b-implementation.md) | rev. 3; independent R2b review NOT_READY applied; re-review READY_WITH_CORRECTIONS applied |

Later blocks (explanation and others) are not designed yet.
