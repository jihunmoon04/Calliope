# Agent — packet AG3a implementation: `display_v1` and the AI commentary panel

Status: **rev. 2 — independent review NOT_READY (B1, B2) applied (§5); AG-D AM7; re-review of rev. 2:
ready to merge (2026-10-15); owner's check of the panel passed (2026-10-15, the demo game served on
this machine)**.
Date: 2026-10-15. Design: [`agent-ag3-design.md`](agent-ag3-design.md) rev. 4 (AG3-D: D1–D8, D12,
D14, §3, §3.1, §5). Base: `main @ 1e0146a` (AG3-D merged, PR #98).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `server/commentary.py` | `displayed(record, start_fen)`: `display_v1` on each proposition and on the record (`subject`), computed with python-chess when read, never stored (D14, §3.1); `listing(…, start_fen)` and `with_commentary` pass every record through it; the combined document's `ai_commentary` gains `display` |
| `server/web.py` | the commentary route reads the job's start FEN with its game (one parse) |
| `results/schema/calliope_result_v1.json` | `DisplayLine`, `Display`; `AiCommentary.display` and `AiCommentary.propositions[].display`, optional — the AR-D amendment D14 names; every existing document stays valid |
| `viewer/index.html` | the pure part: `readableCommentary`, `propositionLine` (§3), `propositionFrames` (D7), `commentaryIndex` (D4, D8), `commentaryHtml` (D4–D6, D12), `fetchCommentary` (D1); the page: the panel `#ai` under the ply panel (D3), hover/pin/Esc previews of propositions, chips and judged subjects through the existing preview strip, 「해설 새로고침」, the listing fetched after the result in server mode |

## 2. Choices and departures (for the reviewer)

- **`material` keeps the line it was verified against** (rev. 2, AG-D AM7): `base` (the line's
  start, a path from the root) and `moves` join its verified values, so a search line previews
  as an explored one does (§3.1, "the whole line"). A record written before AM7 over a search line
  has neither and gets no `display` (its text is shown).
- **A judgement's position** is found from its source: judgement k of an analysis judges the move
  `path[-1-k]` of the analysis path (the subject's move, then the previous one; R0-D's controller
  order). The stored move must equal that path entry, or the proposition gets no `display`.
- **After `after_reply`**, the reply is written without a move number (`같은 응수 Nf6 뒤`): it is
  the second move of each side's line, and the number of the first is not the reply's.
- **The panel re-renders on every ply change**, so a section opened on one ply is closed on the
  next; the propositions list is open by default (D6).
- **The phone layout** gives `#ai` the ply panel's order, so it follows the text directly (D3).
- **Server-mode tests run the pure part.** The page's DOM wiring (`renderAi`, `loadCommentary`,
  the refresh button) has no DOM under node; its logic is in `commentaryIndex`,
  `commentaryHtml` and `fetchCommentary`, which the tests run. The owner's check covers the page.

## 3. Test obligations (AG3-D §5, the AG3a part)

| Test | Where |
| --- | --- |
| `display_v1`: each kind's shape (`moves` always an array, `best`, `a`, `b` lines, `v` on the outer object only), SAN against python-chess (a disambiguated knight, castling then a check, a mate, a promotion), `legal_moves` as `choices` (the 20 of the start, a position in check), the subject of a played, a judged and an off-game move, damaged propositions left without `display` and unchanged, the record not mutated, schema validation | `tests/server/test_display.py` |
| the listing route and the combined document carry `display` (proposition and subject), equal in both, validate (`schema_errors`, `jsonschema`), and no stored file holds it | `tests/server/test_commentary_route.py` |
| placement (D4, D8): the newest current one as the ply's, an older and a stale one apart and labelled, judged moves on ply 2 and on the start position (k = 0), an off-game variation at game level and on no ply; a combined document's one per ply | `tests/viewer/test_viewer_ai.py` (node, `check_ai.js`) |
| §3 lines of judgement, engine and explored lines, legal moves, attack, `after_reply`; `(표시할 수 없음)` without `display` | same |
| D7 previews: 20 legal moves, each one move from the start position; the explored line step by step; the attack's rings and arrow; both sides of `after_reply`; the judgement's move | same |
| D4–D6: the level tag and note, sourced and interpretation sentences, the agent's line tag, chips, "문장 n" on the propositions, the agent's name and model, no "검증" | same |
| D12: a hostile sentence, agent name and model, ids and a tag escaped; unreadable records skipped | same |
| D1: the listing by a relative URL; a 409 and a network error as messages | same |

Related tests run for this packet (the whole suite was not run): `tests/agent`, `tests/tools`,
`tests/server`, `tests/results`, `tests/test_package_boundaries.py` — 416 passed, 2 skipped (the
Stockfish-gated ones); `tests/viewer` — 11 passed.

## 4. Not in this packet

AG3b: the MCP App (D9–D11, D13), `show_game`, the bridge in the viewer.

## 5. Review dispositions (rev. 1 `74901e3`, independent review: NOT_READY)

The review passed the stored files' immutability, the schema amendment, SAN and `choices`, the
placement of played, judged and off-game commentaries, the split of sentences and propositions,
and the escaping.

| Finding | Disposition |
| --- | --- |
| **B1** `pin` read 「핀: c3 (b4가 고정)」: the pinner seemed the pinned piece | Applied: 「핀: b4 → c3 (고정된 기물 c3)」, the arrow from the pinner to the pinned piece as before. Test: the pin of 3...Bb4+ 4.c3, its line, rings and arrow |
| **B2** a judgement with no best move (`best_move: null`, a sound verified value) lost its whole `display`: `_line(fen, [None])` failed | Applied: the move's line always, `best` only with a best move. Test |
| (deviation) `material` over a search line had no preview, against §3.1 | Resolved rather than kept: AG-D AM7 — `material` stores `base` and `moves`, the line it was verified against; `display` reads them. Tests: the verified record, the display, the viewer's frames over a search line |

Related tests after rev. 2 (the whole suite not run): `tests/viewer`, `tests/server/test_display.py`,
`tests/server/test_commentary_route.py`, `tests/agent` — 123 passed, 1 skipped.

Re-review of rev. 2 (`c498f1f`), independent: ready to merge (2026-10-15).
