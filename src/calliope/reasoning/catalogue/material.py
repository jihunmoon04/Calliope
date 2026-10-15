"""Material consequences (R2-D §3.1, §3.2 as amended by EA-D §2 and EF-D §2–§3): measured from P
along `Lp`, contrasted with `L1`; the event under `trade_pairs_v1`; the `ATTRIBUTED` check of
`concession_v1`."""

from __future__ import annotations

from calliope.facts import Color, Cp, TreeView
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
    needs,
    refuted,
    scope,
    search_id,
    seg,
    supported,
)
from calliope.reasoning.findings import ConcessionFinding, MaterialFinding, OutcomeKind
from calliope.reasoning.grading import Grading
from calliope.reasoning.hypotheses import ClaimRole, Hypothesis, LineContext, ProposeContext
from calliope.reasoning.lines import (
    CONCESSION_POLICY,
    IN_CHECK,
    SEE_POLICY,
    Attribution,
    Line,
    attribution,
    compare,
    decisive_event,
    decisive_ply,
    event_ref,
    mate_for,
    undecided_reason,
    veto,
)
from calliope.reasoning.observer import Grade, standard_line_ids
from calliope.reasoning.refs import MaterialAmount, PieceRef, SearchRef
from calliope.reasoning.verification import ATTRIBUTED, CausalCheck, Verdict

GAIN_CP_PER_POINT = 80  # EA-D E2: a later-line gain needs Lp's score >= this per point gained
SCORE_CHECK = "material_gain.score_check"  # the filter's registry id (DF-D §4.1)


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


def attributed(
    h: Hypothesis,
    view: TreeView,
    grading: Grading,
    lp: Line,
    l1: Line,
    finding: MaterialFinding,
    evidence: list,
) -> Verdict:
    """EF-D §3.4: the claim with its `ATTRIBUTED` check, the needs of `concession_v1`, or
    `INCONCLUSIVE(NOT_COMPUTED(IN_CHECK))` when the undecided nodes leave the attribution open."""

    result = attribution(view, lp, finding.event)
    if result.state is None:
        return needs(h, result.needs)
    if result.state is Attribution.UNDECIDED:
        return inconclusive(h, IN_CHECK, evidence=tuple(evidence))
    passed = result.state is Attribution.ATTRIBUTED
    findings: tuple = (finding, CausalCheck(ATTRIBUTED, passed, result.evidence))
    if not passed:
        findings += (_concession(view, lp, finding, result.origins),)
    proof = scope(
        view, h, grading, (lp.rank, l1.rank), line=lp,
        extra_policies=(SEE_POLICY, CONCESSION_POLICY),
    )  # fmt: skip
    return supported(h, proof, findings, tuple(evidence))


def _concession(view: TreeView, lp: Line, finding: MaterialFinding, origins) -> ConcessionFinding:
    victim = finding.event.victim
    assert victim is not None and origins is not None
    q = finding.event.ply
    at = tuple(dict.fromkeys(lp.nodes[min(o, q - 1)] for o in origins))
    square = view.node(at[0]).square_of(victim.piece)
    assert square is not None
    return ConcessionFinding(PieceRef(victim.piece, at[0], square), origins[0], origins[1], at)


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
    """`material_loss_v2` (EF-D §3.6): `material_loss_v1`, the event under `trade_pairs_v1`, and
    the `ATTRIBUTED` check after rule 6."""

    name = "material_loss_v2"
    directions = frozenset({B})
    predicate = "material_loss"

    def _wants(self, ctx, judgement, lp) -> bool:
        return judgement.grade.at_least(Grade.INACCURACY)

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
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
        return attributed(h, view, grading, lp, l1, finding, evidence)  # rule 7 (EF-D §3)


class MaterialGain(_Material):
    """`material_gain_v3` (EF-D §3.6): `material_gain_v2` (EA-D §2: a gain decided later in `Lp`,
    event ply >= 3, that `Lp`'s own score contradicts is refuted — an empirical filter, not a proof
    the gain is kept), the event under `trade_pairs_v1`, and the `ATTRIBUTED` check after rule 3."""

    name = "material_gain_v3"
    directions = frozenset({F, B})
    predicate = "material_gain"

    def _wants(self, ctx, judgement, lp) -> bool:
        return any(ply % 2 == 1 for ply in lp.changes)  # the mover plays the odd plies from P

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
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
        # EA-D §2 rule 3 reads the line's own balances (EF-D §2: only the named event is reduced)
        decided_at = decisive_ply(lp.balances, loss=False)
        assert decided_at is not None
        if decided_at >= 3 and _score_for(lp) < GAIN_CP_PER_POINT * min(delta_p, delta_b):
            return refuted(h, evidence=tuple(evidence), refuted_by=SCORE_CHECK)  # EA-D §2 rule 3
        evidence.append(event_ref(view, event))
        amount = MaterialAmount(min(delta_p, delta_b))
        finding = MaterialFinding(amount, event, lp.outcome, l1.outcome)
        return attributed(h, view, grading, lp, l1, finding, evidence)  # rule 4 (EF-D §3)


def _score_for(lp: Line) -> int:
    """`Lp`'s centipawns for the mover. Only a `STABLE` line reaches rule 3, and a mate score makes
    the line `MATE` (rule 1, EA-D review B1), so the score is a `Cp`."""

    score = lp.fact.score
    assert isinstance(score, Cp)
    return score.value if lp.mover is Color.WHITE else -score.value
