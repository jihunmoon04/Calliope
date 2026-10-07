"""P10-I6 shared acceptance checks over already-observed real P8/P9 results (not collected).

Only projects retained real evidence through EvidenceBuilder -> ClaimBuilder -> ClaimValidator.
Never calls Stockfish, P7 or chess rules, and never reads a score.
"""

from calliope.domain.analysis import BadMoveExplanationResult, GoodMoveExplanationResult
from calliope.domain.engine import EngineIdentity, EngineSettings
from calliope.domain.explanation import (
    ClaimConfidence,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    ExplanationClaim,
    claim_entity_identity,
    required_claim_scope,
)
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.claim_validator import ClaimValidator
from calliope.services.explanation.evidence_builder import EvidenceBuilder


def project(
    result: BadMoveExplanationResult | GoodMoveExplanationResult,
) -> tuple[EvidenceBundle, tuple[ExplanationClaim, ...]]:
    """Real P8/P9 result -> independently re-validated P10 package."""

    if isinstance(result, BadMoveExplanationResult):
        bundle = EvidenceBuilder().build_bad_move(result)
        claims = ClaimBuilder().build_bad_move(bundle)
        assert ClaimValidator().validate_bad_move(bundle, claims) is claims
    else:
        bundle = EvidenceBuilder().build_good_move(result)
        claims = ClaimBuilder().build_good_move(bundle)
        assert ClaimValidator().validate_good_move(bundle, claims) is claims
    return bundle, claims


def owned(bundle: EvidenceBundle, group) -> list:
    by_id = {record.evidence_id: record for record in bundle.evidence}
    return [by_id[evidence_id] for evidence_id in group.evidence_ids]


def claim_for(claims, group) -> ExplanationClaim:
    (claim,) = [c for c in claims if set(c.evidence_ids) <= set(group.evidence_ids)]
    return claim


def assert_accepted_package(
    bundle: EvidenceBundle,
    claims: tuple[ExplanationClaim, ...],
    sources,
    identity: EngineIdentity,
    settings: EngineSettings,
) -> None:
    """Invariants every accepted real package must satisfy, whatever its family."""

    supported = {(s.kind, tuple(sorted(s.subject, key=repr))) for s in sources}
    grouped = {(g.source_kind, tuple(sorted(g.source_subject, key=repr))) for g in bundle.groups}
    assert grouped == supported  # only SUPPORTED children; no refuted/inconclusive sibling
    assert len(claims) == len(bundle.groups)
    by_key = {(s.kind, tuple(sorted(s.subject, key=repr))): s for s in sources}
    for group in bundle.groups:
        source = by_key[(group.source_kind, tuple(sorted(group.source_subject, key=repr)))]
        claim = claim_for(claims, group)
        records = owned(bundle, group)
        # Provenance is the real upstream decision tuple, copied verbatim.
        assert group.required_probe_results == source.probe_results
        (counterfactual,) = [r for r in records if type(r) is CounterfactualEvidence]
        assert counterfactual.probe_results == group.required_probe_results
        assert claim.subject == group.played_move
        assert claim.confidence is not ClaimConfidence.FORCED
        assert claim.scope is required_claim_scope(claim.predicate)
        assert claim.importance is None
        if claim.confidence is ClaimConfidence.ENGINE_VERIFIED:
            assert claim.evidence_ids == group.evidence_ids
        non_terminal = [r for r in group.required_probe_results if r.engine_analysis is not None]
        engines = [r for r in records if type(r) is EngineEvidence]
        assert [e.probe_result for e in engines] == non_terminal
        for engine in engines:
            analysis = engine.probe_result.engine_analysis
            assert analysis.engine == identity
            assert "stockfish" in analysis.engine.name.lower()
            assert analysis.settings == settings


def assert_silent(bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]) -> None:
    assert bundle.groups == () and bundle.evidence == () and claims == ()


def semantic_signature(bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]) -> tuple:
    """Stable P10 semantics only: no score, PV suffix or engine timing enters the signature."""

    return (
        tuple(
            (
                g.source_kind,
                g.evidence_form,
                g.source_subject,
                g.mate_evidence_level,
                g.evidence_ids,
                tuple(type(r).__name__ for r in owned(bundle, g)),
                tuple((a.rank, a.move.uci) for a in g.failed_alternatives),
            )
            for g in bundle.groups
        ),
        tuple(
            (
                c.claim_id,
                c.predicate,
                c.confidence,
                c.scope,
                claim_entity_identity(c.subject),
                tuple(claim_entity_identity(o) for o in c.objects),
                c.evidence_ids,
            )
            for c in claims
        ),
    )
