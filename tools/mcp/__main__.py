"""`python -m tools.mcp`: the Calliope MCP server on stdio (AG-D §2).

Game ids are derived from the game, so they name the same game in every process (AG4-D G1); the
budget and the work state are the process's (§3), with the limits as options (§3.1).

An MCP client starts it as a subprocess and talks over its stdin and stdout; logs go to stderr.
The engine is `CALLIOPE_STOCKFISH_PATH`; the data directory is the analysis server's, whose ply
cache it shares (AG-D §9). `--viewer` is the viewer's folder: its `index.html` is the MCP App of
`show_game` (AG3-D D9); without it, `show_game` is a plain tool (D13). Needs the optional
dependency group `agent` (the MCP SDK).

    {"mcpServers": {"calliope": {"command": ".venv/bin/python", "args": ["-m", "tools.mcp"],
                                 "env": {"CALLIOPE_STOCKFISH_PATH": "/path/to/stockfish"}}}}
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

DATA = Path.home() / ".local" / "share" / "calliope"
VIEWER = Path(__file__).resolve().parents[2] / "viewer"  # viewer/ beside tools/


def main(argv: list[str] | None = None) -> int:
    from dataclasses import fields

    from calliope.agent import Limits, Session
    from calliope.facts.search import StockfishEngine

    defaults = Limits()
    parser = argparse.ArgumentParser(prog="python -m tools.mcp")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--viewer", type=Path, default=VIEWER)
    for field in fields(Limits):  # AG4-D §3.1: --budget-window, --max-searches, ...
        option = "--budget-window" if field.name == "window_seconds" else (
            "--" + field.name.replace("_", "-"))  # fmt: skip
        kind = float if field.name == "window_seconds" else int
        parser.add_argument(option, dest=field.name, type=kind,
                            default=getattr(defaults, field.name))  # fmt: skip
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(message)s")  # fmt: skip
    path = os.environ.get("CALLIOPE_STOCKFISH_PATH")
    if not path:
        print("error: set CALLIOPE_STOCKFISH_PATH to the Stockfish 19 binary", file=sys.stderr)
        return 2
    try:
        from calliope.agent.server import app_page, build_server
    except ImportError as error:
        print(f"error: the MCP SDK is missing ({error}); install the `agent` extra",
              file=sys.stderr)  # fmt: skip
        return 2
    limits = Limits(**{field.name: getattr(args, field.name) for field in fields(Limits)})
    page = app_page(args.viewer.expanduser())  # read once at start-up; None: a plain show_game
    session = Session(args.data.expanduser(), lambda: StockfishEngine.start(path), limits)
    try:
        build_server(session, page).run("stdio")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
