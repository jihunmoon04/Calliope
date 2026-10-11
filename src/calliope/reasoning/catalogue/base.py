"""What the templates of catalogue v1 share (R2-D §3.0): fields, targets, scopes, verdicts."""

from __future__ import annotations

from typing import ClassVar

from calliope.facts import Color, EngineLineId, LineId, NodeId, TreeView
from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.findings import LineMaterial
from calliope.reasoning.grading import Grading
from calliope.reasoning.hypotheses import (
    Basis,
    ClaimRole,
    Direction,
    Hypothesis,
    Population,
    PopulationKind,
    ProposeContext,
    Quantifier,
    RelationDecl,
    ScopeRequirement,
    VerificationTarget,
    hypothesis,
)
from calliope.reasoning.lines import Line, read_line
from calliope.reasoning.needs import EvidenceNeed
from calliope.reasoning.observer import (
    Judgement,
    JudgementRef,
    JudgementStatus,
    Observation,
    ObservationRef,
    scored,
)
from calliope.reasoning.refs import Evidence, LineSegment, MoveRef, SearchRef
from calliope.reasoning.verification import Claim, ProofScope, Verdict, VerdictStatus

VERSION = "1"
BASE_POLICIES = ("points_v1",)
REQUIRE_LINE = ScopeRequirement(
    Basis.ENGINE, ((Quantifier.SPECIFIC_LINE, PopulationKind.ENGINE_REPORTED),)
)
REQUIRE_OFFER = ScopeRequirement(
    Basis.ENGINE, ((Quantifier.EXISTS_ALTERNATIVE, PopulationKind.ENGINE_REPORTED),)
)
F = Direction.FORWARD
B = Direction.BACKWARD


class Template:
    """A template of catalogue v1: the protocol's fields plus its predicate."""

    name: ClassVar[str]
    version: ClassVar[str] = VERSION
    role: ClassVar[ClaimRole]
    directions: ClassVar[frozenset[Direction]]
    relations: ClassVar[tuple[RelationDecl, ...]] = ()
    predicate: ClassVar[str]

    def make(self, ctx: ProposeContext, **fields) -> Hypothesis:
        return hypothesis(self, predicate=self.predicate, subject=ctx.subject, **fields)

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]:
        raise NotImplementedError

    def verify(self, h: Hypothesis, view: TreeView, grading: Grading) -> Verdict:
        raise NotImplementedError


# -- proposal context -------------------------------------------------------------------------------


def judged(ctx: ProposeContext) -> Judgement | None:
    """The target move's judgement when DECIDED (R2-D §3.0 common rules)."""

    judgement = ctx.judgements[0] if ctx.judgements else None
    if judgement is None or judgement.status is not JudgementStatus.DECIDED:
        return None
    return judgement


def observed(ctx: ProposeContext, kind: str) -> tuple[ObservationRef, Observation] | None:
    for observation in ctx.observations:
        if observation.kind == kind and observation.subject == ctx.subject:
            ref = ObservationRef(
                kind, observation.version, observation.subject, observation.round, 0
            )
            return ref, observation
    return None


def materials(ctx: ProposeContext) -> tuple[ObservationRef, dict[int, LineMaterial]] | None:
    """The `line_material` observation by rank of S."""

    found = observed(ctx, "line_material")
    if found is None:
        return None
    ref, observation = found
    return ref, {m.window.line.rank: m for m in observation.operands}


def judgement_ref(ctx: ProposeContext) -> JudgementRef:
    return JudgementRef(ctx.subject)


def supported_claims(ctx: ProposeContext, template: str) -> tuple[Claim, ...]:
    return tuple(
        c
        for c in ctx.claims
        if c.hypothesis.template == template and c.supported and c.hypothesis.subject == ctx.subject
    )


def claims_of(ctx: ProposeContext, template: str) -> tuple[Claim, ...]:
    return tuple(
        c
        for c in ctx.claims
        if c.hypothesis.template == template and c.hypothesis.subject == ctx.subject
    )


# -- targets (R2-D §3.0) ----------------------------------------------------------------------------


def seg(view: TreeView, line_id: EngineLineId) -> LineSegment | None:
    """`seg(L)`: all attached plies of the line; None when the line is not attached."""

    try:
        record = view.line(line_id)
    except KeyError:
        return None
    return LineSegment(line_id, record.first_index, record.first_index + len(record.nodes) - 1)


def line_target(segment: LineSegment) -> VerificationTarget:
    assert isinstance(segment.line, EngineLineId)
    return VerificationTarget(
        Quantifier.SPECIFIC_LINE,
        segment,
        Population(PopulationKind.ENGINE_REPORTED, segment.line.search_id),
    )


def edge(view: TreeView, parent: NodeId, child: NodeId) -> LineSegment:
    """`edge`: the played line's segment from P to C (R2-D §3.0)."""

    for record in view.lines():
        if not isinstance(record.line_id, LineId):
            continue
        nodes = record.nodes
        for i in range(len(nodes) - 1):
            if nodes[i] == parent and nodes[i + 1] == child:
                first = record.first_index + i
                return LineSegment(record.line_id, first, first + 1)
    raise ReasoningError(f"no input line holds the edge {parent} → {child}")


def played(child: NodeId) -> Population:
    return Population(PopulationKind.EXPLICIT, moves=(MoveRef(child),))


# -- verification -----------------------------------------------------------------------------------


def search_id(h: Hypothesis) -> str:
    population = h.target.population
    if population.search_id is not None:
        return population.search_id
    at = h.target.at
    if isinstance(at, LineSegment) and isinstance(at.line, EngineLineId):
        return at.line.search_id
    raise ReasoningError(f"{h.template}: the target names no search")


def mover(view: TreeView, h: Hypothesis) -> Color:
    return view.node(h.subject.parent).side_to_move


def opponent(color: Color) -> Color:
    return Color.BLACK if color is Color.WHITE else Color.WHITE


def lines(view: TreeView, h: Hypothesis, windows: tuple[LineSegment, ...]) -> tuple[Line, ...]:
    m = mover(view, h)
    return tuple(read_line(view, w, m) for w in windows)


def judgement(view: TreeView, h: Hypothesis, grading: Grading) -> Judgement:
    """The judgement re-read on S, the search the target names (R0-D R0-I1), under `grading`."""

    result = scored(view, h.subject, search_id(h), grading)
    if result.status is not JudgementStatus.DECIDED:
        raise ReasoningError(f"{h.template}: the judgement on S is not decided")
    return result


def scope(
    view: TreeView,
    h: Hypothesis,
    grading: Grading,
    ranks: tuple[int, ...],
    *,
    basis: Basis = Basis.ENGINE,
    plies: int | None = None,
    line: Line | None = None,
    witnesses: tuple[str, ...] = (),
    extra_policies: tuple[str, ...] = (),
) -> ProofScope:
    """The default scope (R2-D §3.0, §13): the target's quantifier and population, S's lines;
    the policies `points_v1`, the analysis's grading policy, then `extra_policies`."""

    sid = search_id(h)
    search = view.search(sid)
    return ProofScope(
        basis,
        h.target.at,
        h.target.quantifier,
        h.target.population,
        witnesses,
        tuple(SearchRef(sid, r) for r in dict.fromkeys(ranks)),
        search.profile.depth,
        search.multipv,
        line.k if line is not None else plies,
        line.record.end if line is not None and line.record is not None else None,
        (*BASE_POLICIES, grading.policy, *extra_policies),
    )


def exact_scope(
    h: Hypothesis, *, plies: int | None = 1, witnesses: tuple[str, ...] = (), policies=()
) -> ProofScope:
    return ProofScope(
        Basis.EXACT,
        h.target.at,
        h.target.quantifier,
        h.target.population,
        witnesses,
        plies=plies,
        policies=policies,
    )


def supported(
    h: Hypothesis, proof: ProofScope, findings: tuple = (), evidence: tuple[Evidence, ...] = ()
) -> Verdict:
    return Verdict(h.id, VerdictStatus.SUPPORTED, evidence, proof, (), findings)


def refuted(h: Hypothesis, findings: tuple = (), evidence: tuple[Evidence, ...] = ()) -> Verdict:
    return Verdict(h.id, VerdictStatus.REFUTED, evidence, None, (), findings)


def inconclusive(
    h: Hypothesis, reason: str, findings: tuple = (), evidence: tuple[Evidence, ...] = ()
) -> Verdict:
    return Verdict(h.id, VerdictStatus.INCONCLUSIVE, evidence, None, (), findings, reason)


def needs(h: Hypothesis, wanted: tuple[EvidenceNeed, ...]) -> Verdict:
    return Verdict(h.id, VerdictStatus.NEEDS_EVIDENCE, needs=tuple(dict.fromkeys(wanted)))
