"""AF-D §0.1 (review N2; rev. 3 re-review N1): for every sentence the judge marked `wrong` on Test 1
(judging `0dd8fe79`), the submitted sentence, each citation **resolved as the server resolved it**
(an explicit proposition by its id; a cited handle expanded into the `verified` entries whose
`by_handle` is that handle), and, for every handle those propositions rest on, its **origin**
restored from the run's records as AF-D §5.1 specifies for v8 runs:

- the handle's `handle` line gives its kind, its `source` and the `call_id` of the call that served
  it; that call's answer gives the line's plies and where each came from;
- an `s` handle whose `source.kind` is `search` is a session search; one served with a ply record is
  the analysis;
- an `x` handle served by `explore` takes its plies' sources from the answer's `ledger.plies[].source`
  (`agent`: typed by the agent; `engine`: appended from the end search's PV, a session search);
- an `x` handle served by `compare_lines` takes them from the line's `source` (`{kind: n}`: the first
  n plies, from the analysis PV for `played`/`best`, typed for a candidate) and `extended` (the next
  plies, from the end search's PV).

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
LINE_FIELDS = ("line", "judgement", "claim")  # the fields of a proposition that name a handle


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


def _answer(call: dict):
    answer = call.get("answer")
    try:
        body = json.loads(answer) if isinstance(answer, str) else answer
        if isinstance(body, dict) and "content" in body:
            body = json.loads(body["content"][0]["text"])
        return body if isinstance(body, dict) else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


class Run:
    def __init__(self, run: str):
        path = RUNS / run / "tools.jsonl"
        self.records = [json.loads(line) for line in path.open(encoding="utf-8")]
        self.handles = {r["ref"]: r for r in self.records if r.get("type") == "handle"}
        self.calls = {r["call_id"]: r for r in self.records if r.get("type") == "call"}

    def origin(self, ref: str) -> dict:
        """Where a handle's record came from (AF-D §5.1's restoration for v8 runs)."""

        handle = self.handles.get(ref)
        if handle is None:
            return {"ref": ref, "origin": "unknown", "why": "no handle line"}
        source = handle.get("source") or {}
        call = self.calls.get(handle.get("call_id"))
        out = {"ref": ref, "kind": handle.get("kind"), "source": source.get("kind"),
               "call_id": handle.get("call_id"), "tool": (call or {}).get("tool")}
        if handle.get("kind") == "search_line":
            out["origin"] = "search" if source.get("kind") == "search" else "analysis"
            return out
        if handle.get("kind") != "explored_line" or call is None:
            out["origin"] = "analysis" if call is None or call.get("tool") == "ply" else "other"
            return out
        body = _answer(call) or {}
        out["arguments"] = call.get("arguments")
        if call.get("tool") == "explore":
            plies = (body.get("ledger") or {}).get("plies") or []
            out["plies"] = [f"{p.get('san')} [{_explore_origin(p.get('source'))}]" for p in plies]
        elif call.get("tool") == "compare_lines":
            for name, line in (body.get("lines") or {}).items():
                if not isinstance(line, dict) or line.get("ref") != ref and (
                        (line.get("searched") or {}).get("ref") != ref):  # fmt: skip
                    continue
                (kind, n), = (line.get("source") or {"?": 0}).items()
                first = "analysis" if kind in ("played", "best", "engine") else "agent"
                origins = [first] * n + ["search"] * int(line.get("extended") or 0)
                out["line"] = name
                out["plies"] = [f"{san} [{o}]" for san, o in zip(line.get("moves") or [], origins)]
                out["end"] = line.get("end")
        sources = {p.rsplit("[", 1)[1].rstrip("]") for p in out.get("plies", [])}
        out["origin"] = ("search" if "search" in sources else
                         "agent" if "agent" in sources else
                         "analysis" if sources == {"analysis"} else "unknown")  # fmt: skip
        return out


def _explore_origin(source: str | None) -> str:
    return {"agent": "agent", "engine": "search"}.get(source or "", source or "unknown")


def resolve(cite: str, verified: list[dict]) -> list[dict]:
    """An explicit proposition by its id, or a cited handle's expansion (`by_handle`)."""

    explicit = [p for p in verified if p.get("id") == cite]
    return explicit or [p for p in verified if p.get("by_handle") == cite]


def reference_lines(game: str, ply: int) -> dict:
    path = REFERENCES / f"{game}-{ply}.json"
    if not path.exists():
        return {}
    digest = json.loads(path.read_text(encoding="utf-8"))["digest"]
    lines = {k: {f: v.get(f) for f in ("move", "score_text", "depth", "pv")}
             for k, v in (digest.get("lines") or {}).items() if isinstance(v, dict)}
    return {"grade": digest.get("grade"), "evaluation": digest.get("evaluation"), "lines": lines}


def main() -> None:
    out, runs, unresolved = [], {}, 0
    for w in wrong_sentences():
        run = runs.setdefault(w["run"], Run(w["run"]))
        submission = next(r for r in run.records if r.get("seq") == w["seq"])
        case = dict(w)
        for subject in submission.get("subjects") or []:
            if subject.get("game_ply") != w["ply"]:
                continue
            sentence = ((subject.get("submitted") or {}).get("sentences") or [])[w["n"] - 1]
            verified = subject.get("verified") or []
            case["text"] = sentence.get("text")
            case["cites"] = []
            for cite in sentence.get("cites") or []:
                props = resolve(cite, verified)
                unresolved += not props
                refs = sorted({p[f] for p in props for f in LINE_FIELDS if isinstance(p.get(f), str)})
                handles = {r: run.origin(r) for r in refs}
                for p in props:  # a material count's origin is its own segment's plies
                    if p.get("kind") == "material" and p.get("line") in handles:
                        plies = handles[p["line"]].get("plies") or []
                        segment = plies[int(p.get("from", 0)):int(p.get("to", 0))]
                        kinds = {s.rsplit("[", 1)[1].rstrip("]") for s in segment}
                        p["segment_origin"] = ("search" if "search" in kinds else
                                               "agent" if "agent" in kinds else
                                               "analysis" if kinds == {"analysis"} else "unknown")
                case["cites"].append({"cite": cite, "propositions": props,
                                      "handles": list(handles.values())})
        case["reference"] = reference_lines(w["game"], w["ply"])
        out.append(case)
    print(json.dumps({"judging": "0dd8fe79", "unresolved_cites": unresolved, "cases": out},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
