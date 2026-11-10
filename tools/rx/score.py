"""TB-D P2: one score row — H on the two development games, one run each, judged by `judge_v2r`
(P2a), appended to `docs/design/rx-evidence/scorecard.jsonl`.

`python -m tools.rx score --name <label> --env-file .env [--model claude-haiku-5-5]
  [--harness-revision 8] [--tools v9] [--reasoning-effort medium] [--judge-model claude-sonnet-5-5]`
`python -m tools.rx score --name <label> --runs <run id> <run id>` judges runs already made.

The row: the commit, the variant (harness revision, tools, model, provider, effort), per game its end,
its moments' ends, the largest request (total input), tokens, cost and seconds, the frame check;
completion (moments with accepted commentary out of those asked); the judged rates with the judging's
model, prompt, schema digest and failures. A moment without commentary counts as a failure in the
rates (`report.moment_values`), never left out. Rows compare only on the same (judging model, prompt,
schema digest); they are not the milestone's scale.
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

from .check import finals, lines
from .manifest import RX_DATA
from .model import is_claude, make_model, read_env_file
from .reference import REFERENCES
from .run import REPO, git_commit

GAMES = ("184800218248", "185264271324")  # the pilots' development games (TB-D Q1)
SET = "validation"
SCORECARD = REPO / "docs" / "design" / "rx-evidence" / "scorecard.jsonl"
PROMPT = REPO / "tools" / "rx" / "prompts" / "judge_v2r.md"
SCHEMA = REPO / "tools" / "rx" / "prompts" / "judge_v2.schema.json"
JUDGE_MODEL = "claude-sonnet-5-5"  # P2a (Q7): the judging model, apart from the writer
BOUNDS = {"turns": 90, "tool_calls": 150, "tokens": 4_000_000}  # the pilots' bounds (rev. 8)
VERDICTS = ("ok", "wrong", "doubtful", "search_only")


def schema_digest() -> str:
    return hashlib.sha256(SCHEMA.read_bytes()).hexdigest()[:16]


def run_command(game: str, args) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "tools.rx",
        "run",
        "--arm",
        "H",
        "--set",
        SET,
        "--game",
        game,
        "--runs",
        "1",
        "--model",
        args.model,
        "--harness-revision",
        str(args.harness_revision),
    ]
    if args.env_file:
        cmd += ["--env-file", str(args.env_file)]
    if args.tools:
        cmd += ["--tools", args.tools]
    if args.reasoning_effort:
        cmd += ["--reasoning-effort", args.reasoning_effort]
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


# -- one run's numbers --------------------------------------------------------------------------


def run_numbers(run_dir: Path) -> dict:
    """End, moments' ends, the largest request (total input), tokens, cost, the frame check."""

    from .report import frame_counts

    agent = lines(run_dir / "agent.jsonl")
    start = agent[0]
    end = next((x for x in reversed(agent) if x.get("type") == "end"), {})
    inputs = [x["usage"].get("input_tokens") or 0 for x in agent
              if x.get("type") == "response" and x.get("usage")]  # fmt: skip
    counted = [x.get("counted_tokens") for x in agent if x.get("type") == "guard"]
    ends = {}
    for x in agent:
        if x.get("type") == "harness" and x.get("stage") == "moment_end":
            ends[str(x["ply"])] = x.get("reason")
    return {"run": run_dir.name, "game": start.get("game"), "end": end.get("reason"),
            "moment_ends": ends, "largest_request": max(inputs, default=0),
            "largest_counted": max((c for c in counted if c), default=None),
            "totals": end.get("totals"), "frames": frame_counts(run_dir),
            "harness": start.get("harness"), "harness_frames": start.get("harness_frames")}  # fmt: skip


# -- the score judge (P2a) ----------------------------------------------------------------------


def judge_input(run_dir: Path, ply: int, final: dict, records) -> dict:
    from .evidence import evidence

    start = lines(run_dir / "agent.jsonl")[0]
    ref = json.loads((REFERENCES / start["set"] / f"{start['game']}-{ply}.json")
                     .read_text(encoding="utf-8"))  # fmt: skip
    cited = evidence(run_dir, final, records)
    sentences = [{"n": n, "text": s.get("text"), "class": s.get("class"), "evidence": e}
                 for n, (s, e) in enumerate(zip(final["sentences"], cited, strict=True), start=1)]  # fmt: skip
    return {"move": ref["move"], "fen_before": ref["fen_before"], "fen_after": ref["fen_after"],
            "moves_before": ref["moves_before"], "digest": ref["digest"],
            "key_causes": [{"cause": n, "role": c.get("role"), "text": c.get("text")}
                           for n, c in enumerate(ref.get("key_causes") or [], start=1)],
            "sentences": sentences}  # fmt: skip


def parse_verdict(text: str, sentences: int, causes: int) -> dict | None:
    """The one JSON object asked for, every sentence and cause judged; None otherwise."""

    start, end = (text or "").find("{"), (text or "").rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        doc = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    rows = doc.get("sentences")
    if not isinstance(rows, list) or sorted(
        r.get("n") for r in rows if isinstance(r, dict)
    ) != list(range(1, sentences + 1)):
        return None
    if any(r.get("verdict") not in VERDICTS for r in rows):
        return None
    judged = doc.get("causes") or []
    if sorted(c.get("cause") for c in judged if isinstance(c, dict)) != list(range(1, causes + 1)):
        return None
    if not isinstance(doc.get("score"), int) or not 1 <= doc["score"] <= 5:
        return None
    return {"sentences": rows, "causes": judged, "score": doc["score"]}


def judge_moment(model, system: str, content: dict) -> tuple[dict | None, dict]:
    """One request, asked again once when the answer is unreadable or cut (C4, re-review N8)."""

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(content, ensure_ascii=False)}]  # fmt: skip
    usage = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "asked": 0}
    for _ in range(2):
        reply = model.complete(messages, [])
        usage["asked"] += 1
        for key in ("cost", "input_tokens", "output_tokens"):
            usage[key] += reply.usage.get(key) or 0
        if reply.cut:
            continue
        verdict = parse_verdict(reply.message.get("content") or "", len(content["sentences"]),
                                len(content["key_causes"]))  # fmt: skip
        if verdict is not None:
            return verdict, usage
    return None, usage


def judge_run(run_dir: Path, model, system: str) -> dict:
    from .evidence import Run
    from .report import moment_values

    start = lines(run_dir / "agent.jsonl")[0]
    records = Run(run_dir)
    out, values, cost, failures = {}, [], 0.0, 0
    for ply, final in finals(run_dir, start["moments"]).items():
        ref = json.loads((REFERENCES / start["set"] / f"{start['game']}-{ply}.json")
                         .read_text(encoding="utf-8"))  # fmt: skip
        order = [c.get("role") for c in ref.get("key_causes") or []]
        verdict = None
        if final is not None and final.get("sentences"):
            verdict, usage = judge_moment(model, system, judge_input(run_dir, ply, final, records))
            cost += usage["cost"] or 0.0
            failures += verdict is None
        values.append(moment_values(verdict, order))
        out[str(ply)] = {"submitted": final is not None and bool(final.get("sentences")),
                         "verdict": verdict}  # fmt: skip
    return {"moments": out, "values": values, "cost": round(cost, 5), "failures": failures}


def rates(values: list[dict]) -> dict:
    from .report import judge_v1_like_rate, search_only_rate, wrong_rate

    decisive = [v["decisive"] for v in values if v["decisive"] is not None]
    scores = [v["score"] for v in values if v["score"] is not None]
    return {"M1b": round(wrong_rate(values), 2), "M1s": round(search_only_rate(values), 2),
            "M1b_plus_M1s": round(judge_v1_like_rate(values), 2),
            "M2b": round(sum(decisive) / len(decisive), 3) if decisive else None,
            "score": round(sum(scores) / len(scores), 2) if scores else None,
            "sentences": sum(v["sentences"] for v in values)}  # fmt: skip


def row(name: str, args, runs: list[Path], seconds: dict) -> dict:
    model = make_model(args.judge_model, None, cache=True, judge=True)
    system = PROMPT.read_text(encoding="utf-8")
    games, values, asked, done, judging_cost, failures = [], [], 0, 0, 0.0, 0
    for run_dir in runs:
        numbers = run_numbers(run_dir)
        judged = judge_run(run_dir, model, system)
        moments = judged["moments"]
        asked += len(moments)
        done += sum(m["submitted"] for m in moments.values())
        values += judged["values"]
        judging_cost += judged["cost"]
        failures += judged["failures"]
        games.append(numbers | {"seconds": seconds.get(run_dir.name),
                                "moments": {p: {"submitted": m["submitted"]}
                                            for p, m in moments.items()}})  # fmt: skip
    first = lines(runs[0] / "agent.jsonl")[0] if runs else {}
    return {"name": name, "date": time.strftime("%Y-%m-%d"), "commit": git_commit(REPO),
            "variant": {"harness_revision": first.get("harness_revision", args.harness_revision),
                        "harness": first.get("harness"), "tools": args.tools or "repository",
                        "model": first.get("model", args.model),
                        "provider": "claude" if is_claude(first.get("model", args.model))
                        else "openrouter",
                        "effort": args.reasoning_effort or ("medium" if is_claude(args.model)
                                                            else None)},
            "games": games, "completion": {"submitted": done, "asked": asked},
            "rates": rates(values),
            "judging": {"model": args.judge_model, "prompt": "judge_v2r",
                        "prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest()[:16],
                        "schema": schema_digest(), "failures": failures,
                        "cost": round(judging_cost, 5)},
            "cost": round(sum((g.get("totals") or {}).get("cost") or 0.0 for g in games), 5)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    from .model import DEFAULT_MODEL

    parser = argparse.ArgumentParser(prog="python -m tools.rx score")
    parser.add_argument("--name", required=True)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--harness-revision", type=int, default=8)
    parser.add_argument("--tools", default=None)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--judge-model", default=JUDGE_MODEL)
    parser.add_argument("--runs", nargs="+", default=None, help="judge these runs, run nothing")
    parser.add_argument("--scorecard", type=Path, default=SCORECARD)
    args = parser.parse_args(argv)
    if args.env_file:
        read_env_file(args.env_file)
    seconds: dict = {}
    if args.runs:
        runs = [RX_DATA / "runs" / r for r in args.runs]
    else:
        with ThreadPoolExecutor(len(GAMES)) as pool:
            results = list(pool.map(lambda g: run_game(g, args), GAMES))
        for r in results:
            print(json.dumps({k: r[k] for k in ("game", "exit", "run", "seconds")}), flush=True)
            if r["stderr"]:
                print(r["stderr"], file=sys.stderr)
        runs = [RX_DATA / "runs" / r["run"] for r in results if r["run"]]
        seconds = {r["run"]: r["seconds"] for r in results if r["run"]}
        if len(runs) < len(GAMES):
            print("a run did not start; no row written", file=sys.stderr)
            return 1
    out = row(args.name, args, runs, seconds)
    args.scorecard.parent.mkdir(parents=True, exist_ok=True)
    with open(args.scorecard, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
    print(json.dumps({k: out[k] for k in ("name", "completion", "rates", "cost")}
                     | {"largest_request": [g["largest_request"] for g in out["games"]]},
                     ensure_ascii=False))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
