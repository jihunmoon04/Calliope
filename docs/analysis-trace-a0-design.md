# Analysis trace — unified, piece-centred line tracking (A0 design draft)

Status: **DRAFT / AWAITING INDEPENDENT A0 REVIEW** (design only; nothing frozen or implemented).
Date: 2026-10-08. Base: `main @ 4940554` (MVP G0 + positional_v1 + activity_v1 + scenario
A1–A3 + observation bridge I1–I3 merged).

This draft proposes one internal **analysis trace**: along every analysed line, record for each
frame the normalized, source-linked state of the pieces and of the position, plus the changes
between frames. It produces **information only**. It renders no sentence, selects nothing for
narration and asserts no cause. Choosing what to explain, and wording it, is a later packet.

## 1. Goals and non-goals

Goals:

1. **Piece-centred tracking.** Each physical piece (initial-square identity, kept through
   captures, promotion and castling) has a per-frame state: location, contacts (attackers and
   defenders, with pinned defenders marked), relations (what it attacks and defends), activity,
   structure roles and the tactical candidates it takes part in.
2. **Position-level tracking.** Per frame: pawn structure, files, king safety, material, check
   and mate.
3. **Normalized and comparable.** Closed typed values; each side-dependent value is recorded only
   when it is measurable and is compared only with like values; "not observed" is never zero.
4. **One integrated pipeline.** By default the normal analysis traces the played move's line and
   the engine's best line from analyses it **already** performs. Additional lines are analysed
   only on explicit request.

Non-goals in this packet:

- No sentences, templates, digests or compact selection; no change to P12 text.
- No new causal, quality or importance claim; P6 candidates stay `DETECTED`.
- No change to schema 0.2, `analyze_move()` output, error behaviour or Stockfish call counts.
- No game-level aggregation (`analyze_game` remains unavailable).

## 2. Verified current state (main `4940554`)

| Area | Fact relevant to this design |
| --- | --- |
| MVP `AnalyzeMoveService.execute` | Inside one request session: `position_analysis` (MultiPV, best line PV), `played_analysis` (`root_moves=(move,)`, PV starting with the played move), optional P2-C1 comparison, then P8/P9 → P10/P11. P12 and projection run after the session. These engine analyses and the P7 probe lines are local to `execute`/explainers and are **not exposed**. |
| `EngineLine` | `rank`, `first_move`, `score`, `pv: tuple[ChessMove, ...]`, `depth`, `seldepth`. |
| P4 `PositionFacts` | Per piece: `attacks`, `attacked_by`, `defended_by` (geometric), `legally_capturable_now`, `hanging_now`; position: `legal_captures`, `side_to_move_in_check`, `side_to_move_checkmated`, material. |
| positional_v1 | Pawn isolated / doubled / passed / geometric supporters; file pawn counts with open / semi-open. |
| activity_v1 | Attack footprint and empty/friendly/enemy partition, slider rays with physical blockers, square access (both colours' geometric attackers for all 64 squares), absolute pins (both colours), current-side legal moves and captures. |
| P6 `TacticalDetector.detect(before, after, delta, before_rules, after_rules)` | Candidates per transition: CHECK, CHECKMATE, HANGING_PIECE, DIRECT_ATTACK, FORK, DOUBLE_ATTACK, ABSOLUTE_PIN, REMOVAL_OF_DEFENDER, FORCED_RESPONSE, each with `actors` / `targets` / `related` / `responses`; status `DETECTED`. Today it is called only inside P8/P9. |
| Scenario layer | Shared FactKind / SourceRef / physical identity / full re-projection validator; EXCHANGE (square focus) and PLAYED_TRANSITION (one ply) with compact two-sentence presentation; opt-in schema 0.3. |
| Cost (PR #34 record, aarch64 2 CPU) | About 85 ms replay + 194 ms projection + 227 ms re-validation per 8-ply line. |

Consequences: the integration needs (a) a seam that exposes the PVs the MVP already computed,
without altering `execute`'s observable behaviour, and (b) a validation strategy whose cost scales
to two or more traced lines per move.

## 3. Unified pipeline

```text
analyze (default)
  MVP judgement + P8/P9/P10/P11 (unchanged; same Stockfish calls)
  -> line set (no new engine call):
       L_played = played move + played_analysis PV
       L_best   = best move   + position_analysis rank-1 PV
       (identical when the played move is the best move: traced once, labelled both)
  -> per line: one rules replay (ActivityLineAnalyzer)
       -> P6 detection per step (rules only)
       -> AnalysisTrace (frames, piece states, position states, change records)
       -> full validation
  -> later packets: claim <-> trace links, selection, narration

analyze + extra (explicit request)
  user-supplied lines | further MultiPV lines | P8/P9 P7 probe lines | deeper search
  (deeper search adds engine work and must be a separately budgeted opt-in)
```

Each traced line records its origin (`PLAYED_PV`, `BEST_PV`, `MULTIPV_k`, `USER`, `PROBE`), the
source analysis' depth and the PV truncation point. Origin is provenance, not evidentiary
strength: an engine PV is not a forced line, and nothing in the trace may say so.

Plies per line are capped (proposal: 12, together with the PV's own length). Trace work runs
outside the engine request session, after the legacy result is complete, as in I3.

## 4. Trace vocabulary (proposal; frozen in T1-D)

All records reuse the shared physical identity (`BasePieceRef`), position ids and the closed
`SourceRef` family. New value kinds are additive extensions of the shared vocabulary, not a
parallel fact system.

### 4.1 Frame and line

- `TracedLine(origin, initial position_id, moves, frames, source_analysis_depth, truncated)`.
- `Frame(index, position_id, side_to_move, in_check, checkmated)`.

### 4.2 Piece frame state (per tracked piece, per frame)

| Group | Values |
| --- | --- |
| Identity / lifecycle | base identity, current square and type, or CAPTURED (with the capture step) |
| Contacts | geometric attackers and defenders as physical identities; each defender flagged `PINNED_ABSOLUTE` when absolutely pinned, with the pin line; counts derived |
| Relations | enemy pieces it attacks, friendly pieces it defends (physical identities) |
| Activity | footprint squares and empty/friendly/enemy counts; per-direction ray visibility and first blocker for sliders; **legal move and legal capture counts only on frames where its side is to move** (otherwise `NOT_OBSERVED`) |
| Structure roles | pawn flags and supporters (positional_v1); pin roles (pinner / pinned / king) |
| Tactical participation | P6 candidates of the step that produced this frame in which it is an actor, target or related piece |

### 4.3 Position frame state

| Group | Values (definitions to be frozen in T1-D) |
| --- | --- |
| Pawn structure | per pawn: isolated, doubled, passed, **backward** (proposed: no friendly pawn on an adjacent file level with or behind it, and its stop square is attacked by an enemy pawn), supporters; per colour: **chains** (maximal sets connected by geometric pawn support), **islands** (maximal groups on adjacent files) |
| Files | white/black pawn counts; open / semi-open for colour / neither |
| King safety (both kings) | **king zone** (proposed: the king's square and its neighbours) with enemy geometric attackers per square and the distinct attacking pieces; **pawn shield** (proposed: friendly pawns on the three files around the king, on the two ranks in front of it); open / semi-open files among those three files; in check; checkmated |
| Material | counts per colour and type |

### 4.4 Tactical candidates per step

For each step k (frame k-1 → k) run P6 on the replayed transition and attach each candidate
(kind, actors, targets, related, responses) to the step with a temporal label:

- `MOVER_SIDE`: actors belong to the side that made move k ("uses" in user terms);
- `OPPONENT_SIDE`: actors belong to the side to move at frame k ("allows" in user terms);
- `appeared` / `persisting` / `resolved` relative to step k-1, keyed by kind plus physical actors
  and targets.

These labels are temporal facts. Status stays `DETECTED`; no candidate becomes a claim, a
verified tactic or a cause.

### 4.5 Change records

For every tracked value: a change record (subject, property, frame pair, before, after) whenever
the value differs. Side-dependent values (legal mobility) compare only frames with the same side
to move (k and k+2); the first comparable pair starts at frame 0 for the side to move and frame 1
for the other side. Geometric values compare adjacent frames for both sides. Change records are
the index a later selection step will query ("when did d4 lose a defender?").

## 5. Piece inclusion policy

- All non-pawn pieces of both colours are tracked over the whole line.
- A pawn is tracked over the **whole** line if at any frame it attacks an enemy piece, is attacked,
  defends or is defended by any piece (geometric), is a pinner/pinned, moves, captures, is captured
  or promotes. Pawns with no such relation anywhere in the line are omitted and listed by identity
  in the trace's accounting, so omission is auditable.
- A captured piece keeps its record up to and including its capture step; later frames hold
  CAPTURED.

## 6. Normalization rules

1. **Measurable or `NOT_OBSERVED`.** A value that the rules do not define for that frame (another
   side's legal moves; a captured piece's activity; pawn flags of a non-pawn) is a typed sentinel,
   never zero or false.
2. **Geometric vs legal is part of the type.** Attack/defence/footprint values are geometric;
   mobility and captures are legal and side-to-move only. Names say which.
3. **Pinned defenders.** A defender flagged `PINNED_ABSOLUTE` still appears among defenders (the
   geometry is true); the flag records that it cannot leave the pin line legally.
4. **No derived judgements.** No "safe", "weak", "active", "good", score or ranking. Derived
   counts (attackers minus defenders) may be stored as plain integers, labelled geometric.
5. **Deterministic canonical order** for every tuple (base board order, FactKind order,
   board-order squares, ray order near to far).

## 7. Validation and provenance

- Every value carries resolvable `SourceRef`s into the retained replay (P4 facts, P5 deltas,
  activity frames, P6 detections). A trace is accepted only if a fresh recomputation from the
  retained replay is equal.
- Accounting lists, per frame and family, every tracked subject, every omitted pawn and every
  change record, so incompleteness is detectable.
- Failures are typed and fail closed; in the integrated analysis an invalid trace never silently
  disappears (exact policy, atomic or per-line typed error, decided in T2-D).

## 8. Cost and limits

Default work per analysed move: two lines of up to 12 plies (one when played equals best). With the
present full re-projection validator this would add roughly 1–2 s per move on the measured host,
too much for a default path. T1-D must therefore decide, **without weakening validation**:

- a single validation per trace build (the builder validates the retained replay once and the
  trace record is constructed only from validated inputs, with an explicit, reviewable trust
  boundary for downstream consumers), or
- incremental per-frame validation reused across lines that share a prefix (played vs best often
  share the root only), or
- an explicit opt-in default until measurements meet a reviewed budget.

Hard caps: lines per request, plies per line, tracked pieces (32), and measured cost reported
separately for replay, P6, trace construction and validation.

## 9. Exposure and compatibility

- T1 is internal; no public field.
- Integration into the normal analysis (T2) must keep `analyze_move()` schema 0.2 byte-identical
  and Stockfish call sequences identical (D18-style differential evidence). The trace would be
  delivered through a new opt-in envelope (proposed schema 0.4, or an extension of the 0.3 method)
  decided in T2-D.
- I1 (PLAYED_TRANSITION) and I2 (EXCHANGE compact) stay as they are. Later they may become views
  over the trace; that migration is a separate reviewed step.

## 10. Delivery gates

| Packet | Deliverable | Gate |
| --- | --- | --- |
| A0 (this) | architecture, vocabulary direction, policies, open questions | independent A0 review READY |
| T1-D | frozen trace vocabulary and definitions (backward pawn, chain, island, king zone, shield), inclusion policy, change-record keys, validation strategy, executable corpus with independent oracles | independent design READY |
| T1 | internal trace builder over supplied lines; corpus acceptance; cost record | independent implementation READY |
| T2-D | seam exposing MVP PVs without changing `execute` behaviour; default line set; failure policy; opt-in envelope | independent design READY |
| T2 | integrated default tracing of played/best lines; extra lines on request; D18-style evidence | independent implementation READY |
| Later | claim ↔ trace links, explanation selection, narration (incl. Korean), P9 tested-response revision | separate reviews |

## 11. Open questions for review / STOP conditions

1. Is the piece-centred frame state complete enough to explain the observed failures (removal of
   defender, fork targets, a defender leaving, conditional mate threats) without new engine work?
2. Are the proposed definitions (backward pawn, chain, island, king zone, pawn shield) acceptable
   as closed geometric definitions, or should some be deferred?
3. Is the pawn inclusion rule auditable and stable enough, or should all pawns always be tracked?
4. Is the temporal `MOVER_SIDE` / `OPPONENT_SIDE` + appeared/persisting/resolved labelling of P6
   candidates free of causal meaning?
5. Which validation strategy (section 8) keeps full integrity while making default tracing
   affordable?
6. How should the MVP PVs be exposed (T2-D) without any change to `execute`'s observable output,
   errors or engine calls?
7. Should P8/P9 probe lines become traceable inputs in T2, or in a later packet?

**STOP** if any proposal requires changing schema 0.2, `analyze_move()` behaviour or Stockfish
call counts, promotes a P6 candidate or trace value to a claim, or weakens integrity validation.
