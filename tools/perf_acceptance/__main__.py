"""`python -m tools.perf_acceptance CONFIG GAME.pgn`: one game through the server's pipeline with
Stockfish, today's way or with the process's store and POSITION records (PF-D §6, one run).

CONFIG is `today` (a fresh result store per ply, no memo), `pf1` (one store and one memo for the
run) or `pf2` (and the played positions surveyed ahead on a second engine). With `--half`, the
first half of the game is analysed into the cache first (not timed, its own store), and the run
reports the plies whose windows were surveyed ahead that the cache held (PF-D §6: none). The game goes through `analyse_game` into an empty ply cache; the line printed is JSON: the
time, the engine calls, the distinct and irregular searches, the `DEADLINE` skips and deadline
cuts, the store's and the memo's entries, the process's peak resident size, and per ply what
must not change (graph digest, text, grade, labels, the tree's F5 digests). `--compare A.json
B.json` checks two such lines for PF-D §6's equalities.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import tempfile
import time
from pathlib import Path

CONFIGS = ("today", "pf1", "pf2")


class _Counting:
    """The engine port, with every search it answers recorded: the request (its `repr`, which
    leaves out the kind — stricter than the store's key) and whether the answer is regular (F4-D
    §5.3; the rule does not depend on the kind)."""

    def __init__(self, port, calls: list) -> None:
        self.port = port
        self.identity = port.identity
        self.calls = calls

    def search(self, request):
        from calliope.facts import SearchKind
        from calliope.facts.search.records import normalize

        raw = self.port.search(request)
        regular = normalize(raw, request, SearchKind.SURVEY, self.identity).regular
        self.calls.append((repr(request), regular))
        return raw

    def close(self) -> None:
        self.port.close()


def run(config: str, pgn: Path, stockfish: str, half: bool = False) -> dict:
    from calliope.facts import EngineProfile, EngineResultStore, FactEngine, PositionRecords
    from calliope.facts.search import StockfishEngine
    from calliope.reasoning import Reasoner, build_digest
    from calliope.server import MAX_POSITION_RECORDS, MAX_STORE_SEARCHES, PlyCache
    from calliope.server.pipeline import (
        EngineSlot,
        Prefetch,
        analyse_game,
        normalized_ply,
        parse_game,
    )

    calls: list = []
    slot = EngineSlot(lambda: _Counting(StockfishEngine.start(stockfish), calls))
    parsed = parse_game(pgn.read_text())
    plies = range(1, len(parsed.sans) + 1)
    profile = EngineProfile()
    store = memo = prefetch = None
    if config != "today":
        store, memo = EngineResultStore(MAX_STORE_SEARCHES), PositionRecords(MAX_POSITION_RECORDS)
    if config == "pf2":
        prefetch = Prefetch(EngineSlot(lambda: _Counting(StockfishEngine.start(stockfish), calls)))
    cached_first = range(1, len(plies) // 2 + 1) if half else range(0)
    skips = cuts = 0
    results = []
    try:
        port = slot.port
        build = Reasoner(FactEngine(engine=port)).build()
        with tempfile.TemporaryDirectory() as folder:
            cache = PlyCache(Path(folder), max_loaded=0)  # every read below replays the files
            if cached_first:
                analyse_game(slot, parsed, cached_first, cache, profile=profile)
                calls.clear()
            started = time.monotonic()
            document = analyse_game(slot, parsed, plies, cache, profile=profile, store=store,
                                    memo=memo, prefetch=prefetch)  # fmt: skip
            seconds = time.monotonic() - started
            for item in document["plies"]:
                expected = normalized_ply(parsed, item["ply"], profile)
                key = PlyCache.key(expected, build_digest(build), port.identity, profile)
                tree_path, _ = cache.paths(key)
                loaded = cache.get(key, expected, build)  # replayed: the files pass F5's checks
                for delta in loaded.analysis.tree.view().manifest():
                    skips += sum(1 for _, _, reason in delta.skipped if reason == "DEADLINE")
                    cuts += len(delta.deadline_cuts)
                answer = item | {"bundle": item["bundle"] | {"tree": None}}  # Q2: bytes may differ
                f5 = json.loads(tree_path.read_bytes())["digests"]
                results.append({"ply": item["ply"], "answer": answer, "f5": f5})
    finally:
        if prefetch is not None:
            prefetch.close()
        slot.close()
    windows_cached = None
    if prefetch is not None:
        windows_cached = sorted(set(prefetch.windows) & set(cached_first))
    return {
        "config": config,
        "game": pgn.name,
        "plies": len(plies),
        "seconds": round(seconds, 1),
        "engine_calls": len(calls),
        "distinct_searches": len({key for key, _ in calls}),
        "irregular": sum(1 for _, regular in calls if not regular),
        "deadline_skips": skips,
        "deadline_cuts": cuts,
        "store_entries": None if store is None else len(store),
        "memo_entries": None if memo is None else len(memo),
        "memo_hits": None if memo is None else memo.hits,
        "prefetch": None if prefetch is None else dict(prefetch.counts),
        "waits": None if store is None else [store.waits, round(store.wait_seconds, 1)],
        "half_cached": len(cached_first),
        "windows_of_cached_plies": windows_cached,
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "ply_results": results,
    }


def compare(a: dict, b: dict) -> list[str]:
    """PF-D §6's equalities between two runs of one game; the differences found."""

    if a["config"] != "today" or (a["game"], a["plies"]) != (b["game"], b["plies"]):
        runs = f"{a['config']} {a['game']}, {b['config']} {b['game']}"
        return [f"not today's run and another of the same game: {runs}"]
    problems = []
    for x, y in zip(a["ply_results"], b["ply_results"], strict=True):
        for field in ("answer", "f5"):
            if x[field] != y[field]:
                problems.append(f"ply {x['ply']}: {field} differs")
    for name in ("irregular", "deadline_skips", "deadline_cuts"):
        if b[name] > a[name]:
            problems.append(f"{name}: {b[name]} > {a[name]}")
    if b["config"] != "today" and b["engine_calls"] != b["distinct_searches"]:
        problems.append(f"engine calls {b['engine_calls']} != distinct {b['distinct_searches']}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.perf_acceptance")
    parser.add_argument("config", nargs="?", choices=CONFIGS)
    parser.add_argument("pgn", nargs="?", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("TODAY", "OTHER"))
    parser.add_argument("--half", action="store_true", help="the first half cached first")
    args = parser.parse_args(argv)
    if args.compare:
        a, b = (json.loads(p.read_text()) for p in args.compare)
        problems = compare(a, b)
        print("\n".join(problems) if problems else "equal")
        return 1 if problems else 0
    if args.config is None or args.pgn is None:
        parser.error("CONFIG and GAME.pgn, or --compare")
    stockfish = os.environ.get("CALLIOPE_STOCKFISH_PATH")
    if not stockfish:
        print("error: set CALLIOPE_STOCKFISH_PATH to the Stockfish 19 binary", file=sys.stderr)
        return 2
    print(json.dumps(run(args.config, args.pgn, stockfish, args.half), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
