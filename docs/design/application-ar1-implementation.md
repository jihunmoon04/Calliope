# Application — packet AR1 implementation: `calliope.results`, `render.trace`, the tool's JSON

Status: **rev. 1 — for independent review**.
Date: 2026-10-12. Design: [`application-result-design.md`](application-result-design.md) rev. 4
(AR-D, final re-review READY_WITH_CORRECTIONS applied, #79). Base: `main @ 48925bc`.

## 1. Scope delivered

| Module | Content |
| --- | --- |
| `results/__init__.py`, `results/document.py` (new package) | `game_result(game, engine, plies) -> dict`, `dumps(document) -> bytes`, `schema()`, `GameInput`, `GameMove`, `EngineRun`, `PlyInput`, `Bundle`, `ResultError` (AR-D §2–§5) |
| `results/schema/calliope_result_v1.json` (new) | the JSON Schema, 2020-12 (AR-D §5) |
| `reasoning/render/__init__.py` | `trace(plan, analysis)`, `TraceRef`, `TracedSegment`; formatters and `phrase` carry the references they expressed (AR-D §4). `render`'s output is unchanged. |
| `reasoning/build.py` | `build_digest(build)`: the sha256 of the build's canonical encoding (AR-D §5) |
| `reasoning/__init__.py` | public `ReasoningBuild`, `build_digest`, `plan_analysis`, `trace`, `TraceRef`, `TracedSegment` |
| `tools/explain_game/__main__.py` | `--json` writes `calliope_result_v1`; `game_input` normalizes the game with python-chess; one warning line on the default curve (AR-D §6) |
| `tests/test_package_boundaries.py` | `calliope.results` is a redesign package: no legacy import either way; nothing in facts or reasoning imports it; it imports only the packages `calliope.reasoning` and `calliope.facts` and never python-chess |
| `pyproject.toml` | `jsonschema>=4.18` in the `dev` extra, for the tests only; python-chess stays the only runtime dependency |

## 2. Implementation decisions and deviations
1. **How `trace` keeps the references (AR-D §4: one code path).**
   - Each formatter (`fmt_move`, `fmt_witness`, `fmt_piece`, `fmt_line`, the played move)
     returns its text as an `Expressed` string, which carries the `TraceRef` it formatted.
     `fmt_amount`, counts and depths return plain strings, so they carry none.
   - `phrase` returns a `Phrased` string. It carries the refs of the chosen variant's slots, in
     the order the slots first appear in the variant.
   - `_Renderer.append` stores each segment's refs beside it. `trace` runs the renderer once and
     pairs `render`'s own segments with them. There is no second renderer.
   - Both string types compare as their text. `Segment.text` is stored as a plain `str`, so
     `RenderedExplanation`, `claim_graph_v1` and the corpus bytes are unchanged (the storage and
     corpus tests pass unchanged).
2. **`TraceRef`** names the node and move: `move` (the edge into `node`), `search_move` (`uci`
   played from `node`), `piece` (`square` at `node`) and `line` (from `node`, the shown child
   nodes and `truncated`; a zero-ply line holds the first move's `uci` and is truncated).
   `calliope.results` turns each into AR-D §4's `Ref` with FENs and SAN read from the analysis's
   final view.
3. **Label segments** reference the played move only (AR-D §4). Label phrases have no slot, so
   the renderer attaches the played move's reference to them, the MISS lead included.
4. **No bare square yet.** No `phrases_en_v1` slot names a square without a piece. The schema
   keeps the `square` kind, and test 7d checks that a square ref must carry its FEN; the builder
   emits none today.
5. **The whole-rendering check uses `explain(a)`.** That is `render(plan_analysis(a), a)`; the
   name `render` cannot be exported from `calliope.reasoning`, where it is the subpackage's name.
   `trace(plan_analysis(a), a)` then has to give the same text and source per segment.
6. **`EngineRun` fields are untyped** (`Any`). `EngineIdentity` is not a public `calliope.facts`
   name, and the builder only compares them by equality and reads their fields.
7. **Headers.** `GameInput.headers` is projected in AR-D §2's order. Absent and `None` values
   are left out; ratings must be integers and the rest strings, else `ResultError`. The tool maps
   the PGN tags and drops PGN's unknown values (`?`, `????.??.??`). A `*` result is kept: it is a
   legal PGN result.
8. **Claims.** Listed in the analysis's claim order. Included: every SUPPORTED claim whose subject
   is the target move, plus every claim a segment names (a scope's claims and pending claims
   included). A segment that names a REFUTED or unknown claim raises `ResultError`.
9. **`grade_basis`.** `mate_distance` when both lines mate for the same winner. That is
   `observer.grade`'s condition (both for the mover, or both against it), checked after rank 1.
10. **An inconclusive ply** has `reason` (the judgement's reason), `grade: null` and
    `evaluation: {"grade_basis": null}`.
11. **`summary`** lists every grade and every label kind, zeros included, so a reader needs no
    default.
12. **Check order.** First the game's FEN chain and the ply numbers, then each ply: build, target,
    root, start FEN, grading, profile, engine identity of every search, the move path, the tree's
    FENs and the whole rendering. Each refusal names the ply and the failed check.
13. **Schema strictness.**
    - Every object allows additional properties (G7).
    - The grading block is a `oneOf` of AR-D §2's four rows. The `explicit` and `default` rows
      also require `pool: null`.
    - A `claim` segment requires `claim`. A judgement, label or connective segment has neither
      `claim` nor `claims`.
    - A line ref has one to six moves.
    - An inconclusive ply requires `reason`, `grade: null` and `grade_basis: null`.
14. **The tool.**
    - `explain_game` now returns `(records, document)`. The records feed the unchanged text
      output.
    - `--json` writes `dumps(document)`: compact UTF-8, replacing the indented per-ply records.
    - `bundle.stored` is true only with `--bundles` (written and re-loaded).
    - The fallback warning goes to stderr, so stdout stays the text.

## 3. Tests (AR-D §7)

| Obligation | Test |
| --- | --- |
| 1, 2, 7g (trace = render) | `test_every_corpus_case_projects_and_validates` (12 cases): equal JSON twice, schema-valid, segments rebuild the text, segment claims listed, `trace` text and source equal `render`'s, `build_digest`, label rules, no REFUTED claim |
| 3, 7d | `test_the_fork_segment_names_exactly_the_piece_and_the_move`, `test_the_judgement_and_the_better_move_name_their_moves_and_line`, `test_a_square_ref_carries_its_fen` |
| 7g | `test_a_long_line_lists_only_the_six_plies_the_text_shows` (8 → 6, truncated), the four-ply line above, `test_a_zero_ply_line_holds_the_first_move_it_rendered` |
| 4, 7c | `test_a_black_move_is_scored_from_whites_view`, `test_mate_scores_and_a_slower_mate` (`mate_distance`, loss 0, not BEST; a Black mate is negative), `test_the_grade_basis_follows_the_grade`, `test_an_inconclusive_judgement_has_no_evaluation` |
| 5 | `test_labels`: forced, brilliant (provisional), miss (`miss_p2`); label segments reference the played move |
| 6, 7f | `test_the_grading_block` (four rows), `test_an_invalid_grading_combination_is_rejected_by_the_schema` |
| 7h | `test_an_unknown_field_still_validates` |
| 7 | `tests/test_package_boundaries.py`: two new tests, `results` in `NEW_PACKAGES`; each checked to fail on a planted import |
| 7a, 7b, 7k | `test_a_partial_analysis_keeps_the_whole_game`, `test_the_engine_block_is_the_run_and_a_foreign_identity_is_refused` (also another profile), `test_a_custom_start_numbers_its_plies_from_the_fen` (17…, then 18.) |
| 7e, 7i, 7j | `test_another_game_or_start_is_refused`, `test_a_target_off_by_one_is_refused`, `test_mixed_builds_are_refused`, `test_pre_root_moves_compare_the_root_nodes_fen`, `test_duplicate_plies_two_gradings_and_a_broken_chain_are_refused`, `test_consistently_altered_fens_are_refused`, `test_a_foreign_or_altered_rendering_is_refused` |
| 8 | `tests/tools/test_explain_game.py`: `--json` writes a valid document; the unrated PGN prints the warning once on stderr and one text line per ply |

## 4. Verification
- Suites: see the PR.
- **A real game.** The owner's 829/808 game (chess.com, 600), plies 15–24, with Stockfish 19,
  `--bundles` and `--json`:
  - 10 plies, 16.9 KB, valid against the schema;
  - `monotone_v1`, pool `chesscom`, `clamped` true (an 829 rating is below the conversion's
    anchors);
  - every `bundle.stored` true;
  - the MISS ply's segments: the judgement and the label reference `8.O-O`; the comparison
    references `8.Qe5+` and its six shown plies.

## 5. What follows
The static viewer (one HTML page that loads a `calliope_result_v1` file), then AS-D. AS-D needs
the owner's answers on audience, hosting and frontend stack.
