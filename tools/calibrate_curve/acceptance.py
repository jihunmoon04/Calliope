"""Packet Q3 (Q-D §9.12, QM-D Q2 review N1, N2): grades against chess.com Game Review.

`python -m tools.calibrate_curve.acceptance GAMES [--out REPORT]` (needs `CALLIOPE_STOCKFISH_PATH`).
`GAMES` is a PGN file or a folder of PGN files of chess.com games with Game Review's classes as
NAGs or move suffixes: `$6`/`?!` inaccuracy, `$2`/`?` mistake, `$4`/`??` blunder, `$9` miss,
`$3`/`!!` brilliant. Ratings come from `WhiteElo` / `BlackElo` (pool `chesscom`), the time class
from `TimeControl` by Lichess's rule.

Each played move is searched once (round 0 under the table grading), and the same search is
judged under every grading: `quality_v1`, `quality_v2` at `scale = 1000`, the shipped table, and
the shipped table with `cp_ratio_permille = 1000` (review N1). The design game of Q-D §2.1 is left
out unless asked for: it is not evidence of agreement (Q-D B2.4).

`--opera` adds the regression record of Q-D §9.11 (the Opera game, no ratings).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import chess.pgn

from calliope.facts import Color, EngineProfile, FactEngine, Mate, RootSpec
from calliope.reasoning import (
    SHIPPED,
    AnalysisRequest,
    Controller,
    GradingBuild,
    GradingSpec,
    judge,
    load_curve_table,
    resolve,
)
from tools.calibrate_curve.pgn import time_class

ROOT = Path(__file__).resolve().parents[2]
DESIGN_GAME = ROOT / "tests/reasoning/fixtures/chesscom_rapid_813_801.pgn"
SYMBOL = {6: "?!", 2: "?", 4: "??", 3: "!!", 9: "miss"}
CLASS = {"inaccuracy": "?!", "mistake": "?", "blunder": "??"}
MARKS = ("", "?!", "?", "??")  # the classes compared; chess.com's `miss` and `!!` count as ""
GRADINGS = ("quality_v1", "scale 1000", "table", "table 1000 ‰")
BAND = 400  # chess.com rating bands of the report
OPERA = [
    "e4",
    "e5",
    "Nf3",
    "d6",
    "d4",
    "Bg4",
    "dxe5",
    "Bxf3",
    "Qxf3",
    "dxe5",
    "Bc4",
    "Nf6",
    "Qb3",
    "Qe7",
    "Nc3",
    "c6",
    "Bg5",
    "b5",
    "Nxb5",
    "cxb5",
    "Bxb5+",
    "Nbd7",
    "O-O-O",
    "Rd8",
    "Rxd7",
    "Rxd7",
    "Rd1",
    "Qe6",
    "Bxd7+",
    "Nxd7",
    "Qb8+",
    "Nxb8",
    "Rd8#",
]


@dataclass
class Game:
    name: str
    moves: list[str]
    symbols: list[str]  # chess.com's class per ply ("" when unmarked)
    white: int | None
    black: int | None
    time_class: str | None
    digest: str  # of the moves, to leave out the design game


def chesscom_time_class(control: str) -> str | None:
    """chess.com writes `600` for 10 | 0 and `1/259200` for daily games."""

    if "/" in control:
        return None
    return time_class(control if "+" in control else f"{control}+0")


def read_games(path: Path) -> list[Game]:
    files = sorted(path.glob("*.pgn")) if path.is_dir() else [path]
    out = []
    for file in files:
        stream = io.StringIO(file.read_text())
        index = 0
        while (game := chess.pgn.read_game(stream)) is not None:
            index += 1
            board = game.board()
            moves, symbols = [], []
            for node in game.mainline():
                moves.append(board.san(node.move))
                board.push(node.move)
                symbols.append(next((SYMBOL[n] for n in sorted(node.nags) if n in SYMBOL), ""))
            h = game.headers
            out.append(Game(
                f"{file.stem}#{index}", moves, symbols, _elo(h.get("WhiteElo")),
                _elo(h.get("BlackElo")), chesscom_time_class(h.get("TimeControl", "-")),
                hashlib.sha256(" ".join(moves).encode()).hexdigest(),
            ))  # fmt: skip
    return out


def _elo(value: str | None) -> int | None:
    return int(value) if value and re.fullmatch(r"\d+", value) else None


def builds() -> dict[str, GradingBuild]:
    """The shipped build, and the same table with `cp_ratio_permille = 1000` (review N1)."""

    table = SHIPPED.curve_table()
    assert table is not None, "Q3 needs the shipped curve table"
    data = (ROOT / "src/calliope/reasoning/curves" / f"{table.name}.toml").read_bytes()
    unit = re.sub(rb"cp_ratio_permille = \d+", b"cp_ratio_permille = 1000", data)
    return {
        "shipped": SHIPPED,
        "unit": GradingBuild((load_curve_table(unit),), SHIPPED.conversions),
    }


@dataclass
class Ply:
    ply: int
    move: str
    theirs: str
    grades: dict[str, tuple[str, int | None]]  # grading -> (grade or reason, loss)
    allows_mate: bool  # the played line is mated, rank 1 is not
    misses_mate: bool  # rank 1 mates, the played line does not


def _mark(grade: str) -> str:
    return CLASS.get(grade, "")


def grade_game(engine, game: Game, gradings: dict) -> list[Ply]:
    rated = game.white is not None and game.time_class is not None
    spec = (
        GradingSpec(white_rating=game.white, black_rating=game.black, rating_pool="chesscom",
                    time_class=game.time_class)
        if rated else GradingSpec(scale=1000)
    )  # fmt: skip
    out = []
    for t in range(1, len(game.moves) + 1):
        request = AnalysisRequest(RootSpec(), tuple(game.moves), t, EngineProfile(), grading=spec)
        zero = Controller(FactEngine(engine=engine), SHIPPED).round_zero(request)
        view = zero.tree.view()
        mover = Color.WHITE if t % 2 == 1 else Color.BLACK
        grades = {}
        allows = misses = False
        for name, make in gradings.items():
            if name.startswith("table") and not rated:
                continue
            j = judge(view, zero.subject, make(spec))
            grades[name] = (j.grade.value if j.grade else str(j.reason), j.loss)
            if j.played is not None and j.best is not None:
                p, b = j.played.score, j.best.score
                allows = isinstance(p, Mate) and p.winner is not mover and not (
                    isinstance(b, Mate) and b.winner is not mover)  # fmt: skip
                misses = isinstance(b, Mate) and b.winner is mover and not (
                    isinstance(p, Mate) and p.winner is mover)  # fmt: skip
        out.append(Ply(t, game.moves[t - 1], game.symbols[t - 1], grades, allows, misses))
    return out


def gradings() -> dict:
    b = builds()
    return {
        "quality_v1": lambda spec: resolve(GradingSpec("quality_v1"), SHIPPED),
        "scale 1000": lambda spec: resolve(GradingSpec(scale=1000), SHIPPED),
        "table": lambda spec: resolve(spec, b["shipped"]),
        "table 1000 ‰": lambda spec: resolve(spec, b["unit"]),
    }


@dataclass
class Tally:
    plies: int = 0
    agree: int = 0
    confusion: Counter = field(default_factory=Counter)  # (chess.com, ours)

    def add(self, theirs: str, ours: str) -> None:
        theirs = theirs if theirs in MARKS else ""
        self.plies += 1
        self.agree += theirs == ours
        self.confusion[(theirs, ours)] += 1

    def summary(self) -> dict:
        marked = [m for m in MARKS if m]
        missed = sum(n for (a, b), n in self.confusion.items() if a and not b)
        false = sum(n for (a, b), n in self.confusion.items() if b and not a)
        return {
            "plies": self.plies,
            "agreement": self.agree / self.plies if self.plies else None,
            "agree": self.agree,
            "missed_marks": missed,
            "false_marks": false,
            "confusion": {f"{a or '·'}→{b or '·'}": n for (a, b), n in sorted(
                self.confusion.items()) if a in marked or b in marked},
        }  # fmt: skip


def summarize(results: list[tuple[Game, list[Ply]]]) -> dict:
    overall = {g: Tally() for g in GRADINGS}
    by_band: dict[str, dict[str, Tally]] = {}
    sensitivity = Counter()
    mates = []
    for game, plies in results:
        band = None
        if game.white is not None:
            rating = (game.white + (game.black or game.white)) // 2
            band = f"{rating // BAND * BAND}–{rating // BAND * BAND + BAND - 1}"
        for p in plies:
            for name, (grade, _) in p.grades.items():
                overall[name].add(p.theirs, _mark(grade))
                if band:
                    by_band.setdefault(band, {g: Tally() for g in GRADINGS})[name].add(
                        p.theirs, _mark(grade))  # fmt: skip
            if "table" in p.grades:
                sensitivity["plies"] += 1
                sensitivity["changed"] += p.grades["table"][0] != p.grades["table 1000 ‰"][0]
            if p.allows_mate or p.misses_mate:
                mates.append({"game": game.name, "ply": p.ply, "move": p.move, "chess.com": p.theirs,
                              "kind": "allows mate" if p.allows_mate else "misses mate",
                              "grades": {k: v[0] for k, v in p.grades.items()}})  # fmt: skip
    return {
        "games": len(results),
        "overall": {g: t.summary() for g, t in overall.items() if t.plies},
        "by_band": {
            b: {g: t.summary() for g, t in ts.items() if t.plies}
            for b, ts in sorted(by_band.items())
        },
        "permille_sensitivity": dict(sensitivity),
        "mate_moves": mates,
    }


def markdown(results: list[tuple[Game, list[Ply]]], summary: dict) -> str:
    lines = [f"# Q3 acceptance — {summary['games']} games\n"]
    lines.append("| grading | plies | agreement | missed marks | false marks |")
    lines.append("| --- | --- | --- | --- | --- |")
    for name, s in summary["overall"].items():
        lines.append(f"| {name} | {s['plies']} | {s['agree']} ({s['agreement']:.1%}) | "
                     f"{s['missed_marks']} | {s['false_marks']} |")  # fmt: skip
    for band, by in summary["by_band"].items():
        lines.append(f"\n**chess.com {band}:** " + "; ".join(
            f"{g} {s['agree']}/{s['plies']}" for g, s in by.items()))  # fmt: skip
    sens = summary["permille_sensitivity"]
    if sens:
        lines.append(f"\n**cp_ratio_permille 1103 vs 1000:** {sens['changed']} of {sens['plies']} "
                     "plies change grade.")  # fmt: skip
    lines.append("\n## Confusion (chess.com → ours)\n")
    for name, s in summary["overall"].items():
        lines.append(f"- {name}: " + ", ".join(f"{k} {n}" for k, n in s["confusion"].items()))
    lines.append("\n## Moves that allow or miss mate\n")
    for m in summary["mate_moves"]:
        lines.append(f"- {m['game']} ply {m['ply']} {m['move']} ({m['kind']}, chess.com "
                     f"{m['chess.com'] or '·'}): " + ", ".join(f"{k} {v}" for k, v in
                                                               m["grades"].items()))  # fmt: skip
    for game, plies in results:
        names = [n for n in GRADINGS if n in plies[0].grades] if plies else []
        lines.append(f"\n## {game.name} ({game.white}/{game.black}, {game.time_class})\n")
        lines.append("| ply | move | chess.com | " + " | ".join(names) + " |")
        lines.append("| --- | --- | --- |" + " --- |" * len(names))
        for p in plies:
            cells = [f"{p.grades[n][0]} ({p.grades[n][1]})" for n in names]
            if p.theirs or len({_mark(p.grades[n][0]) for n in names}) > 1:
                lines.append(f"| {p.ply} | {p.move} | {p.theirs} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from calliope.facts.search import StockfishEngine

    parser = argparse.ArgumentParser(prog="python -m tools.calibrate_curve.acceptance")
    parser.add_argument("games", type=Path, nargs="?", default=None)
    parser.add_argument("--out", type=Path, default=None, help="report stem (.md and .json)")
    parser.add_argument("--include-design-game", action="store_true")
    parser.add_argument("--opera", action="store_true", help="add the Q-D §9.11 record")
    args = parser.parse_args(argv)

    design = read_games(DESIGN_GAME)[0].digest
    found = read_games(args.games) if args.games else []
    if args.include_design_game and not any(g.digest == design for g in found):
        found += read_games(DESIGN_GAME)
    games = [g for g in found if args.include_design_game or g.digest != design]
    if args.opera:
        games.append(Game("opera", OPERA, [""] * len(OPERA), None, None, None, ""))
    skipped = 0 if args.include_design_game else sum(g.digest == design for g in found)
    engine = StockfishEngine.start(os.environ["CALLIOPE_STOCKFISH_PATH"])
    try:
        made = gradings()
        results = [(g, grade_game(engine, g, made)) for g in games]
    finally:
        engine.close()
    summary = summarize([(g, p) for g, p in results if g.name != "opera"])
    summary["design_game_left_out"] = skipped
    text = markdown(results, summary)
    if args.out:
        args.out.with_suffix(".md").write_text(text)
        args.out.with_suffix(".json").write_text(json.dumps(summary, indent=1) + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
