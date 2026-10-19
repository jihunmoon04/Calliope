# Agent PW — numbered lines and plain words (implementation)

Status: **rev. 2 — independent review of rev. 1 (`1ab4979`) READY_WITH_CORRECTIONS (N1–N3) applied (§5); re-review of rev. 2 (`b652480`) READY_FOR_MERGE; criterion 1 of the trial not met (§4): the owner merged with it (2026-10-19), the follow-up of §5 to come**. Date: 2026-10-19. Design:
[`agent-pw-design.md`](agent-pw-design.md) (PW-D rev. 3, with erratum E1 below; owner Q1, Q2 as
recommended). Issue: [#122](https://github.com/jihunmoon04/Calliope/issues/122).
Base: `design/pw @ 5b0cd97` (PW-D on `main @ 0a94d18`).

## 1. What changed

| Item (PW-D §7) | Change |
| --- | --- |
| W1 | `agent/digest.py`: `numbered_line(fen, sans)` (PGN form; a record made by hand, whose FEN is no position, keeps bare SAN as `en_passant` does); `_line` numbers `pv` and `move` from the ply's `fen_before`; `evaluation.best_move` numbered as the ply's move (`_numbered_san`). |
| W2 | `agent/session.py`: the overview's line numbers `best_move` when it writes it (`_numbered_move(parsed, ply, san)`); `_ply_summary` keeps the bare SAN that the "another move was best" rule compares. |
| W3 | `agent/remarks.py` (`board_remarks_ko_v4`): `STATIC` ("그 칸의 잡고 되잡기만 셈하면"); the exposed `threat` and `weakness` texts and `held_proves` (bracket, "이미 … 공격했고", the owner's colour losing N points) and `_best_stops_reply`'s three forms as PW-D §3; `same_reply_proves` takes its moves numbered. `agent/board.py`: `_same_reply` numbers `same` as one line from the position after the best move, the best move from the ply's position and the engine's top move from its own. |
| W4 | `agent/sentences.py`: `read_move(board, text)` — UCI, SAN, or `N.SAN` / `N...SAN` / `...SAN` whose number and side are the board's, else `MoveNumberError`; `session.parse_move` (judge_move, explore, positions, open_game's moves) and `propositions.Verifier._uci` (every proposition's move) use it, with their own refusals; `messages_ko` translates the new refusal for white and black. |
| W5 | `prompts/commentary_ko_v6.md` (v5 with PW-D §4's four changes, the three `board` bullets whole); `build.PROMPTS`; every `commentary_ko_v5` in `server.py`; `definitions.py` (`prompt.commentary_ko_v6`, `board_remarks_ko_v4`); `GUIDANCE_VERSION = "agent_guidance_v9"` (its pin: the instructions, descriptions and searches it digests are unchanged, so the same digest as v8). |
| W6 | `docs/design/README.md`: this packet's row; PW-D's erratum E1. |

## 2. Tests

The suite (`PYTHONPATH=src`, `CALLIOPE_STOCKFISH_PATH` set): **1791 passed** (25 min).

- `tests/agent/test_pw.py` (14, synthetic engine and hand-made texts):
  - numbering: White-first, Black-first, a single move, a promotion with its check and mate marks,
    a record made by hand; `short_pv`'s four tokens on a White-first and a Black-first line; an en
    passant move first in its line equals its token; the digest's lines (every token read back with
    `read_move` against the board), `move` and `best_move`;
  - the overview: `best_move` only where another move was best (one ply's summary patched so its
    best move is the move played — the synthetic engine never plays its own best), numbered as the
    move is;
  - the same reply's text numbered (`2.exd5`-style reply, `1...a5`, the engine's `2...` move); its
    propositions stay SAN. The three-move `same` (the second search's path) is covered by the
    replay (§3: e.g. "6.cxd5 Nxd5 7.Bb5+를 최선수 5...c5 뒤에 두면, 엔진의 최선은 7...Bd7"), not by a
    unit test;
  - moves given numbered: `read_move`'s accepts and refusals (wrong number, wrong side, numbered but
    illegal, two or four dots refused as not legal, surrounding spaces dropped), the Korean refusal;
    `judge_move` (also `...SAN`), `explore` and a position's `from_root` with numbered moves and
    with a wrong number; a judgement's `move` and `best_move`, `engine_line.moves`,
    `engine_score.move` and `explored_line.moves` numbered, stored as the bare move;
  - wording: the exposed `threat` (the owner's colour), `weakness` after a check and not, `held` with
    an unmoved piece; the three `best_stops_reply` forms; none says 교환 or "잡는 쪽";
  - tokens: today's and PW's texts of an exposed threat and a held queen give the same squares and
    counts; numbering the same reply adds none; a threat at the length limit with `opponent_first`
    keeps its squares and counts.
- Updated to PW's texts: `test_bl.py` (the held forms, the promotion — with PW-D review B2's check
  that a rising gain keeps the bracket to "before and after"; a rising gain from a move off a
  defended square is not tested apart: the bracket's text does not depend on the gains), `test_bl_stockfish.py` (34...Qb3's held
  queen), `test_digest.py` (the numbered PV, `move`, `best_move`), `test_guidance.py` (v6, v9 and its
  pin, the prompts' entries), `test_server.py` (the build's prompts).

## 3. The replay (PW-D §8.2)

Every ply of the four games (271) and each game's overview, on `0a94d18` and on PW, from the same
warmed analyses (`scratchpad …/pv122/replay`):

| Game | Plies | PV tokens read back | 교환 in the digests (main → PW) | Items, tokens equal | Over the bound | Digest mean size (main → PW) | Overview size | Overview `best_move` |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| #123's | 71 | 887 | 87 → 0 | 114 of 114 | 0 | 2748 → 2789 | 9960 → 10139 | 47 → 47 |
| rapid | 55 | 653 | 58 → 0 | 75 of 75 | 0 | 2581 → 2618 | 7714 → 7830 | 31 → 31 |
| fourth | 67 | 821 | 90 → 0 | 104 of 104 | 0 | 2681 → 2723 | 9244 → 9394 | 41 → 41 |
| fresh | 78 | 1011 | 78 → 0 | 76 of 76 | 0 | 2421 → 2463 | 10610 → 10806 | 53 → 53 |

Every PV token parses with `read_move` and names the move at its position; every line's `move` is
its PV's first token; every `en_passant` move names a move of its line at its position. Every board
item's allowed tokens (`board_tokens`: squares and counts) equal `0a94d18`'s (items matched by kind
and propositions, the line refs' session-specific suffix aside). The digests grow by about 1.5%
(at most 98 characters), the overviews by about 2%. **Met.**

## 4. The trial (PW-D §8.3, owner Q2)

As PW-D §0.3 (HIMARI v3, one conversation a run, the four games, the analysis warmed once a game and
copied into each run): on this branch (`1850059`), luna ×2 and Haiku ×1 a game, 12 runs, $0.14;
against §0.3's "as today" arm (`0a94d18`, 12 runs, the same day, games, driver and warm analyses).
The fixed moments' commentaries of both arms (74) were shuffled and judged blind together; the
baseline's judged again came to the same 7 as in PW-D §0.3.

Means a run (luna; Haiku in brackets):

| | as today | PW |
| --- | --- | --- |
| Sentences | 19.6 (23.5) | 21.4 (19.0) |
| Sentences citing a reason | 13.4 (14.0) | 13.1 (10.2) |
| … at the fixed moments | 6.4 (7.8) | 6.1 (4.3) |
| Refused submissions | 1.8 (4.0) | 1.3 (4.8) |
| Cost | $0.0080 ($0.020) | $0.0089 ($0.018) |

All sentences (as today 251, PW 247): 교환 in 25 against 5 (PW's five are right: a bishop for a
knight, pawns for pawns); the old `exposed` wording repeated 20 against 0, PW's "잡고 되잡기" 5;
"잡히는 쪽이 … 이득" 2 against 0; line moves written as castling words 0 and 0; numbered moves in
179 sentences against 146; numbering refusals 0 (no agent gave a move numbered for another
position). Kind A (a line's move bound to the wrong move), every candidate read: none in either.

Wrong sentences at the fixed moments (blind):

| Kind | as today | PW |
| --- | --- | --- |
| "who loses" inverted ("잡히는 쪽이 3점 이득") | 2 (Haiku, one run) | 0 |
| `held` read as a new attack | 3 (luna 2 at 34...Qb3; Haiku at 31...Qf6) | **1** (luna, p-hung-1 at 34...Qb3) |
| other kinds | 2 ("흑 퀸은 g4의 백 폰을 공격"; "가장 큰 실수") | 1 ("28.Rxe8#로 백이 1수 만에 메이트되는 수": who is mated, Haiku) |
| **All** | **7** | **2** |

PW-D §8.3's criteria:

1. no `held` read as a new attack: **not met** — one sentence in 12 runs (against 3). p-hung-1 wrote
   "이 이동으로 흑 퀸은 백 룩 f3의 공격을 받게 되었고, 동시에 흑 퀸이 지키던 c5 폰도 백 룩 c4의
   공격에 놓였다", citing the `held` queen (b19) and the `lost_defence` c5 pawn (b20) in one sentence:
   it said both in the `lost_defence` form. The `held` text it cited read "수 전 e3에서 이미 백
   룩(f3)이 공격했고, 수 뒤 b3에서도 공격한다". The other luna run and the Haiku run read it right
   ("퀸은 e3에 있을 때도 f3 룩의 공격을 받고 있었는데 b3로 옮긴 뒤에도 …");
2. no "who loses" inverted: **met** (0; "who is mated" inverted once, counted under other kinds);
3. other kinds not above the baseline's 2: 1 — reported for the owner (re-review N1); 2 if B015's
   "엔진 라인에서 백이 29.Qxd5로" is counted (29.Qxd5 is the `piece_offer` claim's reply, in no engine
   line), still not above.

**Not counted in either arm** (review N1): an attack that existed before the move, read as new from a
`lost_defence` or `weakness` item — "백 퀸 g4는 d7 나이트를 공격하게 됐다" at 19...Kh8 (the queen
attacked d7 since 19.Nh6+), "백 비숍(d5)이 f7을 공격하게 됐다" at 26...Re8 (Bd5 already hit f7). PW
3 (B011, B064, B067), as today about 6 (B000, B007, B008, B069–B071; Qf6 already hit d4, Re5 already
hit e8). The judging left them as borderline in both arms alike, so the 7 → 2 comparison holds; but
they are criterion 1's kind on other items, and B050's error came by the same road: the `held`
queen said in `lost_defence`'s form ("수 뒤에는 그 수비가 없고, X이 Y을 공격한다"), whose text does
not say whether X attacked Y before the move. A guide line on `held` alone does not reach it.

**Not exercised** (review N1): no PW run called `judge_move` or `explore` or gave a proposition with a
move — the runs cite by handle — so "numbering refusals 0" says nothing of the input path of PW-D
review B1; the unit tests cover it (§2).

Smaller, borderline in the judging: B048 calls the square's count "엔진의 13.d4 라인" (the guide says it
is no engine line); B039 says "비숍을 잡아" for 7...Bxe2, which took a knight.

Seen besides (not at a fixed moment): hp-hung-1 at 7.f4, "흑 퀸이 c4 폰을 잡으며 c1의 백 비숍을
핀하는" (no pin) — the term and the ply of PW-D §0.2's "c4 폰이 퀸에게 핀되어"; not a wording PW
touches.

## 5. Review dispositions — rev. 1 (`1ab4979`), independent review: READY_WITH_CORRECTIONS

The review found W1–W6 as PW-D specifies (the texts character by character, the numbering from the
right positions, `top` following `longer`, the except order, the guide v6 word for word, the pin's
reasoning, no other reader of the changed fields, no import cycle, the boundaries test), ruff clean,
15 of 16 mutations caught, the replay reproduced (and every PV token read whole by S3's own
`_MOVE`), the trial tree identical to the branch, and the trial's numbers as §4 gives them.

| # | Finding | Disposition |
| --- | --- | --- |
| N1 | §4 leaves out an uncounted class (an attack that existed before, read as new, on `lost_defence` and `weakness` items, both arms) and says "numbering refusals 0" of a path no run took; smaller misses (B015, B048, B039). | Applied (§4: *Not counted in either arm*, *Not exercised*, the smaller ones; criterion 3 with B015). |
| N2 | Tests missing: numbered input through `from_root`, `explored_line.moves`, `...SAN` through a tool; the three-move `same` only through `numbered_line`; the rising gain off a defended square; a template test that tests no numbering. | Applied: the three input tests; the template test renamed for what it tests, the three-move path stated as the replay's (§2); the rising gain stated as untested apart, the bracket not depending on gains. |
| N3 | `read_move`'s `strip()` untested; `1..e5` refused as "numbered for another position" though its number and side are right. | Applied: the pattern takes one or three dots, never two (`1..e5` and `1....e5` refused as not legal); the strip kept, commented and tested. |

The review's view on criterion 1 (for the owner): merge with the owner's acceptance rather than re-run
the #123 game (a few runs cannot show a rate of about one in three moments to be zero), and take "an
attack that existed before, read as new" into a follow-up packet for every item: give
`lost_defence` the attack before the move (the facts hold it) so its text can say "수 전에도 X이 Y을
공격했고", gate the reading in the guide for every item, and judge a widened criterion 1 blind
against this trial's PW arm.

**Re-review of rev. 2 (`b652480`): READY_FOR_MERGE.** N1–N3 settled; the new tests fail under their
mutations (the two-dot lookahead, `strip()`, `from_root` by `parse_san`, the bare `...` side check,
`Verifier._uci` by `parse_san`); the 17 three-move same replies of the replay read back with their
numbers and sides; 136 tests of the touched files pass, ruff clean. The reviewer's view on criterion 1
unchanged.

## 6. PW-D erratum E1

PW-D §2 says "`en_passant`'s `move` is the token its PV shows". That holds when the en passant capture
is the line's first move; in the middle of a line after a White move the PV shows the bare SAN
(`38.g4 fxg3`) while `en_passant` names it `38...fxg3`. Both name the same move; the replay checks that
(§3). PW-D §2 now reads "names the same move as its PV".
