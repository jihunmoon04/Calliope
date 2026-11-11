"""RV-1 (docs/design/review-2026-11-11.md): a null move is no move (P4-5), a handle spelling never
issued is no handle (P4-8), ply 0 is refused by the shared range rule (P3-4), a schema pattern's
`$` is the string's end (P3-5), and a run of another build than its references is not bundled
(P6-9)."""

from __future__ import annotations

import json

import chess
import pytest

from calliope.agent.handles import HandleError, HandleExpired
from calliope.agent.sentences import read_move
from calliope.results.validate import _pattern
from calliope.server.pipeline import InputError, plies_range


@pytest.mark.parametrize("text", ["--", "0000", "Z0", "@@@@"])
def test_a_null_move_is_no_move(text) -> None:
    with pytest.raises(ValueError):
        read_move(chess.Board(), text)
    assert read_move(chess.Board(), "e4") == chess.Move.from_uci("e2e4")


def test_a_spelling_never_issued_is_no_handle() -> None:
    from calliope.agent.handles import Handles

    handles = Handles()
    ref = handles.serve("c", "g", {"kind": "analysis"}, {"claim": 1}, {})
    token = ref.split(".", 1)[1]
    for spelling in (f"c0.{token}", f"c01.{token}", f"c9.{token}"):
        with pytest.raises(HandleError) as raised:
            handles.resolve(spelling)
        assert not isinstance(raised.value, HandleExpired), spelling


@pytest.mark.parametrize("text", ["0", "0-2"])
def test_ply_zero_is_refused_by_the_range_rule(text) -> None:
    with pytest.raises(InputError):
        plies_range(text, 10)
    assert plies_range("1-3", 10) == range(1, 4)


def test_a_patterns_end_is_the_strings_end() -> None:
    digest = _pattern("^[0-9a-f]{64}$")
    assert digest.search("a" * 64) and not digest.search("a" * 64 + "\n")


def test_a_run_of_another_build_is_not_bundled(tmp_path, monkeypatch) -> None:
    from tools.rx import judge

    refs = tmp_path / "refs" / "train"
    refs.mkdir(parents=True)
    (refs / "g1-3.json").write_text(json.dumps({"build_id": "B1", "key_causes": []}))
    run = tmp_path / "R1"
    run.mkdir()
    (run / "agent.jsonl").write_text(json.dumps(
        {"seq": 1, "type": "start", "arm": "H", "set": "train", "game": "g1", "moments": [3]}) + "\n")  # fmt: skip
    (run / "tools.jsonl").write_text("\n".join(json.dumps(x) for x in [
        {"seq": 1, "type": "build", "build_id": "B2"},
        {"seq": 2, "type": "submission", "call_id": 1,
         "subjects": [{"game_ply": 3, "outcome": "accepted", "submitted": {"sentences": [{"text": "a"}]}}]}]) + "\n")  # fmt: skip
    monkeypatch.setattr(judge, "REFERENCES", tmp_path / "refs")
    with pytest.raises(ValueError, match="its build is not"):
        judge.bundle([run], "J1", seed=1, root=tmp_path / "judging", keys=tmp_path / "keys")
