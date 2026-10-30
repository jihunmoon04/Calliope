# Agent — packet WS implementation: where the pieces of a since sentence stood, the count on a kept attack

Status: **rev. 2 — independent review of rev. 1 (`be6ce4b`) READY_WITH_CORRECTIONS (N1–N4; N5 for the owner)
applied (§6).** Date: 2026-10-30. Design: [`agent-ws-design.md`](agent-ws-design.md)
(WS-D) rev. 2: W1–W4, tests and acceptance (§5). Base: `design/ws` (WS-D, PR #137), stacked; `main @ f267641`
below it.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/board.py` | `_since` returns `then` (W1's sentence: the attacker's and the target's squares at the run's first position where they differ from `p`), `where` (W1 and W2: also the squares at `p` where they differ from after the move) and `moved` (the target's colour, type at `p` and square after, when the move moved it). Each piece is named by its type at that position, read from the board there (`_kinds`; review B2). The four since callers pass them: `held` takes `then` only, in brackets. `_scene`: outside a check after the move (`status`, review B1), each kept target gets `_count` — `exposed_v1` as the verifier reads it, with the same `exchange` entry's gain (review N5) — and an `exposed` proposition at the position after, through `_append`'s `also` |
| `agent/remarks.py` | `board_remarks_ko_v6`; `subject()` (colour and type with 이/가); `since_where()`; `since_lost_defence`, `since_exposed` (the tail names "{subject} 옮겨 간 {sq_a}" when the target moved), `since_held` (W1 in brackets before "이 수는 그 공격을 피하지 못했다", review N3); `scene_fate(move, fates, mover)` with each kept target's gain: "(그 칸의 잡고 되잡기만 셈하면 {mover}이 {gain}점을 잃는다)" or "(… 잃는 것이 없다)", "{sq_a}의" for a moved target (review N4) |
| `agent/definitions.py` | `board.since`, `board.scene` statements; `board_remarks_ko_v6` (replacing v5) |

Unchanged, as WS-D §4 says: `board_v4`, `commentary_ko_v8`, `commentary_check_v6`, `TOOLS_VERSION`,
`GUIDANCE_VERSION` (its pinned digest did not move; the registry digest is not pinned).

## 2. Choices

- **Where a since part's squares are compared.** W1 compares the run's first position with `p`, and W2
  compares `p` with the position after the move. So a piece that moved during the run and again with the
  move gets both sentences, each naming the square of its position.
- **The tail's type.** "{subject} 옮겨 간 {sq_a}" names the piece by its type at `p`, the piece that moved:
  "백 폰이 옮겨 간 e8" for a promotion.
- **The check** is read from the `status` record at the position after the move, as `_opponent_first` and
  `weakness` read theirs.

## 3. Tests

- `tests/agent/test_ws.py` (18):
  - W1: since k, with the square written as a token of the item; from the start; nothing when the pieces stood
    where they stand; at least since the bound, with the attacker cycling a8–a7–a6.
  - W2: a weakness whose knight moved into the rook's file; a threat whose queen captured the defender.
  - A `held` item gets no W2.
  - B2: a promoted queen named a pawn on e7, in W2 and in `held`'s bracket.
  - N3: the link remark follows the held attack's clause.
  - The particle.
  - W3: a defended kept target ("잃는 것이 없다", `not_exposed`, gain 0); an exposed one; none after a check
    (B1); a moved target's square (N4); a double attack's two brackets.
  - Every board in these tests has no refused proposition.
- Updated: `test_st.py`'s first scene test (the bracket and its `exposed`); `test_bl_stockfish.py`'s
  judged-move test (§4.5).
- **Mutations:**
  - with the check ignored, the B1 test fails;
  - with each piece named by its type after the move, the B2 test fails.
- Review N1, whole or nothing: a refused part leaves its `also` propositions out (unit), and a fate that does
  not fit leaves the scene item without its count (board).
- Full suite with Stockfish: see §4.4.

## 4. Acceptance (WS-D §5)

### 4.1 Replay

Every ply of the four trial games (271 plies, warm caches), `main @ f267641` (ST) against this branch:
- **Items:** 632 against 632, and nothing lost. Each ST item's propositions appear in order within its WS
  item's; a double attack's `exposed` propositions interleave with its attacks.
- **Size:**

  | Game | Largest digest, ST → WS (characters) |
  | --- | ---: |
  | hung | 9,206 → 9,666 |
  | rapid | 8,384 → 8,384 |
  | fresh | 7,234 → 7,234 |
  | fourth | 7,277 → 7,559 |

  The bound is 16,000. No bound step ran and no proposition was refused.
- **Item text:** the largest `proves` is 285 characters (`ITEM_CAP` 480). No since part, fate or link remark
  was dropped for size.
- **Texts:**
  - **Since sentences:** 11 items gain W1 or W2. They are 6 `lost_defence`, 3 `threat` and 2 `weakness`, as
    WS-D §0 counts. W2 appears at hung 62 (the queen captured from d4) and fourth 37 (the knight from f5 to h6).
    Examples:
    - hung 9: "2...Qxd5 뒤에는 흑 퀸이 d5에 있었다";
    - rapid 39: "11...Nf6 뒤에는 백 폰이 d4에 있었다";
    - fourth 37: "이 수 전에는 백 나이트가 f5에 있었다. 19.Nh6+로 바뀐 것은 공격이 아니라 백 나이트가 옮겨 간
      h6의 잡고 되잡기 셈이다".
  - **The scene:** of the 114 kept targets on 94 items, 83 read "잃는 것이 없다" and 20 read a loss. The 11
    after a check get no bracket. Rapid 40 now reads "흑 나이트(f5)은 백 퀸(f4)의 공격을 계속 받는다(그 칸의
    잡고 되잡기만 셈하면 잃는 것이 없다)".

### 4.2 Re-verification

Every position proposition stored by the trials' runs re-verifies on this branch, 0 refused:
- 1,248 from the earlier trials: FR rev. 3's 852 and ST's 396;
- 393 from this packet's own runs.

The output is in the scratchpad's `fr3/acc/reverify-ws.out` (review N2).

### 4.3 Tool time

`ply` at every ply of the four games, warm caches, on an otherwise idle machine, with ST and WS alternated
over two rounds: ST 309.0 s and 309.4 s, WS 309.4 s and 308.4 s. The two are the same within noise. The
replay of §4.1 ran beside the trial and a full suite; its times are not used.

### 4.4 Suite

The full suite runs with Stockfish and `PYTHONPATH=src`. The worktree's `.venv` links to `main`'s, whose
editable install points at `main`'s `src`. Without that variable, a worktree's tests run `main`'s code.

- **Void run.** An early run of the agent tests, without `PYTHONPATH=src`, passed against `main`'s code. It
  is not counted.
- **`main @ f267641`** passes 1885 with Stockfish (29.8 min). That run also checked ST against the same
  doubt.
- **This branch at `be6ce4b`:** 1 failed, 1900 passed (24.3 min). The failure is
  `test_bl_stockfish.py::test_the_items_cite_by_handle_and_a_judged_move_reads_the_same` (§4.5).
- **After the review's corrections** (the test updated, two new tests): **1903 passed** (25.3 min).

### 4.5 `judge_move` near the bound

The suite's failure is a real effect, found here and not in WS-D:
- **Why `judge_move` is larger.** It writes every position as `{"from_root": [...]}`, the whole path to it.
  At 34...Qb3 (ply 68), the board's changes are 3,024 characters in `ply` and 8,467 in `judge_move`. On `main`
  that answer is already 15,345 characters in the test's session, and 15,412 in the replay below with warm
  caches (compact JSON), against the 16,000 bound.
- **What WS adds.** WS's propositions (one `exposed` per kept target, and the W1/W2 text) bring it over the
  bound. Step 0 then cuts one item, the pin threat.

`judge_move` of the played move at every ply of the four games (same warm caches):

| | ST (`main`) | WS |
| --- | ---: | ---: |
| Answers where step 0 ran | 1 (hung 62) | 4 (hung 61, 62, 68; fourth 67) |
| Board items cut | 4 | 7 (of about 628) |
| Largest answer (characters) | 15,818 | 15,742 |
| Refused | 0 | 0 |

The bound works as designed: each cut is reported in `not_shown.counts.board`, and the items are cut in
`BOARD_KEEP`'s order. The test now asserts the same items and handles less what step 0 reports (at most one
here), instead of equal lists. The cause, positions written from the root, predates this packet. A later
packet could write a position on the game path as `{"ply": k, "at": …}` in `judge_move` too, which would
roughly halve these answers. It is recorded for the owner (§5).

### 4.6 Short trial

**Setup.**
- ST's eight luna runs again, on a scratch copy of this branch (`w-<game>-<n>`): HIMARI v3, the same prompt,
  games and warm analyses.
- The 24 fixed-moment commentaries of each arm went into one blind set, shuffled. Two fresh judges scored it
  independently, with the same reference sheet as ST's judge.

**Results:**

| | ST, judge A | WS, judge A | ST, judge B | WS, judge B |
| --- | ---: | ---: | ---: | ---: |
| Sentences | 126 | 117 | 126 | 117 |
| Wrong | 2 (1.6 / 100) | 3 (2.6 / 100) | 1 (0.8 / 100) | 2 (1.7 / 100) |
| Old attack read as new | 0 | 2 | 0 | 2 |
| Doubtful | 8 | 7 | 7 | 8 |
| Score (1–5) | 3.46 | 3.42 | 3.54 | 3.42 |

**Against WS-D §5's criteria:**
1. **Wrong per 100 not above ST's: not met.** WS has one sentence more than ST under each judge. The wrong
   sentences are B031 (judge A only) and B033 on the engine line, and B047 on accepted/declined. None is about
   a text this packet changed. ST's B035 (the c5 pawn "lost") is the pawn whose `lost_defence` gives 1 defender
   and 1 attacker; WS-D §6 left it out of scope.
2. **"Old attack read as new" stays 0: not met.** Both judges flag the same two WS sentences:
   - **B042, rapid 52:** "흑 룩이 f8을 떠나면서 … 백 비숍 d5의 공격을 받는 상태가 됐습니다". The item on f7
     (`lost_defence`, "이 수 전에도 있었다(24.Bxd5 뒤부터)") is unchanged by this packet. This is the error ST
     brought to 0 in its own trial.
   - **B004, fourth 38:** "킹이 g8을 떠나면서 … d7 나이트도 백 퀸의 공격을 받게 됩니다". The scene says the queen
     began the attack with 19.Nh6+. This packet adds "(그 칸의 잡고 되잡기만 셈하면 흑이 3점을 잃는다)" after
     19...Kh8, which is true: before the move Black was in check and the count was not defined. The new count
     may have drawn the reading toward 19...Kh8. This is B010's moment, which WS-D §6 leaves out.
3. **No sentence reads a kept, defended target as lost or as the danger at rapid 40: met.** WS's two rapid 40
   commentaries say the queen attacked c7 and f5, and neither calls the knight the danger. Neither judge flagged
   ST's two either, though ST's judge had flagged them on 2026-10-29.

**Reading.**
- Two judges agree within one sentence an arm. ST's same 24 commentaries were judged differently by ST's
  judge and by these two (rapid 40). One or two sentences in about 120 is within the judges' spread and eight
  runs' spread.
- The trial does not show WS better, and it shows no error caused by its new sentences, except possibly B004.
- WS-D §5 said this trial is "a check that nothing got worse … not a measurement". By its own numbers it is not
  met, which is the owner's call (as PW's criterion 1, accepted unmet).

## 5. For the owner

- **Trial criteria 1 and 2 are not met.** By one wrong sentence, and by two "old attack read as new"
  sentences, under each of two judges (§4.6). The targeted reading at rapid 40 is gone. The WS sentences
  flagged are on lines or on items this packet did not change, except possibly B004.
- **`judge_move` is near the bound** (§4.5). WS adds 3 answers in 271 where step 0 cuts one item. A follow-up
  could write game-path positions compactly.
- **A cautious option (review N5).** A follow-up could leave out W3's bracket when the position before the move
  was in check (B004's and B010's moment). The text is true as it is.

## 6. Review dispositions — rev. 1 (`be6ce4b`), independent review: READY_WITH_CORRECTIONS

| Finding | Disposition |
| --- | --- |
| N1 no test of whole-or-nothing for `also` (WS-D §5 test 5) | Applied: two tests; each fails with `also` kept after a refused part |
| N2 §4.2's evidence not saved; this packet's own runs not counted | Applied (§4.2): `reverify-ws.out`, with this packet's 393 |
| N3 15,345 against the replay's 15,412; section order; "the first run" twice; suite not re-run | Applied (§4.4, §4.5): both numbers named; renumbered; the runs named; 1903 passed |
| N4 the judged-move test could catch a silent cut | Applied: `(cut > 0) == ("board" in steps)` |
| N5 trial criteria 1, 2 unmet; a cautious follow-up could leave out the bracket after a move made out of check (B004, B010's moment) | For the owner (§5) |
