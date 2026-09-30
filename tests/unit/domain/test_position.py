import pytest

from calliope.domain.chess import Color, PositionSnapshot, position_id_from_fen


def test_position_snapshot_id_is_bound_to_fen() -> None:
    fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
    snapshot = PositionSnapshot.create(
        fen=fen,
        ply=0,
        side_to_move=Color.WHITE,
        castling_rights="-",
        en_passant_square=None,
        halfmove_clock=0,
        fullmove_number=1,
    )

    assert snapshot.position_id == position_id_from_fen(fen)


def test_position_snapshot_rejects_mismatched_identity() -> None:
    with pytest.raises(ValueError, match="position_id"):
        PositionSnapshot(
            position_id="pos_wrong",
            fen="8/8/8/8/8/8/8/K6k w - - 0 1",
            ply=0,
            side_to_move=Color.WHITE,
            castling_rights="-",
            en_passant_square=None,
            halfmove_clock=0,
            fullmove_number=1,
        )
