# Current design (redesign)

These documents are the **only current** design documents of Calliope. Anything under
[`docs/legacy/`](../legacy/README.md) is frozen history and is never a requirement here
(see [`docs/README.md`](../README.md)).

## Direction

Calliope is rebuilt as composable blocks with one role each. Each block is designed in a packet
(design document → independent review READY or READY_WITH_CORRECTIONS → implementation packets,
each reviewed).

## Packets

| Block | Document | Status |
| --- | --- | --- |
| Fact engine | [`fact-engine-a0-design.md`](fact-engine-a0-design.md) | F0 design; A0 review READY_WITH_CORRECTIONS applied (rev. 4) |
| Fact engine F1 | [`fact-engine-f1-implementation.md`](fact-engine-f1-implementation.md) | implemented; awaiting independent F1 review. Next: F2-D |

Later blocks (explanation and others) are not designed yet.
