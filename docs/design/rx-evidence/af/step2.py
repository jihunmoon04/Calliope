"""AF-D §7.2 step 2: Test 1's commentaries judged with judge v2 (`b2e612ac`) and the constructed
bundle (`a82bb35a-src`), against judge v1's judging of the same commentaries (`0dd8fe79`).

Each judging is read only through `tools.rx.judge.checked_judgings` (its audit passed or the owner's
decision recorded, its schema, every item, sentence and key cause judged once) and joined with its
key. Sentences are matched across judgings by (run, ply, sentence number).

**Bar:** in the bundle as written, none of AF-D §0.1's eleven states a separate search, so each is
`wrong` with kind `source` (or `ok` where the reference holds nothing for it); in the constructed
bundle each is `search_only`; the other wrong sentences of judge v1 (H's four, A's four) still
`wrong`; every change of verdict from judge v1 listed with the judge's reason.

    python docs/design/rx-evidence/af/step2.py
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from tools.rx.judge import KEYS, checked_judgings, join  # noqa: E402

JUDGING_ROOT = REPO.parent / "rx-judging"
V2, SRC = "b2e612ac", "a82bb35a-src"
V1 = REPO / "docs/design/rx-evidence/lt/test/judging-0dd8fe79"
CASES = [("01M6XYBACASXGP0VKSK8TRH87V", 50, 3), ("01M6XYBACASXGP0VKSK8TRH87V", 50, 7),
         ("01M6XY4JJ4VE6012FG2WY2ZKYK", 50, 3), ("01M6XY4JJ4VE6012FG2WY2ZKYK", 50, 4),
         ("01M6XYNBP6J4TAH42VNW827V6J", 50, 2), ("01M6XXPGB0JSKSDWX3KHFJ3HFV", 38, 3),
         ("01M6XWW4BNQ8QFP3D74AB3NVPP", 38, 5), ("01M6XXSQH0KNJ1ZZ0S467SRK7C", 72, 6),
         ("01M6XXSQH0KNJ1ZZ0S467SRK7C", 72, 8), ("01M6XXB9BY4SSFR98SXDXK6CCH", 72, 4),
         ("01M6XWW4BNQ8QFP3D74AB3NVPP", 38, 6)]  # fmt: skip


def sentences(rows: list[dict]) -> dict[tuple, dict]:
    out = {}
    for row in rows:
        for s in row["judged"]["sentences"]:
            out[(row["run_id"], row["ply"], s["n"])] = s | {"arm": row["arm"],
                                                           "moment": f"{row['game']}-{row['ply']}"}
    return out


def v1_rows() -> list[dict]:
    key = json.loads((V1 / "bundle_key.json").read_text(encoding="utf-8"))["key"]
    rows = []
    for part in sorted(p for p in V1.iterdir() if p.is_dir()):
        for item in json.loads((part / "judging.json").read_text(encoding="utf-8"))["items"]:
            rows.append(key[item["key"]] | {"judged": item})
    return rows


def main() -> None:
    v2 = sentences(join(V2, checked_judgings(V2, JUDGING_ROOT / V2)))
    src = sentences(join(SRC, checked_judgings(SRC, JUDGING_ROOT / SRC)))
    v1 = sentences(v1_rows())
    cases = []
    for case in CASES:
        cases.append({"case": f"{case[0][-6:]} {case[1]} #{case[2]}",
                      "v1": v1[case]["verdict"],
                      "v2": {k: v2[case].get(k) for k in ("verdict", "kind", "why")},
                      "constructed": {k: src[case].get(k) for k in ("verdict", "kind", "why")}})  # fmt: skip
    others = [k for k, s in v1.items() if s["verdict"] == "wrong" and k not in CASES]
    other_rows = [{"case": f"{k[0][-6:]} {k[1]} #{k[2]}", "arm": v1[k]["arm"],
                   "v2": {x: v2[k].get(x) for x in ("verdict", "kind", "why")}} for k in others]  # fmt: skip
    changes = [{"sentence": f"{k[0][-6:]} {k[1]} #{k[2]}", "arm": v1[k]["arm"],
                "v1": v1[k]["verdict"], "v2": v2[k]["verdict"], "kind": v2[k].get("kind"),
                "why": v2[k].get("why")}
               for k in sorted(v1) if k in v2 and v1[k]["verdict"] != v2[k]["verdict"]]  # fmt: skip
    totals = {}
    for name, table in (("judge_v1", v1), ("judge_v2", v2)):
        for arm in ("A", "H"):
            totals[f"{name} {arm}"] = dict(Counter(s["verdict"] for s in table.values()
                                                   if s["arm"] == arm))  # fmt: skip
    kinds = Counter((s["arm"], s.get("kind")) for s in v2.values() if s["verdict"] == "wrong")
    bar = {
        "eleven_as_written_wrong_source_or_ok": sum(
            c["v2"]["verdict"] == "ok" or (c["v2"]["verdict"] == "wrong" and c["v2"]["kind"] == "source")
            for c in cases),
        "eleven_constructed_search_only": sum(c["constructed"]["verdict"] == "search_only"
                                              for c in cases),
        "others_still_wrong": sum(o["v2"]["verdict"] == "wrong" for o in other_rows),
        "others": len(other_rows),
    }  # fmt: skip
    out = {"bar": bar, "cases": cases, "other_wrong": other_rows, "totals": totals,
           "v2_wrong_kinds": {f"{a} {k}": n for (a, k), n in kinds.items()}, "changes": changes}
    (HERE / "af-step2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                        encoding="utf-8")  # fmt: skip
    for judging in (V2, SRC):  # the evidence, as LT kept its judging (no conversation text)
        dest = HERE / f"judging-{judging}"
        for part in sorted((JUDGING_ROOT / judging).glob("part*")):
            (dest / part.name).mkdir(parents=True, exist_ok=True)
            for name in ("bundle.json", "judging.json"):
                shutil.copy(part / name, dest / part.name / name)
        for f in (KEYS / judging).glob("*.json"):
            shutil.copy(f, dest / f.name)
    print(json.dumps({"bar": bar, "totals": totals}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
