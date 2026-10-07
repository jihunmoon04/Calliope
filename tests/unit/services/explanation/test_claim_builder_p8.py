import ast
from dataclasses import replace
from pathlib import Path

import pytest
from _p8_claim_scenarios import (
    Kind,
    claims,
    defender,
    engine_mate,
    evidence,
    exact_mate,
    fork,
    group_of,
    knight,
    mate,
    only_kind,
    records_of,
)

from calliope.domain.analysis import GoodMoveBenefitKind
from calliope.domain.chess import Color
from calliope.domain.explanation import (
    BoardFactEvidence,
    ClaimConfidence,
    ClaimPredicate,
    ClaimScope,
    EvidenceBundle,
    EvidenceSourceFamily,
    MotifEvidence,
    VariationEvidence,
    base_frame_piece_entity,
    claim_entity_sort_key,
)
from calliope.errors import ExplanationClaimError, IncompatibleClaimEvidenceError
from calliope.services.explanation import claim_builder as claim_builder_module
from calliope.services.explanation import claim_validator as claim_validator_module
from calliope.services.explanation.claim_builder import ClaimBuilder
from calliope.services.explanation.claim_validator import ClaimValidator

_P = ClaimPredicate
_C = ClaimConfidence

CASES = [
    (knight, Kind.NEWLY_HANGING_PIECE, _P.LEAVES_PIECE_HANGING, _C.ENGINE_VERIFIED),
    (defender, Kind.REMOVED_DEFENDER, _P.REMOVES_DEFENDER, _C.ENGINE_VERIFIED),
    (fork, Kind.FORK_ALLOWED, _P.ALLOWS_FORK, _C.ENGINE_VERIFIED),
    (exact_mate, Kind.MATE_ALLOWED, _P.ALLOWS_CHECKMATE, _C.EXACT),
    (engine_mate, Kind.MATE_ALLOWED, _P.ALLOWS_CHECKMATE, _C.ENGINE_VERIFIED),
    (knight, Kind.MATERIAL_LOSS_LINE, _P.ALLOWS_MATERIAL_LOSS, _C.ENGINE_VERIFIED),
]


def _claim_for(bundle, group):
    (claim,) = [c for c in claims(bundle) if c.evidence_ids[0] == group.evidence_ids[0]]
    return claim


@pytest.mark.parametrize(("make", "kind", "predicate", "confidence"), CASES)
def test_every_p8_mapping(make, kind, predicate, confidence):
    bundle = evidence(make())
    group = group_of(bundle, kind)
    claim = _claim_for(bundle, group)

    assert claim.predicate is predicate
    assert claim.confidence is confidence
    assert claim.scope is ClaimScope.LOCAL
    assert claim.subject is group.played_move
    assert claim.base_position_id == bundle.base_position_id
    assert claim.importance is None

    pieces = [base_frame_piece_entity(bundle.base_position_id, b) for b in group.source_subject]
    expected = sorted([*pieces, group.response], key=claim_entity_sort_key)
    assert list(claim.objects) == expected
    assert group.comparator_move not in claim.objects

    owned = records_of(bundle, group)
    if confidence is _C.EXACT:
        actual = group.required_probe_results[0].probe
        assert claim.evidence_ids == tuple(
            r.evidence_id
            for r in owned
            if isinstance(r, (BoardFactEvidence, MotifEvidence))
            or (isinstance(r, VariationEvidence) and r.probe == actual)
        )
    else:
        assert claim.evidence_ids == group.evidence_ids


def test_exact_mate_claim_is_deterministic_local_fact():
    bundle = evidence(exact_mate())
    (claim,) = claims(bundle)
    group = bundle.groups[0]
    referenced = {r.evidence_id: r for r in bundle.evidence}
    types = [type(referenced[eid]) for eid in claim.evidence_ids]
    assert types == [BoardFactEvidence, MotifEvidence, VariationEvidence]
    assert claim.confidence is _C.EXACT and claim.confidence is not _C.FORCED
    (king,) = [o for o in claim.objects if hasattr(o, "base_ref")]
    assert king.base_ref.piece_type.value == "king" and king.base_ref.color is Color.WHITE
    assert group.response in claim.objects


def test_one_claim_per_group_in_predicate_then_object_order():
    for make in (knight, defender, fork, exact_mate, engine_mate):
        bundle = evidence(make())
        built = claims(bundle)
        assert len(built) == len(bundle.groups)
        keys = [
            (list(_P).index(c.predicate), tuple(claim_entity_sort_key(o) for o in c.objects))
            for c in built
        ]
        assert keys == sorted(keys)
        assert [c.claim_id for c in built] == [f"cl_{n:03d}" for n in range(1, len(built) + 1)]
        assert all(c.importance is None for c in built)


def test_reversed_group_order_gives_identical_claims():
    bundle = evidence(defender())
    reversed_bundle = EvidenceBundle(
        bundle.base_position_id, bundle.evidence, tuple(reversed(bundle.groups))
    )
    forward, backward = claims(bundle), claims(reversed_bundle)
    assert forward == backward
    assert repr(forward) == repr(backward)


def test_independent_runs_are_deterministic():
    assert repr(claims(evidence(fork()))) == repr(claims(evidence(fork())))


def test_engine_score_values_do_not_change_claim_structure():
    two = claims(evidence(engine_mate(mate(Color.BLACK, 2))))
    five = claims(evidence(engine_mate(mate(Color.BLACK, 5))))
    assert two == five


def test_same_punishment_probe_keeps_removes_defender_local():
    bundle = evidence(only_kind(defender(), Kind.REMOVED_DEFENDER))
    group = bundle.groups[0]
    assert len(group.required_probe_results) == 3
    (claim,) = claims(bundle)
    assert (claim.predicate, claim.confidence, claim.scope) == (
        _P.REMOVES_DEFENDER,
        _C.ENGINE_VERIFIED,
        ClaimScope.LOCAL,
    )


def test_empty_bundle_builds_no_claims():
    bundle = EvidenceBundle("pos_base", (), ())
    assert ClaimBuilder().build_bad_move(bundle) == ()
    assert ClaimValidator().validate_bad_move(bundle, ()) == ()


def test_builder_rejects_non_bundle_input():
    with pytest.raises(ExplanationClaimError, match="EvidenceBundle"):
        ClaimBuilder().build_bad_move(knight())


def test_good_move_family_bundle_rejected():
    bundle = evidence(only_kind(knight(), Kind.NEWLY_HANGING_PIECE))
    p9 = replace(
        bundle.groups[0],
        source_family=EvidenceSourceFamily.GOOD_MOVE_BENEFIT,
        source_kind=GoodMoveBenefitKind.MATERIAL_THREAT,
    )
    foreign = EvidenceBundle(bundle.base_position_id, bundle.evidence, (p9,))
    with pytest.raises(IncompatibleClaimEvidenceError, match="BAD_MOVE_CAUSE"):
        ClaimBuilder().build_bad_move(foreign)


def test_missing_source_piece_is_not_reconstructed():
    bundle = evidence(only_kind(knight(), Kind.NEWLY_HANGING_PIECE))
    for record in bundle.evidence:
        if hasattr(record, "pieces"):
            object.__setattr__(record, "pieces", ())
    with pytest.raises(IncompatibleClaimEvidenceError, match="0 retained presentations"):
        claims(bundle)


def test_builder_output_always_passes_validator():
    for make in (knight, defender, fork, exact_mate, engine_mate):
        bundle = evidence(make())
        built = claims(bundle)
        assert ClaimValidator().validate_bad_move(bundle, built) is built


# ---- source guards -----------------------------------------------------------------------------


MODULES = [claim_builder_module, claim_validator_module]


def _tree(module):
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))


@pytest.mark.parametrize("module", MODULES)
def test_no_raw_p8_result_input(module):
    names = {n.id for n in ast.walk(_tree(module)) if isinstance(n, ast.Name)}
    imported = {
        alias.name
        for n in ast.walk(_tree(module))
        if isinstance(n, ast.ImportFrom)
        for alias in n.names
    }
    raw = {"BadMoveExplanationResult", "BadMoveCauseResult", "BadMoveCauseStatus"}
    assert not (names | imported) & raw


@pytest.mark.parametrize("module", MODULES)
def test_no_score_reads(module):
    attrs = {n.attr for n in ast.walk(_tree(module)) if isinstance(n, ast.Attribute)}
    assert not attrs & {
        "score",
        "scores",
        "cp",
        "mate",
        "wdl",
        "rank",
        "cp_loss",
        "expected_score_loss",
        "best_score",
        "played_score",
        "best_line",
        "lines",
        "material_delta",
        "stable_deficit",
        "stable_at_ply",
    }


@pytest.mark.parametrize("module", MODULES)
def test_no_chess_or_engine_execution(module):
    tree = _tree(module)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    allowed = (
        "__future__",
        "collections",
        "dataclasses",
        "calliope.domain",
        "calliope.errors",
        "calliope.services.explanation.claim_validator",
    )
    assert all(name.startswith(allowed) for name in modules), modules
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {
        "PythonChessAdapter",
        "ChessRulesPort",
        "StockfishAdapter",
        "CounterfactualAnalyzer",
        "PositionFactExtractor",
        "BoardDeltaAnalyzer",
        "TacticalDetector",
        "BasePieceIdentityMap",
        "EvidenceBuilder",
    }
