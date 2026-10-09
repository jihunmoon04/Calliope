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
| Fact engine F4b | [`fact-engine-f4b-implementation.md`](fact-engine-f4b-implementation.md) | rev. 2; independent F4b review READY_WITH_CORRECTIONS applied; merged (#50). Next: F5-D |

Later blocks (explanation and others) are not designed yet.
