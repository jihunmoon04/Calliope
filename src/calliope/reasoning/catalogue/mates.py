"""Mate templates (R2-D §3.3–§3.6): delivered, found, allowed in one, allowed, missed."""

from __future__ import annotations

from calliope.facts import LineEnd, StatusFacts, TreeView
from calliope.reasoning.catalogue.base import (
    B,
    F,
    Template,
    edge,
    exact_scope,
    judged,
    judgement_ref,
    line_target,
    lines,
    materials,
    mover,
    observed,
    opponent,
    played,
    refuted,
    scope,
    search_id,
    seg,
    supported,
)
from calliope.reasoning.findings import ComparisonFinding, MateFinding
from calliope.reasoning.grading import Grading
from calliope.reasoning.hypotheses import (
    ClaimRole,
    Hypothesis,
    LineContext,
    NodeContext,
    Population,
    PopulationKind,
    ProposeContext,
    Quantifier,
    VerificationTarget,
)
from calliope.reasoning.lines import Line, fact_ref, mate_for
from calliope.reasoning.observer import standard_line_ids
from calliope.reasoning.refs import MoveRef, SearchMoveRef, SearchRef
from calliope.reasoning.verification import Verdict


def mating_edge(line: Line) -> MoveRef | None:
    """The mating edge when the line ends in CHECKMATE within its attached plies."""

    if line.record is not None and line.record.end is LineEnd.CHECKMATE:
        return MoveRef(line.record.nodes[-1])
    return None


def _edge_origin(ctx: ProposeContext) -> tuple:
    found = observed(ctx, "played_edge")
    return (found[0],) if found is not None else ()


class MateDelivered(Template):
    name = "mate_delivered_v1"
    role = ClaimRole.CONSEQUENCE
    directions = frozenset({F})
    predicate = "mate_delivered"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        child = ctx.subject.child
        if not ctx.view.fact("move", child).gives_mate:
            return ()
        at = edge(ctx.view, ctx.subject.parent, child)
        target = VerificationTarget(Quantifier.SPECIFIC_LINE, at, played(child), horizon=1)
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(MoveRef(child),),
                target=target,
                origins=_edge_origin(ctx),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        child = h.subject.child
        evidence = (fact_ref(view, "move", child, ("gives_mate",)),)
        if not view.fact("move", child).gives_mate:
            return refuted(h, evidence=evidence)
        return supported(h, exact_scope(h), (MateFinding(1, MoveRef(child)),), evidence)


class MateInOneAllowed(Template):
    """R2-D §3.3a: exact, needs no judgement."""

    name = "mate_in_one_allowed_v1"
    role = ClaimRole.CONSEQUENCE
    directions = frozenset({F, B})
    predicate = "mate_in_one_allowed"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        child = ctx.subject.child
        status = ctx.view.fact("status", child)
        if not isinstance(status, StatusFacts) or not status.mating_moves:
            return ()
        target = VerificationTarget(
            Quantifier.EXISTS_RESPONSE, child, Population(PopulationKind.LEGAL), horizon=1
        )
        return (
            self.make(
                ctx,
                context=NodeContext(child),
                operands=(MoveRef(child),),
                target=target,
                origins=_edge_origin(ctx),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        child = h.subject.child
        status = view.fact("status", child)
        evidence = (fact_ref(view, "status", child, ("mating_moves",)),)
        if not status.mating_moves:
            return refuted(h, evidence=evidence)
        witness = status.mating_moves[0]
        proof = exact_scope(h, witnesses=(witness,))
        return supported(h, proof, (MateFinding(1, None),), evidence)


class _LineMate(Template):
    """A mate read from the outcome of `Lp` and `L1` (their windows are the operands)."""

    role = ClaimRole.CONSEQUENCE

    def _windows(self, ctx: ProposeContext):
        judgement = judged(ctx)
        found = materials(ctx)
        if judgement is None or found is None:
            return None
        ref, by_rank = found
        lp, l1 = standard_line_ids(judgement)
        return judgement, ref, by_rank[lp.rank], by_rank[l1.rank]

    def _wants(self, ctx: ProposeContext, played_line, best_line) -> bool:
        raise NotImplementedError

    def _target_line(self, played_line, best_line):
        return played_line

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        found = self._windows(ctx)
        if found is None:
            return ()
        _judgement, _ref, lp, l1 = found
        if not self._wants(ctx, lp, l1):
            return ()
        at = seg(ctx.view, self._target_line(lp, l1).window.line)
        if at is None:
            return ()
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(lp.window, l1.window),
                target=line_target(at),
                origins=(judgement_ref(ctx),),
            ),
        )


class MateFound(_LineMate):
    name = "mate_found_v1"
    directions = frozenset({F})
    predicate = "mate_found"

    def _wants(self, ctx, lp, l1) -> bool:
        m = ctx.view.node(ctx.subject.parent).side_to_move
        return mate_for(lp.outcome, m) and not ctx.view.fact("move", ctx.subject.child).gives_mate

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        lp, _l1 = lines(view, h, h.operands)
        sid = search_id(h)
        evidence = (SearchRef(sid, lp.rank),)
        if not mate_for(lp.outcome, mover(view, h)):
            return refuted(h, evidence=evidence)
        finding = MateFinding(lp.outcome.moves, mating_edge(lp))
        return supported(h, scope(view, h, grading, (lp.rank,), line=lp), (finding,), evidence)


class MateAllowed(_LineMate):
    name = "mate_allowed_v1"
    directions = frozenset({B})
    predicate = "mate_allowed"

    def _wants(self, ctx, lp, l1) -> bool:
        o = opponent(ctx.view.node(ctx.subject.parent).side_to_move)
        return mate_for(lp.outcome, o) and not mate_for(l1.outcome, o)

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        lp, l1 = lines(view, h, h.operands)
        o = opponent(mover(view, h))
        sid = search_id(h)
        evidence = (SearchRef(sid, lp.rank), SearchRef(sid, l1.rank))
        if not mate_for(lp.outcome, o) or mate_for(l1.outcome, o):
            return refuted(h, evidence=evidence)
        finding = MateFinding(lp.outcome.moves, mating_edge(lp))
        return supported(
            h, scope(view, h, grading, (lp.rank, l1.rank), line=lp), (finding,), evidence
        )


class MateMissed(_LineMate):
    name = "mate_missed_v1"
    role = ClaimRole.COMPARISON
    directions = frozenset({B})
    predicate = "mate_missed"

    def _target_line(self, lp, l1):
        return l1

    def _wants(self, ctx, lp, l1) -> bool:
        m = ctx.view.node(ctx.subject.parent).side_to_move
        return mate_for(l1.outcome, m) and not mate_for(lp.outcome, m)

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        lp, l1 = lines(view, h, h.operands)
        m = mover(view, h)
        sid = search_id(h)
        evidence = (
            SearchRef(sid, l1.rank),
            SearchRef(sid, lp.rank),
            fact_ref(view, "status", h.subject.parent, ("legal_moves",)),
        )
        if not mate_for(l1.outcome, m) or mate_for(lp.outcome, m):
            return refuted(h, evidence=evidence)
        finding = ComparisonFinding(SearchMoveRef(sid, l1.rank, 1), l1.outcome, lp.outcome)
        return supported(
            h, scope(view, h, grading, (l1.rank, lp.rank), line=l1), (finding,), evidence
        )
