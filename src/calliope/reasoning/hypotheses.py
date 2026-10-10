"""The hypothesis contract (R0-D §8): what is claimed, where, over what, and from what.

A hypothesis fixes its verification target when it is proposed (R0-D D11). Its id is the sha256 of
the canonical encoding of its identity fields; origins and directions are provenance (§8.3).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Protocol

from calliope.facts import NodeId, TreeView
from calliope.reasoning.refs import ClaimId, LineSegment, MoveRef, MoveSubject, SearchMoveRef

if TYPE_CHECKING:
    from calliope.reasoning.observer import Judgement, Observation
    from calliope.reasoning.verification import Claim, Verdict


class ClaimRole(StrEnum):
    CONSEQUENCE = "consequence"
    MECHANISM = "mechanism"
    CAUSE = "cause"
    FUNCTION = "function"
    COMPARISON = "comparison"


class Direction(StrEnum):
    FORWARD = "forward"
    BACKWARD = "backward"


class Quantifier(StrEnum):
    """R0-D §8.2."""

    SPECIFIC_LINE = "specific_line"
    PERSISTENCE = "persistence"
    EXISTS_RESPONSE = "exists_response"
    ALL_RESPONSES = "all_responses"
    EXISTS_ALTERNATIVE = "exists_alternative"
    ALL_ALTERNATIVES = "all_alternatives"
    SELECTED_ALTERNATIVES = "selected_alternatives"


EXISTS = (Quantifier.EXISTS_RESPONSE, Quantifier.EXISTS_ALTERNATIVE)
ALL = (Quantifier.ALL_RESPONSES, Quantifier.ALL_ALTERNATIVES)
ALTERNATIVES = (
    Quantifier.EXISTS_ALTERNATIVE,
    Quantifier.ALL_ALTERNATIVES,
    Quantifier.SELECTED_ALTERNATIVES,
)


class PopulationKind(StrEnum):
    EXPLICIT = "explicit"
    ENGINE_REPORTED = "engine_reported"
    ENGINE_RANKED = "engine_ranked"
    LEGAL = "legal"


@dataclass(frozen=True, slots=True)
class Population:
    """Which moves a quantifier ranges over (R0-D §8.2).

    `EXPLICIT` lists `moves`; `ENGINE_REPORTED` / `ENGINE_RANKED` name `search_id`; `LEGAL` has
    neither.
    """

    kind: PopulationKind
    search_id: str | None = None
    moves: tuple[MoveRef | SearchMoveRef, ...] = ()

    def __post_init__(self) -> None:
        searched = self.kind in (PopulationKind.ENGINE_REPORTED, PopulationKind.ENGINE_RANKED)
        if searched != (self.search_id is not None):
            raise ValueError(f"population {self.kind} and search id {self.search_id!r} disagree")
        if (self.kind is PopulationKind.EXPLICIT) != bool(self.moves):
            raise ValueError("only an EXPLICIT population lists moves, and it lists some")


@dataclass(frozen=True, slots=True)
class VerificationTarget:
    quantifier: Quantifier
    at: NodeId | LineSegment  # the node whose moves are quantified, or the line
    population: Population
    horizon: int | None = None  # plies within which the outcome must hold or appear

    def __post_init__(self) -> None:
        if (
            self.quantifier is Quantifier.SELECTED_ALTERNATIVES
            and self.population.kind is not PopulationKind.EXPLICIT
        ):
            raise ValueError("SELECTED_ALTERNATIVES takes only an EXPLICIT population (R0-D §8.2)")
        on_lines = self.quantifier in (Quantifier.SPECIFIC_LINE, Quantifier.PERSISTENCE)
        if on_lines != isinstance(self.at, LineSegment):
            raise ValueError(
                f"{self.quantifier} needs `at` to be a {'line' if on_lines else 'node'}"
            )


@dataclass(frozen=True, slots=True)
class NodeContext:
    node: NodeId


@dataclass(frozen=True, slots=True)
class LineContext:
    segment: LineSegment


@dataclass(frozen=True, slots=True)
class SpanContext:
    segment: LineSegment
    first: int
    last: int


Context = NodeContext | LineContext | SpanContext


class Basis(StrEnum):
    """`EXACT` ⊒ `ENGINE` (R0-D §9.4)."""

    EXACT = "exact"
    ENGINE = "engine"

    def at_least(self, other: Basis) -> bool:
        return self is Basis.EXACT or other is Basis.ENGINE


class PremiseRelation(StrEnum):
    """R0-D §8.1.1."""

    SAME_CONTEXT = "same_context"
    SAME_LINE = "same_line"
    LINE_EXTENSION = "line_extension"
    ALTERNATIVE_OF = "alternative_of"
    EARLIER_POSITION = "earlier_position"


class SearchCompat(StrEnum):
    """R0-D §8.1.2."""

    SAME_SEARCH = "same_search"
    ANY_SEARCH = "any_search"


@dataclass(frozen=True, slots=True)
class ScopeRequirement:
    min_basis: Basis
    accepted: tuple[tuple[Quantifier, PopulationKind], ...]


@dataclass(frozen=True, slots=True)
class PremiseUse:
    claim: ClaimId
    requires: ScopeRequirement
    relation: PremiseRelation
    search: SearchCompat


# An origin (R0-D §8.1) is an `ObservationRef`, a `JudgementRef` or a `ClaimId`.


@dataclass(frozen=True, slots=True)
class Hypothesis:
    id: ClaimId
    template: str
    version: str
    role: ClaimRole
    predicate: str
    subject: MoveSubject
    context: Context
    operands: tuple
    target: VerificationTarget
    premises: tuple[PremiseUse, ...]
    origins: tuple  # ObservationRef | JudgementRef | ClaimId, sorted canonically
    directions: tuple[Direction, ...]  # sorted; a set in meaning (R0-D §8.1)


class RelationKind(StrEnum):
    DERIVED_FROM = "derived_from"
    ASSOCIATED_WITH = "associated_with"
    EXPLAINS = "explains"
    CAUSES = "causes"
    ENABLES = "enables"
    PREVENTS = "prevents"
    COMPARES_WITH = "compares_with"
    QUALIFIES = "qualifies"


@dataclass(frozen=True, slots=True)
class RelationDecl:
    """A semantic edge a template may create from its claim to a premise of `premise_template`."""

    kind: RelationKind
    premise_template: str


@dataclass(frozen=True, slots=True)
class ProposeContext:
    view: TreeView
    subject: MoveSubject
    judgements: tuple[Judgement, ...]
    observations: tuple[Observation, ...]
    claims: tuple[Claim, ...]  # every claim so far, any status


class HypothesisTemplate(Protocol):
    name: ClassVar[str]
    version: ClassVar[str]
    role: ClassVar[ClaimRole]
    directions: ClassVar[frozenset[Direction]]
    relations: ClassVar[tuple[RelationDecl, ...]]

    def propose(self, ctx: ProposeContext) -> tuple[Hypothesis, ...]: ...

    def verify(self, h: Hypothesis, view: TreeView) -> Verdict: ...


def hypothesis(
    template: HypothesisTemplate,
    *,
    predicate: str,
    subject: MoveSubject,
    context: Context,
    operands: tuple,
    target: VerificationTarget,
    premises: tuple[PremiseUse, ...] = (),
    origins: tuple = (),
    directions: tuple[Direction, ...] | None = None,
) -> Hypothesis:
    """Build a hypothesis of `template` with its canonical id (R0-D §8.3)."""

    chosen = tuple(sorted(directions if directions is not None else template.directions))
    claim_id = _identity_hash(
        template.name, template.version, predicate, subject, context, operands, target, premises
    )
    return Hypothesis(
        claim_id,
        template.name,
        template.version,
        template.role,
        predicate,
        subject,
        context,
        operands,
        target,
        premises,
        tuple(origins),
        chosen,
    )


def _identity_hash(
    template, version, predicate, subject, context, operands, target, premises
) -> str:
    from calliope.reasoning.encoding import canonical_bytes

    identity = (template, version, predicate, subject, context, operands, target,
                tuple(p.claim for p in premises))  # fmt: skip
    return hashlib.sha256(canonical_bytes(identity)).hexdigest()


def hypothesis_id(h: Hypothesis) -> str:
    """The id a hypothesis must carry (R0-D §8.3); the runner refuses any other."""

    return _identity_hash(
        h.template, h.version, h.predicate, h.subject, h.context, h.operands, h.target, h.premises
    )
