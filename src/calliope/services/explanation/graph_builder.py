"""MVP-P11 GraphBuilder: one revalidated P10 package -> relation-free ExplanationGraph."""

from __future__ import annotations

from calliope.domain.explanation import EvidenceBundle, ExplanationClaim, ExplanationGraph
from calliope.services.explanation.graph_validator import (
    ExplanationGraphValidator,
    validate_p10_package,
)


class GraphBuilder:
    """Wraps the exact validated P10 package; mints no claims and no relations."""

    def __init__(self) -> None:
        self._validator = ExplanationGraphValidator()

    def build(
        self, bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]
    ) -> ExplanationGraph:
        validated = validate_p10_package(bundle, claims)
        graph = ExplanationGraph(
            base_position_id=bundle.base_position_id,
            evidence=bundle,
            claims=validated,
            relations=(),
        )
        return self._validator.validate(graph)
