"""AF-D §7.2 step 3: the pilot (`H@v9`, harness rev. 8, one run on each development game) in
structured form, from the batch `af-pilot-1` and its runs' records — no conversation text kept.

Per run: its end, tokens and cost. Per moment: the frame check's final state, its holds, what an
exhausted moment would have held, `uncheckable`, `ambiguous` (A9) and `search_numbers`; the final
submission's sentence count. Over the run's tool calls: every `explore` answer's plies' sources,
whether it gave an `analysis_score` (and from which `root_ply`) or an `end_score` (a search), a
`departs_at`; whether a line started **before** the moment's own ply (§10.1's `s61` case);
`search: "fresh"` calls; `compare_lines`' ranking source; disagreements.

    python docs/design/rx-evidence/af/pilot_summary.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RX = Path.home() / ".local/share/calliope/rx"
BATCH = sys.argv[1] if len(sys.argv) > 1 else "af-pilot-2"


def read(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def body(call: dict) -> dict:
    answer = call.get("answer")
    try:
        doc = json.loads(answer) if isinstance(answer, str) else answer
        if isinstance(doc, dict) and "content" in doc:
            doc = json.loads(doc["content"][0]["text"])
        return doc if isinstance(doc, dict) else {}
    except (ValueError, KeyError, TypeError, IndexError):
        return {}


def summary(run_id: str) -> dict:
    agent = read(RX / "runs" / run_id / "agent.jsonl")
    tools = read(RX / "runs" / run_id / "tools.jsonl")
    start = agent[0]
    moments = start.get("moments") or []
    frames: dict[int, list[dict]] = {}
    for line in agent:
        if line.get("type") == "frames":
            frames.setdefault(line["ply"], []).append(line)
    states = {line["ply"]: line["state"] for line in agent
              if line.get("type") == "harness" and line.get("stage") == "sentence_state"}  # fmt: skip
    per_moment = {}
    for ply in moments:
        lines_ = frames.get(ply, [])
        sent = next((x for x in reversed(lines_) if x.get("state") in ("passed", "exhausted")), {})
        per_moment[ply] = {
            "state": states.get(ply, "not_run"),
            "holds": sum(x.get("state") == "held" for x in lines_),
            "held_rules": [h["rule"] for x in lines_ if x.get("state") == "held"
                           for h in x.get("held") or []],
            "unsent_holds": [h["rule"] for h in sent.get("unsent_holds") or []],
            "uncheckable": [u["rule"] for u in sent.get("uncheckable") or []],
            "ambiguous": len(sent.get("ambiguous") or []),
            "search_numbers": sent.get("search_numbers", 0),
        }
    explores, compares, fresh, early = [], [], 0, 0
    for call in tools:
        if call.get("type") != "call":
            continue
        args, doc = call.get("arguments") or {}, body(call)
        if call.get("tool") == "explore":
            book = doc.get("ledger") or {}
            position = args.get("position") or {}
            ply = position.get("ply")
            base = (ply if position.get("at", "after") == "after" else (ply or 1) - 1) if ply else None
            moment = next((m for m in moments if base is not None and m - 1 == base), None)
            before = next((m for m in moments if base is not None and m - 1 > base
                           and m - 1 - base <= len(args.get("moves") or [])), None)  # fmt: skip
            early += before is not None
            fresh += args.get("search") == "fresh"
            score = book.get("analysis_score")
            explores.append({
                "position": position, "moves": len(args.get("moves") or []),
                "search": args.get("search"), "continue": args.get("continue_with"),
                "sources": dict(Counter(p.get("source") for p in book.get("plies") or [])),
                "analysis_score": (score.get("root_ply") if isinstance(score, dict) and "root_ply"
                                   in score else sorted(score) if isinstance(score, dict) else None),
                "end_score": (book.get("end_score") or {}).get("source"),
                "departs_at": (doc.get("departs_at") or {}).get("ply"),
                "at_moment": moment, "starts_before_moment": before,
                "error": doc.get("error") if "error" in doc else None,
            })  # fmt: skip
        elif call.get("tool") == "compare_lines":
            compares.append({"ply": args.get("ply"), "candidates": args.get("candidates"),
                             "ranking": (doc.get("ranking") or {}).get("source")})  # fmt: skip
    disagreements = [x for x in tools if x.get("type") == "disagreement"]
    end = next((x for x in reversed(agent) if x.get("type") == "end"), {})
    return {"run": run_id, "game": start.get("game"), "variant": start.get("variant"),
            "harness": start.get("harness"), "frames": start.get("harness_frames"),
            "end": end.get("reason"), "totals": end.get("totals"), "moments": per_moment,
            "explore": explores, "compare_lines": compares, "fresh_calls": fresh,
            "lines_starting_before_a_moment": early, "disagreements": len(disagreements),
            "disagreeing": sum(bool(x.get("disagrees_with_analysis")) for x in disagreements)}  # fmt: skip


def main() -> None:
    rows = read(RX / "batches" / f"{BATCH}.jsonl")
    out = {"batch": BATCH, "runs": []}
    for row in rows:
        result = row.get("result") or {}
        if result.get("run"):
            out["runs"].append(summary(result["run"]) | {"seconds": row.get("seconds"),
                                                         "cost": (result.get("totals") or {})
                                                         .get("cost")})  # fmt: skip
        else:
            out["runs"].append({"game": row.get("game"), "error": row.get("stderr")})
    (HERE / f"{BATCH}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                        encoding="utf-8")  # fmt: skip
    print(json.dumps(out, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
