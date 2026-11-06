"""Quick commentary trial (not a reviewed packet): arm A (guide v8) plus
  --rules  the A2 rules appended to the system prompt
  --ref    each fixed moment's digest and full view (key causes stripped) in the task message
Records go to ~/.local/share/calliope/rx/trial/runs, apart from the RX batches.

python trial.py --model M --game NAME [--rules] [--ref] [--cache] [--runs N]

Note: every run of MH (pilot, cache test, batch trial-haiku-1) was made without session_id, which
the runner now sends (MH review F2).
"""

import argparse
import json
import sys
from pathlib import Path

import anyio

REPO = Path("/mnt/d/00_프로젝트/Calliope")
sys.path.insert(0, str(REPO))

from tools.rx import run as rx  # noqa: E402
from tools.rx.manifest import MANIFEST, RX_DATA, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
PGNS = RX_DATA / "sets"
RECORDS = RX_DATA / "trial" / "runs"


def reference_block(set_name: str, game: str, plies: list[int], pgn: str) -> str:
    names = rx.numbered(pgn, plies)
    parts = ["\n\n아래는 각 장면에 대해 Calliope가 계산해 둔 자료야(`ply`의 요약과 `ply(view=\"full\")`의 전체 결과). "
             "읽고 해설에 써. 기물이 오가는 수순은 explore로 직접 둬 보고 확인해. "
             "제출하기 전에 그 장면의 `ply`를 한 번 불러서 근거 id를 받아."]
    for ply, name in zip(plies, names):
        ref = json.loads((REPO / "tools/rx/references_v1" / set_name / f"{game}-{ply}.json").read_text(encoding="utf-8"))
        data = {"ply": ply, "move": name, "fen_before": ref["fen_before"], "moves_before": ref["moves_before"],
                "digest": ref["digest"], "full": ref["full"]}
        parts.append(f"\n### {name} (ply {ply})\n```json\n{json.dumps(data, ensure_ascii=False, default=str)}\n```")
    return "".join(parts)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--game", required=True)
    p.add_argument("--set", default="validation")
    p.add_argument("--rules", action="store_true")
    p.add_argument("--ref", action="store_true")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--cache", action="store_true", help="Anthropic cache_control (RunSpec.cache)")
    a = p.parse_args()

    from tools.rx.model import OpenRouter, read_env_file

    # MH review F1: the marks are made by OpenRouter.body only; this passes the switch. As run
    # (commit b19f72e), the wrapper marked the system and the last text message itself on a body
    # that had none: the same two marks, so `--cache` reproduces the cached runs and its absence the
    # uncached ones.
    usages = []
    plain_post = OpenRouter._post

    def logged_post(self, body):
        doc = plain_post(self, body)
        usages.append(doc.get("usage") or {})
        return doc

    OpenRouter._post = logged_post

    read_env_file(REPO / ".env")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = next(e for e in manifest["sets"][a.set] if e["name"] == a.game)
    pgn = verify(a.set, entry, PGNS)
    tag = {"trial": True, "rules": a.rules, "ref": a.ref, "cache": a.cache}

    rules = (HERE / "a2_rules.md").read_text(encoding="utf-8") if a.rules else ""
    rx.lessons = lambda spec: (rules, {"lesson_set": None, "lesson_ids": [], "trial": tag})
    if a.ref:
        block = reference_block(a.set, a.game, sorted(entry["moments"]), pgn)
        rx.TASK_BY_ID = rx.TASK_BY_ID + block.replace("{", "{{").replace("}", "}}")

    spec = rx.RunSpec(arm="A", set_name=a.set, game=a.game, pgn=pgn, moments=entry["moments"],
                      base=RX_DATA / "base" / a.set, records=RECORDS, work=RX_DATA / "work",
                      model=a.model, game_id=entry.get("game_id"), cache=a.cache)
    RECORDS.mkdir(parents=True, exist_ok=True)
    for _ in range(a.runs):
        result = anyio.run(rx.run_once, spec)
        print(json.dumps({"model": a.model, "game": a.game} | tag | result, ensure_ascii=False), flush=True)
        (RECORDS / result["run"] / "usage.json").write_text(json.dumps(usages, indent=1), encoding="utf-8")
        usages.clear()


if __name__ == "__main__":
    main()
