"""`python -m tools.mcp`: the Calliope MCP server on stdio (AG-D §2), one session per process.

An MCP client starts it as a subprocess and talks over its stdin and stdout; logs go to stderr.
The engine is `CALLIOPE_STOCKFISH_PATH`; the data directory is the analysis server's, whose ply
cache it shares (AG-D §9). Needs the optional dependency group `agent` (the MCP SDK).

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


def main(argv: list[str] | None = None) -> int:
    from calliope.agent import Limits, Session
    from calliope.facts.search import StockfishEngine

    defaults = Limits()
    parser = argparse.ArgumentParser(prog="python -m tools.mcp")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--max-uncached-plies", type=int, default=defaults.max_uncached_plies)
    parser.add_argument("--max-searches", type=int, default=defaults.max_searches)
    parser.add_argument("--max-nodes", type=int, default=defaults.max_nodes)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(message)s")  # fmt: skip
    path = os.environ.get("CALLIOPE_STOCKFISH_PATH")
    if not path:
        print("error: set CALLIOPE_STOCKFISH_PATH to the Stockfish 19 binary", file=sys.stderr)
        return 2
    try:
        from calliope.agent.server import build_server
    except ImportError as error:
        print(f"error: the MCP SDK is missing ({error}); install the `agent` extra",
              file=sys.stderr)  # fmt: skip
        return 2
    limits = Limits(args.max_uncached_plies, args.max_searches, args.max_nodes)
    session = Session(args.data.expanduser(), lambda: StockfishEngine.start(path), limits)
    try:
        build_server(session).run("stdio")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
