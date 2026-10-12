"""Reading and running an acceptance-corpus case (`tests/reasoning/corpus/*.toml`, R4-D §4.1)."""

from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path

from scripted import scripted
from story import WDL, after, line, run

from calliope.reasoning import GradingSpec

CORPUS = Path(__file__).parent / "corpus"


def cases() -> list[dict]:
    return [tomllib.loads(p.read_text()) | {"file": p.name} for p in sorted(CORPUS.glob("*.toml"))]


def _lines(fen: str, specs: list[dict]) -> list:
    out = []
    for s in specs:
        wdl = tuple(s["wdl"]) if "wdl" in s else None
        out.append(line(fen, s["san"], wdl, cp=s.get("cp", 0), mate=s.get("mate")))
    return out


def grading(case: dict) -> GradingSpec:
    spec = case.get("grading")
    return WDL if spec is None else GradingSpec(**spec)


def analyse(case: dict):
    """The case under its scripted engine: S at P from `[[lines]]`, other positions from
    `[[table]]` (each a `fen`, optional `before` SAN, and its own `lines`)."""

    fen, before = case["fen"], case.get("before", "")
    p = after(fen, before)
    table = {}
    for entry in case.get("table", []):
        at = after(entry["fen"], entry.get("before", ""))
        table[at] = _lines(at, entry["lines"])
    lines = _lines(p, case["lines"])
    kwargs = {"before": before, "multipv": case.get("multipv", 2), "grading": grading(case)}
    if case.get("engine_wdl", True):
        return run(fen, case["played"], lines, table=table, **kwargs)
    from test_quality import NO_WDL

    port = scripted({p: lines, **table}, identity=NO_WDL)
    return run(fen, case["played"], [], engine=port, **kwargs)


def stockfish_request(case: dict):
    """The same position for a real engine: no scripted lines, the default profile."""

    from calliope.facts import EngineProfile, RootSpec
    from calliope.reasoning import AnalysisRequest

    moves = (*case.get("before", "").split(), case["played"])
    return AnalysisRequest(
        RootSpec(fen=case["fen"]), moves, len(moves), replace(EngineProfile()),
        grading=grading(case),
    )  # fmt: skip
