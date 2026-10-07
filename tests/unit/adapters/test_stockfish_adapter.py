import threading
import time
from typing import Any

import chess
import chess.engine
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.adapters.stockfish import StockfishAdapter
from calliope.domain.chess import ChessMove, Color
from calliope.domain.engine import (
    EngineIdentity,
    EngineLimit,
    EngineSettings,
    StabilityLevel,
)
from calliope.errors import (
    EngineAnalysisError,
    EngineClosedError,
    EngineConfigurationError,
    EngineStartupError,
    IllegalMoveError,
    InvalidEngineOutputError,
    InvalidUciError,
    NullMoveNotAllowedError,
)

START = PythonChessAdapter().position_from_fen(chess.STARTING_FEN)
BLACK_TO_MOVE = PythonChessAdapter().position_from_fen(
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
)
M = chess.Move.from_uci


def pov(score: chess.engine.Score, color: chess.Color) -> chess.engine.PovScore:
    return chess.engine.PovScore(score, color)


def info(score: Any, pv: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "score": score,
        "pv": [M(u) for u in (pv if pv is not None else ["e2e4", "e7e5", "g1f3"])],
        "depth": 10,
        "seldepth": 12,
        "nodes": 1234,
    }
    result.update(extra)
    return result


class FakeOption:
    def __init__(self, min_: int | None = None, max_: int | None = None) -> None:
        self.min = min_
        self.max = max_


class FakeEngine:
    def __init__(
        self,
        infos: Any = None,
        name: str = "Stockfish 17.1",
        options: dict[str, FakeOption] | None = None,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.id = {"name": name}
        self.infos = infos if infos is not None else [info(pov(chess.engine.Cp(20), chess.WHITE))]
        self.options = (
            options
            if options is not None
            else {
                "Threads": FakeOption(1, 1024),
                "Hash": FakeOption(1, 4096),
                "UCI_ShowWDL": FakeOption(),
            }
        )
        self.error = error
        self.delay = delay
        self.calls: list[dict[str, Any]] = []
        self.quit_count = 0
        self.active = 0
        self.max_active = 0
        self._guard = threading.Lock()

    def analyse(self, board: chess.Board, limit: Any, **kwargs: Any) -> Any:
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.calls.append({"board": board, "limit": limit, **kwargs})
            if self.delay:
                time.sleep(self.delay)
            if self.error:
                raise self.error
            return self.infos
        finally:
            with self._guard:
                self.active -= 1

    def quit(self) -> None:
        self.quit_count += 1

    def close(self) -> None:
        pass


def make(engine: FakeEngine | None = None) -> tuple[StockfishAdapter, FakeEngine]:
    engine = engine or FakeEngine()
    return StockfishAdapter(engine, EngineIdentity(name=engine.id["name"])), engine  # type: ignore[arg-type]


SETTINGS = EngineSettings(limit=EngineLimit(depth=8))


def run(infos: Any, position: Any = START, settings: EngineSettings = SETTINGS) -> Any:
    adapter, _ = make(FakeEngine(infos=infos))
    return adapter.analyze(position, settings)


# --- A. score POV ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("position", "raw_cp", "raw_color", "expected"),
    [
        (START, 35, chess.WHITE, 35),
        (START, -35, chess.WHITE, -35),
        (BLACK_TO_MOVE, 50, chess.BLACK, -50),
        (BLACK_TO_MOVE, -50, chess.BLACK, 50),
    ],
)
def test_score_is_white_pov(position: Any, raw_cp: int, raw_color: bool, expected: int) -> None:
    pv = ["e7e5"] if position is BLACK_TO_MOVE else ["e2e4"]
    result = run([info(pov(chess.engine.Cp(raw_cp), raw_color), pv=pv)], position)
    score = result.best_line.score
    assert score.centipawns == expected
    assert score.mate is None


# --- B. mate --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "winner", "moves"),
    [
        (pov(chess.engine.Mate(1), chess.WHITE), Color.WHITE, 1),
        (pov(chess.engine.Mate(3), chess.WHITE), Color.WHITE, 3),
        (pov(chess.engine.Mate(-1), chess.WHITE), Color.BLACK, 1),
        (pov(chess.engine.Mate(-4), chess.WHITE), Color.BLACK, 4),
        (pov(chess.engine.Mate(3), chess.BLACK), Color.BLACK, 3),
        (pov(chess.engine.Mate(-4), chess.BLACK), Color.WHITE, 4),
        (pov(chess.engine.MateGiven, chess.WHITE), Color.WHITE, 0),
        (pov(chess.engine.MateGiven, chess.BLACK), Color.BLACK, 0),
        (pov(chess.engine.Mate(0), chess.WHITE), Color.BLACK, 0),
        (pov(chess.engine.Mate(0), chess.BLACK), Color.WHITE, 0),
    ],
)
def test_mate_normalization(raw: Any, winner: Color, moves: int) -> None:
    score = run([info(raw)]).best_line.score
    assert score.centipawns is None
    assert score.mate is not None
    assert score.mate.winner is winner
    assert score.mate.moves == moves


def test_mate_distance_is_not_halved() -> None:
    score = run([info(pov(chess.engine.Mate(3), chess.WHITE))]).best_line.score
    assert score.mate.moves == 3  # UCI "mate N" is already a move count
    assert score.mate.moves != 2


def test_mate_given_and_mate_zero_are_distinguished() -> None:
    given = run([info(pov(chess.engine.MateGiven, chess.WHITE))]).best_line.score
    zero = run([info(pov(chess.engine.Mate(0), chess.WHITE))]).best_line.score
    assert given.mate.winner is Color.WHITE
    assert zero.mate.winner is Color.BLACK


# --- C. WDL ---------------------------------------------------------------------------


def wdl(w: int, d: int, loss: int, color: bool) -> chess.engine.PovWdl:
    return chess.engine.PovWdl(chess.engine.Wdl(w, d, loss), color)


def test_wdl_white_pov_and_normalized() -> None:
    line = run([info(pov(chess.engine.Cp(10), chess.WHITE), wdl=wdl(500, 300, 200, chess.WHITE))])
    got = line.best_line.wdl
    assert (got.white_win, got.draw, got.black_win) == pytest.approx((0.5, 0.3, 0.2))


def test_wdl_black_pov_converted_to_white() -> None:
    line = run(
        [
            info(
                pov(chess.engine.Cp(10), chess.BLACK),
                wdl=wdl(500, 300, 200, chess.BLACK),
                pv=["e7e5"],
            )
        ],
        BLACK_TO_MOVE,
    )
    got = line.best_line.wdl
    assert (got.white_win, got.draw, got.black_win) == pytest.approx((0.2, 0.3, 0.5))


def test_wdl_total_not_hardcoded() -> None:
    got = run([info(pov(chess.engine.Cp(0), chess.WHITE), wdl=wdl(2, 1, 1, chess.WHITE))])
    assert got.best_line.wdl.white_win == pytest.approx(0.5)
    assert got.best_line.wdl.draw == pytest.approx(0.25)


def test_missing_wdl_is_none() -> None:
    assert run([info(pov(chess.engine.Cp(0), chess.WHITE))]).best_line.wdl is None


def test_zero_total_wdl_fails() -> None:
    with pytest.raises(InvalidEngineOutputError):
        run([info(pov(chess.engine.Cp(0), chess.WHITE), wdl=wdl(0, 0, 0, chess.WHITE))])


# --- D. MultiPV -----------------------------------------------------------------------


def cp(value: int) -> chess.engine.PovScore:
    return pov(chess.engine.Cp(value), chess.WHITE)


def test_multipv_1_passed_explicitly() -> None:
    adapter, engine = make()
    result = adapter.analyze(START, SETTINGS)
    assert engine.calls[0]["multipv"] == 1
    assert len(result.lines) == 1


def test_multipv_3_sorted_by_rank() -> None:
    infos = [
        info(cp(10), pv=["d2d4"], multipv=3),
        info(cp(30), pv=["e2e4"], multipv=1),
        info(cp(20), pv=["g1f3"], multipv=2),
    ]
    adapter, engine = make(FakeEngine(infos=infos))
    result = adapter.analyze(START, EngineSettings(limit=EngineLimit(depth=8), multipv=3))
    assert engine.calls[0]["multipv"] == 3
    assert [line.rank for line in result.lines] == [1, 2, 3]
    assert [line.first_move.uci for line in result.lines] == ["e2e4", "g1f3", "d2d4"]


def test_duplicate_rank_fails() -> None:
    with pytest.raises(InvalidEngineOutputError):
        run([info(cp(1), multipv=1), info(cp(1), pv=["d2d4"], multipv=1)])


def test_missing_multipv_uses_return_order() -> None:
    result = run([info(cp(1)), info(cp(0), pv=["d2d4"])])
    assert [line.rank for line in result.lines] == [1, 2]


def test_rank_one_absent_fails() -> None:
    with pytest.raises(InvalidEngineOutputError):
        run([info(cp(1), multipv=2)])


def test_nonpositive_rank_fails() -> None:
    with pytest.raises(InvalidEngineOutputError):
        run([info(cp(1), multipv=0)])


@pytest.mark.parametrize("infos", [[], None, {"score": cp(1)}])
def test_empty_or_malformed_result_fails(infos: Any) -> None:
    adapter, _ = make(FakeEngine(infos=infos if infos is not None else "x"))
    with pytest.raises(InvalidEngineOutputError):
        adapter.analyze(START, SETTINGS)


# --- E. PV ----------------------------------------------------------------------------


def test_pv_san_generated_sequentially() -> None:
    line = run([info(cp(1))]).best_line
    assert line.pv == (
        ChessMove("e2e4", "e4"),
        ChessMove("e7e5", "e5"),
        ChessMove("g1f3", "Nf3"),
    )
    assert line.first_move == line.pv[0]
    assert (line.depth, line.seldepth, line.nodes) == (10, 12, 1234)


@pytest.mark.parametrize(
    "pv",
    [[], ["e7e5"], ["e2e4", "e2e4"], ["0000"]],
)
def test_invalid_pv_fails(pv: list[str]) -> None:
    with pytest.raises(InvalidEngineOutputError):
        run([info(cp(1), pv=pv)])


def test_missing_pv_and_score_fail() -> None:
    bad_pv = info(cp(1))
    del bad_pv["pv"]
    with pytest.raises(InvalidEngineOutputError):
        run([bad_pv])
    bad_score = info(cp(1))
    del bad_score["score"]
    with pytest.raises(InvalidEngineOutputError):
        run([bad_score])


@pytest.mark.parametrize("bound", ["lowerbound", "upperbound"])
def test_bound_score_rejected(bound: str) -> None:
    with pytest.raises(InvalidEngineOutputError):
        run([info(cp(1), **{bound: True})])


# --- F. root_moves --------------------------------------------------------------------


def test_root_moves_none_passes_none() -> None:
    adapter, engine = make()
    adapter.analyze(START, SETTINGS)
    assert engine.calls[0]["root_moves"] is None


def test_root_moves_legal_passed_as_native() -> None:
    adapter, engine = make()
    adapter.analyze(START, SETTINGS, (ChessMove("e2e4"), ChessMove("d2d4")))
    assert engine.calls[0]["root_moves"] == [M("e2e4"), M("d2d4")]


def test_root_moves_forged_san_ignored() -> None:
    adapter, engine = make()
    adapter.analyze(START, SETTINGS, (ChessMove(uci="e2e4", san="garbage"),))
    assert engine.calls[0]["root_moves"] == [M("e2e4")]


@pytest.mark.parametrize(
    ("roots", "error"),
    [
        ((), EngineConfigurationError),
        ((ChessMove("e2e4"), ChessMove("e2e4")), EngineConfigurationError),
        ((ChessMove("e2e5"),), IllegalMoveError),
        ((ChessMove("zzzz"),), InvalidUciError),
        ((ChessMove("0000"),), NullMoveNotAllowedError),
    ],
)
def test_invalid_root_moves(roots: tuple[ChessMove, ...], error: type[Exception]) -> None:
    adapter, engine = make()
    with pytest.raises(error):
        adapter.analyze(START, SETTINGS, roots)
    assert engine.calls == []


# --- G. options / limit ---------------------------------------------------------------


def test_limits_all_translated() -> None:
    adapter, engine = make()
    adapter.analyze(START, EngineSettings(limit=EngineLimit(depth=9, nodes=5000, time_ms=250)))
    limit = engine.calls[0]["limit"]
    assert (limit.depth, limit.nodes, limit.time) == (9, 5000, 0.25)


def test_threads_hash_and_wdl_options() -> None:
    adapter, engine = make()
    adapter.analyze(START, EngineSettings(limit=EngineLimit(depth=5), threads=2, hash_mb=64))
    assert engine.calls[0]["options"] == {"Threads": 2, "Hash": 64, "UCI_ShowWDL": True}
    assert "MultiPV" not in engine.calls[0]["options"]


def test_no_show_wdl_when_unsupported() -> None:
    adapter, engine = make(FakeEngine(options={}))
    result = adapter.analyze(START, SETTINGS)
    assert engine.calls[0]["options"] == {}
    assert result.best_line.wdl is None


@pytest.mark.parametrize(
    ("settings", "options"),
    [
        (EngineSettings(limit=EngineLimit(depth=5), threads=5000), None),
        (EngineSettings(limit=EngineLimit(depth=5), hash_mb=0 + 99999), None),
        (EngineSettings(limit=EngineLimit(depth=5), threads=2), {}),
    ],
)
def test_option_validation(settings: EngineSettings, options: Any) -> None:
    adapter, engine = make(FakeEngine(options=options))
    with pytest.raises(EngineConfigurationError):
        adapter.analyze(START, settings)
    assert engine.calls == []


def test_settings_positivity() -> None:
    with pytest.raises(ValueError):
        EngineSettings(limit=EngineLimit(depth=1), threads=0)
    with pytest.raises(ValueError):
        EngineSettings(limit=EngineLimit(depth=1), hash_mb=0)


# --- H. lifecycle / failures ----------------------------------------------------------


def test_start_success(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine(name="Stockfish 17.1")
    seen: dict[str, Any] = {}

    def popen(command: Any, **kwargs: Any) -> FakeEngine:
        seen.update(command=command, **kwargs)
        return engine

    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", popen)
    with StockfishAdapter.start("sf", timeout_s=3.0) as adapter:
        result = adapter.analyze(START, SETTINGS)
    assert seen == {"command": "sf", "timeout": 3.0}
    assert result.engine == EngineIdentity(name="Stockfish 17.1", version=None)
    assert engine.quit_count == 1


def test_start_rejects_non_stockfish(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine(name="Leela Chess Zero")
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda *a, **k: engine)
    with pytest.raises(EngineStartupError):
        StockfishAdapter.start("lc0")
    assert engine.quit_count == 1


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundError("x"),
        PermissionError("x"),
        chess.engine.EngineTerminatedError("x"),
        TimeoutError("x"),
    ],
)
def test_start_failure_mapped(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise exc

    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", boom)
    with pytest.raises(EngineStartupError):
        StockfishAdapter.start("nope")


def test_close_idempotent_and_closed_rejects() -> None:
    adapter, engine = make()
    adapter.close()
    adapter.close()
    assert engine.quit_count == 1
    with pytest.raises(EngineClosedError):
        adapter.analyze(START, SETTINGS)


@pytest.mark.parametrize(
    "exc",
    [
        chess.engine.EngineTerminatedError("died"),
        chess.engine.EngineError("bad"),
        BrokenPipeError("pipe"),
        TimeoutError("slow"),
    ],
)
def test_engine_failures_mapped(exc: Exception) -> None:
    adapter, _ = make(FakeEngine(error=exc))
    with pytest.raises(EngineAnalysisError) as raised:
        adapter.analyze(START, SETTINGS)
    assert not isinstance(raised.value, chess.engine.EngineError)


@pytest.mark.parametrize(
    "fen",
    ["7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "7k/5Q2/8/8/8/8/8/6K1 b - - 0 1"],
)
def test_terminal_position_rejected(fen: str) -> None:
    position = PythonChessAdapter().position_from_fen(fen)
    adapter, engine = make()
    with pytest.raises(EngineAnalysisError):
        adapter.analyze(position, SETTINGS)
    assert engine.calls == []


def test_stability_is_unknown() -> None:
    stability = run([info(cp(1))]).stability
    assert stability.level is StabilityLevel.UNKNOWN
    assert stability.samples == 1
    assert stability.best_move_switches == 0
    assert stability.max_cp_swing is None


# --- I. concurrency -------------------------------------------------------------------


def test_concurrent_analyses_are_serialized() -> None:
    adapter, engine = make(FakeEngine(delay=0.05))
    errors: list[BaseException] = []

    def work() -> None:
        try:
            adapter.analyze(START, SETTINGS)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(engine.calls) == 4
    assert engine.max_active == 1
