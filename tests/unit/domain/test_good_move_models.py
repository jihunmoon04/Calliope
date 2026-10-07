from dataclasses import FrozenInstanceError, fields, replace

import pytest

import calliope
from calliope.domain import analysis
from calliope.domain.analysis import (
    AlternativeScope,
    BasePieceRef,
    CounterfactualProbe,
    GoodMoveBenefitKind,
    GoodMoveBenefitResult,
    GoodMoveBenefitStatus,
    GoodMoveExplanationResult,
    GoodMoveExplanationStatus,
    GoodMoveMode,
    MateEvidenceLevel,
    MaterialLineEvidence,
    ProbeKind,
    RepresentativeAlternative,
    bad_move,
    good_move,
)
from calliope.domain.chess import ChessMove, Color, PieceType, PositionSnapshot
from calliope.errors import (
    BadMoveExplanationError,
    CalliopeError,
    GoodMoveExplanationError,
    IncompatibleGoodMoveContextError,
)

BASE = PositionSnapshot.create(
    fen="8/8/8/8/8/8/8/K6k w - - 0 1",
    ply=0,
    side_to_move=Color.WHITE,
    castling_rights="-",
    en_passant_square=None,
    halfmove_clock=0,
    fullmove_number=1,
)
PLAYED = ChessMove("a1a2")
SUBJECT = BasePieceRef(Color.WHITE, PieceType.KING, "a1")
OTHER_SUBJECT = BasePieceRef(Color.WHITE, PieceType.PAWN, "e2")
A1 = RepresentativeAlternative(1, ChessMove("a1b1"))
A2 = RepresentativeAlternative(3, ChessMove("a1b2"))
ALTERNATIVES = (A1, A2)
SCOPE = AlternativeScope.REPRESENTATIVE_TOP_ENGINE_LINES
MATERIAL = MaterialLineEvidence(
    probe=CounterfactualProbe(ProbeKind.REFUTATION, BASE, PLAYED),
    material_delta=100,
    stable_at_ply=4,
)


def benefit(**changes) -> GoodMoveBenefitResult:
    values = {
        "kind": GoodMoveBenefitKind.FORCES_RESPONSE,
        "status": GoodMoveBenefitStatus.INCONCLUSIVE,
        "mode": GoodMoveMode.STRONG_MOVE,
        "subject": (SUBJECT,),
        "base_position_id": BASE.position_id,
        "played_move": PLAYED,
        "alternatives": ALTERNATIVES,
    }
    values.update(changes)
    return GoodMoveBenefitResult(**values)


def result(**changes) -> GoodMoveExplanationResult:
    values = {
        "status": GoodMoveExplanationStatus.INCONCLUSIVE,
        "base_position_id": BASE.position_id,
        "played_move": PLAYED,
        "mode": GoodMoveMode.STRONG_MOVE,
        "alternatives": ALTERNATIVES,
        "alternative_scope": SCOPE,
    }
    values.update(changes)
    return GoodMoveExplanationResult(**values)


@pytest.mark.parametrize(
    ("enum", "names"),
    [
        (GoodMoveExplanationStatus, ("SUPPORTED", "REFUTED", "INCONCLUSIVE", "NOT_APPLICABLE")),
        (GoodMoveBenefitStatus, ("SUPPORTED", "REFUTED", "INCONCLUSIVE")),
        (GoodMoveMode, ("STRONG_MOVE", "ONLY_MOVE_CANDIDATE")),
        (
            GoodMoveBenefitKind,
            (
                "FORCES_RESPONSE",
                "MATE_THREAT",
                "MATERIAL_THREAT",
                "PREVENTS_MATE",
                "PREVENTS_MATERIAL_LOSS",
            ),
        ),
        (AlternativeScope, ("REPRESENTATIVE_TOP_ENGINE_LINES",)),
    ],
)
def test_frozen_enum_vocabulary_and_declaration_order(enum, names):
    assert tuple(enum.__members__) == names
    assert tuple(member.value for member in enum) == tuple(name.lower() for name in names)


@pytest.mark.parametrize("rank", [0, -1, -10])
def test_alternative_rejects_non_positive_rank(rank):
    with pytest.raises(ValueError, match="rank must be at least 1"):
        RepresentativeAlternative(rank, PLAYED)


def test_alternative_retains_selection_identity_without_engine_scores():
    assert tuple(field.name for field in fields(RepresentativeAlternative)) == ("rank", "move")
    assert A1.rank == 1 and A1.move.uci == "a1b1"
    assert RepresentativeAlternative(10, PLAYED).rank == 10


@pytest.mark.parametrize("value", [A1, benefit(), result()])
def test_records_are_frozen_and_slotted(value):
    assert not hasattr(value, "__dict__")
    field = fields(value)[0].name
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, getattr(value, field))


@pytest.mark.parametrize("factory", [benefit, result])
def test_non_empty_base_position_required(factory):
    with pytest.raises(ValueError, match="base_position_id must not be empty"):
        factory(base_position_id="")


@pytest.mark.parametrize("subject", [(), (SUBJECT, SUBJECT)])
def test_benefit_requires_non_empty_unique_subject(subject):
    with pytest.raises(ValueError, match="subject"):
        benefit(subject=subject)


def test_duplicate_affected_pieces_rejected():
    with pytest.raises(ValueError, match="affected_pieces"):
        benefit(affected_pieces=(SUBJECT, SUBJECT))


def test_piece_order_is_retained_without_policy_sorting():
    pieces = (OTHER_SUBJECT, SUBJECT)
    value = benefit(subject=pieces, affected_pieces=pieces)
    assert value.subject == pieces and value.affected_pieces == pieces


@pytest.mark.parametrize("factory", [benefit, result])
@pytest.mark.parametrize(
    ("alternatives", "message"),
    [
        ((A1, RepresentativeAlternative(1, A2.move)), "unique ranks"),
        ((A1, RepresentativeAlternative(2, ChessMove(A1.move.uci, "Kb1"))), "unique move UCIs"),
        ((A2, A1), "ascending rank"),
    ],
)
def test_alternatives_require_unique_rank_uci_and_retained_rank_order(
    factory, alternatives, message
):
    with pytest.raises(ValueError, match=message):
        factory(alternatives=alternatives)


def test_rank_gaps_and_empty_alternatives_are_representable():
    # Representative selections need not contain contiguous engine ranks.
    assert benefit().alternatives == ALTERNATIVES
    assert benefit(alternatives=()).alternatives == ()


@pytest.mark.parametrize(
    ("failed", "message"),
    [
        ((RepresentativeAlternative(2, A1.move),), "subset"),
        ((RepresentativeAlternative(1, A2.move),), "subset"),
        ((RepresentativeAlternative(4, ChessMove("a1c1")),), "subset"),
        ((A1, A1), "unique ranks"),
        ((A1, RepresentativeAlternative(1, A2.move)), "unique ranks"),
        ((A1, RepresentativeAlternative(2, ChessMove(A1.move.uci, "Kb1"))), "unique move UCIs"),
        ((A2, A1), "ascending rank"),
    ],
)
def test_failed_alternatives_require_sorted_unique_subset(failed, message):
    with pytest.raises(ValueError, match=message):
        benefit(failed_alternatives=failed)


def test_failed_membership_uses_rank_and_uci_without_san():
    failed = RepresentativeAlternative(A1.rank, ChessMove(A1.move.uci, "Kb1"))
    value = benefit(failed_alternatives=(failed,))
    assert value.failed_alternatives == (failed,)
    assert failed != A1  # SAN differs, while membership identity is the same.
    assert benefit(failed_alternatives=ALTERNATIVES).failed_alternatives == ALTERNATIVES


@pytest.mark.parametrize(
    "kind", [GoodMoveBenefitKind.PREVENTS_MATE, GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS]
)
def test_prevention_requires_only_move_candidate_mode(kind):
    with pytest.raises(ValueError, match="ONLY_MOVE_CANDIDATE"):
        benefit(kind=kind)
    assert benefit(kind=kind, mode=GoodMoveMode.ONLY_MOVE_CANDIDATE).kind is kind


@pytest.mark.parametrize("mode", list(GoodMoveMode))
@pytest.mark.parametrize(
    "kind",
    [
        GoodMoveBenefitKind.FORCES_RESPONSE,
        GoodMoveBenefitKind.MATE_THREAT,
        GoodMoveBenefitKind.MATERIAL_THREAT,
    ],
)
def test_forcing_and_threat_kinds_are_valid_in_both_modes(kind, mode):
    assert benefit(kind=kind, mode=mode).mode is mode


@pytest.mark.parametrize("level", list(MateEvidenceLevel))
@pytest.mark.parametrize(
    "kind",
    [
        GoodMoveBenefitKind.FORCES_RESPONSE,
        GoodMoveBenefitKind.MATERIAL_THREAT,
        GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS,
    ],
)
def test_mate_evidence_rejected_on_non_mate_benefits(kind, level):
    with pytest.raises(ValueError, match="only valid for mate benefits"):
        benefit(kind=kind, mode=GoodMoveMode.ONLY_MOVE_CANDIDATE, mate_evidence_level=level)


@pytest.mark.parametrize(
    "kind", [GoodMoveBenefitKind.MATE_THREAT, GoodMoveBenefitKind.PREVENTS_MATE]
)
def test_supported_mate_benefit_requires_evidence_level(kind):
    with pytest.raises(ValueError, match="supported mate benefit requires"):
        benefit(
            kind=kind, mode=GoodMoveMode.ONLY_MOVE_CANDIDATE, status=GoodMoveBenefitStatus.SUPPORTED
        )
    for level in MateEvidenceLevel:
        value = benefit(
            kind=kind,
            mode=GoodMoveMode.ONLY_MOVE_CANDIDATE,
            status=GoodMoveBenefitStatus.SUPPORTED,
            mate_evidence_level=level,
        )
        assert value.mate_evidence_level is level


@pytest.mark.parametrize("flag", [True, False])
def test_non_none_replayed_mate_flag_requires_evidence_level(flag):
    with pytest.raises(ValueError, match="replayed mate flag requires"):
        benefit(kind=GoodMoveBenefitKind.MATE_THREAT, replayed_pv_ends_in_checkmate=flag)
    value = benefit(
        kind=GoodMoveBenefitKind.MATE_THREAT,
        mate_evidence_level=MateEvidenceLevel.ENGINE_LINE,
        replayed_pv_ends_in_checkmate=flag,
    )
    assert value.replayed_pv_ends_in_checkmate is flag


@pytest.mark.parametrize(
    "kind", [GoodMoveBenefitKind.MATERIAL_THREAT, GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS]
)
def test_supported_material_benefit_requires_existing_material_evidence(kind):
    with pytest.raises(ValueError, match="supported material benefit requires"):
        benefit(
            kind=kind, mode=GoodMoveMode.ONLY_MOVE_CANDIDATE, status=GoodMoveBenefitStatus.SUPPORTED
        )
    value = benefit(
        kind=kind,
        mode=GoodMoveMode.ONLY_MOVE_CANDIDATE,
        status=GoodMoveBenefitStatus.SUPPORTED,
        material_evidence=(MATERIAL,),
    )
    assert value.material_evidence == (MATERIAL,)
    assert value.material_evidence[0] is MATERIAL


@pytest.mark.parametrize(
    "status", [GoodMoveBenefitStatus.REFUTED, GoodMoveBenefitStatus.INCONCLUSIVE]
)
@pytest.mark.parametrize(
    "kind",
    [
        GoodMoveBenefitKind.MATE_THREAT,
        GoodMoveBenefitKind.PREVENTS_MATE,
        GoodMoveBenefitKind.MATERIAL_THREAT,
        GoodMoveBenefitKind.PREVENTS_MATERIAL_LOSS,
    ],
)
def test_non_supported_benefits_can_retain_incomplete_evidence(kind, status):
    assert benefit(kind=kind, mode=GoodMoveMode.ONLY_MOVE_CANDIDATE, status=status)


def test_i0_does_not_evaluate_material_semantics():
    truncated = MaterialLineEvidence(MATERIAL.probe, material_delta=-100, stable_at_ply=None)
    value = benefit(
        kind=GoodMoveBenefitKind.MATERIAL_THREAT,
        status=GoodMoveBenefitStatus.SUPPORTED,
        material_evidence=(truncated,),
    )
    assert value.material_evidence == (truncated,)


@pytest.mark.parametrize("scope", [None, "exhaustive"])
def test_benefit_scope_cannot_imply_exhaustive_alternatives(scope):
    with pytest.raises(ValueError, match="representative alternative scope"):
        benefit(alternative_scope=scope)


@pytest.mark.parametrize("status", list(GoodMoveExplanationStatus))
def test_literal_only_move_proof_is_explicitly_forbidden_for_every_status(status):
    with pytest.raises(ValueError, match="literal_only_move_proven must always be False"):
        result(status=status, literal_only_move_proven=True)


def test_literal_only_move_guard_requires_actual_false():
    for invalid in (None, 0, 1):
        with pytest.raises(ValueError, match="literal_only_move_proven"):
            result(literal_only_move_proven=invalid)
    assert result(mode=GoodMoveMode.ONLY_MOVE_CANDIDATE).literal_only_move_proven is False


def not_applicable(**changes):
    values = {
        "status": GoodMoveExplanationStatus.NOT_APPLICABLE,
        "base_position_id": BASE.position_id,
        "played_move": PLAYED,
    }
    values.update(changes)
    return GoodMoveExplanationResult(**values)


def test_not_applicable_has_empty_shape():
    value = not_applicable()
    assert value.mode is None
    assert value.alternatives == ()
    assert value.alternative_scope is None
    assert value.benefits == ()
    assert value.literal_only_move_proven is False


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": GoodMoveMode.STRONG_MOVE},
        {"alternatives": (A1,)},
        {"alternative_scope": SCOPE},
        {"benefits": (benefit(),)},
    ],
)
def test_not_applicable_rejects_eligible_metadata(changes):
    with pytest.raises(ValueError, match="NOT_APPLICABLE"):
        not_applicable(**changes)


@pytest.mark.parametrize(
    "status",
    [
        GoodMoveExplanationStatus.SUPPORTED,
        GoodMoveExplanationStatus.REFUTED,
        GoodMoveExplanationStatus.INCONCLUSIVE,
    ],
)
def test_every_eligible_status_requires_mode_and_representative_scope(status):
    with pytest.raises(ValueError, match="eligible result requires mode"):
        result(status=status, mode=None)
    for scope in (None, "exhaustive"):
        with pytest.raises(ValueError, match="eligible result requires representative"):
            result(status=status, alternative_scope=scope)


@pytest.mark.parametrize("mode", list(GoodMoveMode))
def test_eligible_inconclusive_without_alternatives_or_benefits_is_valid(mode):
    value = result(mode=mode, alternatives=())
    assert value.status is GoodMoveExplanationStatus.INCONCLUSIVE
    assert value.alternatives == () and value.benefits == ()
    assert value.alternative_scope is SCOPE and value.literal_only_move_proven is False


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"base_position_id": "other-position"}, "another base position"),
        ({"played_move": ChessMove("a1b2")}, "played move differs"),
        ({"mode": GoodMoveMode.ONLY_MOVE_CANDIDATE}, "mode differs"),
        ({"alternatives": (A1,)}, "alternatives differ"),
        ({"alternatives": (RepresentativeAlternative(2, A1.move), A2)}, "alternatives differ"),
        (
            {"alternatives": (RepresentativeAlternative(1, ChessMove("a1c1")), A2)},
            "alternatives differ",
        ),
    ],
)
def test_aggregate_rejects_benefit_from_different_context(changes, message):
    with pytest.raises(ValueError, match=message):
        result(benefits=(benefit(**changes),))


def test_aggregate_played_move_binding_ignores_san():
    record = benefit(played_move=ChessMove(PLAYED.uci, "Ka2"))
    assert result(benefits=(record,)).benefits == (record,)


def test_aggregate_rejects_duplicate_benefit_candidates():
    first = benefit(failed_alternatives=(A1,))
    second = benefit(failed_alternatives=(A2,))
    with pytest.raises(ValueError, match="duplicate benefit candidate"):
        result(benefits=(first, second))
    combined = benefit(failed_alternatives=ALTERNATIVES)
    assert result(benefits=(combined,)).benefits == (combined,)


def test_distinct_kind_or_subject_benefits_and_their_order_are_retained():
    first = benefit(kind=GoodMoveBenefitKind.MATE_THREAT)
    second = benefit()
    third = benefit(subject=(OTHER_SUBJECT,))
    records = (first, second, third)
    assert result(benefits=records).benefits == records


def test_supported_aggregate_requires_supported_benefit_and_allows_mixed_statuses():
    supported = benefit(status=GoodMoveBenefitStatus.SUPPORTED)
    refuted = benefit(kind=GoodMoveBenefitKind.MATE_THREAT, status=GoodMoveBenefitStatus.REFUTED)
    incomplete = benefit(kind=GoodMoveBenefitKind.MATERIAL_THREAT)
    for records in ((), (incomplete,), (refuted,)):
        with pytest.raises(ValueError, match="requires a supported benefit"):
            result(status=GoodMoveExplanationStatus.SUPPORTED, benefits=records)
    value = result(
        status=GoodMoveExplanationStatus.SUPPORTED, benefits=(supported, refuted, incomplete)
    )
    assert value.benefits == (supported, refuted, incomplete)


def test_refuted_aggregate_requires_non_empty_wholly_refuted_benefits():
    refuted = benefit(status=GoodMoveBenefitStatus.REFUTED)
    assert result(status=GoodMoveExplanationStatus.REFUTED, benefits=(refuted,))
    other = benefit(kind=GoodMoveBenefitKind.MATE_THREAT)
    supported = benefit(status=GoodMoveBenefitStatus.SUPPORTED)
    for records in ((), (other,), (refuted, other), (supported,)):
        with pytest.raises(ValueError, match="wholly refuted"):
            result(status=GoodMoveExplanationStatus.REFUTED, benefits=records)


def test_inconclusive_cannot_hide_supported_or_wholly_refuted_benefits():
    supported = benefit(status=GoodMoveBenefitStatus.SUPPORTED)
    refuted = benefit(status=GoodMoveBenefitStatus.REFUTED)
    incomplete = benefit(kind=GoodMoveBenefitKind.MATE_THREAT)
    with pytest.raises(ValueError, match="must not contain a supported benefit"):
        result(benefits=(supported, incomplete))
    with pytest.raises(ValueError, match="require a REFUTED aggregate"):
        result(benefits=(refuted,))
    assert result(benefits=(refuted, incomplete)).benefits == (refuted, incomplete)
    assert result().benefits == ()


def test_shared_p8_evidence_types_are_reused_without_refactoring():
    for name in ("BasePieceRef", "MaterialLineEvidence", "MateEvidenceLevel"):
        assert getattr(good_move, name) is getattr(bad_move, name) is getattr(analysis, name)


def test_p9_exports_are_internal_only():
    for name in (
        "AlternativeScope",
        "GoodMoveBenefitKind",
        "GoodMoveBenefitResult",
        "GoodMoveBenefitStatus",
        "GoodMoveExplanationResult",
        "GoodMoveExplanationStatus",
        "GoodMoveMode",
        "RepresentativeAlternative",
    ):
        assert name in analysis.__all__
        assert getattr(analysis, name) is getattr(good_move, name)
        assert name not in calliope.__all__
        assert not hasattr(calliope, name)


def test_p9_error_hierarchy_is_separate_from_p8():
    assert GoodMoveExplanationError.__bases__ == (CalliopeError,)
    assert IncompatibleGoodMoveContextError.__bases__ == (GoodMoveExplanationError,)
    error = IncompatibleGoodMoveContextError("incompatible P9 context")
    assert isinstance(error, CalliopeError)
    assert not isinstance(error, BadMoveExplanationError)
    assert str(error) == "incompatible P9 context"


def test_frozen_records_validate_replacements_without_mutating_originals():
    original = result()
    with pytest.raises(ValueError, match="literal_only_move_proven"):
        replace(original, literal_only_move_proven=True)
    assert original.literal_only_move_proven is False
    record = benefit()
    with pytest.raises(ValueError, match="ascending rank"):
        replace(record, alternatives=tuple(reversed(ALTERNATIVES)))
    assert record.alternatives == ALTERNATIVES
