# Agent — PW-D design: numbered lines and plain words

Status: **rev. 1, for independent review**. Date: 2026-10-19. Base: `main @ 0a94d18` (BL merged).
Issue: [#122](https://github.com/jihunmoon04/Calliope/issues/122) (E1 a PV move read as the
alternative, E2 "퀸 교환" misused), with the guide line BL left to "a later packet with issue #122's
E2" ([`agent-bl-implementation.md`](agent-bl-implementation.md) §4.2).
Inputs: [`agent-ag8-design.md`](agent-ag8-design.md) (AG8-D §3 `proves`),
[`agent-ms-design.md`](agent-ms-design.md) (MS-D §1.1 the invariants, §8.3 what a `proves` writes),
[`agent-bl-design.md`](agent-bl-design.md) (BL-D §3 `held` and `weakness`, §6 the guide).

An agent binds a move of an engine line to the wrong place, and repeats Calliope's own word for a
capture sequence until it means something else. This packet numbers every move Calliope shows as a
string (D1), says what an exposed or held piece risks without the word 교환 and from its owner's
side (D2), and gives the guide the lines that go with them (D3). It changes no claim, no item, no
proposition and no rule of the sentence check.

## 0. What happened

### 0.1 The issue (issue #122, `f07b8d8`, luna)

- **E1, 15.f5:** "엔진은 킹사이드 캐슬링 대신 15.O-O-O를 더 낫게 봤습니다". The digest had
  `lines.played.pv = "f5 Qxd4 Ne2 Qxb2 O-O Qxe5 fxe6 fxe6"` and `lines.best.pv = "O-O-O c5 Ne2
  O-O-O …"`: the played line's 17.O-O, shown as a bare `O-O`, was set against the best move. Written
  as SAN (`15.O-O`) S3 would have refused it; "킹사이드 캐슬링" is not a token.
- **E2, 21.Rf1:** "퀸 교환을 유리하게 이끌 수 있었던 차이" for 21.Rb1 Qxb1 22.Nxb1, a queen won
  for a rook.
- The owner's direction (2026-10-19): number the PV moves; before the packet, count errors of these
  kinds in the stored records of the earlier trials.

### 0.2 The count (2026-10-19)

Every trial JSON that keeps both the tool results and the stored commentaries (AG6 to BL trials,
2026-10-17 to 10-19): 255 files, 4006 stored sentences (luna 2922, Haiku 860, Sonnet 224).
Candidates were found by script (a move named without its number, or in words, that is a PV move
deeper than the first; a trade term against the lines; a tactical term against the digest) and every
candidate was read.

| Kind | Stored | Refused by S3 first |
| --- | ---: | ---: |
| A — a line's move bound to the wrong move | 2 | 2 |
| B — a term misused | 4 (and 2 loose) | — |

- A, stored: E1 itself; and a Haiku sentence at 15.Bxd7+ of the Opera Game, "Bxf6 gxf6 Bxd7+ Qxd7
  Qb8+ 라인에서는 … 여왕 희생이 가능해집니다" — the game's 16.Qb8+ (met by Nxb8) read into the best
  line, where 17.Qb8+ is met by Ke7. Its first draft wrote "15...Bxf6" and "16.Qb8+" and was
  refused by S3; with the numbers removed it passed.
- A, refused: the draft above; "16...Qxf4" for 8...Qxf4 (a ply number written as the move number).
- B: E2; "여왕 교환을 허용하면서" at 34...Qb3 (the queen is lost to 35.Rxb3, BL's trial); "흑의 퀸을
  교환한 뒤 백 퀸의 체크" for a line that wins the queen for a rook after the check; "c4 폰이 퀸에게
  핀되어" (no pin). Loose: "흑 퀸을 교환으로 잃는" (no recapture), "룩 교환" (a rook for a knight and
  a pawn).
- 교환 is in 277 sentences; **163 of them repeat the `exposed` wording** ("교환으로 잃을 수 있는
  상태", "정적 교환"). B's 34...Qb3 sentence turned that wording, said of a hanging queen, into
  "여왕 교환".

Both kinds are rare in what is stored. Kind A happens when a move loses its number: S3 holds a
numbered move to its position, and neither a bare SAN nor a word is held to anything.

### 0.3 A trial without Calliope's sentences (2026-10-19, the owner's question)

The owner asked whether the digest needs Calliope's Korean sentences at all. A trial on `0a94d18`
compared the digest as it is with one that has no `proves` (claims show their findings, board items
the pieces on their squares; the guide's four mentions of `proves` restated): the four games of BL's
trial, luna ×2 and Haiku ×1 a game an arm, 24 runs counted, wrong sentences at the twelve fixed
moments judged blind.

| | as today | without sentences |
| --- | --- | --- |
| Wrong sentences at the fixed moments (luna 8 runs, Haiku 4 runs an arm) | 7 | 4 |
| Sentences citing a reason, a run (luna / Haiku) | 13.4 / 14.0 | 10.9 / 8.8 |
| Sentences with 교환 / repeating the `exposed` wording (all runs) | 25 / 20 | 9 / 2 |

The arm as today had two error kinds of its own, both from the wording: **"정적 교환으로 잡히는
쪽이 3점 이득"** (Haiku, twice: the `proves`' "잡는 쪽" turned round) and **a `held` piece read as a
new attack** ("34...Qb3 뒤 흑 퀸은 백 룩 f3의 공격을 받게 됐고" in both luna runs at 34...Qb3; one
Haiku run at 31...Qf6) — the kind BL's re-review N8 counted. The arm without sentences read the
held queen right ("e3에서 … 공격을 받고 있었고, b3로 옮긴 뒤에도"), but cited fewer reasons; its own
errors came from reading lines and findings unaided (one engine line told as the game). The samples
are small. **The owner kept the sentences (2026-10-19) and chose to fix the two wordings in this
packet**; whether to drop the sentences is not decided here.

## 1. Decisions

| # | Decision |
| --- | --- |
| D1 | **Numbered lines** (§2): every move Calliope shows as a string carries its move number — a digest's PVs (`15.f5 Qxd4 16.Ne2 Qxb2 17.O-O …`, Black's first `15...Qxb2 16.O-O …`), its lines' `move`, `evaluation.best_move`, the overview's `best_move` and the moves in the same reply's `proves`. Propositions and the full view keep their SAN. |
| D2 | **Plain words** (§3): an exposed piece "잡힐 수 있다", and what it costs said from its owner's side ("그 칸에서 잡고 되잡기를 셈하면 흑이 9점을 잃는다"); a `held` piece "수 전에도 … 이미 … 공격했고, 수 뒤에도 공격한다"; `best_stops_reply`'s "정적 교환" the same way. No `proves` says 교환. The tokens each item allows are unchanged. |
| D3 | **The guide** `commentary_ko_v6` (§4): write a line's move with its number, never in words; a `held` piece is no new attack; the board section without 교환; and (owner Q1) when 교환 is the right word. |
| D4 | **Versions** (§5): `board_remarks_ko_v4`, `commentary_ko_v6`, `agent_guidance_v9`; the registry's entries renamed. No check, claim or item format changes. |

## 2. D1 — numbered lines

**Format.** A line's moves from its starting position: a White move is written `N.SAN`, a Black
move `N...SAN` when it is the line's first and plain `SAN` after a White move — the PGN form, one
token a move, separated by single spaces:

```
15.f5 Qxd4 16.Ne2 Qxb2 17.O-O Qxe5 18.fxe6 fxe6        (White to move)
15...Qxb2 16.O-O O-O-O 17.Qd3 Qb6 18.fxe6 fxe6         (Black to move)
```

A single move is written as the line's first (`15.O-O-O`, `15...Qxb2`).

**Where** (every agent-facing string of moves; the numbers from the position each starts at):

| Field | Today | PW |
| --- | --- | --- |
| digest `lines.played.pv`, `lines.best.pv` (`ply`, `judge_move`) | `f5 Qxd4 Ne2 …` | `15.f5 Qxd4 16.Ne2 …` |
| digest `lines.*.move` | `f5` | `15.f5` |
| digest `evaluation.best_move` | `O-O-O` | `15.O-O-O` |
| `game_overview` `lines[].best_move` | `O-O-O` | `15.O-O-O` |
| `board.same_reply`'s `proves` | "엔진 라인의 Qxd4를 최선수 O-O-O 뒤에 두면, 엔진의 최선은 Rxd4" | "엔진 라인의 15...Qxd4를 최선수 15.O-O-O 뒤에 두면, 엔진의 최선은 16.Rxd4" |

The bound's step 2 (`short_pv`) keeps the first `PV_SHORT` tokens of a PV, as today: a token is a
move, its number joined to it. `en_passant`'s `move`, the claims' `proves` (`17...Qxe5`) and
`played_material`'s (`35.Rxb3`) are numbered already.

**What stays SAN.** Propositions (`explored_line.moves`, `engine_score.move`, the agent's own) are
the canonical form the check verifies; the full view (`view: "full"`) and `detail` show a line's
`pv` as `{uci, san, by}` per move, as the records hold it. Neither changes.

**The check.** Unchanged. S3 already reads a numbered move and holds it to its position
(`sentences._MOVE`); a sentence that copies `17.O-O` from a line is checked where today a bare
`O-O` is not.

## 3. D2 — plain words

What `exposed` means does not change: the `exchange` record's static count of captures and
recaptures on the piece's square gives the side that captures `gain` points (`exposed_v1`). The
sentence says it from the side that loses them, and without 교환:

| Item | Today (`board_remarks_ko_v3`) | PW (`board_remarks_ko_v4`) |
| --- | --- | --- |
| `threat`, an exposed piece of the opponent | "… 뒤 백 퀸(g4)은 교환으로 잃을 수 있다 (정적 교환으로 잡는 쪽이 8점 이득; 수 전에는 아니었다)" | "… 뒤 백 퀸(g4)은 잡힐 수 있다: 그 칸에서 잡고 되잡기를 셈하면 백이 8점을 잃는다 (수 전에는 아니었다)" |
| `weakness` | "… 뒤 흑 나이트(d7)은 교환으로 잃을 수 있다 (백 퀸(g4)이 공격하고, 정적 교환으로 잡는 쪽이 3점 이득; 수 전에는 체크 중이었다)" | "… 뒤 흑 나이트(d7)은 잡힐 수 있다: 백 퀸(g4)이 공격하고, 그 칸에서 잡고 되잡기를 셈하면 흑이 3점을 잃는다 (수 전에는 체크 중이었다)" |
| `held` | "[흑의 약점: 수 전에도 수 뒤에도 흑의 기물이 위험하다] 34...Qb3 전에도 뒤에도 흑 퀸은 교환으로 잃을 수 있다: 수 전 e3에서도 수 뒤 b3에서도 백 룩(f3)이 공격한다 (수 뒤 정적 교환으로 잡는 쪽이 9점 이득)" | "[흑의 약점: 이 수가 만든 위험이 아니다, 수 전부터 있었다] 34...Qb3 전에도 뒤에도 흑 퀸은 잡힐 수 있다: 수 전 e3에서 이미 백 룩(f3)이 공격했고, 수 뒤 b3에서도 공격한다 (수 뒤 그 칸에서 잡고 되잡기를 셈하면 흑이 9점을 잃는다)" |

`held`'s other two forms say the same: "{before}에서 이미 {A}이 공격했고 수 뒤에도 공격한다" (the
piece did not move), "수 전에는 {before}에서 이미 {A}이, 수 뒤에는 {after}에서 {B}가 공격한다" (two
attackers); the promotion form keeps its two pieces (BL review B1).

The claims' `proves` (`best_stops_reply_v1`):

| Form | Today | PW |
| --- | --- | --- |
| `rescues` | "({square} 칸의 정적 교환 기준)" | "({square} 칸의 잡고 되잡기를 셈한 기준)" |
| `defends` | "{reply}로 {square}를 잡아도 정적 교환상 이득이 없다" | "{reply}로 {square}를 잡아도 잡고 되잡기를 셈하면 이득이 없다" |
| `covers` | "{square}의 {name}을 정적 교환상 잃는다" | "{square}의 {name}을 잡고 되잡기를 셈하면 잃는다" |

**Tokens (MS-D §8.3, invariant I5).** `board_tokens` reads a `proves`' squares and its counts
before 점/개/수: every square and count of today's text is in PW's (`8점` stays `8점`), and PW adds
none. D1's numbers in the same reply's text add none either: a move number is followed by a dot,
which `_COUNT` does not read, and a pawn move's square (`16.f5`) is read as the bare `f5` is today.
The tokens a cited item allows are the same set; the acceptance replay compares them item by item
(§8).

**Length.** The `held` text grows by about 20 characters; `PROVES_CAP` (240) holds it, and
`with_opponent_first` keeps its room as today.

## 4. D3 — the guide `commentary_ko_v6`

`commentary_ko_v5` with these changes and no other:

1. **표기** gains: "엔진 라인(`pv`)과 최선수에는 수 번호가 붙어 있습니다(`15.f5 Qxd4 16.Ne2`).
   라인의 수를 말할 때는 번호를 붙인 SAN으로 쓰세요(17.O-O). '킹사이드 캐슬링'처럼 말로 바꾸거나
   번호를 빼면 둔 수나 최선수로 읽히고, 검사도 그 수가 어디서 나왔는지 확인하지 못합니다."
2. **`board`**: `threat` "잡힐 수 있게 된 상대 기물", `weakness` "잡힐 수 있게 된 둔 쪽 기물 (그
   기물을 공격하는 상대 기물(`attack`)이 함께 나옵니다)", in place of "교환으로 잡을/잃을 수 있게
   된"; `held`: "수 전에도 수 뒤에도 잡힐 수 있는 둔 쪽 기물입니다. 이 수가 만든 위험이 아닙니다:
   '이 수로 공격받게 됐다', '○가 공격하게 됐다'고 쓰지 않고, '수 전에도 공격받던 ○가 수 뒤에도
   공격받는다'처럼 씁니다." (BL implementation §4.2's line.)
3. **"잡고 되잡기를 셈하면 N점을 잃는다"**: "그 칸에서 서로 잡고 되잡는 수순을 끝까지 셈한 값입니다.
   잃는 쪽은 그 기물의 주인입니다."
4. (owner Q1) **용어**: "'교환'은 비슷한 값의 기물을 서로 잡을 때만 씁니다. 퀸을 룩과 바꾸면 '퀸
   교환'이 아니라 '퀸을 내주고 룩을 얻는다'(또는 '룩으로 퀸을 얻는다')입니다. 한쪽만 잡는 것은
   교환이 아닙니다."

`build.PROMPTS` names `commentary_ko_v6`; v1–v5 stay as data, unserved (BL-D §6).

## 5. D4 — versions and registry

- `remarks.REMARKS_VERSION`: `board_remarks_ko_v3` → `board_remarks_ko_v4`.
- `commentary_ko_v5` → `commentary_ko_v6` (`build.PROMPTS`, `server.GUIDE_URIS`, the prompt and the
  resource); `GUIDANCE_VERSION`: `agent_guidance_v8` → `agent_guidance_v9`.
- Registry (`definitions.py`): `board_remarks_ko_v4` (adds "moves numbered as in PGN; an exposed
  piece's cost from its owner's side, without 교환"), `prompt.commentary_ko_v6`, in place of their
  predecessors.
- Unchanged: `board_v3` (no field changes), `commentary_check_v5`, `agent_tools_v5` (no tool or
  argument changes), `FACTS_BUILD_VERSION`, the reasoning build, stored records (their sentences and
  propositions are as accepted).

## 6. Invariants (MS-D §1.1)

| # | How PW keeps it |
| --- | --- |
| I1 | No relation, item or proposition changes: only the text that shows them. |
| I2 | No claim's status or verdict changes. |
| I3 | Each `proves` still writes what its propositions verify: "잡힐 수 있다 … N점을 잃는다" is `exposed` with `gain` N, said by the owner; "이미 … 공격했고" is the `attack` before the move the `held` item carries. |
| I4 | Unchanged (no settling changes). |
| I5 | The tokens a cited item allows are the same set as today's (§3). |

## 7. Implementation (packet PW) and tests

| Item | Change |
| --- | --- |
| W1 | `agent/digest.py`: `_line`'s `pv` and `move` numbered from the line's start (a helper beside `numbered`); `evaluation.best_move` numbered. |
| W2 | `agent/session.py`: `_ply_summary`'s `best_move` numbered (the overview). |
| W3 | `agent/board.py` / `agent/remarks.py`: `same_reply_proves` with numbered moves; `change_proves` (exposed), `weakness_proves`, `held_proves`, `_best_stops_reply` as §3; `REMARKS_VERSION`. |
| W4 | `prompts/commentary_ko_v6.md`; `build.PROMPTS` and its pin; `server.py`'s mentions; `definitions.py`; `GUIDANCE_VERSION` and its pin. |
| W5 | `docs/design/README.md`: this design and the packet's row. |

Tests (unit; and gated on Stockfish 19 where a test of the board exists):

- numbering: a White-first and a Black-first PV, a line starting at move 1, a promotion and a
  castling move in a line, a check mark kept (`17.Qb8+`), a single move; `short_pv` keeps four moves
  with their numbers; `lines.*.move` and `evaluation.best_move`; the overview's `best_move`;
- every PV token of a digest parses with `sentences._MOVE` and names the move at its position (the
  replay's check, on one fixture game);
- the same reply's `proves` numbered (`15...Qxd4`, `15.O-O-O`, `16.Rxd4`) and its propositions
  unchanged;
- the wording: each form of §3 (threat, weakness after a check and not, held with one attacker that
  moved and did not, two attackers, a promotion; the three `best_stops_reply` forms); no `proves` of
  the fixtures contains 교환; the owner's colour in "…이 N점을 잃는다";
- tokens: for every item of the fixtures, `board_tokens` of PW's `proves` equals today's set (from the
  same propositions);
- the guide v6 served; v5 not; the pins of the versions.

## 8. Acceptance

1. The suite passes (with `CALLIOPE_STOCKFISH_PATH`).
2. Replay of the four games' digests (BL's 271 plies): every PV token parses and names its move; no
   served text contains 교환; every item's allowed tokens equal `0a94d18`'s; no digest over its
   bound; the size change reported.
3. (owner Q2) A short agent trial: the setup of §0.3 (four games, luna ×2 and Haiku ×1, the analysis
   warmed once a game) on PW, against §0.3's "as today" arm as the baseline (same day's code, same
   games, same driver). Reported: wrong sentences at the fixed moments (judged blind with the
   baseline's), sentences repeating the old wording, 교환 sentences and their misuses, `held` read as
   a new attack, line moves written in words or without numbers. Met when the wrong sentences are
   not above the baseline's and no `held` is read as a new attack.

## 9. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Add the guide's line on 교환 (§4 item 4)? It was not chosen on 2026-10-19 as a glossary entry; this is one sentence of the guide. | Yes: of the four misused terms of §0.2, three are 교환 said of a queen lost or won for less; D2 removes the word Calliope taught, not the one the model brings (E2 had no 교환 in its digest). |
| Q2 | A short paid trial after the implementation (§8.3, about 12 runs and $0.15)? | Yes: the change is in what the agent reads, which a replay cannot measure; §0.3's baseline runs need not be repeated. |

## 10. Not in this packet

- Dropping Calliope's sentences from the digest (§0.3): not decided.
- BL's N11 (a particle after a name in brackets, "나이트(d5)이") and N12 (S-rules read numbers, not
  their units): later.
- Korean words for moves read by S3 (issue #122's option 1): not chosen; D3's line asks for the
  numbered SAN instead.
