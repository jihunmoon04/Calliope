"""The batches (RX2-D §6, RX4-D §3.2): arms on sets, `--runs` runs a game, interleaved (game by game,
repeat by repeat, arm by arm: A, A-min, A, A-min, ... on game 1, then game 2; review N1), run by a few
workers, each result logged. Batches written under one `--name` append to one log.

`python -m tools.rx.batch --name rx2-1 --env-file .env [--workers 3]` (RX2: A and A-min, both sets)
`python -m tools.rx.batch --name rx4-screen --env-file .env --arms B D --sets train --runs 1
  --games hung_queen --lessons tools/rx/lessons/candidates_v1.json --candidate L03` (one screening pair)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .manifest import MANIFEST, RX_DATA
from .run import ARMS as RUN_ARMS
from .run import LESSON_ARMS, REPO

ARMS = ("A", "A-min")  # RX2's defaults
SETS = ("train", "validation")
ALL_SETS = ("train", "validation", "test", "test2")  # LT-D §6.4, AF-D §7.4: tests after a freeze
TOOLS = ("v7", "v8", "v9")  # AF: v9 runs from this repository


def split_variant(name: str) -> tuple[str, str | None]:
    """`A@v7` → (`A`, `v7`); `A` → (`A`, None) (LT-D §6.3)."""

    arm, _, tools = name.partition("@")
    if arm not in RUN_ARMS or (tools and tools not in TOOLS):
        raise argparse.ArgumentTypeError(f"no arm {name!r}: ARM or ARM@TOOLS, tools {TOOLS}")
    return arm, (tools or None)


BOUND_FLAGS = ("turns", "tool_calls", "tokens", "run_seconds")


def jobs(runs_a_game: int = 3, arms=ARMS, sets=SETS, games=None, candidate=None) -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out = []
    for set_name in sets:
        for entry in manifest["sets"][set_name]:
            if games and entry["name"] not in games:
                continue
            for repeat in range(1, runs_a_game + 1):
                for name in arms:
                    arm, tools = split_variant(name)
                    job = {"set": set_name, "game": entry["name"], "arm": arm, "repeat": repeat}
                    if tools is not None:
                        job["variant"], job["tools"] = name, tools
                    if candidate is not None:
                        job["candidate"] = candidate
                    out.append(job)
    return out


def command(job: dict, env_file: Path, lessons: Path | None = None, bounds: dict | None = None,
            reproduce: bool = False):  # fmt: skip
    cmd = [sys.executable, "-m", "tools.rx", "run", "--arm", job["arm"], "--set", job["set"],
           "--game", job["game"], "--runs", "1", "--env-file", str(env_file)]  # fmt: skip
    if job["arm"] in LESSON_ARMS:
        if lessons is None:
            raise ValueError(f"arm {job['arm']} needs --lessons")
        cmd += ["--lessons", str(lessons)]
        if reproduce:
            cmd.append("--reproduce")
    if job.get("candidate") is not None:
        cmd += ["--candidate", job["candidate"]]
    if job.get("tools") is not None:
        cmd += ["--tools", job["tools"]]
    for name, value in (bounds or {}).items():
        if value is not None:
            cmd += ["--" + name.replace("_", "-"), str(value)]
    return cmd


def run_job(job: dict, env_file: Path, lessons: Path | None = None, bounds: dict | None = None,
            reproduce: bool = False):  # fmt: skip
    began = time.time()
    done = subprocess.run(command(job, env_file, lessons, bounds, reproduce), cwd=str(REPO),
                          capture_output=True, text=True, check=False)  # fmt: skip
    result = None
    for line in done.stdout.splitlines():
        if line.startswith("{"):
            result = json.loads(line)
    return job | {"exit": done.returncode, "seconds": round(time.time() - began),
                  "result": result, "stderr": done.stderr[-500:] if done.returncode else ""}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.rx.batch")
    parser.add_argument("--name", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--arms", nargs="+", default=list(ARMS),
                        help="arms, or variants ARM@TOOLS (LT-D §6.3): A@v7 A@v9 H@v9")  # fmt: skip
    parser.add_argument("--sets", nargs="+", default=list(SETS), choices=ALL_SETS)
    parser.add_argument("--games", nargs="+", default=None)
    parser.add_argument("--lessons", type=Path, default=None)
    parser.add_argument("--candidate", default=None)
    parser.add_argument("--reproduce", action="store_true")
    for name in BOUND_FLAGS:
        parser.add_argument("--" + name.replace("_", "-"), type=float if name == "run_seconds"
                            else int, default=None)  # fmt: skip
    args = parser.parse_args(argv)
    for name in args.arms:
        try:
            split_variant(name)
        except argparse.ArgumentTypeError as error:
            parser.error(str(error))
    bounds = {name: getattr(args, name) for name in BOUND_FLAGS}
    log = RX_DATA / "batches" / f"{args.name}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    todo = jobs(args.runs, args.arms, args.sets, args.games, args.candidate)
    for job in todo:  # a missing set file stops the batch before any run
        command(job, args.env_file, args.lessons, bounds, args.reproduce)
    with ThreadPoolExecutor(args.workers) as pool, open(log, "a", encoding="utf-8") as out:
        for result in pool.map(
            lambda j: run_job(j, args.env_file, args.lessons, bounds, args.reproduce), todo
        ):
            out.write(json.dumps(result | {"bounds": bounds}, ensure_ascii=False) + "\n")
            out.flush()
            print(json.dumps({k: result.get(k) for k in ("set", "game", "arm", "variant",
                                                         "candidate", "repeat", "exit")}
                             | {"reason": (result["result"] or {}).get("reason")}), flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
