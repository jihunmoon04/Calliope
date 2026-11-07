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
    return bool(entry.get("attacker_count")) or entry.get("absolutely_pinned") not in (None, False) or bool(enemy)


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
    board_props = []
    pins = [0, 0]
    board_total = [0, 0]
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
            # (c) key causes (TO review F1): every position before and after the move, along the
            # subject's played and best engine lines (the record's whole PV) and along each
            # on_request cause's resolved line; every piece on a square a key cause names, with no
            # filter; each one left out is listed with what its full record says it does
            # (d) board items: every proposition of the digest's board items, at its position
            for path in sorted((REFS / set_name).glob("*.json")):
                ref = json.loads(path.read_text(encoding="utf-8"))
                gid = ids[ref["game"]]
                game = session.game(gid)
                uci = list(game.parsed.uci)
                base = uci[: ref["ply"] - 1]
                named = set()
                for cause in ref.get("key_causes") or []:
                    named |= set(SQUARE.findall(cause.get("text", "")))
                walks = {"before": (base, []), "after": (base, [uci[ref["ply"] - 1]])}
                subject = ref["full"]["analysis"]["judgements"][0]
                for name in ("played", "best"):
                    line = subject.get(name) or {}
                    walks[name] = (base, [m["uci"] for m in line.get("pv") or []])
                for n, cause in enumerate(ref.get("key_causes") or []):
                    resolved = (cause.get("request") or {}).get("resolved") or {}
                    if resolved.get("tool") == "explore":
                        walks[f"request{n}"] = (list(resolved["from"]), list(resolved["moves"]))
                seen = set()
                for walk, (start, moves) in walks.items():
                    steps = [moves[:k] for k in range(len(moves) + 1)] if walk not in ("before", "after") else [moves]
                    for k, part in enumerate(steps):
                        position = tuple(start + part)
                        if position in seen:
                            continue
                        seen.add(position)
                        at = {"from_root": list(position)}
                        try:
                            full = session.facts(gid, at, ["pieces"], view="full")["families"]["pieces"]["record"]
                            brief = session.facts(gid, at, ["pieces"], view="brief")["families"]["pieces"]["record"]
                        except Exception:  # noqa: BLE001 - a line past the game's end
                            continue
                        kept = kept_set(brief)
                        shown = {b["piece"][1:]: b for b in brief.get("pieces") or []}
                        for e in full.get("pieces") or []:  # TO review N1: every pin, with its pinner
                            pin = e.get("absolutely_pinned")
                            if isinstance(pin, dict):
                                pins[0] += 1
                                b = shown.get(e["square"]) or {}
                                pinner = (b.get("absolutely_pinned") or {}).get("pinner", "")
                                if pinner[1:] == pin.get("pinner"):
                                    pins[1] += 1
                        for e in full.get("pieces") or []:
                            if e["square"] not in named:
                                continue
                            kc_total += 1
                            if e["square"] in kept:
                                kc_kept += 1
                                continue
                            enemy = (e.get("attacks") or {}).get("enemy") or []
                            report["misses"].append({
                                "set": set_name, "check": "key_cause", "moment": f"{ref['game']}-{ref['ply']}",
                                "walk": walk, "ply_in_walk": k, "square": e["square"], "piece": str(e["piece_type"]),
                                "color": str(e.get("color")), "attacked": bool(e.get("attacker_count")),
                                "attacks_enemy": enemy, "pinned": e.get("absolutely_pinned") not in (None, False),
                                "defenders": [d.get("square") if isinstance(d, dict) else d for d in e.get("defenders") or []],
                                "named_in_brief_omitted": any(o[1:] == e["square"] for o in brief.get("omitted") or [])})
                # (d) board items
                for item_key in ("changes", "scene"):
                    items = ref["digest"]["board"].get(item_key) or []
                    items = items if isinstance(items, list) else [items]
                    for item in items:
                        for prop in item.get("propositions") or []:
                            board_props.append((set_name, gid, ref["game"], ref["ply"], prop))
                same = ref["digest"]["board"].get("same_reply")
                if isinstance(same, dict):
                    for prop in same.get("propositions") or []:
                        board_props.append((set_name, gid, ref["game"], ref["ply"], prop))
            for set_n, gid, gname, gply, prop in [b for b in board_props if b[0] == set_name]:
                squares = [prop.get(k) for k in ("attacker", "target", "defender", "defended", "pinned", "pinner", "piece")]
                squares = [q for q in squares + list(prop.get("checkers") or []) if isinstance(q, str) and SQUARE.fullmatch(q)]
                if not squares or "position" not in prop:
                    continue
                try:
                    fam = session.facts(gid, prop["position"], ["pieces"], view="brief")["families"]["pieces"]["record"]
                except Exception:  # noqa: BLE001
                    continue
                kept = kept_set(fam)
                for q in squares:
                    board_total[0] += 1
                    if q in kept:
                        board_total[1] += 1
                    else:
                        report["misses"].append({"set": set_name, "check": "board", "moment": f"{gname}-{gply}",
                                                 "kind": prop.get("kind"), "position": prop["position"], "square": q})
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
    report["key_causes"] = {"kept": kc_kept, "total": kc_total, "filter": "none"}
    report["board"] = {"kept": board_total[1], "total": board_total[0]}
    report["pins"] = {"shown_with_pinner": pins[1], "total": pins[0]}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "misses"}, ensure_ascii=False, indent=1))
    print("misses:", len(report["misses"]))
    for m in report["misses"][:40]:
        print("  ", json.dumps(m, ensure_ascii=False)[:700])


if __name__ == "__main__":
    main()
