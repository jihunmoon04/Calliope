"""`better_move_v1` (R2-D §3.12): the best line's mate or material outcome beats the played one."""

from __future__ import annotations

from calliope.facts import TreeView
from calliope.reasoning.catalogue.base import (
    REQUIRE_LINE,
    B,
    Template,
    claims_of,
    inconclusive,
    judged,
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
from calliope.reasoning.findings import ComparisonFinding
from calliope.reasoning.hypotheses import (
    ClaimRole,
    Hypothesis,
    LineContext,
    PremiseRelation,
    PremiseUse,
    ProposeContext,
    RelationDecl,
    RelationKind,
    SearchCompat,
)
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

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict:
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
            proof = scope(view, h, (l1.rank, lp.rank), line=l1)
            return supported(h, proof, (finding,), evidence)  # rule 1
        return refuted(h, (finding,), evidence)  # rule 2
