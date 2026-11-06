"""Collect the trial's final commentaries next to the rx2-2 arm A baseline and the key causes."""

import json
import sys
from pathlib import Path

sys.path.insert(0, "/mnt/d/00_프로젝트/Calliope")
from tools.rx.check import finals, lines  # noqa: E402
from tools.rx.manifest import RX_DATA  # noqa: E402

REPO = Path("/mnt/d/00_프로젝트/Calliope")
TRIAL = RX_DATA / "trial" / "runs"
GAMES = {"185264271324": [29, 45, 67], "184800218248": [12, 57, 58]}
out = Path(sys.argv[1])


def text(f):
    if not f:
        return "(해설 없음)"
    return " ".join(s.get("text", "") if isinstance(s, dict) else str(s) for s in (f["sentences"] or []))


runs = []  # (label, game, run_dir, totals)
for d in sorted(TRIAL.iterdir()):
    agent = d / "agent.jsonl"
    if d.name.startswith("trial-cc-haiku-"):
        runs.append(("CC-haiku +규칙 +참조", d.name.rsplit("-", 1)[1], d, None))
    elif agent.exists():
        ls = lines(agent)
        st, end = ls[0], ls[-1]
        t = st.get("trial", {})
        label = st["model"].split("/")[1] + (" +규칙" if t.get("rules") else "") + (" +참조" if t.get("ref") else "")
        runs.append((label, st["game"], d, end.get("totals")))
for line in (RX_DATA / "batches" / "rx2-2.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r["arm"] == "A" and r["game"] in GAMES and (r.get("result") or {}).get("run"):
        d = RX_DATA / "runs" / r["result"]["run"]
        runs.append(("기준 luna (rx2-2 A)", r["game"], d, (r.get("result") or {}).get("totals")))

md = ["# 해설 시험 결과 (2026-11-06)\n"]
for game, plies in GAMES.items():
    md.append(f"\n## 대국 {game}\n")
    for ply in plies:
        ref = json.loads((REPO / f"tools/rx/references_v1/validation/{game}-{ply}.json").read_text(encoding="utf-8"))
        md.append(f"\n### ply {ply}: {ref['move']}\n\n**핵심 원인(결정적):**\n")
        for kc in ref["key_causes"]:
            if kc.get("role") == "decisive":
                md.append(f"> {kc['text']}\n")
        md.append("")
        for label, g, d, totals in runs:
            if g != game:
                continue
            f = finals(d, plies)[ply]
            md.append(f"- **{label}** `{d.name[:12]}`: {text(f)}")
md.append("\n## 실행\n")
for label, g, d, totals in runs:
    calls = sum(1 for x in lines(d / "tools.jsonl") if x.get("type") == "call") if (d / "tools.jsonl").exists() else "?"
    md.append(f"- {label}, {g}, `{d.name}`: tool calls {calls}, totals {json.dumps(totals)}")
out.write_text("\n".join(md) + "\n", encoding="utf-8")
print(out)
