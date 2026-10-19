# Agent BL — a blunder's reason from the facts (implementation)

Status: **rev. 1 — for independent review**. Date: 2026-10-19. Design:
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

The suite: (pending).

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
| Weak plies whose item order changed | 14 |

## 4. The trial (BL-D §9.3, owner Q3: short)

(pending)

## 5. Review dispositions

(none yet)
