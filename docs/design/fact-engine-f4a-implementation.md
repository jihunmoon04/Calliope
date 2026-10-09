# Fact engine — packet F4a implementation: engine boundary

Status: **rev. 1 — awaiting independent F4a review**.
Date: 2026-10-09. Design: [`fact-engine-f4-design.md`](fact-engine-f4-design.md) rev. 3
(F4-D §3–§5, §9.1, §9.3 items 1–4). Base: branch `design/fact-engine-f4` @ `f31f74a` (PR #47).

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
6. **Unknown `info` fields** refuse the line. Every field Stockfish 19 prints is known
   (`depth`, `seldepth`, `multipv`, `score`, `wdl`, `nodes`, `nps`, `hashfull`, `tbhits`,
   `time`, `pv`, …).
7. **A missing `seldepth`** reads as `depth`; missing `nodes` / `tbhits` read as 0. Stockfish 19
   prints all of them; the fake engine exercises the defaults.

## 3. Not in F4a

Tree integration (F4-D §6–§8, F4b), persistence and tape replay (F5).

## 4. Evidence

| Check | Result |
| --- | --- |
| `tests/facts/search/test_uci_adapter.py` (15 tests) against `tests/facts/search/fake_uci.py`. Covers: last line per rank (no merge); illegal, null, SAN and malformed PV tokens passed on and refused by normalization; scored line without `pv`; rank gap, excess and fewer ranks; missing WDL; wrong name; start error; process death; cap ⇒ `stop` ⇒ `TIME`; `TIME` at full depth irregular; exact command sequence, with `EvalFile` / `Threads` sent once | pass |
| `tests/facts/search/test_search_records.py` (21 tests). Covers: White-view scores and WDL with both sides to move; mate 0; `UNAVAILABLE`; rank and line refusals; restriction and k; `TIME` with fewer ranks; regularity; window length and form; pseudo-legal start board unchanged; `node_input` across the root; every `SearchId` preimage field; stability across processes; irregular ids; store hit without engine; session-only irregular reuse with pending / commit / discard; thread-safe store; `threads=2` refused | pass |
| `tests/facts/search/test_stockfish_acceptance.py` (4 tests; F4-D §9.3 items 1–4; real Stockfish 19). Covers: identity (name, sha256, one network); fresh-state determinism after unrelated searches and in a new process; en passant form on 150 positions against the engine's own `d`; window equivalence on 3 histories with windows strictly shorter than the history | pass (skipped without `CALLIOPE_STOCKFISH_PATH`) |
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
