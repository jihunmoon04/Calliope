# Analysis trace — trace-centred restructuring of Calliope analysis (A0 design draft)

Status: **DRAFT / AWAITING INDEPENDENT A0 REVIEW** (design only; nothing frozen or implemented).
Date: 2026-10-08. Base: `main @ 4940554` (MVP G0 + P2-C1, positional_v1, activity_v1, scenario
A1–A3, observation bridge I1–I3).

This draft restructures Calliope around **one fact model**: an *analysis trace* of every line the
analysis looks at. A trace records, for each frame, the normalized and source-linked state of the
pieces and of the position, the tactical candidates of each step and the changes between frames.
Explanation rules become queries over traces instead of owning their own replays. The trace
produces **information only**: it renders no sentence, selects nothing for narration and asserts
no cause. Choosing what to explain and wording it are later packets.

## 1. Why restructure

Present analysis computes the same chess facts in several places and keeps the most useful ones
out of reach of explanations:

| Today | Consequence observed in game analysis |
| --- | --- |
| P8 and P9 each replay their own P7 lines; scenarios replay again; validation re-projects everything at each stage | duplicated work; ~0.5 s per traced 8-ply line, ~1.15 s per worst opt-in request |
| P10 evidence holds causes and pieces, not the mechanism | "allows a fork" without the fork square or targets; "material loss" without the removed defender |
| Verified PVs and P7 lines stay inside `execute` | the line a claim was verified on cannot be shown or compared |
| P9 tested responses are chosen by canonical UCI order among replies that fail | conditional threats reported as threats (26.Qh6 / ...Kh8) |
| PLAYED, EXCHANGE and the bridge are separate views with their own rules | three partial vocabularies over one board |

Goals:

1. **Single source of chess facts.** Every analysed line is replayed once into a validated trace.
2. **Piece- and position-centred tracking** with normalized, comparable values (section 4).
3. **Integrated default analysis.** The normal analysis traces the played move's line and the best
   line from analyses it already performs; further lines on explicit request.
4. **Evidence as trace queries.** P8 causes and P9 benefits are re-expressed as pure rules over
   traces, citing trace records, so mechanisms become available to later explanation.
5. **One public result model** with a compatibility view for schema 0.2 during migration.

Non-goals: new prose, narration selection, Korean wording, causal claims beyond the existing closed
predicates, game-level aggregation, LLM use.

## 2. Target architecture

```text
L0 Adapters         python-chess (sole rules), Stockfish (sole evaluation)      [unchanged]
L1 Judgement        MoveJudge on position/played analyses, P2-C1 reconciliation [unchanged]
L2 Line acquisition plan -> engine -> AnalysisLineSet (one request session)
                     · played move + played-analysis PV
                     · best move + position-analysis rank-1 PV (and MultiPV k on request)
                     · counterfactual probe lines planned from first-step traces (P7 protocol)
                     · user-supplied lines (opt-in)
L3 Trace core       per line: one rules replay -> P4/P5/activity/positional/P6 -> AnalysisTrace
                     validated once at construction (section 7)
L4 Evidence rules   P8 causes, P9 benefits as pure queries over traces -> evidence citing TraceRefs
L5 Claims           P10 builder/validator, P11 selection, P12 renderer         [interfaces kept]
L6 Views            square (EXCHANGE), one ply (PLAYED), piece, position — read-only queries
L7 Public           unified result model; schema-0.2 compatibility projection
```

Invariants carried over unchanged:

- Stockfish and MoveJudge alone decide move quality; no trace value is evaluation evidence.
- One request session per analysis; trace work runs outside it; by default no additional engine
  call beyond today's judgement and P7 probe budget.
- Claims arise only from closed L4 rules and the P10 validator; traces never become claims.
- Physical identity is the initial-square `BasePieceRef`; SAN is never identity.
- Every failure is typed and fails closed.

### 2.1 Line acquisition (L2)

Planning is rules-only and deterministic. Phase 1 traces the first step of the played move and of
the best move (no engine). Phase 2 asks the engine, inside the one session, for exactly the probes
the L4 rules declare for those first-step traces; the P7 profile, probe caps and batch rules stay as
today during migration (section 8). Phase 3 traces every returned line. Each `TracedLine` keeps its
origin (`PLAYED_PV`, `BEST_PV`, `MULTIPV_k`, `PROBE`, `USER`), the source analysis' settings and
depth, and the truncation point. Origin is provenance, never evidentiary strength: an engine PV is
not a forced line.

Caps: plies per line (proposal 12), lines per request, extra opt-in lines (proposal 2 user, 2
MultiPV). Deeper search is a separately budgeted opt-in.

## 3. Trace core (L3)

### 3.1 Records

- `AnalysisTrace(line: TracedLine, frames, steps, pieces, position, changes, accounting)`.
- `Frame(index, position_id, side_to_move, in_check, checkmated)`.
- `Step(ply, move, mover, board_delta, tactical_candidates)`.
- `PieceTrack(base, states per frame)` and `PositionTrack(states per frame)`.
- `ChangeRecord(subject, property, frame_a, frame_b, before, after)`.
- `TraceRef`: closed tagged references (line, frame or step, family, subject) that resolve into
  the trace; existing `SourceRef` kinds remain the provenance of trace values.

### 3.2 Piece frame state

| Group | Values |
| --- | --- |
| Identity / lifecycle | base identity; current square and type, or CAPTURED with the capture step |
| Contacts | geometric attackers and defenders (physical identities); defenders flagged `PINNED_ABSOLUTE` with the pin line; counts |
| Relations | enemy pieces attacked; friendly pieces defended |
| Activity | footprint squares with empty/friendly/enemy counts; per-direction ray visibility and first blocker for sliders; legal move and legal capture counts **only on frames where its side is to move**, otherwise `NOT_OBSERVED` |
| Structure roles | pawn flags and supporters; chain and island membership; pin roles |
| Tactical participation | candidates of the producing step in which it is actor, target or related |

### 3.3 Position frame state

| Group | Values (closed definitions frozen in T1-D) |
| --- | --- |
| Pawn structure | isolated, doubled, passed, **backward** (proposal: no friendly pawn on an adjacent file level with or behind it, and its stop square is attacked by an enemy pawn); supporters; **chains** (maximal sets connected by geometric pawn support); **islands** (maximal groups on adjacent files) |
| Files | white/black pawn counts; open / semi-open for colour / neither |
| King safety (both kings) | **king zone** (proposal: king square and neighbours) with enemy geometric attackers per square and distinct attacking pieces; **pawn shield** (proposal: friendly pawns on the king's file and both adjacent files, one and two ranks ahead); open/semi-open files among those; in check; checkmated |
| Material | counts per colour and type |

### 3.4 Tactical candidates per step

P6 runs on every replayed step. Each candidate keeps kind, actors, targets, related pieces and
responses, plus temporal labels: `MOVER_SIDE` (actors belong to the side that moved; "uses") or
`OPPONENT_SIDE` (actors belong to the side to move after the step; "allows"), and
`APPEARED` / `PERSISTING` / `RESOLVED` against the previous step, keyed by kind and physical actors
and targets. Status stays `DETECTED`. Only L4 rules may turn a candidate plus line outcomes into
evidence.

### 3.5 Inclusion policy

All non-pawn pieces of both colours are tracked over the whole line. A pawn is tracked over the
whole line if at any frame it attacks, is attacked, defends or is defended, is in a pin, moves,
captures, is captured or promotes; other pawns are omitted and listed in accounting. Position-level
pawn structure always covers all pawns.

### 3.6 Normalization rules

1. A value undefined for a frame is a typed sentinel (`NOT_OBSERVED`, `CAPTURED`,
   `NOT_APPLICABLE`), never zero or false.
2. Geometric versus legal is part of the type name.
3. Side-dependent values compare only frames with the same side to move (k and k+2); geometric
   values compare adjacent frames for both sides.
4. No judgement-bearing derived value (safe, weak, active, good). Plain derived integers (attackers
   minus defenders) are allowed and labelled geometric.
5. Canonical deterministic order for every tuple.

## 4. Evidence rules over traces (L4)

P8 causes (`NEWLY_HANGING_PIECE`, `REMOVED_DEFENDER`, `FORK_ALLOWED`, `MATE_ALLOWED`,
`MATERIAL_LOSS_LINE`) and P9 benefits (`FORCES_RESPONSE`, `MATE_THREAT`, `MATERIAL_THREAT`,
`PREVENTS_MATE`, `PREVENTS_MATERIAL_LOSS`) become pure functions of traces:

- inputs: the played/best first-step traces and the probe-line traces the rule requested;
- outputs: the same closed cause/benefit records as today, plus `TraceRef`s to the mechanism
  (e.g. the step where a defender left, the fork step with its targets, the frame where material
  changed, the mating frame);
- the P8 material metric and stability contract are re-expressed over trace material and are
  unchanged in value during migration.

P10 evidence forms gain optional trace references; predicates, scopes, confidence and the P10/P11
validators keep their semantics. Rule revisions (for example the P9 tested-response choice: null-move
threat test, exclusion of self-inflicted replies, contrast with the opponent's best reply, the game's
actual next move) are **separate reviewed packets after parity**, never folded into migration.

## 5. Views (L6)

Views are read-only queries over traces with no replay and no validation of their own:

- **Square view** — today's EXCHANGE semantics (focus captures, participants, losses).
- **One-ply view** — today's PLAYED_TRANSITION census.
- **Piece view** — one physical piece across the line (contacts, relations, activity, candidates).
- **Position view** — pawn structure, files, king safety and material across the line.

The existing scenario modules and compact presenters are migrated to these views (T5); until then
they stay in service with their frozen behaviour.

## 6. Public model (L7)

A single result model (proposed schema **1.0**) with: judgement, claims and selection (existing
semantics), deterministic commentary, and an opt-in `analysis` section carrying the traced lines at
a requested detail level (frames and change records; views on request). During migration:

- `analyze_move()` keeps returning schema 0.2, byte-identical on the G0 corpus;
- `analyze_move_with_observations()` (0.3) is kept, then re-implemented over traces and deprecated;
- after T6 the 0.2 and 0.3 shapes are compatibility projections of the 1.0 result, with an
  announced deprecation window.

## 7. Validation and trust boundary

Integrity is checked **once, at construction**, not re-projected at every consumer:

- the trace builder validates the retained replay (P4/P5/activity/P6 consistency, identities,
  anchors) and constructs trace records only from validated inputs;
- trace records are frozen and constructible only through the builder (closed construction path);
  internal consumers (L4–L6) rely on that boundary and do not re-project;
- any trace entering from outside (deserialization, caller input, tests constructing records)
  is accepted only after full recomputation and equality;
- mutation tests prove that forged or edited records cannot pass the external boundary and cannot
  be produced through the internal path.

This deliberately supersedes the I2-D/I3-D rule that every compact presenter re-validates the full
summary, and must be accepted explicitly in review. It is the structural answer to PR #30 L4 and
replaces cross-module private validation helpers (PR #30 L6) by one owned builder.

## 8. Migration plan and parity

| Packet | Deliverable | Gate |
| --- | --- | --- |
| A0 (this) | target architecture, invariants, trace scope, trust boundary, plan | independent A0 READY |
| T1-D | frozen trace vocabulary and definitions, inclusion policy, change keys, TraceRef, construction boundary; corpus with independent oracles (reusing A1 E01–E15 and I1-D D01–D20 where applicable, plus piece/position cases from real games) | independent design READY |
| T1 | trace core over supplied lines, internal only; cost record | independent implementation READY |
| T2-D / T2 | L2 line acquisition seam exposing played/best PVs and probe lines without changing `execute` output, errors or engine calls; default traces; D18-style differential | READY each |
| T3 | P8 causes as trace queries behind a parity harness | **parity**: identical causes, evidence, claims, selection and P12 text on the P8 unit corpus, G0 public fixtures and a seeded random corpus; identical Stockfish call sequences; every difference adjudicated in review |
| T4 | P9 benefits as trace queries, same parity rules | parity READY |
| T5 | retire duplicate replays; scenarios and compact presenters as views; I1/I2 outputs identical or explicitly re-versioned | READY |
| T6 | public schema 1.0, 0.2/0.3 compatibility projections, deprecation notes | READY + real-Stockfish compatibility |
| Later | claim↔trace mechanism links in explanations, P9 tested-response revision, explanation selection, narration (incl. Korean), B1/B2, `analyze_game` | separate reviews |

During T3–T4 the old and new evidence paths run side by side in tests; production switches only
when parity is accepted. No rule is "improved" during a parity packet.

## 9. Cost targets

Measured and reported separately per stage: engine, replay, P6, trace construction/validation, L4
rules, projection. Targets are set in T1-D from measurements; the default analysis must not exceed
an agreed budget per move relative to today's `analyze_move`. Validation is never weakened to meet a
target; only duplicated work is removed.

## 10. Open questions for review / STOP conditions

1. Is the trace (section 3) sufficient for every current P8 cause and P9 benefit, so that L4 rules
   need no direct rules-library access?
2. Is the construction-time trust boundary (section 7) acceptable in place of per-consumer
   re-projection, and what minimal mutation evidence must T1 provide?
3. Can L2 planning reproduce today's P7 probe choices exactly, so that engine calls are identical
   during parity?
4. Are the proposed closed definitions (backward pawn, chain, island, king zone, pawn shield)
   acceptable, or should some be deferred?
5. Is the pawn inclusion rule auditable enough, or should all pawns always be tracked?
6. Is the temporal labelling of P6 candidates free of causal meaning?
7. Is schema 1.0 with 0.2/0.3 compatibility projections the right public end state, and what
   deprecation window applies?

**STOP** if a packet changes move quality decisions, adds default engine work, lets a trace value
become a claim, changes public schema-0.2 output before T6, or weakens integrity checking at an
external boundary.
