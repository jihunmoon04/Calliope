"""`python -m tools.rx` (RX1-D, RX2-D, RX4-D): manifest, run, check, finals, annotate, reference,
requests, bundle, audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anyio

from .check import check, finals, lines
from .manifest import MANIFEST, RX_DATA, TEST_SETS, build, engine_path, opened, verify
from .model import DEFAULT_MODEL, read_env_file
from .run import ARMS, SERVER_ROOTS, TOOLS_VERSIONS, Bounds, RunSpec, run_once, server_root

SETS = ["train", "validation", *TEST_SETS]

PGNS = RX_DATA / "sets"
RUNS = RX_DATA / "runs"
WORK = RX_DATA / "work"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["score"]:  # TB-D P2: one score row (its own arguments)
        from .score import main as score

        return score(argv[1:])
    parser = argparse.ArgumentParser(prog="python -m tools.rx")
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("manifest", help="build the sets' base caches and manifest (RX1-D §5)")
    m.add_argument("--sets", nargs="+", default=["train", "validation", "test"],
                   choices=SETS)  # fmt: skip
    m.add_argument("--pgns", type=Path, default=PGNS)
    ot = sub.add_parser("open-test", help="after the freeze: Test's base and moments (RX0-D §2)")
    ot.add_argument(
        "--freeze", type=Path, required=True, help="the freeze record (RX0-D §2 step 1)"
    )
    ot.add_argument("--pgns", type=Path, default=PGNS)
    ot.add_argument(
        "--set",
        dest="set_name",
        default="test",
        choices=TEST_SETS,
        help="AF-D §7.4: the test set to open (its own freeze record)",
    )
    sw = sub.add_parser(
        "server-worktree", help="AF-D §6: an earlier tools version's server worktree"
    )
    sw.add_argument("tools", choices=sorted(SERVER_ROOTS))
    r = sub.add_parser("run", help="runs of one arm on one game (RX1-D §4)")
    r.add_argument("--arm", required=True, choices=ARMS)
    r.add_argument("--set", dest="set_name", required=True, choices=SETS)
    r.add_argument("--tools", default=None, choices=sorted(TOOLS_VERSIONS),
                   help="LT-D §6.3: the variant's tools; v7 starts the server from its worktree")  # fmt: skip
    r.add_argument(
        "--harness-revision",
        type=int,
        default=8,
        help="arm H: 8 (AF), 7 (LT), 6 and 5 (LT pilots), 4 (HS rev. 4)",
    )
    r.add_argument("--harness-guide", default=None,
                   help="TB-D B2: rev. 9's guide, a prompt name (default: the harness's)")  # fmt: skip
    r.add_argument("--game", required=True)
    r.add_argument("--runs", type=int, default=1)
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--reasoning-effort", default=None)
    r.add_argument("--env-file", type=Path, default=None)
    r.add_argument("--pgns", type=Path, default=PGNS)
    r.add_argument("--records", type=Path, default=RUNS)
    r.add_argument("--lessons", type=Path, default=None, help="the lesson set (arms D, D-min)")
    r.add_argument("--reproduce", action="store_true",
                   help="run a NOT_PROMOTED set to reproduce its result (RX4a re-review N4)")  # fmt: skip
    r.add_argument(
        "--candidate",
        default=None,
        help="screening: the lesson run alone (D, D-min) or the pair's tag (B, A-min)",
    )
    for flag, kind in (("--turns", int), ("--tool-calls", int), ("--tokens", int),
                       ("--run-seconds", float), ("--cost", float)):  # fmt: skip
        r.add_argument(flag, type=kind, default=None, help="a bound other than RX1's (RX4-D §3.1)")
    c = sub.add_parser("check", help="a run's wholeness (RX0-D §4.4)")
    c.add_argument("runs", nargs="+", type=Path)
    f = sub.add_parser("finals", help="each fixed moment's final commentary (RX0-D §6.0)")
    f.add_argument("run", type=Path)
    a = sub.add_parser("annotate", help="the build into a sealed base's base.json (RX2-D §3)")
    a.add_argument("sets", nargs="+", choices=SETS)
    rf = sub.add_parser("reference", help="the fixed moments' references (RX2-D §4.1)")
    rf.add_argument("sets", nargs="+", choices=SETS)
    rf.add_argument("--tier1", action="store_true",
                    help="WG-D §5: each game's judged tier-1 sample, unreviewed")  # fmt: skip
    rq = sub.add_parser("requests", help="run the on_request key causes' requests (RX2-D A2)")
    rq.add_argument("sets", nargs="+", choices=SETS)
    b = sub.add_parser("bundle", help="the blind judging's parts (RX2-D §5)")
    b.add_argument("runs", nargs="+", type=Path)
    b.add_argument("--moments-per-part", type=int, default=6, help="RX4-D §4: 4 for three arms")
    b.add_argument("--max-commentaries", type=int, default=36, help="a part's commentaries at most")
    b.add_argument(
        "--judge",
        choices=["judge_v1", "judge_v2"],
        default="judge_v1",
        help="AF-D §5: judge_v2 gives each sentence its cited evidence",
    )
    au = sub.add_parser("audit", help="a judge's exported transcript against its part's directory")
    au.add_argument("judging")
    au.add_argument("part", type=int)
    au.add_argument("transcript", type=Path, help="the session's exported zip")
    au.add_argument("part_dir", help="the part's directory as the judge saw it")
    args = parser.parse_args(argv)

    if args.command == "manifest":
        build(args.sets, args.pgns, engine_path())
        return 0
    if args.command == "open-test":
        from .manifest import open_test

        open_test(args.pgns, engine_path(), args.freeze, set_name=args.set_name)
        return 0
    if args.command == "check":
        worst = 0
        for run in args.runs:
            result = check(run)
            print(json.dumps({"run": run.name} | result, ensure_ascii=False))
            worst = worst or (0 if result["whole"] else 1)
        return worst
    if args.command == "server-worktree":
        from .servers import make

        out = make(args.tools)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 1 if out["problems"] else 0
    if args.command in ("annotate", "reference", "requests"):  # LT-D §6.4, AF-D §7.4
        manifest_doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
        closed = [t for t in args.sets if t in TEST_SETS and not opened(manifest_doc, t)]
        if closed:
            raise SystemExit(f"{', '.join(closed)} not open: open-test after the freeze (RX0-D §2)")
    if args.command == "annotate":
        from .reference import annotate

        for set_name in args.sets:
            print(set_name, json.dumps(annotate(set_name, engine_path())))
        return 0
    if args.command == "reference":
        from .reference import references

        for set_name in args.sets:
            made = references(set_name, engine_path(), tier1=args.tier1)
            print(set_name, len(made), "references", *[p.name for p in made] if args.tier1 else [])
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
            judge=args.judge,
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
    if "moments" not in entry:  # LT-D §6.4: Test opens after the freeze (RX0-D §2)
        raise SystemExit(f"{args.set_name} {args.game} has no moments: the set is not opened")
    pgn = verify(args.set_name, entry, args.pgns)
    bounds = Bounds()
    for name in ("turns", "tool_calls", "tokens", "run_seconds", "cost"):  # TB-D B5: cost
        if getattr(args, name) is not None:
            setattr(bounds, name, getattr(args, name))
    if args.arm == "H" and args.cost is None:  # TB-D B5 (review F8): rev. 9 runs under $1
        from .harness import PER_MOMENT

        if args.harness_revision in PER_MOMENT:
            bounds.cost = 1.0
    spec = RunSpec(arm=args.arm, set_name=args.set_name, game=args.game, pgn=pgn,
                   moments=entry["moments"], base=RX_DATA / "base" / args.set_name,
                   records=args.records, work=WORK, model=args.model,
                   reasoning_effort=args.reasoning_effort, bounds=bounds,
                   game_id=entry.get("game_id"), lessons_path=args.lessons,
                   candidate_id=args.candidate, reproduce=args.reproduce,
                   harness_revision=args.harness_revision, harness_guide=args.harness_guide,
                   tools=args.tools,
                   server=server_root(args.tools))  # fmt: skip
    if args.set_name in TEST_SETS:  # LT review N1, AF-D §7.4: only its own frozen variant runs
        from .freeze import run_problems

        wrong = run_problems(opened(manifest, args.set_name), spec)
        if wrong:
            raise SystemExit("not the frozen Test run: " + "; ".join(wrong))
    for _ in range(args.runs):
        result = anyio.run(run_once, spec)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
