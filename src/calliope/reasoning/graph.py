"""The claim graph: claims, labels and the edges between them (R0-D §10).

- `DERIVED_FROM` from every claim to its origins and premises; a DAG.
- Semantic edges go from a SUPPORTED claim to one of its own premises, with the kind its template
  declares for that premise's template, at the strength its causal check reached: `CAUSES` needs a
  passed `COUNTERFACTUAL` check, `EXPLAINS` a passed `REALIZED` check; otherwise the edge falls
  back to `ASSOCIATED_WITH` (R0-D D12, D15). Other declared kinds (`COMPARES_WITH`, …) need no
  check.
- `QUALIFIES` from an INCONCLUSIVE or REFUTED claim to each of its premises.
"""

from __future__ import annotations

from dataclasses import dataclass

from calliope.reasoning.errors import ReasoningError
from calliope.reasoning.hypotheses import HypothesisTemplate, RelationKind
from calliope.reasoning.verification import (
    COUNTERFACTUAL,
    REALIZED,
    CausalCheck,
    Claim,
    VerdictStatus,
)

_CHECKED = {RelationKind.CAUSES: COUNTERFACTUAL, RelationKind.EXPLAINS: REALIZED}


@dataclass(frozen=True, slots=True)
class Relation:
    source: str  # ClaimId
    target: object  # ClaimId | ObservationRef | JudgementRef
    kind: RelationKind


def _passed(claim: Claim, kind: str) -> bool:
    return any(
        isinstance(f, CausalCheck) and f.kind == kind and f.passed for f in claim.verdict.findings
    )


def semantic_kind(claim: Claim, declared: RelationKind) -> RelationKind:
    """The strongest level the claim's checks reach, down to `ASSOCIATED_WITH` (R0-D §10.2)."""

    if declared is RelationKind.CAUSES:
        if _passed(claim, COUNTERFACTUAL):
            return RelationKind.CAUSES
        declared = RelationKind.EXPLAINS
    if declared is RelationKind.EXPLAINS:
        return RelationKind.EXPLAINS if _passed(claim, REALIZED) else RelationKind.ASSOCIATED_WITH
    return declared


def relations(
    claims: tuple[Claim, ...], templates: dict[str, HypothesisTemplate]
) -> tuple[Relation, ...]:
    by_id = {c.id: c for c in claims}
    out: list[Relation] = []
    for claim in claims:
        h = claim.hypothesis
        for origin in h.origins:
            out.append(Relation(claim.id, origin, RelationKind.DERIVED_FROM))
        for use in h.premises:
            out.append(Relation(claim.id, use.claim, RelationKind.DERIVED_FROM))
            premise = by_id[use.claim]
            if claim.verdict.status is VerdictStatus.SUPPORTED:
                for decl in templates[h.template].relations:
                    if decl.premise_template == premise.hypothesis.template:
                        out.append(Relation(claim.id, use.claim, semantic_kind(claim, decl.kind)))
            else:
                out.append(Relation(claim.id, use.claim, RelationKind.QUALIFIES))
    _check_acyclic(claims, out)
    return tuple(sorted(dict.fromkeys(out), key=_relation_key))


def _relation_key(relation: Relation) -> tuple:
    from calliope.reasoning.encoding import canonical_bytes

    return (relation.kind.value, relation.source, canonical_bytes(relation.target))


def _check_acyclic(claims: tuple[Claim, ...], edges: list[Relation]) -> None:
    ids = {c.id for c in claims}
    graph: dict[str, list[str]] = {c.id: [] for c in claims}
    for edge in edges:
        if edge.kind is RelationKind.DERIVED_FROM and edge.target in ids:
            graph[edge.source].append(edge.target)  # type: ignore[arg-type]
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        mark = state.get(node, 0)
        if mark == 1:
            raise ReasoningError("DERIVED_FROM has a cycle (R0-D §10.2)")
        if mark == 2:
            return
        state[node] = 1
        for nxt in graph[node]:
            visit(nxt)
        state[node] = 2

    for node in sorted(graph):
        visit(node)
