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

To be filled.
