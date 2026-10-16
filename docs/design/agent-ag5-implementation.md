# Agent — packet AG5 implementation: guidance an agent reaches by itself

Status: **rev. 1 — independent review (`d68f45d`) READY_FOR_MERGE; notes N1–N3 recorded, N2 applied (§5)**. Date: 2026-10-16. Design:
[`agent-ag5-design.md`](agent-ag5-design.md) rev. 2 with notes N3, N4 (AG5-D: G1–G9, §2–§9). Base:
`main @ b20bdab` (AG5-D merged, PR #104).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `agent/server.py` | `INSTRUCTIONS` as AG5-D §3 (1,041 characters); the guide resources `calliope://guides/commentary_ko` and `calliope://guides/check_ko` (`text/markdown`, Korean titles, the descriptions of §4, annotations `audience: ["assistant"]` with priority 1.0 and 0.8); `ply`'s description starts with where a ply starts and names the method's URI; `submit_commentary`'s description (`SUBMIT_COMMENTARY`) lists the kinds from `propositions.KINDS`, says what `proposition.<kind>` is, gives the sentence shape and names both guides; `definitions`' description names its kinds and how a query of several words and an unknown kind answer |
| `agent/build.py` | `guide(name)`: a prompt file formatted with `<game>` / `<ply>`; `agent_build()` gains `guidance`; `find_definitions`: a query of several words matches every word in the id, the statement and the field names; an unknown kind adds `kinds` |
| `agent/definitions.py` | `GUIDANCE_VERSION = "agent_guidance_v1"` |
| `agent/propositions.py` | a kind `proposition.<kind>` for a kind there is is refused with "write `<kind>`" (§5.3) |
| `tests/agent/test_guidance.py` (new) | AG5-D §9 (§3 below) |
| `tests/agent/test_server.py` | the listed resources include the two guides |

The prompt files, the registries (`AGENT_DIGEST`, `REGISTRY_DIGEST`), tool names and arguments
(`agent_tools_v3`) and every tool answer but `definitions`' `kinds` are unchanged.

## 2. Choices and departures (for the reviewer)

- **The sentence shape in `submit_commentary`'s description.** §5.2 lists the kinds, the
  definition ids and the guides; the description also gives a sentence as `{"text", "class":
  "sourced" | "interpretation", "cites": [proposition ids]}`. The trial's agent wrote
  `"propositions"` for `cites` (AG5-D §0, Run 11), the same kind of guess as the kinds, and the
  old description said only "every sentence cites propositions".
- **The pin covers every tool's description**, not only the three §5.2 changes: §6 says the
  version covers "the tool descriptions", and a pin on all of them is as cheap. The digest is
  sha-256 of the instructions and each tool's name and description, sorted by name, as
  `tools/list` gives them.
- **A one-word query keeps today's matching** (the id and the statement), so every earlier answer
  of a one-word query is unchanged; only a query of several words reads the field names (N3).
- **`kinds` is added only when the kind is not one there is** (a known kind with no match after a
  query has no `kinds`); it is every kind in both registries, sorted (26).
- **Titles in Korean** for the guides ("Calliope 해설 작성 지침", "Calliope 해설 점검 목록"), as the
  viewer resource's title; the descriptions are §4's English.

## 3. Test obligations (AG5-D §9)

| Obligation | Where |
| --- | --- |
| Instructions: `initialize` carries the text; it names the tools, the kinds and `proposition.judgement`; the URIs it names are the two guides and the glossary, and all are listed; the prompts named as the user's | `test_guidance.py::test_the_instructions_give_the_order_the_kinds_and_where_the_method_is` |
| Resources: both listed with `text/markdown` and their annotations; each read equals `prompts/get` with `<game>` / `<ply>` character for character, and `guide()`; no escaped brace left; the prompt file unchanged | `test_guidance.py::test_the_guides_are_listed_for_the_model_and_are_the_prompts_text` |
| Descriptions: `ply` starts with where a ply starts and names the guide; `submit_commentary`'s kinds equal `KINDS`, it says what `proposition.<kind>` is, gives `cites`, names both guides and no longer points to `calliope://definitions`; `definitions` says how an unknown kind answers | `test_guidance.py::test_the_descriptions_carry_the_essentials` |
| Refusal: `proposition.judgement`, `proposition.engine_line` say what to write; `foo`, `proposition.foo`, `proposition` keep today's message; the field and `expected` as today | `test_guidance.py::test_a_prefixed_kind_is_refused_saying_what_to_write` |
| `definitions`: `"proposition move grade"` finds `proposition.judgement` (by its fields) and only entries with every word; a subset of the one-word answer; the trial's `"calliope_commentary calliope_check"` finds nothing (no entry holds both) | `test_guidance.py::test_a_query_of_several_words_finds_the_entries_with_every_word` |
| A one-word query as before (id and statement only; `best_move`, a field name, only in a query of several words); no `kinds` | `test_guidance.py::test_a_one_word_query_answers_as_before` |
| An unknown kind answers the 26 kinds sorted and an empty list; a known kind (`proposition`, 15) has no `kinds` | `test_guidance.py::test_an_unknown_kind_answers_with_the_kinds_there_are` |
| Build: `guidance: agent_guidance_v1`, the other keys unchanged; the pin of the instructions, every description and nine searches over a fixed registry (review N2) | `test_guidance.py::test_the_guidance_is_in_the_agent_build_and_pinned` |
| The listing of tools, prompts and resources | `test_server.py::test_the_tools_prompts_and_resources_are_listed` |
| Host integration: the trial of AG5-D §8 | §4 |

## 4. Results

### 4.1 Tests

- The whole suite without Stockfish, on the working tree before the commit: **1414 passed, 28
  skipped** (the Stockfish tests), 19.7 min. With Stockfish 19 on the committed code: §4.3.
- `ruff check` and `ruff format --check` on `src`, `tests` and `tools`: clean.
- Run from a worktree, the suite must have the worktree's `src` first on the path
  (`PYTHONPATH=$PWD/src:$PWD`): the development venv holds an editable install of the main
  checkout, which pytest would otherwise import.

### 4.2 The trial again (AG5-D §8)

HIMARI v3 `main @ 53d72c3` (its trial fixes #44, #45 merged), Calliope at this packet's commit,
stdio in HIMARI's server sandbox, one shared process, a fresh conversation and a fresh data
directory per turn, model `openai/gpt-6-luna`, the request of AG5-D §0. Three turns:

| Turn | Runs | Time | Input tokens (cached) | Output | Calls | `definitions` | Guide read in Run | Submitted in Run | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| §0 (before) | 16 (limit) | 89 s | 425,673 (2,125 a Run) | 3,881 | 24 | 9 | — (guessed 5 URIs) | 11, 14 (unknown outcome, a HIMARI fault) | no commentary |
| 1 | 7 | 42 s | 132,332 (16,146) | 2,850 | 10 | 5 | 1 | 6 | accepted, stored |
| 2 | 9 | 41 s | 191,622 (24,409) | 2,603 | 15 | 8 | 2 | 8 | accepted, stored |
| 3 | 5 | 25 s | 80,809 (13,645) | 1,642 | 8 | 3 | 1 | 4 | accepted, stored |

Against the targets of AG5-D §8:

| Measure | Result |
| --- | --- |
| Guessed URIs read, prompts looked for | **0** in every turn |
| The method | `calliope://guides/commentary_ko` and `check_ko` read before the first submission in every turn (turn 2 listed the resources first, with the `cursor: ""` HIMARI now takes) |
| Ply analysed | 10 (5...h6) in every turn |
| Propositions | kinds as submitted (`judgement`) in every turn; every first submission accepted |
| Commentary | accepted, stored and shown by `commentary` in every turn |
| Runs | 7, 9, 5: turns 1 and 3 within 8, turn 2 not |
| Cost | 55–81 % fewer input tokens than §0 (69, 55, 81 %); not all AG5's (review N3: HIMARI's trial fixes changed between §0 and these turns) |
| Evidence | **not met in substance**: see below |

**The commentaries are correct and shallow.** Every turn cites one proposition, the subject's
judgement, and says its grade and the better move:

- turn 1: "5...h6는 부정확수로 평가됐습니다. 엔진이 제시한 더 나은 선택은 5...Bc5였습니다."
- turn 2: "5...h6는 부정확한 수입니다." / "더 나은 선택은 5...Bc5였습니다."
- turn 3: "5...h6는 부정확수입니다." / "더 나은 선택은 5...Bc5로 비숍을 전개하는 수였습니다."

None answers "why" (the guide's step 3: by comparison), although `ply` served the claims for it;
no turn called `facts`, `explore` or `judge_move`. Nothing in them is unsupported but turn 3's
"비숍을 전개하는" — a description of the move in a `sourced` sentence, which the wording rules
(AG-D §6) say belongs in an `interpretation`. So AG5 removed the failure of §0 — the agent now
reaches the method and submits what the server accepts — and shows the next one: an agent that
can stop at the judgement does. Making a commentary explain is a question of what the server
asks of a commentary (for example, a cause or comparison proposition besides the judgement), for
the owner to decide in a later packet; it is not in AG5-D.

Other observations, for HIMARI (the host): the first `ply` answer adds about 18,000 input tokens
to every later Run (the full claim graph, AG-D §3), and the provider's cache held only the first
2,691 tokens of each request (the system message), not the growing history — HIMARI's to measure
with its run limit and cost work.

### 4.3 The whole suite with Stockfish

The whole suite with Stockfish 19 (`CALLIOPE_STOCKFISH_PATH` set), in one run on the committed code
(`43c9a8b`; only this document changed after it): **1442 passed** (20.7 min), none failed or
skipped.

## 5. Review dispositions — rev. 1 (`d68f45d`), independent review: READY_FOR_MERGE

AG5's scope passed: AG5-D implemented, the guides served, the kind errors gone, every commentary
submitted and stored; no defect that blocks the merge. Gate "a commentary that explains": NOT_READY,
outside AG5's scope.

| # | Note | Disposition |
| --- | --- | --- |
| N1 | The commentaries cite the judgement only; turn 3 put a description in a `sourced` sentence. Not a regression: the limit of `SOURCE_VERIFIED`, shown by the trial. AG5 is not the acceptance of a finished commentary agent | Recorded (§4.2). The next packet makes the agent use `ply`'s claims to say why: rather than requiring one more proposition, check whether the evidence served can explain the judgement and, where it cannot, have the commentary say so. For the owner to open. |
| N2 | The pin covered the instructions and descriptions, not the search | Applied: the pin also covers what `definitions` answers for nine queries (several words through field names, one word, case, kind with query, a known and an unknown kind, ids with a missing one) over a fixed registry, so a change to the search's behaviour moves it and a change to the registries does not. |
| N3 | The fall in input tokens is not all AG5's: HIMARI's fixes also changed | Recorded in §4.2. Measuring AG5 alone needs the same HIMARI version with Calliope before and after; the turns here show the integration works. |

