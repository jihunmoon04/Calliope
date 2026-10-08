# Explanation quality corpus — first scenario packet

Status: A1_READY / A3_READY; independent implementation re-review of `672f162` accepted.
Independent re-review of PR #29 c99d6a3: READY; F1-F7 accepted.
The 15 examples below are executable inputs with manually specified factual oracles.
Their expectations were fixed using positional_v1/activity_v1 before A2 existed.
Separate A2 acceptance now checks the actual selector, compressor and renderer;
the corpus alone does not certify independent implementation review.

Contract: [scenario-line-summary-design.md](scenario-line-summary-design.md).
First policy: [exchange-line-summary-design.md](exchange-line-summary-design.md).
Data: `tests/golden/scenario_explanation_cases.json` (explicit FEN/UCI/focus/facts).
Verification: `tests/golden/test_scenario_design_observations.py`.
Acceptance: `tests/golden/test_scenario_summary_acceptance.py` (15 base + 15 mirrors).
The A3 C1 amendment adds E06's required PROMOTION digest event with initial
subject, actual endpoints and promoted type. Existing factual expectations stay fixed.

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
| E15 | Only the rook participating later castles | CASTLING_ROOK selected; e1g1 labelled step context, rook h1-to-f1 explicit | King MOVE excluded; e1g1 is never the rook's UCI |

JSON summary_expectations is the normative structured oracle. Participant membership
is an exact canonically ordered list of INITIAL squares; FEN fixes color and original
type, so no later square or promoted type can silently replace the identity. Status
and focus_losses are also fixed for every case, including empty sets/counts.

included_fact_keys and excluded_fact_keys are hand-specified CORE membership checks,
not the complete accounting sets. Each key has scope, family and exact selectors:
ply for event/step; frame for snapshot; subject=initial square for piece properties;
square/file/direction or physical pin triple where appropriate. Endpoint implicitly
compares 0,N. History keys refer to complete 0..N tracks. Capture reasons are fixed
explicitly. The common contract defines complete A2 accounting beyond these core keys.

absent_fact_keys identifies keys that MUST NOT be change candidates because values
are equal, rather than candidates excluded for relevance. E12's endpoint pin belongs
here; it must not inflate excluded accounting. included/excluded lists may be empty
when no meaningful candidate of that category exists. No fabricated key is added
merely to make every list nonempty.

E05 also fixes required_digest_events with CAPTURE_EP, landing d6 and victim d5.
E12 fixes the physical pin key (base a8,e2,e1), both selected step keys, the history
key, complete boolean track and required true/false observation templates. E13 fixes
c4 PAWN_FLAGS exclusion in BOTH steps and endpoints. E14 fixes excluded a2 MOVE at
ply 3 separately from its property changes. E15 fixes castling_context with actual
king UCI and rook endpoints, plus included rook/excluded king event keys.

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

제시된 라인의 1번째 수 이후 e2 나이트의 절대 핀이 관측됩니다.
2번째 수 이후에는 그 핀이 관측되지 않습니다. 마지막 수에서 같은 나이트가
d4의 흑 폰을 잡습니다. 초기와 최종에는 그 핀이 없지만 중간 이력에는 남습니다.

Evidence: frame-1 pin, frame-2/3/4 absence, base e2 knight history, ply-4 capture.
The king MOVE is not selected, and the wording makes no causal claim about it.
This is a retrospective account; it proves neither a forced plan nor the cause of gain.

## 4. Next implementation acceptance

Each JSON case is a design oracle. The A2 acceptance test additionally queries
ScenarioSummary and report sentences, requiring complete selected/excluded sets,
membership, focus status, source bindings, endpoint views and history semantics.
The current verifier checks structured participant/status/loss expectations against
existing P5 captures and physical histories, and verifies that named included/excluded
keys denote real observation/event candidates. Equal-valued absent keys are checked
separately. That verifier does NOT implement or test ScenarioSummary selection/accounting or
rendered output. The separate A2 acceptance verifies frozen template obligations.

Corpus changes require review of question, expected facts and forbidden meaning;
do not regenerate expected facts from implementation output to make a failure pass.
Phrase examples are semantic expectations, not a word blacklist or exact-text test.
Do not claim full chess explanation coverage from these 15 diagnostic examples.

Future corpus extensions should include pawn-support loss, same blocker relocation,
underpromotion and same-type identity mutation under the corresponding
scenario rules. Existing focused foundation tests already exercise many of these
observations; that coverage is not scenario-summary acceptance.

## 5. Verification record

Historical 094f4df verification replayed all 14 base cases and 14 color/rank mirrors.
The corrected packet has 15 base cases and 15 mirrors. Base cases assert captures,
material deltas and the distinguishing per-frame facts in JSON. Mirror tests assert
transformed capture/material oracles only, not every feature or prose expectation.

No engine calls, full pytest, fuzz or performance gate is claimed for this packet.
This paragraph describes the A1 packet; its independent design review is now READY.
A2 evidence is in [scenario-summary-a2-implementation.md](scenario-summary-a2-implementation.md).

Historical combined focused regression at 094f4df: **265 passed / 0 failed**
(28 corpus checks plus 237 existing tests). Changed-file Ruff check/format and diff
check pass. Tests used Python UTF-8 mode and explicit worktree PYTHONPATH so the
older editable installation could not substitute its source.

Correction verification: **45 corpus tests passed** (15 factual oracles, 15 mirror
capture/material controls, 15 structured expectation evidence checks). The E12 JSON
pin check covers every frame, including frame 3. Current combined focused results
are recorded in the correction closure document; no independent re-review is claimed.
