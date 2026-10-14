"""Shared definitions of catalogue v1 over lines of S (R2-D §1): balances from P, outcome and its
order, trades and the decisive event, the baseline veto, `exposed_v1`, exposure continuity and the
attribution of a line's material to the move (EF-D §2–§4).

Pure functions of a pinned view. Material is counted as the mover's balance along one line (E3);
no engine number enters it. Missing records are reported, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from calliope.facts import (
    NONE,
    Capture,
    Color,
    Cp,
    Defined,
    EngineLineFact,
    EngineLineId,
    ExchangeFacts,
    LineRecord,
    Mate,
    MaterialFlow,
    MoveFacts,
    NodeId,
    NotApplicable,
    NotComputed,
    PieceId,
    PiecesFacts,
    Promotion,
    Stable,
    StatusFacts,
    TerminalKind,
    TreeView,
    Unstable,
    UnstableReason,
    Wdl,
    material_flow,
)
from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.findings import (
    ChecksDrawFinding,
    DecisiveEvent,
    DrawKind,
    Outcome,
    OutcomeKind,
)
from calliope.reasoning.needs import EvidenceNeed, FamilyNeed, LineNeed
from calliope.reasoning.refs import Evidence, FactRef, LineSegment, MoveRef, PieceRef, SearchRef

SEE_POLICY = "see_v1"  # EF-D §4: `exposed_v1` reads only `see_v1` records
CONCESSION_POLICY = "concession_v1"  # EF-D §3
IMMEDIATE_PLIES = 2  # EF-D §3.3: the move and its reply (R3-D's IMMEDIATE_PLIES)
VETO_PLIES = 4  # R2-D §1.4: the walk back from P passes at most 4 plies
CHECK_RUN = 2  # EV-D §2.1: "check after check"
DRAW_CP = 10  # |cp| of a drawn line's score
DRAW_WDL = 900  # permille drawn for REPEATED and SCORED


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


def trade_pairs(line: Line) -> tuple[tuple[int, int], ...]:
    """`trade_pairs_v1` (EF-D §2): plies `i`, `i + 1` that both capture, neither promoting, where
    `i + 1` takes the piece that moved at `i` on its square, for the same `points_v1` value
    (`c_{i+1} = −c_i`). Left to right, never overlapping."""

    if line.flow is None or not line.counted:
        return ()
    plies, b = line.flow.plies, line.balances
    out: list[tuple[int, int]] = []
    i = 1
    while i < len(plies):
        a, c = plies[i - 1], plies[i]
        if (
            a.capture is not None
            and c.capture is not None
            and a.promotion is None
            and c.promotion is None
            and c.capture.piece == line.moves[i - 1].piece
            and c.capture.square == line.moves[i - 1].to_square
            and b[i + 1] - b[i] == -(b[i] - b[i - 1])
        ):
            out.append((i, i + 1))
            i += 2
        else:
            i += 1
    return tuple(out)


def reduced_balances(line: Line) -> tuple[int, ...]:
    """`b′` (EF-D §2): `b′_i = b_{i−1}` where ply `i` opens a trade, else `b_i`."""

    opens = {i for i, _ in trade_pairs(line)}
    b = line.balances
    return tuple(b[i - 1] if i in opens else b[i] for i in range(len(b)))


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
    q = decisive_ply(reduced_balances(line), loss)
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


# -- safety and exposure (EF-D §4; R2-D §1.6a) ------------------------------------------------------


def pieces(view: TreeView, node: NodeId) -> PiecesFacts | None:
    record = view.fact("pieces", node)
    return record if isinstance(record, PiecesFacts) else None


class Exposed(StrEnum):
    EXPOSED = "exposed"
    NOT_EXPOSED = "not_exposed"
    UNDECIDED = "undecided"  # in check without a safe-moves record (EF1 A1: not expected)


IN_CHECK = "NOT_COMPUTED(IN_CHECK)"  # EF-D E6: the reason of a template that cannot decide


def exposed(view: TreeView, piece: PieceId, node: NodeId) -> Exposed | None:
    """`exposed_v1` (EF-D §4): the opponent wins at least one point by starting captures on the
    piece (`see_v1`; the turn passed for the side to move). For a piece of a side in check, where
    `see_v1` is undefined, exposed when it has no safe move — no answer to the check takes it out
    of the exchange (EF1 A1, F6-D §2.3). None when `exchange` is missing; UNDECIDED only when an
    in-check entry holds no safe moves record.

    A piece not on the board at `node` is not exposed there (R2-D §1.1); a king has no entry.
    """

    square = view.node(node).square_of(piece)
    if square is None:
        return Exposed.NOT_EXPOSED
    record = view.fact("exchange", node)
    if not isinstance(record, ExchangeFacts):
        return None
    entry = next((e for e in record.pieces if e.square == square), None)
    if entry is None:
        return Exposed.NOT_EXPOSED
    if isinstance(entry.gain, NotApplicable):  # its owner is in check (F6-D §2.2)
        if not isinstance(entry.safe_moves, tuple):
            return Exposed.UNDECIDED
        # EF1 A1: exposed when no answer to the check takes it out of the exchange (F6-D §2.3)
        return Exposed.NOT_EXPOSED if entry.safe_moves else Exposed.EXPOSED
    assert isinstance(entry.gain, Defined)
    return Exposed.EXPOSED if entry.gain.value >= 1 else Exposed.NOT_EXPOSED


def exchange_ref(view: TreeView, piece: PieceId, node: NodeId) -> FactRef | None:
    """`FactRef("exchange", N, ("pieces", i))` of the piece's entry; None when it has none."""

    square = view.node(node).square_of(piece)
    record = view.fact("exchange", node)
    if square is None or not isinstance(record, ExchangeFacts):
        return None
    index = next((i for i, e in enumerate(record.pieces) if e.square == square), None)
    return fact_ref(view, "exchange", node, ("pieces", index)) if index is not None else None


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
    UNDECIDED = "undecided"  # records missing: the needs say which
    IN_CHECK = "in_check"  # a node where `exposed_v1` is undecided (EF-D E6)


def exposure(
    view: TreeView, v: PieceId, w: PieceId, nodes: tuple[NodeId, ...]
) -> tuple[Exposure, tuple[FamilyNeed, ...]]:
    """R2-D §1.6a over `nodes` (`N_a … N_{q−1}`) on `exposed_v1`: `v` on one square, exposed,
    attacked by `w`.

    A present failing record (or the square map) decides `NOT_EXPOSED`; then missing records make
    it `UNDECIDED` (with their needs); then a node in check makes it `IN_CHECK`.
    """

    start = view.node(nodes[0]).square_of(v)
    missing: list[FamilyNeed] = []
    in_check = False
    for node in nodes:
        if start is None or view.node(node).square_of(v) != start:
            return Exposure.NOT_EXPOSED, ()
        state = exposed(view, v, node)
        hit = attacks(view, w, v, node)
        if state is Exposed.NOT_EXPOSED or hit is False:
            return Exposure.NOT_EXPOSED, ()
        if state is None:
            missing.append(FamilyNeed(node, "exchange"))
        if hit is None:
            missing.append(FamilyNeed(node, "pieces"))
        in_check = in_check or state is Exposed.UNDECIDED
    if missing:
        return Exposure.UNDECIDED, tuple(missing)
    if in_check:
        return Exposure.IN_CHECK, ()
    return Exposure.EXPOSED, ()


# -- attribution (EF-D §3) --------------------------------------------------------------------------


class Attribution(StrEnum):
    ATTRIBUTED = "attributed"
    CONCESSION = "concession"
    UNDECIDED = "undecided"


@dataclass(frozen=True, slots=True)
class AttributionResult:
    """What `attribution` decided, the needs it still has, and its evidence (EF-D §3.4)."""

    state: Attribution | None  # None: records are needed
    needs: tuple[EvidenceNeed, ...] = ()
    origins: tuple[int, int] | None = None  # (o⁺, o⁻)
    evidence: tuple[Evidence, ...] = ()


def attribution(view: TreeView, line: Line, event: DecisiveEvent) -> AttributionResult:
    """`concession_v1` (EF-D §3): whether the move is shown to bring about the line's material.

    The loser `L` owns the piece captured at the event's ply `q`. Walking back from `N_{q−1}`, the
    exposure run gives two origins: `o⁺` reads undecided (in-check) nodes as exposed, `o⁻` as not.
    Each is classified; the attribution is decided when both agree.
    """

    if event.victim is None:  # a promotion without a capture is not tested (§3.4)
        return AttributionResult(Attribution.ATTRIBUTED, evidence=(event_ref(view, event),))
    q, y, nodes = event.ply, event.victim.piece, line.nodes
    wanted = tuple(
        FamilyNeed(nodes[i], "exchange")
        for i in range(q)
        if not isinstance(view.fact("exchange", nodes[i]), ExchangeFacts)
    )
    if wanted:  # every node of the walk at once: rounds are few (R0-D §6.3)
        return AttributionResult(None, wanted)
    states = [exposed(view, y, nodes[i]) for i in range(q)]
    o_plus = o_minus = q
    i = q - 1
    while i >= 0 and states[i] is not Exposed.NOT_EXPOSED:
        o_plus = i
        i -= 1
    i = q - 1
    while i >= 0 and states[i] is Exposed.EXPOSED:
        o_minus = i
        i -= 1
    winner = view.node(nodes[q]).mover  # the side that captures `y` at ply q
    assert winner is not None
    loser = Color.BLACK if winner is Color.WHITE else Color.WHITE
    found = [_classify(view, line, o, loser, y, q) for o in dict.fromkeys((o_plus, o_minus))]
    needed = tuple(n for result, ns, _ in found if result is None for n in ns)
    if needed:
        return AttributionResult(None, needed)
    evidence: list[Evidence] = []
    for o in dict.fromkeys((o_plus, o_minus)):
        evidence += _origin_evidence(view, line, event, o)
    for i in range(o_plus, q):
        ref = exchange_ref(view, y, nodes[i])
        if ref is not None:
            evidence.append(ref)
        if states[i] is Exposed.UNDECIDED:
            evidence.append(fact_ref(view, "status", nodes[i], ("in_check",)))
    for _result, _ns, refs in found:
        evidence += refs
    results = {result for result, _ns, _refs in found}
    state = results.pop() if len(results) == 1 else Attribution.UNDECIDED
    return AttributionResult(
        state, origins=(o_plus, o_minus), evidence=tuple(dict.fromkeys(evidence))
    )


def _classify(
    view: TreeView, line: Line, o: int, loser: Color, y: PieceId, q: int
) -> tuple[Attribution | None, tuple[EvidenceNeed, ...], tuple[Evidence, ...]]:
    """§3.3 at one origin: attributed, a concession, or None with the needs of the forced test.

    Forced: `L`'s move at ply `o` is its only legal move, or every alternative allows mate in one.
    The alternatives are `L`'s other legal moves at `N_{o−1}`; when `L` is in check there, only
    those that save `y` — `y`'s `safe_moves` there (F6-D §2.3) — count (EF-D §3.3 as amended by
    EF1, A1: a check answer that cannot save the forked piece is forced). A present record that
    shows one alternative without mate decides first. An exposing move that itself captures at
    least `y`'s value is an exchange, not a concession (EF1 A3: a recapture that leaves a pawn)."""

    if o <= IMMEDIATE_PLIES or view.node(line.nodes[o]).mover is not loser:
        return Attribution.ATTRIBUTED, (), ()  # rule 1 (the empty run: ply q is the winner's)
    if _takes_as_much(line, o, q):
        return Attribution.ATTRIBUTED, (), (fact_ref(view, "move", line.nodes[o], ("events",)),)
    before = line.nodes[o - 1]
    status = view.fact("status", before)
    assert isinstance(status, StatusFacts)
    refs: list[Evidence] = [fact_ref(view, "status", before, ("legal_move_count",))]
    if status.legal_move_count == 1:
        return Attribution.ATTRIBUTED, (), tuple(refs)
    played = line.moves[o - 1].uci
    alternatives = [m.uci for m in status.legal_moves if m.uci != played]
    if status.in_check:
        saving = _safe_moves(view, y, before)
        if saving is not None:
            ref = exchange_ref(view, y, before)
            refs += [fact_ref(view, "status", before, ("in_check",)), *((ref,) if ref else ())]
            alternatives = [m for m in alternatives if m in saving]
    wanted: list[EvidenceNeed] = []
    for uci in alternatives:  # rule 2
        child = view.child(before, uci)
        if child is None:
            wanted.append(LineNeed(before, (uci,), NONE))
            continue
        after = view.fact("status", child)
        assert isinstance(after, StatusFacts)
        refs.append(fact_ref(view, "status", child, ("mating_moves",)))
        if after.mating_moves == ():
            return Attribution.CONCESSION, (), tuple(refs)  # a present record decides first
    if wanted:
        return None, tuple(wanted), ()
    return Attribution.ATTRIBUTED, (), tuple(refs)


def _takes_as_much(line: Line, o: int, q: int) -> bool:
    """EF1 A3: ply `o` captures, neither it nor the event promotes, and what it takes is worth at
    least the piece lost at `q` (`|c_o| ≥ |c_q|`, `points_v1` through the balances)."""

    plies, b = line.flow.plies, line.balances
    if o == q or plies[o - 1].capture is None or plies[o - 1].promotion or plies[q - 1].promotion:
        return False
    return abs(b[o] - b[o - 1]) >= abs(b[q] - b[q - 1])


def _safe_moves(view: TreeView, piece: PieceId, node: NodeId) -> frozenset[str] | None:
    """`y`'s `safe_moves` at `node` (F6-D §2.3), or None when the record does not hold them."""

    square = view.node(node).square_of(piece)
    record = view.fact("exchange", node)
    if square is None or not isinstance(record, ExchangeFacts):
        return None
    entry = next((e for e in record.pieces if e.square == square), None)
    if entry is None or not isinstance(entry.safe_moves, tuple):
        return None
    return frozenset(entry.safe_moves)


def _origin_evidence(view: TreeView, line: Line, event: DecisiveEvent, o: int) -> list[Evidence]:
    """§3.4 at one origin: `exchange` of `N_{o−1}` and `N_o`; `N_0` alone; or, for the empty run,
    `exchange` of `N_{q−1}` and the event's capture."""

    assert event.victim is not None
    y, q, nodes = event.victim.piece, event.ply, line.nodes
    if o == q:
        refs = [exchange_ref(view, y, nodes[q - 1]), event_ref(view, event)]
    elif o == 0:
        refs = [exchange_ref(view, y, nodes[0])]
    else:
        refs = [exchange_ref(view, y, nodes[o - 1]), exchange_ref(view, y, nodes[o])]
    return [r for r in refs if r is not None]


# -- checking draws (EV-D §2.1) ---------------------------------------------------------------------


def checking_draw(view: TreeView, line: Line, side: Color) -> ChecksDrawFinding | str | None:
    """The line as a checking draw by `side`: its finding, None when it is not one, or the reason
    (`NOT_COMPUTED(<family>)`, `NOT_COMPUTED(wdl)`) a needed record is missing."""

    k = line.k
    first = 1 if side is line.mover else 2  # the mover plays the odd plies from P
    plies = list(range(first, k + 1, 2))
    run: list[int] = []
    for i in reversed(plies):
        move = view.fact("move", line.nodes[i])
        if not isinstance(move, MoveFacts):
            return "NOT_COMPUTED(move)"
        if not move.gives_check or move.gives_mate:
            break
        run.insert(0, i)
    if len(run) < CHECK_RUN:
        return None
    score = line.fact.score
    if not isinstance(score, Cp) or abs(score.value) > DRAW_CP:
        return None
    if view.node(line.nodes[k]).terminal.kind is TerminalKind.CHECKMATE:
        return None
    q = run[0]
    draws = []
    for i in range(q, k + 1):
        record = view.fact("draw", line.nodes[i])
        if isinstance(record, NotComputed):
            return "NOT_COMPUTED(draw)"
        draws.append((i, record))
    segment = LineSegment(line.line_id, q - 1, k)

    def found(kind: DrawKind, at: int | None) -> ChecksDrawFinding:
        repeat = MoveRef(line.nodes[at]) if at is not None else None
        return ChecksDrawFinding(side, kind, segment, len(run), repeat)

    for kind, field in ((DrawKind.FIVEFOLD, "fivefold_reached"),
                        (DrawKind.THREEFOLD, "threefold_reached")):  # fmt: skip
        at = next((i for i, r in draws if getattr(r, field) is True), None)
        if at is not None:
            return found(kind, at)
    wdl = line.fact.wdl
    if not isinstance(wdl, Wdl):
        return "NOT_COMPUTED(wdl)"
    if wdl.draw < DRAW_WDL:
        return None
    at = next((i for i, r in draws if _count(r.occurrences) >= 2), None)
    return found(DrawKind.REPEATED if at is not None else DrawKind.SCORED, at)


def _count(occurrences) -> int:
    """An `AtLeast(n)` counts as `n`."""

    return occurrences if isinstance(occurrences, int) else occurrences.n


FIELD = {
    DrawKind.FIVEFOLD: "fivefold_reached",
    DrawKind.THREEFOLD: "threefold_reached",
    DrawKind.REPEATED: "occurrences",
}


def checking_draw_evidence(
    view: TreeView, line: Line, f: ChecksDrawFinding
) -> tuple[Evidence, ...]:
    """The line's search, every check of the run, and the repetition's `draw` record (§2.1)."""

    q = f.line.first + 1
    out: list[Evidence] = [SearchRef(line.line_id.search_id, line.rank)]
    out += [
        fact_ref(view, "move", line.nodes[q + 2 * j], ("gives_check",)) for j in range(f.checks)
    ]
    if f.repeat_at is not None:
        out.append(fact_ref(view, "draw", f.repeat_at.node, (FIELD[f.kind],)))
    return tuple(out)


# -- evidence ---------------------------------------------------------------------------------------


def fact_ref(view: TreeView, family: str, node: NodeId, path: tuple = ()) -> FactRef:
    """A reference to a visible record, at the revision that added it (R0-D §4)."""

    entry = view.fact_entry(family, node)
    if entry is None:
        raise ReasoningError(f"no {family} record for {node} at rev {view.rev}")
    return FactRef(family, entry.target, entry.rev, path)
