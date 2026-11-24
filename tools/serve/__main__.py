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
import math
import os
import shutil
import sys
import webbrowser
from pathlib import Path

from calliope.server import MAX_LOADED, MAX_LOADED_MB, MAX_POSITION_RECORDS, MAX_STORE_SEARCHES
from calliope.server.jobs import Jobs
from calliope.server.pipeline import EngineSlot
from calliope.server.web import serve

from .commentary import DEFAULT_COST_LIMIT, CommentaryJobs, resolve_config

VIEWER = Path(__file__).resolve().parents[2] / "viewer"
DATA = Path.home() / ".local" / "share" / "calliope"


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def close_engines(jobs: Jobs, slot: EngineSlot, timeout: float = 1) -> bool:
    """The engines are closed only once the worker has ended, the one ahead first (PF-D §4.2);
    a job still running keeps both, and the process's exit ends them."""

    if not jobs.stop(timeout=timeout):
        logging.getLogger(__name__).warning("a job is still running: its engines end with the "
                                            "process")  # fmt: skip
        return False
    if jobs.prefetch is not None:
        jobs.prefetch.close()
    slot.close()
    return True


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
    # the process's searches and POSITION records (PF-D §2, §3)
    parser.add_argument(
        "--max-store-searches",
        type=int,
        default=MAX_STORE_SEARCHES,
        help="engine searches kept in memory, least recently used dropped first",
    )
    parser.add_argument(
        "--max-position-records",
        type=int,
        default=MAX_POSITION_RECORDS,
        help="POSITION fact records kept in memory, least recently used dropped first",
    )
    parser.add_argument(
        "--prefetch-engines",
        type=int,
        default=1,
        help="engines that survey a job's played positions ahead of its analysis (0: none)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="optional KEY=value file loaded before reading engine/API keys",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model for AI commentary (default: auto-detect from API keys)",
    )
    parser.add_argument(
        "--cost-limit",
        type=float,
        default=DEFAULT_COST_LIMIT,
        help="stop threshold for LLM spend per game in USD; last request may exceed it (default: 1.0)",
    )
    parser.add_argument(
        "--no-commentary",
        action="store_true",
        help="disable the AI commentary generator in the web app",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the local viewer URL in the default web browser",
    )
    args = parser.parse_args(argv)
    if args.prefetch_engines not in (0, 1):
        parser.error("--prefetch-engines is 0 or 1")
    if args.max_loaded < 0 or args.max_loaded_mb < 0:
        parser.error("--max-loaded and --max-loaded-mb are at least 0")
    if args.max_store_searches < 1 or args.max_position_records < 1:
        parser.error("--max-store-searches and --max-position-records are at least 1")
    if not math.isfinite(args.cost_limit) or args.cost_limit <= 0:
        parser.error("--cost-limit must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.env_file is not None:
        from tools.rx.model import read_env_file

        try:
            read_env_file(args.env_file.expanduser())
        except OSError as error:
            print(f"error: cannot read env file {args.env_file}: {error}", file=sys.stderr)
            return 2
    path = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")
    if not path:
        print("error: set CALLIOPE_STOCKFISH_PATH to the Stockfish 19 binary", file=sys.stderr)
        return 2
    if not _loopback(args.host):
        print(f"warning: listening on {args.host}: the app has no authentication; "
              "put a proxy that authenticates in front of it", file=sys.stderr)  # fmt: skip
    slot = EngineSlot(lambda: StockfishEngine.start(path))
    # started by the first job with two or more plies to analyse (PF-D §4.2)
    ahead = EngineSlot(lambda: StockfishEngine.start(path)) if args.prefetch_engines else None
    try:
        # starts the engine: a bad binary stops here
        jobs = Jobs(args.data.expanduser(), slot, verify_writes=args.verify_writes,
                    max_loaded=args.max_loaded, max_loaded_mb=args.max_loaded_mb,
                    max_store_searches=args.max_store_searches,
                    max_position_records=args.max_position_records,
                    ahead_slot=ahead)  # fmt: skip
    except (FactEngineError, OSError) as error:
        print(f"error: the engine cannot be started: {error}", file=sys.stderr)
        return 2
    jobs.recover()
    jobs.start()
    commentary_config = resolve_config(
        enabled=not args.no_commentary,
        model=args.model,
        cost_limit=args.cost_limit,
    )
    commentary_jobs = CommentaryJobs(args.data.expanduser(), path, commentary_config)
    try:
        server = serve(jobs, args.viewer, args.host, args.port, commentary_jobs=commentary_jobs)
    except OSError as error:
        print(f"error: cannot listen on {args.host}:{args.port}: {error}", file=sys.stderr)
        close_engines(jobs, slot)
        return 2
    if commentary_config.enabled:
        commentary_jobs.start_worker()
    bound_host, bound_port = server.server_address[:2]
    url = f"http://{bound_host}:{bound_port}/"
    print(f"Calliope on {url} (data: {args.data})", file=sys.stderr)
    if commentary_config.enabled:
        print(
            f"AI commentary: enabled (model: {commentary_config.model}, "
            f"stop threshold: ~${commentary_config.cost_limit:.2f})",
            file=sys.stderr,
        )
    else:
        print(f"AI commentary: disabled ({commentary_config.reason})", file=sys.stderr)
    if args.open:
        try:
            webbrowser.open(url)
        except (OSError, webbrowser.Error) as error:
            logging.getLogger(__name__).warning("cannot open browser: %s", error)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        commentary_jobs.stop(timeout=5)
        close_engines(jobs, slot)
        logging.getLogger(__name__).info("ply cache: %s, kept %s", jobs.cache.counts,
                                         jobs.cache.kept())  # fmt: skip
        logging.getLogger(__name__).info("searches kept %d, POSITION records kept %d "
                                         "(%d hits, %d computed)", len(jobs.store),
                                         len(jobs.memo), jobs.memo.hits,
                                         jobs.memo.misses)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
