"""Internal immutable MVP-P11 explanation graph and selection values.

Structural containers only.  Building one of these values proves nothing: it is not evidence
that the retained P10 package is valid, that a relation is true, or that a selection follows
the frozen selection policy.  Service-level P10 revalidation, the current empty-relation
policy and selection recomputation belong to the P11 graph validator and selector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from calliope.domain.explanation.claim import ExplanationClaim
from calliope.domain.explanation.evidence import EvidenceBundle
from calliope.errors import CalliopeError, ExplanationGraphError, ExplanationSelectionError

MAX_SELECTED_CLAIMS = 3
"""Frozen A0 cap on primary claims in one selection."""


class ExplanationRelationKind(StrEnum):
    """Reserved relation vocabulary; no kind is an active relation rule in MVP-P11."""

    ENABLES = "enables"
    PREVENTS = "prevents"
    LEADS_TO = "leads_to"
    CAUSES = "causes"
    CONTRASTS_WITH = "contrasts_with"
    SUPPORTS = "supports"


# -- request-local ordinal ids --

_ORDINAL_ID = re.compile(r"(rel|cl|ev)_([0-9]{3,})")


def _ordinal(value: object, prefix: str) -> int | None:
    """The 1-based ordinal of an exact canonical ``<prefix>_###`` id, otherwise None."""

    if not isinstance(value, str):
        return None
    match = _ORDINAL_ID.fullmatch(value)
    if match is None or match.group(1) != prefix:
        return None
    ordinal = int(match.group(2))
    if ordinal < 1 or value != f"{prefix}_{ordinal:03d}":
        return None
    return ordinal


def mint_relation_id(index: int) -> str:
    """Request-local relation id for the given 1-based canonical ordinal."""

    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise ExplanationGraphError("rel id ordinal must be an integer of at least 1")
    return f"rel_{index:03d}"


def _require_ids(
    values: object, prefix: str, label: str, error: type[CalliopeError]
) -> tuple[int, ...]:
    if not isinstance(values, tuple):
        raise error(f"{label} must be a tuple")
    ordinals = tuple(_ordinal(value, prefix) for value in values)
    if any(ordinal is None for ordinal in ordinals):
        raise error(f"{label} must contain canonical {prefix}_### ids")
    if len(set(values)) != len(values):
        raise error(f"{label} must be unique")
    return ordinals  # type: ignore[return-value]


# -- relation --


@dataclass(frozen=True, slots=True)
class ExplanationRelation:
    """Reserved claim-to-claim edge shape.

    Only structure is checked.  Whether ``evidence_ids`` belong to either endpoint, or prove
    the edge at all, is deliberately undecided: endpoint claim evidence is not relation
    authority, and relation-specific provenance needs its own reviewed design.
    """

    relation_id: str
    base_position_id: str
    source_claim_id: str
    kind: ExplanationRelationKind
    target_claim_id: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if _ordinal(self.relation_id, "rel") is None:
            raise ExplanationGraphError("relation_id must be a canonical rel_### id")
        if not self.base_position_id:
            raise ExplanationGraphError("relation base_position_id must not be empty")
        for label, claim_id in (("source", self.source_claim_id), ("target", self.target_claim_id)):
            if _ordinal(claim_id, "cl") is None:
                raise ExplanationGraphError(f"relation {label} must be a canonical cl_### id")
        if self.source_claim_id == self.target_claim_id:
            raise ExplanationGraphError("relation source and target must differ")
        if type(self.kind) is not ExplanationRelationKind:
            raise ExplanationGraphError("relation kind must be an ExplanationRelationKind")
        _require_ids(self.evidence_ids, "ev", "relation evidence_ids", ExplanationGraphError)


def _relation_order_key(relation: ExplanationRelation) -> tuple[object, ...]:
    """Frozen A0 §14 order: source ordinal, kind order, target ordinal, evidence ids."""

    kinds = list(ExplanationRelationKind)
    return (
        _ordinal(relation.source_claim_id, "cl"),
        kinds.index(relation.kind),
        _ordinal(relation.target_claim_id, "cl"),
        tuple(_ordinal(evidence_id, "ev") for evidence_id in relation.evidence_ids),
    )


# -- graph --


@dataclass(frozen=True, slots=True)
class ExplanationGraph:
    """The retained P10 package plus reserved relations.

    Structural container only, never a proof token.  Service-level P10 revalidation (from the
    retained ``evidence`` and ``claims``) and the current empty-relation policy belong to the
    P11 graph validator, which every graph consumer must run.
    """

    base_position_id: str
    evidence: EvidenceBundle
    claims: tuple[ExplanationClaim, ...]
    relations: tuple[ExplanationRelation, ...]

    def __post_init__(self) -> None:
        base = self.base_position_id
        if not base:
            raise ExplanationGraphError("graph base_position_id must not be empty")
        if not isinstance(self.evidence, EvidenceBundle):
            raise ExplanationGraphError("graph evidence must be an EvidenceBundle")
        if self.evidence.base_position_id != base:
            raise ExplanationGraphError("graph evidence belongs to another base position")

        if not isinstance(self.claims, tuple):
            raise ExplanationGraphError("graph claims must be a tuple")
        if any(not isinstance(claim, ExplanationClaim) for claim in self.claims):
            raise ExplanationGraphError("graph claims must contain ExplanationClaim values")
        if any(claim.base_position_id != base for claim in self.claims):
            raise ExplanationGraphError("graph claim belongs to another base position")
        claim_ids = tuple(claim.claim_id for claim in self.claims)
        _require_ids(claim_ids, "cl", "graph claim ids", ExplanationGraphError)

        if not isinstance(self.relations, tuple):
            raise ExplanationGraphError("graph relations must be a tuple")
        if any(not isinstance(relation, ExplanationRelation) for relation in self.relations):
            raise ExplanationGraphError("graph relations must contain ExplanationRelation values")
        if any(relation.base_position_id != base for relation in self.relations):
            raise ExplanationGraphError("graph relation belongs to another base position")
        relation_ids = tuple(relation.relation_id for relation in self.relations)
        if len(set(relation_ids)) != len(relation_ids):
            raise ExplanationGraphError("graph relation ids must be unique")
        known = set(claim_ids)
        for relation in self.relations:
            if relation.source_claim_id not in known:
                raise ExplanationGraphError("relation source claim is not in the graph")
            if relation.target_claim_id not in known:
                raise ExplanationGraphError("relation target claim is not in the graph")
        edges = [(r.source_claim_id, r.kind, r.target_claim_id) for r in self.relations]
        if len(set(edges)) != len(edges):
            raise ExplanationGraphError("duplicate (source, kind, target) relation")
        keys = [_relation_order_key(relation) for relation in self.relations]
        if keys != sorted(keys):
            raise ExplanationGraphError("graph relations must be in canonical order")
        if relation_ids != tuple(mint_relation_id(i) for i in range(1, len(relation_ids) + 1)):
            raise ExplanationGraphError("relation ids must match canonical tuple positions")


# -- selection --


@dataclass(frozen=True, slots=True)
class ExplanationSelection:
    """Selected claim/relation ids in priority (render) order.

    Structural container only.  Graph membership, family uniqueness, priority order and
    exact recomputation need the paired graph and belong to P11 selection validation.
    """

    base_position_id: str
    selected_claim_ids: tuple[str, ...]
    selected_relation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.base_position_id:
            raise ExplanationSelectionError("selection base_position_id must not be empty")
        _require_ids(self.selected_claim_ids, "cl", "selected_claim_ids", ExplanationSelectionError)
        if len(self.selected_claim_ids) > MAX_SELECTED_CLAIMS:
            raise ExplanationSelectionError(
                f"a selection holds at most {MAX_SELECTED_CLAIMS} claims"
            )
        _require_ids(
            self.selected_relation_ids, "rel", "selected_relation_ids", ExplanationSelectionError
        )
