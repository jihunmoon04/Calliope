# Explanation quality corpus — first scenario packet

Status: DRAFT_AWAITING_INDEPENDENT_DESIGN_REVIEW.
The 14 examples below are executable inputs with manually specified factual oracles.
They exercise existing positional_v1/activity_v1. They do not implement or certify the
proposed common scenario selector, compressor or renderer.

Contract: [scenario-line-summary-design.md](scenario-line-summary-design.md).
First policy: [exchange-line-summary-design.md](exchange-line-summary-design.md).
Data: `tests/golden/scenario_explanation_cases.json` (explicit FEN/UCI/focus/facts).
Verification: `tests/golden/test_scenario_design_observations.py`.

## 1. Why these examples

Each example binds a user question to required facts, deliberate exclusions,
unsupported assertions and the extra evidence a deeper explanation would need.
We first evaluate question relevance and evidentiary discipline, not eloquent prose.
These are constructed diagnostic positions, not claimed master games or best lines.

The corpus contains genuine counterexamples to common shortcuts: attack is not a
legal capture; no focus capture is not no capture; equal counts are not equality of
position; promoted identity is not original type; endpoint equality is not no history.

## 2. Case index and explanation oracle

| ID | User question / distinction | Required result | Deliberate exclusion / unsupported claim |
| --- | --- | --- | --- |
| E01 | Empty supplied line at e4 | One focus snapshot; no focus captures or participants | No invented change, safety or impossibility |
| E02 | A single exd5 | Black pawn -1, white pawn on d5 at endpoint | No settled exchange or forced gain |
| E03 | exd5 followed by Qxd5 | Captures at plies 3/4; each side pawn -1; black queen on d5 | Equal counts do not establish equal position |
| E04 | EP landing focus d6 | Capture lands d6, victim removed d5 | Do not say the victim occupied d6 |
| E05 | Same EP line, victim-square focus d5 | Zero focus captures; other capture and full material retained | No focus capture does not imply no capture |
| E06 | Capture-promotion then promoted queen captured | Same base pawn identity; current queen loss differs from endpoint counts | No original queen loss or weighted exchange judgement |
| E07 | Quiet interruption between focus captures | Captures at plies 1/4, both retained chronologically | Unrelated king motion excluded; no contiguous forced chain |
| E08 | exd5 with focus e4 | Zero focus captures; d5 capture remains line context | Departure square does not define membership |
| E09 | Pinned knight geometrically attacks d4 | Focus white attacker e2; current white legal captures empty | Full observed pin is not selected as participant pin with zero participants |
| E10 | a2-a3 changes location only | Final a3 occupant; no capture | EXCHANGE does not claim pawn improvement or select unrelated pawn flags |
| E11 | Knight vacates rook's file | Final a7 geometric attackers a1/b5; no capture | Unrelated full rook-ray report excluded; no access beyond next blocker |
| E12 | Temporary pin on a later capture participant | Pin absent/present/absent history, no endpoint pin difference | No causal attribution; no recursive selection of every pinner/king fact |
| E13 | Capture changes both participant file and stationary nonparticipant pawn | e-file becomes open | c4 pawn change remains full observation, excluded from EXCHANGE selection |
| E14 | Unrelated a-pawn move after capture | d5 event and participant result retained | a-pawn motion/footprint excluded and accounted |

For future summary acceptance, participant membership is exact, not "contains at
least these pieces": E02={white pawn e4, black pawn d5}; E03={white pawn e2,
black pawn d7, black queen d8}; E04={white pawn e5, black pawn d5};
E06={white pawn a7, black rook b8, black rook c8}; E07={white pawn e4,
black pawn d5, black queen d8}; E12={white knight e2, black pawn d4};
E13/E14={white pawn e4, black pawn d5}. E01/E05/E08/E09/E10/E11 have none.
All identifiers here are base-position identities, not later occupied squares.

E06 focus losses are black rook 1 + white queen 1. Its endpoint counts are black
rook -1 + white pawn -1, with no queen delta. E03/E07 focus losses are one pawn of
each color. E05/E08 have no focus losses even though whole-line material changes.
These views must never share a single ambiguous "exchange balance" field.

## 3. Concrete output semantics to review

The following Korean examples describe target meaning, not a current Korean renderer
or exact wording golden. Every factual sentence in the future report needs resolving
references. Production v1 templates are proposed in English; localization is separate.

### E03: what a supplied recapture proves

제시된 라인의 3번째 수에서 백 폰이 d5의 흑 폰을 잡고, 4번째 수에서 흑 퀸이
그 백 폰을 잡습니다. 라인 끝에는 양쪽 폰이 하나씩 줄고 흑 퀸이 d5에 남습니다.

Evidence: P5 captures at plies 3/4, endpoint material counts, frame-4 d5 occupant,
physical histories. This does not establish best play, equal evaluation or forced Qxd5.

### E09: geometry versus action

현재 백 나이트 e2는 d4를 기하적으로 공격하지만, 현재 백의 d4 합법 잡기는 없습니다.
제시된 수가 없으므로 라인에서 d4에 도착한 잡기도 없습니다.

Evidence: frame-0 square access and current-side legal captures; empty capture stream.
The complete observations also retain an absolute pin. With no exchange participants,
that pin is not separately selected by EXCHANGE. A future direct piece-action query
may explain the pin explicitly under its own reviewed rule, rather than silently
expanding EXCHANGE's membership.

### E12: a temporary fact must survive endpoint compression

제시된 라인에서 흑 룩이 e8로 이동한 뒤 e2 나이트에 절대 핀이 생깁니다.
백 왕이 f1로 이동하면 그 핀이 해소됩니다. 마지막 수에서 같은 나이트가 d4의
흑 폰을 잡습니다. 초기와 최종에는 그 핀이 없지만 중간 이력에는 남습니다.

Evidence: frame-1 pin, frame-2 absence, base e2 knight history, ply-4 capture.
This is a retrospective account; it proves neither a forced plan nor the cause of gain.

## 4. Next implementation acceptance

Each JSON case is a design oracle. A later acceptance test must additionally query
ScenarioSummary and report sentences, requiring complete selected/excluded sets,
membership, focus status, source bindings, endpoint views and history semantics.
The current verifier does none of those unimplemented checks.

Corpus changes require review of question, expected facts and forbidden meaning;
do not regenerate expected facts from implementation output to make a failure pass.
Phrase examples are semantic expectations, not a word blacklist or exact-text test.
Do not claim full chess explanation coverage from these 14 diagnostic examples.

Future corpus extensions should include pawn-support loss, same blocker relocation,
castling, underpromotion and same-type identity mutation under the corresponding
scenario rules. Existing focused foundation tests already exercise many of these
observations; that coverage is not scenario-summary acceptance.

## 5. Verification record

At this design revision, the existing foundation successfully replays all 14 base
cases and their 14 color/rank mirrors. The base cases assert explicit captures,
material deltas and the distinguishing per-frame facts in JSON. Mirror tests assert
transformed capture/material oracles only, not every feature or prose expectation.

No engine calls, full pytest, fuzz or performance gate is claimed for this packet.
Independent design review and production implementation remain pending.

Combined focused regression on 2026-10-08 (Korea date): **265 passed / 0 failed**
(28 corpus checks plus 237 existing tests). Changed-file Ruff check/format and diff
check pass. Tests used Python UTF-8 mode and explicit worktree PYTHONPATH so the
older editable installation could not substitute its source.
