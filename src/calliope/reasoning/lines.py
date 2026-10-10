"""Shared definitions of catalogue v1 over lines of S (R2-D §1): balances from P, outcome and its
order, the decisive event, the baseline veto, `unsafe_v1` and exposure continuity.

Pure functions of a pinned view. Material is counted as the mover's balance along one line (E3);
no engine number enters it. Missing records are reported, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts import (
    PIECE_ORDER_RANK,
    Capture,
    Color,
    EngineLineFact,
    EngineLineId,
    LineRecord,
    Mate,
    MaterialFlow,
    MoveFacts,
    NodeId,
    NotComputed,
    PieceId,
    PiecesFacts,
    Promotion,
    Stable,
    TerminalKind,
    TreeView,
    Unstable,
    UnstableReason,
    material_flow,
)
from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.findings import DecisiveEvent, Outcome, OutcomeKind
from calliope.reasoning.refs import FactRef, LineSegment, PieceRef

UNSAFE_POLICY = "unsafe_v1"
VETO_PLIES = 4  # R2-D §1.4: the walk back from P passes at most 4 plies


@dataclass(frozen=True, slots=True)
class Line:
    """A line of S read over its window `N_0 … N_k` (`N_0` = P). Not stored: recomputed per view."""

    window: LineSegment
    fact: EngineLineFact
    record: LineRecord | None
    nodes: tuple[NodeId, ...]
    moves: tuple[MoveFacts, ...]  # plies 1 … k (empty when the flow is missing)
    flow: MaterialFlow | None
    balances: tuple[int, ...]  # b_0 … b_k for the mover, from P (empty when the flow is missing)
    mover: Color
    outcome: Outcome
    terminal: tuple[bool, ...]  # per node of the window: the game ends there

    @property
    def line_id(self) -> EngineLineId:
        assert isinstance(self.window.line, EngineLineId)
        return self.window.line

    @property
    def rank(self) -> int:
        return self.line_id.rank

    @property
    def k(self) -> int:
        return len(self.nodes) - 1

    @property
    def attached(self) -> int:
        """`r`: the plies attached as nodes (0 without a record)."""

        return len(self.record.nodes) - 1 if self.record is not None else 0

    @property
    def counted(self) -> bool:
        return bool(self.balances)


def search_line(view: TreeView, search_id: str, rank: int) -> EngineLineFact:
    line = next((ln for ln in view.search(search_id).lines if ln.rank == rank), None)
    if line is None:
        raise ReasoningError(f"search {search_id} has no line of rank {rank}")
    return line


def read_line(view: TreeView, window: LineSegment, mover: Color) -> Line:
    """The line of `window` (an `EngineLineId` segment from ply 0) and its outcome (R2-D §1.3)."""

    line_id = window.line
    if not isinstance(line_id, EngineLineId) or window.first != 0:
        raise ReasoningError(f"{window} is not a window of an engine line")
    fact = search_line(view, line_id.search_id, line_id.rank)
    try:
        record: LineRecord | None = view.line(line_id)
    except KeyError:
        record = None
    if record is None:
        nodes: tuple[NodeId, ...] = (line_id.anchor,)
    else:
        nodes = record.nodes[: min(window.last, len(record.nodes) - 1) + 1]
    flow = material_flow(view, nodes)
    moves: tuple[MoveFacts, ...] = ()
    balances: tuple[int, ...] = ()
    if not isinstance(flow.stable, NotComputed):
        balances = tuple(flow.balance(mover, i) for i in range(len(nodes)))
        moves = tuple(view.fact("move", n) for n in nodes[1:])
    terminal = tuple(view.node(n).terminal.ends_game for n in nodes)
    outcome = _outcome(view, fact, record, nodes, flow, balances)
    return Line(window, fact, record, nodes, moves, flow, balances, mover, outcome, terminal)


def _outcome(view, fact, record, nodes, flow, balances) -> Outcome:
    k = len(nodes) - 1
    end = record.end if record is not None else None
    if isinstance(fact.score, Mate):
        return Outcome(OutcomeKind.MATE, fact.score.winner, fact.score.moves, None, k, end)
    if record is None:
        return Outcome(OutcomeKind.MISSING, plies=k, reason="NOT_COMPUTED(NOT_ATTACHED)")
    if len(record.nodes) == 1:
        return Outcome(OutcomeKind.MISSING, plies=0, line_end=end, reason="LINE_TOO_SHORT")
    if isinstance(flow.stable, NotComputed):
        return Outcome(OutcomeKind.MISSING, plies=k, line_end=end, reason="NOT_COMPUTED(material)")
    last = view.node(nodes[-1])
    if last.terminal.kind is TerminalKind.CHECKMATE:
        assert last.mover is not None
        return Outcome(OutcomeKind.MATE, last.mover, (k + 1) // 2, None, k, end)
    if isinstance(flow.stable, Unstable) and flow.stable.reason is UnstableReason.DRAWN_END:
        return Outcome(OutcomeKind.DRAWN, plies=k, line_end=end)
    if isinstance(flow.stable, Stable):
        return Outcome(OutcomeKind.STABLE, delta=balances[k], plies=k, line_end=end)
    return Outcome(OutcomeKind.OPEN, plies=k, line_end=end)


# -- the outcome order (R2-D §1.3) ------------------------------------------------------------------

DECIDED = (OutcomeKind.MATE, OutcomeKind.STABLE, OutcomeKind.DRAWN)


def decided(outcome: Outcome) -> bool:
    return outcome.kind in DECIDED


def undecided_reason(outcome: Outcome) -> str:
    """The INCONCLUSIVE reason of an undecided outcome: `OPEN` lacks plies (R2-D §3.1 rule 2)."""

    if outcome.kind is OutcomeKind.MISSING:
        assert outcome.reason is not None
        return outcome.reason
    return "LINE_TOO_SHORT"


def mate_for(outcome: Outcome, color: Color) -> bool:
    return outcome.kind is OutcomeKind.MATE and outcome.winner is color


def _key(outcome: Outcome, mover: Color) -> tuple[int, int | None] | None:
    if outcome.kind is OutcomeKind.MATE:
        assert outcome.moves is not None
        return (2, -outcome.moves) if outcome.winner is mover else (0, outcome.moves)
    if outcome.kind is OutcomeKind.STABLE:
        return (1, outcome.delta)
    if outcome.kind is OutcomeKind.DRAWN:
        return (1, None)
    return None


def compare(a: Outcome, b: Outcome, mover: Color) -> int | None:
    """The sign of `a` against `b` for the mover, best first; None if undecided or incomparable.

    `MATE(m, n)` (smaller `n` first) > `STABLE(Δ)` (larger Δ first) > `MATE(o, n)` (larger `n`
    first); `DRAWN` is below every `MATE(m, ·)`, above every `MATE(o, ·)`, and incomparable with
    `STABLE`.
    """

    ka, kb = _key(a, mover), _key(b, mover)
    if ka is None or kb is None:
        return None
    if ka[0] != kb[0]:
        return 1 if ka[0] > kb[0] else -1
    x, y = ka[1], kb[1]
    if x is None or y is None:
        return 0 if x is None and y is None else None  # DRAWN against STABLE
    return (x > y) - (x < y)


# -- the decisive event (R2-D §1.5) -----------------------------------------------------------------


def decisive_ply(balances: tuple[int, ...], loss: bool) -> int | None:
    """The first ply where the balance reaches its final level and stays on its side of 0."""

    if not balances:
        return None
    k = len(balances) - 1
    delta = balances[k]
    if (loss and delta > -1) or (not loss and delta < 1):
        return None
    for q in range(1, k + 1):
        reached = balances[q] <= delta if loss else balances[q] >= delta
        rest = balances[q:]
        if reached and all((b < 0) if loss else (b > 0) for b in rest):
            return q
    return None


def event_at(line: Line, ply: int) -> DecisiveEvent:
    """The capture or promotion of ply `ply` of the line, as a `DecisiveEvent`."""

    assert line.flow is not None
    material = line.flow.plies[ply - 1]
    before = line.nodes[ply - 1]
    move = line.moves[ply - 1]
    victim = capturer = None
    if material.capture is not None:
        victim = PieceRef(material.capture.piece, before, material.capture.square)
        capturer = PieceRef(move.piece, before, move.from_square)
    promotion = material.promotion.to if material.promotion is not None else None
    return DecisiveEvent(ply, line.nodes[ply], victim, capturer, promotion)


def decisive_event(line: Line, loss: bool) -> DecisiveEvent | None:
    if line.outcome.kind is not OutcomeKind.STABLE:
        return None
    q = decisive_ply(line.balances, loss)
    return event_at(line, q) if q is not None else None


def event_ref(view: TreeView, event: DecisiveEvent) -> FactRef:
    """`FactRef("move", N_q, ("events", i))` of the event's capture (or promotion)."""

    move = view.fact("move", event.node)
    wanted = Capture if event.victim is not None else Promotion
    index = next(i for i, e in enumerate(move.events) if isinstance(e, wanted))
    return fact_ref(view, "move", event.node, ("events", index))


def changes(line: Line) -> tuple[int, ...]:
    if line.flow is None or not line.counted:
        return ()
    return tuple(
        p.index for p in line.flow.plies if p.capture is not None or p.promotion is not None
    )


# -- the baseline veto (R2-D §1.4) ------------------------------------------------------------------


def baseline_path(view: TreeView, p: NodeId) -> tuple[NodeId, ...]:
    """`B … P`: back from P while the ply into the node captures or checks, at most 4 plies."""

    path = [p]
    while len(path) - 1 < VETO_PLIES:
        node = view.node(path[0])
        if node.parent is None:
            break
        move = view.fact("move", path[0])
        if not isinstance(move, MoveFacts):
            break
        if not (move.gives_check or any(isinstance(e, Capture) for e in move.events)):
            break
        path.insert(0, node.parent)
    return tuple(path)


def veto(view: TreeView, line: Line) -> tuple[int, ...] | None:
    """`bB_0 … bB_k`: the mover's balance from B along `B … P, N_1 … N_k`; None when B = P."""

    path = baseline_path(view, line.nodes[0])
    if len(path) == 1 or not line.counted:
        return None
    flow = material_flow(view, path + line.nodes[1:])
    if isinstance(flow.stable, NotComputed):
        return None
    d = len(path) - 1
    return tuple(flow.balance(line.mover, d + i) for i in range(len(line.nodes)))


# -- safety and exposure (R2-D §1.6, §1.6a) ---------------------------------------------------------


def pieces(view: TreeView, node: NodeId) -> PiecesFacts | None:
    record = view.fact("pieces", node)
    return record if isinstance(record, PiecesFacts) else None


def unsafe(view: TreeView, piece: PieceId, node: NodeId) -> bool | None:
    """`unsafe_v1`: outnumbered, or attacked by a lower piece; None if `pieces` is missing.

    A piece not on the board at `node` is not unsafe there (R2-D §1.1: the test is false).
    """

    square = view.node(node).square_of(piece)
    if square is None:
        return False
    record = pieces(view, node)
    if record is None:
        return None
    entry = record.at(square)
    assert entry is not None
    if entry.attackers_exceed_defenders:
        return True
    own = PIECE_ORDER_RANK[entry.piece_type]
    return any(PIECE_ORDER_RANK[t] < own for t in entry.lowest_attacker_types.value)


def attacks(view: TreeView, attacker: PieceId, victim: PieceId, node: NodeId) -> bool | None:
    """`sq(victim, N) ∈ pieces(attacker, N).attacks.enemy`; None if `pieces` is missing."""

    current = view.node(node)
    a, v = current.square_of(attacker), current.square_of(victim)
    if a is None or v is None:
        return False
    record = pieces(view, node)
    if record is None:
        return None
    entry = record.at(a)
    assert entry is not None
    return v in entry.attacks.enemy


class Exposure(StrEnum):
    EXPOSED = "exposed"
    NOT_EXPOSED = "not_exposed"
    UNDECIDED = "undecided"


def exposure(
    view: TreeView, v: PieceId, w: PieceId, nodes: tuple[NodeId, ...]
) -> tuple[Exposure, tuple[NodeId, ...]]:
    """R2-D §1.6a over `nodes` (`N_a … N_{q−1}`): `v` on one square, unsafe, attacked by `w`.

    A present failing record (or the square map) decides `NOT_EXPOSED`; otherwise the nodes whose
    `pieces` record is missing make it `UNDECIDED`.
    """

    start = view.node(nodes[0]).square_of(v)
    missing: list[NodeId] = []
    for node in nodes:
        if start is None or view.node(node).square_of(v) != start:
            return Exposure.NOT_EXPOSED, ()
        if pieces(view, node) is None:
            missing.append(node)
            continue
        if not unsafe(view, v, node) or not attacks(view, w, v, node):
            return Exposure.NOT_EXPOSED, ()
    if missing:
        return Exposure.UNDECIDED, tuple(missing)
    return Exposure.EXPOSED, ()


# -- evidence ---------------------------------------------------------------------------------------


def fact_ref(view: TreeView, family: str, node: NodeId, path: tuple = ()) -> FactRef:
    """A reference to a visible record, at the revision that added it (R0-D §4)."""

    entry = view.fact_entry(family, node)
    if entry is None:
        raise ReasoningError(f"no {family} record for {node} at rev {view.rev}")
    return FactRef(family, entry.target, entry.rev, path)
