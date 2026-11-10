"""TB-D P2: one score row — H on the two development games, one run each, judged with judge v2 by a
Claude Code session (P2a, rev. 5), appended to `docs/design/rx-evidence/scorecard.jsonl`.

    python -m tools.rx score run --name <label> --env-file .env [--harness-revision 15]
        [--model anthropic/claude-haiku-5.5] [--tools v10] [--reasoning-effort medium]
    (a Claude Code session judges each part the command printed, as in AF step 2; its exported
     transcript is audited with `python -m tools.rx audit`)
    python -m tools.rx score finish --name <label> [--judge-model <the sessions' model>]

`run` makes the runs and judge v2's bundle and keeps what `finish` needs under
`RX_DATA/score/<label>.json`. `finish` reads the audited judgings (`judge.checked_judgings`, the
milestone's own checks) and writes the row: the commit, the variant, per game its end, its moments'
ends, the largest request (total input), tokens, cost and seconds, the frame check; completion
(moments with accepted commentary out of those asked); the judged rates with the judging's id, judge,
prompt and schema digests and the sessions' model. A moment without commentary counts as a failure in
the rates (`report.moment_values`), never left out. The rates are judge v2's, the milestone's scale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .check import lines
from .manifest import RX_DATA
from .model import DEFAULT_MODEL, is_claude
from .reference import REFERENCES
from .run import REPO, git_commit

GAMES = ("184800218248", "185264271324")  # the pilots' development games (TB-D Q1)
SET = "validation"
SCORECARD = REPO / "docs" / "design" / "rx-evidence" / "scorecard.jsonl"
PENDING = RX_DATA / "score"
PROMPTS = REPO / "tools" / "rx" / "prompts"
JUDGE = "judge_v2"
# TB-D B5 (review F8): the cost bound is the one that bites (a rev. 9 game: 1.4–1.7M tokens, ~$0.08)
BOUNDS = {"turns": 90, "tool_calls": 150, "tokens": 20_000_000, "cost": 1.0}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def run_command(game: str, args) -> list[str]:
    cmd = [sys.executable, "-m", "tools.rx", "run", "--arm", "H", "--set", SET, "--game", game,
           "--runs", "1", "--model", args.model, "--harness-revision", str(args.harness_revision)]  # fmt: skip
    if args.env_file:
        cmd += ["--env-file", str(args.env_file)]
    if args.tools:
        cmd += ["--tools", args.tools]
    if args.reasoning_effort:
        cmd += ["--reasoning-effort", args.reasoning_effort]
    if args.harness_guide:
        cmd += ["--harness-guide", args.harness_guide]
    for name, value in BOUNDS.items():
        cmd += ["--" + name.replace("_", "-"), str(value)]
    return cmd


def run_game(game: str, args) -> dict:
    began = time.time()
    done = subprocess.run(run_command(game, args), cwd=str(REPO), capture_output=True, text=True,
                          check=False)  # fmt: skip
    result = None
    for line in done.stdout.splitlines():
        if line.startswith("{"):
            result = json.loads(line)
    return {"game": game, "exit": done.returncode, "seconds": round(time.time() - began),
            "run": (result or {}).get("run"), "stderr": done.stderr[-500:] if done.returncode else ""}  # fmt: skip


def run_numbers(run_dir: Path) -> dict:
    """End, moments' ends, the largest request (total input), tokens, cost, the frame check."""

    from .report import frame_counts

    agent = lines(run_dir / "agent.jsonl")
    start = agent[0]
    end = next((x for x in reversed(agent) if x.get("type") == "end"), {})
    inputs = [x["usage"].get("input_tokens") or 0 for x in agent
              if x.get("type") == "response" and x.get("usage")]  # fmt: skip
    guards = [x for x in agent if x.get("type") in ("guard", "compact")]  # review N8
    tiers = next((x for x in agent if x.get("type") == "tiers"), None)  # WG-D §4
    # RV-1 P5-3: a tiered run whose tier 1 was planned and never summed, or never planned
    incomplete = bool(start.get("harness_tier1")) and tiers is None
    whole = end.get("totals")
    totals = whole
    first_batch = next((x["seq"] for x in agent if x.get("type") == "tiers_plan"), None)
    if first_batch is not None:  # WG-D §5: today's fields are tier 2's, so rows compare
        inputs = [x["usage"].get("input_tokens") or 0 for x in agent if x.get("type") == "response"
                  and x.get("usage") and x["seq"] < first_batch]  # fmt: skip
        guards = [g for g in guards if g["seq"] < first_batch]
        if tiers and isinstance(whole, dict):
            later = [tiers["totals"].get("tier1") or {}, tiers["totals"].get("tier0") or {}]
            totals = {k: (round(v - sum(t.get(k, 0) for t in later), 6)
                          if isinstance(v, (int, float)) and k in later[0] else v)
                      for k, v in whole.items()}  # fmt: skip
    ends = {str(x["ply"]): x.get("reason") for x in agent
            if x.get("type") == "harness" and x.get("stage") == "moment_end"}  # fmt: skip
    return {"run": run_dir.name, "game": start.get("game"), "end": end.get("reason"),
            "moment_ends": ends, "largest_request": max(inputs, default=0),
            "largest_counted": max((g["counted_tokens"] for g in guards), default=None),
            "guard": sorted({g.get("how") for g in guards}) or None,
            "totals": totals, "frames": frame_counts(run_dir),
            "totals_whole_run": whole if first_batch is not None else None,
            "frames_tier1": frame_counts(run_dir, 1) if tiers else None,
            "tiers_incomplete": incomplete,
            "tiers": {k: tiers.get(k) for k in ("coverage", "totals", "ends", "sample")}
            if tiers else None,
            "model": start.get("model"), "harness": start.get("harness"),
            "harness_guide": start.get("harness_guide")}  # fmt: skip


def rates(values: list[dict]) -> dict:
    from .report import judge_v1_like_rate, search_only_rate, wrong_rate

    decisive = [v["decisive"] for v in values if v["decisive"] is not None]
    scores = [v["score"] for v in values if v["score"] is not None]
    return {"M1b": round(wrong_rate(values), 2), "M1s": round(search_only_rate(values), 2),
            "M1b_plus_M1s": round(judge_v1_like_rate(values), 2),
            "M2b": round(sum(decisive) / len(decisive), 3) if decisive else None,
            "score": round(sum(scores) / len(scores), 2) if scores else None,
            "sentences": sum(v["sentences"] for v in values)}  # fmt: skip


def moment_rows(runs: list[Path], judged: dict, tier: int = 2) -> tuple[list[dict], dict]:
    """Each run's moments: their values (a missing commentary a failure) and completion. Tier 1
    (WG-D §5): the run's judged sample instead of its fixed moments."""

    from .check import finals
    from .judge import tier1_sample
    from .report import moment_values
    from .tiers import SAMPLE

    values, done, asked = [], 0, 0
    for run_dir in runs:
        start = lines(run_dir / "agent.jsonl")[0]
        plies = start["moments"] if tier == 2 else tier1_sample(run_dir)
        if tier == 1 and not plies and start.get("harness_tier1") and not any(
            x.get("type") == "tiers_plan" for x in lines(run_dir / "agent.jsonl")
        ):  # RV-1 P5-3: the run ended before tier 1; its sample counts as asked, not given
            asked += SAMPLE
            values += [moment_values(None, []) for _ in range(SAMPLE)]
            continue
        for ply, final in finals(run_dir, plies).items():
            ref = json.loads((REFERENCES / start["set"] / f"{start['game']}-{ply}.json")
                             .read_text(encoding="utf-8"))  # fmt: skip
            order = [c.get("role") for c in ref.get("key_causes") or []]
            submitted = final is not None and bool(final.get("sentences"))
            asked += 1
            done += submitted
            values.append(moment_values(judged.get((run_dir.name, ply)) if submitted else None,
                                        order))  # fmt: skip
    return values, {"submitted": done, "asked": asked}


def do_run(args) -> int:
    from .judge import bundle
    from .model import read_env_file

    if args.env_file:
        read_env_file(args.env_file)
    with ThreadPoolExecutor(len(GAMES)) as pool:
        results = list(pool.map(lambda g: run_game(g, args), GAMES))
    for r in results:
        print(json.dumps({k: r[k] for k in ("game", "exit", "run", "seconds")}), flush=True)
        if r["stderr"]:
            print(r["stderr"], file=sys.stderr)
    if any(not r["run"] for r in results):
        print("a run did not start; nothing to judge", file=sys.stderr)
        return 1
    runs = [RX_DATA / "runs" / r["run"] for r in results]
    made = bundle(runs, judge=JUDGE)
    PENDING.mkdir(parents=True, exist_ok=True)
    pending = {"name": args.name, "runs": [r["run"] for r in results],
               "seconds": {r["run"]: r["seconds"] for r in results}, "judging": made["judging"],
               "parts": made["parts"],
               "variant": {"harness_revision": args.harness_revision, "tools": args.tools,
                           "model": args.model, "reasoning_effort": args.reasoning_effort,
                           "harness_guide": args.harness_guide}}  # fmt: skip
    (PENDING / f"{args.name}.json").write_text(json.dumps(pending, indent=1), encoding="utf-8")
    print(json.dumps({"judging": made["judging"], "parts": made["parts"], "items": made["items"]}))
    return 0


def do_finish(args) -> int:
    from .judge import JUDGING_ROOT, checked_judgings, join

    pending = json.loads((PENDING / f"{args.name}.json").read_text(encoding="utf-8"))
    judging = pending["judging"]
    joined = join(judging, checked_judgings(judging, JUDGING_ROOT / judging))
    judged = {(r["run_id"], r["ply"]): r["judged"] for r in joined}
    runs = [RX_DATA / "runs" / r for r in pending["runs"]]
    values, completion = moment_rows(runs, judged)
    values1, completion1 = moment_rows(runs, judged, tier=1)  # WG-D §5: empty before rev. 12
    games = [run_numbers(r) | {"seconds": pending["seconds"].get(r.name)} for r in runs]
    variant = pending["variant"]
    model = games[0].get("model") or variant["model"]
    effort = variant.get("reasoning_effort") or ("medium" if is_claude(model) else None)
    row = {"name": args.name, "date": time.strftime("%Y-%m-%d"), "commit": git_commit(REPO),
           "variant": {"harness_revision": variant["harness_revision"],
                       "harness": games[0].get("harness"),
            "harness_guide": games[0].get("harness_guide"), "tools": variant["tools"] or "repository",
                       "model": model, "provider": "claude" if is_claude(model) else "openrouter",
                       "effort": effort},
           "games": games, "completion": completion, "rates": rates(values),
           **({"completion_tier1": completion1, "rates_tier1": rates(values1)}
              if completion1["asked"] else {}),
           "judging": {"id": judging, "judge": JUDGE, "by": "claude_code_session",
                       "model": args.judge_model,
                       "prompt_sha256": digest(PROMPTS / f"{JUDGE}.md"),
                       "schema": digest(PROMPTS / f"{JUDGE}.schema.json"),
                       "items": len(joined)},
           "cost": round(sum((g.get("totals") or {}).get("cost") or 0.0 for g in games), 5)}  # fmt: skip
    if completion1["asked"]:  # WG-D §5: the whole run's cost and the tier-1 items, apart
        row["cost_whole_run"] = round(sum((g.get("totals_whole_run") or {}).get("cost") or 0.0
                                          for g in games), 5)  # fmt: skip
        row["judging"]["items_tier1"] = completion1["asked"]
    args.scorecard.parent.mkdir(parents=True, exist_ok=True)
    with open(args.scorecard, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({k: row[k] for k in ("name", "completion", "rates", "cost")}
                     | {"largest_request": [g["largest_request"] for g in games]},
                     ensure_ascii=False))  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.rx score")
    sub = parser.add_subparsers(dest="step", required=True)
    r = sub.add_parser("run", help="the two runs and judge v2's bundle")
    r.add_argument("--name", required=True)
    r.add_argument("--env-file", type=Path, default=None)
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--harness-revision", type=int, default=15)
    r.add_argument("--tools", default=None)
    r.add_argument("--reasoning-effort", default=None)
    r.add_argument("--harness-guide", default=None, help="rev. 9's guide (default: the harness's)")
    f = sub.add_parser("finish", help="the audited judgings into one scorecard row")
    f.add_argument("--name", required=True)
    f.add_argument("--judge-model", default="claude-code-session",
                   help="the model the judging sessions ran on, as recorded")  # fmt: skip
    f.add_argument("--scorecard", type=Path, default=SCORECARD)
    args = parser.parse_args(argv)
    return do_run(args) if args.step == "run" else do_finish(args)


if __name__ == "__main__":
    sys.exit(main())
