"""AF-D §7.2 step 2: the constructed bundle beside Test 1's judge v2 judging.

The seven commentaries that hold AF-D §0.1's eleven "another search" sentences, taken from the
judge v2 bundle, with each of those sentences rewritten **to state its source** ("별도 탐색에서는 …")
— the same numbers, the same citations and evidence; every other sentence as written. Judged by its
own fresh judge session with judge_v2: each of the eleven should be `search_only` (the reference
holds another value), where the bundle as written should judge them `wrong` with kind `source`.

Its key stays in the RX data directory (`judging/<id>-src`), never beside the part.

    python docs/design/rx-evidence/af/constructed_bundle.py <judging id of the judge v2 bundle>
"""

from __future__ import annotations

import json
import random
import secrets
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RX = Path.home() / ".local/share/calliope/rx"
JUDGING_ROOT = REPO.parent / "rx-judging"
# (run, ply, sentence) → (the words replaced, the words that state the source)
REWRITES = {
    ("01M6XYBACASXGP0VKSK8TRH87V", 50, 3): ("둔 수 뒤 엔진 라인 9수째에서",
                                            "둔 수 뒤 별도 탐색으로 이어 둔 수순의 9수째에서"),
    ("01M6XYBACASXGP0VKSK8TRH87V", 50, 7): ("엔진 라인 9수째 물질은",
                                            "별도 탐색으로 이어 둔 수순의 9수째 물질은"),
    ("01M6XY4JJ4VE6012FG2WY2ZKYK", 50, 3): ("둔 수 뒤 엔진 라인에서",
                                            "둔 수 뒤 별도 탐색으로 이어 둔 수순에서"),
    ("01M6XY4JJ4VE6012FG2WY2ZKYK", 50, 4): ("흑은 룩과", "별도 탐색으로 이어 둔 그 수순에서 흑은 룩과"),
    ("01M6XYNBP6J4TAH42VNW827V6J", 50, 2): ("백 룩이 되잡아 라인 끝에서",
                                            "별도 탐색으로 이어 둔 수순에서는 백 룩이 되잡아 라인 끝에서"),
    ("01M6XXPGB0JSKSDWX3KHFJ3HFV", 38, 3): ("이 라인은 6수 뒤", "별도 탐색으로 이어 둔 이 수순은 6수 뒤"),
    ("01M6XWW4BNQ8QFP3D74AB3NVPP", 38, 5): ("이어진 Bxh2로", "별도 탐색으로 이어 둔 수순에서 이어진 Bxh2로"),
    ("01M6XWW4BNQ8QFP3D74AB3NVPP", 38, 6): ("둔 수 뒤 엔진 평가는", "깊이 12의 별도 탐색에서 둔 수 뒤 평가는"),
    ("01M6XXSQH0KNJ1ZZ0S467SRK7C", 72, 6): ("이 라인의 평가는", "별도 탐색에서 이 라인의 평가는"),
    ("01M6XXSQH0KNJ1ZZ0S467SRK7C", 72, 8): ("36...Rb2 뒤 평가는", "별도 탐색에서 36...Rb2 뒤 평가는"),
    ("01M6XXB9BY4SSFR98SXDXK6CCH", 72, 4): ("둔 수 뒤 엔진 평가도", "별도 탐색에서 둔 수 뒤 평가도"),
}


def main(source_id: str) -> None:
    key = json.loads((RX / "judging" / source_id / "bundle_key.json").read_text())["key"]
    wanted = {(r, p) for r, p, _ in REWRITES}
    items, moments = [], set()
    src_root = JUDGING_ROOT / source_id
    for part in sorted(src_root.glob("part*")):
        for item in json.loads((part / "bundle.json").read_text(encoding="utf-8"))["items"]:
            info = key[item["key"]]
            if (info["run_id"], info["ply"]) not in wanted:
                continue
            item = json.loads(json.dumps(item))
            for s in item["sentences"]:
                rewrite = REWRITES.get((info["run_id"], info["ply"], s["n"]))
                if rewrite:
                    old, new = rewrite
                    assert old in s["text"], (info["run_id"], info["ply"], s["n"], s["text"])
                    s["text"] = s["text"].replace(old, new, 1)
            items.append((item, info, part))
            moments.add(item["moment"])
    assert len(items) == 7, len(items)
    judging_id = f"{secrets.token_hex(4)}-src"
    part_dir = JUDGING_ROOT / judging_id / "part01"
    (part_dir / "references").mkdir(parents=True)
    random.Random(secrets.randbits(32)).shuffle(items)
    out, new_key = [], {}
    for item, info, part in items:
        k = secrets.token_hex(4)
        new_key[k] = info | {"part": 1, "constructed_from": item["key"]}
        out.append(dict(item, key=k))
        ref = part / "references" / f"{item['moment'].split('/')[1]}.json"
        shutil.copy(ref, part_dir / "references" / ref.name)
    (part_dir / "bundle.json").write_text(json.dumps({"items": out}, ensure_ascii=False, indent=1),
                                          encoding="utf-8")  # fmt: skip
    for name in ("judge_v2.md", "judge_v2.schema.json"):
        shutil.copy(REPO / "tools" / "rx" / "prompts" / name, part_dir / name)
    keys = RX / "judging" / judging_id
    keys.mkdir(parents=True)
    runs = sorted({info["run_id"] for _, info, _ in items})
    (keys / "bundle_key.json").write_text(json.dumps({"runs": runs, "judge": "judge_v2",
                                                      "constructed_from": source_id,
                                                      "key": new_key}, indent=1))  # fmt: skip
    print(json.dumps({"judging": judging_id, "part": str(part_dir), "items": len(out),
                      "moments": sorted(moments)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
