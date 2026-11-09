"""AF-D §7.2 step 1(b): harness rev. 8's frame check (`tools/rx/frames.py`) over every final
sentence of Test 1's judging (`0dd8fe79`, both arms) and of the evaluation sample's HS rev. 4
judging (`33814b65`), against the judge's verdicts. **Bar:** false holds — sentences the judge
marked `ok` that the check holds — at most 2% of the `ok` sentences.

The check reads the records a v9 run's `detail` would give. These runs are v7/v8's, so each record is
rebuilt as v9 would serve it, from the run's own records and the board — never from the judge or the
reference's verdicts:

- a `material` proposition's line (an `x` handle): its start FEN and moves from the handle line's
  address, the ledger's `standing` (start, after each ply) computed from the board
  (`calliope.agent.lines.standing_white`), as v9's ledger computes it, and each ply's `source` the
  origin restored from the run's records as of the submission (`tools/rx/evidence.Run`);
- a cited judgement: its grade and label from the run's own `ply` call answer for that ply (the
  digest the agent read), when the judgement is that ply's subject; otherwise no record (F3 then does
  not apply);
- an `s` handle: the analysis's (`search` index) unless its `source.kind` is `search`.

Run in WSL from the repository's root:

    python docs/design/rx-evidence/af/replay_frames.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import chess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from calliope.agent.lines import standing_white  # noqa: E402
from tools.rx import frames  # noqa: E402
from tools.rx.evidence import Run  # noqa: E402

RUNS = Path.home() / ".local/share/calliope/rx/runs"
JUDGINGS = {
    "test1": REPO / "docs/design/rx-evidence/lt/test/judging-0dd8fe79",
    "evaluation": REPO / "docs/design/rx-evidence/hs2/judging-33814b65",
    "test1_judge_v2": REPO / "docs/design/rx-evidence/af/judging-b2e612ac",  # step 2's (§11)
}


def records_of(run_dir: Path) -> tuple[dict, dict, dict]:
    rows = [json.loads(x) for x in (run_dir / "tools.jsonl").open(encoding="utf-8")]
    handles = {r["ref"]: r for r in rows if r.get("type") == "handle"}
    calls = {r["call_id"]: r for r in rows if r.get("type") == "call"}
    by_seq = {r["seq"]: r for r in rows}
    return handles, calls, by_seq


def _answer(call: dict | None) -> dict | None:
    try:
        body = json.loads(call["answer"]) if isinstance(call.get("answer"), str) else call["answer"]
        if isinstance(body, dict) and "content" in body:
            body = json.loads(body["content"][0]["text"])
        return body if isinstance(body, dict) else None
    except (ValueError, KeyError, TypeError, IndexError):
        return None


def line_record(handle: dict, origins: list[str] | None) -> tuple[str, dict] | None:
    """The line as v9 would serve it: its standing from the board, each ply's source the origin
    restored from the run's records as of the submission (`tools/rx/evidence.Run`, PR #163 F2)."""

    address = handle.get("address") or {}
    path, moves = address.get("from"), address.get("moves")
    if not isinstance(path, list) or not isinstance(moves, list):
        return None
    board = chess.Board()
    for uci in path:
        board.push_uci(uci)
    start = standing_white(board.fen())
    plies = []
    for i, uci in enumerate(moves):
        board.push_uci(uci)
        source = origins[i] if origins and i < len(origins) else "unknown"
        plies.append({"standing_white": standing_white(board.fen()), "source": source})
    return "explored_line", {"ledger": {"standing": {"start": {"white_minus_black": start}},
                                        "plies": plies}}  # fmt: skip


def judgement_record(handle: dict, calls: dict) -> tuple[str, dict] | None:
    address = handle.get("address") or {}
    if address.get("judgement") != 0:
        return None
    body = _answer(calls.get(handle.get("call_id")))
    if not body or "grade" not in body:
        return None
    return "judgement", {"grade": body.get("grade"), "label": body.get("label"),
                         "move": {"san": body.get("san") or body.get("move")}}  # fmt: skip


def records_for(arguments: dict, handles: dict, calls: dict, run: Run, before: int) -> dict:
    out = {}
    for ref in frames.refs_needed(arguments):
        handle = handles.get(ref)
        if handle is None:
            continue
        kind = handle.get("kind")
        if kind == "explored_line":
            found = line_record(handle, run.plies_origin(ref, before))
        elif kind == "judgement":
            found = judgement_record(handle, calls)
        elif kind == "search_line":
            item = {} if (handle.get("source") or {}).get("kind") == "search" else {"search": 0}
            found = ("search_line", item)
        else:
            found = None
        if found is not None:
            out[ref] = found
    return out


def main() -> None:
    report: dict = {}
    for name, judging in JUDGINGS.items():
        key = json.loads((judging / "bundle_key.json").read_text(encoding="utf-8"))["key"]
        verdicts = {}
        for part in sorted(p for p in judging.iterdir() if p.is_dir()):
            for item in json.loads((part / "judging.json").read_text(encoding="utf-8"))["items"]:
                verdicts[item["key"]] = {s["n"]: s["verdict"] for s in item["sentences"]}
        counts: Counter = Counter()
        held_rows, uncheckable_rows = [], []
        cache: dict = {}
        for k, info in key.items():
            run = info["run_id"]
            if run not in cache:
                cache[run] = (*records_of(RUNS / run), Run(RUNS / run))
            handles, calls, by_seq, origins = cache[run]
            submission = by_seq[info["seq"]]
            subject = next(s for s in submission["subjects"] if s.get("game_ply") == info["ply"])
            arguments = {"items": [subject.get("submitted") or {}]}
            out = frames.check(arguments, records_for(arguments, handles, calls, origins,
                                                      info["seq"]))  # fmt: skip
            judged = verdicts.get(k, {})
            arm = info["arm"]
            counts[(arm, "sentences")] += out["sentences"]
            counts[(arm, "ok")] += sum(v == "ok" for v in judged.values())
            counts[(arm, "wrong")] += sum(v == "wrong" for v in judged.values())
            counts[(arm, "search_numbers")] += out["search_numbers"]
            counts[(arm, "ambiguous")] += len(out["ambiguous"])  # A9
            counts[(arm, "ambiguous_judged_wrong")] += sum(
                judged.get(a["sentence"]) == "wrong" for a in out["ambiguous"])
            rules: dict[int, list[dict]] = {}
            for h in out["held"]:  # one sentence may be held by several rules
                rules.setdefault(h["sentence"], []).append(h)
            for n, hs in rules.items():
                verdict = judged.get(n)
                counts[(arm, f"held_{verdict}")] += 1  # a sentence counted once
                text = (subject["submitted"]["sentences"][n - 1] or {}).get("text")
                held_rows.append({"moment": f"{info['game']}-{info['ply']}", "arm": arm,
                                  "run": run[-6:], "n": n, "rules": [h["rule"] for h in hs],
                                  "verdict": verdict, "text": text,
                                  "replies": [h["reply"] for h in hs]})  # fmt: skip
            for u in out["uncheckable"]:
                counts[(arm, f"uncheckable_{u['rule']}")] += 1
                uncheckable_rows.append({"moment": f"{info['game']}-{info['ply']}", "arm": arm,
                                         "n": u["sentence"], "rule": u["rule"], "why": u["why"]})  # fmt: skip
        by_arm = {}
        for arm in sorted({a for a, _ in counts}):
            row = {field: counts[(arm, field)] for a, field in counts if a == arm}
            ok = row.get("ok", 0)
            row["false_hold_rate_of_ok"] = round(row.get("held_ok", 0) / ok, 4) if ok else None
            by_arm[arm] = row
        report[name] = {"by_arm": by_arm, "held": held_rows, "uncheckable": uncheckable_rows}
        print(name, json.dumps(by_arm, ensure_ascii=False))
    out = HERE / "af-replay-frames.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
