# Agent — packet AG2 implementation: propositions, the sentence check and stored commentary

Status: **rev. 5 — re-review of rev. 4 NOT_READY (B5) applied (§8); AG-D AM5**.
Rev. 2 applied an agent-run review of rev. 1 (§5), not an owner-arranged independent review.
Date: 2026-10-15. Design: [`agent-mcp-design.md`](agent-mcp-design.md) rev. 6 with AM1 (AG-D).
Base: `main @ 11d3b6e` (AG1 merged, PR #96).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/propositions.py` (new) | `Verifier`: the 15 proposition kinds of AG-D §4 and the 7 uses of §4.1, each field checked against its source; a handle of another kind, game or session refuses (`Refused(field, problem, expected)`); each verified proposition says what a sentence citing it may write (`Allowed`) |
| `agent/sentences.py` (new) | S1–S4: the S3 tokenizer and its six rules in order (moves with move numbers and sides, scores rounded half away from zero, mates, squares, signed integers, the rest a violation) |
| `agent/session.py` | `submit_commentary` (§5): every proposition and sentence checked, every violation returned, nothing stored on a refusal; the subject's own judgement required; S6 (`by_agent` on a sentence citing an explored line); the record stored with resolved sources, the subject's bundle digests, the agent build and the reasoning build. `commentary`: a subject's accepted commentaries, newest first, `stale` against the ply cache. The served `ply` and `judge_move` answers gain, on each judgement line, its PV (`by: engine`) and depth, and on the subject's judgement its label (what the propositions cite) |
| `agent/build.py` (new) | the agent build, the prompt texts and the registries, free of the MCP SDK (moved from `server.py`) |
| `agent/server.py` | the tools `submit_commentary` and `commentary` |
| `agent/definitions.py`, `agent/prompts/commentary_ko_v1.md` | the proposition fields as implemented (handle fields `judgement`, `claim`, `line`; `definition`); tools `agent_tools_v2`; the prompt's step on propositions and submission |
| `server/commentary.py` (new) | `game_key` (`game_key_v1`, moved from the agent, AG1 review note), `subject_digest`, `CommentaryStore` (write once through a unique temporary; read newest first), `stale`, `listing`, `with_commentary` |
| `server/web.py`, `server/jobs.py` | `GET /api/games/{id}/commentary` (`no-store`); `GET /api/games/{id}/result?with=commentary` builds the combined document fresh (`no-store`), the plain route keeps the stored bytes and `immutable`; `Jobs.pgn` |
| `results/schema/calliope_result_v1.json` | `Ply.ai_commentary` → `AiCommentary` (AR-D §14 AM1) |
| `tools/explain_game` | `--with-commentary DATA` (with `--json`) |

## 2. Choices and departures (for the reviewer)

- **Proposition formats.** AG-D §4 names fields; AG2 fixes how they are written. A handle field
  names the source: `judgement` (a `j` ref), `claim` (`c`), `line` (`s`, or `x` for `material`
  and `explored_line`). Moves are SAN or UCI and stored as UCI; positions are a tool position
  argument (`{"ply", "at"}` or `{"from_root"}`). `definition` takes the registry id in the field
  `definition` (the proposition's own `id` is its id). Optional `refs` are checked to be handles
  of the game.
- **Position kinds read the facts tree** (implicit source, AG-D §4): `attack`, `defence`,
  `exposed`, `pin`, `check`, `legal_moves`, `pattern` need no handle. Their positions are extended
  into the facts tree and charged to the node budget like `facts`.
- **`legal_moves.moves`** is the whole legal set (equality), and lets no sentence write those
  moves (AM2 (e)); `check.checkers` an exact set (empty: not in check).
- **`after_reply`** is always the agent's comparison: its citations are stored `by: agent`
  (AM2 (d)).
- **`pattern.participants`** are the record's fields by square (`actor`, `slider`, `front`,
  `back`, `defender`, `king`), lists of squares (`targets`, `defended`, `blockers`, compared as
  sets) and `line` as `[file step, rank step]`. Verified patterns are stored with
  `configuration_only: true`.
- **What a sentence may write (S3).** A `judgement` allows its move and best move (and their
  squares and move numbers); `engine_score` its move, score or mate, depth; `engine_line` and
  `material` and `explored_line` their moves; `claim` the moves, squares and points its record
  names (evidence lines, population moves, pieces); position kinds their squares (and counts,
  gains); `after_reply` the two moves, the reply and its nested propositions'.
- **The subject's judgement.** A submission needs a `judgement` proposition citing the subject's
  own judgement: the first judgement of the analysis of exactly the subject's path.
- **`stale`** in the session's `commentary` tool compares the stored bundle digests with the
  cached files' digests now (null when the ply is not cached); the HTTP route compares with the
  job's result (§8).
- **Agent-only answer fields.** The PVs, depths and the label added to `ply` answers are not in
  `calliope_result_v1`; the document is unchanged.

## 3. Test obligations (AG-D §11, the AG2 part)

| # | Test |
| --- | --- |
| 4 | `tests/agent/test_propositions.py`: a handle of another kind (a claim as a judgement), another game and another session refuses |
| 5 | `test_propositions.py`: one accepting and one refusing case for each of the 15 kinds and the 7 uses — among them a gain as `result` with `ATTRIBUTED` failed and absent, a `mechanism` whose target is not SUPPORTED, `scopes` of a premised claim (`sacrifice_sound_v1`: `specific_line` and `exists_alternative`) accepted whole and refused with one missing or one field changed, `exposed` (`exposed`, `not_exposed`, a wrong gain), an `after_reply` with two different P, a failing nested side and nested kinds that differ, an explored line cited as an engine line |
| 6 | `tests/agent/test_commentary.py`: the tokenizer on Korean text; each token rule (29 cases: move numbers and sides, particles, bare squares, scores with sign and rounding, `−`, mates, integers, `0-0`, `Stockfish16`, `0.385`, `Ne9`, `O-O`); a signed integer against a balance; S1 and S2; S3 on an interpretation (S4); `by_agent` (S6); the review's B1 case — a sentence with no token citing an unrelated claim is accepted as `SOURCE_VERIFIED` only, and the record says so |
| 7 | `test_commentary.py`: an accepted commentary stored with resolved sources and bundle; a refused one lists every violation (proposition field, subject, S2, S3) and stores nothing; the subject needs its own judgement; a judged move as subject. `tests/server/test_commentary_route.py`: the route (current, stale, beyond the job's range, judged), the combined document (only current commentary; validates with the shipped validator and `jsonschema`), the plain result route and `result.json` byte-identical with `immutable`. `tests/tools/test_explain_game.py`: `--with-commentary` |
| 2, 9 | `tests/agent/test_server.py`: the eight tools listed; a refused and an accepted submission and `commentary` through the MCP client |
| 10 | `tests/agent/test_stockfish.py` (gated): 17.Ne3 — a commentary with `judgement`, `check` (e8), `engine_score`, the exchange `claim` as `line_fact`, and one interpretation, accepted; the same claim as `result` refused on `use` |

The whole suite with Stockfish and the `agent` group: **1280 passed** at rev. 2 (17 min; AG1's
1217); rev. 3 in §6.

## 4. Not in this packet

AG3: the viewer's AI commentary panel (verified propositions, sourced and interpretation sentences,
stale ones apart) and the MCP App.

## 5. Review dispositions (rev. 1 `220e490`, agent-run review: NOT_READY)

The review reproduced three ways an accepted commentary could state what Calliope did not verify;
it found the handles, the uses of a claim, `after_reply`'s geometry, the engine lines, the
material check, the store's keys and paths, the routes' caching and the schema sound.

| Finding | Disposition |
| --- | --- |
| **B1** the subject check took the first judgement source, and `refs` were resolved first: an extra `refs` naming the subject's judgement made another judgement's fields pass for the subject | Applied: a judgement proposition records the source of its own `judgement` field (`judged`), and the subject check and the stored bundle read it; `refs` are resolved after the fields. Test: the review's case is refused |
| **B2** `parse_san` ignores `x`, `+`, `#`: `Nf3#`, `Nxf3`, `2.exd5#` passed for quiet moves; `O-O+` was never checked | Applied (AM2 (b)): `x` exactly for a capture, `+` only for a check that is not mate, `#` only for mate (a mark may be left out); castling with a mark is a move token. Tests |
| **B3** an en dash, `－`, `⁻` and full-width digits and letters hid signs and numbers (`–2점` against +2, `－1.00` against +1.00, `Ｍ３`) | Applied (AM2 (a)): NFKC, every dash and minus sign read as `-`, a digit of another script a violation. Tests |
| 1. S6 never applied to `after_reply` | Applied (AM2 (d)): always `by: agent`. Test |
| 2. `legal_moves.moves` licensed any legal move in a sentence | Applied (AM2 (e)): it licenses none. Test |
| 3. a damaged store file broke the route; a damaged job's empty PGN raised | Applied: unreadable or incomplete records are skipped; the route answers 409. Tests |
| 4. ids of one second sorted at random | Applied: ids start with the time in nanoseconds. Test |
| 5. `exposed` `undecided` untested | Applied: in check (`IN_CHECK` gain) and `undecided` (the rule stubbed, as no real position reaches it). Test |
| 6. a non-string `definition` or cite raised | Applied: a refusal and an S2 violation. Tests |
| (note) a lone move number ending a sentence was refused | Applied (AM2 (c)): it reads as its integer. Test |
| (note) the session's `commentary` hashes the cache files without the shared lock | Kept: at worst one answer shows `stale` for a moment |

## 6. Review dispositions (rev. 2 `0864fad`, independent review: NOT_READY)

The review (owner-supplied, external) confirmed rev. 2's fixes, the uses of a claim and the split
of engine and explored lines, and found the store's records, the combined route's errors and the
move numbers unsound.

| Finding | Disposition |
| --- | --- |
| **B1** `_sound` checked the format, id, path and bundle only: a readable newest record without `sentences`, `propositions` or `level` went into `ai_commentary`, and the combined document broke `calliope_result_v1` | Applied (AM3 (b)): a record is read only when what the combined document carries of it is a valid `AiCommentary` (`schema_errors(value, "AiCommentary")`, the shipped validator on one definition); others are skipped by the listing and the combined document alike. Test: four damaged newer records skipped, the combined document valid |
| **B2** `?with=commentary` did not catch a damaged job's `InputError`; the commentary route answered 409 | Applied (AM3 (c)): 409 on both; the plain result route still serves the stored bytes. Test |
| **B3** a move number was joined only across exactly one space: `17.  Rxe3` (two spaces, a tab, a line break) split into `17` and `Rxe3`, so black's 17...Rxe3 passed written as white's 17th | Applied (AM3 (a)): a move number joins the next token across any whitespace, `17 . Rxe3` and `17 ... Rxe3` read as `17. Rxe3` and `17... Rxe3`, and a number with two or four or more dots before a move is a violation. Test: seven spellings refused, five accepted; the case fails on rev. 2 |
| 3. a list as `pattern` raised `TypeError` | Applied: a refusal. A test replaces every field (and every field of a nested object) of an accepted proposition of each kind with `[]`, `{}`, a list, an object, a float, `true` and `null`: each is refused or accepted, never an error. It found one more: a `from_root` that is not a list of strings raised in `Session.path` (also the tools' position argument); now an `AgentError`, and a boolean `ply` is no ply |

The whole suite with Stockfish 19 and the `agent` group at rev. 3: **1298 passed** (17 min 24 s).

## 7. Review dispositions (rev. 3 `c53d81b`, independent re-review: NOT_READY)

The re-review passed B1–B3 of §6, the `pattern` and `from_root` refusals, and found the S3
tokenizer still split a sign or a move number from what it qualifies.

| Finding | Disposition |
| --- | --- |
| **B4** a sign apart from its number (`평가는 - 1.00이다.`, `백은 − 2점`: tokens `-` and `1.00`, the sign never checked) and an invisible U+200B between `17.` and `Rxe3` (tokens `17` and `Rxe3`) | Applied (AM4): characters shown as nothing (Unicode's default-ignorable code points, format and control characters) are removed before tokenising and U+2800 read as a space; across a gap with no letter or digit, a sign or a mate mark joins the number after it (`- 1.00`, `−(2)`, `M 3`, `# 3` read as `-1.00`, `-2`, `M3`, `#3`) and a move number its move; a sign touching a word before a number (`-약 1.00`) is a violation; a dash elsewhere in prose is no token. A dash written right before a number reads as its sign. Test: the review's three cases fail on rev. 3 |
| (same class, found while fixing) a Hangul filler (U+3164, U+FFA0) or a braille blank between a move number and its move; a homoglyph (`Rxе3` with a Cyrillic е: tokens `Rx` and `3`); a combining mark on a digit (`1́.00`) | Applied (AM4): the fillers are removed or read as a space; a letter or mark other than ASCII and Hangul touching a move or a number is a violation. Tests |
| (found while fixing) the agent's definition `token.split` still said "followed by one space" (rev. 3 changed the rule, not the text) | Applied: it states AM3 and AM4; the agent definitions digest changes with it |

The whole suite with Stockfish 19 and the `agent` group at rev. 4: **1299 passed** (17 min 25 s).

## 8. Review dispositions (rev. 4 `0b1ada9`, independent re-review: NOT_READY)

The re-review passed B1–B4 and found a sign that could not join its number was dropped.

| Finding | Disposition |
| --- | --- |
| **B5** a sign apart from a number with a word or another sign between (`평가는 - 약 1.00이다.`, `평가는 - (+1.00)이다.`) was dropped as a dash in prose, and `1.00`, `+1.00` passed against +1.00 | Applied (AM5): a sign, `M` or `#` that does not join the number after it is a violation whenever the next token writes a number, a score or a mate; it is no token only before a word or a move (`e4 - e5`, `Rxe3 — 좋은 수다`). Prose dashes before a number (`Rxe3 — 백은 2점`) are now refused: the relation cannot be decided. Tests: the review's two cases, `M 약 3`; they fail on rev. 4 |

At the owner's request only the related tests were run for rev. 5 (`tests/agent/test_commentary.py`,
`test_propositions.py`, `test_server.py`: 77 passed); the whole suite was not.
