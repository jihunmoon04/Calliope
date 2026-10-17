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

from calliope.server import MAX_LOADED, MAX_LOADED_MB
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
        # starts the engine: a bad binary stops here
        jobs = Jobs(args.data.expanduser(), slot, verify_writes=args.verify_writes,
                    max_loaded=args.max_loaded, max_loaded_mb=args.max_loaded_mb)  # fmt: skip
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
        logging.getLogger(__name__).info("ply cache: %s, kept %s", jobs.cache.counts,
                                         jobs.cache.kept())  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
