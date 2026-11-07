"""TO-D §6.1: replay through the v7 tools on the RX bases (no model).
(a) every recorded explore and facts call, brief against full (searches left out: unchanged, small);
(b) every piece an accepted submission cited (attack, defence, pin, exposed, check): kept in the brief
    view at its position;
(c) every square a reviewed key cause names, at the positions before and after its move, when a piece
    there is in play in the full record (attacked, pinned or attacking): kept in the brief view.
"""

import glob
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/mnt/d/00_프로젝트/Calliope")
from calliope.agent import Limits, Session  # noqa: E402
from calliope.facts.search import StockfishEngine  # noqa: E402
from tools.rx.manifest import MANIFEST, RX_DATA, engine_path, pgn_text  # noqa: E402

REFS = Path("/mnt/d/00_프로젝트/Calliope/tools/rx/references_v1")
OUT = Path(sys.argv[1])
SQUARE = re.compile(r"(?<![a-z])([a-h][1-8])(?![0-9])")
LIMITS = Limits(max_nodes_per_tree=500_000, max_nodes_total=5_000_000, max_handles=1_000_000,
                max_uncached_plies=10_000, max_uncached_plies_per_call=10_000)


def size(x) -> int:
    return len(json.dumps(x, ensure_ascii=False))


def kept_set(answer_pieces) -> set:
    return {e["piece"][1:] for e in (answer_pieces or {}).get("pieces") or []}


def in_play(entry) -> bool:
    enemy = (entry.get("attacks") or {}).get("enemy") or []
    return bool(entry.get("attacker_count")) or entry.get("absolutely_pinned") is True or bool(enemy)


manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
calls = defaultdict(list)  # set -> recorded (tool, arguments)
cited = defaultdict(list)  # set -> accepted position propositions
for agent in glob.glob(str(RX_DATA / "runs/*/agent.jsonl")) + glob.glob(str(RX_DATA / "trial/runs/*/agent.jsonl")):
    d = Path(agent).parent
    try:
        start = json.loads(Path(agent).read_text(encoding="utf-8").splitlines()[0])
    except (ValueError, IndexError):
        continue
    set_name = start.get("set")
    if set_name not in ("train", "validation"):
        continue
    for line in Path(agent).read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        if x["type"] == "response":
            for c in x["message"].get("tool_calls") or []:
                if c["function"]["name"] in ("explore", "facts"):
                    try:
                        calls[set_name].append((c["function"]["name"], json.loads(c["function"]["arguments"] or "{}")))
                    except ValueError:
                        pass
    tools = d / "tools.jsonl"
    if tools.exists():
        rows = [json.loads(line) for line in tools.read_text(encoding="utf-8").splitlines()]
        games = {r.get("call_id"): (r.get("arguments") or {}).get("game") for r in rows if r.get("type") == "call"}
        for x in rows:
            if x.get("type") != "submission":
                continue
            for s in x["subjects"]:
                if s.get("outcome") != "accepted":
                    continue
                game = games.get(x.get("call_id"))
                for p in (s.get("submitted") or {}).get("propositions") or []:
                    if p.get("kind") in ("attack", "defence", "pin", "exposed", "check"):
                        cited[set_name].append((game, p))

def main():
    global calls, cited
    report = {"sizes": {}, "cited": {}, "key_causes": {}, "misses": []}
    sizes = defaultdict(lambda: {"brief": [], "full": []})
    cited_total = cited_kept = 0
    kc_total = kc_kept = 0
    for set_name in ("train", "validation"):
        tmp = Path(tempfile.mkdtemp(prefix="rx-replay-"))
        shutil.copytree(RX_DATA / "base" / set_name / "data", tmp / "data")
        session = Session(tmp / "data", lambda: StockfishEngine.start(engine_path()), LIMITS)
        try:
            ids = {}
            for entry in manifest["sets"][set_name]:
                ids[entry["name"]] = session.open_game(pgn=pgn_text(set_name, entry, RX_DATA / "sets"))["game"]
            known = set(ids.values())
            # (a) sizes
            for tool, args in calls[set_name]:
                if args.get("game") not in known:
                    continue
                try:
                    if tool == "explore":
                        b = session.explore(args["game"], args["position"], args.get("moves"), False, "brief")
                        f = session.explore(args["game"], args["position"], args.get("moves"), False, "full")
                    else:
                        a = dict(game_id=args["game"], position=args["position"], families=args.get("families"))
                        b = session.facts(a["game_id"], a["position"], a["families"], view="brief")
                        f = session.facts(a["game_id"], a["position"], a["families"], view="full")
                except Exception as error:  # noqa: BLE001 - a recorded call refused then is refused now
                    sizes[tool + " refused"]["brief"].append(0)
                    continue
                sizes[tool]["brief"].append(size(b))
                sizes[tool]["full"].append(size(f))
            # (b) cited pieces
            for game, p in cited[set_name]:
                if game not in known:
                    continue
                squares = [p.get(k) for k in ("attacker", "target", "defender", "defended", "pinned", "pinner", "piece")]
                squares += list(p.get("checkers") or [])
                squares = [q for q in squares if isinstance(q, str) and SQUARE.fullmatch(q)]
                try:
                    fam = session.facts(game, p["position"], ["pieces"], view="brief")["families"]["pieces"]["record"]
                except Exception:  # noqa: BLE001
                    continue
                kept = kept_set(fam)
                for q in squares:
                    cited_total += 1
                    if q in kept:
                        cited_kept += 1
                    else:
                        report["misses"].append({"set": set_name, "check": "cited", "game": game,
                                                 "position": p["position"], "kind": p["kind"], "square": q})
            # (c) key causes
            for path in sorted((REFS / set_name).glob("*.json")):
                ref = json.loads(path.read_text(encoding="utf-8"))
                gid = ids[ref["game"]]
                named = set()
                for cause in ref.get("key_causes") or []:
                    named |= set(SQUARE.findall(cause.get("text", "")))
                for at in ("before", "after"):
                    position = {"ply": ref["ply"], "at": at}
                    full = session.facts(gid, position, ["pieces"], view="full")["families"]["pieces"]["record"]
                    brief = session.facts(gid, position, ["pieces"], view="brief")["families"]["pieces"]["record"]
                    kept = kept_set(brief)
                    for e in full.get("pieces") or []:
                        if e["square"] in named and in_play(e):
                            kc_total += 1
                            if e["square"] in kept:
                                kc_kept += 1
                            else:
                                report["misses"].append({
                                    "set": set_name, "check": "key_cause",
                                    "moment": f"{ref['game']}-{ref['ply']}", "at": at,
                                    "square": e["square"], "piece": str(e["piece_type"]),
                                    "color": str(e.get("color")),
                                    "attackers": [(a.get("square"), str(a.get("piece_type"))) for a in e.get("attackers") or []],
                                    "defenders": [d.get("square") if isinstance(d, dict) else d for d in e.get("defenders") or []],
                                    "enemy": (e.get("attacks") or {}).get("enemy"),
                                    "causes": [c["text"] for c in ref["key_causes"] if e["square"] in c.get("text", "")]})
        finally:
            session.close()
            shutil.rmtree(tmp, ignore_errors=True)

    for tool, v in sizes.items():
        if v["full"]:
            report["sizes"][tool] = {"calls": len(v["full"]),
                                     "full_median": statistics.median(v["full"]),
                                     "brief_median": statistics.median(v["brief"]),
                                     "brief_p90": sorted(v["brief"])[int(0.9 * (len(v["brief"]) - 1))],
                                     "ratio_median": statistics.median(b / f for b, f in zip(v["brief"], v["full"]))}
        else:
            report["sizes"][tool] = {"calls": len(v["brief"])}
    report["cited"] = {"kept": cited_kept, "total": cited_total}
    report["key_causes"] = {"kept": kc_kept, "total": kc_total}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "misses"}, ensure_ascii=False, indent=1))
    print("misses:", len(report["misses"]))
    for m in report["misses"][:40]:
        print("  ", json.dumps(m, ensure_ascii=False)[:700])


if __name__ == "__main__":
    main()
