from dataclasses import replace
from pathlib import Path

import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.chess import PositionObservation
from calliope.errors import IncompatiblePositionObservationError
from calliope.services.position import PositionFactExtractor

rules = PythonChessAdapter()
POSITION = rules.position_from_fen("4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1")


class WrongIdObservations:
    def observe_position(self, position) -> PositionObservation:
        real = rules.observe_position(position)
        return replace(real, position_id="pos_other")


def test_observation_bound_to_position_id():
    with pytest.raises(IncompatiblePositionObservationError):
        PositionFactExtractor(WrongIdObservations()).extract(POSITION)


class ShuffledObservations:
    def observe_position(self, position) -> PositionObservation:
        real = rules.observe_position(position)
        return replace(
            real,
            pieces=real.pieces[::-1],
            attacks=real.attacks[::-1],
            legal_captures=real.legal_captures[::-1],
        )


def test_output_order_independent_of_observation_order():
    assert PositionFactExtractor(ShuffledObservations()).extract(POSITION) == (
        PositionFactExtractor(rules).extract(POSITION)
    )


def test_no_python_chess_outside_adapters():
    root = Path(__file__).resolve().parents[4] / "src" / "calliope"
    forbidden = ("import chess", "from chess", "chess.Board", "chess.Move", "SquareSet")
    for sub in ("domain", "services", "application/ports"):
        for path in (root / sub).rglob("*.py"):
            text = path.read_text()
            for token in forbidden:
                assert token not in text, f"{token!r} in {path}"
