"""`python -m tools.rx` (RX1-D, RX2-D, RX4-D): manifest, run, check, finals, annotate, reference,
requests, bundle, audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anyio

from .check import check, finals, lines
from .manifest import MANIFEST, RX_DATA, build, engine_path, verify
from .model import read_env_file
from .run import ARMS, Bounds, RunSpec, run_once

PGNS = RX_DATA / "sets"
RUNS = RX_DATA / "runs"
WORK = RX_DATA / "work"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.rx")
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("manifest", help="build the sets' base caches and manifest (RX1-D §5)")
    m.add_argument("--sets", nargs="+", default=["train", "validation", "test"],
                   choices=["train", "validation", "test"])  # fmt: skip
    m.add_argument("--pgns", type=Path, default=PGNS)
    r = sub.add_parser("run", help="runs of one arm on one game (RX1-D §4)")
    r.add_argument("--arm", required=True, choices=ARMS)
    r.add_argument("--set", dest="set_name", required=True, choices=["train", "validation"])
    r.add_argument("--game", required=True)
    r.add_argument("--runs", type=int, default=1)
    r.add_argument("--model", default="openai/gpt-6-luna")
    r.add_argument("--reasoning-effort", default=None)
    r.add_argument("--env-file", type=Path, default=None)
    r.add_argument("--pgns", type=Path, default=PGNS)
    r.add_argument("--records", type=Path, default=RUNS)
    r.add_argument("--lessons", type=Path, default=None, help="the lesson set (arms D, D-min)")
    r.add_argument(
        "--candidate",
        default=None,
        help="screening: the lesson run alone (D, D-min) or the pair's tag (B, A-min)",
    )
    for flag, kind in (("--turns", int), ("--tool-calls", int), ("--tokens", int),
                       ("--run-seconds", float)):  # fmt: skip
        r.add_argument(flag, type=kind, default=None, help="a bound other than RX1's (RX4-D §3.1)")
    c = sub.add_parser("check", help="a run's wholeness (RX0-D §4.4)")
    c.add_argument("runs", nargs="+", type=Path)
    f = sub.add_parser("finals", help="each fixed moment's final commentary (RX0-D §6.0)")
    f.add_argument("run", type=Path)
    a = sub.add_parser("annotate", help="the build into a sealed base's base.json (RX2-D §3)")
    a.add_argument("sets", nargs="+", choices=["train", "validation"])
    rf = sub.add_parser("reference", help="the fixed moments' references (RX2-D §4.1)")
    rf.add_argument("sets", nargs="+", choices=["train", "validation"])
    rq = sub.add_parser("requests", help="run the on_request key causes' requests (RX2-D A2)")
    rq.add_argument("sets", nargs="+", choices=["train", "validation"])
    b = sub.add_parser("bundle", help="the blind judging's parts (RX2-D §5)")
    b.add_argument("runs", nargs="+", type=Path)
    b.add_argument("--moments-per-part", type=int, default=6, help="RX4-D §4: 4 for three arms")
    b.add_argument("--max-commentaries", type=int, default=36, help="a part's commentaries at most")
    au = sub.add_parser("audit", help="a judge's exported transcript against its part's directory")
    au.add_argument("judging")
    au.add_argument("part", type=int)
    au.add_argument("transcript", type=Path, help="the session's exported zip")
    au.add_argument("part_dir", help="the part's directory as the judge saw it")
    args = parser.parse_args(argv)

    if args.command == "manifest":
        build(args.sets, args.pgns, engine_path())
        return 0
    if args.command == "check":
        worst = 0
        for run in args.runs:
            result = check(run)
            print(json.dumps({"run": run.name} | result, ensure_ascii=False))
            worst = worst or (0 if result["whole"] else 1)
        return worst
    if args.command == "annotate":
        from .reference import annotate

        for set_name in args.sets:
            print(set_name, json.dumps(annotate(set_name, engine_path())))
        return 0
    if args.command == "reference":
        from .reference import references

        for set_name in args.sets:
            print(set_name, len(references(set_name, engine_path())), "references")
        return 0
    if args.command == "requests":
        from .requests import run_requests

        for set_name in args.sets:
            for line in run_requests(set_name, engine_path()):
                print(set_name, line)
        return 0
    if args.command == "bundle":
        from .judge import bundle

        out = bundle(
            args.runs,
            moments_per_part=args.moments_per_part,
            max_commentaries=args.max_commentaries,
        )
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    if args.command == "audit":
        from .judge import record_audit

        result = record_audit(args.judging, args.part, args.transcript, args.part_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["passed"] else 1
    if args.command == "finals":
        start = lines(args.run / "agent.jsonl")[0]
        print(json.dumps(finals(args.run, start["moments"]), ensure_ascii=False, indent=1))
        return 0
    if args.env_file is not None:
        read_env_file(args.env_file)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next(e for e in manifest["sets"][args.set_name] if e["name"] == args.game)
    pgn = verify(args.set_name, entry, args.pgns)
    bounds = Bounds()
    for name in ("turns", "tool_calls", "tokens", "run_seconds"):
        if getattr(args, name) is not None:
            setattr(bounds, name, getattr(args, name))
    spec = RunSpec(arm=args.arm, set_name=args.set_name, game=args.game, pgn=pgn,
                   moments=entry["moments"], base=RX_DATA / "base" / args.set_name,
                   records=args.records, work=WORK, model=args.model,
                   reasoning_effort=args.reasoning_effort, bounds=bounds,
                   game_id=entry.get("game_id"), lessons_path=args.lessons,
                   candidate_id=args.candidate)  # fmt: skip
    for _ in range(args.runs):
        result = anyio.run(run_once, spec)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
