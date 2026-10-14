# Facts and reasoning — DF-D design: one vocabulary of definitions, units and verdicts

Status: **rev. 3 — review NOT_READY (B1–B4) applied; re-review NOT_READY (B5–B7) applied (§13)**.
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
| B5 | Units and perspective are implicit | `calliope_result_v1` | scores are White's view; the grade's loss is in 1/2000 expected points, the mover's, under both policies (`quality_v1` reads the WDL, `quality_v2` the curve; `observer.grade`: `loss = max(0, best.expected − played.expected)`); `"loss": 122` carries no unit |
| B6 | One status, several meanings | the claim graph, `calliope_result_v1.claims` | SUPPORTED with `ASSOCIATED_WITH` (12.Qxe4's fork: the configuration occurred, its `REALIZED` check failed); SUPPORTED with a failed `ATTRIBUTED` check (EF-D: the line's material, a concession of the loser); REFUTED for "false in scope" and for an empirical filter (EA-D E2) with no rule named; the result lists only supported and rendered claims |
| B7 | The proof scope is one phrase of text | renderer | "Along the engine line" stands for `SPECIFIC_LINE` over one PV of one depth-12 search; "at least N points" for a window that may end before the material settles |
| B8 | The line rules are spread out | `facts.flow`, `reasoning.lines`, `render`, `ReasoningBudget` | settled = two plies after the last change and no capture at the end (`flow`, the 2 is a literal); window 10 plies (`pv_plies`); text 6 plies (`MAX_LINE_PLIES`); "line." form after ply 2 (`IMMEDIATE_PLIES`); `DRAWN` and `STABLE` are incomparable |
| B9 | Thresholds in mixed units, partly outside the build | catalogue, labels, lines, observer | cp: `GAIN_CP_PER_POINT` 80, `DRAW_CP` 10; 1/2000: the grade bands 40/100/200/400 (`observer.BANDS`, both policies), `ONLY_MOVE_MARGIN` 400, `SOUND_EXPECTED` 1000, `NEAR_BEST` 100, `NOT_BAD` 1000, `WINNING` 1700, `MISS_*` 130/160; points: `OFFER_MIN` 1, `GIVE_UP` −2, `TRADED_NET` −1; permille: `DRAW_WDL` 900; plies: `CHECK_RUN` 2, `VETO_PLIES` 4. Only the label rules' parameters are in `ReasoningBuild`; the rest change the build only through a template rename |
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
  predicate and quantifier, and the statements of its checks are their own entries:
  "`material_gain_v3`: along `Lp`'s window the mover's balance from P ends at least 1 point up and
  settled, and `Lp`'s score is at least 80 cp per point when the event is after the reply
  (`material_gain.score_check`)"; "`ATTRIBUTED` (`concession_v1`): the lost piece was exposed
  before the loser's own choices after the reply, or the loser's exposing move was forced (only
  legal move, or every other move allows mate in one); failed means not shown to be forced by the
  move, not that the loser could keep the material". A concession leaves the material claim
  SUPPORTED (EF-D §3.4).

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
"units": {"score": "cp_white | mate_white", "loss": "expected_2000",
          "expected": "expected_2000", "material": "points_v1"}
```

`loss` is `expected_2000` under both policies; they differ only in how `expected` is computed
(`quality_v1` from the WDL, `quality_v2` from the curve; R1, Q1). Each ply's `evaluation` gains
`expected` (`played`, `best`, in `expected_2000`) whenever the judgement is decided, under either
policy.

### 3.2 Searches

Each ply's `evaluation` gains `search`: `{"kind": "comparison" | "survey", "multipv", "depth",
"profile"}` of the search S the grade read (R0-D R0-I1). Every scope in §4 names its searches the
same way.

## 4. The verdict model

### 4.1 Meanings (normative; each status is a registry entry)

| Status | Means | Does not mean |
| --- | --- | --- |
| SUPPORTED | the template's predicate holds within its scope (§4.2) | that it caused the result: only a relation `EXPLAINS` or `CAUSES` whose causal check (`REALIZED` / `COUNTERFACTUAL`) passed says that; for a material consequence, that the move brought it about: the `ATTRIBUTED` check says that (EF-D §3) |
| REFUTED | the predicate is false within the scope, or a named rule of the template refuses it (`refuted_by`) | that the opposite is proven outside the scope |
| INCONCLUSIVE | the evidence could not decide; `reason` from the closed set (R0-D §9.2, EF-D `IN_CHECK`, §6.2) | anything about the predicate |
| NEEDS_EVIDENCE | never final (closed as INCONCLUSIVE at the last round) | — |

`refuted_by` is new in the verdict: the id of the rule when a filter refused the claim
(`material_gain.score_check` for EA-D E2, …), absent when the predicate itself is false (Q3). It is
an optional field of `Verdict` and of the stored graph (§8). Every rule of a template — the
predicate's own rules (R2-D's numbered rules) and the filters — is a registry entry under the
template (`material_gain_v3.rule3`, …), so a REFUTED claim without `refuted_by` reads as "false by
the template's statement", which the registry states in full. (After EF-D, a concession is a failed
`ATTRIBUTED` check, not a refusal.)

### 4.2 Scope

The scope of a claim is its `ProofScope` (R0-D §9): `basis` (exact / engine), `at`, `quantifier`
(`specific_line`, `persistence`, `exists_response`, `all_responses`, `exists_alternative`,
`all_alternatives`, `selected_alternatives`), `population`, `witnesses`, `searches`, `depth`,
`multipv`, `plies`, `line_end`, `policies`. Each quantifier has a registry statement, for example
`specific_line`: "the predicate holds along this one engine line over the stated plies; other
replies are not considered".

### 4.3 In the result document (Q2)

Each ply gains an optional `analysis`. Every internal identifier is replaced (AR-D G3): node ids by
positions, search ids by indexes into `analysis.searches`, piece ids are dropped.

```text
"analysis": {
  "root": {"fen", "p_ply": int},   # the request's root position; P is p_ply moves after it
  "searches": [Search],            # every search the analysis read, in first-use order
  "judgement": Judgement,
  "observations": [Observation],
  "claims": [Claim],               # every claim of the analysis, in the graph's order
}

Search      = {"kind": "survey" | "comparison" | "analysis", "position": Position,
               "root_moves": [uci] | null, "multipv", "depth", "profile"}
Position    = {"kind": "position", "fen", "from_root": [uci], "ply": int}
              # from_root: the moves from the analysis' root (`analysis.root`) to the node;
              # ply: len(from_root) − len(P's from_root), negative for P's ancestors
Judgement   = {"status": "decided", "search": int, "played": LineScore, "best": LineScore,
               "alternatives": [LineScore], "loss": int, "grade", "policy", "curve": Curve | null}
            | {"status": "inconclusive", "reason": str, "search": int | null,
               "played": LineScore | null, "best": LineScore | null,
               "alternatives": [LineScore], "loss": int | null, "grade": null, "policy",
               "curve": Curve | null}
LineScore   = {"search": int, "rank", "move": Move, "score": Score, "wdl": Wdl | null, "expected"}
Observation = {"kind", "version", "round", "index", "operands": [Value]}
Claim       = {"id", "template", "role", "status", "reason"?, "refuted_by"?,
               "scope": Scope | null, "relations": [Relation],
               "checks": [{"kind": "realized" | "counterfactual" | "attributed", "passed",
                           "evidence": [Value]}],
               "findings": [Finding]}
Scope       = {"basis", "quantifier", "population": {"kind", "search": int | null,
               "moves": [uci]}, "at": Value, "witnesses": [uci], "searches": [SearchLine],
               "depth", "multipv", "plies", "line_end", "policies": [id]}
Relation    = {"kind", "target": Target}
Target      = {"type": "claim", "id"}
            | {"type": "observation", "kind", "version", "round", "index"}
            | {"type": "judgement", "move": Move}
```

- `Judgement` is a union on `status` (`observer.Judgement`: `search`, `played`, `best`, `loss` and
  `grade` may be `None`): a decided judgement has all of them, an inconclusive one has its `reason`
  and whatever was computed, `null` otherwise. The schema states the same union. `wdl` is `null`
  when the search reported none (`Unavailable`); `curve` as AR-D's.
- A `Position` is identified by `from_root`, not by its FEN: two nodes with one FEN reached by
  different paths (a transposition, or a played node and an engine node) differ in `from_root`.
  Every node of the tree is a descendant of the root (`TreeView.path`), P's ancestors included.
- `ClaimRelation.target` is a `ClaimId`, an `ObservationRef` or a `JudgementRef` (`graph.py`);
  `Target` keeps the three apart. An observation target names an entry of `observations` by
  `(kind, version, round, index)`; a judgement target names the move it judges.
- `claims` (AR-D) keeps its meaning and contents.
- `analysis` is written when the request asks for it (`tools/explain_game --analysis`, the server's
  `detail` field); the viewer does not need it. DF1 measures its size (§7).

### 4.4 Values: the projection of every reasoning type

One recursive rule, `project`, maps every value that can occur in a finding, an observation's
operands, a scope or a check's evidence. Every case is listed; a type without a case is a test
failure (§7, test 4).

| Type | JSON |
| --- | --- |
| `int`, `bool`, `str`, `None` | itself; an `int` field's unit is its registry entry's |
| enum (`OutcomeKind`, `Fate`, `DrawKind`, `ReplyKind`, `HangingKind`, …), `Color`, `PieceType` | its value (`"white"`, `"knight"`, …) |
| tuple | array of the projected items; `OfferFinding.keeping`'s pairs become `{"line": …, "fate": …}` |
| finding dataclass | `{"type": <class name>, <field>: project(value), …}`; each class has a registry entry and a schema |
| `NodeId` (`DecisiveEvent.node`, `MechanismFinding.node`, `ReplyFinding.board`, `.counter`, `ConcessionFinding.nodes`, `MoveSubject`) | `Position` (`from_root` from `TreeView.path`) |
| `PositionKey` | `{"kind": "position", "fen": <the key's FEN with clocks 0 1>}` |
| `PieceRef` | AR-D piece ref (`square`, `piece`, `color`, `fen` of its node); the `PieceId` is dropped |
| `MoveRef` | AR-D move ref (`uci`, `san`, `fen` before the move) |
| `SquareRef` | AR-D square ref, `fen` of the finding's board node (`ReplyFinding.board`) or of P |
| `LineSegment` | AR-D line ref (`fen` at its start, `moves`, the segment's first and last ply) |
| `SearchRef` | `SearchLine` = `{"kind": "search_line", "search": int, "rank": int | null}` |
| `SearchMoveRef` | `{"kind": "search_move", "search": int, "rank", "ply", "uci", "san", "fen"}` |
| `MaterialAmount` | `{"points", "unit": "points_v1", "policy"}` |
| `Unavailable`, `NotComputed`, `NotApplicable` (where a field allows them) | `null`, with the sentinel's code in a sibling `<field>_reason` when it has one |
| `Outcome` | `{"kind", "winner"?, "moves"?, "delta"?, "plies", "line_end"?, "reason"?}`, `delta` in `points_v1` for the mover |
| `FactRef` | `{"kind": "fact", "family", "position": Position, "path": [str | int]}`; the revision is dropped |
| `Cp`, `Mate`, `Wdl` | `{"cp"}` / `{"mate"}` in White's view (AR-D), `{"win", "draw", "loss"}` in permille |
| `LineId`, `EngineLineId`, `MissingLine` | the line's `LineSegment` form, or `{"kind": "missing_line", "search": int, "rank", "reason"}` |

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

**Reasoning (unchanged codes, closed).** Every code in use keeps its spelling; DF1 adds none and
renames none, so no stored verdict changes. The closed set is the registry's:

| Code | Where | Statement |
| --- | --- | --- |
| `ROUND_LIMIT`, `BUDGET`, `NEED_UNMET`, `IRREGULAR_SEARCH`, `DEADLINE`, `UNSTABLE`, `LINE_TOO_SHORT`, `MATE_LINE`, `SCOPE_SHORT` | `verification.REASONS` (R0-D §9.2) | as R0-D |
| `NOT_COMPUTED(<family>)`: `move`, `status`, `squares`, `material`, `draw`, `exchange`, and any family a `FamilyNeed` names | templates, `lines` | the family's record was missing at a node the claim reads |
| `NOT_COMPUTED(wdl)` | `lines.checking_draw` (EV-D) | the line's search reported no WDL |
| `NOT_COMPUTED(WDL_UNAVAILABLE)` | `capture_holds_v1` (LV-D) | the same fact, older spelling; the registry marks the two as one meaning |
| `NOT_COMPUTED(NO_LINES)` | `capture_holds_v1` | the survey reported no line |
| `NOT_COMPUTED(NO_RANK_2)` | `only_move_v1` | the search reported no second line |
| `NOT_COMPUTED(NOT_ATTACHED)` | `lines._outcome` (a line read) | the line's PV is not attached to the tree |
| `NOT_COMPUTED(IN_CHECK)` | `piece_offer_v1` (LV1), EF-D | the exchange test is undefined for a side in check |
| `NOT_COMPUTED(<refusal>)`: `FactEngineError`, `BudgetExceededError`, `CrossSearchError`, `EngineError`, `EngineOutputError`, `EngineUnsupportedError` | `runner` (a refused request, R0-D §15) | the fact engine refused the request with this error type; the set is `storage.REFUSALS` |

Merging `wdl` and `WDL_UNAVAILABLE` waits for the next version of either template.

**Fact engine (codes replace free text).** `NotApplicable` and `NotComputed` take a code from a
closed set, each a registry entry: today's codes (`IN_CHECK`, `NOT_EXPOSED`, `IRREGULAR_SEARCH`,
`COMPARISON_NOT_REQUESTED`, `PARENT_NOT_SEARCHED`, `BUDGET`) keep their spelling; `tier` → `TIER`,
`not requested` → `NOT_REQUESTED`; the free texts become `NO_SAME_SIDE_ANCESTOR`,
`ROOT_HAS_NO_MOVE`, `TERMINAL`, `FAMILY_NOT_SELECTED`, `NOT_COMPUTED_AT_NODE`. The node, revision and
family of the last two move to an optional `detail` of the sentinel, which `TreeView.fact` fills and
the encoding does not store. These are fact-side sentinels; no reasoning code above reads their
text (`NOT_COMPUTED(<family>)` is built from the family name, not from the sentinel).

## 7. Test obligations (packet DF1)

1. **Completeness.** Every family field (by the closed type registry, F5-D), template, policy,
   label rule, finding type, reason code, unit and module-level numeric constant of the listed
   modules has an entry; every entry names something that exists. A new constant without an entry
   fails the test.
2. **One value table.** No module outside `calliope.facts` defines a piece-value mapping (static).
3. **Units.** Every number in a `calliope_result_v1` of the corpus is covered by `units` or by a
   field whose schema names its unit.
4. **Analysis.** For the corpus and `g1014`: every claim, observation and relation of each
   analysis appears in `analysis` once, and decoding it back to (claim id, target type, target key,
   kind) equals the claim graph's relations, observation and judgement targets included; statuses
   and scopes equal the graph's; EA-D E2's refusals carry `refuted_by`; every finding type of
   `findings.KINDS` projects (a type without a case fails) and validates against its schema; no
   string of the form of a `NodeId`, `SearchId` or `PieceId` appears in the document (G3); every
   `Position` resolves by replaying `from_root` from `analysis.root` to its `fen`; an inconclusive
   judgement of the corpus (missing S, a missing played line) validates;
   `analysis` absent unless requested; the schema accepts both.
5. **Reasons.** Every sentinel the fuzz (F1–F6 suites) produces has a code from the set; every
   INCONCLUSIVE reason of the corpus and the three games is in §6.2's table; every
   `FactEngineError` subclass the facts API raises is in `storage.REFUSALS`; a static scan finds no
   `NOT_COMPUTED(` literal outside the table.
6. **Builds.** The registry digest is in `ReasoningBuild`; changing one threshold changes the build;
   the fact build changes with the reason codes (§8) and nothing else.
7. **No behaviour change.** Every verdict's status, reason, findings and scope, every plan and
   every sentence of the corpus and the three games is unchanged against EF1's build; the only
   differences are the build identities, `refuted_by` where §4.1 adds it, and the fact sentinels'
   codes (§6.2), each listed by the test.
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
| Q3 | `refuted_by` for every refusing rule, or only for the filters? | Only for the filters; every rule, the predicate's included, is a registry entry (§4.1) |

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

## 12. Review dispositions (rev. 1 `f609af1`, independent review: NOT_READY)

The review passed the registry, `configuration_only`, the single value table, `refuted_by`,
`settle_v1`, the thresholds in the build and the opt-in `analysis`, and recommended Q1 keep, Q2 on
request, Q3 filters only. Each finding was checked against the code.

| Finding | Disposition |
| --- | --- |
| **B1** `quality_v1`'s loss is not in centipawns: both policies compute `loss = max(0, best.expected − played.expected)` | Accepted (`observer.grade`). `loss` is `expected_2000` under both; the grade bands are 1/2000 (B9 row corrected); `evaluation.expected` for both policies (§0, §3.1). |
| **B2** a relation's target can be a claim, an observation or a judgement | Accepted (`ClaimRelation.target`). `Target` is a tagged union, `analysis.observations` lists the observation targets, and test 4 decodes the relations back to the graph's (§4.3). |
| **B3** the closed `NOT_COMPUTED(…)` set left out codes in use (`NO_RANK_2`, `NOT_ATTACHED`, and the runner's refusal types) | Accepted. §6.2 lists every reasoning code with its decision: all kept unchanged, the two WDL spellings marked as one meaning; the refusal types are `storage.REFUSALS`. Test 7 is narrowed to what really stays fixed, and test 5 scans for unlisted literals. |
| **B4** findings hold `NodeId`, `SearchRef`, nested tuples; AR-D has no search ref and forbids internal ids | Accepted. §4.4 projects every type, nodes to positions with the moves from P, searches to indexes into `analysis.searches`; piece ids dropped; test 4 checks every finding type, the schemas and the absence of internal ids. |
| (note) Q3: rules without `refuted_by` must still be readable | Applied: every template rule is a registry entry (§4.1). |

## 13. Re-review dispositions (rev. 2 `6ca6b5a`: NOT_READY)

The re-review passed B1–B3 and B4 with notes.

| Finding | Disposition |
| --- | --- |
| **B5** §2.1's statement of `material_gain_v3` excluded concessions, while EF-D rev. 2 keeps a concession SUPPORTED with a failed `ATTRIBUTED` check | Accepted. The template's statement is the line's material; `ATTRIBUTED` (`concession_v1`) is its own entry, with its meaning (§2.1); B6 lists the failed check as a meaning of SUPPORTED, and E2 alone as a filter that refutes (§0). |
| **B6** `Judgement` required `search`, `played`, `best`, `loss`, which an inconclusive judgement may lack | Accepted (`observer.Judgement`). `Judgement` is a union on `status`, `wdl` may be `null`; the schema states the union; test 4 validates the corpus' inconclusive judgements (§4.3). |
| **B7** `from_p` cannot place P's ancestors, and a FEN does not identify a node | Accepted. `Position` carries `from_root` (from the request's root, `analysis.root`) and `ply` relative to P; identity is the path, not the FEN; test 4 replays every position (§4.3, §4.4). |
| (B4 note) boundary cases of the projection | Sentinels in optional fields project to `null` with a `<field>_reason` code (§4.4). |
