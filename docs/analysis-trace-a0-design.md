# Analysis trace — frozen legacy plus a new trace-based analysis path (A0 design draft, rev. 2)

Status: **CORRECTED DRAFT / AWAITING INDEPENDENT A0 RE-REVIEW** (design only; nothing frozen or
implemented). Date: 2026-10-08. Base: `main @ 4940554`.
Previous revision `e42324a`: independent A0 review **NOT_READY** (B1–B4 plus five clarifications,
review 5457620748). Section 11 maps every finding.

## 0. Decision changed in this revision

Rev. 1 proposed to **port** P8/P9 onto traces under strict parity. Review showed that parity forces
the new design to reproduce every detail of the current P7 protocol and evidence (B1–B3) and would
also reproduce its known limitations (missing mechanisms, tested-response choice). Rev. 2 instead:

1. **Freezes the legacy pipeline** (P7–P12, schema 0.2, I1–I3 / schema 0.3) as it is. It is not
   ported, edited or re-validated by the new path. It keeps serving the public API and acts as a
   **comparison baseline**.
2. Builds a **new analysis path** from scratch: an observational *analysis trace* per line, a
   separate *engine evidence record* (sidecar), and later new evidence rules over both.
3. Replaces parity with **recorded, reproducible comparison reports**: on fixed corpora, legacy
   claims and new-path results are produced from the same recorded engine transcript and every
   difference is classified in review (improvement / regression / intended change).
4. Switches the default only when the new path meets agreed comparison criteria (section 9).

The trace still produces **information only**: no sentence, no narration selection, no causal or
quality assertion. Choosing what to explain and wording it are later packets.

## 1. Goals and non-goals

Goals: (G1) one validated fact model per analysed line; (G2) piece- and position-centred normalized
tracking (section 4); (G3) engine evidence preserved completely and separately (section 3); (G4) the
normal analysis traces the played move's line and the best line from engine work the legacy request
already performs, further lines on explicit request; (G5) a reproducible comparison harness against
legacy.

Non-goals in this packet: new evidence rules, claims, prose, Korean wording, public schema change,
`analyze_game`, LLM use. Legacy behaviour, output, errors and Stockfish call sequences are unchanged.

## 2. Architecture

```text
 public analyze_move()  ──► LEGACY (frozen): judgement, P7–P12, schema 0.2 / 0.3
                               │  every engine call passes through
                               ▼
                    EngineTranscriptRecorder (transparent wrapper of the engine port)
                               │  immutable EngineTranscript of this request
                               ▼
 NEW PATH (internal; outside the request session; after the legacy result exists)
   A. line acquisition   (section 3.2 state machine; default = no extra engine call)
   B. trace builder      one rules replay per line ─► AnalysisTrace (section 4)
   C. evidence record    EngineEvidence linking transcript entries ↔ traced lines (section 3)
   D. later packets      new evidence rules / claims / selection / narration over B + C
```

Invariants:

- Legacy code paths are not modified. The recorder only observes: it returns exactly the object
  the adapter returned and adds no engine call, setting or session operation (proved by D18-style
  byte and call-sequence differential on G0, both output modes).
- New-path work runs outside the engine request session and never calls the engine port in the
  default configuration. Extra engine work is a separate, explicit, budgeted opt-in (section 3.3).
- Stockfish and MoveJudge alone decide move quality; no trace value is evaluation evidence and no
  trace value is a claim.
- Physical identity is the initial-square `BasePieceRef`; SAN is never identity.
- Failures are typed and fail closed. A new-path failure never alters or suppresses the legacy
  result; how it is reported is decided in T2-D (section 10).

## 3. Engine evidence (B1) and line acquisition (B2)

### 3.1 EngineTranscript and EngineEvidence

`EngineTranscript` is the ordered, immutable list of every engine call made by one legacy request:
for each call its index, request position id, `EngineSettings`, `root_moves`, batch/probe identity
when issued by P7, and the complete returned `EngineAnalysis` (all `EngineLine`s with rank,
first move, full PV, mate-aware `EngineScore`, WDL, depth, seldepth, nodes, engine identity), plus
session boundaries. It records P2-C1 reconciliation searches and P7 `ProbeResult`s with their
request/result identities and terminal outcomes exactly as returned.

`EngineEvidence` is the typed correspondence between transcript entries and traced lines: for each
`TracedLine`, the transcript call and line rank it came from, the PV prefix replayed, terminal
status (`CHECKMATE`, `STALEMATE`, `PV_END`, `ILLEGAL_PV_MOVE` refusal), and for probes the probe
request (base position, execution move, settings) and the branch it belongs to (played, best,
representative alternative rank k, tested response). It is distinct from the observational trace:
scores and rankings live only here.

Coverage requirement for T1-D: a matrix listing every datum the legacy P8/P9 rules read (from
`bad_move_causes.py`, `good_move.py`, `good_move_benefits.py`, `good_move_preservation.py`,
`counterfactual/analyzer.py`: probe results and identities, mate-aware scores, terminal outcomes,
root moves, representative ranking, legal-move and legal-capture observations, capture/promotion
events, material stability by ply, P2-C1 provenance) and where it is preserved in
`EngineTranscript` + `EngineEvidence` + `AnalysisTrace`. New rules are not required to use all of
it, but nothing the legacy decision depended on may be unrecoverable, so comparisons can explain
differences.

### 3.2 Default line acquisition (no extra engine work)

A deterministic state machine run after the legacy result is complete:

```text
S0  read EngineTranscript of the request (refuse if absent or inconsistent with the result anchor)
S1  L_played := played move + PV of the played-analysis call (root_moves=(played,))
S2  L_best   := rank-1 first move + PV of the position-analysis call; if equal to L_played,
               one line with both origins
S3  for every P7 probe result in the transcript: L_probe := execution move + returned PV,
               labelled with its branch (comparator punishment, representative alternative k,
               tested response, preservation) as recorded by the transcript
S4  replay each line once (shared prefixes are replayed once and shared, see 4.6)
S5  build traces and EngineEvidence; validate once (section 6)
```

Because S3 only *reads* what legacy already requested, the new path does not reproduce the P7
conditional protocol and adds no engine call. Its line set is therefore exactly the legacy request's
engine evidence.

### 3.3 Opt-in extra lines

User-supplied lines, further MultiPV ranks of an existing call and deeper or new probes are opt-in.
Lines needing new engine work run in a **separate, explicitly budgeted request session** after the
legacy session, recorded in their own transcript; their protocol (state machine, caps, settings,
errors) is a T2-D deliverable and is designed for the new rules, not copied from P7.

### 3.4 Full-line fidelity (B3)

Evidence traces keep the **entire returned PV** of every acquired line; no evidence trace is
truncated. Caps apply only to (a) opt-in user lines at request time and (b) public/detail rendering
of traces, never to what evidence is computed on. A PV containing an illegal or terminal-crossing
move is recorded with its terminal status and refused beyond that point, as today.

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

Lines sharing a prefix (for example the played move's first step in `L_played` and in probes that
start after it) reuse the replayed prefix frames. Each distinct (initial position, move sequence)
prefix is replayed once per request.

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

## 6. Validation and trust boundary (clarification 3)

- The trace builder validates the retained replay and the transcript correspondence once and
  constructs records only from validated inputs; nested records are frozen.
- Internal consumers rely on this construction path and do not re-project. This is an integrity
  convention, not a security guarantee: Python objects can be mutated by reflective code.
- Anything entering from outside (deserialized traces or transcripts, caller-constructed records,
  test fixtures) is accepted only after full recomputation and equality.
- `TraceRef` / `SourceRef` resolution is closed (exact tagged types, exact anchors).
- T1 must ship mutation tests: forged references, wrong anchors, swapped frames, edited values,
  transcript/line mismatch, nested-record edits and attempted construction bypass.

## 7. Comparison harness (replaces parity; B3, clarification 4)

- **Recorded tapes.** Corpus requests are run once against real Stockfish with the recorder; the
  resulting `EngineTranscript`s are stored. Legacy and new path are then evaluated from the tape
  (legacy through a replaying engine port that returns the recorded objects and fails on any call
  not in the tape, proving identical call sequences). Real-engine reruns are not assumed
  byte-identical (P7 has a time budget).
- **Legacy-compatible projection.** Legacy output is compared through its public 0.2/0.3 projection
  and error types, not raw internal objects.
- **Report, not gate, until switch.** Per corpus item: legacy claims and selection, new-path
  results, and a classification of each difference (improvement / regression / intended change /
  unexplained). Unexplained differences block a switch.

## 8. Cost (clarification 5)

Measured per stage (recorder overhead, line acquisition, replay, P6, trace construction and
validation, views) separately for G0 normal requests and the I3 worst opt-in request. Default
tracing is activated only after a reviewed budget per move is met by measurement; until then the
new path is opt-in or offline (comparison harness). Validation is never weakened to meet a budget;
duplicated replay and re-projection are what the design removes.

## 9. Delivery gates

| Packet | Deliverable | Gate |
| --- | --- | --- |
| A0 rev. 2 | this architecture, invariants, finding dispositions | independent A0 READY |
| R1-D / R1 | `EngineTranscriptRecorder` + `EngineTranscript` + tape replay port; legacy byte and call-sequence differential on G0 (both modes) | READY each |
| T1-D | frozen trace and EngineEvidence vocabulary, coverage matrix (3.1), state predicates (4.5), metric definitions (4.4), TraceRef, construction boundary, cost method; corpus with independent oracles (A1 E01–E15, I1-D D01–D20 where applicable, real-game positions incl. the reviewed 2026-10-08 game) | independent design READY |
| T1 | trace builder over transcripts and supplied lines; S0–S5 acquisition; mutation tests; cost record | independent implementation READY |
| H1 | comparison harness and first report on the tape corpus (no new rules yet: shows what facts exist per legacy claim) | READY |
| E1-D / E1 … | new evidence rules (incl. revised threat/tested-response logic and mechanism links), claims, comparison reports | READY each |
| Switch | default path change when comparison criteria agreed in review are met | explicit decision |
| Later | public result model, 0.2/0.3 sunset policy (stated before any public change), narration, Korean, `analyze_game` | separate reviews |

## 10. Open questions / STOP conditions

1. Is the recorder truly observation-only for every legacy call path (judgement, P2-C1, P7 batches,
   failures mid-session)?
2. Is the coverage matrix (3.1) sufficient for comparisons to explain every legacy decision?
3. Is reading probes from the transcript (S3) the right default, leaving new probe protocols to the
   opt-in extra-line design?
4. Are the proposed state predicates (4.5) and metrics (4.4) acceptable candidates for T1-D?
5. How is a new-path failure surfaced in an integrated request without touching the legacy result
   (T2-D)?
6. What comparison criteria justify a switch?

**STOP** if a packet modifies legacy behaviour, output, errors or engine calls, adds default engine
work, truncates evidence lines, turns a trace value or P6 event into a claim, or weakens validation
at an external boundary.

## 11. Review disposition (review 5457620748 on `e42324a`)

| Finding | Disposition in rev. 2 |
| --- | --- |
| B1 L4 input closure | Engine evidence separated from the trace (`EngineTranscript` + `EngineEvidence`, 3.1); legacy-data coverage matrix required in T1-D; L4 port of P8/P9 removed — new rules are later packets built on trace + evidence |
| B2 P7 protocol equivalence | No re-implementation of P7: default acquisition reads the recorded legacy transcript (3.2), so engine calls and order are legacy's by construction; new probe protocols only for opt-in extra lines with their own reviewed state machine (3.3) |
| B3 truncation vs parity | Evidence traces keep the full returned PV (3.4); caps only on opt-in input and rendering; parity replaced by tape-based comparison with call-sequence enforcement (7) |
| B4 P6 temporal labels | P6 kept as step events with its own semantics, no persistence or side-role labels for actorless candidates; persistence moved to new frame-level state predicates and their change records (4.5) |
| C1 track all pieces | All pieces including every pawn (4.2) |
| C2 metrics observational | Versioned observational metrics; new ones frozen in T1-D or deferred (4.4) |
| C3 trust boundary | Construction-time validation with external full recomputation, closed refs and required mutation tests; no security claim (6) |
| C4 compatibility comparison | Comparison via legacy public projection and error types; 0.2/0.3 untouched; sunset policy stated before any public change (7, 9) |
| C5 cost gate | Default activation gated on measured per-stage cost for G0 and I3 worst requests (8) |
