"""Scenarios for catalogue v1 tests: a position, the played moves and the lines of S at P.

`run(fen, "a3", [line(...), ...])` analyses the target move `a3` from `fen` (after the moves in
`before`), with the scripted engine answering at P exactly the listed lines, PVs included.
"""

from __future__ import annotations

from dataclasses import replace

import chess
from scripted import scripted

from calliope.facts import EngineProfile, FactEngine, RootSpec
from calliope.reasoning import AnalysisRequest, ReasoningBudget
from calliope.reasoning.runner import Analysis, Reasoner
from calliope.reasoning.verification import Claim, VerdictStatus

S = VerdictStatus.SUPPORTED
R = VerdictStatus.REFUTED
I = VerdictStatus.INCONCLUSIVE


def uci(fen: str, sans: str) -> tuple[str, ...]:
    board = chess.Board(fen)
    out = []
    for san in sans.split():
        move = board.parse_san(san)
        out.append(move.uci())
        board.push(move)
    return tuple(out)


def line(fen: str, sans: str, wdl: tuple[int, int, int], *, cp: int = 0, mate: int | None = None):
    """A line of S at `fen`: its PV in SAN, WDL and score from the side to move."""

    moves = uci(fen, sans)
    score = ("mate", mate) if mate is not None else ("cp", cp)
    return (moves[0], score, wdl, moves)


def after(fen: str, sans: str) -> str:
    board = chess.Board(fen)
    for san in sans.split():
        board.push_san(san)
    return board.fen()


def run(
    fen: str,
    played: str,
    lines: list,
    *,
    before: str = "",
    table: dict | None = None,
    budget: ReasoningBudget | None = None,
    multipv: int = 3,
    templates=None,
    engine=None,
) -> Analysis:
    moves = (*before.split(), played)
    p = after(fen, before)
    answers = {p: lines, **(table or {})}
    port = engine or scripted(answers)
    profile = replace(EngineProfile(), multipv=multipv)
    request = AnalysisRequest(
        RootSpec(fen=fen), moves, len(moves), profile, budget or ReasoningBudget()
    )
    return Reasoner(FactEngine(engine=port), templates).analyse(request)


def claims(analysis: Analysis, template: str) -> list[Claim]:
    return [c for c in analysis.claims if c.hypothesis.template == template]


def claim(analysis: Analysis, template: str) -> Claim:
    (found,) = claims(analysis, template)
    return found


def status(analysis: Analysis, template: str) -> VerdictStatus | None:
    found = claims(analysis, template)
    assert len(found) <= 1, f"{template}: {len(found)} claims"
    return found[0].verdict.status if found else None


def finding(c: Claim, kind: type):
    return next(f for f in c.verdict.findings if isinstance(f, kind))


def table(analysis: Analysis) -> dict[str, tuple]:
    """template → (status, reason) of every claim, for compact assertions."""

    return {c.hypothesis.template: (c.verdict.status, c.verdict.reason) for c in analysis.claims}
