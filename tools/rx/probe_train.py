"""Call one Calliope tool on a Train game, on a copy of Train's sealed base (RX4-D §2.1).

Run in WSL from this directory:
  python probe.py <game> ply <ply> [digest|full]
  python probe.py <game> explore '<position json>' '<uci moves json>'
  python probe.py <game> facts '<position json>' '<families json>'
  python probe.py <game> judge_move '<position json>' <uci move>
  python probe.py <game> detail <ref>
<game> is a Train game: hung, rapid, fresh, fourth. A position is the tools' own form, e.g.
{"ply": 37} or {"from_root": ["e2e4", ...]}. Only Train is reachable.
"""

import json
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("CALLIOPE_REPO", "/mnt/d/00_프로젝트/Calliope"))
sys.path[:0] = [str(REPO), str(REPO / "src")]

from tools.rx.manifest import MANIFEST, RX_DATA, pgn_text
from tools.rx.reference import probe_session

game, tool, *args = sys.argv[1:]
engine = os.environ["CALLIOPE_STOCKFISH_PATH"]
entries = {e["name"]: e for e in json.loads(MANIFEST.read_text(encoding="utf-8"))["sets"]["train"]}
if game not in entries:
    sys.exit(f"{game}: not a Train game ({', '.join(entries)})")
with probe_session("train", engine) as s:
    gid = s.open_game(pgn=pgn_text("train", entries[game], RX_DATA / "sets"))["game"]
    if tool == "ply":
        out = s.ply(gid, int(args[0]), *(args[1:2]))
    elif tool == "explore":
        out = s.explore(gid, json.loads(args[0]), json.loads(args[1]), search=True)
    elif tool == "facts":
        out = s.facts(gid, json.loads(args[0]), json.loads(args[1]) if len(args) > 1 else None)
    elif tool == "judge_move":
        out = s.judge_move(gid, json.loads(args[0]), args[1])
    elif tool == "detail":
        out = s.detail(gid, args[0])
    else:
        sys.exit(f"{tool}: one of ply, explore, facts, judge_move, detail")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
