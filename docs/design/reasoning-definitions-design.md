# Facts and reasoning — DF-D design: one vocabulary of definitions, units and verdicts

Status: **rev. 1 — draft for independent review**.
Date: 2026-10-14. Base: `main @ 14f071d`, after EF-D
([`reasoning-explanation-fixes-design.md`](reasoning-explanation-fixes-design.md)). Inputs:
[`fact-engine-a0-design.md`](fact-engine-a0-design.md) (A0: fact classes, sentinels, versioned
definitions); [`fact-engine-f2-design.md`](fact-engine-f2-design.md),
[`fact-engine-f3-design.md`](fact-engine-f3-design.md), [`fact-engine-f6-design.md`](fact-engine-f6-design.md)
(the DEFINED families); [`reasoning-r0-design.md`](reasoning-r0-design.md) (R0-D §9 verdicts and
scopes, §10 the claim graph, §14 the build); [`application-result-design.md`](application-result-design.md)
(AR-D: `calliope_result_v1`, G7 versioning).

Calliope's data will be read by agents (status and roadmap §5.3). Every value it produces is
correct under a definition, but many definitions live only in code and design prose, some are
special cases, and the result document leaves out what a reader needs to weigh a claim. An agent
that sees `skewers`, `"status": "supported"` or `"loss": 122` cannot tell what was established.
This packet states every definition once, in a form a program can read, and adds to the result
document the units, scopes and relations it lacks. It changes no verdict and no sentence.

## 0. Inventory

Found while checking `g1014` (EF-D §0) and reading the DEFINED families.

| # | Ambiguity | Where | Example |
| --- | --- | --- | --- |
| B2 | Pattern names say more than their definitions | `patterns_v1` (F3-D) | `skewers` is "a slider's ray whose first enemy piece outranks the second" — it never asks whether anything can be won; `sole_defenders` needs two or more defended pieces (an overloaded defender), not one; equal-rank pairs on a ray are in no list; `back_ranks` never asks whether a heavy piece can reach the rank |
| B3 | Legal, geometric and hypothetical facts sit side by side | `pieces`, `squares`, `king`, `exchange` | an absolutely pinned piece counts as an attacker and a defender (flagged); a square behind a checked king on the checking line has no geometric attacker; flight squares are legal for the side to move and geometric for the other; `see_v1` passes the turn for the side to move and is `NotApplicable(IN_CHECK)` in check |
| B4 | One value table is copied | `material.POINTS_V1`, `render.VALUE`, `catalogue.exchange.VALUE` | three copies of P1 N3 B3 R5 Q9; `piece_order_v1` (B = N, K first) is a second scale |
| B5 | Units and perspective are implicit | `calliope_result_v1` | scores are White's view, the grade's loss is in 1/2000 expected points under `quality_v2` and in centipawns under `quality_v1`; `"loss": 122` carries neither |
| B6 | One status, several meanings | the claim graph, `calliope_result_v1.claims` | SUPPORTED with `ASSOCIATED_WITH` (12.Qxe4's fork: the configuration occurred, its `REALIZED` check failed); REFUTED for "false in scope" and for an empirical filter (EA-D E2, EF-D concession) with no rule named; the result lists only supported and rendered claims |
| B7 | The proof scope is one phrase of text | renderer | "Along the engine line" stands for `SPECIFIC_LINE` over one PV of one depth-12 search; "at least N points" for a window that may end before the material settles |
| B8 | The line rules are spread out | `facts.flow`, `reasoning.lines`, `render`, `ReasoningBudget` | settled = two plies after the last change and no capture at the end (`flow`, the 2 is a literal); window 10 plies (`pv_plies`); text 6 plies (`MAX_LINE_PLIES`); "line." form after ply 2 (`IMMEDIATE_PLIES`); `DRAWN` and `STABLE` are incomparable |
| B9 | Thresholds in mixed units, partly outside the build | catalogue, labels, lines, observer | cp: `GAIN_CP_PER_POINT` 80, `DRAW_CP` 10, `quality_v1` bands 40/100/200/400; 1/2000: `ONLY_MOVE_MARGIN` 400, `SOUND_EXPECTED` 1000, `NEAR_BEST` 100, `NOT_BAD` 1000, `WINNING` 1700, `MISS_*` 130/160; points: `OFFER_MIN` 1, `GIVE_UP` −2, `TRADED_NET` −1; permille: `DRAW_WDL` 900; plies: `CHECK_RUN` 2, `VETO_PLIES` 4. Only the label rules' parameters are in `ReasoningBuild`; the rest change the build only through a template rename |
| B10 | Sentinel reasons are free text | facts | `NotApplicable("no same-side ancestor in the tree")`, `NotApplicable("terminal or after a terminal node")`, `NotComputed(f"{family} not computed for {node_id} at rev …")` beside codes (`IN_CHECK`, `IRREGULAR_SEARCH`, `BUDGET`); reasoning's `NOT_COMPUTED(…)` mixes `exchange`, `wdl`, `NO_LINES`, `WDL_UNAVAILABLE` |
| B11 | Which search a number came from is not shown | `calliope_result_v1.evaluation` | the grade reads the comparison search (MultiPV 6 in `g1014`), lines may come from the survey (MultiPV 5); "the 6 moves the engine reported" is the comparison's; depth and profile appear only in `provenance` |

## 1. Decisions

| # | Decision |
| --- | --- |
| D1 | **A definitions registry** (§2): every name the data can carry — family, record field, policy, template, label rule, threshold, reason code, unit — is one entry with a normative one-sentence statement, a kind, a basis, a unit, a perspective, a provenance and its source. Code owns it; a test proves it complete (§7). |
| D2 | **Pattern names stay; their definitions are stated** (§2.3). Stored names (`patterns_v1`, digests) do not change. Each pattern entry carries `configuration_only: true` and its exact condition; agent-facing names are the tools' concern (Q1). |
| D3 | **Every fact field names its basis**: `rule` (legal moves and game rules), `geometric` (attack sets, pins by the ray rule), `hypothetical` (computed under a stated change, such as the turn passed), `engine` (an attested search) (§2.2). |
| D4 | **One value table.** `points_v1` and `piece_order_v1` live in `calliope.facts` (they do today) and every other copy imports them. No value changes. |
| D5 | **Units and perspective are data** (§3): a `units` block in `calliope_result_v1` and in the registry; every number in the document has one. |
| D6 | **One verdict model** (§4): status, scope, relations, causal checks and, for REFUTED, the rule that refuted. The result document gains an optional per-ply `analysis` with every claim of the analysis (Q2). |
| D7 | **One line-settlement definition**, `settle_v1` (§5), with its constants named, in one place. |
| D8 | **Every threshold is a registry entry and part of the build** (§6). |
| D9 | **Closed reason vocabularies** (§6.2) for the fact engine's sentinels and for reasoning's `NOT_COMPUTED(…)`. |
| D10 | **The search behind each number** (§3.2): per ply, the grade's search (kind, MultiPV, depth, profile) and each line's search. |
| D11 | **Additive in `calliope_result_v1`** (AR-D G7). The fact and reasoning builds change only where D8 and D9 change stored bytes (§8). |

## 2. The registry

### 2.1 Entry

```text
Definition = {
  id:          str     # "see_v1", "patterns_v1.skewers", "material_gain_v3", "GAIN_CP_PER_POINT"
  kind:        "rule" | "defined" | "attested" | "policy" | "template" | "label_rule"
             | "threshold" | "reason" | "unit"
  statement:   str     # one English sentence, normative: what holds when the value is present
  basis:       "rule" | "geometric" | "hypothetical" | "engine" | "count" | null
  unit:        unit id | null          # §3.1
  perspective: "white" | "mover" | "side_to_move" | "owner" | null
  value:       int | null              # thresholds only
  provenance:  "rules" | "design" | "measured" | "provisional" | "owner"
  source:      str     # "F6-D §2.1", "EA-D E2", "LV-D §5"
  configuration_only: bool             # patterns: a configuration, not a result (D2)
  depends_on:  [id]                    # definitions it reads
}
```

- `calliope.facts.definitions` holds the fact engine's entries (families, fields, `points_v1`,
  `piece_order_v1`, sentinels, reason codes); `calliope.reasoning.definitions` holds reasoning's
  and re-exports the facts' through the public API (package boundaries unchanged).
- `definitions_v1` is the registry as canonical JSON: `python -m tools.definitions` writes it; the
  digest of that JSON is in the reasoning build (§6).
- A statement says what is established, not what it suggests. A template's statement is its
  predicate and quantifier ("`material_gain_v3`: along `Lp`'s window, the mover's balance from P
  ends at least 1 point up and settled, the gain is not a concession (`concession_v1`) and `Lp`'s
  score is at least 80 cp per point when the event is after the reply").

### 2.2 Basis of the fact fields

| Family | Field | Basis | Note in the statement |
| --- | --- | --- | --- |
| `status` | all | rule | |
| `pieces` | `attacks`, `attackers`, `defenders`, counts, `lowest_attacker_types` | geometric | "an absolutely pinned piece is counted, and flagged in `absolutely_pinned`" |
| `pieces` | `legal_destinations`, `legal_moves`, `legally_capturable_now` | rule | side to move only |
| `squares` | attackers | geometric | |
| `lines` | rays, x-rays, batteries | geometric | |
| `king` | `zone` attackers | geometric | "behind a checked king on the checking line a square shows no attacker" |
| `king` | `flight_squares` | rule (side to move) / geometric (other side) | the record's `kind` says which |
| `pawns` | all | geometric (pawn structure) | DEFINED, `pawns_v1` |
| `patterns`, `pattern_delta` | all | geometric | `configuration_only` |
| `delta`, `same_side_delta` | per component | as the component's family | |
| `exchange` | `gain` | rule, or hypothetical (`hypothetical: true`: the turn passed) | legal captures, least valuable first, either side may stop |
| `exchange` | `safe_moves` | rule | |
| searches | lines, scores, WDL | engine | depth, MultiPV, profile in the search record |

### 2.3 Pattern statements (D2)

| Entry | Statement |
| --- | --- |
| `patterns_v1.multi_target_attacks` | A piece attacks two or more enemy pieces (geometric); each target's rank against the actor under `piece_order_v1`. Defences and values are not considered. |
| `patterns_v1.relative_pins` | On a slider's ray the first two occupants are enemy pieces and the farther one outranks the nearer (`piece_order_v1`), the farther not a king. |
| `patterns_v1.skewers` | On a slider's ray the first two occupants are enemy pieces and the nearer one outranks the farther. |
| `patterns_v1.discovery_lines` | On a slider's ray the first occupant is the slider's own piece and the second an enemy piece. |
| `patterns_v1.sole_defenders` | One piece is the only defender of two or more attacked pieces (kings excluded). |
| `patterns_v1.back_ranks` | A king on its first rank whose three forward squares are each own-occupied or enemy-attacked, at least one own-occupied. Access by enemy pieces to the rank is not considered. |
| (not recorded) | Two enemy pieces of equal rank on a ray; a single sole defender of one piece. |

Whether a configuration works is a reasoning claim (`fork_v2`, `pin_v2`, `skewer_v2`,
`discovery_v2`, EF-D), and only a claim with a passed `REALIZED` check explains a result.

## 3. Units, perspective and searches

### 3.1 Units

| Unit id | Meaning |
| --- | --- |
| `cp_white` | centipawns, White's view (`calliope_result_v1` scores, AR-D G5) |
| `cp_mover` | centipawns, the mover's view (thresholds such as `GAIN_CP_PER_POINT`) |
| `mate_white` | moves to mate, positive when White mates |
| `expected_2000` | expected points in 1/2000 of a game (1000 = a draw), the mover's view |
| `points_v1` | material points |
| `permille` | WDL shares |
| `plies` | half-moves |

`calliope_result_v1` gains, at the top level:

```text
"units": {"score": "cp_white | mate_white", "loss": "expected_2000" | "cp_mover",
          "expected": "expected_2000", "material": "points_v1"}
```

`loss` is `expected_2000` under `quality_v2` and `cp_mover` under `quality_v1` (R1, Q1). Each ply's
`evaluation` gains `expected` (`played`, `best`, in `expected_2000`, when the policy has a curve).

### 3.2 Searches

Each ply's `evaluation` gains `search`: `{"kind": "comparison" | "survey", "multipv", "depth",
"profile"}` of the search S the grade read (R0-D R0-I1). Every scope in §4 names its searches the
same way.

## 4. The verdict model

### 4.1 Meanings (normative; each status is a registry entry)

| Status | Means | Does not mean |
| --- | --- | --- |
| SUPPORTED | the template's predicate holds within its scope (§4.2) | that it caused the result: only a relation `EXPLAINS` or `CAUSES` whose causal check (`REALIZED` / `COUNTERFACTUAL`) passed says that |
| REFUTED | the predicate is false within the scope, or a named rule of the template refuses it (`refuted_by`) | that the opposite is proven outside the scope |
| INCONCLUSIVE | the evidence could not decide; `reason` from the closed set (R0-D §9.2, EF-D `IN_CHECK`, §6.2) | anything about the predicate |
| NEEDS_EVIDENCE | never final (closed as INCONCLUSIVE at the last round) | — |

`refuted_by` is new in the verdict: the id of the rule when a filter refused the claim
(`material_gain.score_check` for EA-D E2, `concession_v1`, …), absent when the predicate itself is
false. It is an optional field of `Verdict` and of the stored graph (§8).

### 4.2 Scope

The scope of a claim is its `ProofScope` (R0-D §9): `basis` (exact / engine), `at`, `quantifier`
(`specific_line`, `persistence`, `exists_response`, `all_responses`, `exists_alternative`,
`all_alternatives`, `selected_alternatives`), `population`, `witnesses`, `searches`, `depth`,
`multipv`, `plies`, `line_end`, `policies`. Each quantifier has a registry statement, for example
`specific_line`: "the predicate holds along this one engine line over the stated plies; other
replies are not considered".

### 4.3 In the result document (Q2)

Each ply gains an optional `analysis`:

```text
"analysis": {
  "claims": [{
    "id", "template", "role", "status", "reason"?, "refuted_by"?,
    "scope": {"basis", "quantifier", "population", "at": Ref, "searches": [SearchRef],
              "depth", "multipv", "plies", "line_end", "policies": [id]},
    "relations": [{"kind", "target": claim id}],
    "causal": [{"kind": "realized" | "counterfactual", "passed"}],
    "findings": [Finding]          # §4.4
  }],
  "judgement": {"status", "reason"?, "search": SearchRef, "played": LineScore,
                "best": LineScore, "alternatives": [LineScore]}
}
```

- Every claim of the analysis is listed, in the graph's order, whatever its status; `claims` (AR-D)
  keeps its meaning and contents.
- `analysis` is written when the request asks for it (`tools/explain_game --analysis`, the
  server's `detail` field); the viewer does not need it. Size is measured in DF1 (§7).

### 4.4 Findings as JSON

A finding is its dataclass with typed fields projected by one rule: a `PieceRef` / `MoveRef` /
`SquareRef` / `SearchRef` / `LineSegment` becomes the AR-D ref of the same kind (with its FEN), an
enum its value, a `MaterialAmount` `{"points", "unit": "points_v1"}`, a score with its unit. Each
finding type has a registry entry whose statement says what its fields mean.

## 5. `settle_v1` — one line-settlement definition

| Name | Value | Statement |
| --- | --- | --- |
| `SETTLE_PLIES` | 2 | a path's material is settled when at least this many plies follow its last capture or promotion and the last ply is not a capture (`facts.flow`, today a literal) |
| `pv_plies` (`ReasoningBudget`) | 10 | a line's window from P |
| `MAX_LINE_PLIES` | 6 | plies of a line quoted in text |
| `IMMEDIATE_PLIES` | 2 | an event at or before this ply is the move's own ("it wins …"), later ones the line's |
| outcome order | — | `MATE(m)` > `STABLE(Δ)` > `MATE(o)`; `DRAWN` above `MATE(o)`, below `MATE(m)`, incomparable with `STABLE` (R2-D §1.3) |

`flow`'s literal becomes the named constant; the values do not change.

## 6. Thresholds and reasons

### 6.1 Thresholds (D8)

Every module-level numeric constant read by a template, a label rule, the observer, the planner
or the renderer is a registry entry with `kind: threshold`, its unit, value, provenance and source
(the B9 list, plus the `quality_v1` bands and the curve table names). `ReasoningBuild` gains the
registry's digest, so changing any threshold changes the build without a template rename.
`label_parameters` stays (it is part of today's build bytes) and is checked against the registry.

### 6.2 Reasons (D9)

- **Fact engine.** `NotApplicable` and `NotComputed` take a code from a closed set, each a registry
  entry: today's codes (`IN_CHECK`, `NOT_EXPOSED`, `IRREGULAR_SEARCH`, `COMPARISON_NOT_REQUESTED`,
  `PARENT_NOT_SEARCHED`, `BUDGET`, `tier`→`TIER`, `not requested`→`NOT_REQUESTED`) and new codes for
  the free texts: `NO_SAME_SIDE_ANCESTOR`, `ROOT_HAS_NO_MOVE`, `TERMINAL`, `FAMILY_NOT_SELECTED`,
  `NOT_COMPUTED_AT_NODE`. The node, revision and family move to optional fields of the sentinel
  (`detail`), which `TreeView.fact` fills and the encoding does not store.
- **Reasoning.** `NOT_COMPUTED(<x>)` takes `<x>` from a closed set: family names
  (`exchange`, `move`, `status`, …) and `WDL`, `LINES`; `NO_LINES` → `LINES`,
  `WDL_UNAVAILABLE` and `wdl` → `WDL`.

## 7. Test obligations (packet DF1)

1. **Completeness.** Every family field (by the closed type registry, F5-D), template, policy,
   label rule, finding type, reason code, unit and module-level numeric constant of the listed
   modules has an entry; every entry names something that exists. A new constant without an entry
   fails the test.
2. **One value table.** No module outside `calliope.facts` defines a piece-value mapping (static).
3. **Units.** Every number in a `calliope_result_v1` of the corpus is covered by `units` or by a
   field whose schema names its unit.
4. **Analysis.** For the corpus and `g1014`: every claim of each analysis appears in `analysis`
   once; statuses, scopes and relations equal the claim graph's; REFUTED claims of EA-D E2 and
   EF-D §3 carry `refuted_by`; `analysis` absent unless requested; the schema accepts both.
5. **Reasons.** Every sentinel the fuzz (F1–F6 suites) produces has a code from the set; every
   INCONCLUSIVE reason of the corpus is in the closed set.
6. **Builds.** The registry digest is in `ReasoningBuild`; changing one threshold changes the build;
   the fact build changes with the reason codes (§8) and nothing else.
7. **No behaviour change.** Every verdict, plan and sentence of the corpus and the three games is
   unchanged against EF1's build (only build identities differ).
8. **Size.** `analysis` adds at most a stated factor to a 75-ply document; DF1 records it.

## 8. Builds and stored data

| Change | Effect |
| --- | --- |
| Reason codes in stored sentinels (§6.2) | the fact encoding's bytes change for the records that hold a sentinel (DF1 lists them; the sentinels `TreeView.fact` returns for a missing record are not stored): a new fact build (`facts_build_version`, F5-D); saved trees of the old build are rebuilt, not loaded |
| `refuted_by` in verdicts (§4.1) | stored claim graphs change: the reasoning build changes |
| Registry digest in `ReasoningBuild` (§6.1) | the reasoning build changes |
| `calliope_result_v1` fields | additive (AR-D G7); the schema gains them as optional |

The server's cache misses once after DF1, as after EF1.

## 9. Owner questions

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Rename the patterns in a `patterns_v2` (for example `line_pair_front_outranks`) or keep the names with the statements of §2.3? | Keep; the agent tools may present other names |
| Q2 | `analysis` on request, or always? | On request; the viewer does not read it and it multiplies the size |
| Q3 | `refuted_by` for every refusing rule, or only for the filters (E2, concession)? | Only for rules that are not the predicate itself |

## 10. Not in this packet

- The agent tools and the MCP server, their names and their projection of the registry.
- Threat facts (`opponent_view`, A0 §14) and a played-against-alternative view.
- Line continuation (EV-D §0.4).

## 11. Delivery

| Packet | Content | Gate |
| --- | --- | --- |
| DF-D (this) | the registry, units, verdict model, settlement, thresholds, reasons | independent review READY |
| DF1 | §2–§6 in code, `tools/definitions`, the result fields, the tests of §7 | READY |

DF1 follows EF1, so that the registry starts with EF-D's definitions.
