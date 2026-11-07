"""Brief-view keep rules compared on the replay's positions: size of the pieces record and retention of
the key-cause squares and the agents' cited squares. A: TO-D §2.1 as implemented; B: every piece
attacked, pinned or attacking an enemy piece (plus A); C: B and the defenders of the kept pieces."""

import json
import re
import shutil
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/mnt/d/00_프로젝트/Calliope")
sys.path.insert(0, "/mnt/c/Users/jihun/AppData/Local/Temp/claude/a611d286c2c1f808/9fb2b0e8-67a5-46a5-a598-e5bd099a5720/scratchpad/trial")
from calliope.agent import Session  # noqa: E402
from calliope.agent.brief import _brief_entry, _squares, exposed_squares, kept_squares  # noqa: E402
from calliope.facts.search import StockfishEngine  # noqa: E402
from tools.rx.manifest import MANIFEST, RX_DATA, engine_path, pgn_text  # noqa: E402

sys.argv = [sys.argv[0], "/dev/null"]
import replay_to as R  # noqa: E402  (reuses its call and citation lists; its run writes /dev/null)


def variant(name, pieces, exchange, status, last):
    a = kept_squares(pieces, exposed_squares(exchange), status, last)
    if name == "A":
        return a
    b = set(a)
    for e in pieces:
        enemy = (e.get("attacks") or {}).get("enemy") or []
        if e.get("attacker_count") or e.get("absolutely_pinned") is True or enemy:
            b.add(e["square"])
    if name == "B":
        return b
    by = {e["square"]: e for e in pieces}
    c = set(b)
    for sq in list(b):
        c |= set(_squares((by.get(sq) or {}).get("defenders")))
    return c & set(by)


def size(pieces, kept):
    return len(json.dumps([_brief_entry(e) for e in pieces if e["square"] in kept], ensure_ascii=False))


positions = defaultdict(set)  # set -> {(game, position json)}
for set_name, rows in R.calls.items():
    for tool, args in rows:
        if tool == "facts":
            positions[set_name].add((args.get("game"), json.dumps(args.get("position"), sort_keys=True), None))
stats = {v: {"size": [], "kc": [0, 0], "cited": [0, 0]} for v in "ABC"}
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
for set_name in ("train", "validation"):
    tmp = Path(tempfile.mkdtemp(prefix="rx-variants-"))
    shutil.copytree(RX_DATA / "base" / set_name / "data", tmp / "data")
    s = Session(tmp / "data", lambda: StockfishEngine.start(engine_path()), R.LIMITS)
    try:
        ids = {e["name"]: s.open_game(pgn=pgn_text(set_name, e, RX_DATA / "sets"))["game"]
               for e in manifest["sets"][set_name]}

        def records(game, position):
            fam = s.facts(game, position, ["pieces", "exchange", "status"], view="full")["families"]
            path = s.path(s.game(game), position)
            return (fam["pieces"]["record"]["pieces"], fam["exchange"]["record"], fam["status"]["record"],
                    path[-1][2:4] if path else None)

        for game, pos, _ in positions[set_name]:
            try:
                p, x, st, last = records(game, json.loads(pos))
            except Exception:  # noqa: BLE001
                continue
            for v in "ABC":
                stats[v]["size"].append(size(p, variant(v, p, x, st, last)))
        for game, prop in R.cited[set_name]:
            sq = [prop.get(k) for k in ("attacker", "target", "defender", "defended", "pinned", "pinner", "piece")]
            sq = [q for q in sq + list(prop.get("checkers") or []) if isinstance(q, str) and R.SQUARE.fullmatch(q)]
            try:
                p, x, st, last = records(game, prop["position"])
            except Exception:  # noqa: BLE001
                continue
            for v in "ABC":
                k = variant(v, p, x, st, last)
                stats[v]["cited"][1] += len(sq)
                stats[v]["cited"][0] += sum(q in k for q in sq)
        for path in sorted((R.REFS / set_name).glob("*.json")):
            ref = json.loads(path.read_text(encoding="utf-8"))
            named = set()
            for c in ref.get("key_causes") or []:
                named |= set(R.SQUARE.findall(c.get("text", "")))
            for at in ("before", "after"):
                p, x, st, last = records(ids[ref["game"]], {"ply": ref["ply"], "at": at})
                need = [e["square"] for e in p if e["square"] in named and R.in_play(e)]
                for v in "ABC":
                    k = variant(v, p, x, st, last)
                    stats[v]["kc"][1] += len(need)
                    stats[v]["kc"][0] += sum(q in k for q in need)
            # the full record's pieces size, for scale
        stats.setdefault("full", {"size": []})
        for game, pos, _ in positions[set_name]:
            try:
                p, *_ = records(game, json.loads(pos))
            except Exception:  # noqa: BLE001
                continue
            stats["full"]["size"].append(len(json.dumps(p, ensure_ascii=False)))
    finally:
        s.close()
        shutil.rmtree(tmp, ignore_errors=True)
for v, d in stats.items():
    line = f"{v}: pieces median {statistics.median(d['size']):7,.0f} chars (n={len(d['size'])})"
    if "kc" in d:
        line += f" | key causes {d['kc'][0]}/{d['kc'][1]} | cited {d['cited'][0]}/{d['cited'][1]}"
    print(line)
