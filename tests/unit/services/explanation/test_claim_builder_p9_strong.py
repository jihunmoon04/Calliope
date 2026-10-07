import ast
from dataclasses import replace
from pathlib import Path

import pytest
from _p9_strong_claim_scenarios import (
    SCENARIOS,
    claims,
    direct_mate,
    evidence,
    exact_mate,
    forces,
    package,
    tamper,
)

from calliope.domain.explanation import (
    BoardFactEvidence,
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    CounterfactualEvidence,
    EngineEvidence,
    EvidenceBundle,
    MotifEvidence,
    MoveClaimEntity,
    PieceClaimEntity,
    VariationEvidence,
    claim_entity_sort_key,
)
from calliope.errors import ExplanationClaimError, IncompatibleClaimEvidenceError
from calliope.services.explanation import claim_builder, claim_validator, evidence_builder
from calliope.services.explanation.claim_validator import ClaimValidator


@pytest.mark.parametrize(
    "make,predicate,confidence,scope",
    [
        (SCENARIOS[0], ClaimPredicate.FORCES_RESPONSE, ClaimConfidence.EXACT, ClaimScope.LOCAL),
        (SCENARIOS[1], ClaimPredicate.DELIVERS_CHECKMATE, ClaimConfidence.EXACT, ClaimScope.LOCAL),
        (
            SCENARIOS[2],
            ClaimPredicate.LEADS_TO_MATE,
            ClaimConfidence.ENGINE_VERIFIED,
            ClaimScope.LOCAL,
        ),
        (
            SCENARIOS[3],
            ClaimPredicate.THREATENS_MATE_IF_IGNORED,
            ClaimConfidence.ENGINE_VERIFIED,
            ClaimScope.TESTED_RESPONSE,
        ),
        (
            SCENARIOS[4],
            ClaimPredicate.WINS_MATERIAL,
            ClaimConfidence.ENGINE_VERIFIED,
            ClaimScope.LOCAL,
        ),
        (
            SCENARIOS[5],
            ClaimPredicate.THREATENS_MATERIAL_IF_IGNORED,
            ClaimConfidence.ENGINE_VERIFIED,
            ClaimScope.TESTED_RESPONSE,
        ),
    ],
)
def test_six_real_semantic_mappings(make, predicate, confidence, scope):
    bundle, claim, group, records = package(make)
    assert (claim.predicate, claim.confidence, claim.scope) == (predicate, confidence, scope)
    assert claim.subject == group.played_move and claim.importance is None
    assert len([o for o in claim.objects if isinstance(o, PieceClaimEntity)]) == len(
        group.source_subject
    )
    assert [o for o in claim.objects if isinstance(o, MoveClaimEntity)] == (
        [group.response] if group.response else []
    )
    assert list(claim.objects) == sorted(claim.objects, key=claim_entity_sort_key)
    by_id = {r.evidence_id: r for r in records}
    if confidence is ClaimConfidence.EXACT:
        assert not any(
            isinstance(by_id[eid], (EngineEvidence, CounterfactualEvidence))
            for eid in claim.evidence_ids
        )
        if make is forces:
            assert [type(by_id[eid]) for eid in claim.evidence_ids] == [
                BoardFactEvidence,
                MotifEvidence,
            ]
        if make is exact_mate:
            assert isinstance(by_id[claim.evidence_ids[-1]], VariationEvidence)
    else:
        assert claim.evidence_ids == group.evidence_ids
    built = (claim,)
    assert ClaimValidator().validate_good_move(bundle, built) is built


def test_reversing_groups_produces_identical_canonical_claim_tuple():
    bundle = evidence(direct_mate())
    built = claims(bundle)
    assert len(built) == len(bundle.groups) == 2
    reversed_bundle = EvidenceBundle(bundle.base_position_id, bundle.evidence, bundle.groups[::-1])
    assert claims(reversed_bundle) == built
    assert repr(claims(reversed_bundle)) == repr(built)
    assert [c.claim_id for c in built] == ["cl_001", "cl_002"]


def test_builder_does_not_reconstruct_missing_source_entities():
    bundle, _, _, records = package(forces)
    for record in records:
        if hasattr(record, "pieces"):
            tamper(record, pieces=())
    with pytest.raises(IncompatibleClaimEvidenceError, match="0 retained presentations"):
        claims(bundle)


def test_empty_bundle_is_valid():
    assert claims(EvidenceBundle("pos_base", (), ())) == ()


def test_wrong_runtime_type():
    with pytest.raises(ExplanationClaimError, match="EvidenceBundle"):
        claims(None)


@pytest.mark.parametrize("module", [evidence_builder, claim_builder, claim_validator])
def test_no_score_policy_and_no_execution_dependencies(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    forbidden = {
        "score",
        "scores",
        "cp",
        "mate",
        "wdl",
        "cp_loss",
        "expected_score_loss",
        "best_score",
        "played_score",
        "best_line",
        "lines",
        "material_delta",
        "stable_at_ply",
        "stable_deficit",
    }
    assert not {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} & forbidden
    rank_reads = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rank"]
    assert all(isinstance(n.value, ast.Name) and n.value.id == "alternative" for n in rank_reads)
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(
        name.startswith(
            (
                "__future__",
                "collections",
                "dataclasses",
                "calliope.domain",
                "calliope.errors",
                "calliope.services.explanation.claim_validator",
            )
        )
        for name in imports
    )
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {
        "PythonChessAdapter",
        "ChessRulesPort",
        "StockfishAdapter",
        "CounterfactualAnalyzer",
        "GoodMoveExplainer",
        "PositionFactExtractor",
        "BoardDeltaAnalyzer",
        "TacticalDetector",
        "BasePieceIdentityMap",
    }


@pytest.mark.parametrize("module", [claim_builder, claim_validator])
def test_claim_services_cannot_read_raw_p9_results(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not (names | imported) & {
        "GoodMoveExplanationResult",
        "GoodMoveBenefitResult",
        "GoodMoveBenefitStatus",
    }


def test_san_only_entity_difference_is_canonical_identity():
    bundle, claim, _, _ = package(forces)
    sanned = replace(claim.subject, move=replace(claim.subject.move, san="Ra1+"))
    changed = replace(claim, subject=sanned)
    assert ClaimValidator().validate_good_move(bundle, (changed,)) == (changed,)
