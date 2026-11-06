"""Session folders for the Claude Code arm: .mcp.json, serve.sh, task.md (same content as the API arm)."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.argv = ["x"]
import trial  # noqa: E402
from tools.rx import run as rx  # noqa: E402
from tools.rx.manifest import MANIFEST, RX_DATA, verify  # noqa: E402

ROOT = Path("/mnt/d/00_프로젝트/rx-trial")
REPO = "/mnt/d/00_프로젝트/Calliope"
ENGINE = f"{REPO}/.venv/stockfish19/stockfish/stockfish-windows-x86-64-universal.exe"
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
guide = (Path(REPO) / "src/calliope/agent/prompts/commentary_ko_v8.md").read_text(encoding="utf-8")
rules = (HERE / "a2_rules.md").read_text(encoding="utf-8")

for game in ("185264271324", "184800218248"):
    entry = next(e for e in manifest["sets"]["validation"] if e["name"] == game)
    pgn = verify("validation", entry, trial.PGNS)
    folder = ROOT / f"cc-haiku-{game}"
    (folder / ".claude").mkdir(parents=True, exist_ok=True)
    run_id = f"trial-cc-haiku-{game}"
    work = RX_DATA / "trial" / "work" / run_id
    (folder / "serve.sh").write_text(f"""set -u
source ~/calliope-venv/bin/activate
export CALLIOPE_STOCKFISH_PATH={ENGINE}
export CALLIOPE_RUN_ID={run_id}
export CALLIOPE_RUN_RECORDS={trial.RECORDS}
mkdir -p {trial.RECORDS}/{run_id}
if [ ! -d {work} ]; then mkdir -p {work.parent}; cp -r {RX_DATA}/base/validation/data {work}; chmod -R u+w {work}; fi
cd {REPO}
exec python -m tools.mcp --data {work} --guide commentary_ko_v8 2>> {trial.RECORDS}/{run_id}/server.stderr
""", encoding="utf-8", newline="\n")
    (folder / ".mcp.json").write_text(json.dumps({"mcpServers": {"calliope": {
        "command": "wsl", "args": ["-d", "Ubuntu", "--", "bash", f"{folder}/serve.sh"]}}}, indent=1), encoding="utf-8")
    (folder / ".claude" / "settings.local.json").write_text(json.dumps(
        {"enableAllProjectMcpServers": True, "enabledMcpjsonServers": ["calliope"]}, indent=1), encoding="utf-8")
    moments = rx.numbered(pgn, entry["moments"])
    task = rx.TASK_BY_ID.format(game_id=entry["game_id"], moments=", ".join(moments))
    task += trial.reference_block("validation", game, sorted(entry["moments"]), pgn)
    (folder / "task.md").write_text("# 해설 가이드\n\n" + guide + "\n\n" + rules + "\n\n# 작업\n\n" + task + "\n",
                                    encoding="utf-8")
    print(folder, len((folder / "task.md").read_text(encoding="utf-8")))
