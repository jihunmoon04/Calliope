# Agent — packet AG6a implementation: what an agent is shown

Status: **rev. 1 — for independent review**. Date: 2026-10-17. Design:
[`agent-ag6-design.md`](agent-ag6-design.md) rev. 4 (AG6-D: F2, F4–F7, F12–F16, §3, §5, §7 for one
ply; checks I1–I3, §19), owner decisions Q1–Q3 and Q7 (2026-10-17, AG6-D §15). Base: `main @
2880a33` (AG6-D merged, PR #106; the code of `1f9ef15`). Packet AG6b (the game path) follows.

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/digest.py` (new) | the digest of a ply (AG6-D §3.2): grade and label with their Korean names, the evaluation as text, the judgement's ref, the played and the best line (ref, move, score, depth, 8 SAN plies), up to 3 other candidates, Calliope's text, the SUPPORTED and INCONCLUSIVE claims in the role order (ref, template, role, status, scope in one line, `says`, `attributed`, findings without positions), REFUTED claims named, observations counted, `not_shown`; the caps and the six steps of §3.6 with the final check (`DigestTooLarge`) |
| `agent/session.py` | `ply` / `judge_move` take `view` (`digest` by default, `full` today's answer); `_digest` adds the unrendered claims' own sentences, `cached`, `budget_left`, `next` and the bound; `detail(game, ref)`; `open_game` refused part-way answers what it analysed (F13); `submit_commentary` takes `items`, each subject through `_commentary` with its outcome (`accepted`, `duplicate`, `refused`, `not_stored`), the size limits of §5.3 and the duplicate key (F15); `next` on the one-ply path (§7) |
| `agent/propositions.py` | a `judgement` proposition's `move`, `grade`, `label`, `best_move` and a `claim` proposition's `scopes`: verified when given, filled from the cited item when left out (§5.1); the stored record is unchanged |
| `agent/handles.py` | `is_handle(value)` |
| `agent/server.py` | the tool `detail`; `view` on `ply` and `judge_move`; `items` on `submit_commentary` (its `propositions` and `sentences` now optional); every tool but `show_game` answers `answer(dict)` — compact JSON in `content`, the dict in `structuredContent` (F12), annotated `Annotated[CallToolResult, dict[str, Any]]` so each `outputSchema` stays as it was; the instructions (one-ply order with digests, references, `items`, saving to show on the board, `next`); the descriptions of `ply`, `judge_move`, `detail`, `submit_commentary` |
| `agent/definitions.py` | `agent_tools_v4`, `agent_guidance_v2`; the statements of `proposition.judgement` and `proposition.claim` (fields left out are the item's) and of the tools entry |
| `agent/prompts/commentary_ko_v1.md` | steps 1, 2, 5, 7 for the digest, `detail`, references and `items`; a step 8: saved commentary is what the board shows |
| `reasoning/render` | `claim_sentence(analysis, claim_id)`: one claim's sentence form, bound and phrased as `render` would write it; exported from `calliope.reasoning` |
| `server/commentary.py` | `board_form(record, start_fen)` (what a combined document carries of a record; `with_commentary` now uses it) and `board_size(record, start_fen)` (its UTF-8 bytes once stored, an unwritten record measured with its format and an id of the store's length, `ID_LENGTH` 29) |
| `tests/agent/test_digest.py` (new), `tests/agent/golden/full_answers_1f9ef15.json` (new) | §3 below |
| `tests/agent/*` | the tests that read the full graph pass `view="full"`; the server tests' commentary uses a judgement by reference; the tools listed include `detail`; versions and the guidance pin (`agent_guidance_v2`, v1's digest kept) |
| `docs/design/agent-mcp-design.md` | amendment AM9 (AG-D §19) |

Not changed: `show_game` and the viewer (AG6b), `facts` and `explore` answers (AG6-D §10), the
budget, the reasoning build and every cache key (the build covers versions, templates, the
phrasebook file, grading and the registry, not the renderer's code), the stored record format
(`ai_commentary_v1`).

## 2. Choices and departures (for the reviewer)

- **`says` for an unrendered claim** comes from a new public `claim_sentence` in the renderer: a
  `_Renderer` without a plan binds and phrases the claim's `sentence` form, as `render` does for
  the claims a plan keeps. A template with no usable sentence form answers None (`says` absent,
  AG6-D §3.2's own branch). On the Opera Game every comparison claim the text left out gets one
  ("Instead, 15.Bxf6 was better.").
- **`attributed` only where ATTRIBUTED applies**: claims of `material_gain_v3` and
  `material_loss_v2` carry `passed`, `failed` or `absent`; other claims omit the field (absent for
  them says nothing, and §3.2 asks for it next to the claims that a `result` use depends on).
- **`lines.best` is null when the played move is the best**: its line is `lines.played` (one line,
  one ref).
- **Scores twice in a line, once in the evaluation**: a line carries the raw `score` (what an
  `engine_score` proposition must give) and `score_text` (`+3.64`, `M3`, `-M3`: what a sentence
  writes, rounded half away from zero as token rule `score` reads it); the evaluation carries the
  text only.
- **A label** is its kind with `label_ko`, and `label_provisional: true` when the record says so.
- **Steps 5 and 6 put their bookkeeping first.** The tests found that step 6, measured without its
  own `left_out` and step entry, left a digest 46 characters over the bound. Steps 5 and 6 now
  record themselves before they move anything, so every measure counts what the answer will carry.
  Step 6 leaves out the REFUTED list's entries first, then the named claims, each from the end.
- **The duplicate key** leaves out, besides every handle (`ref` keys, handle strings), the facts
  tree's `rev` in a `facts_tree` source: it grows with the tree and differs between processes, so
  a key with it would miss the duplicate of a position-reading proposition after a restart. The
  analysis, search and explored-line sources are request-derived and stay in the key.
- **A single subject's answer** keeps its shape (`accepted`, `id`, `level`, the counts, or
  `violations`) and gains `next`; a duplicate is `accepted: true, duplicate: true` with the stored
  id; a failed write stays a tool error as before. `items` answers `{"items": [{"index",
  "outcome", …}], "next"}`; a non-object item and an item whose subject does not hold are
  `refused` with the rule `item` or `subject`.
- **Over 32 propositions** an item is refused with the size violation alone, before any is
  verified; an id over 32 characters is refused with the uniqueness check's violation ("a unique id
  of at most 32 characters is required").
- **`next` after `open_game`** points to `ply` in AG6a (`analyze_game` comes with AG6b); after a
  part-way refusal it says to comment only the analysed plies and when the rest can be analysed.
- **F12 covers every tool** that answers a dict (`open_game`, `ply`, `judge_move`, `detail`,
  `facts`, `explore`, `definitions`, `submit_commentary`, `commentary`); `show_game` already
  answered a short text with its document in `structuredContent`.
- **The prompt file is edited in place**, as AG2 and AG4 did: its id stays `commentary_ko_v1`, its
  digest in the agent build changes.
- **The golden test** (`view: "full"` field for field, AG6-D §13) compares the full answers of
  `ply` 3 and an unplayed `judge_move` over the synthetic engine with those of `main @ 2880a33`,
  handles made neutral; the fixture was written by running the same code against that commit, and
  a run of the new code wrote a byte-identical file.

## 3. Test obligations (AG6-D §13, the AG6a part; I3)

| Obligation | Where |
| --- | --- |
| Digest: the fields of §3.2, nothing hidden shown (V4, V5), REFUTED named with their refs, observations counted, every ref resolves | `test_digest.py::test_the_digest_has_the_fields_of_the_design_and_nothing_hidden` |
| The claim order | `::test_claims_are_in_the_role_order` |
| A judged move digested as a ply; an unknown view refused | `::test_a_judged_move_is_digested_as_a_ply`, `::test_a_view_other_than_digest_or_full_is_refused` |
| Scores and moves as a sentence writes them | `::test_the_score_and_the_move_as_a_sentence_writes_them` |
| `says` from the text or from the claim's own sentence; `claim_sentence` | `::test_an_unrendered_claim_says_its_own_sentence`, `::test_claim_sentence_phrases_one_claim_or_answers_none` |
| Bounds: each step 1–6 in turn, in order, the bound held, the never-moved fields kept | `::test_each_step_runs_in_order_and_the_bound_holds` |
| `not_shown` names the steps, counts and named entries | `::test_steps_move_items_behind_detail_and_say_so` |
| Still over after every step: an error, never a cut | `::test_a_digest_still_over_after_every_step_is_an_error_not_a_cut` |
| Caps on `text`, `says`, finding strings; positions left out of findings | `::test_fields_of_free_length_are_capped` |
| `view: "full"` equals today's answer field for field (golden) | `::test_the_full_view_is_todays_answer_field_for_field` |
| `detail` of a judgement, claim, search line, fact record and explored line equals the item; a foreign handle refused | `::test_detail_answers_the_item_as_the_full_answer_projects_it`, `::test_detail_refuses_a_handle_of_another_process` |
| By-reference propositions verify and fill, and store as the full form (the second is a duplicate) | `::test_a_proposition_by_reference_is_filled_and_stores_as_the_full_form` |
| A field given is still verified; a wrong `use` refused | `::test_a_field_given_is_still_verified_and_a_wrong_use_refused` |
| `items`: accepted and refused each on its own, ids per item, a bad item and a bad subject refused | `::test_items_are_verified_and_stored_each_on_its_own` |
| `items` and a single subject not mixed; at most 16 | `::test_items_and_a_single_subject_are_not_mixed_and_items_are_bounded` |
| A failed write on the third of five: `accepted, accepted, not_stored, accepted, accepted`; the resend stores the third once | `::test_a_failed_write_is_reported_per_item_and_a_resend_stores_each_once` |
| I3: the same commentary from a new process (new handles, persisted records) is a duplicate; renamed ids are new | `::test_the_same_commentary_from_a_new_process_is_a_duplicate` |
| 33 propositions, an id of 33 characters, over 64 KiB on the board: refused with `size` | `::test_one_commentary_is_bounded` |
| `board_size` is the stored record's board form | `::test_the_board_size_is_measured_as_the_record_will_be_stored` |
| F13: refused part-way answers the analysed plies with `refused`; a refused first ply stays an error | `::test_an_open_game_refused_part_way_answers_what_it_analysed` |
| `next` on the one-ply path | `::test_next_on_the_one_ply_path` |
| F12 through the client: compact `content` equal to `structuredContent`; the output schema unchanged; `detail` through the client | `test_server.py::test_answers_are_compact_json_equal_to_their_structured_content` |
| `items` and duplicates through the client | `test_server.py::test_several_subjects_in_one_submission_through_the_client` |
| Build: `agent_tools_v4`, `agent_guidance_v2` pinned | `test_guidance.py::test_the_guidance_is_in_the_agent_build_and_pinned`, `test_commentary.py::test_an_accepted_commentary_is_stored_with_its_sources` |

## 4. Results

### 4.1 Tests

To be filled: the whole suite with Stockfish 19, `ruff`.

### 4.2 The digest on the Opera Game

The 33 full answers of AG6-D §0.3, digested by this packet's code (compact JSON, as sent): median
1,881, max 5,089 characters; no step of §3.6 ran. Through a session over the cached analyses,
`ply` 18, 29 and 31 asked no search (`budget.meter.used` 0) and every SUPPORTED comparison claim
the text left out said its own sentence.

### 4.3 Trials in HIMARI

HIMARI v3 `main @ 9a07e0e` (its driver, server sandbox, one shared Calliope process, the MCP App
on), Calliope at this packet's commit `f29ef46`, `openai/gpt-6-luna`, a fresh conversation and data
directory per turn, 2026-10-17. **T1**: the request of AG5-D §0 (open the game, analyse 5...h6,
write and save its commentary), three turns. **T2**: the request of AG6-D §0.2 ("이 대국을 분석해
줘." with the Opera Game), two turns. Baselines: AG5's turns (AG5 §4.2) for T1, AG6-D §0.2 for T2
(the same HIMARI and model, Calliope `1f9ef15`).

| Turn | Runs | Time | Input tokens (cached) | Largest request | Output | Calls | Submissions | Commentaries stored |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AG5 turns 1–3 (before) | 7, 9, 5 | 42, 41, 25 s | 132,332 / 191,622 / 80,809 | — | 2,850 / 2,603 / 1,642 | 10 / 15 / 8 | 1 each | 1 each (judgement only) |
| T1a | 7 | 27 s | 51,618 (41,779) | 9,089 | 1,440 | 8 | 3 | 1 |
| T1b | 5 | 21 s | 32,966 (27,779) | 8,099 | 738 | 6 | 1 | 1 |
| T1c | 7 | 28 s | 52,200 (45,606) | 9,256 | 1,534 | 8 | 3 | 1 |
| §0.2 (before) | 9 | 103 s | 80,640 (49,397) | 30,243 | 6,087 | 13 | 0 | 0 (chat, from memory) |
| T2a | 9 | 82 s | 103,178 (89,858) | 15,542 | 3,534 | 15 | 3 (`items`) | 3 (plies 7–9) |
| T2b | 7 | 104 s | 142,064 (115,465) | 29,383 | 7,489 | 24 | 2 (`items`, 10 and 8) | 10 (plies 19–31) |

What changed:

- **T1: 35–83% fewer input tokens than AG5's turns** at the same or fewer Runs, and every
  commentary cites claims besides the judgement (2–3 claim propositions each), all by reference:
  "엔진 라인에서는 7.Nxe5로 e5의 흑 폰을 잡아 … 1점의 기물 손실이 발생한다", "더 나은 대안은 5...Bc5였고,
  제시된 라인은 5...Bc5 6.O-O d6 7.c3 Ba7 8.Re1로 이어진다". Every turn ended with `show_game` and a
  chat reply of 92–116 characters.
- **T2: the commentary is on the board, not in the chat.** Both turns read the plies the budget
  allowed as digests (7 and 16 `ply` calls; the largest request 15,542 and 29,383 tokens, against
  about 18,000 for each full answer the deployment read), submitted them with `items`, and called
  `show_game`; no summarising. The replies (253 and 406 characters) summarise what the board holds
  and say that the rest was not judged because of the budget, instead of commenting it from memory.
  T2b chose the game's moments itself (19, 21, 23–25, 27–31: the sacrifices, 15.Bxd7+ and the mate).
- **Every proposition by reference**: no turn copied a field; no `scopes` was written.

Not changed, and for what follows:

- **The analysis budget still decides what a game commentary covers**: 10 plies in T2a (1–10), and
  T2b's later `ply` calls refused (`up to 10 searches`, 6 left). That is AG6b's job (`analyze_game`
  and its own budget).
- **`use` is the agent's commonest mistake now**: T1a, T1c and T2a each had a submission refused for a
  claim's `use` — `"supported"` (the claim's status written as its use) or `result` for a claim that
  is not a consequence — and fixed it on the next one. A candidate for a later packet: the digest
  could list each claim's admissible uses (the verifier's own rule, §4.1 of AG-D).
- **No turn called `detail`, `judge_move`, `facts` or `explore`**: the "why" is still what the
  catalogue's claims say (AG6-D §10, server-built comparisons).
- T2b's first `items` call stored 2 of 10 items; the 8 others were refused each on its own (the
  record's first 3,000 characters name S1, S2 and S3 sentence rules — e.g. a move `10...cxb5` no
  cited proposition holds — and a claim's `use`). Its second call resubmitted only those 8, all
  accepted: 10 records for 10 plies. The duplicate rule was not exercised in the trials.
