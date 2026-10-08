# Analysis trace — frozen legacy plus a new trace-based analysis path (A0 design draft, rev. 3)

Status: **CORRECTED DRAFT / AWAITING INDEPENDENT A0 RE-REVIEW** (design only; nothing frozen or
implemented). Date: 2026-10-08. Base: `main @ 4940554`.
Review history: rev. 1 `e42324a` NOT_READY (review 5457620748, B1–B4 + C1–C5); rev. 2 `a9f0471`
NOT_READY (review 5457830901, R2-B1/R2-B2 + four gates). Section 11 maps every finding.

## 0. Decisions

1. **Legacy is frozen** (P7–P12, schema 0.2, I1–I3 / schema 0.3): not ported, not edited, not
   re-validated by the new path. It keeps serving the public API and is the comparison baseline.
2. A **new analysis path** is built from scratch: an observational *analysis trace* per line, a
   separate *engine evidence* record, and later new evidence rules over both.
3. Legacy behaviour is **captured, not reconstructed**: three transparent observer seams record
   what the legacy request actually did (section 2). Facts the seams cannot see are derived only
   from captured objects by a frozen, versioned rule, and are labelled `DERIVED` (section 3.3).
4. **Comparison replaces parity**: on recorded tapes, legacy and new-path results are compared and
   every difference is dispositioned against independent oracles (section 7).

The trace produces **information only**: no sentence, no narration selection, no causal or quality
assertion.

## 1. Goals and non-goals

Goals: (G1) one validated fact model per analysed line; (G2) piece- and position-centred normalized
tracking (section 4); (G3) engine and probe evidence captured completely and separately (section 3);
(G4) the normal analysis traces the played line, the best line and every P7 probe line from work the
legacy request already performed, further lines only on explicit request; (G5) a reproducible
comparison harness against legacy.

Non-goals in this packet: new evidence rules, claims, prose, Korean wording, public schema change,
`analyze_game`, LLM use. Legacy behaviour, output, errors and Stockfish call sequences are unchanged.

## 2. Capture topology (R2-B1)

The verified sources of a legacy request are three independent boundaries, all wired in
`composition.py` around the one `StockfishAdapter` and the one shared `CounterfactualAnalyzer`:

| Seam | Wrapped object | What it sees |
| --- | --- | --- |
| E: engine | `EngineAnalysisPort.analyze(position, settings, root_moves)` — the adapter instance given to `AnalyzeMoveService.engine` **and** to `CounterfactualAnalyzer.engine` | every engine call and its returned `EngineAnalysis` or raised error |
| S: session | `EngineRequestSessionPort.request_session()` — `AnalyzeMoveService.sessions` | session enter, exit and exceptional exit |
| C: counterfactual | the shared `CounterfactualAnalyzer.execute(CounterfactualBatchRequest)` held by both explainers (P8 `bad_move.py` batches A/B, P9 `good_move.py` Batch A / IGNORE_THREAT Batch B) | every batch request and its returned `CounterfactualBatchResult`, including terminal `ProbeResult`s that made **no** engine call, or the raised error |

Seam rules:

- Each seam delegates to the wrapped object and returns **the identical object** or re-raises **the
  identical exception**; it never copies, normalizes, retries, reorders or suppresses. It performs no
  engine, rules or session operation of its own.
- The seam objects are injected only in `composition.py`. Identity contracts that legacy tests rely
  on are preserved: one engine object serves service and P7 (both the same E wrapper), one shared
  C wrapper serves both explainers (`bad.counterfactual is good.counterfactual`).
- Events go to a **request-local capture scope** opened by the public entry point around the legacy
  call (section 2.1) and held in a `contextvars.ContextVar`; events outside an open scope are not
  recorded and change nothing. Concurrent requests on other threads have separate scopes; the
  Stockfish session already serializes engine use, and the scope does not depend on that.
- Ordering: one monotonically increasing sequence per scope across E, S and C events. Engine calls
  inside a C batch carry the enclosing batch sequence number, so batch membership is captured, not
  inferred.
- Failure: on an exception the scope keeps every event up to the failure, including the error type
  and identity, then the exception propagates unchanged. Capture failures (e.g. an unexpected
  internal error in the seam) must not change legacy results or errors: the seam records a
  `CAPTURE_FAILED` marker and the new path is skipped for that request with a typed report.

### 2.1 Composition under both public entry points

- `analyze_move()` (schema 0.2): the facade opens a capture scope, calls the unchanged legacy use
  case, closes the scope, returns the legacy result unchanged. In the default configuration the new
  path does not run inside `analyze_move()`; the captured transcript is available to internal
  callers and the comparison harness. Any later integration into this entry point is gated by I-D.
- `analyze_move_with_observations()` (schema 0.3): its existing preflight (shape, canonical UCI,
  duplicates, full supplied-line legality before any engine work) runs first and unchanged; the
  scope then wraps only its call of the legacy use case; the 0.3 observation work and atomic failure
  policy are unchanged. New-path results are not added to the 0.3 DTO in this design.

## 3. Engine evidence and line assembly

### 3.1 EngineTranscript (captured)

An immutable, versioned (`engine_transcript_v1`) and serializable record of one scope:

- `SessionEvent(seq, ENTER | EXIT | EXIT_WITH_ERROR, error_type)`;
- `EngineCall(seq, batch_seq | None, position_id, settings, root_moves, result: EngineAnalysis |
  None, error_type | None)` with the complete returned object (all lines: rank, first move, full PV,
  mate-aware score, WDL, depth, seldepth, nodes, engine identity);
- `BatchCall(seq, request: CounterfactualBatchRequest, result: CounterfactualBatchResult | None,
  error_type | None, engine_call_seqs)` keeping every `ProbeResult` with its probe (kind, base,
  intervention, execution), `analysis_position`, `intervention_position`, `root_moves`,
  `engine_analysis` or `terminal`;
- request anchor: base `position_id`, played move UCI, entry point, legacy result schema version or
  legacy error type.

Serialized tapes carry the transcript version and the engine identity; a tape replay port (R1)
returns recorded `EngineAnalysis` objects in order and fails on any unrecorded or out-of-order call.

### 3.2 Line assembly matrix (R2-B2)

Lines are assembled as **base-rooted canonical UCI sequences** from captured objects only. Contracts
verified in source: `EngineLine.pv[0] == first_move` (`domain/engine/analysis.py`);
`position_analysis` and `played_analysis` both analyse the base position, the latter with
`root_moves=(played,)` (`application/analyze_move.py`); probe preparation in
`counterfactual/analyzer.py`.

| Origin | Engine analysis position | Forced root | Base-rooted line | Terminal case |
| --- | --- | --- | --- | --- |
| `JUDGEMENT_POSITION` rank k (first judgement call) | base | none | `pv` of line k | n/a |
| `JUDGEMENT_PLAYED` (second judgement call) | base | `(played,)` | `pv` (pv[0] = played) | n/a |
| `JUDGEMENT_RECONCILE` (P2-C1 paired call, if any) | base | `(best, played)` | `pv` of each line | n/a |
| `BEST_RESPONSE` probe | `probe.base` | none | `pv` from `probe.base` | terminal base: empty line, terminal recorded |
| `ALTERNATIVE_MOVE` probe | `probe.base` | `(intervention,)` | `pv` (pv[0] = intervention) | terminal base refused by P7 (no result) |
| `REFUTATION` probe | after intervention | none | `(intervention,) + pv` | terminal after intervention: `(intervention,)`, terminal recorded |
| `IGNORE_THREAT` probe | after intervention | `(execution,)` | `(intervention,) + pv` (pv[0] = execution) | terminal after intervention refused by P7 (no result) |

Assembly rules:

- Validate: analysis position id equals the stated position; forced root equals pv[0]; every move
  is legal in sequence from the line's base (`probe.base` for probes, request base for judgement
  calls); intervention position equals the base after the intervention. Any mismatch **refuses**
  the line with a typed error; nothing is repaired or partially kept.
- A probe whose `probe.base` is not the request base (e.g. P9 probes from the position after the
  played move) is a line from that base; its correspondence to the request root is recorded as the
  captured base position id, never re-derived.
- **Deduplication** only for entire identical (base position id, UCI sequence) pairs: such a line is
  replayed once and keeps **every** evidence origin. Lines with equal first moves but different
  continuations are distinct. Shared prefixes may reuse replayed frames (4.6) without merging lines.
- Full fidelity: every evidence line keeps the entire captured PV; caps apply only to opt-in user
  input and rendering (B3 disposition retained).

### 3.3 EngineEvidence (captured + derived)

`EngineEvidence` binds each traced line to exact captured data: transcript call seq, line rank,
`ProbeResult` (probe base, intervention/execution, analysis position, root moves, terminal), batch
seq, and for judgement calls their order. Two labels are not observable at the seams and are
`DERIVED` by a frozen rule `legacy_role_rules_v1` over captured objects:

- judgement call role (`POSITION`, `PLAYED`, `RECONCILE`): by order within the session and by
  settings/root-move shape as fixed in `analyze_move.py`;
- batch role (P8 batch A / comparator batch B; P9 Batch A / IGNORE_THREAT Batch B): by the legacy
  routing that is itself captured (judgement quality in the result) and batch order and probe kinds.

Every derived label names its rule version; a derivation that does not match the captured shape is
a typed refusal. Captured and derived facts are distinct types.

### 3.4 Opt-in extra lines

User-supplied lines, further MultiPV ranks of a captured call and deeper or new probes are opt-in.
Lines needing new engine work run in a **separate, explicitly budgeted request session** after the
legacy session, recorded in their own transcript; their protocol is designed for the new rules in a
later packet, not copied from P7.

## 4. Analysis trace (observational)

### 4.1 Records

- `AnalysisTrace(line, frames, steps, piece_tracks, position_track, changes, accounting)`.
- `Frame(index, position_id, side_to_move, in_check, checkmated, stalemated, legal_move_count)`.
- `Step(ply, move: canonical UCI, mover, board_delta, capture, promotion, castling, en_passant,
  legal_moves_before: complete canonical UCI set, legal_captures_before, tactical_events)`.
- `PieceTrack(base, state per frame)`, `PositionTrack(state per frame)`.
- `ChangeRecord(subject, property, frame_a, frame_b, before, after)`.
- `TraceRef`: closed tagged references (trace, frame or step, family, subject) resolving into the
  trace; existing `SourceRef` kinds remain the provenance of every value.

### 4.2 Tracked subjects (clarification 1)

All physical pieces present at frame 0 (at most 32) are tracked over the whole line, every pawn
included. A captured piece keeps its record through the capture step and is `CAPTURED` afterwards.
No selective omission.

### 4.3 Piece frame state

| Group | Values |
| --- | --- |
| Identity / lifecycle | base identity; current square and type, or CAPTURED with capture step |
| Contacts | geometric attackers and defenders (physical identities); defenders flagged `PINNED_ABSOLUTE` with the pin line; counts |
| Relations | enemy pieces attacked; friendly pieces defended |
| Activity | footprint squares with empty/friendly/enemy counts; per-direction ray visibility and first blocker (sliders); legal moves and legal captures of this piece **only on frames where its side is to move**, otherwise `NOT_OBSERVED` |
| Structure roles | pawn flags and supporters; chain and island membership; pin roles |
| Tactical state | stateful predicates of section 4.5 in which it is a role holder |

### 4.4 Position frame state (clarification 2)

Versioned **observational metrics**, never "weak / safe / good" facts. Each metric carries a
definition version; new metrics are frozen in T1-D with adversarial cases or deferred.

| Group | Values |
| --- | --- |
| Pawn structure (positional_v1 + proposed v1 additions) | isolated, doubled, passed, supporters; proposed: backward, chains, islands |
| Files | pawn counts; open / semi-open for colour / neither |
| King surroundings (proposed) | king-zone squares with enemy geometric attackers per square; pawn-shield pawns; open/semi-open files near the king; in check; checkmated |
| Material | counts per colour and type |
| Terminal | checkmate, stalemate, legal move count of the side to move |

### 4.5 Tactical events versus tactical state (B4)

Two separate families:

1. **Tactical events (P6 as is).** For each step, the P6 candidates of that transition, with
   kind, actors, targets, related pieces and responses exactly as emitted. Semantics are P6's:
   delta-triggered (e.g. FORK requires a new attack relation; ABSOLUTE_PIN only when newly created;
   FORCED_RESPONSE has no actors or targets). The event records which side moved at that step; it
   does **not** assign "uses/allows" to actorless candidates and carries no persistence label.
2. **Tactical state predicates (new, frame-level, versioned).** Board-state facts evaluated
   independently on every frame from P4/activity values, for example: `ATTACKS_MULTIPLE(piece,
   targets)` (a piece geometrically attacks two or more enemy pieces), `ABSOLUTELY_PINNED(pinner,
   pinned, king)`, `UNDEFENDED_ATTACKED(piece)`, `ATTACKERS_EXCEED_DEFENDERS(piece)`,
   `IN_CHECK(king, checkers)`. Persistence and resolution are **change records of these
   predicates** across frames, not comparisons of event sets. Exact predicate list and definitions
   are a T1-D freeze; none implies a winning tactic.

"Uses / allows" wording from earlier discussion is not part of the trace; a later rule may derive
it from events, state predicates and line outcomes.

### 4.6 One replay per line

Lines from the same base position that share a move prefix (for example the `JUDGEMENT_PLAYED`
line and a `REFUTATION` probe whose intervention is the played move) reuse the replayed prefix
frames. Each distinct (base position id, move prefix) is replayed once per request; lines are never
merged unless their full sequences are identical (3.2).

### 4.7 Normalization rules

1. Undefined values are typed sentinels (`NOT_OBSERVED`, `CAPTURED`, `NOT_APPLICABLE`), never
   zero or false.
2. Geometric versus legal is part of the type.
3. Side-dependent values compare only frames with the same side to move (k, k+2); geometric values
   compare adjacent frames for both sides; the first comparable pair is defined per side.
4. Plain derived integers are allowed and labelled geometric; no evaluative derived value.
5. Canonical deterministic order of every tuple.

## 5. Views

Read-only queries over traces, no replay or validation of their own: square, one-ply, piece,
position. Legacy EXCHANGE / PLAYED modules remain untouched; whether they are later re-based on
views is decided after the switch (section 9).

## 6. Validation and trust boundary

- The trace builder validates the retained replay, the transcript and the line assembly once and
  constructs records only from validated inputs; nested records are frozen.
- Internal consumers rely on this construction path and do not re-project. This is an integrity
  convention, not a security guarantee: Python objects can be mutated by reflective code.
- Anything entering from outside (deserialized tapes or traces, caller-constructed records, test
  fixtures) is accepted only after full recomputation and equality.
- `TraceRef` / `SourceRef` / transcript references resolve through closed tagged types and exact
  anchors.
- Required mutation tests: forged references, wrong anchors, swapped frames, edited values,
  transcript/line mismatch, wrong origin or derived label, nested-record edits, construction bypass.

## 7. Comparison harness and switch criteria

- **Recorded tapes.** Corpus requests run once against real Stockfish with the seams; tapes are
  stored. Legacy is re-run from a tape through the tape replay port (which fails on any unrecorded
  call, enforcing identical call sequences); the new path consumes the same tape. Real-engine reruns
  are not assumed byte-identical (P7 uses a time budget).
- **Legacy-compatible projection.** Legacy is compared through its public 0.2/0.3 projection and
  error types.
- **Independent oracles.** Each corpus item has reviewed factual expectations (and, for causal
  claims, reviewed causal expectations) authored independently of both implementations.
- **Disposition.** Every difference is classified (improvement / regression / intended change /
  unexplained) against the oracles. A classified regression remains a regression: each needs an
  explicit reviewed disposition (fixed, or accepted with a recorded reason). No new path may emit an
  unsupported causal claim.
- **Switch criteria** (numeric thresholds frozen in a reviewed packet before any activation): zero
  unexplained differences; zero unaccepted regressions; oracle agreement at least that of legacy on
  every corpus family; measured cost within the agreed budget.

## 8. Cost

Measured per stage (seam overhead with and without an open scope, line assembly, replay, P6, trace
construction and validation, views) for G0 normal requests and the I3 worst opt-in request. Default
tracing is activated only after a reviewed budget per move is met. Validation is never weakened to
meet a budget; duplicated replay and re-projection are what the design removes.

## 9. Delivery gates

| Packet | Deliverable | Gate |
| --- | --- | --- |
| A0 rev. 3 | architecture, capture topology, assembly matrix, finding dispositions | independent A0 READY |
| R1-D / R1 | E/S/C seams, capture scope, `engine_transcript_v1`, tape serialization and replay port, `CAPTURE_FAILED` handling; differential proving unchanged legacy results, errors and call sequences on G0 (both modes, both entry points, failure injections, concurrent requests) | READY each |
| T1-D | frozen trace and EngineEvidence vocabulary, coverage matrix (legacy data → transcript/evidence/trace), assembly validation, state predicates (4.5), metric definitions (4.4), TraceRef, construction boundary, cost method; corpus with independent oracles (A1 E01–E15, I1-D D01–D20 where applicable, real-game positions incl. the reviewed 2026-10-08 game) | independent design READY |
| T1 | trace builder over transcripts and supplied lines; assembly matrix; mutation tests; cost record | independent implementation READY |
| H1 | comparison harness and first report (no new rules yet) | READY |
| I-D | integration of the new path into public entry points: when it runs, failure reporting without touching legacy results/errors (0.2) or the 0.3 atomic policy, opt-in envelope | independent design READY before any public exposure |
| E1-D / E1 … | new evidence rules (incl. revised threat/tested-response logic and mechanism links), comparison reports | READY each |
| Switch | default path change against the frozen switch criteria | explicit decision |
| Later | public result model, 0.2/0.3 sunset policy (stated before any public change), narration, Korean, `analyze_game` | separate reviews |

## 10. Open questions / STOP conditions

1. Are the three seams sufficient and truly transparent for every legacy path (judgement, P2-C1,
   P8/P9 batches, terminal probes, failures mid-session, concurrent requests)?
2. Are the two `DERIVED` role rules acceptable, or should batch roles be captured by a further
   seam that keeps legacy identity contracts?
3. Is the assembly matrix complete for every probe base used by P8/P9?
4. Are the proposed state predicates (4.5) and metrics (4.4) acceptable candidates for T1-D?
5. What comparison oracles and numeric switch thresholds should be frozen?

**STOP** if a packet modifies legacy behaviour, output, errors or engine calls, adds default engine
work, truncates evidence lines, repairs a mismatching line, turns a trace value or P6 event into a
claim, or weakens validation at an external boundary.

## 11. Review dispositions

Rev. 1 (review 5457620748 on `e42324a`):

| Finding | Disposition |
| --- | --- |
| B1 L4 input closure | engine evidence separated (`EngineTranscript` + `EngineEvidence`); coverage matrix in T1-D; no port of P8/P9 |
| B2 P7 protocol equivalence | P7 not re-implemented; lines come from captured batches (3.1–3.2) |
| B3 truncation vs parity | full captured PV kept for evidence; tape-based comparison with call-sequence enforcement (7) |
| B4 P6 temporal labels | P6 events kept with P6 semantics; persistence via frame-level state predicates (4.5) |
| C1–C5 | all pieces tracked (4.2); versioned observational metrics (4.4); construction boundary with mutation tests (6); comparison through legacy public projection (7); cost-gated activation (8) |

Rev. 2 (review 5457830901 on `a9f0471`):

| Finding | Disposition |
| --- | --- |
| R2-B1 transcript not producible by an engine-only recorder | three seams E/S/C with one correlated request-local scope; terminal probes captured through C; captured vs `DERIVED` facts typed (2, 3.1, 3.3) |
| R2-B2 line grammar | origin × analysis position × forced root × base-rooted line × terminal matrix from verified contracts; validate and refuse; dedupe only identical full sequences, keeping all origins (3.2) |
| Gate: concurrency, failure events, immutability, tape version | context-local scopes, failure events with error identity, `CAPTURE_FAILED`, `engine_transcript_v1`, tape replay port (2, 3.1, R1) |
| Gate: ProbeResult binding, P2-C1, terminal results | `EngineEvidence` binds exact probe/base/intervention/execution/analysis position/call/rank; `JUDGEMENT_RECONCILE` separate; terminal results bound to their captured `ProbeResult` (3.2, 3.3) |
| Gate: regressions and switch criteria | independent oracles, explicit regression disposition, no unsupported causal claims, numeric switch criteria frozen before activation (7) |
| Gate: T2-D reference and entry points | I-D packet added; composition under 0.2 and 0.3 entry points specified, 0.3 preflight and atomic policy preserved (2.1, 9) |
