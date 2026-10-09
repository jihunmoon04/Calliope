# Fact engine — packet F4a implementation: engine boundary

Status: **rev. 2 — independent F4a review READY_WITH_CORRECTIONS applied**.
Date: 2026-10-09. Design: [`fact-engine-f4-design.md`](fact-engine-f4-design.md) rev. 3
(F4-D §3–§5, §9.1, §9.3 items 1–4). Base: branch `design/fact-engine-f4` @ `f31f74a` (PR #47).
Review of `22ccd1d`: READY_WITH_CORRECTIONS (F4a-C1–C8, N1–N8); section 5 maps every finding.

## 1. Scope delivered

F4a adds the package `calliope.facts.search`. It makes no tree changes: F4b integrates it into
`open` / `extend`.

| Module | Content |
| --- | --- |
| `search/profile.py` | `EngineProfile` (threads must be 1); `EngineOption`; `EngineIdentity` with fingerprints; `start_options` (`Threads`, `EvalFile`, sent once at start); `search_options` (sent before every search, only those the engine offers); `SUPPORTED_ENGINE = "Stockfish 19"` |
| `search/port.py` | `EnginePort` protocol, `SearchRequest`, `RawSearch`, `RawLine`, `Bound`, `StoppedBy`; `ScriptedEngine` (table or function, counts calls, thread-safe) |
| `search/uci.py` | `StockfishEngine`: raw UCI over a subprocess. It handles the handshake and identity (exact name, sha256 of the resolved binary, every offered option), start options, and the per-search protocol of F4-D §3.3. It keeps the last scored `info` line per rank, refuses rank gaps and excess ranks, sends an adapter `stop` at the cap (`TIME`), and uses 10 s timeouts. An adapter lock covers each whole search |
| `search/inputs.py` | `EngineInput`; `window_input` (copies the start board; legal en passant; fullmove 1); `node_input` (read-only tree access: pre-root moves + path); `window_end` |
| `search/records.py` | `SearchKind`, `ReuseSource`, `Cp`, `Mate`, `Wdl`, `EngineLineFact`, `EngineSearch`, `SearchRuntime`; `normalize` (F4-D §5.2–§5.3); `request_key`, the length-prefixed `SearchId` (§5.4) |
| `search/store.py` | `EngineResultStore` (thread-safe, regular searches only); `Searcher`: one session's access, with store hits, a session cache of committed and pending irregular searches (`commit`, `discard`), and an engine-call count |
| `errors.py`, `values.py` | `EngineError`, `EngineOutputError`, `EngineUnsupportedError`; `Unavailable` / `UNAVAILABLE` (A0 §1) |

## 2. Implementation decisions within the design

1. **Package name.** `calliope.facts.search`, not A0 §11's `engine/`, which would collide with
   the existing `engine.py` (`FactEngine`).
2. **The question key.** `request_key` computes the regular `SearchId` before the engine runs,
   for store lookups. The session's irregular cache uses the same key: an irregular answer is
   reused for the same question, although its own `search_id` includes its lines.
3. **Root moves** are deduplicated and sorted as strings by `Searcher.search` before they reach
   the request, so the preimage and `searchmoves` are canonical.
4. **Option parsing.** An `option` line's name is the tokens between `name` and `type`; its
   default is the tokens after `default`, up to `min` / `max` / `var`. Buttons have no default.
5. **Start check.** An `info string … ERROR` line before `readyok` refuses the start or the
   search.
6. **Strict `info` parsing.**
   - Lines without `score` and `pv` (progress lines) and `info string` lines are skipped.
   - On a scored or PV line, every field must be one Stockfish 19 prints. A repeated field, a
     `pv` without a score, or a score without a `pv` refuses the line.
   - `multipv`, `depth`, `seldepth`, `nodes` and `tbhits` are required, never invented
     (A0 §1).
7. **Duplicate ranks** (F4-D §3.3 item 7). Stockfish legitimately repeats a rank within one
   search (iterations, bound lines, the final print after `stop`), and the adapter keeps the
   last line of each rank. A duplicate in the final set is therefore impossible by
   construction. Two ranks with the same first move are refused by normalization (duplicate
   first moves). Together these cover the design's duplicate-rank refusal.
8. **Order of reuse.** `Searcher.search` consults the session's own answers (pending, then
   committed) **before** the shared store, so one session never holds two results for one
   question (A0 §7.7). A regular answer obtained by the session is stored and returned as the
   store's record (`put` returns the first record if two sessions raced).
9. **Bounds from White's view**: swapped with Black to move, with the score (F4-D §5.2
   clarified).
10. **Root moves** are validated (non-empty, legal at the window end) before any engine call;
    `normalize` re-checks them.
11. **Budget accounting.** `engine_calls` counts committed requests plus the pending one;
    `discard` rolls the pending calls back, so F4b can use it for `max_searches`.
12. **Process trust.** After a `readyok` or post-`stop` `bestmove` timeout, the adapter kills the
    process, and later searches raise `EngineError`. A missing binary raises `EngineError`;
    `close` closes the pipes; a reader decode error ends the stream. The adapter has no switch
    around the exact-name rule, and `command[0]` must be the engine itself, because it is the
    file that is hashed.

## 3. Not in F4a

Tree integration (F4-D §6–§8, F4b), persistence and tape replay (F5).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/search/test_uci_adapter.py` (21 tests) against `tests/facts/search/fake_uci.py`, which offers Stockfish 19's real option list. Covers: last line per rank (no merge); illegal, null, SAN and malformed PV tokens passed on and refused by normalization; scored line without `pv`; rank gap, excess and fewer ranks; missing WDL; wrong name; start error; process death; no `readyok`; no `bestmove` after `stop`; a timed-out process not reused; a missing binary; cap ⇒ `stop` ⇒ `TIME`; `TIME` at full depth irregular; the exact command sequence of two complete searches, one with window moves and every pinned option, with `EvalFile` / `Threads` sent once; missing fields refused; strict parsing; the engine usable after a refused search | pass |
| `tests/facts/search/test_search_records.py` (28 tests). Covers: White-view scores, bounds and WDL with both sides to move; mate 0; `UNAVAILABLE`; WDL sum; rank and line refusals; restriction and k; `TIME` with fewer ranks; regularity; window length and form; pseudo-legal start board unchanged; `node_input` across the root; every `SearchId` preimage field varied independently (input FEN and moves, kind, MultiPV, root moves, each profile field, each identity field, the pinned options alone); stability across processes; irregular ids including lines and stop reason; store hit without engine; session answer before the store; session-only irregular reuse with pending / commit / discard; engine-call rollback; root moves validated before the engine; store returns the first record; thread-safe store; `threads=2` refused | pass |
| `tests/facts/search/test_stockfish_acceptance.py` (5 tests; F4-D §9.3 items 1–4; real Stockfish 19). Covers: identity (name, sha256, one network); fresh-state determinism after unrelated searches and in a new process; en passant form against the engine's own `d`, on 150 FENs (parse path) and 120 double pushes sent as moves (`do_move` path); window equivalence on 3 histories with windows strictly shorter than the history, where a bare FEN differs | pass (skipped without `CALLIOPE_STOCKFISH_PATH`) |
| F1–F3 suites, `tests/test_package_boundaries.py` | pass |
| `ruff check`, `ruff format` | pass |

### Cost

Measured on aarch64 with 2 CPUs: 80 surveys from 8 random games, depth 12, MultiPV 5.

| Measure | Value |
| --- | --- |
| Engine time (`go` to `bestmove`), median | 158 ms |
| Wall time per search, median | 170 ms |
| Wall time per search, max | 815 ms |
| Adapter overhead per search, median (options, `ucinewgame`, Clear Hash, `isready`, parsing, normalization) | 11.8 ms |
| Irregular searches | 0 |

The overhead is consistent with M11: the per-search option group costs about 8 ms. Sending
`EvalFile` per search would have added about 200 ms.

## 5. Review dispositions (independent F4a review of `22ccd1d`: READY_WITH_CORRECTIONS)

| Finding | Disposition |
| --- | --- |
| F4a-C1 bound not converted to White's view | swapped with Black to move; F4-D §5.2 states it; test |
| F4a-C2 store consulted before the session's irregular answer | session first (§2.8); test |
| F4a-C3 irregular id without the stop reason | `stopped_by` in the irregular preimage; test |
| F4a-C4 duplicate-rank refusal undefined | covered by last-line semantics plus the duplicate-first-move refusal (§2.7) |
| F4a-C5 missing adapter tests; weak sequence test; vacuous test | `readyok` / `bestmove` timeouts tested; the fake offers Stockfish 19's options; full sequences of two searches; vacuous test replaced |
| F4a-C6 `SearchId` and default-field coverage overstated | every field varied independently; chained comparison fixed; defaults removed (C7) |
| F4a-C7 invented field values | missing fields refused (§2.6) |
| F4a-C8 refused request's engine calls counted | `discard` rolls them back (§2.11) |
| F4a-N1 port reused after a timeout | the process is killed; later searches raise (§2.12) |
| F4a-N2 lenient parsing | repeated fields, PV without score, `info string` lines; negative counts and WDL sums refused |
| F4a-N3 adapter robustness | missing binary, pipes, reader errors, no name switch, wrapper commands stated (§2.12) |
| F4a-N4 root moves validated late | validated before the engine call (§2.10) |
| F4a-N5 `put` keeps both racing records | returns the stored one |
| F4a-N6 stop before depth 1 | stated in F4-D §5.2 |
| F4a-N7 acceptance gaps | `do_move` en passant path; a bare FEN shown to differ |
| F4a-N8 stale roadmap row | rewritten |
