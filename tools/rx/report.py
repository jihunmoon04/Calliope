"""RX2's baseline report (RX2-D §7): the audited, checked judging joined with its key, the records'
metrics, their intervals by arm and set, and arms compared paired by moment.

`python -m tools.rx.report --batch rx2-2 --judging 80ad6cfd --parts <dir> [--pair A A-min]`

RX4-D: `--batch` may be given more than once (RX2's A runs judged with RX4's B and D). A run that carries a
`candidate` (a screening run, §2.3 step 2) is reported under `<arm>:<candidate>` (`D:L03`, `B:L03`), so two
candidates on the same moment are never pooled (review N4); pair them with `--pair D:L03 B:L03`.

Every run and fixed moment comes from the batch records, not from the judging, so a moment-run with no
judged commentary counts as its decisive cause not explained (RX0-D §6.0; RX2 review N1).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

from .check import lines
from .judge import checked_judgings, join
from .manifest import RX_DATA
from .metrics import m1a, record_moments
from .reference import REFERENCES

DRAWS = 4000
LEVEL = 0.90


def label(row: dict) -> str:
    """A batch row's arm, with its screening candidate when it has one (RX4-D review N4)."""

    return row["arm"] + (f":{row['candidate']}" if row.get("candidate") else "")


def share(flags: list) -> float | None:
    return sum(flags) / len(flags) if flags else None


def roles_of(reference_dir: Path) -> dict[tuple, list[str]]:
    out = {}
    for p in reference_dir.rglob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[(d["set"], d["game"], d["ply"])] = [c.get("role") for c in d.get("key_causes") or []]
    return out


def moment_values(judged: dict | None, order: list[str]) -> dict:
    """One moment-run's values: wrong and sentence counts, the decisive cause explained (0 without a
    commentary, None when the moment has no key cause), the score (None without a commentary)."""

    if judged is None:
        return {"wrong": 0, "sentences": 0, "decisive": 0.0 if order else None, "score": None}
    dec = [c for c in judged.get("causes") or []
           if 0 < c["cause"] <= len(order) and order[c["cause"] - 1] == "decisive"]  # fmt: skip
    return {"wrong": sum(s["verdict"] == "wrong" for s in judged["sentences"]),
            "sentences": len(judged["sentences"]),
            "decisive": float(dec[0]["verdict"] == "explained") if dec else None,
            "score": float(judged["score"])}  # fmt: skip


def _resample(tree: dict, rng: random.Random) -> list:
    """Games, then runs within a game, then moments within a run, with replacement."""

    games = sorted(tree)
    out = []
    for g in (rng.choice(games) for _ in games):
        runs = list(tree[g].values())
        for r in (rng.choice(runs) for _ in runs):
            out += [rng.choice(r) for _ in r] if r else []
    return out


def interval(tree: dict, stat, seed: int = 1) -> tuple[float, float, float]:
    """`stat` over the whole tree and its 90% bootstrap interval. `stat` takes a list of moment-run
    values, so a ratio (M1b: wrong over sentences) is resampled as a ratio (RX2 review B4)."""

    rng = random.Random(seed)
    point = stat([v for g in tree.values() for r in g.values() for v in r])
    draws = sorted(stat(_resample(tree, rng)) for _ in range(DRAWS))
    return point, draws[int((1 - LEVEL) / 2 * DRAWS)], draws[int((1 + LEVEL) / 2 * DRAWS) - 1]


def wrong_rate(vs):
    n = sum(v["sentences"] for v in vs)
    return 100 * sum(v["wrong"] for v in vs) / n if n else 0.0


def mean_of(field):
    def stat(vs):
        xs = [v[field] for v in vs if v[field] is not None]
        return sum(xs) / len(xs) if xs else float("nan")

    return stat


def paired(cells: dict, set_name: str, arm_a: str, arm_b: str, field: str, seed: int = 3) -> dict:
    """arm_a − arm_b paired by moment: each moment's value over its runs (M1b as a ratio of sums),
    resampled over games, then moments (RX2 implementation §6)."""

    rng = random.Random(seed)
    diffs: dict[str, list[float]] = defaultdict(list)
    by_moment = {}
    for (s, g, p), by_arm in sorted(cells.items()):
        if s != set_name or arm_a not in by_arm or arm_b not in by_arm:
            continue
        stat = wrong_rate if field == "wrong" else mean_of(field)
        a, b = stat(by_arm[arm_a]), stat(by_arm[arm_b])
        if not (math.isnan(a) or math.isnan(b)):
            diffs[g].append(a - b)
            by_moment[f"{g}-{p}"] = a - b  # RX4-D §2.3: a candidate is read on its source moments
    games = sorted(diffs)
    if not games:
        return {"diff": None, "lo": None, "hi": None, "moments": 0, "games": 0, "by_moment": {}}
    flat = [d for g in games for d in diffs[g]]
    draws = []
    for _ in range(DRAWS):
        sample = []
        for g in (rng.choice(games) for _ in games):
            sample += [rng.choice(diffs[g]) for _ in diffs[g]]
        draws.append(sum(sample) / len(sample))
    draws.sort()
    return {"diff": sum(flat) / len(flat), "lo": draws[int((1 - LEVEL) / 2 * DRAWS)],
            "hi": draws[int((1 + LEVEL) / 2 * DRAWS) - 1], "moments": len(flat), "games": len(games),
            "by_moment": by_moment}  # fmt: skip


def build(batch: str | list[str], judging: str, parts: Path, pairs: list[tuple[str, str]]) -> dict:
    batches = [batch] if isinstance(batch, str) else list(batch)
    rows = [json.loads(x) for b in batches
            for x in (RX_DATA / "batches" / f"{b}.jsonl").read_text().splitlines()]  # fmt: skip
    for r in rows:
        r["arm"] = label(r)
    joined = join(judging, checked_judgings(judging, parts))
    judged = {(r["run_id"], r["ply"]): r["judged"] for r in joined}
    roles = roles_of(REFERENCES)
    trees: dict[tuple, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    cells: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))
    runs_by: dict[tuple, list[str]] = defaultdict(list)
    for r in rows:
        run = r["result"]["run"]
        start = lines(RX_DATA / "runs" / run / "agent.jsonl")[0]
        runs_by[(r["arm"], r["set"])].append(run)
        for ply in start["moments"]:
            v = moment_values(judged.get((run, ply)), roles.get((r["set"], r["game"], ply), []))
            trees[(r["arm"], r["set"])][r["game"]][run].append(v)
            cells[(r["set"], r["game"], ply)][r["arm"]].append(v)
    report = {"batch": batch if isinstance(batch, str) else batches, "judging": judging,
              "arms": {}, "paired": {}}  # fmt: skip
    for (arm, set_name), tree in sorted(trees.items()):
        run_ids = runs_by[(arm, set_name)]
        flat = [v for g in tree.values() for rr in g.values() for v in rr]
        moments = [m for r in run_ids for m in record_moments(RX_DATA / "runs" / r, REFERENCES)]
        dec = [c for m in moments for c in m["causes"] if c["role"] == "decisive"]
        sup = [c for m in moments for c in m["causes"] if c["role"] == "supporting"]
        # the judged verdict of each decisive cause beside its use (M3 against M2b)
        explained_by_use = {"used": [], "not_used": []}
        for m in moments:
            jd = judged.get((m["run"], m["ply"]))
            order = roles.get((set_name, m["game"], m["ply"]), [])
            for n, c in enumerate(m["causes"], start=1):
                if c["role"] != "decisive":
                    continue
                verdict = next(
                    (x["verdict"] for x in (jd or {}).get("causes") or [] if x["cause"] == n), None
                )
                explained_by_use["used" if c["used"] else "not_used"].append(verdict == "explained")
        kinds: dict[str, int] = defaultdict(int)
        sup_verdicts = []
        for (run, ply), jd in judged.items():
            if run not in run_ids:
                continue
            for s in jd["sentences"]:
                if s["verdict"] == "wrong":
                    kinds[s.get("kind", "other")] += 1
            order = roles.get(
                (set_name, next(r["game"] for r in rows if r["result"]["run"] == run), ply), []
            )
            for x in jd.get("causes") or []:
                if 0 < x["cause"] <= len(order) and order[x["cause"] - 1] == "supporting":
                    sup_verdicts.append(x["verdict"] == "explained")
        on_req = [c for c in dec if c["route"] == "on_request"]
        in_digest = [c for c in dec if c["route"] == "in_digest"]
        report["arms"][f"{arm}/{set_name}"] = {
            "runs": len(run_ids),
            "moment_runs": len(flat),
            "moment_runs_without_commentary": sum(1 for v in flat if v["score"] is None),
            "M1a_refused_per_run": statistics.mean(
                m1a(RX_DATA / "runs" / r)["refused"] for r in run_ids
            ),
            "M1b_wrong_per_100": interval(tree, wrong_rate),
            "M2b_decisive_explained": interval(tree, mean_of("decisive")),
            "M4_score": interval(tree, mean_of("score")),
            "M2a_decisive_cited": sum(c["covered"] for c in dec) / len(dec) if dec else None,
            "M1c_wrong_kinds": dict(kinds),
            "M2b_supporting_explained": share(sup_verdicts),
            "M3_decisive_in_digest_used": share([c["used_direct"] for c in in_digest]),
            "M3_decisive": {
                "available": share([c["available"] for c in dec]),
                "used_direct": share([c["used_direct"] for c in dec]),
                "used_related": share([c["used_related"] for c in dec]),
                "used": share([c["used"] for c in dec]),
                "explained_when_used": share(explained_by_use["used"]),
                "explained_when_not_used": share(explained_by_use["not_used"]),
                "n_used": len(explained_by_use["used"]),
                "n_not_used": len(explained_by_use["not_used"]),
            },
            "M3_supporting_used": share([c["used"] for c in sup]),
            "P1_key_cause_shown_not_used": share(
                [c["p1_unread"] for m in moments for c in m["causes"]]
            ),
            "P2_scores_alone": share([m["p2_scores_alone"] for m in moments if m["commented"]]),
            "M3_decisive_on_request": {
                "n": len(on_req),
                "fetched": sum(bool(c["request_fetched"]) for c in on_req),
                "used": sum(c["used_direct"] for c in on_req),
            },
            "sentences": sum(v["sentences"] for v in flat),
            "cost": round(
                sum(r["result"]["totals"]["cost"] for r in rows if r["result"]["run"] in run_ids), 4
            ),
        }
    for a, b in pairs:
        for set_name in ("train", "validation"):
            entry = {
                field: paired(cells, set_name, a, b, field)
                for field in ("wrong", "decisive", "score")
            }
            # RX2 re-review N3: the paired M1b is the mean of each moment's difference of rates (the
            # value promotion reads, RX2 implementation §6); the pooled difference of the two arms'
            # M1b is given beside it and is a different estimator
            pooled = [
                wrong_rate(
                    [v for g in trees[(arm, set_name)].values() for r in g.values() for v in r]
                )
                for arm in (a, b)
                if (arm, set_name) in trees
            ]
            if not entry["decisive"]["moments"]:
                continue  # the pair has no moment in this set
            entry["wrong_pooled_difference"] = pooled[0] - pooled[1] if len(pooled) == 2 else None
            report["paired"][f"{a} - {b} / {set_name}"] = entry
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.rx.report")
    parser.add_argument("--batch", required=True, action="append")
    parser.add_argument("--judging", required=True)
    parser.add_argument("--parts", type=Path, required=True)
    parser.add_argument("--pair", nargs=2, action="append", default=None)
    args = parser.parse_args(argv)
    pairs = [tuple(p) for p in (args.pair or [["A", "A-min"]])]
    print(
        json.dumps(
            build(
                args.batch if len(args.batch) > 1 else args.batch[0],
                args.judging,
                args.parts,
                pairs,
            ),
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
