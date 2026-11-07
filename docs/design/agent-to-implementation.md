# Agent TO — tool outputs: brief views, `compare_lines`, a compact overview

Status: rev. 3; independent review NOT_READY (F1–F3) applied; re-review NOT_READY (N1) applied (§9);
merged by the owner (PR #149, 2026-11-07).
Implements `agent-to-design.md` rev. 3 (READY_FOR_MERGE,
PR #148). The design's §6.1 (the replay) is done here; §6.2 (the pilot) and §6.3 (the blind batch)
run after this review (§6).

## 1. What changed

| File | Change |
| --- | --- |
| `src/calliope/agent/brief.py` (new) | The brief views (TO-D §2): `kept_squares` (rules 1–8 and A1's 9–10), `brief_pieces` (compact entries, A2; the omitted pieces named), `brief_exchange` (the exposed pieces), `brief_status` (A3), `brief_families`. Pure functions over the projected records; they never change them. |
| `src/calliope/agent/session.py` | `facts(…, view="brief")` and `explore(…, view="brief")`: the handle keeps the full record, the answer carries the brief view; `_brief` reads `exchange` and `status` when the call did not ask for them. `compare_lines(game, ply, length=16)` and `_compared_line` (§3: the record's whole PV, one search a line, the extension without a search, `x` and `s` refs, partial answers); `_extension`, `_forcing`, `_numbered_best`. `game_overview`: a `names` table, `label` only when set (§4). `compare` (the board's same reply) keeps the full answer. |
| `src/calliope/agent/server.py` | `view` on `facts` and `explore`, the tool `compare_lines`, their descriptions. |
| `src/calliope/agent/definitions.py` | `agent_tools_v7`, `agent_guidance_v12`; the `tools` entry names TO's additions and fields (§5). |
| `tests/agent/test_to.py` (new) | 18 tests (§3). |
| `tests/agent/test_{session,game_path,server,commentary,guidance}.py` | The identity test reads `view: "full"`; the overview's names; the tool list; the two versions and v12's guidance digest. |

## 2. Departures and amendments

- **A1 — two keep rules more (§2.1).** The replay (§4) found rules 1–8 lost 10 of 88 key-cause
  squares and 65 of 303 squares the agents had cited. The misses were relations the rules do not
  see from counts: a sacrifice on a pawn defended three times (rapid-52, 27.Bxf7+ and mate), a pawn
  the queen takes later in a line (185371835722 plies 31–32, …Qxb2), a pawn capture between equal
  pieces (fresh-56, …fxg4). Added: **9**, every piece attacked, pinned or attacking an enemy piece;
  **10**, the defenders of every kept piece. Three rule sets were replayed on the same positions:

  | Rules | `pieces` median (characters) | Key-cause squares in play, before and after the move (filtered as rule 9; review F1, §4) | Cited squares |
  | --- | --- | --- | --- |
  | 1–8 (the design) | 1,670 | 78 / 88 | 238 / 303 |
  | 1–9 | 2,514 | 88 / 88 | 292 / 303 |
  | **1–10 (kept)** | 2,824 | **88 / 88** | **302 / 303** |
  | the full record | 10,187 | — | — |

- **A2 — compact entries (§2.1's fields).** With A1 the brief `explore` was 9,677 characters at the
  median, over §6's 8,000. An entry now names the piece (`"Rd4"`, upper case White, lower case
  Black), its attackers, defenders and the enemy pieces it attacks by name (`"nf5"`, `"Nc3
  pinned"` for an absolutely pinned one), `origin` when it is not the piece's square, and only the
  flags that are true; `attacker_count`, `defender_count` and `lowest_attacker_types` follow from
  the lists and are left out, as is a `legally_capturable_now` that is a sentinel. The answer says
  so (`entries`).
- **A3 — `status` in brief (§2.2 said "as today").** `legal_moves` is the count ("30 (view
  \"full\" lists them)"); the full record lists them. No accepted submission of the RX records cited
  a `legal_moves` proposition; the proposition is checked against the facts tree as before.
- **`best_move`** in `compare_lines` is numbered as `move` is (`23.dxe5`), as the design's example.
- **`searched`** is the line's own `x` when the line was not extended.

## 3. Tests

`tests/agent/test_to.py`, 18 tests: the 1-against-1 exchange that loses (rules 1–3, B3) and the
compact entry; pins, a fork, a check and the last move; the brief exchange; `facts` brief against
full on the exposed knight of 3...h6 (32 pieces: kept and omitted add up; the handle keeps all);
`explore` brief against full (one handle, the same plies; a `material` proposition from it
verifies); a `defence` proposition about two omitted pieces verifies; `compare_lines` — the record's
whole PV (B1), material cited from `x` and the score from `s`, the score from the `x` refused (C1),
`root`'s `s` refs (N2), the game's continuation; one search a line and no second search; the
arguments (0, 33, "16", `true` refused before any work; 1 and 32 answer; C3); an uncached ply
analysed, `cached` false then true (C2); the extension (`_extension` on a capture, a quiet stop,
`length`); a line ending in mate answers its status; a budget that admits no search answers lines
without scores (B2); numbered moves. Review F2: `status` alone is brief, the same as with `pieces`.
Review F3, through `submit_commentary`: a commentary of ply 4 citing the played line's material by its
`x`, its end score by its `score_ref` and the root's score by its `s` is accepted
(SOURCE_VERIFIED); the same with the end score cited by the `x` is refused. Re-review N1: on the
fact engine's own record (1.e4 e5 2.d4 Bb4+ 3.c3), the pinned c3 pawn is kept and its entry names
the pinner (`{"pinner": "bb4"}`); the hand-made records carry a `Pin` as the engine projects it.

The agent tests: 584 passed before A1–A3; the whole suite on the final code: §7.

## 4. The replay (TO-D §6.1)

`rx-evidence/to/replay_to.py` on copies of the RX bases (WSL; node limits raised so a replay of
every call fits; no model, no searches — the search part of `explore` is unchanged):

| | Calls | Full, median | Brief, median | Brief, p90 | Brief / full |
| --- | --- | --- | --- | --- | --- |
| `explore` | 111 | 23,286 | **5,444** | 7,465 | 0.27 |
| `facts` | 49 | 18,002 | **5,755** | 9,127 | 0.27 |

One recorded `explore` call raises an error in the replay and is left out of the sizes.

- **Key causes (review F1).** rev. 1 counted only the pieces in play (attacked, pinned or
  attacking) before and after the move: the filter is rule 9 itself, so its 88 of 88 proved
  nothing. rev. 2 counts **every piece on a square a key cause names, with no filter**, at every
  position: before and after the move, along the subject's played and best engine lines (the
  record's whole PV, ply by ply) and along each `on_request` cause's resolved line. **858 of 1,043
  kept.** Each of the 185 left out was read from its full record: **none is attacked, attacks an
  enemy piece or is pinned**, and **every one is named in the answer's `omitted` list** — what the
  brief view drops for them is their defences of pieces nothing attacks, their moves and their
  origin. 180 are on the engine lines, where a named piece stands idle for some plies; the five at
  the moment itself were read against their causes: the c4 pawn of hung-14 and the a1 rook of
  23.Rxe5 are attacked only later in the line the cause gives (…Qxc4, …Qc3), where they are kept;
  the f7 rook of 185922072242-138 is the piece that moves (to f6, kept). No relation a key cause
  states was dropped.
- **Pins (re-review N1).** At every position the key-cause check walks, every piece the full
  record shows absolutely pinned: **187 of 187** in the brief view with their pinner named.
- **Board items (review F1).** Every proposition of the digests' board items (`changes`, `scene`,
  `same_reply`) at its position: **315 of 315 squares kept**.
- **Cited:** every square of the 303 `attack`, `defence`, `pin`, `exposed` and `check` propositions
  accepted in the RX runs, at its position: **302 kept**. The one left out: 185264271324 before ply
  33, a `defence` by the piece on f1 of a piece nothing attacks (rule 10 keeps the defenders of kept
  pieces only); the agent reads it with `view: "full"` or `detail`.

`rx-evidence/to/replay.json` holds the numbers; `variants_to.py` the comparison of A1.

## 5. `compare_lines` on the 24 fixed moments

`rx-evidence/to/compare-lines-24.txt` (`compare_to.py`): answers of **1,721–2,255 characters**
(median 2,092); 0–3 searches a call (a line that ends the game has none); 19 of 70 lines extended
by 1–5 plies. 23.Rxe5 (185264271324 ply 45):

- `played`: 23.Rxe5 Rxe5 24.dxe5 Qxe5 25.Nxc4 Qxc3 — material [3, −2, 3, 2, 3, 2], as the
  key-cause sheet; extended by 26.Bb2 Qxc4 27.Qg5 Qf7 (the knight lost: −1), `end_score` +2.59 at
  ply 6 (`score_ref` the search there).
- `best`: the record's 13 plies (the digest shows 8) and one more, ending +1; `end_score` +2.88 at
  ply 13.
- `game`: 16 plies of the game, [3, −2, 3, 2, 2, −1, 0, −1, 2, −3, …], the a1 rook lost at 27...Qxa1.
- `root`: +0.08 and +4.56 with the analysis record's `s` refs.

## 6. Still to run

TO-D §6.2 (two games, the plain loop and the staged harness, two runs each, on v7) and §6.3
(Validation, three runs a game, the plain loop on v7 judged in one judging with `trial-haiku-1`,
non-inferiority M2b ≥ −0.10, M1b ≤ +2.0 per 100, cost at least 30% lower). Expected cost on
OpenRouter: about $1 and $2.

## 7. The whole suite

WSL, rev. 3's code: **1931 passed, 27 skipped**; 3 failed and 2 errors, all known: the digest golden
on the Windows engine build, and the four `zstd` tests (two failures, two errors; RX1 §3). (rev. 2's
run: 1929 passed, with `test_digest.py`'s `detail` test failing on F2's brief `status`, then fixed;
rev. 1's: 1926 passed, with `brief.py`'s own table of piece values failing, then fixed.)

## 8. Questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Accept A1–A3 (two keep rules more, compact entries, legal moves counted)? | Yes: the replay is the check the design set, and all three pass it. |
| Q2 | Run §6.2 and §6.3 after this review, or now? | After the review: the batch's judging pairs v7 with `trial-haiku-1`, and a change from the review would mean running it again. |

## 9. Review (rev. 1 → rev. 2)

Independent review of `e8fce0a`: NOT_READY.

| # | Finding | Disposition |
| --- | --- | --- |
| F1 (P1) | The replay checked key causes only before and after the move, through the filter rule 9 is made of, and not the board items | Applied (§4): every piece on a named square, unfiltered, at every position of the subject's engine lines and of the resolved requests: 858 of 1,043, each of the 185 left out read (none attacked, attacking or pinned; all named in `omitted`); board items 315 of 315. The A1 table says what its count was filtered by. |
| F2 (P2) | `status` alone was not brief, with `pieces` it was | Applied: `_brief` applies `brief_status` whenever `status` is there, and reads `exchange` and `status` only for `pieces`; a test compares the two calls. |
| F3 (P2) | No test through `submit_commentary` | Applied: a commentary citing `compare_lines`' `x` (material) and `s` (end and root scores) is accepted; the end score by the `x` is refused. |

Re-review of `f1243f5`: NOT_READY (F1–F3 resolved).

| # | Finding | Disposition |
| --- | --- | --- |
| N1 (P2) | A piece's `absolutely_pinned` is the fact engine's `Pin | None` (a dict when projected), so `is True` never held: rules 5 and 9 did not keep a piece for its pin, and the entry dropped the pin | Applied: `_pinner` reads the `Pin`'s `pinner`; rules 5 and 9 keep a pinned piece; its entry says `absolutely_pinned: {"pinner": "bb4"}`. An attacker's or defender's `absolutely_pinned` is a bool (`geometry.Relation`) and its `"pinned"` mark was right. A test on the engine's own pin; the replay counts pins (187 of 187 shown with their pinner) and its classification of the 185 left-out pieces reads the `Pin` (none pinned). |

## 10. The measurement (TO-D §6.2, §6.3), after the merge

**Runs.** Validation, arm A, the runner's defaults on v7 (Haiku, cache marks, `session_id`), three
runs a game (`batch-to-validation-1*.jsonl`): 16 started, 11 judged. Left out: two runs of
184800218248 whose first `game_overview` gave no answer in 600 s (`tool timeout`), with three staged
runs and two other batch runs at once; one rerun of it whose model request gave no answer twice in
120 s; and three runs of 185922072242 (the first and two reruns) whose provider answer was cut short
(`IncompleteRead`, the runner does not retry it). 185922072242 is judged on two runs. Two runs that
ended at the token bound saved all three moments and are judged, as in MH. The plain loop's pilot
(§6.2) is this batch's runs on 185264271324 and 184800218248.

**Judging `8341bd37`.** The 11 v7 runs and `trial-haiku-1`'s 12 (v6), 69 commentaries in two
parts, `judge_v1`, fresh sessions; both audits passed. Report (`validation-report.json`, `--pair A
A:haiku`, v7 − v6 paired by moment, 90%):

| Bound (TO-D §6) | v6 | v7 | v7 − v6 | Met |
| --- | --- | --- | --- | --- |
| M2b decisive explained, lower bound ≥ −0.10 | 0.750 | 0.727 | 0.000 (−0.056 … +0.056) | yes |
| M1b wrong per 100, upper bound ≤ +2.0 | 2.30 | 3.66 | +1.17 (−1.41 … +3.96) | **no** |
| Cost a run, at least 30% lower | $0.142 | $0.126 | −11% | **no** |
| M4 score | 4.19 | 4.03 | −0.11 (−0.29 … +0.06) | — |
| Decisive `on_request` evidence fetched | 0 of 6 | 1 of 6 | | — |
| Moment-runs without commentary | 0 | 0 | | — |

**What the plain loop did with the new tools.** Across the 11 runs: `explore` 0 calls, `facts` 2,
`compare_lines` 2 (`ply` 138, `submit_commentary` 96). The brief views barely reach this arm; its
cost is `ply`'s and the conversation's, which TO did not change, and the 11% is about the overview's
names and run-to-run spread. The seven wrong v7 sentences are misread defences and attacks (an e3
pawn's defender, a king leaving g7, a pawn "kept" by a rook move); three of them, at 185371835722
plies 30–32, came from three runs of which two called neither `facts` nor `explore` — they come
from the digest's board items, which TO did not change. One (ply 31) came from the run that called
`facts` twice. The same misreading at 185922072242 ply 140 is in both arms.

**The staged harness (§6.2),** where the tools are used: the same two games, two runs each
(`pilot-staged-v7.jsonl`, `staged.py`), against the MH pilot's staged runs on v6:

| Staged harness | v6 | v7 |
| --- | --- | --- |
| Cost a run, mean | $0.375 | **$0.137 (−63%)** |
| Prompt tokens a request, mean | 81k–154k | 56k–90k |
| Requests over 100,000 tokens a run | 10–26 | 0–17 |
| `compare_lines` called | — | in 3 of 4 runs |

At 23.Rxe5 one v7 staged run comes nearer the key cause than any run before ("the same knight taken
by 23.dxe5 keeps the gain without the rook exchange"); neither reaches the lines' ends.

**Read.** On the plain loop, v7 is no worse on decisive causes (the interval within ±0.06) and the
wrong-sentence bound is missed by an interval that also holds zero; the cost bound cannot be met by
an arm that does not call the trimmed tools. The cost TO was made for is the staged harness's,
where it fell by 63%.

| # | Question | Recommendation |
| --- | --- | --- |
| Q3 | Keep v7 (merged) on this result? | Yes: M2b non-inferior; M1b's miss is an interval over zero, with errors from the unchanged digest; the cost fell where the tools are used. Measure the staged harness blind in its own packet (TO-D §8). |
| Q4 | The runner's retries | A follow-up: retry a cut-short provider answer (`IncompleteRead`) as a timeout is retried; look at `game_overview` waiting 600 s under load. |
