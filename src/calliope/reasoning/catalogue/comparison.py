"""`better_move_v1` (R2-D §3.12): the best line's mate or material outcome beats the played one.
`missed_gain_v1` (MV-D §4): rank 1 of S beats the played move by expected points.
`better_alternative_v1` (EA-D §3): rank 1 of S beats an inaccuracy or worse, by any loss.
`best_stops_reply_v1` (EV-D §3): what the best move does about the opponent's reply in `Lp`."""

from __future__ import annotations

from calliope.facts import (
    POINTS_V1_BY_TYPE,
    Capture,
    Color,
    Defined,
    ExpansionSpec,
    MoveFacts,
    NodeId,
    NotComputed,
    PieceExchange,
    Promotion,
    StatusFacts,
    TreeView,
)
from calliope.reasoning.catalogue.base import (
    REQUIRE_LINE,
    B,
    Template,
    claims_of,
    inconclusive,
    judged,
    judgement,
    judgement_ref,
    line_target,
    lines,
    materials,
    mover,
    needs,
    opponent,
    refuted,
    scope,
    search_id,
    seg,
    supported,
)
from calliope.reasoning.catalogue.exchange import EXCHANGE, SEE
from calliope.reasoning.findings import (
    ComparisonFinding,
    MissedGainFinding,
    OutcomeKind,
    ReplyFinding,
    ReplyKind,
)
from calliope.reasoning.grading import Grading
from calliope.reasoning.hypotheses import (
    ClaimRole,
    Hypothesis,
    LineContext,
    NodeContext,
    Population,
    PopulationKind,
    PremiseRelation,
    PremiseUse,
    ProposeContext,
    Quantifier,
    RelationDecl,
    RelationKind,
    SearchCompat,
    VerificationTarget,
)
from calliope.reasoning.labels import MISS_LOSS
from calliope.reasoning.lines import (
    Line,
    compare,
    decided,
    fact_ref,
    mate_for,
    read_line,
    undecided_reason,
)
from calliope.reasoning.needs import FamilyNeed, LineNeed
from calliope.reasoning.observer import Grade, standard_line_ids
from calliope.reasoning.refs import (
    LineSegment,
    MoveRef,
    PieceRef,
    SearchMoveRef,
    SearchRef,
    SquareRef,
)
from calliope.reasoning.verification import Verdict

MATE_ALLOWED = "mate_allowed_v1"
MATERIAL_LOSS = "material_loss_v2"


class BetterMove(Template):
    name = "better_move_v1"
    role = ClaimRole.COMPARISON
    directions = frozenset({B})
    relations = (
        RelationDecl(RelationKind.COMPARES_WITH, MATE_ALLOWED),
        RelationDecl(RelationKind.COMPARES_WITH, MATERIAL_LOSS),
    )
    predicate = "better_move"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        found = materials(ctx)
        if judgement_ is None or found is None or not judgement_.grade.at_least(Grade.INACCURACY):
            return ()
        _ref, by_rank = found
        lp_id, l1_id = standard_line_ids(judgement_)
        lp, l1 = by_rank[lp_id.rank], by_rank[l1_id.rank]
        at, played_at = seg(ctx.view, l1_id), seg(ctx.view, lp_id)
        if at is None or played_at is None:
            return ()
        # proposed once every consequence on Lp it may rest on is final (R2-D §3.12)
        o = opponent(ctx.view.node(ctx.subject.parent).side_to_move)
        wanted = [MATERIAL_LOSS]
        if mate_for(lp.outcome, o) and not mate_for(l1.outcome, o):
            wanted.insert(0, MATE_ALLOWED)
        on_lp = {
            name: [c for c in claims_of(ctx, name) if c.hypothesis.target.at == played_at]
            for name in wanted
        }
        if any(not found_ for found_ in on_lp.values()):
            return ()
        if any(
            h.role is ClaimRole.CONSEQUENCE
            and h.target.at == played_at
            and h.subject == ctx.subject
            for h in ctx.pending
        ):
            return ()  # a consequence on Lp is not final yet
        premise = next(
            (c for name in wanted for c in on_lp[name] if c.supported),
            None,
        )
        premises = ()
        if premise is not None:
            premises = (
                PremiseUse(
                    premise.id,
                    REQUIRE_LINE,
                    PremiseRelation.ALTERNATIVE_OF,
                    SearchCompat.SAME_SEARCH,
                ),
            )
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(l1.window, lp.window),
                target=line_target(at),
                premises=premises,
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        l1, lp = lines(view, h, h.operands)
        sid = search_id(h)
        evidence = (
            SearchRef(sid, l1.rank),
            SearchRef(sid, lp.rank),
            l1.window,
            lp.window,
            fact_ref(view, "status", h.subject.parent, ("legal_moves",)),
        )
        finding = ComparisonFinding(SearchMoveRef(sid, l1.rank, 1), l1.outcome, lp.outcome)
        order = compare(l1.outcome, lp.outcome, mover(view, h))
        if order is None:
            pending = [o for o in (l1.outcome, lp.outcome) if not decided(o)]
            reason = undecided_reason(pending[0]) if pending else "UNSTABLE"
            return inconclusive(h, reason, (finding,), evidence)  # rule 3
        if order > 0:
            proof = scope(view, h, grading, (l1.rank, lp.rank), line=l1)
            return supported(h, proof, (finding,), evidence)  # rule 1
        return refuted(h, (finding,), evidence)  # rule 2


class MissedGain(Template):
    """MV-D §4: in S, a reported move beat the played move by at least `MISS_LOSS`.

    It proves only that a better move existed, by expected points. It reads S alone and never the
    previous move (MV-D review B1); `label_v2` adds the opponent's side for MISS (`miss_p2`). The
    witness is a reported move, so a rank-1 PV left unattached does not lose it (review B2)."""

    name = "missed_gain_v1"
    role = ClaimRole.COMPARISON
    directions = frozenset({B})
    predicate = "missed_gain"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        if judgement_ is None or judgement_.played is None or judgement_.loss is None:
            return ()
        if judgement_.played.rank == 1 or judgement_.loss < MISS_LOSS:
            return ()
        assert judgement_.search is not None
        parent = ctx.subject.parent
        population = Population(PopulationKind.ENGINE_REPORTED, judgement_.search.search_id)
        return (
            self.make(
                ctx,
                context=NodeContext(parent),
                operands=(),
                target=VerificationTarget(Quantifier.EXISTS_ALTERNATIVE, parent, population),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        result = judgement(view, h, grading)
        assert result.played is not None and result.best is not None and result.loss is not None
        sid = search_id(h)
        evidence = (SearchRef(sid, result.best.rank), SearchRef(sid, result.played.rank))
        if result.played.rank == 1 or result.loss < MISS_LOSS:
            return refuted(h, evidence=evidence)
        finding = MissedGainFinding(SearchMoveRef(sid, result.best.rank, 1), result.loss)
        ranks = (result.best.rank, result.played.rank)
        proof = scope(view, h, grading, ranks, witnesses=(result.best.move,))
        return supported(h, proof, (finding,), evidence)


class BetterAlternative(Template):
    """EA-D §3: the played move, graded INACCURACY or worse, is not rank 1 of S, so rank 1 was
    better. The judgement already proves it; the claim lets the explanation name the move when no
    other comparison does (the planner takes it last). It never grounds a label (MISS keeps
    `missed_gain_v1`)."""

    name = "better_alternative_v1"
    role = ClaimRole.COMPARISON
    directions = frozenset({B})
    predicate = "better_alternative"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        if judgement_ is None or judgement_.played is None or judgement_.loss is None:
            return ()
        if judgement_.played.rank == 1 or not judgement_.grade.at_least(Grade.INACCURACY):
            return ()
        assert judgement_.search is not None
        parent = ctx.subject.parent
        population = Population(PopulationKind.ENGINE_REPORTED, judgement_.search.search_id)
        return (
            self.make(
                ctx,
                context=NodeContext(parent),
                operands=(),
                target=VerificationTarget(Quantifier.EXISTS_ALTERNATIVE, parent, population),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        result = judgement(view, h, grading)
        assert result.played is not None and result.best is not None and result.loss is not None
        sid = search_id(h)
        evidence = (SearchRef(sid, result.best.rank), SearchRef(sid, result.played.rank))
        if result.best.rank != 1 or result.played.rank == 1 or result.loss <= 0:
            return refuted(h, evidence=evidence)
        finding = MissedGainFinding(SearchMoveRef(sid, result.best.rank, 1), result.loss)
        ranks = (result.best.rank, result.played.rank)
        proof = scope(view, h, grading, ranks, witnesses=(result.best.move,))
        return supported(h, proof, (finding,), evidence)


# -- best_stops_reply_v1 (EV-D §3) ------------------------------------------------------------------

NO_SEARCH = ExpansionSpec(False, False, False)


def _idx(square: str) -> int:
    """`idx(s)`: a1 = 0 … h8 = 63, the order of `squares` (EV-D §3.1)."""

    return ord(square[0]) - ord("a") + 8 * (int(square[1]) - 1)


def _record(view: TreeView, family: str, node: NodeId):
    record = view.fact(family, node)
    return None if isinstance(record, NotComputed) else record


def _exchange_at(view: TreeView, node: NodeId, square: str) -> tuple[int, PieceExchange] | None:
    """`ex(N, s)` and its index in `ExchangeFacts.pieces`."""

    return next(((i, r) for i, r in enumerate(view.fact(EXCHANGE, node).pieces)
                 if r.square == square), None)  # fmt: skip


def _gain(record: PieceExchange | None) -> int | None:
    return record.gain.value if record is not None and isinstance(record.gain, Defined) else None


def _attackers(squares, square: str, side: Color):
    entry = squares.squares[_idx(square)]
    return entry.white_attackers if side is Color.WHITE else entry.black_attackers


def _side(side: Color) -> str:
    return "white_attackers" if side is Color.WHITE else "black_attackers"


def _falls(lp: Line) -> bool | str:
    """`Lp` is `STABLE(Δp ≤ −1)` and the balance falls at ply 2; the reason when uncounted."""

    if lp.outcome.kind is OutcomeKind.MISSING and lp.outcome.reason != "LINE_TOO_SHORT":
        assert lp.outcome.reason is not None
        return lp.outcome.reason
    if lp.outcome.kind is not OutcomeKind.STABLE:
        return False
    assert lp.outcome.delta is not None
    return lp.outcome.delta <= -1 and lp.balances[2] < lp.balances[1]


def _legal(view: TreeView, node: NodeId, uci: str) -> int | None | str:
    """The index of `uci` in `status.legal_moves` at `node`, None when it is not legal, or
    `NOT_COMPUTED(status)` when the record is missing (EV1 review B1)."""

    status = view.fact("status", node)
    if not isinstance(status, StatusFacts):
        return "NOT_COMPUTED(status)"
    return next((i for i, m in enumerate(status.legal_moves) if m.uci == uci), None)


class BestStopsReply(Template):
    """EV-D §3: what the best move does about the opponent's reply `r` in `Lp`, by static exchange.
    RESCUES: it moves the piece `r` takes to safety. DEFENDS: the same capture `r`, profitable after
    the played move, gains nothing after the best move, whose piece recaptures first. COVERS: `r`
    played after the best move loses its piece on its square to the best move's piece.

    It says what static exchange evaluation shows on one square, never that the best move stops
    `r` overall (EV-D §3.3, V7). The counterfactual node `B1 + r` is created without a search."""

    name = "best_stops_reply_v1"
    role = ClaimRole.COMPARISON
    directions = frozenset({B})
    predicate = "best_stops_reply"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        found = materials(ctx)
        if judgement_ is None or found is None or not judgement_.grade.at_least(Grade.INACCURACY):
            return ()
        if judgement_.played is None or judgement_.played.rank == 1:
            return ()
        _ref, by_rank = found
        lp_id, l1_id = standard_line_ids(judgement_)
        lp = by_rank[lp_id.rank]
        at, played_at = seg(ctx.view, l1_id), seg(ctx.view, lp_id)
        if at is None or played_at is None or at.last - at.first < 1:
            return ()
        if played_at.last - played_at.first < 2 or lp.window.last < 2:
            return ()
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(LineSegment(l1_id, 0, 1), LineSegment(lp_id, 0, lp.window.last)),
                target=line_target(played_at),  # EV1 note 1: the scope's plies are Lp's window
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        l1_window, lp_window = h.operands
        sid = search_id(h)
        m = mover(view, h)
        lp = read_line(view, lp_window, m)
        if lp.k < 2:
            return inconclusive(h, "LINE_TOO_SHORT")
        p, a1, r_node = h.subject.parent, lp.nodes[1], lp.nodes[2]
        l1 = view.line(l1_window.line)
        b1 = l1.nodes[1]
        r, b = view.fact("move", r_node), view.fact("move", b1)
        if not isinstance(r, MoveFacts) or not isinstance(b, MoveFacts):
            return inconclusive(h, "NOT_COMPUTED(move)")
        base = (SearchRef(sid, 1), SearchRef(sid, lp.rank))
        capture = next(((i, e) for i, e in enumerate(r.events) if isinstance(e, Capture)), None)
        if capture is None:
            kind = ReplyKind.COVERS
        else:
            kind = ReplyKind.RESCUES if b.piece == capture[1].piece else ReplyKind.DEFENDS
        args = (h, view, grading, lp, base, (p, a1, r_node, b1), r, b)
        if kind is ReplyKind.RESCUES:
            return self._rescues(*args, capture)
        if kind is ReplyKind.DEFENDS:
            return self._defends(*args, capture)
        return self._covers(*args, l1)

    # -- the kinds (EV-D §3.3) ----------------------------------------------------------------

    def _rescues(self, h, view, grading, lp, base, nodes, r, b, capture) -> Verdict:
        p, a1, r_node, _b1 = nodes
        e_r, victim = capture
        s = r.to_square
        if victim.en_passant or victim.square != s:
            return refuted(h, evidence=base)
        if view.node(p).piece_at(s) != victim.piece or view.node(a1).piece_at(s) != victim.piece:
            return refuted(h, evidence=base)
        falls = _falls(lp)
        if isinstance(falls, str):
            return inconclusive(h, falls, evidence=base)
        if not falls:
            return refuted(h, evidence=base)
        wanted = tuple(FamilyNeed(n, EXCHANGE) for n in (p, a1)
                       if isinstance(view.fact(EXCHANGE, n), NotComputed))  # fmt: skip
        if wanted:
            return needs(h, wanted)
        at_p, at_a1 = _exchange_at(view, p, s), _exchange_at(view, a1, s)
        if at_p is None or at_a1 is None:
            return refuted(h, evidence=base)
        (i_p, before), (i_a1, after) = at_p, at_a1
        evidence = (
            *base,
            fact_ref(view, "move", r_node, ("events", e_r)),
            fact_ref(view, EXCHANGE, p, ("pieces", i_p)),
            fact_ref(view, EXCHANGE, a1, ("pieces", i_a1)),
        )
        safe = before.safe_moves
        exposed = (_gain(before) or 0) >= 1 and (_gain(after) or 0) >= 1
        if not exposed or not isinstance(safe, tuple) or b.uci not in safe:
            return refuted(h, evidence=evidence)
        finding = ReplyFinding(ReplyKind.RESCUES, SearchMoveRef(search_id(h), 1, 1),
                               MoveRef(r_node), PieceRef(victim.piece, p, s),
                               None, None, None, None, None, None, None)  # fmt: skip
        return self._supported(h, view, grading, lp, finding, evidence)

    def _defends(self, h, view, grading, lp, base, nodes, r, b, capture) -> Verdict:
        p, a1, r_node, b1 = nodes
        e_r, victim = capture
        s, v = r.to_square, victim.piece
        ordinary = not victim.en_passant and victim.square == s and r.piece_type.value != "king"
        if not ordinary or any(isinstance(e, Promotion) for e in r.events):
            return refuted(h, evidence=base)
        if any(view.node(n).piece_at(s) != v for n in (p, a1, b1)):
            return refuted(h, evidence=base)
        squares_a1, squares_b1 = _record(view, "squares", a1), _record(view, "squares", b1)
        if squares_a1 is None or squares_b1 is None:
            return inconclusive(h, "NOT_COMPUTED(squares)", evidence=base)
        l = _legal(view, b1, r.uci)
        if isinstance(l, str):
            return inconclusive(h, l, evidence=base)
        if l is None:
            return refuted(h, evidence=base)  # rev. 3, B5: not a defence by check or pin
        m = mover(view, h)
        j = next((j for j, x in enumerate(_attackers(squares_b1, s, m))
                  if x.square == b.to_square and not x.absolutely_pinned), None)  # fmt: skip
        before = {view.node(a1).piece_at(x.square) for x in _attackers(squares_a1, s, m)}
        if j is None or b.piece in before:
            return refuted(h, evidence=base)  # no new, unpinned defender
        falls = _falls(lp)
        if isinstance(falls, str):
            return inconclusive(h, falls, evidence=base)
        if not falls:
            return refuted(h, evidence=base)
        c = view.child(b1, r.uci)
        wanted: list = []
        if c is None:
            wanted.append(LineNeed(b1, (r.uci,), NO_SEARCH))
        for node in (r_node, c):
            if node is not None and isinstance(view.fact(EXCHANGE, node), NotComputed):
                wanted.append(FamilyNeed(node, EXCHANGE))
        if wanted:
            return needs(h, tuple(wanted))
        assert c is not None
        again = view.fact("move", c)
        if not isinstance(again, MoveFacts):
            return inconclusive(h, "NOT_COMPUTED(move)", evidence=base)
        e_c = next((i for i, e in enumerate(again.events) if isinstance(e, Capture)), None)
        same = (
            e_c is not None
            and again.piece == r.piece
            and again.to_square == s
            and again.events[e_c].piece == v
            and again.events[e_c].square == s
            and view.node(c).piece_at(s) == r.piece
            and view.node(r_node).piece_at(s) == r.piece
        )
        if not same:
            return refuted(h, evidence=base)
        at_r, at_c = _exchange_at(view, r_node, s), _exchange_at(view, c, s)
        if at_r is None or at_c is None:
            return refuted(h, evidence=base)
        (i_r, played_x), (i_c, best_x) = at_r, at_c
        evidence = (
            *base,
            fact_ref(view, "move", r_node, ("events", e_r)),
            fact_ref(view, "move", c, ("events", e_c)),
            fact_ref(view, EXCHANGE, r_node, ("pieces", i_r)),
            fact_ref(view, EXCHANGE, c, ("pieces", i_c)),
            fact_ref(view, "status", b1, ("legal_moves", l)),
            fact_ref(view, "squares", b1, ("squares", _idx(s), _side(m), j)),
        )
        q_r, q_c = _gain(played_x), _gain(best_x)
        if q_r is None or q_c is None:
            return refuted(h, evidence=evidence)
        value = POINTS_V1_BY_TYPE[victim.piece_type]
        g_r, g_c = value - q_r, value - q_c  # the reply's own gain (rev. 4, B7)
        first = best_x.first_capture
        if g_r < 1 or g_c > 0 or first is None or first[:2] != b.to_square:
            return refuted(h, evidence=evidence)
        finding = ReplyFinding(ReplyKind.DEFENDS, SearchMoveRef(search_id(h), 1, 1),
                               MoveRef(r_node), PieceRef(v, b1, s), SquareRef(s), b1, c, first,
                               None, g_r, g_c)  # fmt: skip
        return self._supported(h, view, grading, lp, finding, evidence)

    def _covers(self, h, view, grading, lp, base, nodes, r, b, l1) -> Verdict:
        p, a1, r_node, b1 = nodes
        s, x = r.to_square, r.piece
        if r.castling is not None or view.node(p).piece_at(s) is not None:
            return refuted(h, evidence=base)
        if view.node(a1).piece_at(s) is not None:
            return refuted(h, evidence=base)
        squares_a1, squares_b1 = _record(view, "squares", a1), _record(view, "squares", b1)
        if squares_a1 is None or squares_b1 is None:
            return inconclusive(h, "NOT_COMPUTED(squares)", evidence=base)
        m = mover(view, h)
        if any(not a.absolutely_pinned for a in _attackers(squares_a1, s, m)):
            return refuted(h, evidence=base)  # the square was already covered
        j = next((j for j, a in enumerate(_attackers(squares_b1, s, m))
                  if a.square == b.to_square and not a.absolutely_pinned), None)  # fmt: skip
        if j is None:
            return refuted(h, evidence=base)
        later = None
        for node in lp.nodes[3:]:
            move = view.fact("move", node)
            if not isinstance(move, MoveFacts):
                return inconclusive(h, "NOT_COMPUTED(move)", evidence=base)
            if move.piece == x and (move.gives_check or any(isinstance(e, Capture)
                                                            for e in move.events)):  # fmt: skip
                later = node
                break
        if later is None:
            return refuted(h, evidence=base)  # the reply does nothing later in the line
        if len(l1.nodes) > 2 and view.node(l1.nodes[2]).incoming_move == r.uci:
            return refuted(h, evidence=base)  # the opponent enters the square anyway
        l = _legal(view, b1, r.uci)
        if isinstance(l, str):
            return inconclusive(h, l, evidence=base)
        if l is None:
            return refuted(h, evidence=base)
        c = view.child(b1, r.uci)
        if c is None:
            return needs(h, (LineNeed(b1, (r.uci,), NO_SEARCH),))
        if isinstance(view.fact(EXCHANGE, c), NotComputed):
            return needs(h, (FamilyNeed(c, EXCHANGE),))
        at_c = _exchange_at(view, c, s)
        if at_c is None:
            return refuted(h, evidence=base)
        i_c, entered = at_c
        evidence = (
            *base,
            fact_ref(view, "move", r_node, ("to_square",)),
            fact_ref(view, "squares", a1, ("squares", _idx(s), _side(m))),
            fact_ref(view, "squares", b1, ("squares", _idx(s), _side(m), j)),
            fact_ref(view, "status", b1, ("legal_moves", l)),
            fact_ref(view, EXCHANGE, c, ("pieces", i_c)),
            fact_ref(view, "move", later, ()),
        )
        lost, first = _gain(entered), entered.first_capture
        if lost is None or lost < 1 or first is None or first[:2] != b.to_square:
            return refuted(h, evidence=evidence)
        finding = ReplyFinding(ReplyKind.COVERS, SearchMoveRef(search_id(h), 1, 1),
                               MoveRef(r_node), PieceRef(x, c, s), SquareRef(s), b1, c, first,
                               lost, None, None)  # fmt: skip
        return self._supported(h, view, grading, lp, finding, evidence)

    def _supported(self, h, view, grading, lp, finding, evidence) -> Verdict:
        """The scope is `Lp`'s window (rev. 3, N3), stated on the target, `Lp`'s attached segment,
        which always holds it (R0-D §9.2); `L1` is among the scope's lines."""

        proof = scope(view, h, grading, (1, lp.rank), line=lp, extra_policies=(SEE,))
        return supported(h, proof, (finding,), evidence)
