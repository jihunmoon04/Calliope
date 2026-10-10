"""Material consequences (R2-D §3.1, §3.2): measured from P along `Lp`, contrasted with `L1`."""

from __future__ import annotations

from calliope.facts import TreeView
from calliope.reasoning.catalogue.base import (
    B,
    F,
    Template,
    inconclusive,
    judged,
    judgement_ref,
    line_target,
    lines,
    materials,
    mover,
    refuted,
    scope,
    search_id,
    seg,
    supported,
)
from calliope.reasoning.findings import MaterialFinding, OutcomeKind
from calliope.reasoning.hypotheses import ClaimRole, Hypothesis, LineContext, ProposeContext
from calliope.reasoning.lines import (
    Line,
    compare,
    decisive_event,
    event_ref,
    mate_for,
    undecided_reason,
    veto,
)
from calliope.reasoning.observer import Grade, standard_line_ids
from calliope.reasoning.refs import MaterialAmount, SearchRef
from calliope.reasoning.verification import Verdict


def played_line_rules(h: Hypothesis, lp: Line) -> Verdict | None:
    """Rules 1–2 of R2-D §3.1: a mate, a missing record, an open or drawn window."""

    kind = lp.outcome.kind
    if kind is OutcomeKind.MATE:
        return inconclusive(h, "MATE_LINE")
    if kind in (OutcomeKind.MISSING, OutcomeKind.OPEN):
        return inconclusive(h, undecided_reason(lp.outcome))
    if kind is OutcomeKind.DRAWN:
        return inconclusive(h, "UNSTABLE")
    return None


class _Material(Template):
    role = ClaimRole.CONSEQUENCE

    def _wants(self, ctx: ProposeContext, judgement, lp) -> bool:
        raise NotImplementedError

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement = judged(ctx)
        found = materials(ctx)
        if judgement is None or found is None:
            return ()
        ref, by_rank = found
        lp_id, l1_id = standard_line_ids(judgement)
        lp, l1 = by_rank[lp_id.rank], by_rank[l1_id.rank]
        at = seg(ctx.view, lp_id)
        if at is None or not self._wants(ctx, judgement, lp):
            return ()
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(lp.window, l1.window),
                target=line_target(at),
                origins=(judgement_ref(ctx), ref),
            ),
        )


class MaterialLoss(_Material):
    name = "material_loss_v1"
    directions = frozenset({B})
    predicate = "material_loss"

    def _wants(self, ctx, judgement, lp) -> bool:
        return judgement.grade.at_least(Grade.INACCURACY)

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict:
        lp, l1 = lines(view, h, h.operands)
        sid = search_id(h)
        evidence = [SearchRef(sid, lp.rank), SearchRef(sid, l1.rank), lp.window, l1.window]
        early = played_line_rules(h, lp)
        if early is not None:
            return early
        delta_p = lp.outcome.delta
        assert delta_p is not None
        if delta_p >= 0:
            return refuted(h, evidence=tuple(evidence))  # rule 3
        best = l1.outcome
        if best.kind is OutcomeKind.DRAWN:
            return inconclusive(h, "UNSTABLE")  # rule 4: incomparable with STABLE
        order = compare(best, lp.outcome, mover(view, h))
        if order is None:
            return inconclusive(h, undecided_reason(best))  # rule 4
        if order <= 0:
            return refuted(h, evidence=tuple(evidence))  # rule 6: L1 loses at least as much
        event = decisive_event(lp, loss=True)
        assert event is not None
        evidence.append(event_ref(view, event))
        if mate_for(best, mover(view, h)):
            amount = -delta_p
        else:
            assert best.delta is not None
            amount = min(-delta_p, best.delta - delta_p)
        finding = MaterialFinding(MaterialAmount(amount), event, lp.outcome, best)
        proof = scope(view, h, (lp.rank, l1.rank), line=lp)
        return supported(h, proof, (finding,), tuple(evidence))


class MaterialGain(_Material):
    name = "material_gain_v1"
    directions = frozenset({F, B})
    predicate = "material_gain"

    def _wants(self, ctx, judgement, lp) -> bool:
        return any(ply % 2 == 1 for ply in lp.changes)  # the mover plays the odd plies from P

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict:
        lp, l1 = lines(view, h, h.operands)
        sid = search_id(h)
        evidence = [SearchRef(sid, lp.rank), lp.window]
        early = played_line_rules(h, lp)
        if early is not None:
            return early
        delta_p = lp.outcome.delta
        assert delta_p is not None
        baseline = veto(view, lp)
        delta_b = baseline[-1] if baseline is not None else delta_p
        if min(delta_p, delta_b) < 1:
            return refuted(h, evidence=tuple(evidence))
        event = decisive_event(lp, loss=False)
        assert event is not None
        evidence.append(event_ref(view, event))
        amount = MaterialAmount(min(delta_p, delta_b))
        finding = MaterialFinding(amount, event, lp.outcome, l1.outcome)
        proof = scope(view, h, (lp.rank, l1.rank), line=lp)
        return supported(h, proof, (finding,), tuple(evidence))
