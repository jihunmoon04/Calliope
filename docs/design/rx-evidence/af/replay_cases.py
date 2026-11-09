"""AF-D §7.2 step 1(a): the eleven cases of AF-D §0.1's first two rows, put to v9.

For each wrong sentence whose cited line or score came from a session search (H's, Test 1, judging
`0dd8fe79`), the call that served the cited handle is read from the run's records (the handle's
`call_id`), and the same call — tool, position, moves and options — is made on v9, in a session on a
copy of Test 1's sealed base. The answer is set beside the reference's lines. **Bar:** each gives the
analysis record's line and score (`analysis_score`, the plies' `source: analysis`), or `departs_at`
where the agent's own moves left the analysis.

Run in WSL from the repository's root, with `CALLIOPE_STOCKFISH_PATH` set:

    python docs/design/rx-evidence/af/replay_cases.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lt"))

from replay_common import REPO, Cases, arguments, session_on  # noqa: E402

RUNS = Path.home() / ".local/share/calliope/rx/runs"
REFERENCES = REPO / "tools/rx/references_v1/test"
# AF-D §0.1: (game, ply, run, sentence, the cited handle)
CASES = [
    ("186491823816", 50, "01M6XYBACASXGP0VKSK8TRH87V", 3, "x23"),
    ("186491823816", 50, "01M6XYBACASXGP0VKSK8TRH87V", 7, "x23"),
    ("186491823816", 50, "01M6XY4JJ4VE6012FG2WY2ZKYK", 3, "x30"),
    ("186491823816", 50, "01M6XY4JJ4VE6012FG2WY2ZKYK", 4, "x30"),
    ("186491823816", 50, "01M6XYNBP6J4TAH42VNW827V6J", 2, "x28"),
    ("186437361608", 38, "01M6XXPGB0JSKSDWX3KHFJ3HFV", 3, "x33"),
    ("186203030416", 38, "01M6XWW4BNQ8QFP3D74AB3NVPP", 5, "x39"),
    ("186437361608", 72, "01M6XXSQH0KNJ1ZZ0S467SRK7C", 6, "s121"),
    ("186437361608", 72, "01M6XXSQH0KNJ1ZZ0S467SRK7C", 8, "s138"),
    ("186437361608", 72, "01M6XXB9BY4SSFR98SXDXK6CCH", 4, "s126"),
    ("186203030416", 38, "01M6XWW4BNQ8QFP3D74AB3NVPP", 6, "s61"),
]


def serving_call(run: str, prefix: str) -> dict:
    records = [json.loads(x) for x in (RUNS / run / "tools.jsonl").open(encoding="utf-8")]
    handle = next(r for r in records if r.get("type") == "handle"
                  and r["ref"].split(".")[0] == prefix)  # fmt: skip
    call = next(r for r in records if r.get("type") == "call"
                and r.get("call_id") == handle.get("call_id"))  # fmt: skip
    return {"tool": call["tool"], "arguments": call["arguments"], "handle_kind": handle["kind"]}


def reference(game: str, ply: int) -> dict:
    digest = json.loads((REFERENCES / f"{game}-{ply}.json").read_text(encoding="utf-8"))["digest"]
    out = {}
    for name, line in (digest.get("lines") or {}).items():
        if isinstance(line, dict):
            out[name] = {"move": line.get("move"), "score": line.get("score_text"),
                         "pv": line.get("pv"), "ref_kind": "analysis"}  # fmt: skip
    for other in digest.get("others") or []:
        if isinstance(other, dict) and other.get("move"):
            out[f"other {other['move']}"] = {"score": other.get("score_text"), "pv": other.get("pv")}
    return out


def summary(tool: str, answer: dict) -> dict:
    if tool == "explore":
        book = answer.get("ledger") or {}
        return {
            "plies": [f"{p['san']} [{p['source']}]" for p in book.get("plies") or []],
            "analysis_score": book.get("analysis_score"),
            "end_score": book.get("end_score"),
            "departs_at": answer.get("departs_at"),
            "analysis_ends_at": answer.get("analysis_ends_at"),
            "standing": book.get("standing"),
        }
    ranking = answer.get("ranking") or {}
    return {
        "ranking_source": ranking.get("source"),
        "ranking": [{k: e.get(k) for k in ("move", "white_view", "source", "at")}
                    | {"analysis": (e.get("analysis_score") or {}).get("white_view")}
                    for e in ranking.get("moves") or []],  # fmt: skip
        "lines": {n: {"analysis_score": (ln.get("analysis_score") or {}).get("white_view"),
                      "end": ln.get("end"), "moves": ln.get("moves")}
                  for n, ln in (answer.get("lines") or {}).items() if isinstance(ln, dict)},
    }


def verdict(tool: str, s: dict) -> str:
    """The bar, read off the answer: the analysis's line and score, or `departs_at`."""

    if tool == "explore":
        if s["analysis_score"]:
            return "analysis"
        return "departs" if s["departs_at"] else "search only"
    return "analysis" if s["ranking_source"] == "analysis" or any(
        e["analysis"] for e in s["ranking"]) else "search only"  # fmt: skip


def main() -> None:
    args = arguments(__doc__.splitlines()[0])
    session = session_on(args.rx_data / "base" / "test" / "data")
    ids: dict[str, str] = {}
    cases = Cases()
    try:
        for game, ply, run, n, prefix in CASES:
            def one(game=game, ply=ply, run=run, prefix=prefix):
                if game not in ids:
                    pgn = (args.rx_data / "sets" / f"{game}.pgn").read_text(encoding="utf-8")
                    ids[game] = session.open_game(pgn=pgn)["game"]
                g = ids[game]
                session.ply(g, ply)  # the base's record (a cache hit)
                call = serving_call(run, prefix)
                given = dict(call["arguments"], game=g)
                if call["tool"] == "explore":
                    answer = session.explore(g, given["position"], given.get("moves"),
                                             given.get("search", False), "brief",
                                             given.get("continue_with"), given.get("length", 8))  # fmt: skip
                else:
                    answer = session.compare_lines(g, given["ply"], given.get("length", 16),
                                                   given.get("candidates"))  # fmt: skip
                s = summary(call["tool"], answer)
                return {"call": call, "v9": s, "verdict": verdict(call["tool"], s),
                        "reference": reference(game, ply)}  # fmt: skip

            cases(f"{game}-{ply} {run[-6:]} #{n} {prefix}", one)
    finally:
        session.close()
    cases.save((HERE if args.out == HERE.parent / "lt" else args.out) / "af-replay-cases.json")


if __name__ == "__main__":
    main()
