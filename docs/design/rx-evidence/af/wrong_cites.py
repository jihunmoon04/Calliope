"""AF-D §0.1 (review N2): for every sentence the judge marked `wrong` on Test 1 (judging
`0dd8fe79`), the submitted sentence, the propositions it cites as the server verified them, the
`explore` or `compare_lines` call behind each cited line (its arguments and the ledger's plies with
their sources), and the analysis record's lines for the moment from its reference.

Run in WSL from the repository root, where the runs are (`~/.local/share/calliope/rx/runs`):

    python docs/design/rx-evidence/af/wrong_cites.py > docs/design/rx-evidence/af/test1-wrong-cites.json
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
RUNS = Path.home() / ".local/share/calliope/rx/runs"
JUDGING = REPO / "docs/design/rx-evidence/lt/test/judging-0dd8fe79"
REFERENCES = REPO / "tools/rx/references_v1/test"


def wrong_sentences() -> list[dict]:
    key = json.loads((JUDGING / "bundle_key.json").read_text(encoding="utf-8"))["key"]
    found = []
    for part in sorted(p for p in JUDGING.iterdir() if p.is_dir()):
        judging = json.loads((part / "judging.json").read_text(encoding="utf-8"))
        for item in judging["items"]:
            where = key[item["key"]]
            for sentence in item["sentences"]:
                if sentence["verdict"] == "wrong":
                    found.append({"arm": where["arm"], "run": where["run_id"], "game": where["game"],
                                  "ply": where["ply"], "seq": where["seq"], "n": sentence["n"],
                                  "kind": sentence.get("kind"), "why": sentence.get("why")})
    return found


def handle_calls(records: list[dict]) -> dict[str, dict]:
    """Each `x`/`s` handle prefix → the explore or compare_lines call whose answer served it."""

    calls = {}
    for r in records:
        if r.get("type") != "call" or r.get("tool") not in ("explore", "compare_lines"):
            continue
        answer = r.get("answer")
        text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        try:
            body = json.loads(text)
            if isinstance(body, dict) and "content" in body:
                body = json.loads(body["content"][0]["text"])
        except (ValueError, KeyError, IndexError, TypeError):
            body = None
        entry = {"call_seq": r["seq"], "tool": r["tool"], "arguments": r.get("arguments")}
        if isinstance(body, dict) and isinstance(body.get("ledger"), dict):
            ledger = body["ledger"]
            entry["plies"] = [f"{p['san']} [{p.get('source')}]" for p in ledger.get("plies", [])]
            entry["net"] = ledger.get("net")
            entry["end_score"] = ledger.get("end_score")
        for token in set(_handles(text)):
            calls.setdefault(token, entry)
    return calls


def _handles(text: str):
    import re

    return re.findall(r"\b([xs]\d+)\.[0-9a-f]{24}\b", text)


def reference_lines(game: str, ply: int) -> dict:
    path = REFERENCES / f"{game}-{ply}.json"
    if not path.exists():
        return {}
    digest = json.loads(path.read_text(encoding="utf-8"))["digest"]
    lines = {k: {f: v.get(f) for f in ("move", "score_text", "depth", "pv")}
             for k, v in (digest.get("lines") or {}).items() if isinstance(v, dict)}
    return {"grade": digest.get("grade"), "evaluation": digest.get("evaluation"), "lines": lines}


def main() -> None:
    out = []
    cache: dict[str, list[dict]] = {}
    for w in wrong_sentences():
        if w["run"] not in cache:
            path = RUNS / w["run"] / "tools.jsonl"
            cache[w["run"]] = [json.loads(line) for line in path.open(encoding="utf-8")]
        records = cache[w["run"]]
        submission = next(r for r in records if r.get("seq") == w["seq"])
        calls = handle_calls(records)
        case = dict(w)
        for subject in submission.get("subjects") or []:
            if subject.get("game_ply") != w["ply"]:
                continue
            submitted = subject.get("submitted") or {}
            sentence = (submitted.get("sentences") or [])[w["n"] - 1]
            verified = {p.get("id"): p for p in subject.get("verified") or []}
            case["text"] = sentence.get("text")
            case["cites"] = []
            for cite in sentence.get("cites") or []:
                prop = verified.get(cite)
                ref = (prop or {}).get("line") or (prop or {}).get("judgement") or cite
                prefix = ref.split(".")[0] if isinstance(ref, str) else None
                case["cites"].append({"cite": cite, "verified": prop,
                                      "served_by": calls.get(prefix)})
        case["reference"] = reference_lines(w["game"], w["ply"])
        out.append(case)
    print(json.dumps({"judging": "0dd8fe79", "cases": out}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
