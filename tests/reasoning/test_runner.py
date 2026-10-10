"""R2a: the hypothesis contract, verification and the rounds (R0-D §6.2–§6.4, §8–§10, §18.4–§18.6).

The templates here are test-only; catalogue v1 (R2-D) is packet R2b.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import ClassVar

import pytest
from synthetic import engine

from calliope.facts import NONE, EngineProfile, ExpansionSpec, FactEngine, RootSpec
from calliope.reasoning import (
    AnalysisRequest,
    GradingSpec,
    JudgementRef,
    JudgementStatus,
    ReasoningBudget,
)
from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.hypotheses import (
    Basis,
    ClaimRole,
    Direction,
    LineContext,
    NodeContext,
    Population,
    PopulationKind,
    PremiseRelation,
    PremiseUse,
    Quantifier,
    RelationDecl,
    RelationKind,
    ScopeRequirement,
    SearchCompat,
    VerificationTarget,
    hypothesis,
)
from calliope.reasoning.needs import FamilyNeed, LineNeed
from calliope.reasoning.observer import standard_line_ids
from calliope.reasoning.refs import LineSegment
from calliope.reasoning.runner import Reasoner
from calliope.reasoning.verification import (
    REALIZED,
    CausalCheck,
    ProofScope,
    Verdict,
    VerdictStatus,
    satisfies,
)

PROFILE = EngineProfile()
GAME = ("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5")
REQUIRE_LINE = ScopeRequirement(
    Basis.ENGINE, ((Quantifier.SPECIFIC_LINE, PopulationKind.ENGINE_REPORTED),)
)


def _lp(ctx):
    judgement = ctx.judgements[0]
    if judgement.status is not JudgementStatus.DECIDED:
        return None
    lp, _l1 = standard_line_ids(judgement)
    record = ctx.view.line(lp)
    return judgement, LineSegment(lp, 0, len(record.nodes) - 1)


def _line_target(segment: LineSegment) -> VerificationTarget:
    return VerificationTarget(
        Quantifier.SPECIFIC_LINE,
        segment,
        Population(PopulationKind.ENGINE_REPORTED, segment.line.search_id),
    )


def _scope(target: VerificationTarget, **kw) -> ProofScope:
    return ProofScope(Basis.ENGINE, target.at, target.quantifier, target.population, **kw)


class _Template:
    version: ClassVar[str] = "t1"
    role: ClassVar[ClaimRole] = ClaimRole.CONSEQUENCE
    directions: ClassVar[frozenset[Direction]] = frozenset({Direction.BACKWARD})
    relations: ClassVar[tuple[RelationDecl, ...]] = ()


class Probe(_Template):
    """Supported on the played line of S."""

    name: ClassVar[str] = "probe"

    def propose(self, ctx):
        found = _lp(ctx)
        if found is None:
            return ()
        judgement, segment = found
        return (
            hypothesis(
                self,
                predicate="probe",
                subject=ctx.subject,
                context=LineContext(segment),
                operands=(),
                target=_line_target(segment),
                origins=(JudgementRef(judgement.subject),),
            ),
        )

    def verify(self, h, view, grading):
        return Verdict(h.id, VerdictStatus.SUPPORTED, scope=_scope(h.target))


@dataclass
class Derived(_Template):
    """A mechanism on Probe; its REALIZED check passes or fails as configured."""

    realized: bool = True
    refute: bool = False
    name: ClassVar[str] = "derived"
    role: ClassVar[ClaimRole] = ClaimRole.MECHANISM
    relations: ClassVar[tuple[RelationDecl, ...]] = (RelationDecl(RelationKind.EXPLAINS, "probe"),)

    def propose(self, ctx):
        out = []
        for claim in ctx.claims:
            if claim.hypothesis.template == "probe" and claim.supported:
                use = PremiseUse(
                    claim.id, REQUIRE_LINE, PremiseRelation.SAME_CONTEXT, SearchCompat.SAME_SEARCH
                )
                out.append(
                    hypothesis(
                        self,
                        predicate="derived",
                        subject=ctx.subject,
                        context=claim.hypothesis.context,
                        operands=(),
                        target=claim.hypothesis.target,
                        premises=(use,),
                        origins=(claim.id,),
                    )
                )
        return tuple(out)

    def verify(self, h, view, grading):
        if self.refute:
            return Verdict(h.id, VerdictStatus.REFUTED, scope=_scope(h.target))
        check = CausalCheck(REALIZED, self.realized)
        return Verdict(h.id, VerdictStatus.SUPPORTED, scope=_scope(h.target), findings=(check,))


@dataclass
class NeedsFacts(_Template):
    """Needs `patterns` at the last node of the played line (outside the round-0 ensure)."""

    family: str = "patterns"
    name: ClassVar[str] = "needs_facts"

    def propose(self, ctx):
        found = _lp(ctx)
        if found is None:
            return ()
        _, segment = found
        return (
            hypothesis(
                self,
                predicate="needs",
                subject=ctx.subject,
                context=LineContext(segment),
                operands=(),
                target=_line_target(segment),
            ),
        )

    def verify(self, h, view, grading):
        last = view.line(h.target.at.line).nodes[-1]
        record = view.fact(self.family, last)
        if type(record).__name__ == "NotComputed":
            return Verdict(
                h.id, VerdictStatus.NEEDS_EVIDENCE, needs=(FamilyNeed(last, self.family),)
            )
        return Verdict(h.id, VerdictStatus.SUPPORTED, scope=_scope(h.target))


class LineNeeder(_Template):
    """Needs one more ply after the played line's end, a move absent at proposal (an ANALYSIS
    line with NONE); the move is an operand, fixed when proposed."""

    name: ClassVar[str] = "line_needer"

    def propose(self, ctx):
        found = _lp(ctx)
        if found is None:
            return ()
        _, segment = found
        last = ctx.view.line(segment.line).nodes[-1]
        legal = [m.uci for m in ctx.view.fact("status", last).legal_moves]
        move = legal[-1]  # never the synthetic PV's continuation (the first legal move)
        return (
            hypothesis(
                self,
                predicate="line",
                subject=ctx.subject,
                context=LineContext(segment),
                operands=(move,),
                target=_line_target(segment),
            ),
        )

    def verify(self, h, view, grading):
        last = view.line(h.target.at.line).nodes[-1]
        (move,) = h.operands
        if view.child(last, move) is None:
            need = LineNeed(last, (move,), NONE)
            return Verdict(h.id, VerdictStatus.NEEDS_EVIDENCE, needs=(need,))
        return Verdict(h.id, VerdictStatus.SUPPORTED, scope=_scope(h.target))


class SelfDeriving(_Template):
    """Each supported claim of its own derives another: a chain only the limits stop."""

    name: ClassVar[str] = "chain"

    def propose(self, ctx):
        found = _lp(ctx)
        if found is None:
            return ()
        _, segment = found
        target = _line_target(segment)
        mine = [c for c in ctx.claims if c.hypothesis.template == self.name and c.supported]
        if not mine:
            return (
                hypothesis(
                    self,
                    predicate="chain",
                    subject=ctx.subject,
                    context=LineContext(segment),
                    operands=(0,),
                    target=target,
                ),
            )
        return tuple(
            hypothesis(
                self,
                predicate="chain",
                subject=ctx.subject,
                context=LineContext(segment),
                operands=(c.hypothesis.operands[0] + 1,),
                target=target,
                premises=(
                    PremiseUse(
                        c.id, REQUIRE_LINE, PremiseRelation.SAME_CONTEXT, SearchCompat.SAME_SEARCH
                    ),
                ),
            )
            for c in mine
        )

    def verify(self, h, view, grading):
        return Verdict(h.id, VerdictStatus.SUPPORTED, scope=_scope(h.target))


class ScopeShort(_Template):
    """Claims every alternative as ranked by S, proves only the lines S reported."""

    name: ClassVar[str] = "scope_short"

    def propose(self, ctx):
        found = _lp(ctx)
        if found is None:
            return ()
        judgement, _ = found
        ranked = Population(PopulationKind.ENGINE_RANKED, judgement.search.search_id)
        target = VerificationTarget(Quantifier.ALL_ALTERNATIVES, ctx.subject.parent, ranked)
        return (
            hypothesis(
                self,
                predicate="short",
                subject=ctx.subject,
                context=NodeContext(ctx.subject.parent),
                operands=(),
                target=target,
            ),
        )

    def verify(self, h, view, grading):
        reported = replace(h.target.population, kind=PopulationKind.ENGINE_REPORTED)
        scope = ProofScope(Basis.ENGINE, h.target.at, Quantifier.ALL_ALTERNATIVES, reported)
        return Verdict(h.id, VerdictStatus.SUPPORTED, scope=scope)


def _analyse(templates, *, budget=None, moves=GAME, target=5, port=None):
    fact_engine = FactEngine(engine=port or engine(pv_plies=6))
    request = AnalysisRequest(
        RootSpec(),
        moves,
        target,
        PROFILE,
        budget or ReasoningBudget(),
        grading=GradingSpec("quality_v1"),
    )
    return Reasoner(fact_engine, tuple(templates)).analyse(request)


def _by_template(result, name):
    return [c for c in result.claims if c.hypothesis.template == name]


# -- the fixpoint, premises, relations (R0-D §6.3, §8, §10) -----------------------------------------


def test_a_premise_chain_resolves_in_one_round_with_explains() -> None:
    result = _analyse([Probe(), Derived()])
    (probe,) = _by_template(result, "probe")
    (derived,) = _by_template(result, "derived")
    assert probe.supported and derived.supported
    assert (probe.decided, derived.decided, derived.depth) == (0, 0, 1)
    kinds = {(r.source, r.kind) for r in result.relations if r.target == probe.id}
    assert (derived.id, RelationKind.EXPLAINS) in kinds
    assert (derived.id, RelationKind.DERIVED_FROM) in kinds
    assert result.rounds == ()  # nothing needed: no request after round 0


def test_a_failed_check_falls_back_to_associated_and_a_refutation_qualifies() -> None:
    result = _analyse([Probe(), Derived(realized=False)])
    (derived,) = _by_template(result, "derived")
    assert any(
        r.kind is RelationKind.ASSOCIATED_WITH and r.source == derived.id for r in result.relations
    )
    assert not any(r.kind is RelationKind.EXPLAINS for r in result.relations)
    result = _analyse([Probe(), Derived(refute=True)])
    (derived,) = _by_template(result, "derived")
    assert derived.verdict.status is VerdictStatus.REFUTED
    assert any(
        r.kind is RelationKind.QUALIFIES and r.source == derived.id for r in result.relations
    )


def test_effective_scope_includes_the_premise() -> None:
    result = _analyse([Probe(), Derived()])
    (probe,) = _by_template(result, "probe")
    (derived,) = _by_template(result, "derived")
    assert set(probe.effective_scope) <= set(derived.effective_scope)


def test_template_order_does_not_change_the_result() -> None:
    templates = [Probe(), Derived(), NeedsFacts(), LineNeeder()]
    first = _analyse(templates)
    shuffled = templates[:]
    random.Random(7).shuffle(shuffled)
    second = _analyse(shuffled)
    assert [(c.id, c.seq, c.verdict.status) for c in first.claims] == [
        (c.id, c.seq, c.verdict.status) for c in second.claims
    ]
    assert first.relations == second.relations
    assert first.rounds == second.rounds and first.limits_reached == second.limits_reached
    assert first.tree.view(first.rev).digest() == second.tree.view(second.rev).digest()


def test_refused_premises_are_template_bugs() -> None:
    @dataclass
    class OnRefuted(_Template):
        name: ClassVar[str] = "on_refuted"

        def propose(self, ctx):
            refuted = [c for c in ctx.claims if c.verdict.status is VerdictStatus.REFUTED]
            return tuple(
                hypothesis(
                    self,
                    predicate="x",
                    subject=ctx.subject,
                    context=c.hypothesis.context,
                    operands=(),
                    target=c.hypothesis.target,
                    premises=(
                        PremiseUse(
                            c.id,
                            REQUIRE_LINE,
                            PremiseRelation.SAME_CONTEXT,
                            SearchCompat.SAME_SEARCH,
                        ),
                    ),
                )
                for c in refuted
            )

        def verify(self, h, view, grading):  # pragma: no cover
            raise AssertionError

    with pytest.raises(ReasoningError, match="not a SUPPORTED claim"):
        _analyse([Probe(), Derived(refute=True), OnRefuted()])

    @dataclass
    class WrongRelation(Derived):
        name: ClassVar[str] = "wrong_relation"

        def propose(self, ctx):
            return tuple(
                replace(
                    h,
                    premises=tuple(
                        replace(p, relation=PremiseRelation.ALTERNATIVE_OF) for p in h.premises
                    ),
                )
                for h in Derived.propose(self, ctx)
            )

    with pytest.raises(ReasoningError, match="relation"):
        _analyse([Probe(), WrongRelation()])


def test_derivation_limits_are_recorded() -> None:
    budget = replace(ReasoningBudget(), max_derivation_depth=2)
    result = _analyse([SelfDeriving()], budget=budget)
    chain = _by_template(result, "chain")
    assert [c.depth for c in chain] == [0, 1, 2]
    assert any(limit.limit == "max_derivation_depth" for limit in result.limits_reached)
    budget = replace(ReasoningBudget(), max_hypotheses=2, max_derivation_depth=10)
    result = _analyse([SelfDeriving()], budget=budget)
    assert len(_by_template(result, "chain")) == 2
    assert any(limit.limit == "max_hypotheses" for limit in result.limits_reached)


def test_a_scope_that_does_not_reach_the_target_is_scope_short() -> None:
    result = _analyse([ScopeShort()])
    (claim,) = _by_template(result, "scope_short")
    assert (claim.verdict.status, claim.verdict.reason) == (
        VerdictStatus.INCONCLUSIVE,
        "SCOPE_SHORT",
    )


# -- needs, admission and requests (R0-D §6.2–§6.4) -------------------------------------------------


def test_a_family_need_is_ensured_and_reverified_next_round() -> None:
    budget = replace(ReasoningBudget(), pv_plies=1)  # the line's last node is past the ensure
    result = _analyse([NeedsFacts()], budget=budget)
    (claim,) = _by_template(result, "needs_facts")
    assert claim.supported and claim.decided == 1
    (round0,) = result.rounds
    assert type(round0.requests[0].request).__name__ == "EnsureRequest"
    assert round0.requests[0].outcome.startswith("rev:")


def test_a_line_need_is_extended_with_a_deterministic_label() -> None:
    result = _analyse([LineNeeder()])
    (claim,) = _by_template(result, "line_needer")
    assert claim.supported
    (request,) = result.rounds[0].requests
    (line,) = request.request.lines
    assert line.label.startswith("r") and len(line.label) == 17
    assert request.request.role.by == "reasoning"


def test_budget_round_limit_and_need_unmet() -> None:
    small = replace(ReasoningBudget(), pv_plies=1, max_ensure_nodes=0)
    (claim,) = _by_template(_analyse([NeedsFacts()], budget=small), "needs_facts")
    assert claim.verdict.reason == "BUDGET"
    once = replace(ReasoningBudget(), pv_plies=1, max_rounds=1)
    result = _analyse([NeedsFacts()], budget=once)
    (claim,) = _by_template(result, "needs_facts")
    assert claim.verdict.reason == "ROUND_LIMIT" and result.rounds == ()

    class Stubborn(NeedsFacts):
        name: ClassVar[str] = "stubborn"

        def verify(self, h, view, grading):
            last = view.line(h.target.at.line).nodes[-1]
            return Verdict(h.id, VerdictStatus.NEEDS_EVIDENCE, needs=(FamilyNeed(last, "pieces"),))

    (claim,) = _by_template(
        _analyse([Stubborn()], budget=replace(small, max_ensure_nodes=64)), "stubborn"
    )
    assert claim.verdict.reason == "NEED_UNMET"


def test_line_needs_are_admitted_by_searches_and_nodes() -> None:
    class Surveying(LineNeeder):
        name: ClassVar[str] = "surveying"

        def verify(self, h, view, grading):
            verdict = LineNeeder.verify(self, h, view, grading)
            if verdict.status is VerdictStatus.NEEDS_EVIDENCE:
                (need,) = verdict.needs
                probe = ExpansionSpec(True, False, False)
                return replace(verdict, needs=(replace(need, expansion=probe),))
            return verdict

    no_searches = replace(ReasoningBudget(), max_extra_searches=0)
    (claim,) = _by_template(_analyse([Surveying()], budget=no_searches), "surveying")
    assert claim.verdict.reason == "BUDGET"
    # the line's start (an engine-only node) and its new child are surveyed: two searches
    result = _analyse([Surveying()], budget=replace(ReasoningBudget(), max_extra_searches=2))
    (claim,) = _by_template(result, "surveying")
    assert claim.supported
    no_room = replace(ReasoningBudget(), max_tree_nodes=1)
    (claim,) = _by_template(_analyse([LineNeeder()], budget=no_room), "line_needer")
    assert claim.verdict.reason == "BUDGET"


def test_origins_and_directions_merge_without_changing_the_id() -> None:
    class Twice(Probe):
        name: ClassVar[str] = "twice"

        def propose(self, ctx):
            (h,) = Probe.propose(self, ctx)
            other = replace(h, origins=(), directions=(Direction.FORWARD,))
            return (h, other)

    (claim,) = _by_template(_analyse([Twice()]), "twice")
    assert claim.hypothesis.directions == (Direction.BACKWARD, Direction.FORWARD)
    assert len(claim.hypothesis.origins) == 1


# -- satisfaction (R0-D §9.4) -----------------------------------------------------------------------


def test_exists_witnesses_and_alternatives_exclude_the_played_move() -> None:
    result = _analyse([Probe()])
    view = result.tree.view(result.rev)
    parent = result.round_zero.subject.parent
    played = view.node(result.round_zero.subject.child).incoming_move
    search_id = result.round_zero.judgements[0].search.search_id
    reported = Population(PopulationKind.ENGINE_REPORTED, search_id)
    target = VerificationTarget(Quantifier.EXISTS_ALTERNATIVE, parent, reported)
    other = next(ln.move for ln in view.search(search_id).lines if ln.move != played)

    def scope(witness):
        return ProofScope(
            Basis.ENGINE, parent, Quantifier.EXISTS_ALTERNATIVE, reported, witnesses=(witness,)
        )

    assert satisfies(view, scope(other), target, played)
    assert not satisfies(view, scope(played), target, played)
    reported_moves = {ln.move for ln in view.search(search_id).lines}
    absent = next(
        m.uci for m in view.fact("status", parent).legal_moves if m.uci not in reported_moves
    )
    assert not satisfies(view, scope(absent), target, played)  # not reported by S
    legal = Population(PopulationKind.LEGAL)
    all_target = VerificationTarget(Quantifier.ALL_ALTERNATIVES, parent, reported)
    assert satisfies(
        view,
        ProofScope(Basis.ENGINE, parent, Quantifier.ALL_ALTERNATIVES, legal),
        all_target,
        played,
    )
    stronger = VerificationTarget(Quantifier.ALL_ALTERNATIVES, parent, legal)
    assert not satisfies(
        view,
        ProofScope(Basis.ENGINE, parent, Quantifier.ALL_ALTERNATIVES, reported),
        stronger,
        played,
    )


# -- refusals, ids, relations, provenance, acyclicity ---------------------------------------------


class _Surveying(LineNeeder):
    name: ClassVar[str] = "surveying"

    def verify(self, h, view, grading):
        verdict = LineNeeder.verify(self, h, view, grading)
        if verdict.status is VerdictStatus.NEEDS_EVIDENCE:
            (need,) = verdict.needs
            return replace(
                verdict, needs=(replace(need, expansion=ExpansionSpec(True, False, False)),)
            )
        return verdict


def test_a_refused_request_is_recorded_and_closes_its_verdict() -> None:
    from synthetic import IDENTITY, synthetic

    from calliope.facts.errors import EngineError
    from calliope.facts.search import ScriptedEngine

    answer, calls = synthetic(6), {"n": 0, "limit": None}

    def counting(request):
        calls["n"] += 1
        if calls["limit"] is not None and calls["n"] > calls["limit"]:
            raise EngineError("the engine stopped")
        return answer(request)

    budget = replace(ReasoningBudget(), max_extra_searches=0)
    _analyse([_Surveying()], budget=budget, port=ScriptedEngine(IDENTITY, counting))
    calls["limit"], calls["n"] = calls["n"], 0  # round 0's searches succeed, later ones fail
    budget = replace(ReasoningBudget(), max_extra_searches=4)
    result = _analyse([_Surveying()], budget=budget, port=ScriptedEngine(IDENTITY, counting))
    (claim,) = _by_template(result, "surveying")
    assert claim.verdict.reason == "NOT_COMPUTED(EngineError)"
    assert result.rounds[0].requests[0].outcome == "REFUSED(EngineError)"


def test_hypothesis_ids_are_stable_across_processes() -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent
    probe = (
        "import sys; sys.path[:0] = [{!r}, {!r}]\n"
        "from test_runner import _analyse, Probe, Derived\n"
        "print(sorted(c.id for c in _analyse([Probe(), Derived()]).claims))\n"
    ).format(str(here), str(here.parent / "facts" / "search"))
    outputs = {
        subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2")
    }
    assert len(outputs) == 1


def test_premise_relations_and_search_provenance() -> None:
    from calliope.facts import EngineLineId
    from calliope.reasoning.verification import relation_holds, search_compatible

    result = _analyse([Probe(), Derived()])
    view = result.tree.view(result.rev)
    probe = _by_template(result, "probe")[0]
    h = probe.hypothesis
    segment = h.target.at
    longer = replace(h, target=replace(h.target, at=LineSegment(segment.line, 0, segment.last)))
    shorter = replace(h, target=replace(h.target, at=LineSegment(segment.line, 0, 2)))
    assert relation_holds(view, PremiseRelation.SAME_LINE, shorter, longer)
    assert relation_holds(view, PremiseRelation.LINE_EXTENSION, shorter, longer)
    assert not relation_holds(view, PremiseRelation.LINE_EXTENSION, longer, shorter)

    def at_node(node):
        return replace(h, target=replace(h.target, quantifier=Quantifier.EXISTS_RESPONSE, at=node))

    at_p = at_node(result.round_zero.subject.parent)
    assert relation_holds(view, PremiseRelation.SAME_CONTEXT, at_p, h)  # anchored at P
    best = EngineLineId(segment.line.anchor, segment.line.search_id, 1)
    sibling = replace(h, target=replace(h.target, at=LineSegment(best, 0, 2)))
    assert relation_holds(view, PremiseRelation.ALTERNATIVE_OF, sibling, h) == (
        best != segment.line
    )
    earlier = at_node(result.round_zero.previous.parent)
    assert relation_holds(view, PremiseRelation.EARLIER_POSITION, earlier, h)
    use = PremiseUse(probe.id, REQUIRE_LINE, PremiseRelation.SAME_CONTEXT, SearchCompat.SAME_SEARCH)
    elsewhere = replace(
        h.target,
        quantifier=Quantifier.ALL_ALTERNATIVES,
        population=Population(PopulationKind.ENGINE_REPORTED, "s_other"),
        at=result.round_zero.subject.parent,
    )
    assert search_compatible(probe, use, h.target)
    assert not search_compatible(probe, use, elsewhere)
    assert search_compatible(probe, replace(use, search=SearchCompat.ANY_SEARCH), elsewhere)


def test_derived_from_cycles_are_refused() -> None:
    from calliope.reasoning.graph import relations

    result = _analyse([Probe(), Derived()])
    probe, derived = (_by_template(result, n)[0] for n in ("probe", "derived"))
    looped = replace(probe, hypothesis=replace(probe.hypothesis, origins=(derived.id,)))
    with pytest.raises(ReasoningError, match="cycle"):
        relations((looped, derived), {"probe": Probe(), "derived": Derived()})
