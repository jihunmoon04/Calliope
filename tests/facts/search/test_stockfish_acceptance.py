"""F4-D §9.3 items 1–4 against the real engine (gated on `CALLIOPE_STOCKFISH_PATH`)."""

import hashlib
import os
import random
import subprocess

import chess
import pytest

from calliope.facts.search import (
    EngineInput,
    EngineProfile,
    EngineResultStore,
    Searcher,
    SearchKind,
    StockfishEngine,
    window_input,
)

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")
pytestmark = pytest.mark.skipif(not STOCKFISH, reason="CALLIOPE_STOCKFISH_PATH is not set")
PROFILE = EngineProfile()
POSITIONS = (
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 1",
    "r2q1rk1/pp2bppp/2n1bn2/3p4/3P4/2NBBN2/PP3PPP/R2Q1RK1 w - - 4 1",
    "8/5pk1/6p1/3R4/8/6P1/5PKP/3r4 b - - 0 1",
)


@pytest.fixture(scope="module")
def engine():
    with StockfishEngine.start(STOCKFISH) as port:
        yield port


def _search(engine, engine_input: EngineInput):
    # a fresh store per call: every call reaches the engine
    return Searcher(engine, EngineResultStore(), PROFILE).search(engine_input, SearchKind.SURVEY)[0]


def test_identity_is_recorded_and_admitted(engine) -> None:
    identity = engine.identity
    assert identity.name == "Stockfish 19"
    with open(os.path.realpath(STOCKFISH), "rb") as handle:
        assert identity.binary_sha256 == hashlib.sha256(handle.read()).hexdigest()
    assert identity.default("EvalFile")
    assert not identity.offers("EvalFileSmall")  # one network on Stockfish 19 (F4-D M1)


def test_fresh_state_is_deterministic(engine) -> None:
    inputs = [window_input(chess.Board(fen), (), 0) for fen in POSITIONS]
    first = [_search(engine, i) for i in inputs]
    for engine_input in reversed(inputs):
        _search(engine, engine_input)
    again = [_search(engine, i) for i in inputs]
    assert first == again and all(s.regular for s in first)
    with StockfishEngine.start(STOCKFISH) as other:
        assert [_search(other, i) for i in inputs] == first


def _engine_fens(fens: list[str], moves: list[str] | None = None) -> list[str]:
    moves = moves or [""] * len(fens)
    script = (
        "uci\n"
        + "".join(
            f"position fen {fen}" + (f" moves {m}" if m else "") + "\nd\n"
            for fen, m in zip(fens, moves, strict=True)
        )
        + "quit\n"
    )
    out = subprocess.run(
        [STOCKFISH], input=script, capture_output=True, text=True, timeout=120, check=True
    ).stdout
    return [line[5:].strip() for line in out.splitlines() if line.startswith("Fen:")]


def test_en_passant_form_matches_the_engine() -> None:
    rng = random.Random(4)
    fens = [
        "7k/8/8/KPp4r/8/8/8/8 w - c6 0 1",  # pseudo-legal only: a rank pin
        "8/8/8/8/k1Pp3R/8/8/7K b - c3 0 1",
        "4r2k/8/8/3pP3/8/8/8/4K3 w - d6 0 1",  # file pin
        "7k/8/8/3pP3/8/8/8/K7 w - d6 0 1",  # legal
    ]
    while len(fens) < 150:
        board = chess.Board()
        for _ in range(rng.randrange(4, 50)):
            legal = list(board.legal_moves)
            if not legal:
                break
            doubles = [
                m
                for m in legal
                if board.piece_type_at(m.from_square) == chess.PAWN
                and abs(m.to_square - m.from_square) == 16
            ]
            board.push(rng.choice(doubles) if doubles and rng.random() < 0.5 else rng.choice(legal))
            if board.ep_square is not None:
                fens.append(board.fen(en_passant="fen"))
    ours = [window_input(chess.Board(fen), (), 0).fen for fen in fens]
    theirs = _engine_fens(fens)
    assert [f.split()[3] for f in ours] == [f.split()[3] for f in theirs]


def test_en_passant_form_matches_the_engine_after_a_move() -> None:
    """The `do_move` path: the double push is sent as a window move (F4-D §4, M3)."""

    rng = random.Random(9)
    befores: list[str] = ["7k/2p5/8/KP5r/8/8/8/8 b - - 0 1"]  # c7c5 creates a pinned ep
    pushes: list[str] = ["c7c5"]
    while len(befores) < 120:
        board = chess.Board()
        for _ in range(rng.randrange(4, 50)):
            legal = list(board.legal_moves)
            if not legal:
                break
            doubles = [
                m
                for m in legal
                if board.piece_type_at(m.from_square) == chess.PAWN
                and abs(m.to_square - m.from_square) == 16
            ]
            if doubles and rng.random() < 0.5:
                move = rng.choice(doubles)
                befores.append(board.fen())
                pushes.append(move.uci())
                board.push(move)
            else:
                board.push(rng.choice(legal))
    ours = []
    for fen, uci in zip(befores, pushes, strict=True):
        board = chess.Board(fen)
        board.push_uci(uci)
        ours.append(board.fen(en_passant="legal").split()[3])
    theirs = [f.split()[3] for f in _engine_fens(befores, pushes)]
    assert ours == theirs


def _windowed(history: list[str]) -> tuple[EngineInput, EngineInput]:
    board = chess.Board()
    for uci in history:
        board.push_uci(uci)
    full = EngineInput(chess.STARTING_FEN, tuple(history))
    return window_input(chess.Board(), history, board.halfmove_clock), full


def test_window_input_equals_full_history(engine) -> None:
    shuffle = ["g1f3", "g8f6", "f3g1", "f6g8"]
    histories = [
        ["e2e4", "e7e5", *shuffle, *shuffle],  # window 8 of 10
        ["d2d4", "d7d5", "c2c4", "e7e6", *shuffle, "g1f3"],  # window 5 of 9
        ["e2e4", "c7c5", "g1f3", "b8c6", *["f3g1", "c6b8", "g1f3", "b8c6"] * 2],  # 10 of 12
    ]
    bare_differs = 0
    for history in histories:
        windowed, full = _windowed(history)
        assert 0 < len(windowed.moves) < len(full.moves)
        lines = _search(engine, windowed).lines
        assert lines == _search(engine, full).lines
        board = chess.Board()
        for uci in history:
            board.push_uci(uci)
        bare = window_input(chess.Board(board.fen()), (), 0)
        bare_differs += _search(engine, bare).lines != lines
    assert bare_differs >= 1  # the window matters: a bare FEN loses the repetition history
