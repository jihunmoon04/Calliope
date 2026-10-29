"""`tools/perf_acceptance --compare` (PF-D §6): what it reports."""

from __future__ import annotations

import copy

from tools.perf_acceptance.__main__ import compare


def _run(config="today", calls=3, distinct=3, irregular=0):
    return {
        "config": config,
        "game": "g.pgn",
        "plies": 2,
        "engine_calls": calls,
        "distinct_searches": distinct,
        "irregular": irregular,
        "deadline_skips": 0,
        "deadline_cuts": 0,
        "ply_results": [
            {"ply": 1, "answer": {"text": "1. e4"}, "f5": ["a"]},
            {"ply": 2, "answer": {"text": "1... e5"}, "f5": ["b"]},
        ],
    }


def test_equal_runs_compare_equal() -> None:
    assert compare(_run(calls=5), _run("pf1")) == []


def test_a_changed_answer_or_digest_is_reported() -> None:
    other = _run("pf1")
    other["ply_results"][1]["answer"]["text"] = "1... d5"
    other["ply_results"][0]["f5"] = ["c"]
    assert compare(_run(), other) == ["ply 1: f5 differs", "ply 2: answer differs"]


def test_more_irregular_searches_or_repeated_calls_are_reported() -> None:
    assert compare(_run(), _run("pf1", irregular=1)) == ["irregular: 1 > 0"]
    assert compare(_run(), _run("pf1", calls=4)) == ["engine calls 4 != distinct 3"]


def test_runs_of_other_games_or_without_today_are_refused() -> None:
    other = copy.deepcopy(_run("pf1"))
    other["game"] = "h.pgn"
    assert compare(_run(), other)[0].startswith("not today's run")
    assert compare(_run("pf1"), _run("pf1"))[0].startswith("not today's run")
