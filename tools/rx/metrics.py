"""M1–M4 (RX0-D §6, RX2-D §7) and their intervals (RX0-D §7.1).

Record metrics (M1a, M2a, M3) read a run's two layers; judged metrics (M1b, M1c, M2b, M4) read the
audited judging joined with its key (`judge.join`). Rates are per 100 sentences of the final
commentaries at the fixed moments. The independent unit is the game: intervals resample games, then
runs within a game, then moments within a run.
"""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from pathlib import Path

from .check import cites, finals, lines

FACT_RULES = {"S3", "S7", None}  # None: a proposition that did not verify (RX1 §4)
FORM_RULES = {"S1", "S2", "S8", "subject", "size", "item", "agent", "propositions"}


def refusal_class(rule: str | None) -> str:
    if rule in FACT_RULES:
        return "fact"
    if rule in FORM_RULES:
        return "form"
    return "other"


def m1a(run: Path) -> dict:
    """Refused subjects a run, and their problems by class (RX0-D §6.1)."""

    refused, classes = 0, Counter()
    for line in lines(run / "tools.jsonl"):
        if line.get("type") != "submission":
            continue
        for subject in line["subjects"]:
            if subject.get("outcome") == "refused":
                refused += 1
                for problem in subject.get("problems") or []:
                    classes[refusal_class(problem.get("rule"))] += 1
    return {"refused": refused, "classes": dict(classes)}


def _build_ids(run: Path) -> set[str]:
    return {x["build_id"] for x in lines(run / "tools.jsonl") if x.get("type") == "build"}


def record_moments(run: Path, reference_dir: Path) -> list[dict]:
    """M2a and M3 per fixed moment of one run (RX0-D §6.2, §6.3)."""

    agent = lines(run / "agent.jsonl")
    tools = lines(run / "tools.jsonl")
    start = agent[0]
    served = {x["ref"]: x for x in tools if x.get("type") == "handle"}
    builds = _build_ids(run)
    final = finals(run, start["moments"])
    out = []
    for ply in start["moments"]:
        ref_path = reference_dir / start["set"] / f"{start['game']}-{ply}.json"
        reference = json.loads(ref_path.read_text(encoding="utf-8"))
        if builds and reference["build_id"] not in builds:
            raise ValueError(f"{run.name}: its build is not the reference's (RX2-D §3)")
        reviewed = reference.get("status") == "reviewed"  # RX2-D §4.2: only reviewed causes count
        causes = (reference.get("key_causes") or []) if reviewed else []
        f = final[ply]
        last_seq = f["seq"] if f else None
        # Available: refs shown by successful calls before the moment's last accepted submission
        shown = set()
        for line in tools:
            successful = line.get("type") == "call" and "error" not in line
            if successful and (last_seq is None or line["seq"] < last_seq):
                shown.update(line.get("shown") or [])
        cited = cites(f["sentences"]) if f else set()
        details = {line["arguments"].get("ref") for line in tools
                   if line.get("type") == "call" and line.get("tool") == "detail"}  # fmt: skip
        rows = []
        for cause in causes:
            items = cause.get("items") or []
            ids = {i.get("identity") for i in items if i.get("identity")}
            keys = {i.get("line_key") for i in items if i.get("line_key")}
            resolved = (cause.get("request") or {}).get("resolved")  # RX2-D A2: an on_request cause

            def hit(refs, ids=ids, keys=keys, resolved=resolved):
                for ref in refs:
                    known = served.get(str(ref).split(":", 1)[0])
                    if not known:
                        continue
                    if known["identity"] in ids or known.get("line_key") in keys:
                        return True
                    if resolved and requested(known, resolved):
                        return True
                return False

            available = hit(shown)
            direct = hit(cited) or hit(details)
            rows.append({"role": cause.get("role", "decisive"), "route": cause.get("route"),
                         "available": available, "used_direct": direct,
                         "covered": hit(cited)})  # fmt: skip
        out.append({"run": run.name, "arm": start["arm"], "set": start["set"],
                    "game": start["game"], "ply": ply, "commented": f is not None,
                    "causes": rows})  # fmt: skip
    return out


def requested(known: dict, resolved: dict) -> bool:
    """A served handle that is the evidence an on_request cause asks for (RX2-D A2): an explored
    line from the request's position whose moves begin with its first two, or the request's facts."""

    address = known.get("address") or {}
    if resolved.get("tool") == "explore" and known.get("kind") == "explored_line":
        moves = list(address.get("moves") or [])
        want = list(resolved.get("moves") or [])[:2]
        return (
            list(address.get("from") or []) == list(resolved["from"]) and moves[: len(want)] == want
        )
    if resolved.get("tool") == "facts" and known.get("kind") == "fact":
        return (list(address.get("position") or []) == list(resolved["position"])
                and address.get("family") in set(resolved.get("families") or []))  # fmt: skip
    return False


def judged_metrics(rows: list[dict], roles: dict[tuple, list[str]] | None = None) -> dict:
    """M1b, M1c, M2b, M4 over joined judging rows (`judge.join`). `roles`: (set, game, ply) → the
    reference's cause roles in order; M2b's headline is the decisive causes explained (RX2-D A2)."""

    sentences = wrong = 0
    kinds = Counter()
    causes = {"decisive": Counter(), "supporting": Counter()}
    scores = []
    for row in rows:
        judged = row["judged"]
        for s in judged["sentences"]:
            sentences += 1
            if s["verdict"] == "wrong":
                wrong += 1
                kinds[s.get("kind", "other")] += 1
        order = (roles or {}).get((row.get("set"), row.get("game"), row.get("ply")), [])
        for c in judged.get("causes") or []:
            role = order[c["cause"] - 1] if 0 < c["cause"] <= len(order) else "decisive"
            causes[role][c["verdict"]] += 1
        scores.append(judged["score"])

    def share(counter):
        total = sum(counter.values())
        return counter["explained"] / total if total else None

    return {
        "sentences": sentences,
        "wrong_per_100": 100 * wrong / sentences if sentences else None,  # M1b
        "wrong_kinds": dict(kinds),  # M1c
        "decisive_explained": share(causes["decisive"]),  # M2b's headline
        "supporting_explained": share(causes["supporting"]),
        "explained_share": share(causes["decisive"] + causes["supporting"]),
        "score_mean": statistics.mean(scores) if scores else None,  # M4
    }


def bootstrap(values: dict[str, dict[str, list[float]]], draws: int = 2000, seed: int = 1,
              level: float = 0.90) -> tuple[float, float, float]:  # fmt: skip
    """The mean and its interval over games, then runs in a game, then moments in a run.
    `values`: game → run → the moment values."""

    rng = random.Random(seed)
    games = sorted(values)

    def mean_of(sample):
        flat = [v for run in sample for v in run]
        return sum(flat) / len(flat) if flat else float("nan")

    point = mean_of([m for g in games for m in values[g].values()])
    stats = []
    for _ in range(draws):
        sample = []
        for g in (rng.choice(games) for _ in games):
            runs = list(values[g].values())
            for r in (rng.choice(runs) for _ in runs):
                sample.append([rng.choice(r) for _ in r] if r else [])
        stats.append(mean_of(sample))
    stats.sort()
    lo = stats[int((1 - level) / 2 * draws)]
    hi = stats[int((1 + level) / 2 * draws) - 1]
    return point, lo, hi
