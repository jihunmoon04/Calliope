"""Claims on the `exchange` facts (LV-D §4.1, §5, §6, §15): a piece offer, its capture branch and
a rescue.

`piece_offer_v1` reads S and the static exchange facts (F6-D) at P, C and the children of S's
other lines; once its static steps hold, it asks for a survey after the opponent's capture. It
says the move offers a piece, not that the offer is sound. `capture_holds_v1`, proposed on a
SUPPORTED offer, reads that survey alone. A sound sacrifice is the pair, both SUPPORTED
(`sound_sacrifice` in `reasoning.labels`); `label_v2` makes a provisional BRILLIANT from it (LV-D
§5, rule `brilliant_p2`). `rescue_v1` takes a routine retreat out of GREAT (LV-D §4.1).
"""

from __future__ import annotations

from calliope.facts import (
    POINTS_V1_BY_TYPE,
    Capture,
    Color,
    Defined,
    ExchangeFacts,
    ExpansionSpec,
    NodeId,
    NotApplicable,
    NotComputed,
    PieceExchange,
    Promotion,
    SearchKind,
    TreeView,
    Wdl,
)
from calliope.reasoning.catalogue.base import (
    REQUIRE_LINE,
    F,
    Template,
    edge,
    exact_scope,
    inconclusive,
    judged,
    judgement,
    judgement_ref,
    line_target,
    mover,
    needs,
    played,
    refuted,
    scope,
    search_id,
    seg,
    supported,
    supported_claims,
)
from calliope.reasoning.findings import CaptureHoldsFinding, PieceOfferFinding, RescueFinding
from calliope.reasoning.grading import Grading
from calliope.reasoning.hypotheses import (
    Basis,
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
    SearchCompat,
    VerificationTarget,
)
from calliope.reasoning.lines import fact_ref
from calliope.reasoning.needs import FamilyNeed, LineNeed
from calliope.reasoning.observer import Grade, score_points, standard_line_ids
from calliope.reasoning.observer import expected as wdl_points
from calliope.reasoning.refs import LineSegment, MoveRef, PieceRef, SearchRef
from calliope.reasoning.verification import ProofScope, Verdict

# the parameters of `brilliant_p2` (LV-D §5, §15): provisional, changed only by an amendment (§8)
OFFER_MIN = 1  # points_v1 net
NEAR_BEST = 100  # loss, 1/2000
NOT_BAD = 1000  # expected points after the move, and after the capture
WINNING = 1700  # a non-offering line at least this good: the mover was winning anyway
SEE = "see_v1"
SURVEY = ExpansionSpec(True, False, False)
EXCHANGE = "exchange"


def _index(square: str) -> int:
    """The square's index a1 = 0 … h8 = 63, for the tie-break of LV-D §5 step 1."""

    return (int(square[1]) - 1) * 8 + ord(square[0]) - ord("a")


def _not_exposed(value: object) -> bool:
    return isinstance(value, NotApplicable) and value.reason == "NOT_EXPOSED"


def _facts(view: TreeView, node: NodeId) -> ExchangeFacts | None:
    record = view.fact(EXCHANGE, node)
    return record if isinstance(record, ExchangeFacts) else None


def _captured(view: TreeView, child: NodeId) -> int:
    """`points_v1` of what the move into `child` captured."""

    move = view.fact("move", child)
    capture = next((e for e in move.events if isinstance(e, Capture)), None)
    return POINTS_V1_BY_TYPE[capture.piece_type] if capture is not None else 0


def _offer(view: TreeView, child: NodeId, side: Color) -> tuple[PieceExchange, int] | None:
    """LV-D §5 step 1 at `child`: the `side`'s non-king, non-pawn piece with the largest offer.

    A piece the move into `child` has just promoted is not offered (`brilliant_p2`, LV-D §15): the
    move gave up a pawn, not the piece it became."""

    facts = _facts(view, child)
    assert facts is not None
    captured = _captured(view, child)
    move = view.fact("move", child)
    promoted = move.to_square if any(isinstance(e, Promotion) for e in move.events) else None
    best: tuple[PieceExchange, int] | None = None
    for record in facts.pieces:
        if record.color is not side or record.piece_type.value in ("pawn", "king"):
            continue
        if record.square == promoted:
            continue
        if not isinstance(record.gain, Defined) or record.gain.value <= 0:
            continue
        amount = record.gain.value - captured
        if best is None or (amount, -_index(record.square)) > (best[1], -_index(best[0].square)):
            best = (record, amount)
    return best


def _at(facts: ExchangeFacts, square: str) -> PieceExchange | None:
    return next((r for r in facts.pieces if r.square == square), None)


def _survey_at(view: TreeView, node: NodeId) -> str | None:
    return next((s.search_id for s in view.searches(node) if s.kind is SearchKind.SURVEY), None)


def _edge_segment(view: TreeView, judgement_) -> LineSegment | None:
    """Lp's first ply P → C, on S's line: the target names S (LV-D §6.1)."""

    ids = standard_line_ids(judgement_)
    if ids is None:
        return None
    whole = seg(view, ids[0])
    if whole is None or whole.last == whole.first:
        return None
    return LineSegment(whole.line, whole.first, whole.first + 1)


class PieceOffer(Template):
    """LV-D §5 steps 1–4 and §6.1 (provisional rule `brilliant_p2`): the move offers a piece.

    SUPPORTED says the static steps hold and the capture survey exists. It does not say the offer
    is sound: that is `capture_holds_v1` resting on it. Nothing reads this claim alone as a
    sacrifice (LV1 review B1)."""

    name = "piece_offer_v1"
    role = ClaimRole.FUNCTION
    directions = frozenset({F})
    predicate = "piece_offer"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        if judgement_ is None or judgement_.played is None or judgement_.loss is None:
            return ()
        if judgement_.loss >= NEAR_BEST or judgement_.played.expected < NOT_BAD:
            return ()
        if ctx.view.fact("status", ctx.subject.parent).legal_move_count < 2:
            return ()
        at = _edge_segment(ctx.view, judgement_)
        if at is None:
            return ()
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(),
                target=line_target(at),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        parent, child = h.subject.parent, h.subject.child
        result = judgement(view, h, grading)
        assert result.played is not None and result.loss is not None
        sid = search_id(h)
        side = mover(view, h)
        if result.loss >= NEAR_BEST or result.played.expected < NOT_BAD:
            return refuted(h, evidence=(SearchRef(sid, result.played.rank),))  # step 3
        others = [a for a in result.alternatives if a.rank != result.played.rank]
        wanted: list = []
        children: dict[int, NodeId] = {}
        for line in others:
            node = view.child(parent, line.move)
            if node is None:  # cut by the node budget: create it first (LV-D §6.1, review B1)
                wanted.append(LineNeed(parent, (line.move,), ExpansionSpec(False, False, False)))
                continue
            children[line.rank] = node
        for node in (parent, child, *children.values()):
            if isinstance(view.fact(EXCHANGE, node), NotComputed):
                wanted.append(FamilyNeed(node, EXCHANGE))
        if wanted:
            return needs(h, tuple(wanted))
        # step 1: a piece is offered
        found = _offer(view, child, side)
        evidence = (SearchRef(sid, result.played.rank), fact_ref(view, EXCHANGE, child))
        if found is None or found[1] < OFFER_MIN:
            return refuted(h, evidence=evidence)
        offered, amount = found
        move = view.fact("move", child)
        before_square = move.from_square if offered.square == move.to_square else offered.square
        before_facts = _facts(view, parent)
        assert before_facts is not None
        before = _at(before_facts, before_square)
        assert before is not None
        # step 2: saveable (the piece's own safe moves) and created or a capture
        if not _not_exposed(before.safe_moves) and before.safe_moves == ():
            return refuted(h, evidence=evidence)
        capture = any(isinstance(e, Capture) for e in move.events)
        created: bool | None
        if isinstance(before.gain, NotApplicable):  # in check: unknown, never read as 0
            created = None
            if not capture:
                return inconclusive(h, "NOT_COMPUTED(IN_CHECK)", evidence=evidence)
        else:
            assert isinstance(before.gain, Defined) and isinstance(offered.gain, Defined)
            created = before.gain.value < offered.gain.value
            if not (created or capture):
                return refuted(h, evidence=evidence)
        # step 4: not already winning with a line that offers nothing
        keeping = [
            line for line in others
            if (o := _offer(view, children[line.rank], side)) is None or o[1] < OFFER_MIN
        ]  # fmt: skip
        best = max(keeping, key=lambda line: (line.expected, -line.rank), default=None)
        if best is not None and best.expected >= WINNING:
            return refuted(h, evidence=(*evidence, SearchRef(sid, best.rank)))
        # step 5 is `capture_holds_v1`: ask for the survey after the capture, once
        assert offered.first_capture is not None
        taken = view.child(child, offered.first_capture)
        if taken is None or _survey_at(view, taken) is None:
            return needs(h, (LineNeed(child, (offered.first_capture,), SURVEY),))
        piece = view.node(child).piece_at(offered.square)
        assert piece is not None
        finding = PieceOfferFinding(
            PieceRef(piece, child, offered.square),
            amount,
            created,
            capture,
            MoveRef(taken),
            SearchRef(sid, best.rank) if best is not None else None,
            best.expected if best is not None else None,
        )
        ranks = (result.played.rank, *((best.rank,) if best is not None else ()))
        proof = scope(view, h, grading, ranks, extra_policies=(SEE,))
        refs = (
            fact_ref(view, EXCHANGE, parent),
            *(fact_ref(view, EXCHANGE, n) for n in children.values()),
        )
        return supported(h, proof, (finding,), (*evidence, *refs))


class CaptureHolds(Template):
    """LV-D §6.2: after the opponent takes the offered piece, the mover holds half a point."""

    name = "capture_holds_v1"
    role = ClaimRole.CONSEQUENCE
    directions = frozenset({F})
    predicate = "capture_holds"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        out = []
        for offer in supported_claims(ctx, PieceOffer.name):
            (finding,) = (f for f in offer.verdict.findings if isinstance(f, PieceOfferFinding))
            x = finding.taken_by.node
            sid = _survey_at(ctx.view, x)
            if sid is None:
                continue
            use = PremiseUse(
                offer.id,
                REQUIRE_LINE,
                PremiseRelation.EARLIER_POSITION,
                SearchCompat.ANY_SEARCH,
            )
            out.append(
                self.make(
                    ctx,
                    context=NodeContext(x),
                    operands=(),
                    target=VerificationTarget(
                        Quantifier.EXISTS_RESPONSE, x, Population(PopulationKind.ENGINE_RANKED, sid)
                    ),
                    premises=(use,),
                    origins=(offer.id,),
                )
            )
        return tuple(out)

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        sid = search_id(h)
        search = view.search(sid)
        if search.kind is not SearchKind.SURVEY:
            return inconclusive(h, "SCOPE_SHORT")
        if not search.lines:
            return inconclusive(h, "NOT_COMPUTED(NO_LINES)")
        x = h.target.at
        assert isinstance(x, NodeId)
        side = view.node(x).side_to_move
        best = search.lines[0]
        if grading.curve is not None:
            expected = score_points(best.score, side, grading)
        elif isinstance(best.wdl, Wdl):  # quality_v1 reads the WDL (R0-D §7.2)
            expected = wdl_points(best.wdl, side)
        else:
            return inconclusive(h, "NOT_COMPUTED(WDL_UNAVAILABLE)")
        finding = CaptureHoldsFinding(SearchRef(sid, best.rank), expected)
        evidence = (SearchRef(sid, best.rank),)
        if expected < NOT_BAD:
            return refuted(h, (finding,), evidence)
        proof = ProofScope(
            Basis.ENGINE,
            x,
            Quantifier.EXISTS_RESPONSE,
            h.target.population,
            (best.move,),
            (SearchRef(sid, best.rank),),
            search.profile.depth,
            search.multipv,
            policies=("points_v1", grading.policy),
        )
        return supported(h, proof, (finding,), evidence)


class Rescue(Template):
    """LV-D §4.1: the move saves a piece that was en prise (it takes the move out of GREAT)."""

    name = "rescue_v1"
    role = ClaimRole.FUNCTION
    directions = frozenset({F})
    predicate = "rescue"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        if judgement_ is None or judgement_.grade is not Grade.BEST:
            return ()
        parent, child = ctx.subject.parent, ctx.subject.child
        move = ctx.view.fact("move", child)
        if move.piece_type.value == "king":
            return ()
        pieces = ctx.view.fact("pieces", parent)
        record = next((p for p in pieces.pieces if p.square == move.from_square), None)
        if record is None or record.attacker_count == 0:
            return ()
        at = edge(ctx.view, parent, child)
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(MoveRef(child),),
                target=VerificationTarget(Quantifier.SPECIFIC_LINE, at, played(child), horizon=1),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        parent, child = h.subject.parent, h.subject.child
        wanted = tuple(FamilyNeed(n, EXCHANGE) for n in (parent, child)
                       if isinstance(view.fact(EXCHANGE, n), NotComputed))  # fmt: skip
        if wanted:
            return needs(h, wanted)
        move = view.fact("move", child)
        before = _at(_facts(view, parent), move.from_square)
        after = _at(_facts(view, child), move.to_square)
        evidence = (fact_ref(view, EXCHANGE, parent), fact_ref(view, EXCHANGE, child))
        if before is None or after is None or not isinstance(before.gain, Defined):
            return refuted(h, evidence=evidence)  # in check: a check evasion, already excluded
        assert isinstance(after.gain, Defined)
        if before.gain.value >= 1 and after.gain.value == 0:
            piece = view.node(child).piece_at(move.to_square)
            assert piece is not None
            finding = RescueFinding(PieceRef(piece, child, move.to_square), before.gain.value)
            return supported(h, exact_scope(h, policies=(SEE,)), (finding,), evidence)
        return refuted(h, evidence=evidence)
