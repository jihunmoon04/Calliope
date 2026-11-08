"""Shared by the LT replay scripts (agent-lt-implementation.md §9): the repository from this file's
place, the RX data directory and the output directory from arguments, a session on a copy of a
set's base. Run from the repository's root in its environment, with `CALLIOPE_STOCKFISH_PATH` set:

    python docs/design/rx-evidence/lt/replay_train.py [--rx-data DIR] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]  # docs/design/rx-evidence/lt → the repository
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))


def arguments(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--rx-data", type=Path,
                        default=Path(os.path.expanduser("~/.local/share/calliope/rx")),
                        help="the RX data directory (bases, sets)")  # fmt: skip
    parser.add_argument("--out", type=Path, default=HERE, help="where the JSON is written")
    return parser.parse_args()


def engine_path() -> str:
    path = os.environ.get("CALLIOPE_STOCKFISH_PATH")
    if not path:
        raise SystemExit("set CALLIOPE_STOCKFISH_PATH to the Stockfish binary")
    return path


def session_on(base: Path, searches: int = 400):
    """A session on a writable copy of a set's base cache (the base itself stays sealed)."""

    from calliope.agent import Limits, Session
    from calliope.facts.search import StockfishEngine

    work = Path(tempfile.mkdtemp()) / "data"
    shutil.copytree(base, work)
    for p in work.rglob("*"):
        p.chmod(0o644 if p.is_file() else 0o755)
    path = engine_path()
    return Session(
        work, lambda: StockfishEngine.start(path), replace(Limits(), max_searches=searches)
    )


class Cases:
    """Each case's answer (or its error), printed and kept for the JSON."""

    def __init__(self) -> None:
        self.out: dict = {}

    def __call__(self, key: str, fn) -> None:
        try:
            self.out[key] = fn()
        except Exception as error:  # noqa: BLE001 - a failing case is recorded, not fatal
            self.out[key] = {"error": f"{type(error).__name__}: {error}"}
        print(key, json.dumps(self.out[key], ensure_ascii=False)[:600], flush=True)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("saved", path)
