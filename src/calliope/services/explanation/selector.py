"""MVP-P11 minimal explanation selection and exact selection revalidation.

The only chess-semantic knowledge here is the frozen closed ``(predicate, confidence)`` ->
priority tier map and predicate -> selection family map.  Nothing reads scores, ranks, PVs,
engine analyses, evidence internals or ``importance``, and no claim is created or changed.
"""

from __future__ import annotations

from enum import StrEnum

from calliope.domain.explanation import (
    ClaimConfidence,
    ClaimPredicate,
    ExplanationClaim,
    ExplanationGraph,
    ExplanationSelection,
)
from calliope.domain.explanation.graph import MAX_SELECTED_CLAIMS
from calliope.errors import ExplanationSelectionError
from calliope.services.explanation.graph_validator import ExplanationGraphValidator

_P = ClaimPredicate
_C = ClaimConfidence


class SelectionFamily(StrEnum):
    """Explanatory roles; at most one primary claim per family is selected."""

    MATE_OUTCOME = "mate_outcome"
    MATERIAL_OUTCOME = "material_outcome"
    TACTICAL_MECHANISM = "tactical_mechanism"
    FORCED_RESPONSE = "forced_response"
    TESTED_THREAT = "tested_threat"


_F = SelectionFamily

SELECTION_FAMILIES: dict[ClaimPredicate, SelectionFamily] = {
    _P.ALLOWS_CHECKMATE: _F.MATE_OUTCOME,
    _P.DELIVERS_CHECKMATE: _F.MATE_OUTCOME,
    _P.LEADS_TO_MATE: _F.MATE_OUTCOME,
    _P.AVOIDS_REPRESENTATIVE_MATE_FAILURE: _F.MATE_OUTCOME,
    _P.ALLOWS_MATERIAL_LOSS: _F.MATERIAL_OUTCOME,
    _P.WINS_MATERIAL: _F.MATERIAL_OUTCOME,
    _P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS: _F.MATERIAL_OUTCOME,
    _P.LEAVES_PIECE_HANGING: _F.TACTICAL_MECHANISM,
    _P.REMOVES_DEFENDER: _F.TACTICAL_MECHANISM,
    _P.ALLOWS_FORK: _F.TACTICAL_MECHANISM,
    _P.FORCES_RESPONSE: _F.FORCED_RESPONSE,
    _P.THREATENS_MATE_IF_IGNORED: _F.TESTED_THREAT,
    _P.THREATENS_MATERIAL_IF_IGNORED: _F.TESTED_THREAT,
}
"""Frozen A0 §8 predicate -> family map; closed over every current predicate."""

PRIORITY_TIERS: dict[tuple[ClaimPredicate, ClaimConfidence], int] = {
    # Tier 0 - exact checkmate outcome.
    (_P.DELIVERS_CHECKMATE, _C.EXACT): 0,
    (_P.ALLOWS_CHECKMATE, _C.EXACT): 0,
    # Tier 1 - verified mate/material consequence or preservation.
    (_P.ALLOWS_CHECKMATE, _C.ENGINE_VERIFIED): 1,
    (_P.LEADS_TO_MATE, _C.ENGINE_VERIFIED): 1,
    (_P.AVOIDS_REPRESENTATIVE_MATE_FAILURE, _C.ENGINE_VERIFIED): 1,
    (_P.ALLOWS_MATERIAL_LOSS, _C.ENGINE_VERIFIED): 1,
    (_P.WINS_MATERIAL, _C.ENGINE_VERIFIED): 1,
    (_P.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS, _C.ENGINE_VERIFIED): 1,
    # Tier 2 - verified tactical mechanism.
    (_P.LEAVES_PIECE_HANGING, _C.ENGINE_VERIFIED): 2,
    (_P.REMOVES_DEFENDER, _C.ENGINE_VERIFIED): 2,
    (_P.ALLOWS_FORK, _C.ENGINE_VERIFIED): 2,
    # Tier 3 - exact forced response.
    (_P.FORCES_RESPONSE, _C.EXACT): 3,
    # Tier 4 - tested threat.
    (_P.THREATENS_MATE_IF_IGNORED, _C.ENGINE_VERIFIED): 4,
    (_P.THREATENS_MATERIAL_IF_IGNORED, _C.ENGINE_VERIFIED): 4,
}
"""Frozen A0 §9 total map over the 14 P10-valid pairs; there is no default tier."""


def priority_tier(predicate: ClaimPredicate, confidence: ClaimConfidence) -> int:
    """Tier of an exact P10-valid pair; every other pair fails closed (FORCED included)."""

    if type(predicate) is not ClaimPredicate or type(confidence) is not ClaimConfidence:
        raise ExplanationSelectionError("priority requires exact P10 predicate/confidence members")
    tier = PRIORITY_TIERS.get((predicate, confidence))
    if tier is None:
        raise ExplanationSelectionError(
            f"no frozen priority for {predicate.value} / {confidence.value}"
        )
    return tier


def selection_family(predicate: ClaimPredicate) -> SelectionFamily:
    if type(predicate) is not ClaimPredicate or predicate not in SELECTION_FAMILIES:
        raise ExplanationSelectionError("predicate has no frozen selection family")
    return SELECTION_FAMILIES[predicate]


def select_claim_ids(claims: tuple[ExplanationClaim, ...]) -> tuple[str, ...]:
    """The frozen A0 §10 algorithm over an already-validated canonical claim tuple.

    Pure ordering only; it validates nothing.  Callers use ``ExplanationSelector``.
    """

    ranked = sorted(
        enumerate(claims),
        key=lambda item: (priority_tier(item[1].predicate, item[1].confidence), item[0]),
    )
    families: list[SelectionFamily] = []
    selected: list[str] = []
    for _, claim in ranked:
        family = selection_family(claim.predicate)
        if family in families:
            continue
        families.append(family)
        selected.append(claim.claim_id)
        if len(selected) == MAX_SELECTED_CLAIMS:
            break
    return tuple(selected)


class ExplanationSelector:
    """Graph -> minimal primary selection; the graph is revalidated first, never trusted."""

    def __init__(self) -> None:
        self._graphs = ExplanationGraphValidator()

    def select(self, graph: ExplanationGraph) -> ExplanationSelection:
        self._graphs.validate(graph)
        return ExplanationSelection(
            base_position_id=graph.base_position_id,
            selected_claim_ids=select_claim_ids(graph.claims),
            # Graph validation admits no relation, so no relation can be selected.
            selected_relation_ids=(),
        )


class ExplanationSelectionValidator:
    """Validates a (graph, selection) pair by exact recomputation from that graph.

    Request-local ids such as ``cl_001`` repeat across packages, so id membership alone
    never establishes that a selection belongs to a graph.
    """

    def __init__(self) -> None:
        self._selector = ExplanationSelector()

    def validate(
        self, graph: ExplanationGraph, selection: ExplanationSelection
    ) -> ExplanationSelection:
        expected = self._selector.select(graph)  # runs ExplanationGraphValidator first
        if type(selection) is not ExplanationSelection:
            raise ExplanationSelectionError("selection validation requires an ExplanationSelection")
        if selection.base_position_id != graph.base_position_id:
            raise ExplanationSelectionError("selection belongs to another base position")
        if (
            type(selection.selected_claim_ids) is not tuple
            or type(selection.selected_relation_ids) is not tuple
            or selection.selected_claim_ids != expected.selected_claim_ids
            or selection.selected_relation_ids != expected.selected_relation_ids
        ):
            raise ExplanationSelectionError(
                "selection differs from the exact frozen recomputation for this graph"
            )
        return selection
