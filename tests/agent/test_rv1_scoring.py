"""RV-1 (docs/design/review-2026-11-11.md), the scoring side: the audit's relative steps out (P6-1)
and its part directory (P6-6), a judging checked against the key, not the part's own files (P6-2),
evidence for a material count over an engine line (P6-4), and no handle in a bundle (P6-8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rx import evidence, judge

PART = "D:/00_x/rx-judging/J/part01"


def _bash(command: str) -> list[dict]:
    return [{"tool": "Bash", "input": {"command": command}}]


@pytest.mark.parametrize("command", [
    "cd .. && cat part02/judging.json",
    "Get-Content ..\\part02\\bundle.json",
    "Set-Location ..\\..; Get-Content 0a1b2c3d\\part01\\judging.json",
    "python -c \"import os; os.chdir('..'); print(open('part02/judging.json').read())\"",
    "cd ~ && ls",
    "cd && ls",
    "pushd /tmp",
])  # fmt: skip
def test_the_audit_flags_a_relative_step_out(command) -> None:
    assert judge.audit(_bash(command), PART), command


@pytest.mark.parametrize("command", [
    f'cd "{PART}" && cat bundle.json',
    "cd references && ls",
    "python -c \"s='17...Rxe3'; t = '...'; print(s, t)\"",
    "python check.py --range 1..5",
])  # fmt: skip
def test_the_audit_still_passes_what_stays_inside(command) -> None:
    assert judge.audit(_bash(command), PART) == [], command


def test_an_audit_reads_only_against_the_judgings_own_part_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(judge, "JUDGING_ROOT", tmp_path / "rx-judging")
    expected = judge.expected_part_dir("abcd1234", 1, tmp_path / "rx-judging")
    assert expected.endswith("rx-judging/abcd1234/part01")
    zip_path = tmp_path / "t.zip"
    import zipfile

    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("s.jsonl", "")
    keys = tmp_path / "keys"
    (keys / "abcd1234").mkdir(parents=True)
    for wrong in (tmp_path / "rx-judging", Path("D:/"), tmp_path / "rx-judging" / "abcd1234" / "part02"):
        with pytest.raises(ValueError, match="part 1 of abcd1234"):
            judge.record_audit("abcd1234", 1, zip_path, wrong, keys)
    right = judge.record_audit("abcd1234", 1, zip_path, tmp_path / "rx-judging" / "abcd1234" / "part01", keys)
    assert right["passed"] is True


def _bundle(tmp_path, monkeypatch) -> tuple[Path, Path]:
    refs = tmp_path / "refs"
    (refs / "train").mkdir(parents=True)
    (refs / "train" / "g1-3.json").write_text(json.dumps({"key_causes": [{"text": "a"}, {"text": "b"}]}))
    run = tmp_path / "runs" / "R1"
    run.mkdir(parents=True)
    (run / "agent.jsonl").write_text(json.dumps(
        {"seq": 1, "type": "start", "arm": "H", "set": "train", "game": "g1", "moments": [3]}) + "\n")  # fmt: skip
    (run / "tools.jsonl").write_text(json.dumps(
        {"seq": 2, "type": "submission", "call_id": 1,
         "subjects": [{"game_ply": 3, "outcome": "accepted",
                       "submitted": {"sentences": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}}]}) + "\n")  # fmt: skip
    monkeypatch.setattr(judge, "REFERENCES", refs)
    judge.bundle([run], "J1", seed=1, root=tmp_path / "judging", keys=tmp_path / "keys")
    part = tmp_path / "judging" / "J1" / "part01"
    (tmp_path / "keys" / "J1" / "audit-part01.json").write_text(json.dumps({"passed": True}))
    return part, tmp_path / "keys"


def _judging(part: Path, sentences: int, causes: int) -> None:
    key = json.loads((part / "bundle.json").read_text())["items"][0]["key"]
    doc = {"items": [{"key": key, "sentences": [{"n": n, "verdict": "ok"} for n in range(1, sentences + 1)],
                      "causes": [{"cause": c} for c in range(1, causes + 1)]}]}  # fmt: skip
    (part / "judging.json").write_text(json.dumps(doc))


def test_a_judging_is_checked_against_the_key_not_the_parts_own_files(tmp_path, monkeypatch) -> None:
    import jsonschema

    monkeypatch.setattr(jsonschema, "validate", lambda doc, schema: None)
    part, keys = _bundle(tmp_path, monkeypatch)
    _judging(part, 3, 2)
    assert judge.checked_judgings("J1", part.parent, keys)  # as bundled: accepted
    bundle = json.loads((part / "bundle.json").read_text())
    bundle["items"][0]["sentences"].pop()  # the judge drops a sentence from its own copy
    (part / "bundle.json").write_text(json.dumps(bundle))
    _judging(part, 2, 2)
    with pytest.raises(ValueError, match="sentences are not judged one each"):
        judge.checked_judgings("J1", part.parent, keys)
    _judging(part, 3, 1)
    (part / "references" / "g1-3.json").write_text(json.dumps({"key_causes": [{"text": "a"}]}))
    with pytest.raises(ValueError, match="was changed"):
        judge.checked_judgings("J1", part.parent, keys)


class _Run:
    def __init__(self, handles):
        self.handles = handles

    def start_fen(self, ref):
        return None

    def plies_origin(self, ref, before):
        return None

    def origin(self, ref, before):
        return "analysis"


def test_a_material_count_over_an_engine_line_gets_its_fen_and_moves() -> None:
    fen = "2Rb4/1k1P4/5rp1/4K2p/p7/8/6PP/3R4 b - - 9 44"
    ref = "s313." + "a" * 24
    run = _Run({ref: {"ref": ref, "address": {"fen": fen}}})
    material = {"kind": "material", "line": ref, "from": 0, "to": 2, "side": "black", "balance": -3}
    line = {"kind": "engine_line", "line": ref, "moves": ["f6c6", "c8d8"]}
    out = evidence.render(material, run, 5, [material, line])
    assert out["start_fen"] == fen and out["moves"] == ["Rc6", "Rxd8"]
    assert len(out["standing_white_after"]) == 2 and out["change"] == -3


def test_no_handle_reaches_a_rendered_proposition() -> None:
    prop = {"kind": "judgement", "judgement": "j1." + "8" * 24, "grade": "mistake", "id": "p1"}
    out = evidence.render(prop, _Run({}), 5)
    assert "judgement" not in out and out["grade"] == "mistake"
    assert not evidence.HANDLE.search(json.dumps(out))
