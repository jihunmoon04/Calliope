"""The reasoning type registry and canonical bytes (R0-D §14.1).

The encoding is the fact engine's `fact_encoding_v1` (F5-D §2) over a closed registry: every fact
type (`type_registry(REGISTRY)`) plus the reasoning types. Integers only, no floats.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from calliope.facts import REGISTRY, canonical, encode, type_registry


@cache
def reasoning_registry() -> dict[str, type]:
    from calliope.reasoning import (
        findings,
        grading,
        graph,
        hypotheses,
        labels,
        needs,
        observer,
        refs,
        verification,
    )

    registry = dict(type_registry(REGISTRY))
    kinds = (
        refs.MoveSubject,
        refs.PieceRef,
        refs.SquareRef,
        refs.MoveRef,
        refs.SearchMoveRef,
        refs.MaterialAmount,
        refs.LineSegment,
        refs.FactRef,
        refs.SearchRef,
        refs.ScopeRef,
        hypotheses.ClaimRole,
        hypotheses.Direction,
        hypotheses.Quantifier,
        hypotheses.PopulationKind,
        hypotheses.Population,
        hypotheses.VerificationTarget,
        hypotheses.NodeContext,
        hypotheses.LineContext,
        hypotheses.SpanContext,
        hypotheses.Basis,
        hypotheses.PremiseRelation,
        hypotheses.SearchCompat,
        hypotheses.ScopeRequirement,
        hypotheses.PremiseUse,
        hypotheses.Hypothesis,
        hypotheses.RelationKind,
        grading.GradingSpec,
        grading.CurveSource,
        grading.Curve,
        grading.Grading,
        observer.Grade,
        observer.JudgementStatus,
        observer.JudgementRef,
        observer.ObservationRef,
        observer.MissingLine,
        observer.LineScore,
        observer.Judgement,
        observer.Observation,
        verification.VerdictStatus,
        verification.ProofScope,
        verification.CausalCheck,
        verification.Verdict,
        verification.Claim,
        graph.ClaimRelation,
        needs.FamilyNeed,
        needs.LineNeed,
        *findings.KINDS,
        labels.LabelKind,
        labels.Label,
    )
    for kind in kinds:
        existing = registry.setdefault(kind.__name__, kind)
        if existing is not kind:
            raise TypeError(f"two registered types are named {kind.__name__}")
    return registry


def register(*kinds: type) -> None:
    """Add record types of a later catalogue to the closed registry."""

    registry = reasoning_registry()
    for kind in kinds:
        existing = registry.setdefault(kind.__name__, kind)
        if existing is not kind:
            raise TypeError(f"two registered types are named {kind.__name__}")


def canonical_bytes(value: Any) -> bytes:
    return canonical(value, reasoning_registry())


def encoded(value: Any) -> Any:
    return encode(value, reasoning_registry())
