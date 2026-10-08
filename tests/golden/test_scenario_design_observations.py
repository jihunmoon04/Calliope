"""Verify design examples against existing observations, not future summary acceptance.

Expected captures, counts and distinguishing facts are manually specified in JSON.
No new scenario service or renderer is implemented or simulated here.
"""

import json
from pathlib import Path

import chess
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.chess import ChessMove
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer

CORPUS = json.loads(
    Path(__file__).with_name("scenario_explanation_cases.json").read_text(encoding="utf-8")
)
CASES = CORPUS["cases"]


def build():
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    return rules, ActivityLineAnalyzer(
        LineAnalyzer(transitions), ActivityAnalyzer(positions, rules)
    )


def type_key(piece):
    return f"{piece.color.value}:{piece.piece_type.value}"


def observations(result):
    captures = []
    for ply, step in enumerate(result.structural.transitions, 1):
        capture = step.board_delta.capture
        if capture:
            captures.append(
                {
                    "ply": ply,
                    "landing": capture.landing_square,
                    "victim_square": capture.captured_square,
                    "victim": type_key(capture.captured),
                    "ep": capture.is_en_passant,
                }
            )
    material = {
        f"{c.color.value}:{c.piece_type.value}": c.count_delta
        for c in result.structural.material_changes
    }
    return captures, material


def read_check(result, check):
    if check["kind"] == "history":
        history = next(
            h
            for h in result.structural.piece_histories
            if h.base.base_square == check["base_square"]
        )
        return [f"{p.square}:{p.piece_type.value}" if p else None for p in history.states]
    frame = result.activity_frames[check["frame"]]
    kind = check["kind"]
    if kind in ("occupant", "attackers", "legal_captures"):
        access = next(s for s in frame.activity.squares if s.square == check["square"])
        if kind == "occupant":
            return type_key(access.occupant) if access.occupant else None
        if kind == "attackers":
            attackers = getattr(access, f"{check['color']}_attackers")
            return [p.square for p in attackers]
        return [c.move.uci for c in access.current_legal_captures]
    if kind == "pins":
        return [
            [p.pinner.square, p.pinned.square, p.king.square] for p in frame.activity.absolute_pins
        ]
    if kind == "pawn":
        pawn = next(p for p in frame.structural.features.pawns if p.pawn.square == check["square"])
        return {
            "isolated": pawn.isolated,
            "doubled": pawn.doubled,
            "passed": pawn.passed,
            "supporters": [p.square for p in pawn.pawn_supporters],
        }
    if kind == "file":
        file = next(f for f in frame.structural.features.files if f.file == check["file"])
        return [file.white_pawns, file.black_pawns]
    if kind == "ray":
        ray = next(
            r
            for r in frame.activity.rays
            if r.source.square == check["square"] and r.direction == tuple(check["direction"])
        )
        return list(ray.visible_squares)
    raise AssertionError(f"Unknown observation oracle: {kind}")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_design_case_factual_oracles(case):
    rules, lines = build()
    result = lines.analyze(
        rules.position_from_fen(case["fen"]), tuple(ChessMove(m) for m in case["moves"])
    )
    assert len(result.activity_frames) == len(case["moves"]) + 1
    assert observations(result) == (case["captures"], case["material"])
    for check in case["checks"]:
        assert read_check(result, check) == check["value"], (case["id"], check)

    # Replay is independently legal in python-chess; explicit JSON remains the fact oracle.
    board = chess.Board(case["fen"])
    assert board.is_valid()
    for i, uci in enumerate(case["moves"], 1):
        move = chess.Move.from_uci(uci)
        assert move in board.legal_moves
        board.push(move)
        observed = chess.Board(result.activity_frames[i].structural.position.fen)
        assert observed.piece_map() == board.piece_map()
        assert observed.turn == board.turn
    assert case["required"] and case["forbidden"] and case["alternative_needed"]


def mirror_square(square):
    return chess.square_name(chess.square_mirror(chess.parse_square(square)))


def mirror_move(uci):
    return mirror_square(uci[:2]) + mirror_square(uci[2:4]) + uci[4:]


def mirror_type_key(key):
    color, kind = key.split(":")
    return f"{'black' if color == 'white' else 'white'}:{kind}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_design_case_color_mirror_capture_and_material_oracles(case):
    rules, lines = build()
    initial = chess.Board(case["fen"]).mirror()
    result = lines.analyze(
        rules.position_from_fen(initial.fen()),
        tuple(ChessMove(mirror_move(m)) for m in case["moves"]),
    )
    expected_captures = [
        dict(
            c,
            landing=mirror_square(c["landing"]),
            victim_square=mirror_square(c["victim_square"]),
            victim=mirror_type_key(c["victim"]),
        )
        for c in case["captures"]
    ]
    expected_material = {mirror_type_key(k): v for k, v in case["material"].items()}
    assert observations(result) == (expected_captures, expected_material)
