"""MVP-P11 graph trust boundary: P10 package revalidation and the empty-relation policy.

Owning an ``ExplanationGraph`` grants no authority; frozen values can be constructed by hand
or tampered.  Every graph consumer runs ``ExplanationGraphValidator`` first.  It re-runs the
canonical P10 ``ClaimValidator`` from the retained package and never reads chess meaning,
scores, engines or rules.
"""

from __future__ import annotations

from calliope.domain.explanation import (
    EvidenceBundle,
    EvidenceGroup,
    EvidenceSourceFamily,
    ExplanationClaim,
    ExplanationGraph,
)
from calliope.errors import ExplanationClaimError, ExplanationEvidenceError, ExplanationGraphError
from calliope.services.explanation.claim_validator import ClaimValidator


def validate_p10_package(
    bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]
) -> tuple[ExplanationClaim, ...]:
    """Re-run P10 validation, dispatched only by the bundle's group ``source_family``.

    Returns the exact supplied claim tuple object; nothing is copied, sorted or renumbered.
    """

    if not isinstance(bundle, EvidenceBundle):
        raise ExplanationGraphError("P11 requires a P10 EvidenceBundle")
    if not isinstance(bundle.groups, tuple) or any(
        not isinstance(group, EvidenceGroup) for group in bundle.groups
    ):
        raise ExplanationGraphError("P10 bundle groups must be a tuple of EvidenceGroup values")
    # Exact enum members only: a plain string would compare equal to the StrEnum value.
    if any(type(group.source_family) is not EvidenceSourceFamily for group in bundle.groups):
        raise ExplanationGraphError("P10 group source_family must be an EvidenceSourceFamily")
    validator = ClaimValidator()
    families = {group.source_family for group in bundle.groups}
    if not families:
        # Family-neutral empty package; anything empty-like but non-empty is never normalized.
        if bundle.evidence != () or bundle.groups != () or claims != ():
            raise ExplanationGraphError("a package without groups must be completely empty")
        validate = validator.validate_bad_move
    elif families == {EvidenceSourceFamily.BAD_MOVE_CAUSE}:
        validate = validator.validate_bad_move
    elif families == {EvidenceSourceFamily.GOOD_MOVE_BENEFIT}:
        validate = validator.validate_good_move
    else:
        raise ExplanationGraphError("P10 package must have exactly one supported source family")
    try:
        validated = validate(bundle, claims)
    except (ExplanationClaimError, ExplanationEvidenceError) as exc:
        raise ExplanationGraphError(f"P10 package failed revalidation: {exc}") from exc
    if validated is not claims:
        raise ExplanationGraphError("P10 validation must return the exact supplied claim tuple")
    return validated


class ExplanationGraphValidator:
    """The P11 trust boundary every graph consumer must run before reading a graph."""

    def validate(self, graph: ExplanationGraph) -> ExplanationGraph:
        if type(graph) is not ExplanationGraph:
            raise ExplanationGraphError("graph validation requires an ExplanationGraph")
        # ACTIVE_RELATION_RULES == (): no relation has reviewed relation-specific provenance.
        if graph.relations != ():
            raise ExplanationGraphError("no relation rule is active; relations must be empty")
        if not isinstance(graph.evidence, EvidenceBundle):
            raise ExplanationGraphError("graph evidence must be an EvidenceBundle")
        if not graph.base_position_id or graph.evidence.base_position_id != graph.base_position_id:
            raise ExplanationGraphError("graph evidence belongs to another base position")
        validate_p10_package(graph.evidence, graph.claims)
        return graph
