"""`python -m tools.serve`: the analysis server on loopback (AS-D §8).

Open it through a proxy that authenticates: code-server's `/proxy/<port>/` (with the trailing
slash) during development, a Caddy site with `basic_auth` later. The engine is
`CALLIOPE_STOCKFISH_PATH`; the data directory holds PGNs with players' names and stays outside
the repository.
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
import os
import sys
from pathlib import Path

from calliope.server.jobs import Jobs
from calliope.server.pipeline import EngineSlot
from calliope.server.web import serve

VIEWER = Path(__file__).resolve().parents[2] / "viewer"
DATA = Path.home() / ".local" / "share" / "calliope"


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def main(argv: list[str] | None = None) -> int:
    from calliope.facts import FactEngineError
    from calliope.facts.search import StockfishEngine

    parser = argparse.ArgumentParser(prog="python -m tools.serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--viewer", type=Path, default=VIEWER)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = os.environ.get("CALLIOPE_STOCKFISH_PATH")
    if not path:
        print("error: set CALLIOPE_STOCKFISH_PATH to the Stockfish 19 binary", file=sys.stderr)
        return 2
    if not _loopback(args.host):
        print(f"warning: listening on {args.host}: the app has no authentication; "
              "put a proxy that authenticates in front of it", file=sys.stderr)  # fmt: skip
    slot = EngineSlot(lambda: StockfishEngine.start(path))
    try:
        jobs = Jobs(args.data.expanduser(), slot)  # starts the engine: a bad binary stops here
    except (FactEngineError, OSError) as error:
        print(f"error: the engine cannot be started: {error}", file=sys.stderr)
        return 2
    jobs.recover()
    jobs.start()
    server = serve(jobs, args.viewer, args.host, args.port)
    print(f"Calliope on http://{args.host}:{args.port}/ (data: {args.data})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        jobs.stop(timeout=1)
        slot.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
