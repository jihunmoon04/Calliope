# Agent LT — line tools v8, harness rev. 5, variants and the Test set

Status: rev. 3; independent review NOT_READY (F1, F2; F3, F4) applied; re-review READY_FOR_MERGE
(N1 applied) (§7, §8). Implements `agent-lt-design.md` rev. 3 (merged, PR #155).
The replay, the pilot and the measurement of LT-D §6.2 run after this review (§6).

## 1. What changed

| Part | What | Where |
| --- | --- | --- |
| T1 | `explore` answers a `ledger`: each ply numbered with `says` (who moved what, what it took from whom, check, mate, promotion, castling), `side` and `source`, `captured` (with the victim's own square, so en passant is right); `captured` by each side; `net` per side and for the first mover (equal to the end's `material_balance_white`); `end` (`moved_pieces`, `gone`, `status`); with `search`, `end_score` (White's view, the side to move's view, `favours`, `score_ref`, `end_score_at`). The `x` record holds it. `continue_with: "engine"` (with `search`) plays the end search's PV on, up to `length` (1–16, default 8), with no second search; those plies are `source: "engine"`. A line that ends the game answers `search: {"terminal": status}` and a terminal `end_score` instead of an error, with no search admitted or charged (re-review R1). | `src/calliope/agent/lines.py` (new: `ledger`, `end_score`, `terminal_score`), `session.explore` |
| T2 | `compare_lines(…, candidates)`: 1–4 moves, each legal at the position before the ply, checked before any search; each candidate's line is the candidate and the PV of one search after it, played to `length` with its ledger outcome; every line (best, played, game) carries its ledger outcome. `ranking`: played, best and candidates, each scored by one search after the move on the session's profile, in the mover's view (`for_mover`), with `white_view`, `depth`, `score_ref`; a move that ends the game ranked from the board (`terminal`, `fen_after`, `source: "board"`), never searched; LT-D §3's order; `vs_played` (a text when a mate or checkmate is involved); `close` within ±0.30; a budget refusal `unranked`. The answer is served under a `k` handle (`comparison`), read by `detail`, never citable. `root` is never ranked. | `lines.py` (`for_side`, `rank_key`, `ranking`, `vs_played`), `session.compare_lines`, `_rank`, `_scored`, `_candidate_moves`; `handles.KINDS` |
| T3 | `squares(game, position, squares)`: 1–8 squares; an occupied square's attackers and defenders from its piece's full `pieces` record, its `exchange` entry; an empty square's attackers by side, by reverse lookup of every piece's `attacks.empty` (re-review R2); pinned pieces included and marked with their pinner; attackers with `can_move_there` (the square in the piece's `legal_destinations`); at `{"ply": n, "at": "after"}`, `changed_by_move` by piece identity. The `pieces` and `exchange` records are served under `f` handles (`refs`). | `lines.py` (`square_entry`, `changed_by_move`), `session.squares`, `server.squares` |
| — | `agent_tools_v8`, `agent_guidance_v13` (the descriptions of `explore`, `compare_lines` and `squares`; the registry's tools entry and its fields); the pin `9da0dbc1…`. | `definitions.py`, `server.py`, `test_guidance.py` |
| H1 | `harness_v3.md`'s facts message asks for the claims block (six kinds, as LT-D §5.1, and `attackers` beside `defenders`). | `tools/rx/prompts/harness_v3.md`, `harness.claims_of` |
| H2 | The checker: each claim's record read through the server's `detail` as the harness's own call (`harness_call` line), and checked by code (`check_claim`): `agrees`, `disagrees` with the record's value, or `unbacked`. Problems go back with the `check` message (H4) and share the two retries; no judge request then. A reply without a block goes back. The checker never reads the prose. | `harness.check_claim`, `check_claims`, `read_record` |
| H3 | Rubric v3 (`harness_judge_v2.md`): failures 5 (against the claims) and 6 (coverage); the judge's input is the reply and the checked claims with their records' summaries, at most 2,500 characters. | `harness.judge_input`, `judge(system, content)` |
| H4 | `harness_v3.md`'s `check` message: call the tool again, correct from the record, cite it. | prompts |
| H5 | The sentence check at submission: a call that passes the gate is read first (`harness_sentences_v1.md`, the run's model) against the checked claims; `contradicts` or `unbacked` holds it (`tool_unsent`, `reason: "sentence_check"`) with the reasons; at most two holds, then the call goes unchecked; an unreadable check sends it. The sentences are read after `normalized` (JSON-string `items`). Each moment's state (`passed`, `unreadable`, `exhausted`, `not_run`) is logged (`sentence_state`), its usage counted with the judge's. | `harness.Gate._sentences`, `sentences_of`, `check_sentences` |
| — | `HARNESS_VERSION` `harness_v3`, `JUDGE_VERSION` `harness_judge_v2`, `harness_sentences_v1` on the `start` line; rev. 4 (`harness_v2`, `harness_judge_v1`) kept and selectable. | `harness.VERSIONS`, `RunSpec.harness_revision`, `--harness-revision` |
| §6.3 | Variants: `run --tools v7|v8`; `batch --arms A@v7 A@v8 H@v8` (rows carry `variant`); `report.label` reads `variant`. v7's server starts from `RX_DATA/servers/agent-tools-v7` (`cwd` and `PYTHONPATH` there). The `start` line carries `variant` and `server` (root, commit, expected tools); a `server` line after `initialize` carries the version the server reports, and a mismatch ends the run as `error`. | `run.py` (`server_root`, `_server_info`, `_run`), `batch.py` (`split_variant`), `report.py` (`label`) |
| §6.4 | The Test set: `open-test --freeze <record>` analyses Test, chooses its moments as Validation's, seals its base and records the freeze's digest — refused without a freeze record or once open; `run`, `batch`, `annotate`, `reference`, `requests` take `test`, the last three only once Test is open. The report pairs over every set held; `train` and `validation` pool as before; a Test-only report decides from `<a> − <b> / test` (`read_from: "test"`); Test beside another set is refused. | `manifest.open_test`, `__main__.py`, `report.pair_up` |
| R3 | The report's arm entries for H rev. 5: `sentence_check`, moment-runs and M1b per state. | `report.sentence_states`, `by_state` |
| — | The run checker pairs the harness's `detail` calls with the server's lines (`asked_calls`); the metrics leave them out (`harness_call_ids`), so M3 and P1 count the agent's calls only. | `check.py`, `metrics.py` |

## 2. Amendments

| # | Amendment | Why |
| --- | --- | --- |
| A1 | `explore`'s parameter is **`continue_with`**, not `continue`. | `continue` is a Python keyword: the tool's signature (and its JSON schema) cannot name it. |
| A2 | The tools version the server reports is written on a **`server` line** after `initialize`, not on the `start` line. The `start` line holds the variant, the root, its commit and the expected version. | The `start` line is written before the server starts; the version is known only from its `initialize` answer (`serverInfo.version` = `TOOLS_VERSION`). |
| A3 | `defenders`/`attackers` claims compare piece names **case aside**. | The role fixes the colour, and the guide's notation writes a black king `Kg8`; the tools write it `kg8`. |
| A4 | The harness's `detail` calls are logged as **`harness_call`** lines; the run checker and the metrics pair them with the server's `call` lines in order. | LT-D §5.2 said "not counted as the agent's tool call"; the server's recorder writes every call, and the checker matches calls one for one. |
| A5 | **Harness rev. 4 stays selectable** (`harness_revision`, default 5). | HS rev. 4's runs (§8, §10 of HS) stay reproducible; the HS tests keep testing rev. 4. |
| A6 | **The measurement order** (owner, 2026-11-08, cost): on Test, `A@v7` and `H@v8` first; `A@v8` only when the tools' share needs splitting from the harness's. The development pilot runs **one run a game**. | Cost: the third variant is a third of the Test batch (about $1.5); the adoption reads `H@v8 − A@v7` alone. |
| A7 | `changed_by_move` is given **per role** (`attackers`, `defenders`, each `lost`, `gained`, `kept`); a square whose occupant changed colour or became empty says so (`occupant_changed`, `empty`) instead of lists. | LT-D §4's example put roles in the names; per role is what the checker and the agent read. |
| A8 | The `k` handle is served **only with `candidates`**. | Without candidates there is no ranking; `compare_lines` answers as v7 did. |
| A9 | A candidate line's end score is the **ranking search after the candidate** (`end_score_at: 1`); no second search at the line's end. | One search a candidate (LT-D §3's bound); the line's later moves are that search's PV. |

## 3. Tests

- `tests/agent/test_lt.py` (18, rev. 2: F4): the ledger on a trade (captured by each side, `net` equal to the
  balance, `gone`, `moved_pieces`, the `x` record holding it), en passant's square, castling, a
  promotion on records made by hand; a mating line answering its terminal status with no search
  charged; `continue_with` playing the stored search's PV with no further search, and its argument
  checks; scores for the mover and `favours` at the band's edges; the ranking order (checkmate, a
  mate for, centipawns and a stalemate at 0.00, a mate against; `vs_played` as numbers and texts;
  `close`; `unranked`); a mating candidate ranked first from the board, with its FEN in the `k`
  record; every ranked score from a search after the move, `root` not ranked, the lines' ledger
  outcomes; candidates checked before any search; a `k` handle refused as a proposition source;
  `squares` (all attackers and defenders, `changed_by_move`, an empty square by reverse lookup, a
  pinned attacker marked with `can_move_there: false`, argument checks); the f7 case on records made
  by hand (the rook leaves, the king and knight stay).
- `tests/agent/test_lt_harness.py` (16, rev. 2: F2, F3): every claim kind agreeing; the §0.2 cases disagreeing or
  unbacked, the record's value returned; the block read fenced or not; the loop — checked claims in
  the judge's and the sentence check's inputs, the `harness_call` line, no tool message for it; a
  disagreeing claim sent back before any judge request; a reply without a block; a contradicting
  sentence held then corrected (`passed`, one hold); two holds then unchecked (`exhausted`); an
  unreadable check (`unreadable`); JSON-string `items`; the run checker pairing a harness call; the
  metrics' pairing helper.
- `tests/agent/test_lt_runner.py` (14, rev. 2: F1; rev. 3: N1): variants (`split_variant`, jobs and `--tools`, labels, the
  server root and the `start` line's `server`); a Test-only report deciding from its Test entry;
  Train and Validation still pooled; a report holding Test beside Train refused; `open-test`
  refused without a freeze record; M1b per sentence-check state.
- Updated: `test_session` (a finished position answers its terminal status, still free),
  `test_server` (the `squares` tool), `test_commentary` (`agent_tools_v8`), `test_guidance` (v13 and
  its pin), `test_hs` (rev. 4 named, and rev. 5's versions on the `start` line).

## 4. The whole suite

WSL, at `b86aa1f`: **1994 passed, 27 skipped**; 3 failed and 2 errors, all known (the digest golden
on the Windows engine build; the four `zstd` tests of `test_calibrate_curve`). The last commit (the
metrics' pairing, `be2e842`) was run after it with `test_lt_harness.py` and `tests/tools`: all pass
but the same `zstd` four. `ruff check` and `ruff format --check` clean.

Rev. 2 (§7): `tests/agent`, `test_definitions` and `test_package_boundaries` — **688 passed**, the
digest golden the one failure (known); `ruff` clean. The rev. 2 changes touch `tools/rx`,
`lines.py` and two tool descriptions only.

## 5. Before the measurement

1. **Tag** `agent-tools-v7` at main before this packet merges (`029d649`, LT-D §7 Q6), and make the
   worktree `RX_DATA/servers/agent-tools-v7` from it.
2. **Replay** (LT-D §6.2 step 1, no model): Train's 13 tool-shaped cases of LT-D §0.2 put to T1–T3,
   case by case; then Validation's 9 as the check.
3. **Pilot** (A6): the development sample, `H@v8`, one run a game: the claims blocks, the checker's
   verdicts, the holds, cost.
4. **Freeze**, then `open-test`, the references and the key causes for the owner's review (RX0-D
   §2), then the blind batch (A6's order).

## 6. Not in this packet

- The 100k-prompt cost work (one conversation a moment, or the tool answers of submitted moments
  shortened): its own small packet after this one (owner, 2026-11-08).

## 7. Review (rev. 1 → rev. 2)

Independent review of rev. 1 (PR #156, HEAD `6e37ccb`): **NOT_READY**, two blocking findings and two
others, all applied.

| # | Finding | Applied |
| --- | --- | --- |
| F1 (P1) | `open-test` raises `KeyError` on every input: `build_base` chose moments for `validation` only, so `done["moments"]` was empty for Test — after every ply had been analysed. | `build_base` chooses moments for `validation` and `test`. `open_test` checks every game's moments before writing anything and stops, unsealed and unrecorded, when `rx_moments` refuses a game. Tests: Test's games analysed (the synthetic engine), moments and slots written, the base sealed, the freeze's digest kept, a second opening refused; a game without moments stops before sealing. |
| F2 (P1) | A partial sentence check (one row for three sentences) passed: the answer was read without checking it judged every sentence, so unchecked sentences reached the server as `passed`. | `_parse_sentences` takes the sentence count: the rows must number 1..N, each once, each verdict `ok`, `contradicts` or `unbacked`; anything else is unreadable, asked again once, then `unreadable` (the call sent as such, never `passed`). A call with no sentence needs no request. Tests: partial, duplicated, misnumbered and unknown-verdict answers each asked again and then unreadable; a whole answer on the re-ask read. |
| F3 (P2) | `better_for_mover` agreed from the ranking's places, so of two moves scored the same the first-placed was "better". | The check compares the two moves' `for_mover` scores with the ranking's own order (`rank_key`): strictly better agrees, a tie disagrees, a move unranked or absent is unbacked. Tests: an exact tie, an unranked move. |
| F4 (P2) | `can_move_there` was `false` for the side not to move, whose `legal_destinations` the fact engine does not observe (`not_observed`). | `can_move_there` is `null` unless the record lists the piece's legal destinations; the `squares` note and description say so (the guidance pin moves, `agent_guidance_v13` unmerged). Tests: White's knight after 3.Ng5 with Black to move; a record made by hand with `not_observed`. |

## 8. Re-review (rev. 2 → rev. 3)

Re-review of rev. 2 (HEAD `9dc17dc`): F1–F4 resolved; **READY_FOR_MERGE** with one non-blocking
finding, applied before the merge.

| # | Finding | Applied |
| --- | --- | --- |
| N1 (P2) | `open-test` checked only that the freeze record exists: an empty file or `{}` opened Test, and nothing tied a Test run to what was frozen. | `tools/rx/freeze.py`: the record `freeze_v1` — the model, the repository's commit, the bounds (turns, tool calls, tokens) and each variant (`ARM@TOOLS`) with its tools version, an optional server commit, and for H its harness revision and the messages, judge and sentence-check versions that revision names. `open-test` refuses a record with any problem (`problems`) and keeps its path and digest. Before every Test run, `run` refuses a run that is not the frozen one (`run_problems`): Test not open, the record changed since, the variant not frozen, another model, another bound, another harness revision. Tests: a whole record; `{}`, an empty file and a record with wrong versions refused; a Test run with each mismatch refused. |
