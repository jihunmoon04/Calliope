# Agent MS-b — `board_v2`, groups and a smaller digest

Status: **rev. 1 — for independent review**. Date: 2026-10-18. Base: `main @ 135a0d3` (MS-a
merged). Design: [`agent-ms-design.md`](agent-ms-design.md) §6–§8 (R5–R7). Citing by handle, the
derived use, the guide and the trial are MS-c's.

## 1. What was built

| MS-D | Where |
| --- | --- |
| R5 §6 `board_v2` | `agent/board.py`: `Board.build(analysis)` makes the items from `piece_relations.move_relations` on the session's facts tree, `limited` as AG8's; each item as AG8's (kind by side, propositions before and after, `proves`) with a `ref`, a handle of the new kind `b` (`agent/handles.py`; `detail` gives the item). `_link`: a SUPPORTED relation claim whose relation at the move is an item's — `PieceRelation.identity()`: kind, pieces, place, time — is that item's `leads_to` (`claim`, `template`, `link`, `to`, `to_template`, `did`), its sentence added to the item's `proves` (`remarks.link_remark`); one whose relation held is a `held` item (`_held`: `exposed` before and after; `remarks.held_proves`); the others are listed with their `relation` and `link` (`session._annotate`). `agent/digest.py` `settle`: after the bound, a claim leaves `claims` only when its item is shown; a linked item moved out is named in `not_shown.named` (`{"board", "ref", "leads_to"}`) and its claim stays listed |
| R6 §7 groups | `digest.GROUPS`, `digest.grouped`: the first SUPPORTED member by what it names, else the first INCONCLUSIVE; `also` with `ref`, `template`, `status`, `proves` |
| R7 §8.1 | `digest.digest`: no `says`, no `text`; `findings` only for a claim with no `proves`; `not_shown.refuted` and `not_shown.others` by their refs; `lines` holds the played and best lines only; the session no longer phrases Calliope's sentences for the digest |
| R7 §8.2 | `agent/remarks.py` `board_remarks_ko_v2`: `claim_remark` gives `(proves, Tokens)` for every template (the table of MS-D §8.2), `claim_proves` its text |
| R7 §8.3 | `remarks.Tokens` records the moves (with their positions), squares and numbers a `proves` writes; `propositions.Verifier._claim` adds them to the cited claim's S3 tokens, built again from the claim's record |
| the bound | `digest.bounded`: step 0 keeps a linked or `held` item before a plain one of its kind (`BOARD_KEEP` adds `held: 0`); a new step `also` after it names a group's other members; the `text` step is gone (no text in the digest); `findings` counts only where shown; `named_left_out` takes from `not_shown.refuted`, `others`, then `named` |
| registry | `board.board_v2` (was `board_v1`), `board.held`, `board.leads_to`, `board_remarks_ko_v2` |

## 2. Where the implementation departs from the design, and why

1. **No em dash in a `proves`.** The test that writes every template's `proves` as a sentence
   (§3) found the AG8 texts refused: S3 reads "—" as a sign standing apart from a number. Material
   and mate claims' `proves` (AG8-D §4) and the brackets of `threat` and `weakness` used it; they
   now use ":" and "," (`[흑(둔 쪽)의 위협: 백의 기물이 …]`, `… 메이트한다 (마지막 수 30.Ng5#, 이
   라인에서만)`). The meaning is AG8's.
2. **No "%p".** A Latin letter after a number is a token of its own for S3; a loss in expected
   points is written `… 15퍼센트포인트`, and the ranks `1순위`, `2순위` are tokens of their `proves`.
3. **`mate_in_one_allowed_v1` has a `proves` without a move.** Its finding is exact and names no
   mating move (R2-D §3.3a); its `proves` says the other side can mate in one, and nothing else.
4. **`relation` and `link` on listed claims.** MS-D §6 item 4 shows them for a relation claim in
   the engine line; a relation claim at the move that no item shows (an item not served — refused
   or limited) is listed with them too, so its relation is never lost (I4).
5. **The registry's board entries now, the guide in MS-c.** `board_v2` is what the digest serves,
   so the registry says so in this packet; `commentary_ko_v3` still warns against translating
   `text` and `says`, which no digest carries now — harmless, and replaced by `commentary_ko_v4`
   in MS-c.
6. **The fourth game is a fixture.** `tests/agent/fixtures/weak_engines_2.pgn` (the AG8 trial's
   fourth game) holds the one `best_stops_reply_v1` the four games have.
7. **The relations are public names of `calliope.reasoning`.** The agent imports only a
   package's public names (`test_package_boundaries`); `move_relations`, `limited`,
   `claim_relation`, `PieceRelation`, `ClaimRelation`, `Place`, `MOVE` and `RELATION_FAMILIES`
   are exported from `calliope.reasoning`.
8. **MS-a's comparison leaves the `held` items out.** `test_piece_relations.same_as_board`
   compares the board with `limited(move_relations(...))`; a `held` item is a claim's (MS-D §6
   item 3), not a relation the move began or ended, so it is not in that set.

## 3. Tests

- `tests/agent/test_ms_b.py` (5): a group shows its first SUPPORTED member and keeps the others'
  status in `also` (review B5); a claim leaves the list only under a shown item; a linked item the
  bound moved out leaves its claim listed and the item named (review B4); the steps; a link's
  sentence says what the graph holds (`associated_with`: "원인으로 확인되지는 않음").
- `tests/agent/test_ms_b_stockfish.py` (Stockfish 19, gated, 29): 31...Qf6's lost defence f8→f5
  carries `removed_defender_v2` (not listed again), f5 is `held` for `left_en_prise_v2`, the
  discovery listed with its line place, `detail` of the `b` handle; 38...Rxh5's weakness carries
  `newly_exposed_v1` (`explains`), 13.Rxd7's double attack `fork_v2`; **every one of the 26
  templates' `proves`, written as it stands in a sentence citing its claim, is accepted** (I5);
  every claim is reachable at the examples' plies (I4).
- `tests/agent/test_digest.py`: the digest's keys (no `text`, no `refuted`), every claim reachable
  (I4), `not_shown.refuted` and `others`, a claim without `proves` keeps its findings, the steps.
- Changed: `board_v1` → `board_v2`, the brackets' wording, the mate `proves`.

## 4. Results

A `ply` digest's characters, `main` (MS-a) against MS-b, by `size` (the compact JSON a tool
sends), the same analyses:

| Plies | `main` median / mean | MS-b median / mean | Change (median / mean) |
| --- | --- | --- | --- |
| The trial's 12 fixed moments | 5,836 / 5,744 | 4,025 / 4,134 | −31% / −28% |
| Every ply of the Opera Game and the rapid game (88) | 2,712 / 3,168 | 2,420 / 2,617 | −11% / −17% |

At the fixed moments the cut is MS-D §8.1's estimate (0.70): `findings` (1,014 characters a
digest), `refuted` (400), Calliope's `text` (251) and the other candidates leave; `proves` for
every claim (+87), `also` (+239), the `b` refs (+94) and `leads_to` (+55) come. A quiet ply has few
claims, so little leaves. MS-D §13 criterion 4 (25% fewer at the median, measured by the trial on
its fixed moments) is MS-c's to measure.

Full suite (Stockfish 19): **1691 passed**. ruff check and format clean. The reasoning build is MS-a's (no reasoning rule changes here).
