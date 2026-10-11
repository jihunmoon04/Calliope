"""F6: the `exchange` family (`see_v1`) and on-request families (F6-D §2, test obligations §5)."""

from __future__ import annotations

from typing import ClassVar

import chess
import pytest

from calliope.facts import (
    PLAYED,
    EnsureRequest,
    ExtendRequest,
    FactEngine,
    InputLine,
    OpenRequest,
    RoleKind,
    RootSpec,
    storage,
)
from calliope.facts.families import REGISTRY, ExchangeFamily, FamilyContext
from calliope.facts.families.exchange import IN_CHECK, NOT_EXPOSED, SEE_V1
from calliope.facts.tree import Scope
from calliope.facts.values import NOT_OBSERVED, Defined, FactClass, NotComputed

FAMILY = ExchangeFamily()


def record(fen: str):
    return FAMILY.compute(FamilyContext(board=chess.Board(fen), records={}))


def piece(fen: str, square: str):
    return next(p for p in record(fen).pieces if p.square == square)


def gain(fen: str, square: str) -> int:
    value = piece(fen, square).gain
    assert isinstance(value, Defined) and value.definition == SEE_V1
    return value.value


# -- §5.1 the swap-off --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fen", "square", "expected", "first"),
    [
        ("4k3/8/4n3/8/2B5/8/8/4K3 w - - 0 1", "e6", 3, "c4e6"),  # an undefended knight
        ("4k3/5p2/4n3/8/2B5/8/8/4K3 w - - 0 1", "e6", 0, None),  # a defended knight: a trade
        ("4k3/8/8/8/8/8/r7/R3K3 w - - 0 1", "a2", 5, "a1a2"),  # an undefended rook
        ("4k3/8/4p3/3n4/8/1BN5/8/4K3 w - - 0 1", "d5", 1, "b3d5"),  # B = N: b3 before c3
        ("r3k3/8/n7/8/8/8/R7/R3K3 w - - 0 1", "a6", 3, "a2a6"),  # a battery joins
        ("r3k3/8/n7/8/8/8/R7/4K3 w - - 0 1", "a6", 0, None),  # the same without the battery
        ("4r1k1/8/8/8/8/3b4/4B3/4K3 w - - 0 1", "d3", 0, None),  # a pinned attacker may not
        ("4r1k1/8/8/8/4q3/8/4R3/4K3 w - - 0 1", "e4", 4, "e2e4"),  # it may along its pin
        ("4k3/8/8/8/8/8/3r4/4K3 w - - 0 1", "d2", 5, "e1d2"),  # a king takes an undefended rook
        ("4k3/8/8/8/1b6/8/3r4/4K3 w - - 0 1", "d2", 0, None),  # but not a defended one
        ("r3k3/1P6/8/8/8/8/8/4K3 w - - 0 1", "a8", 13, "b7a8q"),  # a capture that promotes
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "d5", 0, None),  # en passant is not counted
        ("3qk3/8/8/3p4/8/2N5/8/3RK3 w - - 0 1", "d5", 1, "c3d5"),  # Black declines Qxd5
    ],
)
def test_the_swap_off(fen: str, square: str, expected: int, first: str | None) -> None:
    found = piece(fen, square)
    assert gain(fen, square) == expected
    assert found.first_capture == first
    assert not found.hypothetical  # the owner is not to move: the gain is real


# -- §5.2 exposure of the side to move ----------------------------------------------------------

KNIGHT = "4k3/8/8/3p4/4N3/8/8/4K3 w - - 0 1"


def test_the_side_to_move_is_exposed_with_the_turn_passed() -> None:
    knight = piece(KNIGHT, "e4")
    assert knight.hypothetical and gain(KNIGHT, "e4") == 3 and knight.first_capture == "d5e4"
    pawn = piece(KNIGHT, "d5")
    assert not pawn.hypothetical and pawn.safe_moves == NOT_OBSERVED  # side not to move


def test_in_check_the_side_to_move_has_no_gain() -> None:
    fen = "4k3/8/8/8/4N3/8/4r3/4K3 w - - 0 1"  # the rook on e2 checks
    knight = piece(fen, "e4")
    assert knight.gain == IN_CHECK and knight.first_capture is None
    assert isinstance(knight.safe_moves, tuple)  # every piece is scanned in check
    assert gain(fen, "e2") == 5 and piece(fen, "e2").first_capture == "e1e2"  # undefended


# -- §5.3 safe moves ---------------------------------------------------------------------------


def test_a_hanging_piece_lists_its_retreats() -> None:
    board = chess.Board(KNIGHT)
    retreats = {m.uci() for m in board.legal_moves if m.from_square == chess.E4}
    assert set(piece(KNIGHT, "e4").safe_moves) == retreats  # king moves leave it hanging


def test_a_piece_that_is_not_exposed_is_not_scanned() -> None:
    fen = "4k3/8/8/8/4N3/8/8/4K3 w - - 0 1"
    assert piece(fen, "e4").safe_moves == NOT_EXPOSED


def test_a_trapped_piece_has_no_safe_move_and_a_capture_elsewhere_does_not_save_it() -> None:
    fen = "7k/8/8/8/4b2p/p3p3/K7/7N w - - 0 1"  # Nh1: f2 and g3 are covered; Kxa3 is possible
    assert gain(fen, "h1") == 3
    assert piece(fen, "h1").safe_moves == ()
    assert chess.Move.from_uci("a2a3") in chess.Board(fen).legal_moves


def test_a_terminal_position_has_no_safe_moves() -> None:
    mated = "4k3/8/8/8/8/8/5PPP/3r2KN w - - 0 1"  # back-rank mate, the knight on h1 attacked
    board = chess.Board(mated)
    assert board.is_checkmate()
    assert piece(mated, "h1").safe_moves == ()


# -- §5.4 on request ---------------------------------------------------------------------------

ENGINE = FactEngine()


def _tree(*moves: str, **kwargs):
    tree = ENGINE.open(OpenRequest(root=RootSpec(), **kwargs))
    ENGINE.extend(tree, ExtendRequest((InputLine("game", moves),), PLAYED))
    return tree, tree.view().input_line("game", RoleKind.PLAYED).nodes[-1]


def test_exchange_is_computed_only_on_request() -> None:
    tree, end = _tree("e4", "d5")
    view = tree.view()
    assert "exchange" not in view.eager() and "exchange" not in view.default_families()
    assert "exchange" in view.families()
    assert isinstance(view.fact("exchange", end), NotComputed)
    ENGINE.ensure(tree, EnsureRequest((end,), ("exchange",)))
    pawn = next(p for p in tree.view().fact("exchange", end).pieces if p.square == "e4")
    assert pawn.hypothetical and pawn.gain == Defined(SEE_V1, 1)  # exd5 is next: e4 hangs to d5
    named, end2 = _tree("e4", families=("exchange",))
    assert not isinstance(named.view().fact("exchange", end2), NotComputed)


class _OnRequest:
    name: ClassVar[str] = "probe_on_request"
    version: ClassVar[str] = "probe_v1"
    scope: ClassVar[Scope] = Scope.POSITION
    fact_class: ClassVar[FactClass] = FactClass.DEFINED
    requires: ClassVar[tuple[str, ...]] = ()
    on_request: ClassVar[bool] = True
    record_types: ClassVar[tuple[type, ...]] = ()

    def compute(self, ctx: FamilyContext) -> int:
        return 0


class _NeedsIt(_OnRequest):
    name: ClassVar[str] = "probe_default"
    requires: ClassVar[tuple[str, ...]] = ("probe_on_request",)
    on_request: ClassVar[bool] = False


def test_a_default_family_may_not_require_an_on_request_family() -> None:
    with pytest.raises(ValueError, match="on-request"):
        FactEngine((*REGISTRY, _OnRequest(), _NeedsIt()))


def test_the_flag_is_part_of_the_build_identity() -> None:
    entries = {e.name: e for e in storage.build_identity(REGISTRY).families}
    assert entries["exchange"].on_request and not entries["material"].on_request


# -- §5.5 determinism --------------------------------------------------------------------------


def test_records_are_shared_by_position_and_survive_a_save() -> None:
    a, end_a = _tree("Nf3", "Nf6", "Nc3", families=("exchange",))
    b, end_b = _tree("Nc3", "Nf6", "Nf3", families=("exchange",))
    assert a.view().fact("exchange", end_a) == b.view().fact("exchange", end_b)
    loaded = storage.load(ENGINE, storage.save(a))
    assert loaded.view().fact("exchange", end_a) == a.view().fact("exchange", end_a)
