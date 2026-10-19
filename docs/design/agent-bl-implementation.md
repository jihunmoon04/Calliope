# Agent BL — a blunder's reason from the facts (implementation)

Status: **rev. 2 — review of rev. 1 (`0414a93`) READY_WITH_CORRECTIONS (B1, B2; N1–N7) applied (§5); BL-D erratum E1**. Date: 2026-10-19. Design:
[`agent-bl-design.md`](agent-bl-design.md) (BL-D rev. 4; owner Q1, Q2, Q4 as recommended, Q3 a
short trial after the implementation). Issue: [#123](https://github.com/jihunmoon04/Calliope/issues/123).
Base: `design/bl @ d8c2d31` (BL-D on `main @ f07b8d8`).

## 1. What changed

| Item (BL-D §8) | Change |
| --- | --- |
| L1 | `reasoning/piece_relations.py`: `move_relations` gives a `held` `exposed` relation for each of the mover's pieces (not the king) exposed before and after the move, by `held_exposed`, when the mover was not in check before; the mover's exposed relations, began and held, sorted together by value; `FORMAT = "piece_relations_v2"`. |
| L2 | `agent/board.py` (`board_v3`): `_gated` (a held relation at gain ≥ `HELD_GAIN` = 3, any gain on a weak move) before `limited`; `_weakness` and `_held` with the `attack` of `exchange.first_capture` (`_attacker`), the in-check clause; `_link` matches a claim's held relation to the facts' `held` item by `identity()`, else builds a claim-made one as before; on a weak move the items other than threats by `_stake`, then the threats; `_opponent_first` (§5 (3)); `_played_material` with the pure rule `played_points` (§4, owner's review O1) and `_balances`. |
| L3 | `agent/remarks.py` (`board_remarks_ko_v3`): `weakness_proves`, `held_proves` (one attacker moved or not, two attackers), `played_material_proves`, `OPPONENT_FIRST` and `with_opponent_first` (the text capped at `PROVES_CAP − len(suffix)`). |
| L4 | `agent/digest.py`: step 0 keeps the first item on a weak move and every `opponent_first` target, by identity, before `BOARD_KEEP` applies; `played_material` is outside step 0. |
| L5 | `agent/session.py`: `_keep_board` lists `played_material` after `same_reply`; the reason flag counts board items of part `reason` and SUPPORTED claims of part `reason` (O2); `CHECK = "commentary_check_v5"`. |
| L6 | `prompts/commentary_ko_v5.md` (the `board` section: `weakness`'s attacker, `held` without "방치", `opponent_first`, `played_material`, the order); `build.PROMPTS`; every `commentary_ko_v4` in `server.py`; `definitions.py` (`board_v3`, `held`, `weakness`, `played_material`, `opponent_first`, `board_remarks_ko_v3`, `commentary_check_v5`, `piece_relations_v2`, `prompt.commentary_ko_v5`); `GUIDANCE_VERSION = "agent_guidance_v8"` (its pin: the searches it digests are unchanged, so the same digest as v7). |
| L7 | `docs/design/README.md`: this packet's row. |

Notes:

- The board reads `first_capture` at the position before from the records `Board.build` already
  ensures there (`pieces`, `exchange`); no record is added to any analysis.
- `played_material` is verified like every item (`Verifier._material`): a refusal is counted in
  `refused` and no item is served (no refusal in the replay, §3).
- `digest.WEAK` repeats `board.WEAK_GRADES`: `board` imports `digest`, so the reverse import would
  be circular.
- The guide says two things BL-D §6 does not spell out (review N4), both read from what the items
  verify: a `held` item's attacker that is the same piece before and after may be said to keep
  aiming at it ("같은 ○가 계속 노린다"; the two `attack` propositions name it), and on a weak move
  the costs come first by what is at stake (§5 (1)).
- `played_material`'s one-proposition form (`k = n`) cannot occur: condition 3 makes ply `n` quiet,
  so `b_{n−1} = e` and `k < n`. It is kept as BL-D §4 gives it; its text is tested, not its build.
- A promotion keeps the piece's identity (`facts/identity.py`), so a pawn exposed before and its
  promoted piece exposed after is `held`; its text names both pieces (review B1, BL-D E1).

## 2. Tests

- `tests/agent/test_bl.py` (synthetic engine and pure rules, 15): a piece held where it stood and
  one moved along its attacker's line (the texts, the propositions); after a check a `weakness`
  that says "수 전에는 체크 중이었다" and no `held`; a new weakness's `attack`; the gate; the
  one- and two-attacker texts; `played_points` on 34...Qb3's line, a line ending on a capture, not
  behind, one ply, a best line as far behind (13.Rb1), a best line cut after a capture (N12) and
  one with no quiet ply (O1), `k` at the end; `_stake`; the suffix within the cap; step 0 keeping
  the first item and the target on a weak move and today's counts otherwise; the reason flag
  (INCONCLUSIVE reason claims no reason, SUPPORTED ones and reason items a reason).
- `tests/agent/test_bl_stockfish.py` (Stockfish 19, gated, 4) on issue #123's game
  (`tests/agent/fixtures/hung_queen.pgn`, moves only): 34...Qb3, 7...Bxe2, 13.Rb1 and 34.Rf3 as
  BL-D §8 lists them, every served proposition verifying as given.
- Changed: `test_piece_relations.same_as_board` compares the board's items with the gated and limited
  relations, the facts' `held` items included (review N18); `test_board_stockfish._all_verify`
  verifies `played_material` too; the version pins (`board_v3`, `commentary_check_v5`,
  `commentary_ko_v5`, `agent_guidance_v8`, `piece_relations_v2`); `held_proves`' new signature in
  `test_ms_b`.

The suite (`PYTHONPATH=src`, `CALLIOPE_STOCKFISH_PATH` set; run beside the 15 trial runs):

- on `b5205e2` (rev. 2's code): **1775 passed**;
- on `fe94a01` (rev. 1's code): 1766 passed, 1 failed —
  `tests/agent/test_game_jobs.py::test_a_cancel_while_the_job_is_active_always_ends_cancelled`, the
  known stop-timing flake under load; it and `tests/agent/test_bl_stockfish.py` passed three times
  in a row alone;
- a first run on `23f804b` failed `test_ms_b_stockfish.py::test_31_qf6` (31...Qf6 has two held
  items now, the d5 bishop first by stake; since `fe94a01` the test picks the f5 item),
  `test_game_path.py::test_the_job_budget_holds` (job timing under load) and once
  `test_bl_stockfish.py::test_7_bxe2` (its text lost; it passed alone three times and in the
  second full run);
- `main @ f07b8d8`: 1748 passed.

## 3. The replay (BL-D §9.2)

Every ply's digest of the four games (271 plies: issue #123's game, `chesscom_rapid_813_801`,
`fourth`, `fresh`) on `f07b8d8` and on this branch, from the same cached analyses:

| Criterion | Result |
| --- | --- |
| `held` items | 19 on 17 plies (3 blunders, 3 mistakes, 8 inaccuracies, 3 best, 2 excellent by item), the survey's list |
| Items `f07b8d8` serves and this branch does not | 0 |
| `played_material` | 2: 34...Qb3 (`(2, −9), (8, −9)`), 34.Rb4 (`(6, −1), (7, −1)`) |
| Refused items | 0 |
| Digests over the bound (step 0 run) | 0; largest 6,246 characters of 16,000 |
| Size | +65 characters a digest on average, +1,420 at most |
| Weak plies whose item order changed | 14, mostly by new `held` items; items `f07b8d8` serves reordered on 3 (review N5) |

## 4. The trial (BL-D §9.3, owner Q3: short)

As MS-c's (MS-c §4): HIMARI v3 drove one conversation a run ("이 대국을 분석하고 중요한 장면들을
해설해서 저장해 줘" and the PGN), on this branch (`23f804b`, the code of rev. 1) — luna
(`openai/gpt-6-luna`) ×2 and Haiku 5.5 ×1 on each of four games: issue #123's game (moves only,
fixed moments 7...Bxe2, 13.Rb1, 34...Qb3), the rapid game, `fresh` and `fourth` (their fixed
moments as AG8-D §9). Against `main` (`f07b8d8`) on issue #123's game, the same counts; the other
three games against MS-c's records (luna ×5, Haiku ×2). 15 new runs, $0.20.

Means a run (luna; Haiku in brackets):

| Game | Arm | Moments saved | Fixed moments saved | Sentences citing a reason at the fixed moments | Refused submissions | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| #123's game | main | 8.0 (8) | 3 (3) | 4.5 (3) | 1.0 (1) | $0.009 ($0.020) |
| #123's game | BL | 8.0 (8) | 3 (3) | **7.5 (8)** | 0.5 (2) | $0.009 ($0.026) |
| Rapid | MS-c | 8.6 (7.0) | 2.8 (3) | 4.6 (5.0) | 0.6 (1.5) | $0.008 ($0.023) |
| Rapid | BL | 8.0 (8) | 3 (3) | 5.0 (6) | 1.0 (1) | $0.009 ($0.026) |
| Fresh | MS-c | 3.2 (3.0) | 3 (3) | 5.8 (5.0) | 0.4 (0.5) | $0.007 ($0.013) |
| Fresh | BL | 3.5 (3) | 3 (3) | 4.0 (6) | 0.5 (2) | $0.009 ($0.016) |
| Fourth | MS-c | 6.0 (5.0) | 3 (3) | 6.0 (6.5) | 0.2 (1.5) | $0.009 ($0.017) |
| Fourth | BL | 5.0 (5) | 3 (3) | 5.5 (5) | 1.0 (1) | $0.009 ($0.018) |

**The criterion of BL-D §9.3, the queen.** At 34...Qb3 and at 7...Bxe2 every BL run (3 of 3)
says the queen can be lost, citing the `held` item: "34...Qb3 뒤 흑 퀸은 백 룩 c4를 공격했지만,
동시에 백 룩 f3의 공격을 받아 교환상 위험해졌다", "7...Bxe2 뒤에도 흑 퀸 e5는 백 폰 f4의 공격을 받고
있으며"; at 34...Qb3 each also cites `played_material` ("35.Rxb3로 퀸을 잃은 뒤 흑은 물질에서 9점
뒤진다"). On `main` the three runs say 34...Qb3 loses the queen through the engine line (35.Rxb3),
and none says at 7...Bxe2 that the queen stays attacked: two write the bishop's double attack (one
with the line's 8.Qa4+), one the line's 8.Qa4+. **Met.**

**Wrong sentences at the fixed moments** (by hand, AG7-D §7's marks; recounted after the review's
B2), all at 34...Qb3:

| Run | Sentence | Why wrong | From |
| --- | --- | --- | --- |
| bl-hung-1 (luna) | "백은 35.Rxb3로 흑 퀸을 잡고 9점의 물질 우위를 얻는다" | White is 6 up after 35.Rxb3: Black was 3 points up before the move | `played_material` without "수 전보다" |
| bl-hung-1 (luna) | "여왕 교환을 허용하면서" | a queen lost to a rook is no exchange of queens | issue #122's E2 (a term) |
| bl-hung-2 (luna) | "그 수 뒤 흑은 물질에서 9점 뒤진다" | 6 behind, as above | `played_material` without "수 전보다" |
| hbl-hung-1 (Haiku) | "…퀸을 잃은 뒤 흑은 물질에서 9점 뒤진다" | as above | `played_material` without "수 전보다" |
| hbl-hung-1 (Haiku) | "…c5 폰도 잃는 장면이 되었다" | the `lost_defence` item says the pawn is attacked, not lost | a misreading of an existing item |

luna 3 sentences in its 2 runs, Haiku 2 in 1; the three other games 0 (MS-c: 0 in 15 runs);
`main` on #123's game 0 in 3 (its "체크로 퀸 교환을 유도" at 7...Bxe2 is right: both queens are
taken in that line). **Not met** ("not above MS-c's"). Three of the five come from the new item:
they cite `played_material` and drop its "수 전보다", which the guide's own example
("35.Rxb3 뒤 9점 뒤진다") invited. Fixed in rev. 2 (the `proves` says a change against before the
move, the guide's example keeps it and says why: BL-D erratum E1); §4.1 re-runs #123's game.

Reported:

- Fixed-moment reasons on the other games are near MS-c's (luna rapid 5.0 / 4.6, fourth 5.5 / 6.0,
  fresh 4.0 / 5.8), on two runs against five: too few to tell a change from noise (review N5).
- The refusals are S3 (a move, a square or a number not in the cited propositions), none from a BL
  item: bl-hung-1's "f4" was a sentence at 10.c5 citing that ply's items.
- Notes are fewer (0.5–4 a run, Haiku's rapid run 4, against MS-c's 4.4–14.8): `commentary_check_v5` no longer counts an
  INCONCLUSIVE reason claim (O2), and the cites rule of CV4.
- Cost: luna the same; Haiku $0.003 above on each game it ran (it wrote more sentences on #123's
  game: 29 against 24).

## 4.1 #123's game again on rev. 2

The same harness on rev. 2's code (`b5205e2`), #123's game only: luna ×2, Haiku ×1, $0.041.

| Arm | Moments saved | Fixed moments saved | Sentences citing a reason at the fixed moments | Refused submissions | Cost |
| --- | --- | --- | --- | --- | --- |
| main | 8.0 (8) | 3 (3) | 4.5 (3) | 1.0 (1) | $0.009 ($0.020) |
| BL rev. 1 | 8.0 (8) | 3 (3) | 7.5 (8) | 0.5 (2) | $0.009 ($0.026) |
| BL rev. 2 | 8.0 (7) | 3 (2) | 5.0 (4) | 1.0 (1) | $0.011 ($0.019) |

- **The baseline.** Every sentence citing `played_material` keeps it (3 of 3): "엔진 라인 35.Rxb3 뒤
  흑의 물질 차이는 수 전보다 9점 나빠진다"; none writes "9점 뒤진다" or "우위".
- **The queen.** At 34...Qb3 every run says the queen is lost or attacked by the rook (3 of 3); at
  7...Bxe2 both luna runs say the f4 pawn still attacks the queen ("백의 f폰이 이미 e5의 퀸을 공격하는
  상황에서", "흑 퀸은 f4폰의 공격 아래 남아 있어"); the Haiku run saved no commentary at 7...Bxe2
  (its 2 fixed moments).
- **Wrong sentences at the fixed moments:** none clear. Two are loose: bl2-hung-2 "퀸이 e3에서 b3로
  옮기자 백 룩 f3가 퀸을 공격하게 됐고" (the rook attacked the queen on e3 too; the `held` item says
  both — rev. 1's bl-hung-1 wrote the same), hbl2-hung-1 "c5 폰도 함께 놓친" (the defence of c5, said
  loosely).
- Fixed-moment reasons are fewer than rev. 1's on these three runs (luna 5.0 against 7.5), still
  above `main`'s 4.5; three runs are too few to read more into it.

## 5. Review dispositions — rev. 1 (`0414a93`), independent review: READY_WITH_CORRECTIONS

| # | Finding | Disposition |
| --- | --- | --- |
| B1 | A promotion gives a `held` text naming the promoted piece before the move (I3). | Applied: `held_proves` takes the types before and after and names each position's piece (`수 전 b7의 백 폰도, 수 뒤 b8의 백 퀸도`); BL-D E1; a test (`1.b8=Q+`). |
| B2 | The guide's `played_material` example drops "수 전보다"; three trial sentences read it as an absolute deficit. | Applied: the `proves` says "물질 차이는 수 전보다 …점 나빠진다", the guide's example keeps the baseline and says why (BL-D E1); §4 recounted (not met); #123's game re-run (§4.1). |
| N1 | Tests missing; the step-0 test passes without the guard. | Applied: a step-0 test whose cut reaches the costs (fails without the guard); the other side's held piece; the gate end to end (11.d3, a best move, no item for the c5 pawn); `opponent_first` on a fake board (the largest target, a tie, not on a check, not in check, not below gain 3); `_played_material`'s conditions (no claim, `MATE_LINE`, SUPPORTED, best is the played move); the `b` handles cited and `judge_move` of the played move giving the same board (Stockfish). Not added: "undecided before" (an in-check entry without a safe-moves record, not expected; and the held row asks for no check before); the claim-made item below the gate or beyond the limit (no fixture has one); `k = n` (unreachable, §1). |
| N2 | Two claims on one held piece: the second overwrites `leads_to` and appends a link. | Applied: the first link stays; the second claim stays listed in `claims` (I4). |
| N3 | A missing attacker: `_held` drops silently, `_weakness` serves without `attack`. | Applied: both count a fault in `refused` and serve no item. |
| N4 | Guide text beyond BL-D §6. | Kept and recorded (§1): both are what the items verify. |
| N5 | Document details. | Applied: the suite (§2), "reordered" (§3), the notes' range and "noise" (§4). |
| N6 | Particles ("나이트은", 은/는 after squares). | Applied: `topic()` for the type; no particle after a square in the two-attacker form; BL-D E1; a test. |
| N7 | "보인 라인의 마지막 수" after `short_pv`. | Applied: "엔진 라인 {n}수째" (BL-D E1). |
