"""M1–M4 (RX0-D §6, RX2-D §7) and their intervals (RX0-D §7.1).

Record metrics (M1a, M2a, M3) read a run's two layers; judged metrics (M1b, M1c, M2b, M4) read the
audited judging joined with its key (`judge.join`). Rates are per 100 sentences of the final
commentaries at the fixed moments. The independent unit is the game: intervals resample games, then
runs within a game, then moments within a run.
"""

from __future__ import annotations

import json
import random
import re
import statistics
from collections import Counter
from pathlib import Path

from .check import cites, finals, harness_call_ids, lines

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


SQUARE = re.compile(r"\b[a-h][1-8]\b")
SAN = re.compile(
    r"\b(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)[+#]?"
)


def reference_objects(reference: dict) -> dict[str, list[dict]]:
    """Every served item of a reference (its digest and full record), by its handle's prefix part
    (`c12`), as the reference shows it."""

    out: dict[str, list[dict]] = {}

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("ref"), str):
                out.setdefault(o["ref"].split(".")[0], []).append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(reference.get("digest"))
    walk(reference.get("full"))
    return out


def item_facts(objects: list[dict]) -> dict:
    """What an item names: its line's moves in UCI, the squares and the moves (SAN or UCI) its own
    texts name (RX0-D §6.3's related use; FENs and paths are not read)."""

    pv_uci, squares, moves = [], set(), set()
    for o in objects:
        for m in o.get("pv") or []:
            if isinstance(m, dict) and m.get("uci"):
                pv_uci.append(m["uci"])
        texts = [o.get(k) for k in ("proves", "text", "says", "san") if isinstance(o.get(k), str)]
        move = o.get("move")
        if isinstance(move, dict):
            texts += [str(move.get("san") or ""), str(move.get("uci") or "")]
        for text in texts:
            squares.update(SQUARE.findall(text))
            moves.update(x.rstrip("+#") for x in SAN.findall(text))
        if isinstance(move, dict) and move.get("uci"):
            moves.add(move["uci"])
    return {"pv": pv_uci[:8], "squares": squares, "moves": moves}


def related(known: dict, facts: dict, call: dict | None) -> bool:
    """A call that changes or tests what the item is about (RX0-D §6.3, RX0-D review N5): an explored
    line whose first two moves are the item's line's; one with a move from or to a square the item
    names; a `judge_move` of a move the item names. A piece that only appears is never use. (The
    rule's fourth case, an `exchange` record on the item's square, is not read: end facts are not
    kept per square in the record.)"""

    if known.get("kind") == "explored_line":
        if (known.get("address") or {}).get("by") != "agent":
            return False  # a line Calliope played itself (the same reply), not the agent's test
        moves = list((known.get("address") or {}).get("moves") or [])
        if facts["pv"][:2] and moves[:2] == facts["pv"][:2]:
            return True
        return any(m[:2] in facts["squares"] or m[2:4] in facts["squares"] for m in moves)
    if call is not None and call.get("tool") == "judge_move":
        move = str((call.get("arguments") or {}).get("move") or "").rstrip("+#")
        return bool(move) and move in facts["moves"]
    return False


def record_moments(run: Path, reference_dir: Path) -> list[dict]:
    """M2a and M3 per fixed moment of one run (RX0-D §6.2, §6.3)."""

    agent = lines(run / "agent.jsonl")
    tools = lines(run / "tools.jsonl")
    own = harness_call_ids(agent, tools)  # LT-D §5.2: the harness's reads are not the agent's
    tools = [x for x in tools if not (x.get("type") == "call" and x.get("call_id") in own)]
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
        objects = reference_objects(reference)
        calls_by_id = {line["call_id"]: line for line in tools if line.get("type") == "call"}
        # the handles and the calls of the moment-run, before its last accepted submission
        later_refs = {ref for ref, line in served.items()
                      if line.get("call_id") in calls_by_id and "error" not in calls_by_id[line["call_id"]]
                      and calls_by_id[line["call_id"]].get("tool") == "explore"
                      and (last_seq is None or calls_by_id[line["call_id"]]["seq"] < last_seq)}  # fmt: skip
        judge_calls = [line for line in tools if line.get("type") == "call" and line.get("tool") == "judge_move"
                       and "error" not in line and (last_seq is None or line["seq"] < last_seq)]  # fmt: skip
        details = {line["arguments"].get("ref") for line in tools
                   if line.get("type") == "call" and line.get("tool") == "detail"}  # fmt: skip
        # the calls that succeeded, by id, before the moment's last accepted submission
        ok_calls = {line["call_id"] for line in tools
                    if line.get("type") == "call" and "error" not in line
                    and (last_seq is None or line["seq"] < last_seq)}  # fmt: skip
        fetched_refs = {ref for ref, line in served.items() if line.get("call_id") in ok_calls}
        rows = []
        for cause in causes:
            items = cause.get("items") or []
            ids = {i.get("identity") for i in items if i.get("identity")}
            keys = {i.get("line_key") for i in items if i.get("line_key")}
            resolved = (cause.get("request") or {}).get("resolved")  # RX2-D A2: an on_request cause

            def item_hit(refs, ids=ids, keys=keys):
                """A cited or shown ref that is one of the cause's items (digest evidence)."""
                for ref in refs:
                    known = served.get(str(ref).split(":", 1)[0])
                    if known and (known["identity"] in ids or known.get("line_key") in keys):
                        return True
                return False

            def request_hit(refs, resolved=resolved):
                """A ref that is the evidence the cause's request asks for (RX2 review B1)."""
                if not resolved:
                    return False
                for ref in refs:
                    known = served.get(str(ref).split(":", 1)[0])
                    if known and requested(known, resolved):
                        return True
                return False

            on_request = cause.get("route") == "on_request"
            # fetched: a successful call actually served the requested evidence; for an in_digest
            # cause, Available and Used read the cause's own items as before (RX0-D §6.3)
            fetched = request_hit(fetched_refs) if on_request else None
            if on_request:
                available = bool(fetched) and request_hit(shown)
                direct = bool(fetched) and (request_hit(cited) or request_hit(details))
            else:
                available = item_hit(shown)
                direct = item_hit(cited) or item_hit(details)
            # Used, related (RX0-D §6.3): a call that tests what one of the cause's items names
            facts = [
                item_facts(objects.get(str(i.get("ref", "")).split(".")[0], [])) for i in items
            ]
            rel = any(related(served[ref], fx, None) for ref in later_refs for fx in facts) or any(
                related({"kind": "judge"}, fx, call) for call in judge_calls for fx in facts
            )
            rows.append({"role": cause.get("role", "decisive"), "route": cause.get("route"),
                         "request_fetched": fetched, "available": available, "used_direct": direct,
                         "used_related": rel, "used": direct or rel,
                         "covered": item_hit(cited) or request_hit(cited),
                         "p1_unread": available and not (direct or rel)})  # fmt: skip
        # P2, scores alone: the final commentary cites only judgements and lines while a board item
        # of a key cause was shown (RX0-D §6.3)
        cited_kinds = {
            served[r.split(":", 1)[0]]["kind"] for r in cited if r.split(":", 1)[0] in served
        }
        board_shown = any(served.get(r, {}).get("kind") == "board_item" and r in shown and
                          any(served[r]["identity"] == i.get("identity") for c in causes
                              for i in c.get("items") or []) for r in shown)  # fmt: skip
        p2 = (
            bool(f)
            and bool(cited_kinds)
            and cited_kinds <= {"judgement", "search_line"}
            and board_shown
        )
        out.append({"run": run.name, "arm": start["arm"], "set": start["set"],
                    "game": start["game"], "ply": ply, "commented": f is not None,
                    "p2_scores_alone": p2, "causes": rows})  # fmt: skip
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
