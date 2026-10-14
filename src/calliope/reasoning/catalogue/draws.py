"""Draws by checks (EV-D §2): `checks_draw_v1`, the played move's line ends in checks that draw;
`checks_draw_missed_v1`, the best line was the mover's own checks to a draw.

A checking draw is a run of checks ending the window, a near-zero score, and a fifth or third
occurrence (rule facts) or the engine's WDL (`reasoning.lines.checking_draw`). The text tells a
draw by rule from a draw by score (EV-D V7)."""

from __future__ import annotations

from calliope.facts import TreeView
from calliope.reasoning.catalogue.base import (
    B,
    Template,
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
from calliope.reasoning.findings import ChecksDrawFinding
from calliope.reasoning.grading import Grading
from calliope.reasoning.hypotheses import ClaimRole, Hypothesis, LineContext, ProposeContext
from calliope.reasoning.lines import Line, checking_draw, checking_draw_evidence
from calliope.reasoning.observer import Grade, standard_line_ids
from calliope.reasoning.refs import SearchRef
from calliope.reasoning.verification import Verdict


def _windows(ctx: ProposeContext, *, not_best: bool):
    """`(Lp, L1)` of a decided judgement graded INACCURACY or worse, both attached; else None."""

    judgement = judged(ctx)
    found = materials(ctx)
    if judgement is None or found is None or not judgement.grade.at_least(Grade.INACCURACY):
        return None
    if not_best and (judgement.played is None or judgement.played.rank == 1):
        return None
    _ref, by_rank = found
    lp_id, l1_id = standard_line_ids(judgement)
    at_p, at_1 = seg(ctx.view, lp_id), seg(ctx.view, l1_id)
    if at_p is None or at_1 is None:
        return None
    return (by_rank[lp_id.rank], at_p), (by_rank[l1_id.rank], at_1)


class ChecksDraw(Template):
    """EV-D §2.2: the played move's line is a checking draw, by either side, and the best line is
    not the same side's checking draw."""

    name = "checks_draw_v1"
    role = ClaimRole.CONSEQUENCE
    directions = frozenset({B})
    predicate = "checks_draw"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        found = _windows(ctx, not_best=False)
        if found is None:
            return ()
        (lp, at), (l1, _) = found
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(lp.window, l1.window),
                target=line_target(at),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        lp, l1 = lines(view, h, h.operands)
        m = mover(view, h)
        reasons: list[str] = []
        for side in (opponent(m), m):  # the opponent's run first
            found = checking_draw(view, lp, side)
            if isinstance(found, str):
                reasons.append(found)
                continue
            if found is None:
                continue
            best = checking_draw(view, l1, side)
            if isinstance(best, str):
                reasons.append(best)
                continue
            if best is None:
                return _supported(h, view, grading, lp, l1, found)
        if reasons:
            return inconclusive(h, reasons[0])
        return refuted(h, evidence=_searches(h, lp, l1))


class ChecksDrawMissed(Template):
    """EV-D §2.3: the best line is the mover's checking draw and the played line is no checking
    draw of either side. The loss already says the draw was better than `Lp`."""

    name = "checks_draw_missed_v1"
    role = ClaimRole.COMPARISON
    directions = frozenset({B})
    predicate = "checks_draw_missed"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        found = _windows(ctx, not_best=True)
        if found is None:
            return ()
        (lp, _), (l1, at) = found
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(l1.window, lp.window),
                target=line_target(at),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        l1, lp = lines(view, h, h.operands)
        m = mover(view, h)
        found = checking_draw(view, l1, m)
        if isinstance(found, str):
            return inconclusive(h, found)
        if found is None:
            return refuted(h, evidence=_searches(h, l1, lp))
        reasons: list[str] = []
        for side in (opponent(m), m):
            played = checking_draw(view, lp, side)
            if isinstance(played, str):
                reasons.append(played)
            elif played is not None:
                return refuted(h, evidence=_searches(h, l1, lp))
        if reasons:
            return inconclusive(h, reasons[0])
        return _supported(h, view, grading, l1, lp, found)


def _searches(h: Hypothesis, a: Line, b: Line) -> tuple[SearchRef, ...]:
    sid = search_id(h)
    return (SearchRef(sid, a.rank), SearchRef(sid, b.rank))


def _supported(
    h: Hypothesis, view: TreeView, grading: Grading, drawn: Line, other: Line, f: ChecksDrawFinding
) -> Verdict:
    """The drawn line's evidence, then the other line's search; the scope is the drawn line's."""

    evidence = (*checking_draw_evidence(view, drawn, f), SearchRef(search_id(h), other.rank))
    proof = scope(view, h, grading, (drawn.rank, other.rank), line=drawn)
    return supported(h, proof, (f,), evidence)
