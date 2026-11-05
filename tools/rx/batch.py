"""RX2's batch (RX2-D §6): arms A and A-min on Train and Validation, three runs a game, interleaved by
game (A, A-min, A, A-min, ... on game 1, then game 2), run by a few workers, each result logged.

`python -m tools.rx.batch --name rx2-1 --env-file .env [--workers 3]`
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
from .run import REPO

ARMS = ("A", "A-min")
SETS = ("train", "validation")


def jobs(runs_a_game: int = 3) -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out = []
    for set_name in SETS:
        for entry in manifest["sets"][set_name]:
            for repeat in range(1, runs_a_game + 1):
                for arm in ARMS:
                    out.append({"set": set_name, "game": entry["name"], "arm": arm, "repeat": repeat})
    return out


def run_job(job: dict, env_file: Path) -> dict:
    began = time.time()
    done = subprocess.run(
        [sys.executable, "-m", "tools.rx", "run", "--arm", job["arm"], "--set", job["set"],
         "--game", job["game"], "--runs", "1", "--env-file", str(env_file)],
        cwd=str(REPO), capture_output=True, text=True,
    )  # fmt: skip
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
    args = parser.parse_args(argv)
    log = RX_DATA / "batches" / f"{args.name}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    todo = jobs(args.runs)
    with ThreadPoolExecutor(args.workers) as pool, open(log, "a", encoding="utf-8") as out:
        for result in pool.map(lambda j: run_job(j, args.env_file), todo):
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            print(json.dumps({k: result[k] for k in ("set", "game", "arm", "repeat", "exit")}
                             | {"reason": (result["result"] or {}).get("reason")}), flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
