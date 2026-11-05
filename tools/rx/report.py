"""RX2's baseline report (RX2-D §7): the audited judging joined with its key, the records' metrics, and
their intervals by arm and set.

`python -m tools.rx.report --batch rx2-2 --judging 80ad6cfd --parts <dir>`
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from .judge import join
from .manifest import RX_DATA
from .metrics import bootstrap, judged_metrics, m1a, record_moments
from .reference import REFERENCES


def roles_of(reference_dir: Path) -> dict[tuple, list[str]]:
    out = {}
    for p in reference_dir.rglob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[(d["set"], d["game"], d["ply"])] = [c.get("role") for c in d.get("key_causes") or []]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.rx.report")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--judging", required=True)
    parser.add_argument("--parts", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = [json.loads(x) for x in (RX_DATA / "batches" / f"{args.batch}.jsonl").read_text().splitlines()]
    runs = {r["result"]["run"]: r for r in rows}
    judgings = {}
    for part in sorted(args.parts.glob("part*")):
        judgings[int(part.name[4:])] = json.loads((part / "judging.json").read_text(encoding="utf-8"))
    joined = join(args.judging, judgings)
    roles = roles_of(REFERENCES)
    by_arm_set: dict[tuple, list[dict]] = defaultdict(list)
    for row in joined:
        by_arm_set[(row["arm"], row["set"])].append(row)

    report = {"batch": args.batch, "judging": args.judging, "arms": {}}
    for (arm, set_name), rs in sorted(by_arm_set.items()):
        key = f"{arm}/{set_name}"
        overall = judged_metrics(rs, roles)
        # per moment values for the intervals: game -> run -> [moment values]
        wrong: dict = defaultdict(lambda: defaultdict(list))
        decisive: dict = defaultdict(lambda: defaultdict(list))
        score: dict = defaultdict(lambda: defaultdict(list))
        for row in rs:
            j = row["judged"]
            n = len(j["sentences"])
            wrong[row["game"]][row["run_id"]].append(
                100 * sum(s["verdict"] == "wrong" for s in j["sentences"]) / n if n else 0
            )
            order = roles.get((row["set"], row["game"], row["ply"]), [])
            dec = [c for c in j.get("causes") or [] if 0 < c["cause"] <= len(order)
                   and order[c["cause"] - 1] == "decisive"]  # fmt: skip
            if dec:
                decisive[row["game"]][row["run_id"]].append(float(dec[0]["verdict"] == "explained"))
            score[row["game"]][row["run_id"]].append(j["score"])
        # record metrics
        run_ids = sorted({row["run_id"] for row in rs})
        refusals = [m1a(RX_DATA / "runs" / r)["refused"] for r in run_ids]
        moments = [m for r in run_ids for m in record_moments(RX_DATA / "runs" / r, REFERENCES)]
        dec_rows = [c for m in moments for c in m["causes"] if c["role"] == "decisive"]
        covered = defaultdict(lambda: defaultdict(list))
        for m in moments:
            for c in m["causes"]:
                if c["role"] == "decisive":
                    covered[m["game"]][m["run"]].append(float(c["covered"]))
        report["arms"][key] = {
            "runs": len(run_ids),
            "commentaries": len(rs),
            "M1a_refused_per_run": statistics.mean(refusals),
            "M1b_wrong_per_100": overall["wrong_per_100"],
            "M1b_interval": bootstrap(wrong),
            "M1c_kinds": overall["wrong_kinds"],
            "M2a_decisive_cited": sum(c["covered"] for c in dec_rows) / len(dec_rows) if dec_rows else None,
            "M2a_interval": bootstrap(covered) if covered else None,
            "M2b_decisive_explained": overall["decisive_explained"],
            "M2b_interval": bootstrap(decisive) if decisive else None,
            "M2b_supporting_explained": overall["supporting_explained"],
            "M3_decisive_available": sum(c["available"] for c in dec_rows) / len(dec_rows) if dec_rows else None,
            "M3_decisive_used_direct": sum(c["used_direct"] for c in dec_rows) / len(dec_rows) if dec_rows else None,
            "M3_by_route": {
                route: {"n": len(xs), "available": sum(c["available"] for c in xs) / len(xs),
                        "used": sum(c["used_direct"] for c in xs) / len(xs)}  # fmt: skip
                for route in ("in_digest", "on_request")
                if (xs := [c for c in dec_rows if c["route"] == route])
            },
            "M4_score": overall["score_mean"],
            "M4_interval": bootstrap(score),
            "sentences": overall["sentences"],
            "cost": round(sum(runs[r]["result"]["totals"]["cost"] for r in run_ids), 4),
        }
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
