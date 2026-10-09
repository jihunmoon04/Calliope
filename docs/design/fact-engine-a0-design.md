# Fact engine — normalized, trusted chess facts over a frame tree (A0 design draft)

Status: **rev. 4 — A0 READY_WITH_CORRECTIONS applied**; packet F1 implemented (see
[`fact-engine-f1-implementation.md`](fact-engine-f1-implementation.md)).
Date: 2026-10-08. Base: `main @ 4940554`.
Review history: rev. 2 `e9338fc` NOT_READY (B1–B3, C1–C9, N1–N9); rev. 3 `fc15c86`
READY_WITH_CORRECTIONS (R3-C1–C4, R3-N1–N3). Section 15 maps every finding.

Supersedes: the analysis-trace A0 / R1-D direction (tags `abandoned/analysis-trace-a0`,
`abandoned/analysis-trace-r1d`), which kept the legacy P7–P12 path frozen and captured it. That
direction is abandoned. This packet starts the ground-up redesign at its lowest layer.

## 0. Decisions

1. Calliope is rebuilt as composable blocks with one role each. This packet covers **only the
   first block**: the *fact engine*, which normalizes input with python-chess and Stockfish.
2. The fact engine is one large **fact emitter**. For a root position, the lines it is asked
   about and the lines the engine reports, it builds **one tree whose nodes are frames** and
   records, per frame and per move, every fact that can be computed.
3. It records **facts only**: no evaluation words, hypotheses, causes, selection, explanation or
   move-quality labels. Explanation layers are later blocks that consume this output.
4. The output is **trusted by construction**. Consumers use it without re-validation.
   Correctness is established once, by the fact engine and its test suite, not again at runtime
   by every reader (section 9).
5. The public API may break. Legacy schema 0.2/0.3 is not preserved by this block, and legacy code
   is neither ported nor wrapped. Legacy algorithms are reused only where section 12 marks them.

## 1. What counts as a fact

Every record belongs to one of three classes. The class is part of its type.

| Class | Definition | Examples |
| --- | --- | --- |
| `RULE` | Follows from the rules of chess and the known history, with no parameters | legal moves, check, checkmate, stalemate, repetition count, material counts, geometric attacks |
| `DEFINED` | Deterministic function of `RULE` facts under a named, **versioned definition** | isolated pawn (`pawns_v1`), relative-pin geometry (`piece_order_v1`), king-zone squares (`king_zone_v1`) |
| `ATTESTED` | A recorded observation from an external oracle, with complete provenance | "Stockfish 17 with profile `d12_mpv5_v1`, given this engine input, reported line 1 = e4, cp +31, depth 12" |

Admission rules:

- **No evaluative vocabulary in names or values.** Forbidden: good, bad, weak, strong, safe,
  dangerous, threat, winning, hanging, mobility (as a quality), forced, best (except as the
  engine's *reported* rank 1), loss, blunder, outpost.
- **An `ATTESTED` fact is a fact about the report, not about the position.** The tree asserts
  that the engine said X for input I under setting S. It does not assert that X is true.
- **Undefined is never zero or false.** Typed sentinels:

  | Sentinel | Meaning |
  | --- | --- |
  | `NOT_OBSERVED` | the value depends on the side to move and is undefined for this frame |
  | `HISTORY_UNKNOWN` | the value depends on positions before the known history (2.2) |
  | `NOT_APPLICABLE` | the question does not apply, e.g. an engine search at a checkmate node (7.8) |
  | `NOT_COMPUTED(reason)` | not computed: family not requested, budget, or tier (7.5) |
  | `UNAVAILABLE` | the engine does not provide the value |
  | `Absent(reason)` | the piece no longer exists in the role the fact describes; reason ∈ {`CAPTURED`, `PROMOTED`} (added by F2-D §11) |

- **Partial counts are typed.** A count over incomplete history is `AtLeast(n)`, never a bare
  integer (6.9).
- **No arithmetic across incompatible sources.** The tree stores no score differences, no loss,
  and no "A better than B" except the ranking inside one engine search (7.3).

## 2. Requests

### 2.1 Session API (C2)

The fact engine has one API. A session owns one tree.

```text
FactEngine.open(OpenRequest(
    root: RootSpec,                 # see 2.2
    engine: EngineProfile | None,   # None → no ATTESTED facts at all
    families: FamilySelection,      # default: all RULE and DEFINED families (tiering, 7.5)
    defaults: ExpansionSpec,        # default expansion per input role (7.6)
    budget: SessionBudget,          # cumulative over the whole session
)) -> FactTree at rev 1             # root node, its families and its searches

FactEngine.extend(tree, ExtendRequest(
    lines: tuple[InputLine, ...],   # each: label, start node (default: root), moves (UCI or SAN)
    role: PLAYED | EXPLORED | ANALYSIS(by),
    expansion: ExpansionSpec | None # None → session default for this role (ANALYSIS has none)
)) -> rev

FactEngine.ensure(tree, EnsureRequest(nodes, families)) -> rev   # on-demand families (7.5)
```

- A user move and a block's analysis request use the same `extend` path: the same validation,
  canonicalization, families and search policy. Only the role, and therefore the default
  expansion, differ.
- `ANALYSIS` has **no default expansion** (N7): the requesting block states whether its nodes are
  searched and whether PVs are attached, because legacy-style probe volumes would otherwise
  multiply the tree.
- A one-shot call (`analyze(root, lines)`) is only `open` followed by one `extend`; there is no
  second API.
- python-chess and Stockfish are used only inside `calliope.facts`. Whether later blocks may
  import python-chess is decided with those blocks; the contract here is that every fact they
  rely on comes from this engine.

### 2.2 Root forms and history completeness (B2)

Accepted root forms (decided 2026-10-08): `startpos + moves`, `FEN + moves`, bare `FEN`. The moves
are replayed; the position after them is the root.

History is judged **per node**, not per root form:

- `known_plies(node)` = number of plies replayed before the node (pre-root moves plus the path
  from the root).
- `history_complete(node)` ⇔ `known_plies(node) ≥ halfmove_clock(node)`.

Every earlier position that can repeat the node lies inside the last `halfmove_clock` plies,
because a capture or pawn move makes every earlier position unreachable and resets the clock.
So:

- `startpos + moves`: every node is complete (the clock starts at 0).
- Bare FEN with clock 0: complete. Bare FEN with clock 20: the root and its next nodes are
  incomplete until a capture or pawn move resets the clock.
- `FEN + moves`: complete exactly where the formula holds; not by root form.

Effects (6.9, 7.8): positive findings inside known history stay `RULE`-true; counts over
incomplete history are `AtLeast(n)`; negative answers are `HISTORY_UNKNOWN`.

### 2.3 Input rules (lessons A1–A3, G)

1. **One canonicalizer.** Every move goes through one board-aware function before it becomes an
   edge, a key or an engine argument: input UCI, input SAN and every engine PV move.
   - All 8 castling notations (king-to-rook included) map to standard king-move UCI.
   - Null moves and malformed promotion suffixes are refused.
   - Variant: standard chess only. Chess960 is a typed refusal (`UnsupportedVariant`).
2. **Fail before engine work.** Every line of a request is parsed and checked for legality before
   the request's first engine call. An illegal line refuses the whole request with label and
   ply, and makes zero engine calls.
3. **Lines after an automatic draw** (C4). Moves that remain legal after a fivefold,
   seventy-five-move or insufficient-material node are accepted as input. Those nodes get every
   non-engine family and the header flag `after_terminal`, and are never searched. A root that is
   an automatic draw is accepted the same way.

### 2.4 Budget (C2, C6)

`SessionBudget` is **cumulative over the session**: `max_nodes`, `max_searches`, optional
`deadline_per_request_ms`.

- **Pre-check per request**: the request's input plies and its worst-case searches are compared
  with the remaining budget before any work. Worst case per new input-role node = 2 (survey and
  comparison), plus 1 re-comparison for every existing node that gains a new input child (7.3).
  A request whose input alone does not fit is refused.
- **During the build**, engine-line attachment and on-demand families (whose size is unknown in
  advance) run in a fixed priority: surveys in line order → comparisons → engine-line attachment.
  When a limit stops work, the result is recorded, not hidden:
  - a skipped comparison → `BasisEntry = NOT_COMPUTED(BUDGET)` (7.3);
  - a line cut short → end status `BUDGET_LIMIT`;
  - the manifest delta of that revision lists what was not done.

## 3. Output: the fact tree

```text
FactTree (fact_tree_v1)
 ├─ manifest      per-revision deltas: family versions, engine identity + profile, coverage, reuse
 ├─ positions     PositionKey → PositionRecord        (shared; position-only facts)
 ├─ nodes         NodeId → FrameNode                  (the tree itself)
 ├─ edges         EdgeId → Edge
 ├─ roles         revision-stamped role entries on nodes and edges
 ├─ lines         LineId → LineRecord                 (input lines, engine PVs)
 ├─ searches      SearchId → EngineSearch             (ATTESTED; content-addressed)
 └─ bases         revision-stamped BasisEntry per node (7.3)
```

### 3.1 Identities (lesson A5, B1, C2, C3)

| Id | Composed of | Used for |
| --- | --- | --- |
| `PositionKey` | placement, side to move, castling rights, **legal** en passant square (python-chess / FIDE repetition semantics) | sharing position-only facts; this engine's repetition facts |
| `RootId` | digest of the normalized `RootSpec` (root position + pre-root moves) | session identity; the same root always gives the same id, whatever lines, budget or profile follow |
| `NodeId` | digest(parent `NodeId`, canonical move); the root node's id is `RootId` | the tree node |
| `EngineInput` | exactly what is sent to Stockfish (7.4) | engine searches and the result store |
| `SearchId` | regular search: digest(`EngineInput`, kind, root moves, MultiPV, profile, engine identity); irregular search: the same preimage **plus a digest of its reported lines** | a search; content-derived, so equal ids always mean equal content (R3-C3) |

`PositionKey` and `EngineInput` are deliberately different. python-chess and FIDE count an en
passant square only if a legal capture exists; Stockfish 17 records it whenever an enemy pawn is
adjacent (`position.cpp:268-274, 783-788`). Stockfish 19, the v1 engine, records only the legal
square, as measured in F4-D §1 (M3); `EngineInput` follows what the configured engine parses
(F4-D §4), and it still differs from `PositionKey` by the halfmove clock and the window moves. Repetition facts in this tree follow the rules
(`PositionKey`). Engine searches are keyed by what the engine actually received (`EngineInput`),
so a stored search is never returned for an input the engine would have treated differently.

### 3.2 Nodes, edges, roles, lines

**One tree; input and engine membership are roles** (decided 2026-10-08).

- **One node per distinct path.** An engine PV move and an input move that are the same move
  from the same node are the same edge and the same child node.
- **Node header** (immutable; written once):
  - `side_to_move`, `ply` (from the root), `fullmove_number`, `halfmove_clock`;
  - `fen`: the full current position, so every node is self-contained;
  - `parent` and the incoming edge, with its mover;
  - `known_plies`, `history_complete` (2.2);
  - `terminal`: `CHECKMATE`, `STALEMATE`, `AUTOMATIC_DRAW(kind)`, `UNPROVEN(HISTORY_UNKNOWN)` or
    `NONE`; `after_terminal`. `UNPROVEN` is used when a fivefold can be neither proven nor
    ruled out over incomplete history (`fivefold_reached = HISTORY_UNKNOWN`, 6.9); `NONE` is only
    written when every automatic-draw rule is disproved (R3-C1; bound made exact in F1).
    `after_terminal` means **proven ended before** (F1 review C2): an earlier *known* position
    (pre-root or on the path) ended the game by rule, or the halfmove clock exceeds 150. `false`
    asserts only that no known earlier position did; an ending hidden in unknown history is not
    ruled out (read `history_complete`), and an `UNPROVEN` ancestor does not set it;
  - `rev`: the revision that added the node.
- **Roles** are separate revision-stamped entries on nodes and edges, never in the header:
  - `PLAYED(label, index)` — a move actually played in the game being analysed;
  - `EXPLORED(label, index)` — a line the user asked to explore;
  - `ANALYSIS(by, label, index)` — a line requested by a downstream block; never a user move;
  - `ROOT(index 0)` — the root node at `open`, carrying the root's expansion (F4-D §6.1);
  - `ENGINE(anchor, search_id, rank, pv_index)` — the node lies on the PV of rank `rank` of
    that search at node `anchor`, at ply `pv_index`; line depth and seldepth are read from the
    search record (F4-D §8.1).
  
  `ROOT`, `PLAYED`, `EXPLORED` and `ANALYSIS` are the *input roles*. "The engine's line at A began with
  the move that was played" is an edge carrying both an input role and an `ENGINE` role.
- **Input status follows the user's moves.** When the user plays along an existing engine line,
  those nodes gain input roles at a new revision; input-role nodes are searched under the policy
  of their role (7.6), so new engine lines grow from them.
- **Engine lines stay recoverable as wholes.** `LineRecord` id for an engine line is
  `(anchor NodeId, search_id, rank)` (C3), so a search reused at two anchors gives two distinct
  lines. A PV keeps its record even when part of it later gains input roles.
- **Transpositions.** Different paths to one position are different nodes sharing one
  `PositionRecord`.
- `LineRecord(id, origin, node path, end status, unattached_plies)`.
  - Origins: `PLAYED(label)`, `EXPLORED(label)`, `ANALYSIS(by, label)`,
    `ENGINE_PV(anchor, search_id, rank)`.
  - End status: `CHECKMATE`, `STALEMATE`, `DRAW_RULE(kind)`, `INPUT_END`, `PV_END`,
    `EXPANSION_LIMIT` or `BUDGET_LIMIT`. Every engine line also records how many PV plies were not
    attached as nodes (`unattached_plies`, 7.5).
- **No replay outside the fact engine.** Consumers walk nodes and edges; new facts come only from
  `extend` / `ensure`.

### 3.3 Revisions (C1)

- The tree is **append-only**. Nothing is modified or removed.
- **One revision per committed request** (`open`, `extend`, `ensure`). Every record a request
  adds carries that request's `rev`. A request commits atomically: a reader sees rev r−1 or rev r,
  never part of r.
- Readers see the latest committed revision by default, or pin a revision and read "as of rev r"
  (every record with `rev ≤ r`). This reproduces the state an earlier output was built from.
- One writer at a time (the fact engine).
- The manifest is a sequence of **per-revision deltas** (families computed, searches run or
  reused, work skipped and why); the manifest as of rev r is the fold of deltas ≤ r.
- Take-backs are not modelled. Going back is reading or extending from an earlier node.

### 3.4 Coverage

The manifest records, per family: its version; on which nodes it was computed and at which
revision; and for engine searches which input-role nodes were searched, skipped or not applicable,
and why. "Empty" and "not computed" are always distinguishable.

### 3.5 Canonical order and digest (C3, N8)

- Squares by index a1…h8; pieces by (square index, colour, type); moves and children by canonical
  UCI; input roles by (kind, label, index) with kind order `PLAYED < EXPLORED < ANALYSIS`;
  `ENGINE` roles by (anchor, search_id, rank, pv_index), after input roles; searches by
  `SearchId`; engine lines by rank; basis entries by (node, rev).
- The digest of rev r covers every fact record with `rev ≤ r`. It **excludes** runtime metadata
  that is not a fact (7.2: `time_ms`, `nps`, `hashfull`) and reuse markers (`REUSED`). A cold and a
  warm build of the same session give the same digest **provided** every search was regular and
  no per-request deadline was hit; an irregular search or a deadline-skipped comparison makes the
  digest load-dependent, and the manifest says so (R3-C3).

## 4. Piece identity (lessons C1–C5)

- **Root identity.** Every piece on the root frame receives a `PieceId` from its root square,
  colour and type (for example `w.N.g1`). Piece ids are global across the tree, so the same
  physical piece compares equal in every branch.
- **Assignment is per node.** `PositionRecord` facts refer to **squares**, which keeps them
  shareable across transpositions. `FrameNode.pieces` maps square → `PieceId` for that path.
- **Advancing identity across an edge** uses only the exact move: the mover goes from source to
  target; castling moves king and rook between their standard endpoints; en passant removes the
  victim from the victim square; promotion keeps the pawn's `PieceId` and changes its type; every
  other piece is unchanged. Nothing is guessed from piece type or count.
- **Capture lifecycle.** A captured piece gets `captured_at(edge)` and no square afterwards.
- **Every piece reference carries its node**: `(node, square)` or `(node, PieceId)` (lesson C5).

## 5. Fact families: the blocks

Every family implements one interface, the common connector that lets blocks fit together.

```python
class FactFamily(Protocol):
    name: str                   # e.g. "pawns"
    version: str                # e.g. "pawns_v1"
    scope: Scope                # POSITION | NODE | EDGE | SPAN
    requires: tuple[str, ...]   # families it reads (acyclic), resolved on every node it touches
    def compute(self, ctx: FamilyContext) -> FamilyRecord: ...
```

- Scopes: `POSITION` (per `PositionKey`), `NODE` (path-dependent, per node), `EDGE` (parent →
  child), `SPAN` (grandparent → node, two plies, for same-side comparisons, 6.10).
- `FamilyContext` gives read-only access to the node's internal board view (built from the node's
  stored position and history) and to the records of required families. For `EDGE` and `SPAN`
  scopes, `requires` is resolved on every node involved, so `ensure(delta)` also ensures the
  parent's families (C7).
- A family never calls the engine and never re-validates its inputs.
- Adding a family is one module and one registry entry. A changed definition gets a new version
  string.
- Families are pure: the same inputs and version give the same record, which makes sharing,
  on-demand computation and digests sound.

## 6. Fact catalogue (v1)

Drawn from the facts legacy already computed (P4 facts, P5 delta, P6 detector, positional_v1,
activity_v1, P8/P9 replay helpers). Anything not listed is out of v1.

### 6.1 `status` (POSITION, RULE)
- side to move; in check and the checking pieces;
- checkmate, stalemate, insufficient material (python-chess's test; 7.8);
- legal move count and legal moves (canonical UCI + SAN, canonical order);
- legal captures (capturer, victim, landing square, victim square, en passant, promotion);
- legal checking moves, legal mating moves (exact mate-in-1), legal promotions.

### 6.2 `material` (POSITION, RULE and DEFINED)
- counts by colour and type; bishops by square colour (RULE);
- `points_v1`: sums under 1/3/3/5/9 (DEFINED; a counting convention, not an evaluation). The
  legacy P8/P9 weights 100/320/330/500/900 would be a separate `points_cp_v1`, never a silent
  replacement.

### 6.3 `pieces` (POSITION, RULE)

Per piece: square, colour, type; geometric attack set (empty / friendly / enemy targets);
geometric attackers and defenders of its square with their types; legal moves and legal captures
**only for the side to move**, otherwise `NOT_OBSERVED`; absolute-pin status (pinner, line).
Derived counts are labelled geometric: attacker count, defender count, lowest attacker type.

The legacy `hanging_now` mixed legal and geometric notions. It is replaced by two facts (N3):
- `attacked_geometrically ∧ ¬defended_geometrically`;
- `legally_capturable_now`, for pieces of the side not to move.

### 6.4 `squares` (POSITION, RULE)
Per square: occupant, white attackers, black attackers; control counts per colour.

### 6.5 `lines` (POSITION, RULE)
Per slider and direction: visible squares and first blocker; x-ray continuation past the first
blocker, marked `XRAY` and never presented as an attack; batteries (aligned same-colour sliders).

### 6.6 `pawns` (POSITION, DEFINED, `pawns_v1`)
Extends positional_v1: isolated, doubled, passed; supporters and phalanx neighbours; backward
(definition frozen in F2); chain membership and islands; per-file pawn counts; open /
semi-open-for-colour files; `outside_enemy_pawn_cones` (N2): squares that no **current** enemy
pawn attacks now or could attack by advancing straight on its current file. It is a property of
the current pawn set, not a claim about the future (pawns change files by capturing).

### 6.7 `king` (POSITION, DEFINED, `king_zone_v1`)
King square; king-zone squares with enemy geometric attackers per square; pawn-shield pawns; open
and semi-open files on and next to the king file; legal flight squares (side to move) or
geometric flight squares (other side, labelled).

### 6.8 `patterns` (POSITION, DEFINED, `patterns_v1`)

Geometric configurations recorded per position as predicates. **A pattern asserts only that the
configuration holds, never that it wins, works or is a threat.** It replaces the P6 "candidates",
whose names implied tactical success.

| Predicate | Definition (summary; exact text in F3-D §2) |
| --- | --- |
| `MULTI_TARGET_ATTACK(piece, targets)` | a piece geometrically attacks ≥ 2 enemy pieces |
| `RELATIVE_PIN_GEOMETRY(pinner, front, back)` | ray occupants [front, back], both enemy, back above front in `piece_order_v1` (K > Q > R > B = N > P), back not a king |
| `SKEWER_GEOMETRY(attacker, front, back)` | ray occupants [front, back], both enemy, front above back |
| `DISCOVERY_LINE(slider, blocker, target)` | ray occupants [own blocker, enemy target] |
| `SOLE_DEFENDER(defender, pieces)` | one piece is the only geometric defender of ≥ 2 friendly attacked non-king pieces |
| `BACK_RANK_GEOMETRY(king)` | king on its first rank; each forward square on the second rank is own-occupied or enemy-attacked, and at least one is own-occupied |

`ABSOLUTE_PIN` left `patterns` (F3-D §2.1, §6): it is `pieces.absolutely_pinned`, with changes
in `delta.pins`; the ray form [pinned, king] is the same set.

`ATTACKERS_EXCEED_DEFENDERS` and `UNDEFENDED_ATTACKED` moved to `pieces` as
`attackers_exceed_defenders` and `attacked_without_defender` (F2-D §2, §11); their changes are in
`delta.piece_flags`. Pattern changes are a separate EDGE family `pattern_delta`, defined by
F3-D §4, which also records `DEFENCE_ENDED_UNDER_ATTACK` (removal-of-defender geometry).

### 6.9 `draw` (NODE, RULE)

- `halfmove_clock`, `fullmove_number` (exact: given by the FEN or the replay).
- `occurrences`: occurrences of this node's `PositionKey` within the last `halfmove_clock` plies,
  including this node. Exact if `history_complete`, otherwise `AtLeast(n)` (2.2).
- Two different threefold notions (N1), named separately:
  - `threefold_reached`: occurrences ≥ 3 (python-chess `is_repetition(3)`);
  - `threefold_claimable_by_move`: the side to move can make a move that reaches the third
    occurrence (the extra case in python-chess `can_claim_threefold_repetition()`).
- `fifty_move_reached`: `halfmove_clock ≥ 100`; `seventy_five_move_reached`: `≥ 150` and not
  checkmate; `fivefold_reached`: occurrences ≥ 5.
- Over incomplete history (`u = halfmove_clock − known_plies > 0` plies of the window are
  unknown), a count reaches a threshold `t` as follows (F1):
  - `true` if the known plies alone reach `t`;
  - `false` if even the most the unknown plies can hide cannot reach `t`. Two occurrences of
    one position are at least 4 plies apart, so `u` unknown plies hide at most `ceil(u / 4)`
    occurrences;
  - `HISTORY_UNKNOWN` otherwise, never a guessed `false`.

### 6.10 `move`, `delta` and `same_side_delta`
- **`move` (EDGE, RULE).** Canonical UCI, SAN, mover colour, mover `PieceId`, from and to;
  flags: capture, en passant, promotion piece, castling side, gives check, gives mate; captured
  `PieceId` and victim square. Capture and promotion in one ply are two ordered facts (lesson A4).
- **Identity transitions** (section 4).
- **`delta` (EDGE).** Defined exactly by F2-D §7.1 (`delta_v1`): identity-keyed set differences of
  the side-independent `pieces`, `lines`, `pawns` and `king` facts, with a class per component.
  Material changes are `move` events; pattern changes are `pattern_delta` (F3-D §4), which
  also carries `DEFENCE_ENDED_UNDER_ATTACK`.
- **`same_side_delta` (SPAN, RULE).** Side-dependent facts (legal destinations, legal captures,
  capturability, legal flight squares) are compared only between a node and its grandparent,
  which have the same side to move (lesson D2). Defined exactly by F2-D §7.2.

### 6.11 Excluded from v1
- `opponent_view` (null-move view of what the side not to move could capture or check); the
  opponent's real options are recorded at the child nodes.
- Static exchange evaluation (attacker-order choice needs a policy); "trapped piece" (needs a
  safety definition); space and mobility scores; any engine-free evaluation.

These can enter later only as new `DEFINED` families with a reviewed definition.

## 7. Engine facts (ATTESTED)

### 7.1 Profile, identity and engine state (B2–B4, C9)

```text
EngineProfile(name, version,                     # default "d12_mpv5_v1"
  limit: depth 12 + time cap 2000 ms,           # depth | nodes; pure time limits allowed, marked
  multipv: 5, threads: 1, hash_mb: 16,
  options: {UCI_ShowWDL: true if offered},
  state: FRESH_PER_SEARCH)
```

- **Fresh state per search.** Before every search the adapter sends `ucinewgame` and clears the
  hash. With python-chess this means passing a **new `game` object to every `analyse` call**
  (python-chess sends `ucinewgame` only when `game` changes; legacy passed one per request,
  `stockfish/adapter.py:134-141`) and sending `setoption name Clear Hash`. Verified: with this,
  depth-limited results are identical after unrelated searches and in a fresh process; without
  `ucinewgame`, 2 of 3 test positions changed.
- **Engine identity** recorded on every search: name, version, `EvalFile` and `EvalFileSmall`
  when offered (Stockfish 17 loads two nets; Stockfish 19 offers one, F4-D M1), the binary's
  sha256, and every option value actually set (F4-D §3.2).
- **WDL.** The profile sets `UCI_ShowWDL` when the engine offers it. WDL is `UNAVAILABLE` only when
  the engine does not offer it, never because it was not requested. WDL is Stockfish's model of
  score and material (`search.cpp:2066`), recorded as attested, not as independent evidence.
- **Stops.** Every search records `stopped_by = DEPTH | TIME` and the reached depth of every
  line. Measured survey median is 181 ms, so the 2000 ms cap is rarely reached.

### 7.2 Search record (C3, C5)

```text
EngineSearch(search_id, input: EngineInput, kind: SURVEY | COMPARISON | ANALYSIS, profile, engine_identity,
  root_moves: tuple[UCI] | None, multipv, stopped_by, regular: bool,
  lines: tuple[EngineLineFact, ...])
EngineLineFact(rank, move, score: Cp(white_pov) | Mate(winner, moves), bound: EXACT | LOWER | UPPER,
  wdl: WDL | UNAVAILABLE, depth, seldepth, nodes, tbhits, pv: tuple[UCI, ...])
SearchRuntime(rev, search_id, elapsed_ms, reused)  # metadata, not a fact; outside the digest
```

Exact shapes, the raw-UCI adapter and `stopped_by` as decided by the adapter are in F4-D §3 and
§5 (amended by F4-D).

- **Normalization** (kept from legacy): scores from White's point of view; mate as (winner,
  moves) with `Mate(0)` mapped explicitly; every PV move canonicalized and replayed for legality
  from the search position. An illegal PV refuses the search with a typed error; it is never
  repaired or cut.
- **Regular and irregular searches.** A search is `regular` iff it stopped by `DEPTH` and every
  line is `EXACT` at the requested depth. A time-stopped search can mix depths across ranks and
  carry bound scores on the line being searched (`search.cpp:2037-2043, 2051, 2079-2080`). Such a
  search is recorded faithfully (`regular = false`, per-line depth and bound), but it is **never
  a comparison basis** and **never enters the result store**.
- **Score and board are separate facts.** A cp score whose PV ends in checkmate keeps both;
  neither is inferred from the other (lesson B5).
- **Searches are bound to their input, not to a node.** `search_id` is content-derived (3.1).
  Nodes reference searches through revision-stamped `NodeSearch(node, rev, search_id)` entries; a
  search reused at another node with the same `EngineInput` is the same record referenced twice.
- `EngineStability` is dropped (never filled in legacy).

### 7.3 Comparable searches and the basis rule (B3, C6, N5, N6)

Scores from different searches are **not comparable**. Measured on the P2-C1 position (played
f4h6 = Qh6, Stockfish 17, depth 12), independently reproduced in the A0 review:

| Move | Survey MultiPV 5 | Played-only (legacy) | Comparison (6 moves) | Pair (legacy P2-C1) |
| --- | --- | --- | --- | --- |
| Qf6 | +422 (rank 1) | | +415 (rank 4) | +456 (rank 1) |
| Re7 | +372 (rank 2) | | +461 (rank 1) | |
| Qh6 (played) | not ranked | +321 | +325 (rank 6) | +251 |

- `SURVEY` at an input-role node N: unrestricted MultiPV K.
- `COMPARISON` at N: one search with `root_moves = survey moves ∪ every current PLAYED / EXPLORED
  child move of N`, MultiPV = size of that set. It runs when at least one such child is outside
  the survey moves. Engine-only and `ANALYSIS` children never trigger it, so the set of searches
  does not depend on build order, and the basis of a played move never depends on which probes a
  downstream block requested (R3-C2). An `ANALYSIS` request that needs comparable scores asks for
  its own comparison through its expansion; that search is recorded as an attested fact and is
  never N's basis.
- **Re-comparison.** When a later revision gives N a `PLAYED` / `EXPLORED` child outside the
  current comparison set — a new child, or an existing engine-only or `ANALYSIS` child that gains
  one of these roles — the comparison is run again over the enlarged set. If the latest entry is
  `NOT_COMPUTED` (budget or irregular), the set is rebuilt from the survey moves plus all current
  `PLAYED` / `EXPLORED` children (R3-C4).
- **Basis.** The basis of N is a revision-stamped node-level record:
  `BasisEntry(node, rev, search_id | NOT_COMPUTED(reason))`. The entry with the highest
  `rev ≤` the reader's revision applies to **every child of N**.
  - No comparison needed so far → basis = the survey (R3-N3).
  - Otherwise → basis = the latest comparison; the survey stays as an attested fact
    ("unrestricted candidates"), never as a basis.
  - Comparison skipped (budget) → `NOT_COMPUTED(BUDGET)`, never the survey (C6).
  - Survey or comparison irregular (7.2) → `NOT_COMPUTED(IRREGULAR_SEARCH)`.
  - N terminal or `after_terminal` → `NOT_APPLICABLE`.
  - N engine-only (never searched) → `NOT_COMPUTED(PARENT_NOT_SEARCHED)`.
- **Children outside the basis search.** A child of N whose move is not in the basis search's
  root-move set (for example an engine-only child from the parent's PV) has no rank there: its
  basis reading is `NOT_IN_BASIS`, never a borrowed score (R3-C4).
- Disagreements between survey and comparison (rank 1, scores) are recorded, not resolved.
- **Scores carry their search.** Scores are exposed as `SearchScore(search_id, rank, value)`; the
  ordering helper the tree provides refuses operands from different searches. This prevents the
  easy mistakes (e.g. survey Qf6 − comparison Qh6 = 97, a number no search produced). A consumer
  that extracts raw integers can still subtract across searches, e.g. "child survey − parent
  survey" (the legacy eval-before/after pattern); that is outside the tree's guarantees and is a
  rule for downstream blocks.
- **Cost.**
  - Per node a comparison is more expensive than legacy's played-only search: on the P2-C1
    position, survey 132 ms, union comparison 120 ms, played-only 31 ms.
  - In aggregate it costs less than legacy's fixed second search only while comparisons are rare
    (2 of 33 input nodes in the Opera game).
- **Legacy, for reference.** Legacy always ran MultiPV 5 plus a played-only search. It computed
  the loss across those two searches. An inversion within 20 cp was clamped to zero; only beyond
  20 cp did it run a paired search. Comparable numbers were therefore produced only after a
  visible inversion.

### 7.4 Engine input (B1)

The engine receives exactly what Stockfish's repetition and fifty-move logic can use, and
nothing that it cannot:

- `window(node)` = the last `w` plies before the node, with
  `w = min(halfmove_clock(node), known_plies(node))`. Stockfish checks repetitions over
  `min(rule50, pliesFromNull)` plies (`position.cpp:838-853`), and `pliesFromNull` is reset by a
  FEN `position` command (`position.cpp:203`).
- `EngineInput(node)` = (FEN of the position at the window start, the window moves in canonical
  UCI). The FEN is normalized to what Stockfish can distinguish (R3-N1): the en passant square is
  written only under the engine's own condition. For Stockfish 17 that was an enemy pawn able
  to capture pseudo-legally (python-chess `en_passant="xfen"`); for Stockfish 19 it is a legal
  capture (`en_passant="legal"`, F4-D §4, M3), the halfmove clock is kept, and the fullmove number is
  written as 1 (Stockfish uses it only for time management). The normalized form is exactly what
  is sent, so the key is still "what the engine received". F4 acceptance repeats the review's
  equivalence test (trimmed normalized input vs full history, identical lines; ep A/B case
  separated).
- Sending the window-start FEN plus the window moves gives Stockfish the same `rule50` and the
  same repetition window as sending the full game. Nothing from before the window reaches the
  search: root-level `priorCapture` / `prevSq` are gated on a previous move that does not exist
  at the root (`search.cpp:552, 625, 734`).
- With incomplete history, the engine sees exactly the known window, as this tree does.
- `EngineInput` keeps the engine's own en passant behaviour inside the key. On Stockfish 17 two
  histories equal under `PositionKey` could differ for the engine (review experiment: `b8g3
  +521` vs `b8b3 +708`) and had different `EngineInput`s. On Stockfish 19, which uses the legal
  square, such histories map to one `EngineInput`, correctly (F4-D §4).

### 7.5 Engine lines and family tiers (C4, C7)

**The tree is the input lines plus the engine's lines.** Every PV returned at a searched
input-role node is attached as nodes with `ENGINE` roles, under the expansion of that node's
role (7.6).

- A PV that starts with the next input move runs along the input nodes while the moves agree
  (shared nodes, both roles), and forks where they differ.
- **Attachment stops at a terminal node** (checkmate, stalemate, automatic draw; 7.8). The
  `EngineLineFact.pv` tuple always keeps the complete PV; the `LineRecord` ends with the terminal
  kind and `unattached_plies` = the PV plies after it. Example from the review: from
  `8/8/4k3/8/8/2n5/4P3/4K3 w`, PVs of length 8–11 reach insufficient material after 2 or 8 plies.
- Engine-only nodes are not searched by default.
- **Search depth is not PV length.** At depth 12 over 165 PVs: median 11 plies, min 1, max 21
  (median seldepth 16). An optional `pv_plies` cap is a cap, not a guarantee; it removed only 8%
  of PV nodes on the sample.
- **Family tiers.**
  - Input-role nodes: every requested family, eagerly.
  - Engine-only nodes: the *eager tier* — header, identity, `status`, `material`, `draw`, `move`.
    The others (`pieces`, `squares`, `lines`, `pawns`, `king`, `patterns`, `delta`,
    `same_side_delta`, `pattern_delta`) are `NOT_COMPUTED(TIER)` until `ensure` computes them from the node's
    stored position, with the same family code and version, at a new revision.
  - When an engine-only node gains an input role, the missing families are computed at that
    revision.
- **Cost.** Opera game sample (33 input plies, MultiPV 5, depth 12):
  - Engine-line attachment adds 1,601 nodes (about 48 per input node).
  - Eager tier: 0.71 ms (`status`) + 0.30 ms (draw claims) per node, measured independently, so
    about 2–3 s for 1,601 nodes.
  - Engine survey time: 6.2 s.
  - Legacy full extraction measured 5.6 ms per position including re-projection.

### 7.6 Expansion policy (default)

| Role of node | Survey | Comparison | Engine lines attached |
| --- | --- | --- | --- |
| `PLAYED`, `EXPLORED` | yes | yes, if a `PLAYED` / `EXPLORED` child is outside the survey | every PV of every search at the node |
| `ANALYSIS(by)` | as the request states (no default) | as the request states | as the request states |
| engine-only | no | no | — |
| `after_terminal`, terminal | no (`NOT_APPLICABLE`) | no | — |

A node holding several roles gets the **union** of their expansions (a `PLAYED` node that is also
`ANALYSIS` is searched as `PLAYED`, plus whatever the analysis request asked). The start node of
an `InputLine` gains that line's role at index 0, so a line started from an engine-only node makes
that node searchable under the line's role (R3-C4).

### 7.7 Engine result store (B1, C3, C5, C8)

- `EngineResultStore` memoizes finished **regular** searches by
  `(EngineInput, kind, root_moves, multipv, profile, engine identity)`, which is the `SearchId`
  preimage. A hit returns the stored `EngineSearch` and runs no engine.
- Irregular searches (time-stopped or with bounds) are never stored, so later trees cannot
  become deterministic by accident. Within one session, an irregular search is reused for an
  identical request instead of searching again, so one session never holds two different
  results for one engine question.
- Reuse is recorded in the revision's manifest delta (`REUSED`), outside the digest (3.5).
- The store can persist across sessions and serves as the test tape. A persisted store is an
  ingestion source (9.1).

### 7.8 Terminal and draw nodes (decided 2026-10-08)

| Situation | Legacy | Policy here |
| --- | --- | --- |
| No legal moves: checkmate, stalemate | adapter refused (`EngineAnalysisError`); P7 recorded `TerminalOutcome` from rules without an engine call; ALTERNATIVE / IGNORE_THREAT refused | no search (`NOT_APPLICABLE`); node `terminal = CHECKMATE / STALEMATE`; no repeated cross-checks |
| Root itself terminal | request error | valid tree; no searches |
| Ordering terminal outcomes against scores (P8 `_outcome_key`) | in the explainer | downstream; the fact engine records only the terminal kind |
| PV ends in mate while the score is cp | kept separate (CR2) | kept separate (7.2) |
| Threefold, fifty-move (claimable) | not modelled; engine got no history | `draw` facts; node still searched (the game continues unless claimed; Stockfish scores repetitions internally) |
| Fivefold, seventy-five-move (automatic) | not modelled | `terminal = AUTOMATIC_DRAW(kind)` when proven by known history (2.2); no search; engine-line attachment stops there. If fivefold can be neither proven nor ruled out, `terminal = UNPROVEN(HISTORY_UNKNOWN)`; the node is searched normally (the engine sees the same window) |
| Insufficient material | not modelled | `terminal = AUTOMATIC_DRAW(INSUFFICIENT_MATERIAL)` under python-chess's conservative test (a subset of FIDE dead positions; the definition is named in the manifest) |
| Input moves after an automatic draw | — | accepted, `after_terminal`, not searched (2.3) |

## 8. What the engine does **not** produce

Move-quality labels, accuracy, centipawn loss, "best response", threats, refutations, causes,
claims, selections, sentences in any language.

`MoveJudge` and every P7–P12 concept are downstream blocks. A downstream block that needs more
lines (what legacy P7 did with probes) calls `extend(..., role=ANALYSIS(by), expansion=...)`.
The fact engine never adds engine work on its own initiative.

## 9. Trust boundary (lessons E1–E3, C8)

1. **Validation happens only at ingestion**:
   - requests (parsing, canonicalization, legality, budget);
   - engine output (normalization, PV legality, regularity);
   - a persisted `EngineResultStore` (decoded entries are re-keyed from their content and their
     PVs replayed for legality before use);
   - a stored tree (2 below).
   Nothing inside the fact engine re-validates a record it produced itself.
2. **Construction is the only path.** Records are frozen and created only by the fact engine.
   Constructors check cheap structural shape and nothing else. "Rebuild in `__post_init__` and
   compare" is banned (re-projecting `ActivityFacts` cost about 40% of activity time).
3. **Consumers trust.** They do not re-check checkmate, replay lines or recompute deltas. A
   consumer that needs a new fact asks for a family or an `extend`.
4. **Correctness is proven once, offline.** A test-only auditor rebuilds every family with a naive
   python-chess implementation and compares, over fixture corpora (G0, I1-D D01–D20, scenario
   E01–E15) and a game-replay fuzz of at least 400 games. It is never on the runtime path.
5. **Stored trees.**
   - Accepted only if `fact_tree_v1`, every family version, the engine identity **and the fact
     engine's build version** (`facts_build_version`) match, and the digest matches.
   - A digest proves integrity, not origin; trees are only loaded from storage the fact engine
     itself wrote.
   - A bug fix in a family without a version bump changes `facts_build_version`, so stale trees
     are rebuilt, never trusted.

## 10. Build and cost

- **Board view.** One internal python-chess `Board` (with move stack) per node during
  construction; bitboard attack maps computed once per `PositionKey` and shared by families.
- **Order within a request.**
  1. Validation and budget pre-check.
  2. Input nodes and their families.
  3. Surveys in line order.
  4. Comparisons and basis entries.
  5. Engine-line attachment (eager tier).
  6. Atomic commit of the revision.
- **Reference numbers.**
  - Legacy activity 4.6–5.9 ms per position.
  - Legacy I1–I3 opt-in 1150 ms per request.
  - Legacy 8-ply replay 85 ms, plus validation 227 ms.
  - New eager tier about 1 ms per node (7.5).
  - Engine time is governed by the profile and reported separately.

## 11. Package layout (new; independent of legacy)

```text
src/calliope/facts/
  request.py        OpenRequest, ExtendRequest, EnsureRequest, RootSpec, InputLine,
                    ExpansionSpec, SessionBudget
  keys.py           PositionKey, RootId, NodeId, EngineInput, SearchId, PieceId, canonical UCI
  tree.py           FactTree, FrameNode, PositionRecord, Edge, roles, LineRecord, BasisEntry,
                    manifest deltas, revision reads
  identity.py       piece identity advance
  board.py          BoardView (the only python-chess user besides ingestion)
  families/         status, material, pieces, squares, lines, pawns, king, patterns,
                    draw, move, delta, same_side_delta   (one FactFamily each)
  engine/           profile.py, stockfish.py (UCI, fresh state, normalization),
                    search.py (survey, comparison, basis), store.py (result store)
  engine.py         FactEngine: open / extend / ensure
  storage.py        canonical serialization, digest, tree loading
```

- Nothing in `calliope.facts` imports legacy packages. Shared vocabulary (`Color`, `PieceType`)
  is redefined in `facts/keys.py` (lesson G1).

## 12. Lessons → design rules

Evidence below refers to the frozen MVP (tag `legacy-mvp-g0`) and is evidence only, never a current
requirement. Short names map to legacy documents and code as follows:
`p2-c1` → `docs/legacy/p2-c1-judgement-cross-search-stabilization-design.md`;
`G0 §…` → `docs/legacy/mvp-g0-application-integration-design.md`;
`I1–I3 §…` → `docs/legacy/observation-bridge-i1-i3-implementation.md`;
`positional F…` → `docs/legacy/positional-foundation-review.md`;
`A3 L…` → `docs/legacy/scenario-summary-a3-corrections.md`;
`activity semantics` → `docs/legacy/positional-activity-design.md`;
`core-models` → `docs/legacy/core-models.md`;
`P8 …` / `P10 …` → `docs/legacy/mvp-p8-bad-move-design.md` / `docs/legacy/mvp-p10-evidence-claim-design.md`;
file names such as `adapter.py`, `facts.py`, `positional.py`, `piece_identity.py` → the legacy
modules under `src/calliope/` at that tag.

| Legacy problem | Evidence | Rule here |
| --- | --- | --- |
| Castling aliases escaped canonicalization | `3fd7868`, `811f28b` | one canonicalizer for input and PV moves (2.3) |
| Malformed UCI reached records | `7628ed5` | structural UCI rule in `keys.py`, typed errors only |
| ep square in FEN without legal ep; `position_id` over clocks | `adapter._canonical_fen` | `PositionKey` uses legal ep only; clocks on the node; engine keyed separately by `EngineInput` (3.1, 7.4) |
| No history → no repetition or fifty-move facts | positional.py:102 | per-node history completeness, `draw` family (2.2, 6.9) |
| Promotion with capture dropped | `672f162` | two ordered facts in one edge (6.10) |
| Cross-search inversion P2-C1 | `985ab49`, p2-c1 §1 | survey / comparison, revisioned basis, `SearchScore` (7.3) |
| Hash and session carry-over | `0a37bf8`, G0 §15 | `ucinewgame` + Clear Hash per search, new `game` per call (7.1) |
| Time-bound nondeterminism, build dependence | P7 profile, I1–I3 §3 | depth limit + cap, `stopped_by`, irregular searches never basis or stored; engine identity incl. every offered network (both nets on Stockfish 17, one on Stockfish 19; F4-D §3.2) |
| Mate in PV vs cp score conflated | `b81c2a2` CR2 | score and board terminal are separate facts (7.2) |
| WDL missing treated ad hoc | judge fallback | `UCI_ShowWDL` set by profile; `UNAVAILABLE` only if not offered |
| `EngineStability` always UNKNOWN | adapter.py:154 | removed |
| Identity guessed or swapped by type and count | `646190f`, `de020c8` | identity composed only from the exact move (4) |
| Square without frame read as current | `9c9d5c8` | every piece reference carries its node (4) |
| Geometric/legal mixed in `hanging_now` | facts.py | split facts; legal values only for side to move (6.3) |
| Side-dependent diffs across a side flip | activity semantics | `same_side_delta` (SPAN) grandparent ↔ node (6.10) |
| Detector "candidates" drifted into claims | `b81c2a2` CR3, P10 B1–B3 | patterns are geometry predicates with neutral names (6.8) |
| Four independent replay loops, 6+ ply DTOs | inventory | one fact engine, consumers never replay (3.2) |
| Validation repeated 6–7×, re-projection ~40% cost | I1–I3 §4 | ingestion-only validation, offline auditor (9) |
| Identity in `services.explanation`, private cross-imports | positional F2, A3 L6 | neutral `facts/keys.py`, `facts/identity.py` (11) |
| Exact English bytes frozen during fact work | `5817595` etc. | no wording at all in this block (8) |

**Reused from legacy (as algorithms, rewritten):**
- Stockfish score, mate and WDL normalization, and refusal of bound-only scores.
- `Board.parse_uci`-based canonicalization.
- Pin resolution against ray occupants.
- positional_v1 pawn definitions.
- activity_v1 footprint and ray definitions.
- Identity-advance rules from `piece_identity.py`, without P8 error types.

## 13. Delivery packets

| Packet | Deliverable | Gate |
| --- | --- | --- |
| F0 (this) | architecture, fact classes, identities, tree and revisions, catalogue v1, engine search model, trust boundary | independent A0 review READY |
| F1 | `keys`, `request`, `tree` (revisions, roles), `identity`, `board`; families `status`, `material`, `draw`, `move`; `open` / `extend` without engine; auditor + 400-game fuzz | independent review READY |
| F2-D / F2 | definitions and implementation of `pieces`, `squares`, `lines`, `pawns`, `king`, `delta`, `same_side_delta`; `ensure` and tiers | READY each |
| F3-D / F3 | `patterns_v1` definitions with adversarial cases; implementation | READY each |
| F4-D / F4 | engine profile and fresh state, `EngineInput`, ingestion and regularity, survey / comparison / basis, engine-line attachment, result store, budget | READY each |
| F5 | canonical serialization, digest, tree loading, cost record against legacy numbers | READY |

## 14. Decisions (2026-10-08)

- **PV expansion.** Input lines plus every engine PV found at searched input-role nodes, attached
  until a terminal node; engine-only nodes not searched by default (7.5, 7.6).
- **Value-ordered geometry.** Included: `RELATIVE_PIN_GEOMETRY`, `SKEWER_GEOMETRY`, `points_v1`
  under the versioned `piece_order_v1` and points table (6.2, 6.8).
- **Node header** carries `side_to_move`, the full position and the other header fields (3.2).
- **Engine state.** Fresh state per search plus a result store for regular searches (7.1, 7.7).
- **One tree with roles.** `PLAYED`, `EXPLORED`, `ANALYSIS`, `ENGINE` (3.2).
- **Append-only revisions**, one per committed request; take-backs not modelled (3.3).
- **Requests.** Facts enter only through `open` / `extend` / `ensure`; a user move and a block's
  analysis request share one path (2.1).
- **Comparison and basis.** Union comparison over survey and input-role children; revisioned
  basis per node (7.3).
- **Engine-line volume.** MultiPV 5, eager tier on engine-only nodes, no `pv_plies` cap by
  default; to be revisited with measurements.
- **Opponent view.** Excluded from v1 (6.11).
- **Root forms.** All accepted; history completeness judged per node (2.2).
- **Time limits.** Depth 12 with a 2000 ms per-search cap; optional per-request deadline (7.1,
  2.4).
- **Terminal policy.** As in 7.8.

**STOP** if any packet:
- adds an evaluative word or value;
- stores cross-search arithmetic;
- infers engine terminal state from board state, or board state from engine output;
- repairs or truncates an illegal or mismatching line, or drops PV plies from `EngineLineFact.pv`;
- re-validates trusted records at runtime;
- makes an engine call that the request did not plan;
- returns a stored search for a different `EngineInput`.

## 15. Review dispositions (rev. 2 `e9338fc`, independent A0 review: NOT_READY)

| Finding | Disposition |
| --- | --- |
| B1 `SearchPosition` key unsound (Stockfish pseudo-legal ep, FEN resets `pliesFromNull`, three keyings) | `EngineInput` = window-start FEN as sent + window moves, window `min(halfmove_clock, known_plies)`; one key for searches, store and tape; `SearchId` content-derived (3.1, 7.2, 7.4, 7.7) |
| B2 "FEN + moves = KNOWN" false; sentinel contradictions | per-node `history_complete`; `AtLeast(n)`; `HISTORY_UNKNOWN` for unprovable negatives; one rule in 2.2 / 6.9 / 7.8; sentinel table (1) |
| B3 `engine_basis` vs append-only; order-dependent trigger | revision-stamped `BasisEntry` per node; trigger only on input-role children; re-comparison over the enlarged set (7.3) |
| C1 revision atomicity | one revision per committed request; per-revision manifest deltas (3.3) |
| C2 two API models; root id; budget scope | single session API; one-shot = open + extend; `RootId` from normalized `RootSpec`; `ExpansionSpec` per request and role; cumulative `SessionBudget` (2.1, 2.4, 3.1) |
| C3 reused-search line ids; nondeterministic ids and fields in digest | line id includes anchor; `SearchId` content-derived; `SearchRuntime` and `REUSED` outside the digest (3.2, 3.5, 7.2) |
| C4 truncating attested PVs at automatic draws; input past automatic draw | PV tuple kept whole, attachment stops at terminal with `unattached_plies`; input after automatic draw accepted, `after_terminal`, not searched (2.3, 7.5) |
| C5 time-stopped searches mix depths and bounds | `stopped_by`, per-line depth and bound; irregular searches never basis, never stored (7.2, 7.7) |
| C6 comparison skipped for budget | `BasisEntry = NOT_COMPUTED(BUDGET)`; pre-check assumes up to 2 searches per input node plus re-comparisons (2.4, 7.3) |
| C7 tiering contradiction; `ensure(delta)` | tiers stated once (7.5); `requires` resolved on parent nodes for EDGE / SPAN (5) |
| C8 store as ingestion source; stale trees | persisted store validated at ingestion; `facts_build_version` in tree acceptance; digest = integrity only (9) |
| C9 two nets, `UCI_ShowWDL` default, `ucinewgame` gating | identity records `EvalFile` and `EvalFileSmall`; profile sets `UCI_ShowWDL`; new `game` object + Clear Hash per search (7.1) |
| N1 two threefold notions | `threefold_reached` vs `threefold_claimable_by_move` (6.9) |
| N2 "never attack again" | `outside_enemy_pawn_cones`, current pawn set only (6.6) |
| N3 hanging replacement formula | `attacked ∧ ¬defended` (6.3) |
| N4 `SameSideDelta` scope; square-keyed deltas | `SPAN` scope; piece relations keyed by `PieceId` (5, 6.10) |
| N5 per-node cost claim | corrected with measured numbers (7.3) |
| N6 "cross-search arithmetic impossible" overclaim | `SearchScore` with same-search ordering; residual risk stated as a downstream rule (7.3) |
| N7 `ANALYSIS` volume | no default expansion for `ANALYSIS`; the requester states it (2.1, 7.6) |
| N8 canonical order of `ENGINE` roles | specified (3.5) |
| N9 feasibility | measured eager-tier cost recorded (7.5) |

Rev. 3 (`fc15c86`, re-review READY_WITH_CORRECTIONS):

| Finding | Disposition |
| --- | --- |
| R3-C1 header `NONE` as an unproven negative | `terminal = UNPROVEN(HISTORY_UNKNOWN)`; node still searched (3.2, 7.8) |
| R3-C2 `ANALYSIS` children change the played move's comparison | union over `PLAYED` / `EXPLORED` children only; `ANALYSIS` comparisons are separate searches, never N's basis; multi-role nodes get the union of expansions (7.3, 7.6) |
| R3-C3 `SearchId` collision for irregular searches; digest claim | irregular ids include a digest of their lines; in-session reuse of irregular searches; digest determinism qualified (3.1, 3.5, 7.7) |
| R3-C4 basis coverage holes | `NOT_IN_BASIS`, `NOT_COMPUTED(PARENT_NOT_SEARCHED)`, `NOT_APPLICABLE` for terminal parents; re-comparison after `NOT_COMPUTED` and on role gain; line start node gains the line's role (7.3, 7.6) |
| R3-N1 `EngineInput` over-distinguishes | ep written under Stockfish's condition (`xfen`), fullmove normalized; equivalence test in F4 acceptance (7.4) |
| R3-N2 `delta` class label | per-component class (6.10) |
| R3-N3 basis wording | "no comparison needed so far" (7.3) |
