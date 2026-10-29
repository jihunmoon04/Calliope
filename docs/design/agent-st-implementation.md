# Agent — packet ST implementation: the scene before the move, since when, rich's material, the guide v8

Status: **rev. 2 — independent review of rev. 1 (`85d3783`) READY_WITH_CORRECTIONS (N1–N6) applied (§5).** Date: 2026-10-29. Design:
[`agent-st-design.md`](agent-st-design.md) (ST-D) rev. 3: D1–D6, owner decisions O1–O3 (§8), tests and
acceptance (§9). Base: `design/st` (ST-D, PR #135), stacked; `main @ bf2ee80` below it.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/board.py` | `board_v4`. D1: `_scene` — the previous move's `began` relations against the mover (attack, exposed, check, double attack, absolute pin), the attack under an exposure and an attack/exposure on a `held` piece dropped, `limited`, `_scene_order` (check first, then stake, value, square), at most `SCENE_ITEMS = 3`; texts and fates by the attacker; propositions before (and the attacks still standing after); `board.scene` its own list, built after `_link`, served after the changes. D2: `_since` (new / since k / at least since k at `SINCE_PLIES = 16` / from the start; a type change ends the walk), `_attacks` (python-chess attack sets by piece identity), `_pos` (`{"ply": 1, "at": "before"}` for the root); since sentences on `lost_defence`, `held`, exposed `weakness` and exposed `threat` (its attacker by `_attacker(child, …)`). §7: `_append` — a part whole or not at all, with its propositions and move token, room kept for `OPPONENT_FIRST` on threats; `_link`'s remark goes through it. D3: `_structure` (`structure`, `file` items after the relation items). The moves an item names are tokens of that item only (`extra_moves`) |
| `agent/remarks.py` | `board_remarks_ko_v5`; `ITEM_CAP = 480`; `appended`, `since_words`, `since_lost_defence`, `since_held`, `since_exposed`, `scene_proves`, `scene_fate`, `structure_proves`, `file_proves`; `with_opponent_first` keeps room under `ITEM_CAP` |
| `agent/digest.py` | `others` shown (numbered move and 6-ply line), out of `not_shown` and `BEHIND_DETAIL`; step 0 cuts `file`, then `structure` beyond 1, then scene beyond `SCENE_KEEP = 1`, then today's kinds; step 2 shortens `others`' lines too |
| `agent/propositions.py` | `pawn` and `file` (from `pawns_v1`; refusals for a square without a pawn, another flag, another letter or state) |
| `agent/session.py` | `commentary_check_v6`: `_notes` gives none; `_keep_board` lists the scene after the changes |
| `agent/definitions.py` | `agent_tools_v6` (`submit_commentary`'s kinds list gains `pawn`, `file`), `agent_guidance_v11`, `proposition.pawn`, `proposition.file`, `prompt.commentary_ko_v8`, `board.board_v4`, `board.scene`, `board.since`, `board.structure`, `board.file`, the `held`/`threat`/`weakness`/`lost_defence` statements, `board_remarks_ko_v5`, `commentary_check_v6` |
| `agent/prompts/commentary_ko_v8.md`, `server.py`, `build.py` | the guide as ST-D Appendix A, served at `calliope://guides/commentary_ko` and as the `calliope_commentary` prompt; v7 kept as data. The server's instructions are unchanged |
| `server/commentary.py`, `viewer/index.html` | `POSITION_KINDS` gains `pawn`, `file`; the viewer's lines "폰: …", "파일: …" and a `pawn`'s ring; `positionMarks` exported for the tests |

## 2. Choices and departures

- **`TOOLS_VERSION` moved to `agent_tools_v6`**: ST-D §7 said "only if a tool's description changes"; it does —
  `submit_commentary`'s description lists the proposition kinds. For the same reason the guidance pin
  (`agent_guidance_v11`) is a new digest, not v10's.
- **The notes are off by `_notes` returning none**, not by removing its call: the check's version and the
  answer's shape (`notes` absent when empty) stay as they were for an answer without notes.
- **`since_held` names no move**: "이 수는 그 공격을 피하지 못했다" instead of "{move}는", which needed a particle
  after a move's SAN.
- **CV4's note tests** (four of them, and v3/v4 note comparisons) are replaced by one test that the notes are
  off; they tested what this packet removes.
- **`after_reply` compares the kinds it compared before** (`AFTER_REPLY_KINDS`): adding `pawn`/`file` to the
  position kinds would have let it nest them, which ST-D does not ask (review N5).
- **The real-game cases of ST-D §9 tests 1–2** (34...Qb3, 26...Re8, 27...Nxf7) are checked by the acceptance's
  every-ply runs on the four games (§4.2, and the review's reading of them), not by unit tests; the unit tests
  build the same shapes from FENs over the synthetic engine (review N3).
- The trial arm's "26.Kc1 뒤부터" at 34...Qb3 (`lost_defence`) is now "적어도 26.Kc1 뒤부터": the walk reaches its
  bound there (ST-D §3.1, review B1 of ST-D).

## 3. Tests

- `tests/agent/test_st.py` (30): the scene (an attack that stands, one that ended by that attacker, the
  attacker taken, none at ply 1, an exposure on a held piece said by the `held` item, an exposure with its
  attacker and count, `judge_move`'s same scene with its own fate and `from_root` positions, the previous
  move as a token, the order); since when (with its three propositions, new, from the start at ply 1 and
  verified after some plies — re-review C1 —, exactly the bound, at least since the bound, a promotion ending
  the walk, an exposed threat with its attacker's three attacks, a new attacker on a weakness, tokens only on
  the items that name the move); `structure` and `file` items and their place; `pawn`/`file` verification
  and refusals; `others`; the caps — the functions, and at the board: a part that does not fit leaves its
  propositions and token, a threat keeps room for `opponent_first`, a real board's items under `ITEM_CAP`
  uncut (review N1); step 0's order with files, structure and the scene, step 2 on `others` (review N2); a
  submission citing a scene item may write its previous move, and is refused (S3) without it (review N3);
  no notes.
- Updated: `test_board.py` (`board_v4`; `judge_move`'s positions on its path; the served index after the
  scene; no notes; `commentary_check_v6`), `test_bl.py` (the suffix under `ITEM_CAP`; `_link`'s fake with
  `_append`), `test_board_stockfish.py` (a lost defence's first two propositions), `test_piece_relations.py`
  (`structure`/`file` are no relation), `test_digest.py` (`others`), `test_guidance.py` (v8, 17 proposition
  kinds, `agent_guidance_v11` and its digest), `test_server.py`, `test_commentary.py` (versions),
  `test_cv4.py` (§2), `tests/viewer/test_viewer_ai.py` and `check_ai.js` (the two display lines and marks).
- Full suite with Stockfish: **1879 passed** (23.8 min) at `189059c`.

## 4. Acceptance (ST-D §9)

1. **The replay.** Every position proposition stored by FR rev. 3's 24 runs (852: v7 229, rich 218, story
   405) re-verifies on ST's code against freshly built answers: none refused. Judgements, claims and lines
   are not changed by ST and were not re-checked. Departure from §9's wording: the stored sentences were not
   re-submitted through `commentary_check_v6` — cited board items changed their handles and propositions, so a
   resubmission would test the mapping, not the check; the check's rules S1–S8 are unchanged and covered by
   the suite.
2. **The bound and nothing lost.** Over the four games' 271 plies, `main` against ST (each from the warm
   analyses, a fresh session):

   | Game | Plies | Largest digest (main → ST) | Mean | Bound steps | Refused items | main's items not served by ST |
   | --- | ---: | --- | --- | ---: | ---: | ---: |
   | hung (#123) | 71 | 6,059 → 9,206 | 2,789 → 3,653 | 0 / 0 | 0 / 0 | 0 |
   | rapid | 55 | 6,460 → 8,384 | 2,618 → 3,437 | 0 / 0 | 0 / 0 | 0 |
   | fresh | 78 | 6,402 → 7,234 | 2,463 → 3,217 | 0 / 0 | 0 / 0 | 0 |
   | fourth | 67 | 5,453 → 7,277 | 2,723 → 3,622 | 0 / 0 | 0 / 0 | 0 |

   ST serves 632 board items where `main` serves 367, and every one of `main`'s is among ST's with its
   propositions as their first ones. Size refusals (`MAX_PROPOSITIONS`) in the trial below: none counted
   (refused submissions 4.25 a run against v7's 3.75, by other rules).
3. **Tool time.** The `ply` answers of the four games, warm, run alone: `main` 305.2 s, ST 307.3 s (+0.7%);
   medians 0.81–1.14 s against 0.90–1.13 s.
4. **The short trial** (luna ×2 a game on the four games, the setup of ST-D §0; tag `t-`, session `e058e396`'s
   `fr3`). Means a run:

   | | v7 (rev. 3) | story (rev. 3) | ST |
   | --- | ---: | ---: | ---: |
   | Sentences | 52.1 | 50.0 | 52.6 |
   | … at a fixed moment | 5.0 | 4.7 | 5.3 |
   | Sentences citing a reason | 26.9 | 25.6 | 26.9 |
   | Interpretations | 12.9 | 12.6 | 13.2 |
   | Commentaries opening with the move's name | 88% | 44% | 32% |
   | Interpretations ending in "보입니다/보인다" | 19% | 0% | 0% |
   | Sentences with "이미", "여전히", "○ 뒤부터" … | 0.9 | 4.1 | 3.9 |
   | Refused submissions | 3.8 | 3.8 | 4.3 |
   | Cost | $0.018 | $0.018 | $0.017 |

   Blind: ST's fixed-moment commentaries mixed with rev. 3's v7 and story ones (72, 24 an arm), one
   fresh-context judge with ST-D §0's instructions, the reference built by ST's code:

   | | v7 | story | ST |
   | --- | ---: | ---: | ---: |
   | Sentences | 121 | 112 | 126 |
   | Wrong | 7 | 3 | 2 |
   | … per 100 | 5.8 | 2.7 | 1.6 |
   | … of them an old attack read as new | 5 | 1 | 0 |
   | … other kinds | 2 | 2 | 2 |
   | Doubtful | 8 | 4 | 4 |
   | Mean score (1–5) | 3.00 | 3.38 | 3.58 |

   ST's two wrong sentences:
   - 34...Qb3 (hung-1): "퀸이 c5 폰을 지키던 자리에서 벗어나자, 백 룩 c4의 공격에 그 폰을 내주게 됐습니다" — the
     c5 pawn stays defended by the c8 rook (the `lost_defence` item says one defender, one attacker);
   - 20...c6 (rapid-2): an interpretation blaming the f5 knight still eyed by the queen; the knight is defended
     by the c8 bishop and the line turns on 21.dxc6.

   **The criteria are met:** old attacks read as new 0 (story's 1, +1 allowed); other kinds 2 (story's 2);
   no wrong sentence from a false fact in a scene's or a since text — both misread items whose texts are true
   (the second drew a cause from the scene's true "f5 나이트는 … 공격을 계속 받는다"); wrong per 100 1.6 against
   v7's 5.8.

   Limits, as in ST-D §0.5: one judge, one model, 24 commentaries an arm; this judge counted v7's rev. 3
   commentaries 7 wrong where rev. 3's judge counted 11 — the arms compare within one judging only.

## 5. Review dispositions — rev. 1 (`85d3783`), independent review: READY_WITH_CORRECTIONS

The reviewer found no correctness bug. It probed castling, en passant, promotions, pins, a fork with check,
`judge_move` off the game path and at the root, and FEN starts; it re-derived §4's numbers from the data.

| Finding | Disposition |
| --- | --- |
| N1 the caps' integration untested (two mutations of `_append` survived) | Applied: three board-level tests (§3) |
| N2 no test for step 0 with the new kinds nor step 2 on `others` | Applied: two tests (§3) |
| N3 §9's real-game cases and test 4's submission | Applied: a submission test; the real-game cases stated as the acceptance's (§2) |
| N4 a since sentence on a piece that moved says "그 칸" of a new square; the scene's "계속 받는다" on a defended piece | Recorded for the owner: as ST-D §3 says (by piece identity). A later wording packet could name the squares before and after when the target moved, and whether the piece is defended |
| N5 `after_reply` accepted `pawn`/`file` | Applied: `AFTER_REPLY_KINDS`, as before (§2) |
| N6 the scene's first part not capped; a link remark that does not fit keeps `leads_to`; `remarks.POSITION_KINDS` dead | Applied: `scene_proves` capped at `PROVES_CAP`. Recorded: when `link_remark` does not fit, `leads_to` stays (the claim still leaves `claims` by `settle`); unreachable at today's lengths (the longest item 9,206-character digests hold stay far under `ITEM_CAP`). `remarks.POSITION_KINDS` predates this packet; left |
