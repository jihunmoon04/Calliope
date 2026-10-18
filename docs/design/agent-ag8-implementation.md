# Agent — AG8 implementation: the reasons with the ply

Status: **rev. 2 — for independent review** (rev. 2: §2 items 6–8 and §4.1, after the trial). Date: 2026-10-18. Base: `main @ 821edd3` (AG8-D
rev. 2 merged). Design: [`agent-ag8-design.md`](agent-ag8-design.md).

## 1. What was built

| AG8-D | Where |
| --- | --- |
| R1 `board` (§2) | `agent/board.py` (new): `Board(...).build()` — the facts tree's `pieces`, `patterns`, `exchange`, `status` before and after the move; `threat`, `weakness`, `lost_defence` with their limits and order; every item verified by the server's own `Verifier` before it is served. `agent/session.py`: `ply` and `judge_move` digests carry it (`ply`'s positions `{"ply", "at"}`, `judge_move`'s `{"from_root"}`); `view: "full"` unchanged. |
| R2 `proves`, `part`, `owner`, `good_for` (§3) | `agent/remarks.py` (new): `board_remarks_ko_v1`, the brackets of side, the pieces as `백 비숍(c4)`, capped at 240 characters. |
| R3 claims (§4) | `agent/digest.py`: every claim gets `part` (`remarks.TEMPLATE_PARTS`); material and mate claims `proves` from their findings (`remarks.claim_proves`). |
| R4 the same reply (§5) | `board.Board._same_reply` and `Session.compare` (an `explore` whose handle says `by: "calliope"`, with one search; a second only when the engine's answer is the played line's); `agent/propositions.py`: such a line is not the agent's (`by_agent` false, the record's `by: "calliope"`). |
| R5 `states`, S7, S8 (§6.1–§6.3) | `agent/sentences.py`: `check_states` (S7a, S7b for propositions that allow a token), S8; `agent/session.py`: the served items per game and subject in canonical form (`Session.boards`, cleared when a game is put away), `_stated` (an item stated when all its propositions are), `states` and `states_items` stored; `check: "commentary_check_v2"`. |
| R6 notes (§6.4) | `session._notes`: `N-reason`, `N-reading` in an accepted answer's `notes`. |
| R7 Korean refusals (§7) | `agent/messages_ko.py` (new): the templates; `problem` Korean, `problem_en` English, for a `ko` submission's violations (S1–S8, the subject, the size, the items, every proposition field). |
| R8 guide and registry | `agent/prompts/commentary_ko_v3.md`; `build.PROMPTS = ("commentary_ko_v3", "check_ko_v1")`; the prompt and the resource render it; `GUIDANCE_VERSION = "agent_guidance_v5"`; the registry's kinds `board` and `remark` with `board.board_v1`, `board.threat`, `board.weakness`, `board.lost_defence`, `board.same_reply`, `board_remarks_ko_v1`, `remark.part`, `remark.proves`, `sentence.states`, `commentary_check_v2`, `prompt.commentary_ko_v3`; `ply`'s description names `board`. |
| §2.3 the bound | `digest.bounded` step 0 (`board`): threats beyond two, then weaknesses, then lost defences beyond two; the same reply never. |

## 2. Where the implementation departs from the design, and why

1. **The comparison never waits for the engine.** AG6-D promises that a cached ply answers while a
   job runs (`test_a_cached_ply_never_waits_for_an_analysis`). The same reply's search needs the
   engine lock, which a job's analysis holds; waiting for it broke that promise. `EngineLock.now()`
   takes the lock only when no one holds it or waits for it; otherwise `same_reply` is
   `{"not_computed": "engine_busy"}`, the rest of the digest is served, and a later read computes
   it. (§5's `not_computed` reasons gain `engine_busy`.)
2. **The guide's first line names v3.** Appendix A says `commentary_ko_v2.md` byte for byte, then
   the section; the first line of v2 is the title `(prompt.commentary_ko_v2)`, which in v3 reads
   `(prompt.commentary_ko_v3)`. The test checks v3 is v2 with that title, then the section.
3. **Another component's message in a Korean frame.** A handle's or a position's own error text
   (`HandleError`, `AgentError` of a path) is not a Calliope rule; it is given as
   `받아들여지지 않았습니다: <the English text>` with `problem_en`. Every rule of the check, the
   submission and the proposition fields has its own Korean template.
4. **An `exposed` candidate whose state is not "exposed" is no item, not a fault.** A positive
   exchange gain does not always make `exposed_v1` say `exposed`; such a piece is left out silently
   instead of counting toward `board.refused`.
5. **Step 0 of the bound always runs when the digest is over its bound**, moving nothing when
   there is no board, so the steps stay a prefix of `STEPS`.

After the acceptance trial (§4), rev. 2:

6. **`lost_defence` and the double attacks are read from the fact engine's `pattern_delta`**, not
   from a comparison of squares in the agent layer. §2.1's "defenders are compared by square"
   becomes `defences_ended_under_attack` by piece identity, kept for a piece of the mover's whose
   reason is `defender_moved` or `line_blocked` (the defended piece stayed on its square, §2.1's
   own rule); the defender's square before is its identity's square in the position before. A
   double attack is a `multi_target_attacks` change of the mover's whose targets after (two or
   more) include one it did not have. At the seven fixed moments of `test_board_stockfish.py`
   the items are the same as rev. 1's (26...Re8 f7, 27...Nxf7 e8, 31...Qf6 f5 by a blocked line,
   38...Rxh5 d6, none at 28...Qe6; 27...Nxf7's and 13.Rxd7's double attacks). The registry's
   `board.lost_defence` says so.
7. **`en_passant` in the digest.** Three of §4's four wrong sentences (and two of `main`'s three)
   read 38...fxg3, the best move's en passant capture at 38...Rxh5, as a capture on g3. The SAN
   is kept (the sentence check reads it); the digest gains `en_passant`, present only when one of
   its lines (the played and best PVs as shown, the other candidates' first moves) holds such a
   capture: `{"line", "move", "text"}`, the text in Korean naming the pawn taken and the square
   left empty (`38...fxg3는 앙파상입니다: 흑 폰이 f4에서 g3로 가며 백 폰(g4)을 잡습니다. g3 칸은
   비어 있었습니다.`). Registry: `remark.en_passant`.
8. **`open_game` over the per-call bound points to `analyze_game`.** Three of §4's eight AG8 Haiku
   runs opened the game with `plies: "1-33"` and saved part of it. When the range's uncached plies
   are over `max_uncached_plies_per_call`, the refusal adds "to analyse the whole game, open it
   without `plies` and call `analyze_game`, which analyses it in the background".

## 3. Tests

- `tests/agent/test_board.py` (synthetic engine, 17): the sides and brackets; `judge_move`'s path
  positions; the same reply's propositions and provenance; every served proposition verifies as
  given; a busy engine and a refused search leave only the same reply out; Calliope's line is not
  the agent's (review N1); S7a, S7b and its scope (review B2: a `definition`, a `legal_moves` by
  moves pass, a count passes only when written); an item stated whole only with all its
  propositions (review B1), a proposition belonging to its item by content (another id, its
  path); S8; the notes; no `N-reason` for a subject whose digest was never served; Korean refusals
  with `problem_en`; `commentary_check_v2`; the material and mate claims' `proves`.
- `tests/agent/test_board_stockfish.py` (Stockfish 19, gated, 5): 26...Re8's lost defence of f7
  and its same reply `[Bd7, Bxf7+]` answered by `Nxf7` with no second search; 27...Nxf7's of e8;
  31...Qf6's of f5; none of f5 or d6 at 28...Qe6; 38...Rxh5 a weakness of Black's; 9...b5's
  threats on White's bishop, the same reply `[a6, Nb5]` answered by `axb5`, the material claim's
  `proves`; 13.Rxd7's gain for White and its double attack; every served proposition verifies at
  each.
- Changed: the digest's keys and steps (`board`, step 0), Korean `problem` with `problem_en` in
  two refusal tests, `commentary_check_v2`, the cache test reads `view: "full"` (a digest's same
  reply searches), the guidance pin `agent_guidance_v5`, the prompt names.
- rev. 2 (`test_board.py`, 3 more): an en passant capture in a line said with the pawn it takes
  (an illegal move ends the line); a digest whose played move is en passant names it; a range over
  the per-call bound points to `analyze_game`. The Stockfish tests are unchanged and pass with the
  items read from `pattern_delta`.
- Fixtures: `tests/agent/fixtures/opera_game.pgn`, `tests/agent/fixtures/weak_engines_1.pgn` (the
  framing note's new game).

Results: see §4.

## 4. Acceptance trial (2026-10-18)

HIMARI v3 drove one conversation a trial, as in AG7-D §0, against this branch (`972a339`) and
against `main` (AG7). luna (`openai/gpt-6-luna`) ×5 and Haiku 5.5 ×2 per game and arm, four
games: the Opera Game, the rapid fixture, `weak_engines_1` (the framing note's new game) and a
fourth game of two weak engine settings (67 plies, 0-1), generated before the trial, its fixed
moments chosen from its `game_overview` moments before the first run: 19.Nh6+, 19...Kh8,
28...Bxg3. `main`'s runs reuse AG7's acceptance runs and the framing note's today-arm runs (same
code) and add the rest: 44 new runs, about $0.6.

Means a run (luna; Haiku in brackets):

| Game | Arm | Moments saved | Sentences citing a reason at the fixed moments | Same reply cited | Refused submissions | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| Opera | main | 6.6 (6.0) | 2.6 | 0 | 1.2 | $0.013 |
| Opera | AG8 | 6.0 (2.5) | 4.4 | 1.4 | 1.6 | $0.011 |
| Rapid | main | 8.2 (8.0) | 0.8 | 0 | 1.2 | $0.012 |
| Rapid | AG8 | 8.2 (9.0) | 5.4 | 1.6 | 1.6 | $0.013 |
| New game | main | 3.0 (3.0) | 4.0 | 0 | 1.2 | $0.011 |
| New game | AG8 | 3.0 (3.0) | 6.6 | 0 | 1.4 | $0.009 |
| Fourth | main | 5.2 (5.0) | 3.4 | 0 | 1.4 | $0.015 |
| Fourth | AG8 | 5.0 (2.5) | 8.2 | 1.6 | 1.6 | $0.011 |

A `ply` digest took 0.17 s (median of the batches of `ply` calls) against 0.05 s on `main`; the
same reply used 2.0–6.0 searches a game (luna's mean).

Wrong sentences at the twelve fixed moments, by hand (AG7-D §7's marks), over luna's five runs:

| Game | main | AG8 |
| --- | --- | --- |
| Opera | 0 | 1 — "the bishop it cannot keep" said of White's c4 bishop for the bishop Black loses on b4 |
| Rapid | 0 | 0 |
| New game | 3 — two "38...fxg3 takes a bishop", one "the actual moves" for the engine line | 3 — "38...fxg3 takes a bishop" (one run's twice, in two submissions of the moment) |
| Fourth | 0 | 0 |
| **All** | **3** | **4** |

No wrong sentence came from a board item that is wrong on the board. 38...fxg3 is not a move of
the game: it is the engine's best move at 38...Rxh5, an en passant capture of the pawn that came
from g2 to g4; both arms read it as a capture on g3 (of a bishop). The Opera Game's sentence mixes
two correct items of one moment, a threat on White's bishop on c4 and the loss of Black's on b4.

The criteria (AG8-D §9), over all luna runs:

1. wrong sentences no more than `main`'s, none from a wrong board item: **not met** — 4 against 3
   (none from a board item);
2. sentences citing a reason at the fixed moments at least twice `main`'s: **met** — 24.6 against
   10.8 (2.3×);
3. every fixed moment in 90% of the runs: **met** for luna (every run, every fixed moment); every
   Haiku run saves every moment: **not met** — three of eight AG8 Haiku runs saved part of the
   game (2, 3 and 0 of 6, 6 and 5 moments): each opened the game with `open_game(plies: "1-33")`,
   was refused by the per-call bound (16 analyses), analysed a range only (`analyze_game(plies)`)
   or asked the user; one `main` Haiku run made the same first call and recovered;
4. refused submissions at most `main`'s plus one: **met** (1.4–1.6 against 1.2–1.4);
5. no sentence outside Korean: **met** (0);
6. cost at most 1.3 times `main`'s, a digest at most 2 s more: **met**.

Reported: the same reply cited 1.4–1.6 times a run where it is served (none on the new game, where
the best move's reply is illegal or the item was not computed); notes given 1.4–8.0 a run;
`states` on 4.6–11.6 sentences a run, a board item stated whole on 1.8–10.4.

### 4.1 After rev. 2 (§2 items 6–8)

A shorter rerun on rev. 2, as above: luna ×3 on the Opera Game and the new game, Haiku 5.5 on the
Opera Game, the new game and the fourth game (×1, ×1, ×2); 10 runs, about $0.15.

| Game | Model | Arm | Runs | Moments saved | Fixed moments saved | Sentences citing a reason at the fixed moments | Refused submissions | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Opera | luna | rev. 2 | 3 | 6.0 | 3.0 | 4.7 | 1.7 | $0.012 |
| New game | luna | rev. 2 | 3 | 3.0 | 3.0 | 6.0 | 1.7 | $0.010 |
| Opera | Haiku | rev. 2 | 1 | 6 | 3 | 2 | 2 | $0.023 |
| New game | Haiku | rev. 2 | 1 | 3 | 3 | 2 | 2 | $0.019 |
| Fourth | Haiku | rev. 2 | 2 | 5.0 | 3.0 | 3.5 | 1.0 | $0.018 |

(`main` and rev. 1 as in §4: Haiku `main` $0.016, $0.012, $0.020.)

- **Haiku**: every run saved every fixed moment and as many moments as `main`'s. All four opened the
  game with a range first, were refused with the new pointer, opened it without `plies` and called
  `analyze_game`. Their cost is that of a whole game analysed: above `main`'s on the Opera Game
  (1.4×, one run), within 1.3× on the others.
- **Wrong sentences at the fixed moments**, by hand: luna 1 in 6 runs — "g3 칸에서 백 폰을 먼저
  잡는" for 38...fxg3 (the pawn taken is on g4); the other two luna runs on the new game wrote it
  right ("…fxg3로 g4폰을 먼저 없애고"), as did Haiku ("f4 폰이 g3로 앙파상하는 38...fxg3").
  Opera 9...b5: no c4/b4 mix in four runs. Haiku 0, with two sentences of broken Korean at
  38...Rxh5 (a reading, not a fact; "키스한 룩 손실").
- Over the same games and the same luna runs counted in §4 (Opera and the new game, five each),
  `main` had 3 and rev. 1 had 4; rev. 2 has 1 in three each.
