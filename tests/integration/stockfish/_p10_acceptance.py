"""P10-I6 shared acceptance checks over already-observed real P8/P9 results (not collected).

Only projects retained real evidence through EvidenceBuilder -> ClaimBuilder -> ClaimValidator.
Never calls Stockfish, P7 or chess rules, and never reads a score.
"""

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
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
from calliope.services.counterfactual import CounterfactualAnalyzer
from calliope.services.explanation import (
    DeterministicExplanationRenderer,
    ExplanationSelectionValidator,
    ExplanationSelector,
    GraphBuilder,
)
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.claim_validator import ClaimValidator
from calliope.services.explanation.evidence_builder import EvidenceBuilder
from calliope.services.explanation.selector import selection_family


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


# ---- P11-I4: selection over the same accepted real package -----------------------------------


def select_p11(bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...]):
    """Accepted real P10 package -> P11 graph + selection; no engine, rules or score access.

    Returns ``(graph, selection, selected claims in render order)``.
    """

    before = repr(claims)
    graph = GraphBuilder().build(bundle, claims)
    selection = ExplanationSelector().select(graph)
    assert ExplanationSelectionValidator().validate(graph, selection) is selection
    assert graph.evidence is bundle and graph.claims is claims
    assert graph.relations == () and selection.selected_relation_ids == ()
    assert selection.base_position_id == bundle.base_position_id
    by_id = {claim.claim_id: claim for claim in claims}
    selected = [by_id[claim_id] for claim_id in selection.selected_claim_ids]
    assert 0 <= len(selected) <= 3
    families = [selection_family(claim.predicate) for claim in selected]
    assert len(set(families)) == len(families)
    assert repr(claims) == before  # P10 claims are untouched by P11
    assert all(claim.importance is None for claim in claims)
    return graph, selection, selected


def p11_signature(graph, selection) -> tuple:
    """Stable P11 semantics only; no cp, PV, timing or engine data."""

    return (
        graph.base_position_id,
        tuple((c.claim_id, c.predicate, c.confidence, c.scope) for c in graph.claims),
        tuple(r.relation_id for r in graph.relations),
        selection.selected_claim_ids,
        selection.selected_relation_ids,
    )


# ---- P12-I1: deterministic rendering of the same accepted real package -----------------------

NO_VERIFIED_EXPLANATION = "No verified explanation is available."
_CONNECTIVES = (" because ", " therefore ", " so ", " causes ", " enables ", " which leads to ")


def _forbid_engine_rules_and_p7(patch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("P11/P12 must not call engines, chess rules or P7")

    for cls in (PythonChessAdapter, StockfishAdapter, CounterfactualAnalyzer):
        for attribute in dir(cls):
            if not attribute.startswith("_") and callable(getattr(cls, attribute)):
                patch.setattr(cls, attribute, forbidden)


def render_p12(bundle: EvidenceBundle, claims: tuple[ExplanationClaim, ...], monkeypatch):
    """Accepted real P10 package -> P11 -> P12 with engines, chess rules and P7 disabled.

    The patch is scoped to this call so engine fixtures can still close afterwards.
    Returns ``(rendered, selected claims in render order)``.
    """

    before = repr(claims)
    with monkeypatch.context() as patch:
        _forbid_engine_rules_and_p7(patch)
        graph, selection, selected = select_p11(bundle, claims)
        rendered = DeterministicExplanationRenderer().render(graph, selection)
    assert rendered.used_claim_ids == selection.selected_claim_ids
    assert len(rendered.sentences) == len(selection.selected_claim_ids)
    if selected:
        assert rendered.text == " ".join(rendered.sentences)
    else:
        assert rendered.text == NO_VERIFIED_EXPLANATION and rendered.sentences == ()
    assert graph.relations == () and selection.selected_relation_ids == ()
    assert not any(word in rendered.text.lower() for word in _CONNECTIVES)
    assert repr(claims) == before  # P12 changes no claim
    return rendered, selected


def p12_signature(rendered) -> tuple:
    return (rendered.text, rendered.sentences, rendered.used_claim_ids)
