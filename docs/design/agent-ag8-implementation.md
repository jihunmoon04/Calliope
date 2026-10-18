# Agent — AG8 implementation: the reasons with the ply

Status: **rev. 1 — for independent review**. Date: 2026-10-18. Base: `main @ 821edd3` (AG8-D
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
- Fixtures: `tests/agent/fixtures/opera_game.pgn`, `tests/agent/fixtures/weak_engines_1.pgn` (the
  framing note's new game).

Results: see §4.

## 4. Acceptance trial

(pending)
