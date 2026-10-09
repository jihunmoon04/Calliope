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
    EngineResultStore,
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


def test_command_sequence_and_pinned_options(tmp_path) -> None:
    engine, log = _engine(
        tmp_path, searches=[[_line(1, "e2e4")], [_line(1, "d2d4"), _line(2, "e2e4")]]
    )
    with engine:
        engine.search(_request(multipv=1, root_moves=("e2e4",)))
        engine.search(_request(multipv=2))
    commands = log.read_text().split("\n")
    assert commands[:5] == [
        "uci",
        "setoption name Threads value 1",
        "setoption name EvalFile value nn-test.nnue",
        "isready",
        "setoption name Hash value 16",
    ]
    assert commands.count("setoption name EvalFile value nn-test.nnue") == 1  # start only (M11)
    assert commands.count("setoption name Threads value 1") == 1
    first_search = commands[4 : commands.index("go depth 12 searchmoves e2e4") + 1]
    assert first_search == [
        "setoption name Hash value 16",
        "setoption name MultiPV value 1",
        "setoption name UCI_ShowWDL value true",
        "ucinewgame",
        "setoption name Clear Hash",
        "isready",
        f"position fen {START.fen}",
        "go depth 12 searchmoves e2e4",
    ]
    assert "setoption name MultiPV value 2" in commands and commands.count("ucinewgame") == 2


def test_store_and_engine_survive_a_refused_search(tmp_path) -> None:
    engine, _log = _engine(tmp_path, searches=[[_line(1, "e2e4"), _line(3, "d2d4")]])
    store = EngineResultStore()
    with engine, pytest.raises(EngineOutputError):
        engine.search(_request())
    assert len(store) == 0
