# Agent — packet AG5 implementation: guidance an agent reaches by itself

Status: **rev. 1 — for independent review**. Date: 2026-10-16. Design:
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
| Build: `guidance: agent_guidance_v1`, the other keys unchanged; the pin of the instructions and every description | `test_guidance.py::test_the_guidance_is_in_the_agent_build_and_pinned` |
| The listing of tools, prompts and resources | `test_server.py::test_the_tools_prompts_and_resources_are_listed` |
| Host integration: the trial of AG5-D §8 | §4 |

## 4. Results

(Filled in after the runs.)
