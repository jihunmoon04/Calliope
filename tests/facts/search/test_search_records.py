"""F4-D §9.1.2–§9.1.6: normalization, regularity, `EngineInput`, `SearchId`, store."""

import subprocess
import sys
import threading

import chess
import pytest

from calliope.facts import PLAYED, ExtendRequest, FactEngine, InputLine, OpenRequest, RootSpec
from calliope.facts.errors import EngineOutputError, InvalidRequestError
from calliope.facts.keys import Color
from calliope.facts.search import (
    Bound,
    Cp,
    EngineIdentity,
    EngineOption,
    EngineProfile,
    EngineResultStore,
    Mate,
    RawLine,
    RawSearch,
    ReuseSource,
    ScriptedEngine,
    Searcher,
    SearchKind,
    SearchRequest,
    StoppedBy,
    Wdl,
    node_input,
    normalize,
    request_key,
    window_input,
)
from calliope.facts.values import UNAVAILABLE

OPTIONS = (
    EngineOption("Threads", "spin", "1"),
    EngineOption("Hash", "spin", "16"),
    EngineOption("MultiPV", "spin", "1"),
    EngineOption("UCI_ShowWDL", "check", "false"),
    EngineOption("EvalFile", "string", "nn-test.nnue"),
)
IDENTITY = EngineIdentity("Stockfish 19", "test", "0" * 64, OPTIONS)
NO_WDL = EngineIdentity("Stockfish 19", "test", "0" * 64, OPTIONS[:3])
PROFILE = EngineProfile()


def _raw(*lines: RawLine, stopped=StoppedBy.DEPTH) -> RawSearch:
    return RawSearch(tuple(lines), stopped, 10)


def _line(rank, pv, score=("cp", 20), depth=12, bound=Bound.EXACT, wdl=(100, 800, 100)):
    return RawLine(rank, depth, depth + 3, score, bound, wdl, 1000, 0, tuple(pv.split()))


def _request(fen=chess.STARTING_FEN, moves=(), multipv=2, roots=None):
    return SearchRequest(window_input(chess.Board(fen), moves, 100), PROFILE, roots, multipv)


# -- normalization ----------------------------------------------------------------------------


def test_scores_and_wdl_are_from_whites_view() -> None:
    black = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    raw = _raw(_line(1, "e7e5", ("cp", 30), wdl=(500, 400, 100)), _line(2, "d7d5", ("mate", 3)))
    search = normalize(raw, _request(black), SearchKind.SURVEY, IDENTITY)
    first, second = search.lines
    assert first.score == Cp(-30) and first.wdl == Wdl(100, 400, 500)
    assert second.score == Mate(Color.BLACK, 3)
    raw = _raw(_line(1, "e2e4", ("mate", -2)), _line(2, "d2d4"))
    assert normalize(raw, _request(), SearchKind.SURVEY, IDENTITY).lines[0].score == Mate(
        Color.BLACK, 2
    )


def test_mate_zero_is_refused() -> None:
    with pytest.raises(EngineOutputError, match="mate 0"):
        normalize(
            _raw(_line(1, "e2e4", ("mate", 0)), _line(2, "d2d4")),
            _request(),
            SearchKind.SURVEY,
            IDENTITY,
        )


def test_wdl_unavailable_only_when_not_offered() -> None:
    raw = _raw(_line(1, "e2e4", wdl=None), _line(2, "d2d4", wdl=None))
    search = normalize(raw, _request(), SearchKind.SURVEY, NO_WDL)
    assert all(line.wdl is UNAVAILABLE for line in search.lines)
    with pytest.raises(EngineOutputError, match="wdl"):
        normalize(raw, _request(), SearchKind.SURVEY, IDENTITY)


@pytest.mark.parametrize(
    ("lines", "match"),
    [
        ((_line(2, "e2e4"), _line(1, "d2d4")), "1..j"),
        ((_line(1, "e2e4"),), "depth-stopped"),
        ((_line(1, "e2e4"), _line(2, "e2e4")), "duplicate"),
        ((_line(1, "e2e4 e7e5 e1e3"), _line(2, "d2d4")), "illegal"),
        ((_line(1, "e2e4 0000"), _line(2, "d2d4")), "null"),
        ((_line(1, "e4"), _line(2, "d2d4")), "not UCI"),
    ],
)
def test_bad_lines_are_refused(lines, match) -> None:
    with pytest.raises(EngineOutputError, match=match):
        normalize(_raw(*lines), _request(), SearchKind.SURVEY, IDENTITY)


def test_restriction_and_k() -> None:
    request = _request(multipv=2, roots=("a2a3", "h2h3"))
    with pytest.raises(EngineOutputError, match="outside"):
        normalize(
            _raw(_line(1, "e2e4"), _line(2, "h2h3")), request, SearchKind.COMPARISON, IDENTITY
        )
    one_legal = "7k/8/8/8/8/8/6q1/7K w - - 0 1"
    search = normalize(
        _raw(_line(1, "h1g2", ("cp", 0))),
        _request(one_legal, multipv=5),
        SearchKind.SURVEY,
        IDENTITY,
    )
    assert [line.move for line in search.lines] == ["h1g2"]


def test_time_stopped_may_report_fewer_ranks() -> None:
    raw = _raw(_line(1, "e2e4", depth=1), stopped=StoppedBy.TIME)
    search = normalize(raw, _request(), SearchKind.SURVEY, IDENTITY)
    assert not search.regular and len(search.lines) == 1


# -- regularity ---------------------------------------------------------------------------------


def test_regularity() -> None:
    exact = (_line(1, "e2e4"), _line(2, "d2d4"))
    assert normalize(_raw(*exact), _request(), SearchKind.SURVEY, IDENTITY).regular
    assert not normalize(
        _raw(*exact, stopped=StoppedBy.TIME), _request(), SearchKind.SURVEY, IDENTITY
    ).regular
    bound = (_line(1, "e2e4", bound=Bound.LOWER), _line(2, "d2d4"))
    assert not normalize(_raw(*bound), _request(), SearchKind.SURVEY, IDENTITY).regular
    shallow = (_line(1, "e2e4", depth=11), _line(2, "d2d4"))
    assert not normalize(_raw(*shallow), _request(), SearchKind.SURVEY, IDENTITY).regular


# -- EngineInput ----------------------------------------------------------------------------------


def test_window_length_and_form() -> None:
    history = ("e2e4", "e7e5", "g1f3", "b8c6", "f3g1", "c6b8")
    full = window_input(chess.Board(), history, 4)
    board = chess.Board()
    for uci in history[:2]:
        board.push_uci(uci)
    assert full.moves == history[2:]
    assert full.fen == board.fen().rsplit(" ", 1)[0] + " 1"
    assert window_input(chess.Board(), history, 0).moves == ()
    assert window_input(chess.Board(), history, 50).moves == history  # incomplete: whole history


def test_start_board_with_pseudo_legal_en_passant_and_fullmove() -> None:
    start = chess.Board("7k/8/8/KPp4r/8/8/8/8 w - c6 0 37")
    before = start.fen()
    engine_input = window_input(start, (), 0)
    assert engine_input.fen == "7k/8/8/KPp4r/8/8/8/8 w - - 0 1"
    assert start.fen() == before  # never mutated


def test_node_input_across_the_root() -> None:
    tree = FactEngine().open(OpenRequest(root=RootSpec(moves=("e4", "e5", "Nf3"))))
    FactEngine().extend(tree, ExtendRequest((InputLine("g", ("Nc6", "Ng1", "Nb8")),), PLAYED))
    node = tree.view().input_line("g").nodes[-1]
    engine_input = node_input(tree, node)
    # the clock was reset by e5 (pre-root): window = Nf3 (pre-root) + the three tree moves
    assert engine_input.moves == ("g1f3", "b8c6", "f3g1", "c6b8")
    assert tree._session.start_board.fen() == chess.STARTING_FEN


# -- SearchId and store ---------------------------------------------------------------------------


def test_search_id_changes_with_every_preimage_field() -> None:
    from dataclasses import replace

    base = _request()
    key = request_key(base, SearchKind.SURVEY, IDENTITY)
    other_fen = SearchRequest(
        window_input(chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1"), (), 0), PROFILE, None, 2
    )
    variants = {
        "kind": request_key(base, SearchKind.COMPARISON, IDENTITY),
        "fen": request_key(other_fen, SearchKind.SURVEY, IDENTITY),
        "moves": request_key(_request(moves=("e2e4",)), SearchKind.SURVEY, IDENTITY),
        "multipv": request_key(_request(multipv=3), SearchKind.SURVEY, IDENTITY),
        "roots": request_key(_request(roots=("d2d4", "e2e4")), SearchKind.SURVEY, IDENTITY),
    }
    for field, value in (
        ("name", "other"),
        ("depth", 13),
        ("time_cap_ms", 1000),
        ("hash_mb", 32),
        ("multipv", 4),
    ):
        profile = replace(PROFILE, **{field: value})
        variants[f"profile.{field}"] = request_key(
            SearchRequest(base.input, profile, None, 2), SearchKind.SURVEY, IDENTITY
        )
    for field, value in (
        ("name", "Stockfish 19 other"),
        ("author", "other"),
        ("binary_sha256", "1" * 64),
        ("options", (*OPTIONS[:-1], EngineOption("EvalFile", "string", "nn-other.nnue"))),
    ):
        identity = replace(IDENTITY, **{field: value})
        variants[f"identity.{field}"] = request_key(base, SearchKind.SURVEY, identity)
    # the pinned options alone: an offered option that is pinned per search
    elo = replace(IDENTITY, options=(*OPTIONS, EngineOption("UCI_Elo", "spin", "1320")))
    elo2 = replace(IDENTITY, options=(*OPTIONS, EngineOption("UCI_Elo", "spin", "1500")))
    variants["pinned"] = request_key(base, SearchKind.SURVEY, elo)
    variants["pinned2"] = request_key(base, SearchKind.SURVEY, elo2)
    values = list(variants.values())
    assert key not in values and len(set(values)) == len(values)


def test_search_id_is_stable_across_processes() -> None:
    code = (
        "import chess;from calliope.facts.search import *;"
        "from test_search_records import IDENTITY, _request;"
        "print(request_key(_request(), SearchKind.SURVEY, IDENTITY))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        cwd=__file__.rsplit("/", 1)[0],
    )
    assert out.stdout.strip() == request_key(_request(), SearchKind.SURVEY, IDENTITY)


def test_irregular_ids_include_the_lines() -> None:
    a = normalize(
        _raw(_line(1, "e2e4", depth=9), stopped=StoppedBy.TIME),
        _request(),
        SearchKind.SURVEY,
        IDENTITY,
    )
    b = normalize(
        _raw(_line(1, "d2d4", depth=9), stopped=StoppedBy.TIME),
        _request(),
        SearchKind.SURVEY,
        IDENTITY,
    )
    regular = normalize(
        _raw(_line(1, "e2e4"), _line(2, "d2d4")), _request(), SearchKind.SURVEY, IDENTITY
    )
    assert len({a.search_id, b.search_id, regular.search_id}) == 3
    assert regular.search_id == request_key(_request(), SearchKind.SURVEY, IDENTITY)


def _answer(request: SearchRequest) -> RawSearch:
    if request.input.moves == ("g1f3",):
        return _raw(_line(1, "e7e5", depth=8), stopped=StoppedBy.TIME)
    return _raw(
        *(_line(i, uci) for i, uci in enumerate(("e2e4", "d2d4", "c2c4", "b2b3", "a2a3"), 1))
    )


def test_store_hit_runs_no_engine_and_irregular_is_session_only() -> None:
    store = EngineResultStore()
    engine = ScriptedEngine(IDENTITY, _answer)
    first = Searcher(engine, store, PROFILE)
    start = window_input(chess.Board(), (), 0)
    search, reused, _ = first.search(start, SearchKind.SURVEY)
    assert reused is None and len(store) == 1 and len(engine.calls) == 1
    second = Searcher(engine, store, PROFILE)
    again, reused, _ = second.search(start, SearchKind.SURVEY)
    assert again is search and reused is ReuseSource.STORE and len(engine.calls) == 1
    odd = window_input(chess.Board(), ("g1f3",), 1)
    irregular, _, _ = first.search(odd, SearchKind.SURVEY)
    assert not irregular.regular and len(store) == 1
    pending, reused, _ = first.search(odd, SearchKind.SURVEY)  # pending request reuse
    assert pending is irregular and reused is ReuseSource.SESSION
    first.discard()
    redo, _, _ = first.search(odd, SearchKind.SURVEY)
    assert len(engine.calls) == 3
    first.commit()
    assert first.search(odd, SearchKind.SURVEY)[0] is redo
    other_session = Searcher(engine, store, PROFILE)
    other_session.search(odd, SearchKind.SURVEY)
    assert len(engine.calls) == 4  # irregular searches are never shared through the store


def test_store_is_thread_safe() -> None:
    store = EngineResultStore()
    engine = ScriptedEngine(IDENTITY, _answer)
    inputs = [window_input(chess.Board(), (), 0), window_input(chess.Board(), ("g1f3", "g8f6"), 2)]
    results: list[str] = []

    def run() -> None:
        searcher = Searcher(engine, store, PROFILE)
        for engine_input in inputs * 20:
            results.append(searcher.search(engine_input, SearchKind.SURVEY)[0].search_id)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(results)) == 2 and len(store) == 2


def test_profile_rejects_threads_above_one() -> None:
    with pytest.raises(InvalidRequestError):
        EngineProfile(threads=2)


def test_bounds_are_from_whites_view() -> None:
    black = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    raw = _raw(
        _line(1, "e7e5", ("cp", 30), bound=Bound.LOWER),
        _line(2, "d7d5", bound=Bound.UPPER),
        stopped=StoppedBy.TIME,
    )
    first, second = normalize(raw, _request(black), SearchKind.SURVEY, IDENTITY).lines
    assert (first.score, first.bound) == (Cp(-30), Bound.UPPER)  # Black >= +30: White <= -30
    assert second.bound is Bound.LOWER
    white = normalize(
        _raw(_line(1, "e2e4", bound=Bound.LOWER), _line(2, "d2d4"), stopped=StoppedBy.TIME),
        _request(),
        SearchKind.SURVEY,
        IDENTITY,
    )
    assert white.lines[0].bound is Bound.LOWER


def test_irregular_id_includes_the_stop_reason() -> None:
    lines = (_line(1, "e2e4", bound=Bound.LOWER), _line(2, "d2d4"))
    depth = normalize(_raw(*lines), _request(), SearchKind.SURVEY, IDENTITY)
    time_ = normalize(_raw(*lines, stopped=StoppedBy.TIME), _request(), SearchKind.SURVEY, IDENTITY)
    assert not depth.regular and not time_.regular and depth.search_id != time_.search_id


def test_the_session_answer_wins_over_a_later_stored_one() -> None:
    store = EngineResultStore()
    question = window_input(chess.Board(), ("g1f3",), 1)
    irregular = ScriptedEngine(IDENTITY, _answer)
    first = Searcher(irregular, store, PROFILE)
    mine, _, _ = first.search(question, SearchKind.SURVEY)
    first.commit()
    regular_lines = _raw(
        *(_line(i, u) for i, u in enumerate(("e7e5", "d7d5", "c7c5", "b7b6", "a7a6"), 1))
    )
    second = Searcher(ScriptedEngine(IDENTITY, lambda r: regular_lines), store, PROFILE)
    theirs, _, _ = second.search(question, SearchKind.SURVEY)
    assert theirs.regular and not mine.regular and len(store) == 1
    again, reused, _ = first.search(question, SearchKind.SURVEY)
    assert again is mine and reused is ReuseSource.SESSION


def test_discard_rolls_back_engine_calls() -> None:
    searcher = Searcher(ScriptedEngine(IDENTITY, _answer), EngineResultStore(), PROFILE)
    searcher.search(window_input(chess.Board(), (), 0), SearchKind.SURVEY)
    searcher.commit()
    searcher.search(window_input(chess.Board(), ("g1f3",), 1), SearchKind.SURVEY)
    assert searcher.engine_calls == 2
    searcher.discard()
    assert searcher.engine_calls == 1


def test_root_moves_are_validated_before_the_engine() -> None:
    engine = ScriptedEngine(IDENTITY, _answer)
    searcher = Searcher(engine, EngineResultStore(), PROFILE)
    start = window_input(chess.Board(), (), 0)
    for roots in ((), ("e2e5",), ("e1h1",)):
        with pytest.raises(InvalidRequestError):
            searcher.search(start, SearchKind.COMPARISON, roots, multipv=1)
    assert engine.calls == []
    with pytest.raises(EngineOutputError, match="not all legal"):
        normalize(
            _raw(_line(1, "e2e4")),
            _request(multipv=1, roots=("e2e5",)),
            SearchKind.COMPARISON,
            IDENTITY,
        )


def test_wdl_must_be_three_permille_parts() -> None:
    with pytest.raises(EngineOutputError, match="permille"):
        normalize(
            _raw(_line(1, "e2e4", wdl=(1, 1, 1)), _line(2, "d2d4")),
            _request(),
            SearchKind.SURVEY,
            IDENTITY,
        )


def test_store_returns_the_first_record() -> None:
    store = EngineResultStore()
    a = normalize(_raw(_line(1, "e2e4"), _line(2, "d2d4")), _request(), SearchKind.SURVEY, IDENTITY)
    b = normalize(_raw(_line(1, "e2e4"), _line(2, "d2d4")), _request(), SearchKind.SURVEY, IDENTITY)
    assert store.put(a) is a and store.put(b) is a
