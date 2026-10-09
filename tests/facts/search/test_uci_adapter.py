"""F4-D §9.1.1: the raw-UCI adapter against a scripted fake engine."""

import json
import sys
from pathlib import Path

import chess
import pytest

from calliope.facts.errors import EngineError, EngineOutputError, EngineUnsupportedError
from calliope.facts.search import (
    Bound,
    EngineProfile,
    SearchKind,
    SearchRequest,
    StockfishEngine,
    StoppedBy,
    normalize,
    window_input,
)

FAKE = Path(__file__).with_name("fake_uci.py")
START = window_input(chess.Board(), (), 0)


def _engine(tmp_path, **script) -> tuple[StockfishEngine, Path]:
    path = tmp_path / "script.json"
    log = tmp_path / "log.txt"
    path.write_text(json.dumps(script))
    return StockfishEngine([sys.executable, str(FAKE), str(path), str(log)]), log


def _request(multipv: int = 2, root_moves=None, cap_ms: int = 2000) -> SearchRequest:
    return SearchRequest(
        input=START,
        profile=EngineProfile(depth=12, time_cap_ms=cap_ms),
        root_moves=root_moves,
        multipv=multipv,
    )


def _line(rank, pv, depth=12, score="cp 20", bound="", wdl=" wdl 100 800 100"):
    return (
        f"info depth {depth} seldepth {depth + 4} multipv {rank} score {score}{bound}{wdl} "
        f"nodes 1000 nps 1 hashfull 0 tbhits 0 time 5 pv {pv}"
    )


def test_last_line_per_rank_is_kept_and_never_merged(tmp_path) -> None:
    engine, _log = _engine(
        tmp_path,
        searches=[
            [
                _line(1, "e2e4 e7e5", depth=11, bound=" lowerbound", wdl=" wdl 300 400 300"),
                _line(2, "d2d4", depth=11),
                _line(1, "e2e4 e7e5 g1f3", depth=12, score="cp 31", wdl=" wdl 10 980 10"),
                _line(2, "d2d4 d7d5", depth=12, score="cp 25"),
            ]
        ],
    )
    with engine:
        raw = engine.search(_request())
    first = raw.lines[0]
    assert (first.depth, first.score, first.bound, first.wdl) == (
        12,
        ("cp", 31),
        Bound.EXACT,
        (10, 980, 10),
    )
    assert first.pv == ("e2e4", "e7e5", "g1f3") and raw.stopped_by is StoppedBy.DEPTH


@pytest.mark.parametrize("pv", ["e2e4 e7e5 e1e3", "e2e4 0000", "e2e4 Nf6", "e2e4 e7e5x"])
def test_bad_pv_tokens_are_passed_on_and_refused_by_normalization(tmp_path, pv) -> None:
    engine, _log = _engine(tmp_path, searches=[[_line(1, pv), _line(2, "d2d4")]])
    with engine:
        raw = engine.search(_request())
    assert raw.lines[0].pv == tuple(pv.split())  # nothing dropped by the adapter
    with pytest.raises(EngineOutputError):
        normalize(raw, _request(), SearchKind.SURVEY, engine.identity)


def test_scored_line_without_pv_is_refused(tmp_path) -> None:
    engine, _log = _engine(
        tmp_path, searches=[["info depth 12 multipv 1 score cp 10 nodes 5", _line(2, "d2d4")]]
    )
    with engine, pytest.raises(EngineOutputError, match="without pv"):
        engine.search(_request())


def test_rank_gap_and_excess_are_refused_fewer_are_passed_on(tmp_path) -> None:
    engine, _log = _engine(
        tmp_path,
        searches=[
            [_line(1, "e2e4"), _line(3, "d2d4")],
            [_line(1, "e2e4"), _line(2, "d2d4"), _line(3, "c2c4")],
            [_line(1, "e2e4")],
        ],
    )
    with engine:
        with pytest.raises(EngineOutputError, match="gap"):
            engine.search(_request())
        with pytest.raises(EngineOutputError, match="exceed"):
            engine.search(_request())
        raw = engine.search(_request())
    assert len(raw.lines) == 1
    with pytest.raises(EngineOutputError, match="depth-stopped"):
        normalize(raw, _request(), SearchKind.SURVEY, engine.identity)


def test_missing_wdl_while_set_is_refused(tmp_path) -> None:
    engine, _log = _engine(tmp_path, searches=[[_line(1, "e2e4", wdl=""), _line(2, "d2d4")]])
    with engine:
        raw = engine.search(_request())
    with pytest.raises(EngineOutputError, match="wdl"):
        normalize(raw, _request(), SearchKind.SURVEY, engine.identity)


def test_wrong_engine_name_is_refused(tmp_path) -> None:
    with pytest.raises(EngineUnsupportedError):
        _engine(tmp_path, name="Stockfish 17.1")


def test_start_error_is_refused(tmp_path) -> None:
    with pytest.raises(EngineError, match="ERROR"):
        _engine(tmp_path, start_error=True)


def test_process_death_raises(tmp_path) -> None:
    engine, _log = _engine(tmp_path, die_on_go=True)
    with pytest.raises(EngineError):
        engine.search(_request())
    engine.close()


def test_cap_sends_stop_and_yields_time(tmp_path) -> None:
    engine, log = _engine(tmp_path, hang=True, searches=[[_line(1, "e2e4", depth=9)]])
    with engine:
        raw = engine.search(_request(multipv=1, cap_ms=200))
    assert raw.stopped_by is StoppedBy.TIME and "stop" in log.read_text().split("\n")
    search = normalize(raw, _request(multipv=1, cap_ms=200), SearchKind.SURVEY, engine.identity)
    assert not search.regular


def test_time_even_at_full_depth_is_irregular(tmp_path) -> None:
    engine, _log = _engine(tmp_path, hang=True, searches=[[_line(1, "e2e4"), _line(2, "d2d4")]])
    with engine:
        raw = engine.search(_request(cap_ms=100))
    assert all(line.depth == 12 for line in raw.lines)
    assert not normalize(raw, _request(cap_ms=100), SearchKind.SURVEY, engine.identity).regular


PER_SEARCH = [
    "setoption name Hash value 16",
    "setoption name MultiPV value {k}",
    "setoption name UCI_ShowWDL value true",
    "setoption name SyzygyPath value <empty>",
    "setoption name Skill Level value 20",
    "setoption name UCI_LimitStrength value false",
    "setoption name UCI_Elo value 1320",
    "setoption name nodestime value 0",
    "setoption name UCI_Chess960 value false",
    "setoption name Ponder value false",
    "ucinewgame",
    "setoption name Clear Hash",
    "isready",
]


def test_command_sequence_and_pinned_options(tmp_path) -> None:
    engine, log = _engine(
        tmp_path, searches=[[_line(1, "e2e4")], [_line(1, "e7e5"), _line(2, "d7d5")]]
    )
    windowed = window_input(chess.Board(), ("e2e4",), 1)
    with engine:
        engine.search(_request(multipv=1, root_moves=("e2e4",)))
        engine.search(SearchRequest(windowed, EngineProfile(), None, 2))
    commands = [c for c in log.read_text().split("\n") if c]
    first = [
        *[c.format(k=1) for c in PER_SEARCH],
        f"position fen {START.fen}",
        "go depth 12 searchmoves e2e4",
    ]
    second = [
        *[c.format(k=2) for c in PER_SEARCH],
        f"position fen {windowed.fen} moves e2e4",
        "go depth 12",
    ]
    assert commands == [
        "uci",
        "setoption name Threads value 1",
        "setoption name EvalFile value nn-test.nnue",
        "isready",
        *first,
        *second,
        "quit",
    ]


def test_refused_search_leaves_the_engine_usable(tmp_path) -> None:
    engine, _log = _engine(
        tmp_path,
        searches=[[_line(1, "e2e4"), _line(3, "d2d4")], [_line(1, "e2e4"), _line(2, "d2d4")]],
    )
    with engine:
        with pytest.raises(EngineOutputError):
            engine.search(_request())
        assert len(engine.search(_request()).lines) == 2


@pytest.mark.parametrize("missing", ["seldepth", "nodes", "tbhits"])
def test_missing_fields_are_refused_never_invented(tmp_path, missing) -> None:
    line = _line(1, "e2e4")
    tokens = line.split()
    at = tokens.index(missing)
    del tokens[at : at + 2]
    engine, _log = _engine(tmp_path, searches=[[" ".join(tokens)]])
    with engine, pytest.raises(EngineOutputError, match="missing"):
        engine.search(_request(multipv=1))


def test_strict_info_parsing(tmp_path) -> None:
    engine, _log = _engine(
        tmp_path,
        searches=[
            [
                "info depth 12 seldepth 14 multipv 1 score cp 20 score cp 99 nodes 1 tbhits 0 pv e2e4"
            ],
            ["info depth 12 seldepth 14 multipv 1 nodes 1 tbhits 0 pv e2e4"],
            ["info string score 5 is not a line", _line(1, "e2e4")],
        ],
    )
    with engine:
        with pytest.raises(EngineOutputError, match="repeated"):
            engine.search(_request(multipv=1))
        with pytest.raises(EngineOutputError, match="without score"):
            engine.search(_request(multipv=1))
        assert engine.search(_request(multipv=1)).lines[0].pv == ("e2e4",)


def test_no_readyok_and_no_bestmove_after_stop_raise(tmp_path, monkeypatch) -> None:
    from calliope.facts.search import uci

    monkeypatch.setattr(uci, "READY_TIMEOUT_S", 0.5)
    monkeypatch.setattr(uci, "STOP_TIMEOUT_S", 0.5)
    engine, _log = _engine(tmp_path, no_readyok_after_start=True, searches=[[_line(1, "e2e4")], []])
    with engine:
        engine.search(_request(multipv=1))
        with pytest.raises(EngineError, match="readyok"):
            engine.search(_request(multipv=1))
        with pytest.raises(EngineError):
            engine.search(_request(multipv=1))  # the timed-out process is not trusted again
    engine, _log = _engine(tmp_path, hang=True, ignore_stop=True, searches=[[_line(1, "e2e4")]])
    with engine, pytest.raises(EngineError, match="bestmove"):
        engine.search(_request(multipv=1, cap_ms=100))


def test_missing_binary_is_an_engine_error() -> None:
    with pytest.raises(EngineError, match="cannot start"):
        StockfishEngine(["/nonexistent/stockfish"])
