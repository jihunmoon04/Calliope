"""PR #158 review N1 (agent-lt-implementation.md §11): the development pilots in structured form —
each run's id, end, tokens and cost, and each moment's checks, judge verdicts, sentence-check
attempts and final state, the hold reasons counted. Reads the batches `lt-pilot-1` … `lt-pilot-4`
and their runs' `agent.jsonl` (no conversation text kept); writes `lt-pilots.json`.

    python docs/design/rx-evidence/lt/pilot_summary.py [--rx-data DIR] [--out DIR]
"""

from __future__ import annotations

import json
from collections import Counter

from replay_common import arguments

args = arguments(__doc__)
BATCHES = ("lt-pilot-1", "lt-pilot-2", "lt-pilot-3", "lt-pilot-4")


def read(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


out = {}
for batch in BATCHES:
    runs = []
    for row in read(args.rx_data / "batches" / f"{batch}.jsonl"):
        result = row.get("result") or {}
        run = {"game": row["game"], "variant": row.get("variant"), "run": result.get("run"),
               "end": result.get("reason"), "seconds": row.get("seconds"),
               "totals": result.get("totals")}  # fmt: skip
        agent = read(args.rx_data / "runs" / result["run"] / "agent.jsonl") if result.get("run") else []
        start = agent[0] if agent else {}
        run["harness"] = {k: start.get(k) for k in ("harness", "harness_judge", "harness_sentences")}
        run["error"] = next((x.get("error") for x in agent if x.get("type") == "error"), None)
        run["requests_over_100k"] = sum(
            1 for x in agent
            if x.get("type") == "response" and ((x.get("usage") or {}).get("input_tokens") or 0) > 100_000
        )  # fmt: skip
        moments: dict = {}
        for x in agent:
            ply = x.get("ply")
            m = moments.setdefault(ply, {"checks": [], "judge": [], "sentence_checks": [],
                                         "final_state": None}) if ply is not None else None  # fmt: skip
            if x.get("type") == "harness" and x.get("stage") == "check":
                m["checks"].append(dict(Counter(r["result"] for r in x.get("results") or [])))
            elif x.get("type") == "judge":
                m["judge"].append(bool((x.get("verdict") or {}).get("pass")))
            elif x.get("type") == "sentences":
                bad = (x.get("verdict") or {}).get("bad") or []
                m["sentence_checks"].append({
                    "state": x.get("state"), "unbacked": x.get("unbacked"),
                    "verdicts": dict(Counter(b.get("verdict") for b in bad)),
                })  # fmt: skip
            elif x.get("type") == "harness" and x.get("stage") == "sentence_state":
                m["final_state"] = {"state": x["state"], "holds": x.get("holds")}
        run["moments"] = {str(k): v for k, v in moments.items()}
        finished = [v for v in moments.values() if v["final_state"]]
        run["moments_finished"] = len(finished)
        run["moments_interrupted"] = sum(1 for v in moments.values() if v["sentence_checks"]
                                         and not v["final_state"])  # fmt: skip
        runs.append(run)
    finals = Counter(v["final_state"]["state"] for r in runs for v in r["moments"].values()
                     if v["final_state"])  # fmt: skip
    holds = Counter(k for r in runs for v in r["moments"].values() for c in v["sentence_checks"]
                    if c["state"] == "held" for k, n in c["verdicts"].items() for _ in range(n))  # fmt: skip
    out[batch] = {
        "runs": runs,
        "final_states": dict(finals),
        "moments_finished": sum(r["moments_finished"] for r in runs),
        "moments_interrupted": sum(r["moments_interrupted"] for r in runs),
        "sentence_check_attempts": sum(len(v["sentence_checks"]) for r in runs
                                       for v in r["moments"].values()),  # fmt: skip
        "held_sentence_verdicts": dict(holds),
        "cost": round(sum((r["totals"] or {}).get("cost", 0) for r in runs), 4),
    }
    print(batch, {k: v for k, v in out[batch].items() if k != "runs"})
path = args.out / "lt-pilots.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("saved", path)
