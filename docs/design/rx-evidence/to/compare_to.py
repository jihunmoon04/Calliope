"""compare_lines on the 24 fixed moments of the RX bases: answer size, lines' lengths and extensions,
searches, and 23.Rxe5 (185264271324 ply 45) against the key-cause sheet."""

import json
import shutil
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/mnt/d/00_프로젝트/Calliope")
from calliope.agent import Limits, Session  # noqa: E402
from calliope.facts.search import StockfishEngine  # noqa: E402
from tools.rx.manifest import MANIFEST, RX_DATA, engine_path, pgn_text  # noqa: E402

LIMITS = Limits(max_nodes_per_tree=500_000, max_nodes_total=5_000_000, max_handles=1_000_000,
                max_searches=10_000)
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
sizes, rows = [], []
for set_name in ("train", "validation"):
    tmp = Path(tempfile.mkdtemp(prefix="rx-compare-"))
    shutil.copytree(RX_DATA / "base" / set_name / "data", tmp / "data")
    for f in (tmp / "data").rglob("*"):
        f.chmod(0o644 if f.is_file() else 0o755)
    s = Session(tmp / "data", lambda: StockfishEngine.start(engine_path()), LIMITS)
    try:
        for entry in manifest["sets"][set_name]:
            gid = s.open_game(pgn=pgn_text(set_name, entry, RX_DATA / "sets"))["game"]
            for ply in sorted(entry["moments"]):
                a = s.compare_lines(gid, ply)
                n = len(json.dumps(a, ensure_ascii=False))
                sizes.append(n)
                rows.append((f"{entry['name']}-{ply}", a["move"], n,
                             {k: (len(v["moves"]), v["extended"], v["end"].get("end_score"), v["material"][-1])
                              for k, v in a["lines"].items()}, a["searches"]))
                if entry["name"] == "185264271324" and ply == 45:
                    print(json.dumps(a, ensure_ascii=False, indent=1)[:3500])
    finally:
        s.close()
        shutil.rmtree(tmp, ignore_errors=True)
print("size median", statistics.median(sizes), "max", max(sizes))
for r in rows:
    print(r)
