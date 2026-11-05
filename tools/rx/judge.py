"""The blind judging (RX2-D §5): the bundle in parts, the judging directories, the key kept apart, the
audit of a judge's tool calls, and the join of the judgings with the key.

A judging directory holds only the part's items, the references they name, `judge_v1.md` and its schema.
`bundle_key.json` and the shuffle's seed stay in the RX data directory, never beside the bundle.
"""

from __future__ import annotations

import json
import random
import re
import secrets
import shutil
from pathlib import Path

from .check import finals, lines
from .manifest import RX_DATA
from .reference import REFERENCES
from .run import REPO

PROMPTS = REPO / "tools" / "rx" / "prompts"
JUDGING_ROOT = REPO.parent / "rx-judging"  # outside the repository (RX2-D §5.1)
KEYS = RX_DATA / "judging"
PART_MOMENTS = 6  # RX2-D §5.3


def bundle(runs: list[Path], judging_id: str | None = None, seed: int | None = None,
           root: Path = JUDGING_ROOT, keys: Path = KEYS) -> dict:  # fmt: skip
    """Every run's final commentaries at its fixed moments, in parts of at most six moments holding
    every arm's commentaries of those moments, shuffled within the part."""

    judging_id = judging_id or secrets.token_hex(4)
    seed = seed if seed is not None else secrets.randbits(32)
    rng = random.Random(seed)
    items = []  # (moment, key info, sentences)
    for run in runs:
        start = lines(run / "agent.jsonl")[0]
        for ply, final in finals(run, start["moments"]).items():
            if final is None or not final.get("sentences"):
                continue
            moment = f"{start['set']}/{start['game']}-{ply}"
            items.append((moment, {"run_id": run.name, "arm": start["arm"], "set": start["set"],
                                   "game": start["game"], "ply": ply, "seq": final["seq"]},
                          final["sentences"]))  # fmt: skip
    moments = sorted({m for m, _, _ in items})
    by_set: dict[str, list[str]] = {}
    for m in moments:
        by_set.setdefault(m.split("/")[0], []).append(m)
    parts = []
    for set_name in sorted(by_set):  # Train and Validation never share a part
        ms = by_set[set_name]
        for i in range(0, len(ms), PART_MOMENTS):
            parts.append(ms[i : i + PART_MOMENTS])
    key: dict[str, dict] = {}
    written = []
    for index, part_moments in enumerate(parts, start=1):
        part_dir = root / judging_id / f"part{index:02d}"
        part_dir.mkdir(parents=True, exist_ok=False)
        chosen = [x for x in items if x[0] in part_moments]
        rng.shuffle(chosen)
        out = []
        for moment, info, sentences in chosen:
            k = secrets.token_hex(4)
            key[k] = info | {"part": index}
            out.append({"key": k, "moment": moment,
                        "sentences": [{"n": n, "text": s.get("text"), "class": s.get("class")}
                                      for n, s in enumerate(sentences, start=1)]})  # fmt: skip
        (part_dir / "bundle.json").write_text(json.dumps({"items": out}, ensure_ascii=False, indent=1),
                                              encoding="utf-8")  # fmt: skip
        refs = part_dir / "references"
        refs.mkdir()
        for moment in part_moments:
            src = REFERENCES / f"{moment}.json"
            shutil.copy(src, refs / src.name)
        for name in ("judge_v1.md", "judge_v1.schema.json"):
            shutil.copy(PROMPTS / name, part_dir / name)
        written.append(part_dir)
    keys_dir = keys / judging_id
    keys_dir.mkdir(parents=True, exist_ok=False)
    (keys_dir / "bundle_key.json").write_text(json.dumps({"seed": seed, "key": key}, indent=1),
                                              encoding="utf-8")  # fmt: skip
    return {"judging": judging_id, "parts": [str(p) for p in written], "items": len(key)}


# -- the audit (RX2-D §5.1) ---------------------------------------------------------------------

WALKS = re.compile(
    r"\b(find|ls\s+-[a-zA-Z]*R|tree|du|locate|os\.walk|rglob|glob\(|listdir|scandir)\b"
)
FORBIDDEN = ("bundle_key", ".local/share/calliope", "\\\\wsl", "/home/", "Calliope", "rx/runs")
PATH_KEYS = ("file_path", "path", "notebook_path", "cwd")


def audit(tool_calls: list[dict], part_dir: Path) -> list[str]:
    """What a judge's recorded tool calls show outside its directory. `tool_calls` are
    `{"tool", "input"}` as the transcript records them. An empty list passes; this checks what the
    transcript can show, not every read a command makes (RX2-D §5.1, re-review N5)."""

    inside = str(part_dir.resolve()).replace("\\", "/").lower()
    problems = []
    for n, call in enumerate(tool_calls, start=1):
        tool, given = call.get("tool"), call.get("input") or {}
        text = json.dumps(given, ensure_ascii=False)
        for name in PATH_KEYS:
            value = given.get(name)
            if isinstance(value, str):
                resolved = str(Path(value).resolve()).replace("\\", "/").lower()
                if not resolved.startswith(inside):
                    problems.append(f"call {n} ({tool}): {name} {value} is outside the directory")
        for marker in FORBIDDEN:
            if marker.lower() in text.lower():
                problems.append(f"call {n} ({tool}): names {marker!r}")
        if tool in ("Bash", "PowerShell", "Glob", "Grep") and WALKS.search(text):
            problems.append(f"call {n} ({tool}): lists or walks directories")
    return problems


def join(judging_id: str, judgings: dict[int, dict], keys: Path = KEYS) -> list[dict]:
    """The audited parts' judgings with the key: one row a commentary."""

    key = json.loads((keys / judging_id / "bundle_key.json").read_text(encoding="utf-8"))["key"]
    rows = []
    for part, doc in judgings.items():
        for item in doc["items"]:
            info = key[item["key"]]
            if info["part"] != part:
                raise ValueError(f"key {item['key']} is not of part {part}")
            rows.append(info | {"judged": item})
    return rows
