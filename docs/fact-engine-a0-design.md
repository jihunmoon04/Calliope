# Fact engine — normalized, trusted chess facts over a frame tree (A0 design draft)

Status: **DRAFT rev. 2 (self-review applied) / AWAITING INDEPENDENT A0 REVIEW** (design only; nothing
implemented). Date: 2026-10-08. Base: `main @ 4940554`.

Supersedes: the analysis-trace A0 / R1-D direction (`design/analysis-trace-a0`,
`design/analysis-trace-r1d`), which kept the legacy P7–P12 path frozen and captured it. That
direction is abandoned. This packet starts the ground-up redesign at its lowest layer.

## 0. Decisions

1. Calliope is rebuilt as composable blocks with one role each. This packet covers **only the
   first block**: the *fact engine*, which normalizes input with python-chess and Stockfish.
2. The fact engine is one large **fact emitter**. For a root position and the supplied lines it
   builds a **tree whose nodes are frames** and records, per frame and per move, every fact that
   can be computed.
3. It records **facts only**. It has no evaluation words, no hypotheses, no causes, no selection,
   no explanation, and no move-quality labels. Explanation layers are later blocks that consume
   this output.
4. The output is **trusted by construction**. Consumers use it without re-validation.
   Correctness is established once, by the builder and its test suite, not again at runtime by
   every reader (section 9).
5. The public API may break. Legacy schema 0.2/0.3 is not preserved by this block, and legacy code
   is neither ported nor wrapped. Legacy algorithms are reused only where section 12 marks them as
   reusable.

## 1. What counts as a fact

A record is admitted to the tree only if it falls into one of three classes. The class is part of
its type.

| Class | Definition | Examples |
| --- | --- | --- |
| `RULE` | Follows from the rules of chess for this frame, with no parameters | legal moves, check, checkmate, stalemate, repetition count, material counts, geometric attacks |
| `DEFINED` | Deterministic function of `RULE` facts under a named, **versioned definition** | isolated pawn (`pawn_v1`), relative-pin geometry (`piece_order_v1`), king-zone squares (`king_zone_v1`) |
| `ATTESTED` | A recorded observation from an external oracle, with complete provenance | "Stockfish 17 with profile `d12_mpv5_v1` searched node N and reported line 1 = e4, cp +31, depth 12" |

Admission rules:

- **No evaluative vocabulary in names or values.** Forbidden: good, bad, weak, strong, safe,
  dangerous, threat, winning, hanging, mobility (as a quality), forced, best (except as the
  engine's *reported* rank 1), loss, blunder.
  - Legacy `hanging_now` is replaced by separate measured facts (section 6.3).
- **An `ATTESTED` fact is a fact about the report, not about the position.** The tree asserts
  that the engine said X under setting S. It does not assert that X is true.
- **Undefined is never zero or false.** The typed sentinels are:
  - `NOT_OBSERVED`: the value is side-dependent and undefined for this frame.
  - `NOT_APPLICABLE`: for example, an engine search at a checkmate or stalemate node (7.8).
  - `NOT_COMPUTED`: the family was not requested.
  - `UNAVAILABLE`: the engine does not provide the value, for example WDL.
- **No arithmetic across incompatible sources.** The tree stores no score differences, no loss,
  and no "A better than B" except inside one comparable engine search (section 7.3).

## 2. Inputs

```text
FactRequest(
  root: RootSpec,                     # FEN, or startpos/FEN plus game moves leading to the root
  lines: tuple[InputLine, ...],       # each: label, moves (UCI or SAN), rooted at the root frame
  expansion: ExpansionSpec,           # engine-PV expansion depth, engine-search policy per origin
  families: FamilySelection,          # default: all RULE and DEFINED families
  engine: EngineProfile | None,       # None → no ATTESTED facts at all
  budget: Budget,                     # max frames, max engine searches, max engine nodes
)
```

Input rules, from lessons A1–A3 and G:

1. **Every root form is accepted** (decided 2026-10-08):
   - **startpos + game moves** and **FEN + moves played from it**: the moves are replayed, so the
     history is `KNOWN`. Repetition and clock facts at and after the root are then exact, and the
     engine receives the same history (section 7.4).
   - **Bare FEN**: the history before the root is `UNKNOWN`.
     - The halfmove clock from the FEN is used as given.
     - Repetition counts only cover positions inside the tree, and the manifest says so.
     - Claims that depend on earlier history (threefold before the root) are `NOT_OBSERVED`.
     - The engine sees only the same truncated history. That is recorded as a property of its
       searches, never hidden.
2. **One canonicalizer.** Every move goes through one board-aware function before it becomes an
   edge, a dedup key or an engine argument. This covers input UCI, input SAN and every engine PV
   move.
   - It maps all 8 castling notations (king-to-rook included) to standard king-move UCI.
   - It rejects null moves and malformed promotion suffixes.
   - Variant: standard chess only. Chess960 is a typed refusal (`UnsupportedVariant`).
3. **Fail before engine work.** Every input line is fully parsed and checked for legality before
   the first engine call. An illegal line refuses the whole request with the line label and ply,
   and makes zero engine calls.
4. **Budget.**
   - Input lines and the number of planned input-node searches are checked before any work; a
     request whose input alone exceeds the budget is refused.
   - Engine-line size is unknown until the searches return (PV length 1–21 at depth 12), so it
     cannot be pre-checked. Limits on it (`max_frames`, optional request **deadline**) are applied
     during the build in a fixed priority: input-node surveys in line order → comparisons → engine
     line attachment → on-demand families.
   - Work not done because of a limit is recorded (`BUDGET_LIMIT` line end, coverage manifest), and
     the request still succeeds. Nothing is truncated silently.

## 3. Output: the fact tree

```text
FactTree (fact_tree_v1)
 ├─ manifest      versions of every family, engine identity + profile, input digest, coverage
 ├─ positions     PositionKey → PositionRecord        (shared; content-addressed)
 ├─ nodes         NodeId → FrameNode                  (path-dependent; the tree itself)
 ├─ edges         EdgeId → Edge                       (move between two nodes)
 ├─ lines         LineId → LineRecord                 (labelled paths: input lines, engine PVs)
 └─ searches      SearchId → EngineSearch             (ATTESTED; bound to a node)
```

### 3.1 Two identities (lesson A5)

| Id | Composed of | Used for |
| --- | --- | --- |
| `PositionKey` | piece placement, side to move, castling rights, **legal** en passant square only | sharing position-only facts across transpositions and prefixes |
| `NodeId` | parent `NodeId` + canonical move (root: request digest) | the tree node; anything that depends on path or clocks |

- The legacy `position_id` hashed the full FEN, clocks and non-legal ep square included. That made
  transpositions look different. It also never carried history, so draws by repetition were
  invisible. Both problems disappear with this split.
- `PositionRecord` holds facts that depend only on the `PositionKey`.
- `FrameNode` holds path-dependent facts: clocks, repetition, draw claims, piece identity, ply, and
  engine searches. Engine searches are path-dependent because the engine sees the move history.
- **Node header.** Every `FrameNode` carries these fields directly, not only inside a family:
  - `side_to_move`
  - `ply` (from the root), `fullmove_number`, `halfmove_clock`
  - `fen`: the full current position (placement, side, castling, ep, clocks), so every node is
    self-contained
  - `parent` and the incoming `edge`, including its mover
  - `terminal`: `CHECKMATE`, `STALEMATE`, `AUTOMATIC_DRAW(kind)` or `NONE`

  - `rev`: the tree revision at which the node was added (3.2)

  Roles (which lines pass through the node) are kept as revision-stamped entries next to the node,
  not in the header (3.2).

  A consumer never has to open a family to learn whose turn it is.

### 3.2 Nodes, edges and lines

**One tree; input and engine are roles, not separate structures** (decided 2026-10-08).

- **One node per distinct path.** `NodeId` = parent + canonical move (3.1). An engine PV move and an
  input move that are the same move from the same node are **the same edge and the same child
  node**. Nothing is duplicated.
- **Membership is recorded as a set of roles** on nodes and edges, each entry stamped with the
  revision at which it was added:
  - `PLAYED(label, index)` — a move actually played in the game being analysed;
  - `EXPLORED(label, index)` — a line the user asked to explore;
  - `ANALYSIS(by, label, index)` — a line requested for analysis by a downstream block (3.5),
    never shown as a user move;
  - `ENGINE(search_id, rank, pv_index, line_depth, line_seldepth)` — the node/edge lies on a PV
    reported by that search, at ply `pv_index`; depth and seldepth of that PV are carried so a
    consumer can see how deep into the PV a node lies.
  `PLAYED`, `EXPLORED` and `ANALYSIS` are the *input* roles. A node may hold several roles. "The
  engine's line at A began with the move that was played" is simply an edge that carries both
  roles; it is read from the tree, not stored as a separate number.
- **Input status follows the user's moves.** When the user plays (or asks to explore) a move along
  an existing engine line, those nodes gain input roles. Every input-role node is searched under the
  default policy (7.6), so its own engine lines grow from it. Nodes that only carry `ENGINE` roles
  are not searched by default.
- **Append-only tree with revisions** (decided 2026-10-08).
  - There is one tree per analysis session. It is never copied into versions and nothing in it is
    ever modified or removed.
  - Every addition gets the next tree revision `rev`: a node, an edge, a role entry, a search, or
    an on-demand family record (7.5).
  - Chess facts never change once written; a node only *gains* roles and records.
  - Readers see the latest revision by default. A reader can also pin a revision and read the
    tree "as of rev r" (everything stamped ≤ r), which reproduces the state an earlier output was
    built from.
  - One writer (the fact engine) at a time. A reader that pins its revision at the start never
    sees a half-finished extension.
  - Take-backs are not modelled. Going back is just reading or extending from an earlier node;
    roles that were added stay, because they record what was requested at that revision.
- **Engine lines stay recoverable as wholes.** Each PV keeps its `LineRecord` (`ENGINE_PV(search_id,
  rank)`, the full node path, end status) even when part of it later becomes input, so "what the
  engine proposed at A" is never overwritten by what was played afterwards.
- **Transpositions.** Different paths to one position are different nodes that share one
  `PositionRecord`.
- `Edge(parent, child, roles, move facts)`. Edge facts are computed once, from the two records and
  the move (section 6.10).
- `LineRecord(label, origin, node path, end status)`.
  - Origins: `PLAYED(label)`, `EXPLORED(label)`, `ANALYSIS(by, label)` and `ENGINE_PV(search_id, rank)`.
  - End status is one of `CHECKMATE`, `STALEMATE`, `DRAW_RULE(kind)`, `INPUT_END`,
    `PV_END(engine_pv_length)`, `EXPANSION_LIMIT` or `BUDGET_LIMIT`. Truncation is a recorded fact, never an
    implicit end.
- **No replay outside the fact engine.** Consumers walk nodes and edges. They obtain new facts
  only by asking the fact engine (3.5), never by computing them.

### 3.3 Coverage manifest

For every family the manifest records:
- its version;
- whether it was computed, and on which node set (all nodes, input-role nodes, engine-only nodes);
- for engine searches, which nodes were searched and which were not, and why (policy or budget).

A consumer can therefore tell "empty" apart from "not computed" without guessing.

### 3.4 Canonical order

Every tuple in the tree has one canonical order so that serialization and digests are
deterministic: squares by index a1…h8; pieces by (square index, colour, type); moves by canonical
UCI; children by canonical UCI; roles by (kind, label, index); searches by (kind, root moves);
engine lines by rank.

### 3.5 Requests to the fact engine

Every fact enters the tree through the fact engine. Blocks never construct facts themselves.

```text
FactEngine.open(root, profile, budget)              -> session tree, rev 0 (root node + searches)
FactEngine.extend(tree, lines, role)                -> new rev
    role = PLAYED | EXPLORED | ANALYSIS(by)          # same build path for all three
FactEngine.ensure(tree, nodes, families)            -> new rev (on-demand families, 7.5)
```

- `extend` is how a user move is added and how a later block asks for an analysis line; both go
  through the same validation, canonicalization, fact families and search policy. Only the role
  differs.
- A request is validated before any work (2.3) and returns the revision that contains its
  result. Results are read from the tree.
- python-chess is used only inside `calliope.facts`. Whether later blocks may import it at all
  is decided with those blocks; the contract here is that facts they rely on come from this
  engine.

## 4. Piece identity (lessons C1–C5)

- **Root identity.** Every piece on the root frame receives a `PieceId` from its root square,
  colour and type (for example `w.N.g1`). Piece ids are global across the whole tree, so the same
  physical piece compares equal in every branch.
- **Assignment is per frame.** `PositionRecord` facts refer to **squares**, which keeps them
  shareable across transpositions. `FrameNode.pieces` maps square → `PieceId` for that path, and
  consumers resolve squares to ids through the node.
- **Advancing identity across an edge** is composed only from the exact move:
  - The mover goes from its source to its target, with the canonical UCI.
  - Castling moves the king and the rook between their standard endpoints.
  - En passant captures on the victim square, not the landing square.
  - Promotion keeps the pawn's `PieceId` and changes its type.
  - Every other piece is unchanged.
  - Nothing is guessed from piece type or count.
- **Capture lifecycle.** A captured piece gets `captured_at(edge)` and no square afterwards.
  References to a piece captured on the previous ply stay resolvable through the edge.
- **Every piece reference carries its frame.** It is either `(node, square)` or
  `(node, PieceId)`. A bare square never travels without its frame (lesson C5).

## 5. Fact families: the blocks

Every family implements one interface: the common connector that lets blocks fit together.

```python
class FactFamily(Protocol):
    name: str            # e.g. "pawns"
    version: str         # e.g. "pawns_v1"
    scope: Scope         # POSITION | FRAME | EDGE
    requires: tuple[str, ...]   # other families it reads (acyclic)
    def compute(self, ctx: FamilyContext) -> FamilyRecord: ...
```

- `FamilyContext` gives read-only access to the frame's internal board view, which is built
  **once** per `PositionKey` (section 10), and to the records of required families.
- A family never calls python-chess outside the board view, never calls the engine, and never
  re-validates its inputs.
- Adding a family takes one module and one registry entry. Changing a definition takes a new
  version string, and old versions stay addressable in the manifest.
- Families are pure: the same inputs and version give the same record. This purity makes the
  sharing in section 3.1 sound.

## 6. Fact catalogue (v1 proposal)

The catalogue is drawn from the facts legacy already computed: P4 facts, P5 delta, P6 detector,
positional_v1, activity_v1 and the P8/P9 replay helpers. Anything not listed is out of v1.

### 6.1 `status` (POSITION, RULE)
- side to move;
- in check and the checking pieces;
- checkmate, stalemate, insufficient material;
- legal move count and the legal moves (canonical UCI + SAN, canonical order);
- legal captures (capturer, victim, landing square, victim square, `en_passant`, promotion);
- legal checking moves, legal mating moves (mate-in-1, exact), legal promotions.

### 6.2 `material` (POSITION, RULE and DEFINED)
- counts by colour and type, and bishops by square colour (RULE);
- `points_v1` sums under the 1/3/3/5/9 table, labelled `DEFINED`. This is a counting convention,
  not an evaluation. The legacy P8/P9 weights 100/320/330/500/900 are a different convention; if a
  downstream block needs them they become `points_cp_v1`, a separate versioned definition, never
  a silent replacement.

### 6.3 `pieces` (POSITION, RULE)

Per piece:
- square, colour, type;
- geometric attack set: empty, friendly and enemy targets;
- geometric attackers and defenders of its square, each with its type;
- legal moves and legal captures **only for the side to move**, otherwise `NOT_OBSERVED`;
- absolute-pin status (pinner and line).

Derived counts are labelled geometric: attacker count, defender count, lowest attacker type.

The legacy `hanging_now` mixed legal and geometric notions. It is replaced by two separate facts:
- `attacked_geometrically ∧ defended_geometrically = false`;
- `legally_capturable_now`, for the side not to move.

### 6.4 `squares` (POSITION, RULE)
- per square: occupant, white attackers, black attackers;
- control counts per colour.

### 6.5 `lines` (geometry) (POSITION, RULE)
- per slider and direction: visible squares and first blocker;
- x-ray continuation past the first blocker, marked `XRAY`. It is never presented as an attack.
- batteries: aligned same-colour sliders on one line.

### 6.6 `pawns` (POSITION, DEFINED, `pawns_v1`)
Extends positional_v1:
- isolated, doubled, passed;
- supporters and phalanx neighbours;
- backward (definition frozen in F2);
- chain membership and islands;
- per-file pawn counts and the open / semi-open-for-colour status;
- squares that enemy pawns can never attack again (geometric, current pawn set). This is
  deliberately not called "outpost".

### 6.7 `king` (POSITION, DEFINED, `king_zone_v1`)
- king square;
- king-zone squares, with enemy geometric attackers per square;
- pawn-shield pawns;
- open and semi-open files on and next to the king file;
- legal flight squares (side to move) or geometric flight squares (other side, labelled).

### 6.8 `patterns` (POSITION, DEFINED, `patterns_v1`)

These are geometric configurations, recorded per frame as predicates. **A pattern asserts only
that the configuration holds, never that it wins, works or is a threat.** This replaces the P6
"candidates": the P6 names implied tactical success, and FORCED_RESPONSE was not a geometry at
all.

| Predicate | Definition (sketch; exact text frozen in F3) |
| --- | --- |
| `MULTI_TARGET_ATTACK(piece, targets)` | a piece geometrically attacks ≥ 2 enemy pieces |
| `ATTACKERS_EXCEED_DEFENDERS(piece)` | geometric attacker count > defender count |
| `UNDEFENDED_ATTACKED(piece)` | ≥ 1 geometric attacker, 0 geometric defenders |
| `ABSOLUTE_PIN(pinner, pinned, king)` | ray occupants exactly [pinned, king] |
| `RELATIVE_PIN_GEOMETRY(pinner, front, back)` | ray occupants [front, back] with back above front in `piece_order_v1` (K > Q > R > B = N > P) |
| `SKEWER_GEOMETRY(attacker, front, back)` | ray occupants [front, back] with front above back |
| `DISCOVERY_LINE(slider, blocker, target)` | own blocker is the only piece between own slider and an enemy piece |
| `SOLE_DEFENDER(defender, pieces)` | one piece is the only geometric defender of ≥ 2 friendly attacked pieces |
| `BACK_RANK_GEOMETRY(king)` | king on its first rank, no flight square off that rank, own pieces block the second rank |

### 6.9 `draw` (FRAME, RULE)
- halfmove clock, fullmove number;
- repetition count of this `PositionKey` within the repetition window (7.7), including the root
  history when it is `KNOWN`;
- claimable threefold, claimable fifty-move, automatic fivefold, automatic seventy-five-move.

All of these are `NOT_OBSERVED` when the history is unknown and the count cannot be exact.

### 6.10 `move` and `delta` (EDGE, RULE)
- **Move.**
  - Canonical UCI, SAN, mover colour, mover `PieceId`, from and to squares.
  - Flags: capture, en passant, promotion piece, castling side, gives check, gives mate.
  - The captured `PieceId` and the victim square.
  - Capture and promotion in one ply are two ordered facts (lesson A4).
- **Identity transitions** (section 4).
- **Delta.**
  - Set differences between the parent's and child's records, taken per family: attacks,
    defences, pins, each pattern predicate (began or ended), pawn flags, file status, material.
  - Side-dependent facts are diffed **only between frames with the same side to move** (k and
    k+2). Those diffs live on a two-ply `SameSideDelta` record, never on the one-ply edge
    (lesson D2).

### 6.11 Excluded from v1
- `opponent_view`: the null-move view of what the side not to move could capture or check. The
  opponent's real options are recorded at the child nodes. This can be added later as its own
  family.
- Static exchange evaluation: the attacker-order choice needs a policy.
- "Trapped piece": needs a safety definition.
- Space and mobility scores.
- Any engine-free evaluation.

These can enter later only as new `DEFINED` families with a reviewed definition.

## 7. Engine facts (ATTESTED)

### 7.1 Profile and determinism (lessons B2–B4)

```text
EngineProfile(name, version,             # e.g. "det_n1m_v1"
  limit: nodes | depth (time allowed only with reproducible=false),
  multipv: int, threads: 1, hash_mb: int,
  state: FRESH_PER_SEARCH)               # ucinewgame + cleared hash before every search
```

- **Default profile: one thread, fresh state, finished results memoized** (decided 2026-10-08).
  - With these settings a search depends only on (engine build, position with history, profile),
    not on the order of searches. That makes tree construction order-independent and repeatable.
  - The `EngineResultStore` (7.7) returns a stored search for an identical key instead of
    searching again.
  - A warm-hash profile can exist as an option. It is marked `reproducible = false`, because hash
    contents depend on search order and can carry path-dependent draw scores between paths that
    reach one position.
- The limit stays depth-based by default (legacy depth 12, profile `d12_mpv5_v1`). With one
  thread and fresh state a depth-limited search is repeatable (verified: identical lines after
  unrelated searches and in a fresh process). A nodes limit is an alternative profile.
- **Per-search time cap** (decided 2026-10-08): the default profile is depth 12 with a safety cap of
  2000 ms (the legacy P7 pattern). Every search records `stopped_by = DEPTH | TIME` and the depth
  actually reached; a search stopped by `TIME` is marked `reproducible = false`. Measured survey
  median is 181 ms, so the cap is rarely reached.
- Purely time-limited profiles stay possible. They carry `reproducible = false` in the manifest.
- Engine identity covers name, version, the option values actually set, and the NNUE net file
  name. P2-C1 goldens differed between Stockfish 17 and 19, so every search is pinned to its build.

### 7.2 Search record

```text
EngineSearch(search_id, search_position, kind: SURVEY | COMPARISON, profile, engine_identity,
  root_moves: tuple[UCI] | None, multipv,
  lines: tuple[EngineLineFact, ...])
EngineLineFact(rank, move, score: Cp(white_pov) | Mate(winner, moves),
  wdl: WDL(white, draw, black) | UNAVAILABLE,
  depth, seldepth, nodes, time_ms, tbhits, pv: tuple[UCI, ...])
```

- **Normalization**, kept from legacy because it worked:
  - Scores are stored from White's point of view. A mate is stored as (winner, moves), with
    `Mate(0)` mapped explicitly.
  - Only exact final scores are admitted. Bound-only infos are refused.
  - Every PV move goes through the canonicalizer and a legality replay. An illegal PV refuses the
    search with a typed error; it is never repaired or cut short.
- **Engine score and board state are separate facts.** For example, a cp score whose PV ends in
  checkmate keeps both, and neither is inferred from the other (lesson B5).
- A search is bound to its `SearchPosition` (7.7), not to a node. Nodes reference searches:
  `FrameNode.searches = (search_id, ...)`. A search reused from the result store at another node
  with the identical `SearchPosition` is therefore the same record, referenced twice.
- `EngineStability` is dropped. It was never filled in. A future multi-sample family can bring it
  back with a definition.

### 7.3 Comparable searches (lesson B1, P2-C1)

Scores from different searches are **not comparable facts**. Separately searching a move that the
first search placed lower can return a higher score, as in the f4h6 case (+622 against +588).

- `SURVEY` search at node N: unrestricted MultiPV K.
- `COMPARISON` search at node N, run only when N has tree children that the survey lines do not
  contain:
  - one search with `root_moves = survey moves ∪ child moves`;
  - MultiPV equal to that set's size.
  - All children and the survey moves are then ranked and scored **inside one search**.
- The tree marks which search is the comparison basis for each child edge
  (`Edge.engine_basis = search_id, rank`).

**Basis rule** (decided 2026-10-08):
- If no comparison ran at node N (every input move is in the survey), the survey is the basis for
  every child edge.
- If a comparison ran, it is the **only** basis for every child edge of N, including moves that
  also appear in the survey. The survey stays as an attested fact ("unrestricted candidates"),
  never as a basis.
- When the two searches disagree on rank 1 or on scores, both are recorded with their own
  `search_id`. The disagreement is not resolved, and it is expected: depth-limited searches over
  different root-move sets distribute effort differently.
- Measured example (P2-C1 position, played f4h6 = Qh6, Stockfish 17, depth 12):

  | Move | Survey MultiPV 5 | Played-only (legacy) | Comparison (6 moves) | Pair (legacy P2-C1) |
  | --- | --- | --- | --- | --- |
  | Qf6 | +422 (rank 1) | | +415 (rank 4) | +456 (rank 1) |
  | Re7 | +372 (rank 2) | | +461 (rank 1) | |
  | Qh6 (played) | not ranked | +321 | +325 (rank 6) | +251 |

  The same move differs by 30–90 cp between searches, and rank 1 differs. "Survey Qf6 − comparison
  Qh6 = 97" is a number that no search produced; the basis rule makes it unconstructible from the
  tree's comparison fields.

**Legacy behaviour, for reference** (`application/analyze_move.py`, `services/judgement/move_judge.py`,
`p2-c1-…-design.md`):
- Legacy always ran two searches: MultiPV 5, then a root-restricted search of the played move at
  MultiPV 1. The second ran even when the played move was already ranked in the first.
- When the played move was outside the MultiPV, the loss was computed **across those two
  searches**. An inversion within 20 cp was clamped to zero loss. Only an inversion beyond 20 cp
  triggered a third, paired search over (best, played) at MultiPV 2.
- So comparable numbers were produced only after a visible inversion. A biased cross-search
  difference below the tolerance was used silently.
- The design here never computes the cross-search difference. It runs the comparable search
  exactly when the played move is not in the survey, and is never more expensive than legacy's
  fixed two searches.

**Measured** (Stockfish 17, depth 12, MultiPV 5, one thread, fresh hash; aarch64 with 2 CPUs; the
33-ply Opera game; script in the F0 review notes):
- Survey: median 181 ms per node.
- Comparison was needed at 2 of 33 input nodes.
  - Union comparison (6 moves): median 193 ms.
  - Paired comparison (best, played) at MultiPV 2: median 68 ms.
- A strong game rarely needs comparison. Weaker play will need it more often.
- The tree stores no differences between searches. A consumer that compares moves uses the basis
  search, and the structure makes cross-search arithmetic impossible to do by accident.

### 7.4 Engine input

- The engine receives the root FEN **plus the move history** (root history and path), so
  repetition and fifty-move state are visible to it.
- Searches are therefore keyed by `NodeId`, not by `PositionKey`.

### 7.5 PV expansion

**Default: the tree is the user's lines plus the engine's lines.** Every PV that the engine
returns at an input-line node is attached to the tree **in full**, as a branch of nodes with origin
`ENGINE_PV(search_id, rank)`.

- This covers every MultiPV rank of the survey and every line of a comparison search. For the
  user's own move, the comparison line is the engine's continuation after that move.
- PV nodes receive every `RULE` and `DEFINED` family, exactly like input nodes.
- A PV that starts with the user's next move runs along the input nodes for as long as the moves
  agree. Those nodes and edges carry both roles (3.2). The PV forks where the moves differ.
- PV nodes are **not** searched by default, which keeps the tree from growing recursively.
  `expansion.search_pv_nodes` and `expansion.pv_plies` (a cap) are explicit, budgeted options.
- The end status of a PV line is `PV_END(length)`, or `CHECKMATE` / `STALEMATE` / `DRAW_RULE` when
  the replayed board ends there. It is `EXPANSION_LIMIT` only when a cap was set.

**Search depth is not PV length.** At depth 12, measured over 165 PVs:
- PV length had a median of 11, a minimum of 1 and a maximum of 21.
- A PV can be cut short by a transposition-table hit, or run past the nominal depth through
  extensions (median seldepth 16).

A cap of `pv_plies = depth` is allowed, but it is a cap and not a guarantee. On the sample it
removed only 8% of PV nodes (1,601 → 1,478).

**Cost of attaching engine lines** (same sample: 33 input plies, MultiPV 5, depth 12):
- Engine lines added **1,601 nodes**, against 34 input nodes. That is about 48 per input node, or
  roughly 5 lines × 10 plies.
- Engine search time is unchanged by attaching: the PVs come with searches that already ran
  (6.2 s survey total).
- The cost is the fact families on the new nodes:
  - legacy facts + positional + activity measured **5.6 ms per position**, which includes the
    legacy re-projection;
  - legacy rule facts alone measured 0.8 ms;
  - a raw python-chess attack and legal sweep measured 0.3 ms.
- At legacy speed the 1,601 engine-line nodes would cost about 9 s, more than the engine time.
  A single-move request (one input node) costs about 50 nodes, about 0.3 s.

**Cost controls**, in the order proposed:
1. Share `PositionRecord`s by `PositionKey`, so transpositions and duplicate lines cost nothing.
2. Compute families from one bitboard sweep per position (10), without legacy re-projection.
3. **Tiered families on engine-line nodes.**
   - Computed eagerly: header, `status`, `move`, `material`, `draw`, identity.
   - Heavier families (`pieces`, `squares`, `lines`, `pawns`, `king`, `patterns`,
     `delta`) are computed on request through `FactEngine.ensure` (3.5), from the node's stored
     position, by the same family code and version, and appended at a new revision.
   - A memoized value is the same fact the eager path would produce. It is never recomputed, and
     the manifest records the tier.
4. The `pv_plies` and `lines_per_node` caps, set explicitly in the request.

### 7.6 Search policy (default)

| Node set | Survey | Comparison | Attached as nodes |
| --- | --- | --- | --- |
| Root and every input-line node | yes | yes, if the next input move is outside the survey lines | every returned PV, in full |
| PV nodes | no (opt-in) | no (opt-in) | — |

### 7.7 Engine result store

This block is separate from the adapter and from the engine's transposition table.

- `EngineResultStore` memoizes **finished search records**. A lookup that hits returns the stored
  `EngineSearch` and runs no engine search.
- The key is `(engine identity, profile, search kind, root_moves, multipv, SearchPosition)`.
- `SearchPosition` is the `PositionKey` plus the history that can change the engine's result:
  - the halfmove clock;
  - the **repetition window**: the ordered `PositionKey`s of the last `halfmove_clock` plies
    before the node (Stockfish checks repetitions over `min(rule50, pliesFromNull)` plies,
    `position.cpp`), which also fixes how many times each earlier position occurred.

  Two paths reaching one position with different repetition windows are therefore distinct keys.
- The store can persist across requests. It is also the tape used in tests: a stored search is
  replayed without the engine.
- A reused search keeps its original `search_id` and provenance, and the manifest lists it as
  `REUSED`.
- The live engine's transposition table is cleared before every search (7.1); the store never
  depends on it.
- F4 must test that python-chess's `PositionKey` (legal en passant only) and Stockfish's
  repetition key agree on en passant edge cases; a disagreement is recorded, not hidden.

### 7.8 Terminal and draw nodes (decided 2026-10-08)

| Situation | Legacy | Policy here |
| --- | --- | --- |
| No legal moves: checkmate, stalemate | adapter refused (`EngineAnalysisError`); P7 recorded `TerminalOutcome` from rules without an engine call; ALTERNATIVE / IGNORE_THREAT refused | no search; node `terminal = CHECKMATE / STALEMATE`; searches field `NOT_APPLICABLE(terminal)`; no repeated cross-checks |
| Root itself terminal | request error (move parse failed) | valid one-node tree, no searches |
| Ordering terminal outcomes against scores (P8 `_outcome_key`) | in the explainer | downstream; the fact engine records only the terminal kind |
| PV ends in mate while the score is cp | kept separate (CR2) | kept separate (7.2) |
| Threefold, fifty-move (claimable) | not modelled; engine got no history | node fact in `draw`; node still searched (the game continues unless claimed; Stockfish scores the repetition internally) |
| Fivefold, seventy-five-move (automatic) | not modelled | `terminal = AUTOMATIC_DRAW(kind)`; no search; an engine line ends there |
| Insufficient material | not modelled | `terminal = AUTOMATIC_DRAW(INSUFFICIENT_MATERIAL)` under python-chess's conservative test (a subset of FIDE dead positions; the definition is named in the manifest) |

With `history = UNKNOWN`, fivefold and threefold use only the positions inside the tree, and the
manifest says so (2.1).

## 8. What the engine does **not** produce

Move-quality labels, accuracy, centipawn loss, "best response", threats, refutations, causes,
claims, selections, sentences in any language.

`MoveJudge` and every P7–P12 concept are downstream blocks. A downstream block that needs more
lines (what legacy P7 did with probes) asks the fact engine with `extend(..., role=ANALYSIS(by))`
(3.5); the engine applies its normal search policy to those nodes. The fact engine itself never
adds engine work on its own initiative.

## 9. Trust boundary (lessons E1–E3)

1. **Validation happens only at ingestion.**
   - Request parsing and line legality (python-chess).
   - Engine output normalization (Stockfish).
   - Deserialization of a stored tree.
   - Nothing inside the builder validates a record that the builder itself produced.
2. **Construction is the only path.** Records are frozen and built only by the builder. Their
   constructors check cheap structural shape and nothing else. The legacy pattern "rebuild in
   `__post_init__` and compare for equality" is banned: re-projecting `ActivityFacts` cost about
   40% of the activity time, and I1–I3 full validation ran twice.
3. **Consumers trust.** Downstream blocks receive a read-only `FactTree`. They do not re-check
   checkmate, re-replay lines or recompute deltas. A consumer that needs a new fact asks for a new
   family; it does not derive the fact privately.
4. **Correctness is proven once, offline.** An independent test-only *auditor* rebuilds every
   family from python-chess with a naive implementation and compares the results:
   - over fixture corpora (G0, I1-D D01–D20, scenario E01–E15);
   - over a game-replay fuzz of at least 400 games, like the reviewer fuzz in
     `positional-foundation-review`.
   The auditor is never on the runtime path.
5. **Stored trees.**
   - A tree is stored with its revision; a digest covers every record up to that revision.
   - A tree whose `fact_tree_v1`, family versions and engine identity all match is accepted
     after a digest check.
   - Any mismatch means the tree is rebuilt, not repaired.
   - Engine searches can be replayed from a stored tree without the engine (a tape), but only
     for the identical node, profile and identity.

## 10. Build and cost

- **Board view.** One internal python-chess `Board` (with move stack) per node during
  construction. Bitboard attack maps are computed once per `PositionKey` and shared by every
  family. The legacy stateless FEN ports rebuilt the board on every call; a 64-ply line cost 257
  `observe_position` calls.
- **Order.**
  1. Request validation.
  2. Tree skeleton: all input lines.
  3. Position records: once per `PositionKey`, families in dependency order.
  4. Frame facts and identity.
  5. Edges and deltas.
  6. Engine searches.
  7. PV expansion.
  8. Sealing.
- **Cost targets.**
  - Measured in F5 against the legacy reference numbers: activity 4.6–5.9 ms per position;
    I1–I3 opt-in 1150 ms per request; 8-ply line replay 85 ms plus validation 227 ms.
  - Target: rule and defined families for an 8-ply line below the legacy replay-only cost, with
    zero validation overhead at runtime.
  - Engine time is reported separately and is governed by the profile.

## 11. Package layout (new; independent of legacy)

```text
src/calliope/facts/
  request.py        FactRequest, RootSpec, InputLine, ExpansionSpec, Budget
  keys.py           PositionKey, NodeId, PieceId, canonical UCI rules
  tree.py           FactTree, FrameNode, PositionRecord, Edge, LineRecord, Manifest
  identity.py       piece identity advance
  board.py          BoardView (the only python-chess user besides ingestion)
  families/         status, material, pieces, squares, lines, pawns, king, patterns,
                    draw, move, delta   (one FactFamily each)
  engine/           profile.py, stockfish.py (UCI + normalization), search.py (survey/comparison)
  builder.py        FactEngine: request → FactTree
  store.py          canonical serialization, digest, tape replay
```

- Legacy packages stay untouched until the redesign reaches a switch point. Nothing in
  `calliope.facts` imports from them.
- Shared vocabulary such as `Color` and `PieceType` is redefined in `facts/keys.py` instead of
  imported from the legacy `domain`. This avoids the identity-in-`services.explanation` layering
  problem (lesson G1).

## 12. Lessons → design rules

| Legacy problem | Evidence | Rule here |
| --- | --- | --- |
| Castling aliases escaped canonicalization | `3fd7868`, `811f28b` | one canonicalizer for all input and PV moves (2.2) |
| Malformed UCI reached records | `7628ed5` | structural UCI rule in `keys.py`, typed errors only |
| ep square in FEN without legal ep; `position_id` over clocks | `adapter._canonical_fen`, core-models | `PositionKey` uses legal ep only; clocks live on the node (3.1) |
| No history → no repetition or fifty-move facts | positional.py:102 | root history and `draw` family (2.1, 6.9) |
| Promotion with capture dropped | `672f162` | two ordered facts in one edge (6.10) |
| Cross-search inversion P2-C1 | `985ab49`, p2-c1 §1 | survey/comparison searches, `engine_basis`, no cross-search arithmetic (7.3) |
| Hash and session carry-over | `0a37bf8`, G0 §15 | fresh state per search, `FRESH_PER_SEARCH` (7.1) |
| Time-bound nondeterminism, build dependence | P7 profile, I1–I3 §3 | depth-limited, one thread, fresh state; engine identity incl. net; `reproducible` flag for time limits |
| Mate in PV vs cp score conflated | `b81c2a2` CR2 | score and board terminal are separate facts (7.2) |
| WDL missing treated ad hoc | judge fallback | `UNAVAILABLE` sentinel |
| `EngineStability` always UNKNOWN | adapter.py:150 | removed |
| Identity guessed or swapped by type and count | `646190f`, `de020c8` | identity composed only from the exact move (4) |
| Square without frame read as current | `9c9d5c8` | every piece reference carries its node (4) |
| Geometric/legal mixed in `hanging_now` | facts.py | split facts; legal values only for side to move (6.3) |
| Side-dependent diffs across a side flip | activity semantics | `SameSideDelta` k↔k+2 (6.10) |
| Detector "candidates" drifted into claims | `b81c2a2` CR3, P10 B1–B3 | patterns are geometry predicates with neutral names (6.8) |
| Four independent replay loops, 6+ ply DTOs | inventory | one builder, consumers never replay (3.2) |
| Validation repeated 6–7×, re-projection ~40% cost | I1–I3 §4 | ingestion-only validation, offline auditor (9) |
| Identity in `services.explanation`, private cross-imports | positional F2, A3 L6 | neutral `facts/keys.py`, `facts/identity.py` (11) |
| Exact English bytes frozen during fact work | `5817595` etc. | no wording at all in this block (8) |

**Reused from legacy (as algorithms, rewritten in place):**
- the Stockfish score, mate and WDL normalization;
- `Board.parse_uci`-based canonicalization;
- the pin resolution against ray occupants;
- positional_v1 pawn definitions;
- activity_v1 footprint and ray definitions;
- the identity-advance rules from `piece_identity.py`, rewritten without P8 error types.

## 13. Delivery packets

| Packet | Deliverable | Gate |
| --- | --- | --- |
| F0 (this) | architecture, fact classes, tree and identity model, catalogue v1, engine search model, trust boundary | user decisions (section 14) + independent A0 review READY |
| F1 | `keys`, `request`, `tree`, `identity`, `board`, families `status`, `material`, `draw`, `move`; builder without engine; auditor + 400-game fuzz | independent review READY |
| F2-D / F2 | frozen definitions and implementation of `pieces`, `squares`, `lines`, `pawns`, `king`, `delta`, `SameSideDelta` | READY each |
| F3-D / F3 | `patterns_v1` definitions with adversarial cases; implementation | READY each |
| F4-D / F4 | engine profile, Stockfish ingestion, survey/comparison searches, PV expansion, budget | READY each |
| F5 | canonical serialization, digest, tape replay, cost record against legacy numbers | READY |

## 14. Open decisions for the user

Resolved (2026-10-08):
- **PV expansion.** Input lines plus every engine PV found at input nodes, attached in full; PV
  nodes are not searched by default (7.5, 7.6).
- **Value-ordered geometry.** Included where possible: `RELATIVE_PIN_GEOMETRY`,
  `SKEWER_GEOMETRY` and `points_v1`, under the versioned `piece_order_v1` and the points table
  (6.2, 6.8).
- **Node header.** Every node carries `side_to_move` and the other header fields directly (3.1).
- **Engine result store.** Memoizes finished searches by a history-aware key (7.7).
- **Transposition-table policy.** Fresh state per search plus the result store; a warm hash is
  only an option, marked `reproducible = false` (7.1).
- **One tree with roles.** `PLAYED`, `EXPLORED`, `ANALYSIS` and `ENGINE` roles on shared nodes and
  edges. Nodes gain input roles when the user plays along an engine line (3.2).
- **Append-only revisions.** One tree per session, nothing modified or removed, every addition
  stamped with `rev`; readers can read "as of rev r". Take-backs are not modelled (3.2).
- **Requests.** Facts enter only through `open` / `extend` / `ensure`; a user move and a block's
  analysis request use the same path with different roles (3.5).
- **On-demand families.** Heavier families on engine-only nodes are computed via `ensure` from
  the node's stored position and appended at a new revision (7.5).
- **Self-review fixes (rev. 2).** Searches are bound to `SearchPosition` (7.2). The repetition
  window follows Stockfish (7.7). `ENGINE` roles carry `pv_index` and line depth (3.2). Canonical
  order is defined (3.4).
- **Comparison set.** The union of the survey moves and the input move, as one search (7.3).
- **Engine-line volume.** MultiPV K = 5, with tiered families on engine-only nodes and no
  `pv_plies` cap by default (7.5). To be revisited with measurements if cost becomes a problem.
- **Opponent view.** Excluded from v1 (6.11).
- **Root forms.** startpos + moves, FEN + moves and bare FEN are all accepted. History is marked
  `KNOWN` or `UNKNOWN` (2.1).

Open: none at user level. Remaining questions go to the independent A0 review.

**STOP** if any packet:
- adds an evaluative word or value;
- stores cross-search arithmetic;
- infers engine terminal state from board state, or board state from engine output;
- repairs or truncates an illegal or mismatching line;
- re-validates trusted records at runtime;
- makes an engine call that the request did not plan.
