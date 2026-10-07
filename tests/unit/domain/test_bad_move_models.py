import pytest

from calliope.domain.analysis import (
    BadMoveCauseKind,
    BadMoveCauseResult,
    BadMoveCauseStatus,
    BadMoveExplanationResult,
    BadMoveExplanationStatus,
    BasePieceRef,
    CounterfactualProbe,
    MateEvidenceLevel,
    MaterialLineEvidence,
    ProbeKind,
)
from calliope.domain.chess import ChessMove, Color, PieceType, PositionSnapshot
from calliope.errors import (
    BadMoveExplanationError,
    CalliopeError,
    IncompatibleBadMoveContextError,
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
COMPARATOR = ChessMove("a1b1")
SUBJECT = BasePieceRef(Color.WHITE, PieceType.QUEEN, "d1")


def cause(
    status: BadMoveCauseStatus,
    *,
    kind: BadMoveCauseKind = BadMoveCauseKind.NEWLY_HANGING_PIECE,
) -> BadMoveCauseResult:
    return BadMoveCauseResult(
        kind=kind,
        status=status,
        subject=(SUBJECT,),
        base_position_id=BASE.position_id,
        played_move=PLAYED,
        comparator_move=COMPARATOR,
    )


def result(
    status: BadMoveExplanationStatus,
    causes: tuple[BadMoveCauseResult, ...] = (),
) -> BadMoveExplanationResult:
    return BadMoveExplanationResult(
        status=status,
        base_position_id=BASE.position_id,
        played_move=PLAYED,
        comparator_move=COMPARATOR,
        causes=causes,
    )


def test_base_piece_ref_validates_base_square() -> None:
    with pytest.raises(ValueError, match="invalid square"):
        BasePieceRef(Color.WHITE, PieceType.KNIGHT, "z9")


def test_material_line_evidence_reports_only_stable_deficits() -> None:
    probe = CounterfactualProbe(ProbeKind.REFUTATION, BASE, PLAYED)

    evidence = MaterialLineEvidence(probe=probe, material_delta=-320, stable_at_ply=4)
    assert evidence.stable_deficit == 320
    assert evidence.stable_at_ply == 4

    # Comparator lines with no loss or a gain must be representable as measured evidence.
    assert MaterialLineEvidence(probe, material_delta=0, stable_at_ply=2).stable_deficit is None
    assert MaterialLineEvidence(probe, material_delta=100, stable_at_ply=2).stable_deficit is None
    # A truncated line keeps its measurement but establishes no stable deficit.
    truncated = MaterialLineEvidence(probe, material_delta=-900, stable_at_ply=None)
    assert truncated.stable_deficit is None

    with pytest.raises(ValueError, match="non-negative"):
        MaterialLineEvidence(probe=probe, material_delta=-320, stable_at_ply=-1)
    with pytest.raises(ValueError, match="checkmate endpoint"):
        MaterialLineEvidence(
            probe=probe, material_delta=-320, stable_at_ply=None, terminal_checkmate=True
        )


def test_cause_requires_distinct_comparator_and_base_position() -> None:
    with pytest.raises(ValueError, match="comparator must differ"):
        BadMoveCauseResult(
            kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
            status=BadMoveCauseStatus.INCONCLUSIVE,
            subject=(SUBJECT,),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=ChessMove(PLAYED.uci),
        )
    with pytest.raises(ValueError, match="base_position_id"):
        BadMoveCauseResult(
            kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
            status=BadMoveCauseStatus.INCONCLUSIVE,
            subject=(SUBJECT,),
            base_position_id="",
            played_move=PLAYED,
            comparator_move=COMPARATOR,
        )


def test_cause_rejects_duplicate_affected_pieces() -> None:
    with pytest.raises(ValueError, match="affected_pieces"):
        BadMoveCauseResult(
            kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
            status=BadMoveCauseStatus.INCONCLUSIVE,
            subject=(SUBJECT,),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=COMPARATOR,
            affected_pieces=(SUBJECT, SUBJECT),
        )


def test_supported_mate_requires_evidence_level() -> None:
    king = BasePieceRef(Color.WHITE, PieceType.KING, "a1")

    def mate(status: BadMoveCauseStatus, level: MateEvidenceLevel | None) -> BadMoveCauseResult:
        return BadMoveCauseResult(
            kind=BadMoveCauseKind.MATE_ALLOWED,
            status=status,
            subject=(king,),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=COMPARATOR,
            mate_evidence_level=level,
        )

    with pytest.raises(ValueError, match="requires mate_evidence_level"):
        mate(BadMoveCauseStatus.SUPPORTED, None)
    assert mate(BadMoveCauseStatus.SUPPORTED, MateEvidenceLevel.EXACT_IMMEDIATE)
    assert mate(BadMoveCauseStatus.SUPPORTED, MateEvidenceLevel.ENGINE_LINE)
    assert mate(BadMoveCauseStatus.INCONCLUSIVE, None).mate_evidence_level is None


def test_cause_requires_non_empty_unique_subject() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        BadMoveCauseResult(
            kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
            status=BadMoveCauseStatus.INCONCLUSIVE,
            subject=(),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=COMPARATOR,
        )

    with pytest.raises(ValueError, match="duplicate"):
        BadMoveCauseResult(
            kind=BadMoveCauseKind.FORK_ALLOWED,
            status=BadMoveCauseStatus.INCONCLUSIVE,
            subject=(SUBJECT, SUBJECT),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=COMPARATOR,
        )


def test_mate_evidence_is_restricted_to_mate_cause() -> None:
    with pytest.raises(ValueError, match="only valid for MATE_ALLOWED"):
        BadMoveCauseResult(
            kind=BadMoveCauseKind.MATERIAL_LOSS_LINE,
            status=BadMoveCauseStatus.SUPPORTED,
            subject=(SUBJECT,),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=COMPARATOR,
            mate_evidence_level=MateEvidenceLevel.ENGINE_LINE,
        )

    with pytest.raises(ValueError, match="requires mate_evidence_level"):
        BadMoveCauseResult(
            kind=BadMoveCauseKind.MATE_ALLOWED,
            status=BadMoveCauseStatus.SUPPORTED,
            subject=(BasePieceRef(Color.WHITE, PieceType.KING, "a1"),),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=COMPARATOR,
            replayed_pv_ends_in_checkmate=True,
        )


def test_supported_aggregate_requires_at_least_one_supported_cause() -> None:
    supported = cause(BadMoveCauseStatus.SUPPORTED)
    inconclusive = cause(
        BadMoveCauseStatus.INCONCLUSIVE,
        kind=BadMoveCauseKind.MATERIAL_LOSS_LINE,
    )

    aggregate = result(BadMoveExplanationStatus.SUPPORTED, (supported, inconclusive))
    assert aggregate.status is BadMoveExplanationStatus.SUPPORTED

    with pytest.raises(ValueError, match="requires a supported cause"):
        result(BadMoveExplanationStatus.SUPPORTED, (inconclusive,))


def test_refuted_aggregate_requires_one_or_more_wholly_refuted_causes() -> None:
    refuted = cause(BadMoveCauseStatus.REFUTED)
    assert result(BadMoveExplanationStatus.REFUTED, (refuted,)).causes == (refuted,)

    with pytest.raises(ValueError, match="wholly refuted"):
        result(BadMoveExplanationStatus.REFUTED)

    with pytest.raises(ValueError, match="wholly refuted"):
        result(
            BadMoveExplanationStatus.REFUTED,
            (refuted, cause(BadMoveCauseStatus.INCONCLUSIVE, kind=BadMoveCauseKind.FORK_ALLOWED)),
        )


def test_inconclusive_aggregate_cannot_hide_supported_or_wholly_refuted_causes() -> None:
    inconclusive = cause(BadMoveCauseStatus.INCONCLUSIVE)
    assert result(BadMoveExplanationStatus.INCONCLUSIVE).causes == ()
    assert result(BadMoveExplanationStatus.INCONCLUSIVE, (inconclusive,)).causes == (inconclusive,)

    with pytest.raises(ValueError, match="must not contain a supported cause"):
        result(
            BadMoveExplanationStatus.INCONCLUSIVE,
            (cause(BadMoveCauseStatus.SUPPORTED),),
        )

    with pytest.raises(ValueError, match="require a REFUTED"):
        result(
            BadMoveExplanationStatus.INCONCLUSIVE,
            (cause(BadMoveCauseStatus.REFUTED),),
        )


def test_not_applicable_aggregate_contains_no_causes() -> None:
    assert result(BadMoveExplanationStatus.NOT_APPLICABLE).causes == ()

    with pytest.raises(ValueError, match="must not contain causes"):
        result(
            BadMoveExplanationStatus.NOT_APPLICABLE,
            (cause(BadMoveCauseStatus.REFUTED),),
        )


def test_aggregate_rejects_cause_bound_to_different_context() -> None:
    other = BadMoveCauseResult(
        kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
        status=BadMoveCauseStatus.REFUTED,
        subject=(SUBJECT,),
        base_position_id="pos_other",
        played_move=PLAYED,
        comparator_move=COMPARATOR,
    )
    with pytest.raises(ValueError, match="another base position"):
        result(BadMoveExplanationStatus.REFUTED, (other,))


def test_aggregate_rejects_cause_with_different_played_or_comparator_move() -> None:
    other_played = BadMoveCauseResult(
        kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
        status=BadMoveCauseStatus.REFUTED,
        subject=(SUBJECT,),
        base_position_id=BASE.position_id,
        played_move=ChessMove("a1b2"),
        comparator_move=COMPARATOR,
    )
    with pytest.raises(ValueError, match="played move differs"):
        result(BadMoveExplanationStatus.REFUTED, (other_played,))

    other_comparator = BadMoveCauseResult(
        kind=BadMoveCauseKind.NEWLY_HANGING_PIECE,
        status=BadMoveCauseStatus.REFUTED,
        subject=(SUBJECT,),
        base_position_id=BASE.position_id,
        played_move=PLAYED,
        comparator_move=ChessMove("a1b2"),
    )
    with pytest.raises(ValueError, match="comparator move differs"):
        result(BadMoveExplanationStatus.REFUTED, (other_comparator,))


def test_eligible_aggregate_requires_distinct_comparator() -> None:
    same = BadMoveExplanationResult(
        status=BadMoveExplanationStatus.NOT_APPLICABLE,
        base_position_id=BASE.position_id,
        played_move=PLAYED,
        comparator_move=ChessMove(PLAYED.uci),
    )
    assert same.causes == ()

    with pytest.raises(ValueError, match="comparator must differ"):
        BadMoveExplanationResult(
            status=BadMoveExplanationStatus.INCONCLUSIVE,
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=ChessMove(PLAYED.uci),
        )


def test_aggregate_rejects_conflicting_punishments_and_duplicate_candidates() -> None:
    def with_punishment(uci: str, kind: BadMoveCauseKind) -> BadMoveCauseResult:
        return BadMoveCauseResult(
            kind=kind,
            status=BadMoveCauseStatus.INCONCLUSIVE,
            subject=(SUBJECT,),
            base_position_id=BASE.position_id,
            played_move=PLAYED,
            comparator_move=COMPARATOR,
            punishment_move=ChessMove(uci),
        )

    hanging = with_punishment("h1h2", BadMoveCauseKind.NEWLY_HANGING_PIECE)
    fork = with_punishment("h1g1", BadMoveCauseKind.FORK_ALLOWED)
    with pytest.raises(ValueError, match="punishment"):
        result(BadMoveExplanationStatus.INCONCLUSIVE, (hanging, fork))

    # Causes without a punishment move do not conflict with one that has it.
    no_punishment = cause(BadMoveCauseStatus.INCONCLUSIVE, kind=BadMoveCauseKind.FORK_ALLOWED)
    assert result(BadMoveExplanationStatus.INCONCLUSIVE, (hanging, no_punishment))

    with pytest.raises(ValueError, match="duplicate cause candidate"):
        result(
            BadMoveExplanationStatus.INCONCLUSIVE,
            (cause(BadMoveCauseStatus.INCONCLUSIVE), cause(BadMoveCauseStatus.INCONCLUSIVE)),
        )


def test_bad_move_errors_extend_calliope_hierarchy() -> None:
    assert issubclass(BadMoveExplanationError, CalliopeError)
    assert issubclass(IncompatibleBadMoveContextError, BadMoveExplanationError)
