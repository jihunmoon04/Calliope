import ast
from dataclasses import replace
from pathlib import Path

import pytest
from _p9_preservation_claim_scenarios import (
    SCENARIOS,
    Kind,
    claims,
    evidence,
    mate_all,
    mate_subset,
    material_all,
    material_subset,
    of_type,
    package,
)

from calliope.domain.chess import ChessMove
from calliope.domain.explanation import (
    BoardFactEvidence,
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    EvidenceBundle,
    MoveClaimEntity,
    PieceClaimEntity,
    claim_entity_sort_key,
)
from calliope.services.explanation import claim_builder, claim_validator, evidence_builder
from calliope.services.explanation.claim_validator import ClaimValidator


@pytest.mark.parametrize("make", SCENARIOS)
def test_preservation_semantics_and_exact_failed_object_set(make):
    bundle, claim, group, records = package(make)
    expected = (
        ClaimPredicate.AVOIDS_REPRESENTATIVE_MATE_FAILURE
        if group.source_kind is Kind.PREVENTS_MATE
        else ClaimPredicate.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS
    )
    assert (claim.predicate, claim.confidence, claim.scope) == (
        expected,
        ClaimConfidence.ENGINE_VERIFIED,
        ClaimScope.REPRESENTATIVE_ALTERNATIVES,
    )
    assert claim.subject is group.played_move
    assert claim.evidence_ids == group.evidence_ids
    assert claim.importance is None
    assert [p.base_ref for p in claim.objects if isinstance(p, PieceClaimEntity)] == list(
        group.source_subject
    )
    move_objects = [o for o in claim.objects if isinstance(o, MoveClaimEntity)]
    assert {o.move.uci for o in move_objects} == {a.move.uci for a in group.failed_alternatives}
    assert all(o.position_id == bundle.base_position_id for o in move_objects)
    board = of_type(records, BoardFactEvidence)[0]
    assert all(any(o is m for m in board.moves) for o in move_objects)
    assert list(claim.objects) == sorted(claim.objects, key=claim_entity_sort_key)
    built = (claim,)
    assert ClaimValidator().validate_good_move(bundle, built) is built


@pytest.mark.parametrize("make", [mate_subset, material_subset])
def test_safe_representative_is_context_only(make):
    _, claim, group, _ = package(make)
    assert len(group.failed_alternatives) == 1 < len(group.representative_alternatives)
    assert len([o for o in claim.objects if isinstance(o, MoveClaimEntity)]) == 1
    assert claim.confidence is ClaimConfidence.ENGINE_VERIFIED


def test_two_real_supported_benefits_have_canonical_claims_and_global_ids():
    bundle = evidence(mate_all())
    built = claims(bundle)
    assert len(bundle.groups) == len(built) == 2
    assert [c.claim_id for c in built] == ["cl_001", "cl_002"]
    assert [c.predicate for c in built] == [
        ClaimPredicate.AVOIDS_REPRESENTATIVE_MATE_FAILURE,
        ClaimPredicate.AVOIDS_REPRESENTATIVE_MATERIAL_LOSS,
    ]
    assert claims(evidence(mate_all())) == built
    assert repr(claims(evidence(mate_all()))) == repr(built)
    reversed_groups = EvidenceBundle(bundle.base_position_id, bundle.evidence, bundle.groups[::-1])
    assert claims(reversed_groups) == built
    result = mate_all()
    assert claims(evidence(replace(result, benefits=result.benefits[::-1]))) == built


def semantic_claims(built):
    return tuple(
        (
            c.claim_id,
            claim_entity_sort_key(c.subject),
            c.predicate,
            c.confidence,
            c.scope,
            tuple(claim_entity_sort_key(o) for o in c.objects),
            c.evidence_ids,
        )
        for c in built
    )


def with_san(move):
    return replace(move, san="presentation only")


@pytest.mark.parametrize("make", [mate_all, material_all])
def test_san_only_source_changes_preserve_eligibility_binding_order_and_ids(make):
    original = make()
    alternatives = tuple(replace(a, move=with_san(a.move)) for a in original.alternatives)
    children = []
    for child in original.benefits:
        probes = tuple(
            replace(
                r, probe=replace(r.probe, intervention_move=with_san(r.probe.intervention_move))
            )
            for r in child.probe_results
        )
        materials = tuple(
            replace(
                m,
                probe=next(
                    r.probe
                    for r in probes
                    if r.probe.intervention_move.uci == m.probe.intervention_move.uci
                ),
            )
            for m in child.material_evidence
        )
        failed = tuple(
            replace(a, move=ChessMove(a.move.uci, "different failed presentation"))
            for a in child.failed_alternatives
        )
        children.append(
            replace(
                child,
                played_move=with_san(child.played_move),
                alternatives=alternatives,
                failed_alternatives=failed,
                probe_results=probes,
                material_evidence=materials,
            )
        )
    varied = replace(
        original,
        played_move=with_san(original.played_move),
        alternatives=alternatives,
        benefits=tuple(children),
    )
    original_bundle = evidence(original)
    varied_bundle = evidence(varied)
    assert semantic_claims(claims(original_bundle)) == semantic_claims(claims(varied_bundle))
    assert [r.evidence_id for r in original_bundle.evidence] == [
        r.evidence_id for r in varied_bundle.evidence
    ]
    assert [type(r) for r in original_bundle.evidence] == [type(r) for r in varied_bundle.evidence]
    for group, child in zip(varied_bundle.groups, varied.benefits, strict=True):
        assert group.representative_alternatives is child.alternatives
        assert group.required_probe_results is child.probe_results
        assert group.failed_alternatives is child.failed_alternatives
    # Frozen values retain presentation verbatim; full repr/equality may differ.
    assert repr(original_bundle) != repr(varied_bundle)


def test_parent_played_san_only_does_not_affect_child_binding():
    result = material_all()
    varied = replace(result, played_move=with_san(result.played_move))
    assert evidence(varied) == evidence(result)


def test_failed_membership_ignores_san_without_promoting_safe_alternative():
    result = mate_subset()
    child = result.benefits[0]
    failed = tuple(replace(a, move=with_san(a.move)) for a in child.failed_alternatives)
    varied = replace(result, benefits=(replace(child, failed_alternatives=failed),))
    assert claims(evidence(varied))


@pytest.mark.parametrize("module", [evidence_builder, claim_builder, claim_validator])
def test_no_score_reads_or_chess_execution(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {
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


def test_no_exhaustive_predicate_or_confidence_added():
    assert {p.name for p in ClaimPredicate} == {
        "LEAVES_PIECE_HANGING",
        "REMOVES_DEFENDER",
        "ALLOWS_FORK",
        "ALLOWS_CHECKMATE",
        "ALLOWS_MATERIAL_LOSS",
        "FORCES_RESPONSE",
        "DELIVERS_CHECKMATE",
        "LEADS_TO_MATE",
        "WINS_MATERIAL",
        "THREATENS_MATE_IF_IGNORED",
        "THREATENS_MATERIAL_IF_IGNORED",
        "AVOIDS_REPRESENTATIVE_MATE_FAILURE",
        "AVOIDS_REPRESENTATIVE_MATERIAL_LOSS",
    }
    assert {c.name for c in ClaimConfidence} == {"EXACT", "ENGINE_VERIFIED", "FORCED"}


def test_failed_metadata_rank_order_and_claim_object_order_are_separate():
    from _p9_preservation_claim_scenarios import MATE_NOW, QUEEN, SAFE, explain, only_kind

    result = only_kind(
        explain(QUEEN, ("h2h3", "d1b1", "d1a1"), {**SAFE, **MATE_NOW}), Kind.PREVENTS_MATE
    )
    bundle = evidence(result)
    (group,) = bundle.groups
    (claim,) = claims(bundle)
    assert [a.move.uci for a in group.failed_alternatives] == ["d1b1", "d1a1"]
    assert [o.move.uci for o in claim.objects if isinstance(o, MoveClaimEntity)] == ["d1a1", "d1b1"]
    assert ClaimValidator().validate_good_move(bundle, (claim,)) == (claim,)
