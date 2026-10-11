"""Functions of the move (R2-D §3.9, §3.10, §3.13): forcing, only move, prevents."""

from __future__ import annotations

from calliope.facts import SearchKind, StatusFacts, TreeView
from calliope.reasoning.catalogue.base import (
    F,
    Template,
    edge,
    exact_scope,
    inconclusive,
    judged,
    judgement,
    judgement_ref,
    lines,
    materials,
    mover,
    observed,
    opponent,
    played,
    refuted,
    scope,
    search_id,
    supported,
)
from calliope.reasoning.findings import (
    AlternativeFinding,
    ForcingFinding,
    OutcomeKind,
    PreventsFinding,
    PreventsKind,
)
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
from calliope.reasoning.lines import decided, fact_ref, mate_for, undecided_reason
from calliope.reasoning.observer import Grade, standard_line_ids
from calliope.reasoning.refs import MoveRef, SearchRef
from calliope.reasoning.verification import Verdict

ONLY_MOVE_MARGIN = 400  # 0.20 expected points in 1/2000 (R0-D D10)


class Forcing(Template):
    """R2-D §3.9: the move checks, or leaves one reply; exact."""

    name = "forcing_v1"
    role = ClaimRole.FUNCTION
    directions = frozenset({F})
    predicate = "forcing"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        child = ctx.subject.child
        move = ctx.view.fact("move", child)
        status = ctx.view.fact("status", child)
        if move.gives_mate or not (move.gives_check or status.legal_move_count == 1):
            return ()
        at = edge(ctx.view, ctx.subject.parent, child)
        found = observed(ctx, "played_edge")
        return (
            self.make(
                ctx,
                context=LineContext(at),
                operands=(MoveRef(child),),
                target=VerificationTarget(Quantifier.SPECIFIC_LINE, at, played(child), horizon=1),
                origins=(found[0],) if found is not None else (),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        child = h.subject.child
        move = view.fact("move", child)
        status: StatusFacts = view.fact("status", child)
        evidence = (
            fact_ref(view, "move", child, ("gives_check",)),
            fact_ref(view, "status", child, ("legal_move_count",)),
        )
        if move.gives_mate or not (move.gives_check or status.legal_move_count == 1):
            return refuted(h, evidence=evidence)
        finding = ForcingFinding(move.gives_check, status.legal_move_count)
        return supported(h, exact_scope(h), (finding,), evidence)


class OnlyMove(Template):
    """R2-D §3.10: rank 2 of the unrestricted search loses at least 0.20 (R0-D D10)."""

    name = "only_move_v1"
    role = ClaimRole.FUNCTION
    directions = frozenset({F})
    predicate = "only_move"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        if judgement_ is None or judgement_.grade is not Grade.BEST:
            return ()
        parent = ctx.subject.parent
        if ctx.view.fact("status", parent).legal_move_count < 2:
            return ()
        assert judgement_.search is not None
        population = Population(PopulationKind.ENGINE_RANKED, judgement_.search.search_id)
        return (
            self.make(
                ctx,
                context=NodeContext(parent),
                operands=(),
                target=VerificationTarget(Quantifier.ALL_ALTERNATIVES, parent, population),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        sid = search_id(h)
        if view.search(sid).kind is not SearchKind.SURVEY:
            return inconclusive(h, "SCOPE_SHORT")  # ENGINE_RANKED needs an unrestricted search
        scores = {s.rank: s for s in judgement(view, h, grading).alternatives}
        if 2 not in scores:
            return inconclusive(h, "NOT_COMPUTED(NO_RANK_2)")
        margin = scores[1].expected - scores[2].expected
        evidence = (SearchRef(sid, 1), SearchRef(sid, 2))
        finding = AlternativeFinding(SearchRef(sid, 2), margin)
        if margin >= ONLY_MOVE_MARGIN:
            return supported(h, scope(view, h, grading, (1, 2)), (finding,), evidence)
        return refuted(h, (finding,), evidence)  # rank 2 is the counterexample


def _bad(outcome, o) -> bool:
    """R2-D §3.13: mated, or a material loss from P."""

    if outcome.kind is OutcomeKind.STABLE:
        assert outcome.delta is not None
        return outcome.delta <= -1
    return mate_for(outcome, o)


class Prevents(Template):
    """R2-D §3.13: every other reported line is mated or loses material, the played line not."""

    name = "prevents_v1"
    role = ClaimRole.FUNCTION
    directions = frozenset({F})
    predicate = "prevents"

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        judgement_ = judged(ctx)
        found = materials(ctx)
        if judgement_ is None or found is None or judgement_.grade is not Grade.BEST:
            return ()
        _ref, by_rank = found
        p = standard_line_ids(judgement_)[0].rank
        others = tuple(by_rank[r].window for r in sorted(by_rank) if r != p)
        if not others:
            return ()
        parent = ctx.subject.parent
        assert judgement_.search is not None
        population = Population(PopulationKind.ENGINE_REPORTED, judgement_.search.search_id)
        return (
            self.make(
                ctx,
                context=NodeContext(parent),
                operands=(by_rank[p].window, *others),
                target=VerificationTarget(Quantifier.ALL_ALTERNATIVES, parent, population),
                origins=(judgement_ref(ctx),),
            ),
        )

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        lp, *others = lines(view, h, h.operands)
        o = opponent(mover(view, h))
        sid = search_id(h)
        evidence = tuple(SearchRef(sid, line.rank) for line in (lp, *others))
        for line in others:  # rule 1: one counterexample
            if decided(line.outcome) and not _bad(line.outcome, o):
                return refuted(h, evidence=evidence)
        if decided(lp.outcome) and _bad(lp.outcome, o):
            return refuted(h, evidence=evidence)  # rule 2
        pending = [line.outcome for line in (*others, lp) if not decided(line.outcome)]
        if pending:
            return inconclusive(h, undecided_reason(pending[0]))  # rule 4
        mates = sum(1 for line in others if line.outcome.kind is OutcomeKind.MATE)
        losses = [-line.outcome.delta for line in others if line.outcome.kind is OutcomeKind.STABLE]
        if not losses:
            kind = PreventsKind.MATE
        elif not mates:
            kind = PreventsKind.MATERIAL
        else:
            kind = PreventsKind.MIXED
        finding = PreventsFinding(kind, len(others), min(losses) if losses else None)
        proof = scope(view, h, grading, tuple(line.rank for line in (lp, *others)))
        return supported(h, proof, (finding,), evidence)
