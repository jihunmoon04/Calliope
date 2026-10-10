"""R2a contract obligations (R0-D §18.4–§18.6c) beyond `test_runner.py` (R2a review C9)."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import ClassVar

import pytest
from synthetic import IDENTITY, engine, synthetic
from test_runner import (
    GAME,
    PROFILE,
    REQUIRE_LINE,
    Derived,
    LineNeeder,
    Probe,
    SelfDeriving,
    _analyse,
    _by_template,
    _line_target,
    _scope,
    _Template,
)

from calliope.facts import NONE, EngineLineId, ExpansionSpec, FactEngine, RootSpec
from calliope.facts.search import EngineResultStore, ScriptedEngine
from calliope.reasoning import AnalysisRequest, JudgementRef, ReasoningBudget
from calliope.reasoning.encoding import canonical_bytes
from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.hypotheses import (
    Basis,
    LineContext,
    NodeContext,
    Population,
    PopulationKind,
    PremiseRelation,
    PremiseUse,
    Quantifier,
    ScopeRequirement,
    SearchCompat,
    SpanContext,
    VerificationTarget,
    hypothesis,
)
from calliope.reasoning.needs import FamilyNeed, LineNeed
from calliope.reasoning.refs import LineSegment, MoveRef
from calliope.reasoning.runner import Reasoner
from calliope.reasoning.verification import ProofScope, Verdict, VerdictStatus, satisfies

# -- premises refused through the runner -------------------------------------------------------------


@dataclass
class OnBestLine(Derived):
    """Builds on Probe (the played line) but states its claim about L1, with a chosen relation."""

    relation: PremiseRelation = PremiseRelation.SAME_CONTEXT
    requires: ScopeRequirement = REQUIRE_LINE
    search: SearchCompat = SearchCompat.SAME_SEARCH
    target_search: str | None = None
    name: ClassVar[str] = "on_best_line"

    def propose(self, ctx):
        out = []
        for claim in ctx.claims:
            if claim.hypothesis.template == "probe" and claim.supported:
                lp = claim.hypothesis.target.at
                best = EngineLineId(lp.line.anchor, self.target_search or lp.line.search_id, 1)
                segment = LineSegment(best, 0, 2)
                target = _line_target(segment)
                use = PremiseUse(claim.id, self.requires, self.relation, self.search)
                out.append(hypothesis(self, predicate="best", subject=ctx.subject,
                                      context=LineContext(segment), operands=(),
                                      target=target, premises=(use,)))  # fmt: skip
        return tuple(out)


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        (OnBestLine(relation=PremiseRelation.SAME_CONTEXT), "relation"),
        (OnBestLine(relation=PremiseRelation.SAME_LINE), "relation"),  # a gain on Lp for L1
        (OnBestLine(relation=PremiseRelation.LINE_EXTENSION), "relation"),
        (OnBestLine(relation=PremiseRelation.EARLIER_POSITION), "relation"),
        (
            OnBestLine(
                relation=PremiseRelation.ALTERNATIVE_OF,
                requires=ScopeRequirement(
                    Basis.EXACT, ((Quantifier.SPECIFIC_LINE, PopulationKind.ENGINE_REPORTED),)
                ),
            ),
            "not accepted",
        ),
    ],
)
def test_premises_are_refused_by_the_runner(variant, message) -> None:
    with pytest.raises(ReasoningError, match=message):
        _analyse([Probe(), variant])


def test_an_alternative_premise_is_accepted_and_same_search_is_enforced() -> None:
    result = _analyse([Probe(), OnBestLine(relation=PremiseRelation.ALTERNATIVE_OF)])
    assert _by_template(result, "on_best_line")[0].depth == 1  # Lp (rank 6) and L1 are siblings
    other = OnBestLine(relation=PremiseRelation.ALTERNATIVE_OF, target_search="s_other")
    with pytest.raises(ReasoningError):
        _analyse([Probe(), other])


def test_an_inconclusive_premise_is_refused() -> None:
    class Unsure(Probe):
        name: ClassVar[str] = "probe"

        def verify(self, h, view):
            return Verdict(h.id, VerdictStatus.INCONCLUSIVE, reason="UNSTABLE")

    class Eager(Derived):
        def propose(self, ctx):
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
                for c in ctx.claims
                if c.hypothesis.template == "probe"
            )

    with pytest.raises(ReasoningError, match="not a SUPPORTED claim"):
        _analyse([Unsure(), Eager()])


def test_a_wrong_id_and_a_shared_id_are_refused() -> None:
    class Forged(Probe):
        name: ClassVar[str] = "forged"

        def propose(self, ctx):
            return tuple(replace(h, id="0" * 64) for h in Probe.propose(self, ctx))

    with pytest.raises(ReasoningError, match="wrong id"):
        _analyse([Forged()])


def test_a_later_claim_origin_is_dropped() -> None:
    class Echo(Probe):
        """Re-proposes its hypothesis with every claim so far as an origin."""

        name: ClassVar[str] = "echo"

        def propose(self, ctx):
            (h,) = Probe.propose(self, ctx)
            return (replace(h, origins=(*h.origins, *(c.id for c in ctx.claims))),)

    result = _analyse([Echo(), Probe(), Derived()])
    (echo,) = _by_template(result, "echo")
    later = {c.id for c in result.claims if c.seq > echo.seq}
    assert later and not later & set(echo.hypothesis.origins)


def test_limits_are_counted_once_per_refused_proposal() -> None:
    budget = replace(ReasoningBudget(), max_derivation_depth=1)
    result = _analyse([SelfDeriving()], budget=budget)
    assert [(lim.limit, lim.refused) for lim in result.limits_reached] == [
        ("max_derivation_depth", 1)
    ]
    passes = replace(ReasoningBudget(), max_fixpoint_passes=2, max_derivation_depth=10)
    result = _analyse([SelfDeriving()], budget=passes)
    assert ("max_fixpoint_passes", 1) in [(lim.limit, lim.refused) for lim in result.limits_reached]


# -- satisfaction ------------------------------------------------------------------------------------


def test_satisfaction_per_quantifier() -> None:
    result = _analyse([Probe()])
    view = result.tree.view(result.rev)
    zero = result.round_zero
    parent, child = zero.subject.parent, zero.subject.child
    played = view.node(child).incoming_move
    legal = [m.uci for m in view.fact("status", child).legal_moves]
    legal_c = Population(PopulationKind.LEGAL)

    exists = VerificationTarget(Quantifier.EXISTS_RESPONSE, child, legal_c, horizon=1)

    def at_c(**kw):
        return ProofScope(Basis.EXACT, child, Quantifier.EXISTS_RESPONSE, legal_c, **kw)

    assert satisfies(view, at_c(witnesses=(legal[0],)), exists, played)
    assert not satisfies(view, at_c(witnesses=("a1a8",)), exists, played)  # not legal at C
    assert not satisfies(view, at_c(), exists, played)  # no witness: SCOPE_SHORT

    siblings = [view.node(n).incoming_move for n in view.children(parent)]
    refs = tuple(MoveRef(n) for n in view.children(parent))
    selected = VerificationTarget(
        Quantifier.SELECTED_ALTERNATIVES, parent, Population(PopulationKind.EXPLICIT, moves=refs)
    )
    narrower = Population(PopulationKind.EXPLICIT, moves=refs[:1])
    scope = ProofScope(Basis.ENGINE, parent, Quantifier.SELECTED_ALTERNATIVES, narrower)
    expected = set(siblings[:1]) - {played} >= set(siblings) - {played}
    assert satisfies(view, scope, selected, played) == expected

    lp = zero.observations[0].operands[0]
    persist = VerificationTarget(
        Quantifier.PERSISTENCE, lp, Population(PopulationKind.ENGINE_REPORTED, lp.line.search_id), 4
    )
    span = ProofScope(Basis.ENGINE, lp, Quantifier.PERSISTENCE, persist.population)
    assert not satisfies(view, replace(span, plies=3), persist, played)
    assert satisfies(view, replace(span, plies=4), persist, played)


# -- needs and requests ------------------------------------------------------------------------------


def test_line_needs_are_grouped_by_expansion_in_canonical_order() -> None:
    class TwoLines(LineNeeder):
        name: ClassVar[str] = "two_lines"

        def verify(self, h, view):
            verdict = LineNeeder.verify(self, h, view)
            if verdict.status is not VerdictStatus.NEEDS_EVIDENCE:
                return verdict
            (need,) = verdict.needs
            last = need.start
            legal = [m.uci for m in view.fact("status", last).legal_moves]
            extra = (
                LineNeed(last, (legal[-2],), NONE),
                LineNeed(last, (legal[-3],), ExpansionSpec(True, False, False)),
            )
            if all(view.child(last, n.moves[0]) is not None for n in (need, *extra)):
                return Verdict(h.id, VerdictStatus.SUPPORTED, scope=_scope(h.target))
            return replace(verdict, needs=(need, *extra))

    result = _analyse([TwoLines()], budget=replace(ReasoningBudget(), max_extra_searches=4))
    (round0,) = result.rounds
    extends = [r.request for r in round0.requests]
    assert [e.expansion for e in extends] == [NONE, ExpansionSpec(True, False, False)]
    assert len(extends[0].lines) == 2 and len(extends[1].lines) == 1
    assert _by_template(result, "two_lines")[0].supported


def test_no_op_and_need_unmet() -> None:
    class Present(Probe):
        name: ClassVar[str] = "present"

        def verify(self, h, view):
            child = h.subject.child  # an input node: `pieces` is already there
            return Verdict(h.id, VerdictStatus.NEEDS_EVIDENCE, needs=(FamilyNeed(child, "pieces"),))

    result = _analyse([Present()])
    assert result.rounds[0].requests[0].outcome == "NO_OP"
    assert _by_template(result, "present")[0].verdict.reason == "NEED_UNMET"


def test_a_line_through_p_retrying_a_skipped_comparison_is_counted() -> None:
    """R0-I1: the retry costs a search; with none left the need is not admitted (BUDGET)."""

    slow = {"on": True}
    answer = synthetic(6)

    def delayed(request):
        if slow["on"]:
            time.sleep(0.02)
        return answer(request)

    class ThroughP(_Template):
        name: ClassVar[str] = "through_p"

        def propose(self, ctx):
            target = VerificationTarget(
                Quantifier.EXISTS_RESPONSE, ctx.subject.parent, Population(PopulationKind.LEGAL)
            )
            slow["on"] = False  # round 0 is over: later searches are fast
            return (hypothesis(self, predicate="p", subject=ctx.subject,
                               context=NodeContext(ctx.subject.parent), operands=(),
                               target=target),)  # fmt: skip

        def verify(self, h, view):
            parent = h.subject.parent
            move = view.fact("status", parent).legal_moves[-1].uci
            if view.child(parent, move) is None:
                need = LineNeed(parent, (move,), NONE)
                return Verdict(h.id, VerdictStatus.NEEDS_EVIDENCE, needs=(need,))
            scope = ProofScope(Basis.EXACT, parent, Quantifier.EXISTS_RESPONSE,
                               h.target.population, witnesses=(move,))  # fmt: skip
            return Verdict(h.id, VerdictStatus.SUPPORTED, scope=scope)

    budget = replace(ReasoningBudget(), deadline_ms=5, max_extra_searches=0)
    request = AnalysisRequest(RootSpec(), ("g4",), 1, PROFILE, budget)
    port = ScriptedEngine(IDENTITY, delayed)
    result = Reasoner(FactEngine(engine=port), (ThroughP(),)).analyse(request)
    assert result.round_zero.judgements[0].reason == "DEADLINE"  # the comparison was skipped
    assert _by_template(result, "through_p")[0].verdict.reason == "BUDGET"


# -- determinism and encoding ------------------------------------------------------------------------


def test_cold_and_warm_store_give_identical_claims_and_relations() -> None:
    store = EngineResultStore()

    def run():
        request = AnalysisRequest(RootSpec(), GAME, 5, PROFILE)
        fact_engine = FactEngine(engine=engine(pv_plies=6), store=store)
        return Reasoner(fact_engine, (Probe(), Derived(), LineNeeder())).analyse(request)

    cold, warm = run(), run()
    assert [(c.id, c.verdict) for c in cold.claims] == [(c.id, c.verdict) for c in warm.claims]
    assert cold.relations == warm.relations
    assert cold.rounds == warm.rounds and cold.limits_reached == warm.limits_reached


def test_the_r0d_8_6_examples_encode() -> None:
    """Prophylaxis and plan hypotheses (R0-D §8.6) fit the contract and encode canonically."""

    result = _analyse([Probe()])
    zero = result.round_zero
    lp = zero.observations[0].operands[0]
    legal = Population(PopulationKind.LEGAL)
    template = Probe()
    h1 = hypothesis(template, predicate="pattern_available", subject=zero.subject,
                    context=NodeContext(zero.subject.parent), operands=("relative_pin", "f3"),
                    target=VerificationTarget(Quantifier.EXISTS_RESPONSE, zero.subject.parent,
                                              legal, 1),
                    origins=(JudgementRef(zero.subject),))  # fmt: skip
    h2 = hypothesis(template, predicate="pattern_prevented", subject=zero.subject,
                    context=NodeContext(zero.subject.child), operands=("relative_pin", "f3"),
                    target=VerificationTarget(Quantifier.ALL_RESPONSES, zero.subject.child, legal, 1),
                    premises=(PremiseUse(h1.id, ScopeRequirement(Basis.EXACT,
                              ((Quantifier.EXISTS_RESPONSE, PopulationKind.LEGAL),)),
                              PremiseRelation.ALTERNATIVE_OF, SearchCompat.ANY_SEARCH),))  # fmt: skip
    h3 = hypothesis(template, predicate="piece_reaches", subject=zero.subject,
                    context=SpanContext(lp, 1, 6), operands=("g3",),
                    target=VerificationTarget(Quantifier.SPECIFIC_LINE, lp,
                                              Population(PopulationKind.ENGINE_REPORTED,
                                                         lp.line.search_id), 6))  # fmt: skip
    for h in (h1, h2, h3):
        assert canonical_bytes(h) == canonical_bytes(replace(h))
    assert len({h1.id, h2.id, h3.id}) == 3
