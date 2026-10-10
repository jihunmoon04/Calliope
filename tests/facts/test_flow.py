"""`material_flow` (reasoning R0-D §6.5, §18.2): per-ply material, balance and stability."""

from __future__ import annotations

import pytest

from calliope.facts import (
    PLAYED,
    Color,
    ExtendRequest,
    FactEngine,
    InputLine,
    InvalidRequestError,
    MaterialFacts,
    NotComputed,
    OpenRequest,
    PieceType,
    RootSpec,
    Stable,
    Unstable,
    UnstableReason,
    material_flow,
)


def _line(*moves: str, fen: str | None = None):
    engine = FactEngine()
    tree = engine.open(OpenRequest(root=RootSpec(fen=fen)))
    engine.extend(tree, ExtendRequest((InputLine("g", moves),), PLAYED))
    view = tree.view()
    return view, view.input_line("g").nodes


def test_a_capture_raises_the_capturers_balance() -> None:
    view, path = _line("e4", "d5", "exd5")
    flow = material_flow(view, path)
    assert [p.capture is not None for p in flow.plies] == [False, False, True]
    assert flow.balance(Color.WHITE, 3) == 1 and flow.balance(Color.BLACK, 3) == -1
    assert flow.last_change == 3
    assert flow.stable == Unstable(UnstableReason.CAPTURE_AT_END)


def test_a_queen_capture_is_nine_though_the_capturers_points_do_not_change() -> None:
    view, path = _line("Nxd8", fen="3qk3/8/2N5/8/8/8/8/4K3 w - - 0 1")
    flow = material_flow(view, path)
    assert flow.points_before[0] == flow.points_after[0]
    assert flow.balance(Color.WHITE, 1) == 9


def test_a_capture_promotion_is_one_ply() -> None:
    view, path = _line("bxa8=Q", fen="r3k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
    flow = material_flow(view, path)
    (ply,) = flow.plies
    assert ply.capture is not None and ply.capture.piece_type is PieceType.ROOK
    assert ply.promotion is not None and ply.promotion.to is PieceType.QUEEN
    assert flow.balance(Color.WHITE, 1) == 5 + 8  # the rook, and a pawn become a queen


def test_en_passant_and_castling() -> None:
    view, path = _line("exd6", fen="4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    (ply,) = material_flow(view, path).plies
    assert ply.capture is not None and ply.capture.en_passant
    view, path = _line("O-O", "Ke7", "Kh1", fen="4k3/8/8/8/8/8/8/4K2R w K - 0 1")
    flow = material_flow(view, path)
    assert flow.last_change is None and flow.stable == Stable()


@pytest.mark.parametrize(
    ("fen", "moves", "stable"),
    [
        (None, ("f3", "e5", "g4", "Qh4#"), Stable()),  # ends in checkmate
        ("7k/8/6Q1/8/8/8/8/K7 w - - 0 1", ("Qf7",), Unstable(UnstableReason.DRAWN_END)),
        (None, ("e4",), Unstable(UnstableReason.TOO_SHORT)),
        (None, ("e4", "e5"), Stable()),  # no change, two plies
        (None, ("e4", "d5", "exd5", "Nf6", "c4"), Stable()),  # two plies after the capture
        (None, ("e4", "d5", "exd5", "Nf6"), Unstable(UnstableReason.TOO_SHORT)),
    ],
)
def test_stability(fen, moves, stable) -> None:
    view, path = _line(*moves, fen=fen)
    assert material_flow(view, path).stable == stable


def test_a_stalemate_after_quiet_plies_is_still_drawn() -> None:
    fen = "7k/8/8/8/8/8/5Q2/K7 w - - 0 1"
    view, path = _line("Ka2", "Kg8", "Kb2", "Kh8", "Qf7", fen=fen)
    assert material_flow(view, path).stable == Unstable(UnstableReason.DRAWN_END)


def test_per_ply_points_are_the_material_records() -> None:
    view, path = _line("e4", "d5", "exd5", "Qxd5", "Nc3", "Qxa2")
    flow = material_flow(view, path)
    for ply, node in zip(flow.plies, path[1:], strict=True):
        record = view.fact("material", node)
        assert isinstance(record, MaterialFacts)
        assert ply.points == record.points.value
    assert flow.balance(Color.BLACK, 6) == 1


def test_path_validation() -> None:
    view, path = _line("e4", "e5", "Nf3")
    with pytest.raises(InvalidRequestError):
        material_flow(view, ())
    with pytest.raises(InvalidRequestError):
        material_flow(view, (path[0], path[2]))
    flow = material_flow(view, (path[1],))
    assert flow.plies == () and flow.stable == Unstable(UnstableReason.TOO_SHORT)


def test_a_missing_record_is_not_computed() -> None:
    engine = FactEngine()
    tree = engine.open(OpenRequest(families=("status",)))
    engine.extend(tree, ExtendRequest((InputLine("g", ("e4", "e5")),), PLAYED))
    view = tree.view()
    flow = material_flow(view, view.input_line("g").nodes)
    assert isinstance(flow.stable, NotComputed) and flow.points_before is None
