"""The game pipeline and the ply cache (AS-D §3, §4; tests 1–3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest
from helpers import PROMOTION, RATED, UNRATED, slot
from synthetic import engine

from calliope.facts import EngineProfile, EngineResultStore, FactEngine, PositionRecords
from calliope.reasoning import Reasoner
from calliope.reasoning.storage import save
from calliope.results import dumps, schema
from calliope.server import (
    InputError,
    JobFailed,
    PlyCache,
    analyse_game,
    normalized_ply,
    parse_game,
    plies_range,
    ply_request,
)
from calliope.server import cache as cache_module
from tools.explain_game.__main__ import explain_game

PROFILE = EngineProfile()


def _run(parsed, plies, cache, the_slot=None):
    the_slot = the_slot if the_slot is not None else slot()[0]
    progress = []
    document = analyse_game(the_slot, parsed, plies, cache, on_ply=progress.append)
    return document, progress


def test_1_the_pipeline_matches_the_tool(tmp_path) -> None:
    """Same texts and the same bundle bytes as `tools/explain_game` (AS-D §3: unchanged)."""

    parsed = parse_game(RATED)
    document, _ = _run(parsed, range(1, 5), PlyCache(tmp_path))
    jsonschema.validate(document, schema(), cls=jsonschema.Draft202012Validator)
    records, tool_document = explain_game(engine(), RATED, plies="1-4", digests=True)
    assert [p["text"] for p in document["plies"]] == [r["text"] for r in records]
    assert [p["bundle"]["graph"] for p in document["plies"]] == [
        r["bundle"]["graph"] for r in records
    ]
    assert [p["bundle"]["stored"] for p in document["plies"]] == [True] * 4
    assert document["game"] == tool_document["game"]
    assert document["grading"] == tool_document["grading"]


@pytest.mark.parametrize(("pgn", "ply"), [(UNRATED, 3), (UNRATED, 9), (RATED, 6), (PROMOTION, 1)])
def test_2_the_normalized_request_is_the_recorded_one(pgn, ply) -> None:
    """Review B1: a capture (3), castling (9), a rated game, a FEN header with a promotion."""

    parsed = parse_game(pgn)
    analysis = Reasoner(FactEngine(engine=engine())).analyse(ply_request(parsed, ply, PROFILE))
    expected = normalized_ply(parsed, ply, PROFILE)
    assert analysis.round_zero.request == expected
    assert expected.root.fen is not None and expected.moves == parsed.uci[:ply]
    assert ply_request(parsed, ply, PROFILE) != expected  # SAN, and maybe no FEN, in the raw one


def test_2_the_moves_after_the_target_change_no_byte() -> None:
    parsed = parse_game(UNRATED)
    full = Reasoner(FactEngine(engine=engine())).analyse(ply_request(parsed, 5, PROFILE))
    cut = replace(parsed, sans=parsed.sans[:5], uci=parsed.uci[:5])
    prefix = Reasoner(FactEngine(engine=engine())).analyse(ply_request(cut, 5, PROFILE))
    from calliope.reasoning import explain

    assert save(full, explain(full)) == save(prefix, explain(prefix))


def test_2_a_missing_fen_header_and_the_standard_fen_share_a_key() -> None:
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    a = parse_game(UNRATED)
    b = parse_game(f'[FEN "{start}"]\n[SetUp "1"]\n\n{UNRATED}')
    identity, digest = engine().identity, "0" * 64
    assert PlyCache.key(normalized_ply(a, 4, PROFILE), digest, identity, PROFILE) == PlyCache.key(
        normalized_ply(b, 4, PROFILE), digest, identity, PROFILE
    )


def test_3_a_second_run_searches_nothing_and_gives_the_same_bytes(tmp_path) -> None:
    parsed, cache = parse_game(UNRATED), PlyCache(tmp_path)
    first_slot, first_started = slot()
    first, progress = _run(parsed, range(1, 11), cache, first_slot)
    assert first_started[0].calls and not any(p.cached for p in progress)
    again_slot, again_started = slot()
    # a new cache: the second run reads the files, not the pairs the first kept (CC-D §2.2)
    second, progress = _run(parsed, range(1, 11), PlyCache(tmp_path), again_slot)
    assert again_started[0].calls == [] and all(p.cached for p in progress)
    assert dumps(first) == dumps(second)
    assert all(p["bundle"]["stored"] for p in first["plies"] + second["plies"])  # re-review B1


def test_3_a_shared_opening_is_analysed_once(tmp_path) -> None:
    cache = PlyCache(tmp_path)
    _run(parse_game(UNRATED), range(1, 7), cache)
    other = parse_game("1. e4 d5 2. exd5 Nf6 3. Nf3 Nxd5 4. d4 Bg4 *")  # plies 1–6 shared
    _, progress = _run(other, range(1, 9), cache)
    assert [p.cached for p in progress] == [True] * 6 + [False] * 2


def test_3_other_ratings_share_nothing(tmp_path) -> None:
    """S4 (re-review note): every key field must be equal, the grading spec included."""

    cache = PlyCache(tmp_path)
    _run(parse_game(UNRATED), range(1, 3), cache)
    _, progress = _run(parse_game(RATED), range(1, 3), cache)
    assert not any(p.cached for p in progress)


def _key_files(tmp_path, parsed, ply):
    port = engine()
    build = Reasoner(FactEngine(engine=port)).build()
    from calliope.reasoning import build_digest

    expected = normalized_ply(parsed, ply, PROFILE)
    key = PlyCache.key(expected, build_digest(build), port.identity, PROFILE)
    return PlyCache(tmp_path), key, expected, build


@pytest.mark.parametrize("damage", ["graph", "tree", "missing tree", "other build"])
def test_3_damaged_or_foreign_files_are_misses_and_are_replaced(tmp_path, damage) -> None:
    """Review B2: `StoredGraphError`, `StoredTreeError`, a missing file, another build."""

    parsed = parse_game(UNRATED)
    first, _ = _run(parsed, range(1, 3), PlyCache(tmp_path))
    cache, key, expected, build = _key_files(tmp_path, parsed, 2)
    tree_path, graph_path = cache.paths(key)
    assert cache.get(key, expected, build) is not None
    if damage == "graph":
        graph_path.write_bytes(graph_path.read_bytes()[:-40])
    elif damage == "tree":
        tree_path.write_bytes(tree_path.read_bytes().replace(b'"', b"'", 3))
    elif damage == "missing tree":
        tree_path.unlink()
    if damage == "other build":
        assert cache.get(key, expected, replace(build, templates=())) is None
        return
    assert cache.get(key, expected, build) is None
    second, progress = _run(parsed, range(1, 3), cache)
    assert [p.cached for p in progress] == [True, False]  # ply 2 analysed again
    assert cache.get(key, expected, build) is not None  # and replaced
    assert dumps(first) == dumps(second)


def test_3_a_left_over_temporary_file_is_ignored(tmp_path) -> None:
    parsed = parse_game(UNRATED)
    cache, key, expected, build = _key_files(tmp_path, parsed, 1)
    _, graph_path = cache.paths(key)
    graph_path.parent.mkdir(parents=True)
    (graph_path.parent / (graph_path.name + ".tmp")).write_bytes(b"{partial")
    assert cache.get(key, expected, build) is None
    _, progress = _run(parsed, range(1, 2), cache)
    assert [p.cached for p in progress] == [False]
    assert cache.get(key, expected, build) is not None


def test_3_with_verify_writes_a_bundle_that_does_not_re_load_fails_the_job(
    tmp_path, monkeypatch
) -> None:
    """Re-review B1, as CC-D §2.4 keeps it: with `verify_writes` a fresh ply is used only after its
    files re-load; else nothing is kept."""

    from calliope.reasoning import StoredGraphError

    def broken(*args, **kwargs):
        raise StoredGraphError("injected")

    monkeypatch.setattr(cache_module, "load", broken)
    with pytest.raises(JobFailed, match="ply 1 failed its check: StoredGraphError"):
        _run(parse_game(UNRATED), range(1, 3), PlyCache(tmp_path, verify_writes=True))
    left = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(p.suffix == ".lock" for p in left)  # removed; lock files stay (AG-D §9)


def test_3_files_read_back_otherwise_fail_the_job(tmp_path, monkeypatch) -> None:
    """CC-D §2.4: without `verify_writes`, a difference between the bytes written and the bytes
    read back fails the job and removes the files."""

    def other_bytes(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data + b" ")

    monkeypatch.setattr(cache_module, "atomic_write", other_bytes)
    with pytest.raises(JobFailed, match="ply 1 failed its check: StoreFailed: the files read back"):
        _run(parse_game(UNRATED), range(1, 3), PlyCache(tmp_path))
    left = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(p.suffix == ".lock" for p in left)


def test_the_intake_refuses_what_it_cannot_read() -> None:
    with pytest.raises(InputError, match="no game"):
        parse_game("")
    with pytest.raises(InputError, match="cannot be read"):
        parse_game("1. e4 e5 2. Ke3 *")
    with pytest.raises(InputError, match="standard chess"):
        parse_game('[Variant "Atomic"]\n\n1. e4 *')
    assert parse_game(f"{UNRATED}\n\n{UNRATED}").warnings[-1].startswith("only the first game")
    assert parse_game(UNRATED).warnings[0].startswith("graded with the default curve")
    assert parse_game(RATED).warnings == ()
    assert plies_range("3-4", 10) == range(3, 5) and plies_range("8-40", 10) == range(8, 11)
    with pytest.raises(InputError):
        plies_range("three", 10)


def test_the_bundle_digests_are_the_files(tmp_path) -> None:
    parsed = parse_game(UNRATED)
    document, _ = _run(parsed, range(1, 2), PlyCache(tmp_path))
    cache, key, _, _ = _key_files(tmp_path, parsed, 1)
    tree_path, graph_path = cache.paths(key)
    bundle = document["plies"][0]["bundle"]
    assert bundle["tree"] == hashlib.sha256(tree_path.read_bytes()).hexdigest()
    assert bundle["graph"] == hashlib.sha256(graph_path.read_bytes()).hexdigest()


def _tree_digests(root: Path) -> dict[str, list[str]]:
    return {p.stem: json.loads(p.read_bytes())["digests"] for p in root.rglob("*.tree")}


def test_a_process_store_and_memo_give_the_same_plies_and_ask_each_search_once(tmp_path) -> None:
    """PF-D §2, §3, §6: with the process's result store and POSITION records every ply has the
    same claim graph, text and F5 tree digests as without them; each search is asked once; only
    the tree files' bytes may differ (`ReplayRecord.engine_calls`, Q2), and they load."""

    parsed = parse_game(RATED)
    plies = range(1, len(parsed.sans) + 1)
    plain_slot, plain_started = slot()
    plain = analyse_game(plain_slot, parsed, plies, PlyCache(tmp_path / "plain"))
    shared_slot, shared_started = slot()
    store, memo = EngineResultStore(1000), PositionRecords(10_000)
    shared = analyse_game(shared_slot, parsed, plies, PlyCache(tmp_path / "shared"),
                          store=store, memo=memo)  # fmt: skip
    calls = shared_started[0].calls
    assert len({repr(c) for c in calls}) == len(calls) == len(store)  # each search once
    assert len(plain_started[0].calls) > len(calls)
    assert memo.hits > 0

    def without_tree(document):
        return [p | {"bundle": p["bundle"] | {"tree": None}} for p in document["plies"]]

    assert without_tree(shared) == without_tree(plain)
    assert {k: v for k, v in shared.items() if k != "plies"} == {
        k: v for k, v in plain.items() if k != "plies"
    }
    assert _tree_digests(tmp_path / "shared") == _tree_digests(tmp_path / "plain")
    again_slot, again_started = slot()  # the files load and pass F5's replay checks
    progress = []
    analyse_game(again_slot, parsed, plies, PlyCache(tmp_path / "shared"), on_ply=progress.append)
    assert again_started[0].calls == [] and all(p.cached for p in progress)
