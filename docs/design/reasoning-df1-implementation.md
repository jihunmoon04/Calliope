# Facts and reasoning — packet DF1 implementation: definitions, units and the verdict model

Status: **rev. 2 — independent review NOT_READY (B1–B3) applied (§5); re-review READY**.
Date: 2026-10-15. Design: [`reasoning-definitions-design.md`](reasoning-definitions-design.md)
rev. 6 (DF-D, final re-review READY_WITH_CORRECTIONS applied). Base: `main @ 73b80da` (after EF1).

## 1. Scope delivered

| Place | Change |
| --- | --- |
| `facts/definitions.py` (new) | `Definition` (DF-D §2.1) and the fact engine's entries: the 14 families; every field of every record type of the closed type registry (the families' records and every record they hold, shared ones per family) and each enum with its values (280 entries); `points_v1`, `piece_order_v1`, `settle_v1`, `SETTLE_PLIES`; the fact classes; the six sentinels; the 15 reason codes. `as_json`, `digest`. Exported through `calliope.facts` (`FACT_DEFINITIONS`, `Definition`, `definitions_json`, `definitions_digest`) |
| `facts/values.py` | `FACT_REASONS`, the closed set (DF-D §6.2) |
| `facts/tree.py`, `facts/engine.py`, `facts/flow.py` | the free-text sentinels become codes: `FAMILY_NOT_SELECTED`, `ROOT_HAS_NO_MOVE`, `NOT_REQUESTED` (was `not requested`), `TIER` (was `tier`), `NOT_COMPUTED_AT_NODE`, `TERMINAL`, `NO_SAME_SIDE_ANCESTOR` (stored by `same_side_delta`), `NOT_APPLICABLE_RECORD` |
| `facts/storage.py` | `FACTS_BUILD_VERSION = "3"`: the stored `NO_SAME_SIDE_ANCESTOR` changes record bytes (DF-D §8) |
| `facts/flow.py` | `SETTLE_PLIES = 2`, the literal named (`settle_v1`, DF-D §5) |
| `facts/families/material.py` | `POINTS_V1_BY_TYPE`: the one value table by `PieceType` (D4) |
| `reasoning/definitions.py` (new) | reasoning's entries — units, statuses, quantifiers, populations, bases, the three causal checks, relation kinds, policies, label rules, the 29 templates, the filter `material_gain.score_check` and the material templates' rules, the finding types, the observations, the thresholds (31, values read from their modules) and the reason codes (DF-D §6.2's table) — with the fact engine's re-exported: `DEFINITIONS` (500), `REGISTRY_DIGEST`, `current_digest()` |
| `reasoning/build.py` | `ReasoningBuild.definitions`: the registry digest with the thresholds the modules hold when the build is made (§6.1) |
| `reasoning/verification.py`, `catalogue/base.py`, `catalogue/material.py` | `Verdict.refuted_by` (only with REFUTED); EA-D's score check refuses with `material_gain.score_check` |
| `reasoning/render/`, `catalogue/exchange.py`, `catalogue/comparison.py` | the three copied value tables removed; `POINTS_V1_BY_TYPE` read instead |
| `reasoning/__init__.py` | exports `FINDING_KINDS`, `CausalCheck` (for `calliope.results`) |
| `results/analysis.py` (new) | the projection of DF-D §4.3–§4.4 |
| `results/document.py` | top-level `units`; `evaluation.expected` and `evaluation.search`; `game_result(…, analysis=True)` adds each ply's `analysis` |
| `results/schema/calliope_result_v1.json` | the new fields, optional (AR-D G7): `units`, `Evaluation.expected`, `.search`, `Ply.analysis` with `Analysis`, `Judgement` (a union on `status`), `AClaim`, `AScope`, `Target`, `Value`, `Position`, `PositionKeyRef`, `Wdl`, … and one `Findings/<type>` per finding type, built from the dataclass fields |
| `server/jobs.py`, `server/pipeline.py`, `server/web.py` | the POST's `detail` (a boolean) asks for `analysis`; it enters the job id only when true, is kept in `job.json` and survives a restart; `result_matches(…, detail)` requires an `analysis` on every ply exactly when the job asked for it; a failed job posted again takes the posted `detail` |
| `tools/explain_game` | `--analysis` (with `--json`) |
| `tools/definitions` (new) | `python -m tools.definitions [OUT]`: `definitions_v1` JSON |

## 2. Choices and departures (for the reviewer)

- **Every record type.** (Rev. 1 stated only the families' main records; review B1.) The fields
  of every record type a family declares are entries, `<family>.<Record>.<field>`; a record two
  families share (`Relation`, `ByColor`, `FileFacts`, `SetChange`, `PiecePair`) is stated once and
  entered under each; an enum is one entry whose statement names every value.
- **No `detail` field on the sentinels.** DF-D §6.2 moved the node and revision of two runtime
  messages to an unstored `detail`. The fact encoding stores every dataclass field, and nothing
  reads those messages, so they became codes and the detail was dropped.
- **Template rules.** Every template entry states its predicate and conditions; the filter that
  `refuted_by` names (`material_gain.score_check`) and the numbered rules of the two material
  templates are entries of their own (`material_loss_v2.rule1` …). Other templates' rules are in
  their statements, not one entry per rule.
- **Kinds and units beyond DF-D §2.1.** Kinds `family`, `field`, `sentinel`, `template_rule`,
  `check`, `status`, `quantifier`, `relation`, `finding`; units `moves` and `count` (a mate in n,
  the number of replies). Unit entries are `unit.<id>`, so `points_v1` stays the value table's id
  (scopes name it as a policy).
- **The digest is taken when the build is made.** `current_digest()` reads the threshold values
  the modules hold at that moment, so a changed threshold changes the build (test 6, and R4's
  build-mismatch test that changes `MISS_LOSS`); `REGISTRY_DIGEST` is the import-time value.
- **Reasoning reason codes are unchanged** (DF-D §6.2): `wdl` and `WDL_UNAVAILABLE` are two
  entries with one meaning.

## 3. Test obligations (DF-D §7)

| # | Test |
| --- | --- |
| 1 | `tests/test_definitions.py`: every family, every field of every record type of `FactFamily.record_types`, every enum value; every template, policy (the build's and those scopes name), label rule, finding type, status, quantifier, population, basis, relation kind, check kind; units and dependencies name entries; every module-level numeric constant of `lines`, `labels`, `planner`, `observer`, `render`, `catalogue/*` is a threshold; threshold values equal the code's and `label_parameters`; `tools.definitions` writes the registry |
| 2 | no module outside `calliope.facts` defines piece values (static) |
| 3 | `tests/results/test_analysis.py`: `units` is the document's; the evaluation's fields; `analysis` absent unless asked |
| 4 | for every corpus case: the schema (shipped validator and `jsonschema`), no node, search or piece id in the text, claims in the graph's order with status, reason, `refuted_by`, scope, effective scopes (element by element), evidence (length and kinds), checks, findings; relations decoded back to the graph's, observation and judgement targets included; judgements and observations; every `Position` replays from the root; the score-check refusal carries `refuted_by`; an inconclusive judgement validates; a MISS case lists two judgements; an unknown type is refused; the schema's finding definitions match the dataclasses |
| 5 | every fact sentinel literal is a code; every sentinel of a played tree with `exchange` is a code; every reasoning `NOT_COMPUTED(…)` literal is in the table; the refusal types are listed |
| 6 | the registry digest is in the build; a changed threshold changes it and the build digest; the fact build is "3" |
| 7 | the corpus texts are unchanged (the corpus suite); the three games re-run (§4) |
| 8 | the size factor over the corpus, asserted below 12 (§4) |

Server: `detail` is part of the id only when true, gives every ply its `analysis`, survives a
restart; a non-boolean `detail` is a 400; a plain result in a detail job's folder is not accepted
(the job resumes); a detail job whose `job.json` lost `detail` is DAMAGED at restart and, posted
again, runs with `detail` (B2, B3). Tool: `explain_game(…, detail=True)`. Analysis: every
evidence reference, scope search and population move decodes to the graph's own reference.

## 4. Runs

- **The suite, rev. 2** (after B1–B3), with Stockfish 19, alone: **1189 passed, 0 failed**
  (16 min 12 s).
- **The suite, rev. 1**, with Stockfish 19, alone: 1168 passed and 1 failed — the fact build guard
  (`test_build_version_guard`), which asks for a row when `FACTS_BUILD_VERSION` changes; the row for
  "3" is added (`735181…`), and the guard test passes. `ruff check` and `ruff format --check`
  clean.
- **No behaviour change (test 7).** The three games of EF1 §5 re-run under DF1 and compared with
  EF1 rev. 2's documents: every ply's text, grade, label, claims (template and status) and
  evaluation (scores, loss, grade basis) are identical (75, 101 and 78 plies); the only differences
  are the build digest and the new fields (`units`, `evaluation.expected`, `evaluation.search`).
- **Size (test 8).** `g1014` with `--analysis`: 2.03 MB against 129 KB without — a factor of 15.7;
  a ply's `analysis` is 14–52 KB (median 26 KB). Over the corpus the largest factor is lower; the
  test bounds it at 20. The shipped validator checks the 2 MB document in 1.3 s with no error and
  no internal identifier in it. `analysis` stays on request (Q2).

## 5. Review dispositions (rev. 1 `608ded4`, independent review: NOT_READY)

The review passed the build digest, `refuted_by`, the one value table, the sentinel codes, the
projection, the schema and `--analysis`.

| Finding | Disposition |
| --- | --- |
| **B1** the registry and its test covered chosen record types only (`ExchangeFacts.pieces`, `PiecesFacts.pieces` missing) | Accepted. Every field of every record type of `FactFamily.record_types` and every enum value is an entry (155 added: 322 fact entries, 500 in all); test 1 walks the closed type registry itself (§1, §2). |
| **B2** `result_matches` did not check `analysis`, so a plain result could pass as a detail job's | Accepted. `result_matches(…, detail)` requires an `analysis` on every ply exactly when the job has `detail`; restart and the worker both pass the job's `detail`. Test: a plain result copied into a detail job's folder resumes the job. |
| **B3** a damaged detail job posted again kept `detail = false` | Accepted. Posting a failed job again sets `job.detail` from the post (the id names it) and writes it to `job.json`. Test: the whole sequence (lost `detail` → DAMAGED → posted again → runs with `analysis`). |
| (evidence) the suite after the guard row was not re-run | Re-run: §4. |
| (recommendation) references compared by length and kind only | Applied: a test decodes every evidence reference (fact targets by path or EPD, searches by index and rank, line segments), scope searches and population moves to the graph's. |
