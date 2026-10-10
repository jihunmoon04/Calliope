"""Verdicts, proof scopes and the runner's checks on them (R0-D §9, §8.1.1, §8.1.2).

Templates verify; this module decides what a verdict may claim: a SUPPORTED verdict whose scope
does not satisfy its target becomes `INCONCLUSIVE(SCOPE_SHORT)`, and a premise whose effective
scope, relation or search provenance is not acceptable is refused as a template bug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from calliope.facts import EngineLineId, LineEnd, NodeId, TreeView
from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.hypotheses import (
    ALL,
    ALTERNATIVES,
    EXISTS,
    Basis,
    Hypothesis,
    LineContext,
    NodeContext,
    Population,
    PopulationKind,
    PremiseRelation,
    PremiseUse,
    Quantifier,
    SearchCompat,
    SpanContext,
    VerificationTarget,
)
from calliope.reasoning.needs import EvidenceNeed
from calliope.reasoning.refs import Evidence, LineSegment, SearchRef


class VerdictStatus(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    NEEDS_EVIDENCE = "needs_evidence"


FINAL = (VerdictStatus.SUPPORTED, VerdictStatus.REFUTED, VerdictStatus.INCONCLUSIVE)


@dataclass(frozen=True, slots=True)
class ProofScope:
    """What a verdict established (R0-D §9.3)."""

    basis: Basis
    at: NodeId | LineSegment
    quantifier: Quantifier
    population: Population
    witnesses: tuple[str, ...] = ()  # for EXISTS_*: the witness move(s), canonical UCI
    searches: tuple[SearchRef, ...] = ()
    depth: int | None = None
    multipv: int | None = None
    plies: int | None = None
    line_end: LineEnd | None = None
    policies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CausalCheck:
    """A finding: kind `REALIZED` (→ EXPLAINS) or `COUNTERFACTUAL` (→ CAUSES) (R0-D §10.2)."""

    kind: str
    passed: bool
    evidence: tuple[Evidence, ...] = ()


REALIZED = "REALIZED"
COUNTERFACTUAL = "COUNTERFACTUAL"


@dataclass(frozen=True, slots=True)
class Verdict:
    hypothesis: str
    status: VerdictStatus
    evidence: tuple[Evidence, ...] = ()
    scope: ProofScope | None = None
    needs: tuple[EvidenceNeed, ...] = ()
    findings: tuple = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.status is VerdictStatus.NEEDS_EVIDENCE) != bool(self.needs):
            raise ReasoningError("needs come with NEEDS_EVIDENCE and only with it")
        if self.status is VerdictStatus.SUPPORTED and self.scope is None:
            raise ReasoningError("a SUPPORTED verdict states its scope")
        if self.status is VerdictStatus.INCONCLUSIVE and not self.reason:
            raise ReasoningError("an INCONCLUSIVE verdict states its reason (R0-D §9.2)")


@dataclass(frozen=True, slots=True)
class Claim:
    """A hypothesis with its final verdict (R0-D §10.1)."""

    id: str
    hypothesis: Hypothesis
    verdict: Verdict
    seq: int  # position in the run's total proposal order
    proposed: int  # round of first proposal
    decided: int  # round of the final verdict
    depth: int  # derivation depth (R0-D §6.3)
    effective_scope: tuple[ProofScope, ...] = field(default=())  # R0-D §9.4, a set

    @property
    def supported(self) -> bool:
        return self.verdict.status is VerdictStatus.SUPPORTED


# -- target satisfaction (R0-D §9.4) ----------------------------------------------------------------


def members(view: TreeView, population: Population, at: NodeId) -> frozenset[str] | None:
    """The moves of a population at a node (canonical UCI); None when it is every legal move."""

    if population.kind is PopulationKind.EXPLICIT:
        out = set()
        for move in population.moves:
            node = getattr(move, "node", None)
            if node is not None:
                out.add(view.node(node).incoming_move)
            else:
                line = next(ln for ln in view.search(move.search_id).lines if ln.rank == move.rank)
                out.add(line.pv[move.ply - 1])
        return frozenset(out)
    if population.kind is PopulationKind.ENGINE_REPORTED:
        assert population.search_id is not None
        return frozenset(line.move for line in view.search(population.search_id).lines)
    return None  # ENGINE_RANKED (every legal move, ranked by the search) and LEGAL


_ORDER = {
    PopulationKind.ENGINE_REPORTED: 0,
    PopulationKind.ENGINE_RANKED: 1,
    PopulationKind.LEGAL: 2,
}


def _stronger(scope: Population, target: Population) -> bool:
    if target.kind is PopulationKind.EXPLICIT or scope.kind is PopulationKind.EXPLICIT:
        if scope.kind is not target.kind:
            return False
        return set(target.moves) <= set(scope.moves)
    if _ORDER[scope.kind] < _ORDER[target.kind]:
        return False
    same_search = scope.search_id == target.search_id
    return target.kind is PopulationKind.LEGAL or scope.kind is PopulationKind.LEGAL or same_search


def satisfies(
    view: TreeView, scope: ProofScope, target: VerificationTarget, subject_move: str | None
) -> bool:
    """Does an achieved scope satisfy a target (R0-D §9.4)?"""

    if scope.quantifier is not target.quantifier or scope.at != target.at:
        return False
    q = target.quantifier
    if q in EXISTS:
        if not scope.witnesses:
            return False
        if q is Quantifier.EXISTS_ALTERNATIVE and subject_move in scope.witnesses:
            return False
        assert isinstance(target.at, NodeId)
        allowed = members(view, target.population, target.at)
        return allowed is None or all(w in allowed for w in scope.witnesses)
    if q in ALL or q is Quantifier.SELECTED_ALTERNATIVES:
        return _stronger(scope.population, target.population)
    # SPECIFIC_LINE, PERSISTENCE
    return target.horizon is None or (scope.plies is not None and scope.plies >= target.horizon)


# -- premises (R0-D §8.1.1, §8.1.2, §9.4) -----------------------------------------------------------


def accepted(premise: Claim, use: PremiseUse) -> bool:
    """Every member of the premise's effective scope is accepted by the requirement."""

    if not premise.supported or not premise.effective_scope:
        return False
    for scope in premise.effective_scope:
        if not scope.basis.at_least(use.requires.min_basis):
            return False
        if (scope.quantifier, scope.population.kind) not in use.requires.accepted:
            return False
    return True


def target_searches(target: VerificationTarget) -> frozenset[str]:
    """The search ids a target names (R0-D §8.1.2)."""

    out = set()
    if target.population.search_id is not None:
        out.add(target.population.search_id)
    if isinstance(target.at, LineSegment) and isinstance(target.at.line, EngineLineId):
        out.add(target.at.line.search_id)
    return frozenset(out)


def scope_searches(scope: ProofScope) -> frozenset[str]:
    """Every search a scope rests on: its listed searches and those its population and line name."""

    out = {ref.search_id for ref in scope.searches}
    if scope.population.search_id is not None:
        out.add(scope.population.search_id)
    if isinstance(scope.at, LineSegment) and isinstance(scope.at.line, EngineLineId):
        out.add(scope.at.line.search_id)
    return frozenset(out)


def search_compatible(premise: Claim, use: PremiseUse, target: VerificationTarget) -> bool:
    """R0-D §8.1.2; an `EXACT` scope naming no search satisfies both declarations."""

    if use.search is SearchCompat.ANY_SEARCH:
        return True
    allowed = target_searches(target)
    return all(scope_searches(scope) <= allowed for scope in premise.effective_scope)


def _anchor(view: TreeView, where: NodeId | LineSegment) -> tuple[NodeId, tuple[NodeId, ...]]:
    """The node a target or context starts at, and the nodes it covers."""

    if isinstance(where, NodeId):
        return where, (where,)
    line = view.line(where.line)
    nodes = line.nodes[where.first - line.first_index : where.last - line.first_index + 1]
    return nodes[0], tuple(nodes)


def _where(context) -> NodeId | LineSegment:
    if isinstance(context, NodeContext):
        return context.node
    if isinstance(context, LineContext | SpanContext):
        return context.segment
    raise ReasoningError(f"unknown context {context!r}")


def relation_holds(
    view: TreeView, relation: PremiseRelation, premise: Hypothesis, h: Hypothesis
) -> bool:
    """R0-D §8.1.1, on the premise's and the hypothesis's target `at`."""

    p_at, h_at = premise.target.at, h.target.at
    p_start, p_nodes = _anchor(view, p_at)
    h_start, _h_nodes = _anchor(view, h_at)
    if relation is PremiseRelation.SAME_CONTEXT:
        if p_at == h_at:
            return True
        node, segment = (p_at, h_at) if isinstance(p_at, NodeId) else (h_at, p_at)
        return (
            isinstance(node, NodeId)
            and isinstance(segment, LineSegment)
            and (_anchor(view, segment)[0] == node)
        )
    if relation is PremiseRelation.SAME_LINE:
        return (
            isinstance(p_at, LineSegment)
            and isinstance(h_at, LineSegment)
            and p_at.line == h_at.line
        )
    if relation is PremiseRelation.LINE_EXTENSION:
        return (
            isinstance(p_at, LineSegment)
            and isinstance(h_at, LineSegment)
            and p_at.line == h_at.line
            and h_at.first <= p_at.first
            and h_at.last >= p_at.last
        )
    if relation is PremiseRelation.ALTERNATIVE_OF:
        return p_start == h_start and p_at != h_at
    if relation is PremiseRelation.EARLIER_POSITION:
        return p_nodes[-1] in view.path(h_start)[:-1]
    raise ReasoningError(f"unknown premise relation {relation}")


def check_premises(view: TreeView, h: Hypothesis, claims: dict[str, Claim]) -> None:
    """A proposal that violates R0-D §8.1–§8.1.2 / §9.4 is a template bug: refuse it."""

    for use in h.premises:
        premise = claims.get(use.claim)
        if premise is None or not premise.supported:
            raise ReasoningError(f"{h.template}: premise {use.claim[:12]} is not a SUPPORTED claim")
        if not accepted(premise, use):
            raise ReasoningError(f"{h.template}: premise scope not accepted by its requirement")
        if not relation_holds(view, use.relation, premise.hypothesis, h):
            raise ReasoningError(f"{h.template}: premise relation {use.relation} does not hold")
        if not search_compatible(premise, use, h.target):
            raise ReasoningError(f"{h.template}: premise searches are not {use.search}")


def effective_scope(
    verdict: Verdict, h: Hypothesis, claims: dict[str, Claim]
) -> tuple[ProofScope, ...]:
    """Own scope and the premises' effective scopes, deduplicated and canonically sorted."""

    from calliope.reasoning.encoding import canonical_bytes

    scopes: dict[bytes, ProofScope] = {}
    if verdict.scope is not None:
        scopes[canonical_bytes(verdict.scope)] = verdict.scope
    for use in h.premises:
        for scope in claims[use.claim].effective_scope:
            scopes[canonical_bytes(scope)] = scope
    return tuple(scopes[k] for k in sorted(scopes))


def check_scope(
    view: TreeView, verdict: Verdict, h: Hypothesis, subject_move: str | None
) -> Verdict:
    """SUPPORTED only when the achieved scope satisfies the target; else SCOPE_SHORT (R0-D §9.2)."""

    if verdict.status is not VerdictStatus.SUPPORTED:
        return verdict
    assert verdict.scope is not None
    if satisfies(view, verdict.scope, h.target, subject_move):
        return verdict
    return Verdict(
        verdict.hypothesis,
        VerdictStatus.INCONCLUSIVE,
        verdict.evidence,
        verdict.scope,
        (),
        verdict.findings,
        "SCOPE_SHORT",
    )


__all__ = [
    "ALTERNATIVES",
    "COUNTERFACTUAL",
    "FINAL",
    "REALIZED",
    "CausalCheck",
    "Claim",
    "ProofScope",
    "Verdict",
    "VerdictStatus",
    "accepted",
    "check_premises",
    "check_scope",
    "effective_scope",
    "members",
    "relation_holds",
    "satisfies",
    "scope_searches",
    "search_compatible",
    "target_searches",
]
