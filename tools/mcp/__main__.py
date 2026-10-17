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
    from calliope.server import MAX_LOADED, MAX_LOADED_MB

    defaults = Limits()
    parser = argparse.ArgumentParser(prog="python -m tools.mcp")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--viewer", type=Path, default=VIEWER)
    named = {"window_seconds": "--budget-window", "job_window_seconds": "--job-window"}
    for field in fields(Limits):  # AG4-D §3.1, AG6-D §8: --budget-window, --max-searches, ...
        option = named.get(field.name, "--" + field.name.replace("_", "-"))
        kind = float if field.name.endswith("window_seconds") else int
        parser.add_argument(option, dest=field.name, type=kind,
                            default=getattr(defaults, field.name))  # fmt: skip
    # the ply cache (CC-D §2.3, §3.2)
    parser.add_argument(
        "--verify-writes",
        action="store_true",
        help="replay every stored ply and compare its bytes (off by default)",
    )
    parser.add_argument(
        "--max-loaded", type=int, default=MAX_LOADED, help="loaded plies kept in memory (0: none)"
    )
    parser.add_argument(
        "--max-loaded-mb",
        type=int,
        default=MAX_LOADED_MB,
        help="estimated memory of the kept plies, MB (0: none)",
    )
    args = parser.parse_args(argv)
    if args.max_loaded < 0 or args.max_loaded_mb < 0:
        parser.error("--max-loaded and --max-loaded-mb are at least 0")
    try:
        limits = Limits(**{field.name: getattr(args, field.name) for field in fields(Limits)})
    except ValueError as error:  # AG4-D AM1
        parser.error(str(error))
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
    page = app_page(args.viewer.expanduser())  # read once at start-up; None: a plain show_game
    session = Session(args.data.expanduser(), lambda: StockfishEngine.start(path), limits,
                      verify_writes=args.verify_writes, max_loaded=args.max_loaded,
                      max_loaded_mb=args.max_loaded_mb)  # fmt: skip
    try:
        build_server(session, page).run("stdio")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
