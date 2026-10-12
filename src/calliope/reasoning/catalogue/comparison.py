"""`better_move_v1` (R2-D §3.12): the best line's mate or material outcome beats the played one.
`missed_gain_v1` (MV-D §4): rank 1 of S beats the played move by expected points.
`better_alternative_v1` (EA-D §3): rank 1 of S beats an inaccuracy or worse, by any loss."""

from __future__ import annotations

from calliope.facts import TreeView
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
    opponent,
    refuted,
    scope,
    search_id,
    seg,
    supported,
)
from calliope.reasoning.findings import ComparisonFinding, MissedGainFinding
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
from calliope.reasoning.lines import compare, decided, fact_ref, mate_for, undecided_reason
from calliope.reasoning.observer import Grade, standard_line_ids
from calliope.reasoning.refs import SearchMoveRef, SearchRef
from calliope.reasoning.verification import Verdict

MATE_ALLOWED = "mate_allowed_v1"
MATERIAL_LOSS = "material_loss_v1"


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
