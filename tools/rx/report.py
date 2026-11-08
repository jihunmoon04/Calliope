"""RX2's baseline report (RX2-D §7): the audited, checked judging joined with its key, the records'
metrics, their intervals by arm and set, and arms compared paired by moment.

`python -m tools.rx.report --batch rx2-2 --judging 80ad6cfd --parts <dir> [--pair A A-min]`

RX4-D: `--batch` may be given more than once (RX2's A runs judged with RX4's B and D). A run that carries a
`candidate` (a screening run, §2.3 step 2) is reported under `<arm>:<candidate>` (`D:L03`, `B:L03`), so two
candidates on the same moment are never pooled (review N4); pair them with `--pair D:L03 B:L03`.

Every fixed moment of a judged run comes from the batch records, not from the judging, so a moment-run
with no judged commentary counts as its decisive cause not explained (RX0-D §6.0; RX2 review N1). The runs
counted are the runs the judging was given (its key's `runs`; RX4a review B2): a batch's run that was not
bundled (another judging's, or one that ended on a provider error and was run again) is left out, not
counted as unexplained. A key written before `runs` was recorded falls back to the runs its items name.

Intervals are 90% bootstrap intervals (`LEVEL`), as in RX2.
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
from .judge import KEYS, checked_judgings, join
from .manifest import RX_DATA
from .metrics import m1a, record_moments
from .reference import REFERENCES

DRAWS = 4000
LEVEL = 0.90


SETS = ("train", "validation", "test")  # LT-D §6.4: per-set pairs over every set a report holds
POOLED_SETS = ("train", "validation")  # pooled as HS-D §6; Test never pooled with them


def label(row: dict) -> str:
    """A batch row's arm, with its screening candidate when it has one (RX4-D review N4), or its
    variant (`A@v7`, LT-D §6.3 review F2), so two tool versions of one arm are two arms."""

    if row.get("variant"):
        return row["variant"]
    return row["arm"] + (f":{row['candidate']}" if row.get("candidate") else "")


def sentence_states(run_dir: Path) -> dict[int, str]:
    """LT-D §5.5 (re-review R3): each moment's sentence-check state in an H rev. 5 run."""

    return {line["ply"]: line["state"] for line in lines(run_dir / "agent.jsonl")
            if line.get("type") == "harness" and line.get("stage") == "sentence_state"}  # fmt: skip


def by_state(values: list[tuple[str, dict]]) -> dict:
    """Moment-runs and M1b per sentence-check state: reported beside the decision, not a bar."""

    out = {}
    for state in sorted({st for st, _ in values}):
        vs = [v for st, v in values if st == state]
        out[state] = {"moment_runs": len(vs), "sentences": sum(v["sentences"] for v in vs),
                      "M1b_wrong_per_100": wrong_rate(vs)}  # fmt: skip
    return out


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


def fetched_value(moment: dict | None) -> float | None:
    """One moment-run's share of its decisive `on_request` causes whose evidence was fetched (M3
    `request_fetched`), None when the moment has none (RX4a review N1: a candidate is kept on M2b or
    on this, so both are paired by moment)."""

    causes = [c for c in (moment or {}).get("causes") or []
              if c.get("role") == "decisive" and c.get("route") == "on_request"]  # fmt: skip
    return sum(bool(c["request_fetched"]) for c in causes) / len(causes) if causes else None


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


def paired(cells: dict, set_name: str | None, arm_a: str, arm_b: str, field: str,
           seed: int = 3) -> dict:  # fmt: skip
    """arm_a − arm_b paired by moment: each moment's value over its runs (M1b as a ratio of sums),
    resampled over games, then moments (RX2 implementation §6). `set_name` None pools every set
    (HS-D §6, review C1): a game is keyed by `(set, game)`, so two sets never merge a game."""

    rng = random.Random(seed)
    diffs: dict[str, list[float]] = defaultdict(list)
    by_moment = {}
    for (s, g, p), by_arm in sorted(cells.items()):
        if (set_name is not None and s != set_name) or arm_a not in by_arm or arm_b not in by_arm:
            continue
        stat = wrong_rate if field == "wrong" else mean_of(field)
        a, b = stat(by_arm[arm_a]), stat(by_arm[arm_b])
        if not (math.isnan(a) or math.isnan(b)):
            game = g if set_name is not None else f"{s}/{g}"
            diffs[game].append(a - b)
            # RX4-D §2.3: a candidate is read on its source moments
            by_moment[f"{game}-{p}"] = a - b
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


def judged_rows(rows: list[dict], key_doc: dict) -> tuple[list[dict], str, list[str]]:
    """RX4a review B2: the batch rows of the runs the judging was given, and those left out. The key's
    `runs` names them; an older key falls back to the runs its items name. A judged run missing from
    the batches given is an error, never a silent gap."""

    if key_doc.get("runs") is not None:
        judged, source = set(key_doc["runs"]), "key"
    else:
        judged, source = {i["run_id"] for i in key_doc["key"].values()}, "items"

    def run_of(r):
        return (r.get("result") or {}).get("run")

    kept = [r for r in rows if run_of(r) in judged]
    left_out = sorted(run_of(r) for r in rows if run_of(r) and run_of(r) not in judged)
    missing = judged - {run_of(r) for r in kept}
    if missing:
        raise ValueError(f"judged runs not in the batches given: {sorted(missing)[:3]}")
    return kept, source, left_out


def build(batch: str | list[str], judging: str, parts: Path, pairs: list[tuple[str, str]]) -> dict:
    batches = [batch] if isinstance(batch, str) else list(batch)
    rows = [json.loads(x) for b in batches
            for x in (RX_DATA / "batches" / f"{b}.jsonl").read_text().splitlines()]  # fmt: skip
    for r in rows:
        r["arm"] = label(r)
    key_doc = json.loads((KEYS / judging / "bundle_key.json").read_text(encoding="utf-8"))
    started = list(rows)  # HS review F3: every started run, for the ledger and the worst case
    rows, runs_source, left_out = judged_rows(rows, key_doc)
    held = {r["set"] for r in rows}
    if "test" in held and len(held) > 1:  # LT-D §6.4 (review F1): Test is judged on its own
        raise ValueError(f"a report holds Test alone, not with {sorted(held - {'test'})}")
    joined = join(judging, checked_judgings(judging, parts))
    judged = {(r["run_id"], r["ply"]): r["judged"] for r in joined}
    roles = roles_of(REFERENCES)
    trees: dict[tuple, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    cells: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))
    runs_by: dict[tuple, list[str]] = defaultdict(list)
    recorded: dict[str, list[dict]] = {}
    states: dict[tuple, list] = defaultdict(list)  # (arm, set) → [(state, values)], LT-D §5.5
    for r in rows:
        run = r["result"]["run"]
        start = lines(RX_DATA / "runs" / run / "agent.jsonl")[0]
        checked = (
            sentence_states(RX_DATA / "runs" / run) if start.get("harness_sentences") else None
        )
        runs_by[(r["arm"], r["set"])].append(run)
        recorded[run] = record_moments(RX_DATA / "runs" / run, REFERENCES)
        by_ply = {m["ply"]: m for m in recorded[run]}
        for ply in start["moments"]:
            v = moment_values(judged.get((run, ply)), roles.get((r["set"], r["game"], ply), []))
            v["fetched"] = fetched_value(by_ply.get(ply))
            trees[(r["arm"], r["set"])][r["game"]][run].append(v)
            cells[(r["set"], r["game"], ply)][r["arm"]].append(v)
            if checked is not None:
                states[(r["arm"], r["set"])].append((checked.get(ply, "not_run"), v))
    report = {"batch": batch if isinstance(batch, str) else batches, "judging": judging,
              "interval": LEVEL, "runs_counted": len(rows), "runs_source": runs_source,
              "runs_left_out": left_out, "arms": {}, "paired": {}, "decisions": {},
              "ledger": ledger(started, set(left_out))}  # fmt: skip
    worst = worst_case(cells, started, set(left_out), roles, manifest_moments)
    for (arm, set_name), tree in sorted(trees.items()):
        run_ids = runs_by[(arm, set_name)]
        flat = [v for g in tree.values() for rr in g.values() for v in rr]
        moments = [m for r in run_ids for m in recorded[r]]
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
            **(
                {"sentence_check": by_state(states[(arm, set_name)])}
                if (arm, set_name) in states
                else {}
            ),
            "cost": round(
                sum(r["result"]["totals"]["cost"] for r in rows if r["result"]["run"] in run_ids), 4
            ),
        }
    pair_up(report, cells, worst, trees, pairs)
    return report


def pair_up(report: dict, cells: dict, worst: dict, trees: dict, pairs) -> None:
    """The paired entries of every pair, per set and pooled, and the decisions (HS-D §6; LT-D
    §6.4: a Test-only report decides from its Test entry)."""

    for a, b in pairs:
        for set_name in SETS:
            entry = {
                field: paired(cells, set_name, a, b, field)
                for field in ("wrong", "decisive", "score", "fetched")
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
        sets = [n for n in POOLED_SETS if f"{a} - {b} / {n}" in report["paired"]]
        test = report["paired"].get(f"{a} - {b} / test")
        if test is not None:  # LT-D §6.4: a Test-only report decides from its Test entry
            worst_entry = {
                field: paired(worst, "test", a, b, field) for field in ("wrong", "decisive")
            }
            report["paired"][f"{a} - {b} / test, worst case"] = worst_entry
            missing = {arm: report["arms"].get(f"{arm}/test", {})
                       .get("moment_runs_without_commentary", 0) for arm in (a, b)}  # fmt: skip
            report["decisions"][f"{a} - {b}"] = decision(
                test, {"test": test}, worst_entry, report["ledger"].get(a, {}),
                report["ledger"].get(b, {}), missing[a], missing[b],
            ) | {"read_from": "test"}  # fmt: skip
        elif (
            len(sets) > 1
        ):  # HS-D §6 (review C1): one value over every set's games, and the decision
            pooled_entry = {
                field: paired(cells, None, a, b, field)
                for field in ("wrong", "decisive", "score", "fetched")
            }
            pooled_entry["sets"] = sets
            report["paired"][f"{a} - {b} / pooled"] = pooled_entry
            worst_entry = {
                field: paired(worst, None, a, b, field) for field in ("wrong", "decisive")
            }
            report["paired"][f"{a} - {b} / pooled, worst case"] = worst_entry
            missing = {arm: sum(report["arms"].get(f"{arm}/{n}", {})
                                .get("moment_runs_without_commentary", 0) for n in sets)
                       for arm in (a, b)}  # fmt: skip
            report["decisions"][f"{a} - {b}"] = decision(
                pooled_entry,
                {n: report["paired"][f"{a} - {b} / {n}"] for n in sets},
                worst_entry,
                report["ledger"].get(a, {}),
                report["ledger"].get(b, {}),
                missing[a],
                missing[b],
            )


# HS-D §6: adoption reads the pooled entry; a set clearly worse blocks it
M2B_GAIN = 0.10
M2B_SET_FLOOR = -0.10
M1B_CEILING = 2.0


def _gain_met(entry: dict) -> bool:
    d = entry["decisive"]
    return d["diff"] is not None and d["diff"] >= M2B_GAIN and d["lo"] is not None and d["lo"] > 0


def quality_gate(pooled: dict, per_set: dict) -> dict:
    """HS-D §6 (review C1): the pooled M2b gains `M2B_GAIN` or more with its interval above zero, no
    set's M2b point estimate falls below `M2B_SET_FLOOR`, the pooled M1b's upper bound is at most
    `M1B_CEILING`. Quality only: `decision` adds the runs (HS review F3)."""

    reasons = []
    m2b = pooled["decisive"]
    if not _gain_met(pooled):
        reasons.append(f"pooled M2b {m2b['diff']} ({m2b['lo']} … {m2b['hi']}) is not +{M2B_GAIN} "
                       "with its interval above zero")  # fmt: skip
    for name, entry in per_set.items():
        d = entry["decisive"]["diff"]
        if d is not None and d < M2B_SET_FLOOR:
            reasons.append(f"{name}: M2b {d} is below {M2B_SET_FLOOR}")
    m1b = pooled["wrong"]
    if m1b["hi"] is None or m1b["hi"] > M1B_CEILING:
        reasons.append(f"pooled M1b's upper bound {m1b['hi']} is above +{M1B_CEILING} per 100")
    signs = {name: e["decisive"]["diff"] for name, e in per_set.items()
             if e["decisive"]["diff"] is not None}  # fmt: skip
    opposite = any(v > 0 for v in signs.values()) and any(v < 0 for v in signs.values())
    return {"passed": not reasons, "reasons": reasons, "sets_disagree": opposite}


def decision(pooled: dict, per_set: dict, worst: dict, ledger_a: dict, ledger_b: dict,
             missing_a: int, missing_b: int) -> dict:  # fmt: skip
    """HS-D §6 in full (HS review F3): `adopted` only when the quality gate passes, the arm compared
    (b, e.g. H) has no more failed runs and no more moment-runs without commentary than the base
    (a's side of the pair is the arm adopted: `a − b` reads H − A), and the worst case — every run
    not judged counted as unexplained — still gains `M2B_GAIN` with its interval above zero."""

    gate = quality_gate(pooled, per_set)
    reasons = list(gate["reasons"])
    if ledger_a.get("failed", 0) > ledger_b.get("failed", 0):
        reasons.append(
            f"failed runs {ledger_a.get('failed', 0)} against {ledger_b.get('failed', 0)}"
        )
    if missing_a > missing_b:
        reasons.append(f"moment-runs without commentary {missing_a} against {missing_b}")
    if not _gain_met(worst):
        w = worst["decisive"]
        reasons.append(f"worst case M2b {w['diff']} ({w['lo']} … {w['hi']}) is not +{M2B_GAIN} "
                       "with its interval above zero")  # fmt: skip
    return {"adopted": not reasons, "quality_gate_passed": gate["passed"], "reasons": reasons,
            "sets_disagree": gate["sets_disagree"]}  # fmt: skip


def failed(row: dict, left_out: set) -> bool:
    """A started run not judged: no result, or a run the judging was not given (HS review R1)."""

    run = (row.get("result") or {}).get("run")
    return not run or run in left_out


def manifest_moments(set_name: str, game: str) -> list[int]:
    """The fixed moments of a game, from the sets' manifest (RX1-D §5)."""

    from .manifest import MANIFEST

    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next((e for e in doc["sets"].get(set_name, []) if e["name"] == game), None)
    return list(entry["moments"]) if entry else []


def worst_case(cells: dict, started: list[dict], left_out: set, roles: dict, moments_of) -> dict:
    """HS-D §6 (review N1; HS reviews F3, R1): the judged cells, copied, and every run not judged —
    whatever it left behind — counted at every fixed moment of its game (`moments_of(set, game)`,
    the manifest's, not the run's log) as without commentary, its decisive cause not explained."""

    worst = defaultdict(lambda: defaultdict(list))
    for key, by_arm in cells.items():  # copies: the judged cells stay as they are
        worst[key] = defaultdict(list, {arm: list(values) for arm, values in by_arm.items()})
    for r in started:
        if not failed(r, left_out):
            continue
        for ply in moments_of(r["set"], r["game"]):
            v = moment_values(None, roles.get((r["set"], r["game"], ply), []))
            worst[(r["set"], r["game"], ply)][r["arm"]].append(v | {"fetched": None})
    return worst


def ledger(rows: list[dict], left_out: set) -> dict:
    """HS-D §6 (review N1): per arm, every started run — judged or not, and how each ended."""

    out: dict[str, dict] = {}
    for r in rows:
        result = r.get("result") or {}
        entry = out.setdefault(r["arm"], {"started": 0, "judged": 0, "failed": 0, "ends": {}})
        entry["started"] += 1
        end = result.get("reason") or "no result"
        entry["ends"][end] = entry["ends"].get(end, 0) + 1
        if failed(r, left_out):
            entry["failed"] += 1
        else:
            entry["judged"] += 1
    return out


def finite(x):
    """RX4a review N1: a value that does not exist (no commentary to score) is `null`, not `NaN`."""

    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {k: finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [finite(v) for v in x]
    return x


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
            finite(
                build(
                    args.batch if len(args.batch) > 1 else args.batch[0],
                    args.judging,
                    args.parts,
                    pairs,
                )
            ),
            ensure_ascii=False,
            indent=1,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
