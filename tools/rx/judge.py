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
PART_MOMENTS = 6  # RX2-D §5.3, the default; RX4-D §4: a setting (4 for three arms)
PART_COMMENTARIES = 36  # RX4-D §4: what one judge handles (RX2's parts held 36)


def pack(items: list, moments_per_part: int, max_commentaries: int) -> list[list]:
    """The parts (RX4a review B2): whole groups, a group being one moment's commentaries of one
    candidate (one moment's commentaries when no run has a candidate), so a candidate's B and D at a
    moment are always judged together. A part holds at most `moments_per_part` moments and at most
    `max_commentaries` commentaries; Train and Validation never share a part."""

    groups: dict[tuple, list] = {}
    for item in items:
        groups.setdefault((item[0], item[1].get("candidate_id") or ""), []).append(item)
    parts, current, moments = [], [], set()
    for set_name in sorted({m.split("/")[0] for m, _ in groups}):
        for (moment, _), group in sorted(
            (k, v) for k, v in groups.items() if k[0].split("/")[0] == set_name
        ):
            if len(group) > max_commentaries:
                raise ValueError(f"{moment}: {len(group)} commentaries of one candidate, more than "
                                 f"a part holds ({max_commentaries})")  # fmt: skip
            new_moment = moment not in moments
            if current and (len(current) + len(group) > max_commentaries
                            or (new_moment and len(moments) >= moments_per_part)):  # fmt: skip
                parts.append(current)
                current, moments = [], set()
            current += group
            moments.add(moment)
        if current:
            parts.append(current)
            current, moments = [], set()
    return parts


def bundle(runs: list[Path], judging_id: str | None = None, seed: int | None = None,
           root: Path = JUDGING_ROOT, keys: Path = KEYS,
           moments_per_part: int = PART_MOMENTS,
           max_commentaries: int = PART_COMMENTARIES) -> dict:  # fmt: skip
    """Every run's final commentaries at its fixed moments, packed into parts (`pack`), shuffled
    within the part."""

    if moments_per_part < 1 or max_commentaries < 1:
        raise ValueError("a part holds at least one moment and one commentary")

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
                                   "candidate_id": start.get("candidate_id"),
                                   "lesson_set_digest": start.get("lesson_set_digest"),
                                   "game": start["game"], "ply": ply, "seq": final["seq"]},
                          final["sentences"]))  # fmt: skip
    parts = pack(items, moments_per_part, max_commentaries)
    key: dict[str, dict] = {}
    written = []
    for index, chosen in enumerate(parts, start=1):
        part_dir = root / judging_id / f"part{index:02d}"
        part_dir.mkdir(parents=True, exist_ok=False)
        part_moments = sorted({x[0] for x in chosen})
        chosen = list(chosen)
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


# -- the audit (RX2-D §5.1; RX2 implementation §9 Q2: outside the directory) ----------------------

# a shell `find` (not Python's `str.find`), recursive listings, walks, globbing
WALKS = re.compile(
    r"(?<![.\w])find\s|\bls\s+-[a-zA-Z]*R|\btree\b|\bdu\b|\blocate\b|os\.walk|rglob|glob\(|"
    r"listdir|scandir|Get-ChildItem"
)
# what makes a listing reach outside: a parent, home, another drive or mount, an absolute path
OUTWARD = re.compile(r"\.\.|~/|/home/|/mnt/|\\\\|(?<![\w])[A-Za-z]:[\\/]|(?<![\w.\\])/[A-Za-z]")
FORBIDDEN = (
    "bundle_key",
    ".local/share/calliope",
    "\\\\wsl",
    "wsl.localhost",
    "/home/",
    "rx/runs",
    "rx-archive",
    "references_v1",
    "rx2-key-causes",
)
PATH_KEYS = ("file_path", "path", "notebook_path", "cwd")


def _norm(path: str) -> str:
    """A path as a lower-case forward-slash string; `/mnt/d/x` and `D:/x` alike."""

    p = path.replace("\\", "/").lower()
    m = re.match(r"^/mnt/([a-z])/(.*)$", p)
    return f"{m.group(1)}:/{m.group(2)}" if m else p


def within(path: str, inside: str) -> bool:
    """`path` is the directory or below it: a prefix that ends at a separator (RX2 re-review N5:
    `part01-other` is not inside `part01`)."""

    return path == inside or path.startswith(inside.rstrip("/") + "/")


def own_dirs(session_ids) -> list[re.Pattern]:
    """RX4a amendment A1: the judge's own scratch files, which hold only what it made from its
    directory. The session's scratchpad (`…/Temp/claude/<x>/<session id>/scratchpad/`) and the app's
    store of its long tool outputs (`…/.claude/projects/<x>/<session id>/tool-results/`), named by its
    own session id from the transcript; another session's are outside."""

    out = []
    for sid in session_ids:
        s = re.escape(sid.lower())
        out.append(
            re.compile(rf"^[a-z]:/users/[^/]+/appdata/local/temp/claude/[^/]+/{s}/scratchpad(/|$)")
        )
        out.append(
            re.compile(rf"^[a-z]:/users/[^/]+/\.claude/projects/[^/]+/{s}/tool-results(/|$)")
        )
    return out


def audit(tool_calls: list[dict], part_dir, own: list | None = None) -> list[str]:
    """What a judge's recorded tool calls show outside its directory. `tool_calls` are
    `{"tool", "input"}` as the transcript records them. An empty list passes. A listing inside the
    directory (`os.listdir('references')`) passes; one that can reach outside does not. This checks
    what the transcript shows, not every read a command makes (RX2-D §5.1, re-review N5)."""

    inside = _norm(str(part_dir)).rstrip("/")
    own = own or []

    def mine(v: str) -> bool:
        return within(v, inside) or any(o.match(v) for o in own)

    problems = []
    for n, call in enumerate(tool_calls, start=1):
        tool, given = call.get("tool"), call.get("input") or {}
        text = json.dumps(given, ensure_ascii=False)
        for name in PATH_KEYS:
            value = given.get(name)
            if isinstance(value, str):
                v = _norm(value)
                absolute = bool(re.match(r"^[a-z]:/", v)) or v.startswith("/")
                if (absolute and not mine(v)) or ".." in v:
                    problems.append(f"call {n} ({tool}): {name} {value} is outside the directory")
        for marker in FORBIDDEN:
            if marker.lower() in text.lower():
                problems.append(f"call {n} ({tool}): names {marker!r}")
        if tool in ("Bash", "PowerShell", "Glob", "Grep"):
            command = str(given.get("command") or given.get("pattern") or "")

            # the command's own `cd` into the directory is not outward; the rest is read raw, so a
            # script's escaped newline is not taken for a path
            def own_cd(m):
                return "" if _norm(m.group(1)).rstrip("/") == inside else m.group(0)

            body = re.sub(r'cd\s+"([^"]+)"', own_cd, command)
            if WALKS.search(command) and OUTWARD.search(body):
                problems.append(f"call {n} ({tool}): lists or walks beyond the directory")
            # any explicit path in the command, read or written by any program (RX2 re-review C1):
            # a parent, home, or an absolute path that is not inside the directory
            for path in explicit_paths(body):
                v = _norm(path)
                if ".." in path or path.startswith("~") or not mine(v):
                    problems.append(
                        f"call {n} ({tool}): names the path {path} outside the directory"
                    )
    return problems


# an absolute path (`/x`, `C:/x`, `C:\x`), a parent (`../x`) or a home path (`~/x`), as a command
# writes it; a script's `\n` (backslash, not slash) is not one
EXPLICIT_PATH = re.compile(
    # a path begins a token: after the start, a space, a quote, `=`, `(`, `[` or `,` — so `sed`'s
    # `s/a/b/` and code such as `x)/c.get(` are not paths
    r"""(?:^|(?<=[\s'"`=(\[,]))(?:[A-Za-z]:[\\/]|/(?=[A-Za-z_.~])|\.\./|~/)[^\s'"`()\],;|&<>]*"""
)


def explicit_paths(command: str) -> list[str]:
    """The paths a command names explicitly (absolute, parent or home), whatever reads them."""

    return [m.group(0) for m in EXPLICIT_PATH.finditer(command)]


def export_calls(zip_path: Path) -> list[dict]:
    """The tool calls of an exported session (the app's Export: a zip of JSON Lines transcripts)."""

    import zipfile

    calls = []
    with zipfile.ZipFile(zip_path) as z:
        for name in sorted(z.namelist()):
            if not name.endswith(".jsonl"):
                continue
            for raw in z.read(name).decode("utf-8", "replace").splitlines():
                try:
                    content = (json.loads(raw).get("message") or {}).get("content")
                except ValueError:
                    continue
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        calls.append({"tool": block.get("name"), "input": block.get("input") or {}})
    return calls


def export_session_ids(zip_path: Path) -> set[str]:
    """The session ids an exported transcript records (its own and its subagents')."""

    import zipfile

    ids = set()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name.endswith(".jsonl"):
                for raw in z.read(name).decode("utf-8", "replace").splitlines():
                    try:
                        sid = json.loads(raw).get("sessionId")
                    except (ValueError, AttributeError):
                        continue
                    if isinstance(sid, str) and re.fullmatch(r"[0-9a-fA-F-]{36}", sid):
                        ids.add(sid)
    return ids


def record_audit(judging_id: str, part: int, zip_path: Path, part_dir, keys: Path = KEYS) -> dict:
    """Audit one part's judge from its exported transcript and keep the result beside the key."""

    calls = export_calls(zip_path)
    problems = audit(calls, part_dir, own_dirs(export_session_ids(zip_path)))
    result = {"part": part, "transcript": zip_path.name, "calls": len(calls),
              "passed": not problems, "problems": problems}  # fmt: skip
    (keys / judging_id / f"audit-part{part:02d}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")  # fmt: skip
    return result


def checked_judgings(judging_id: str, parts_root: Path, keys: Path = KEYS) -> dict[int, dict]:
    """Every part's judging, refused unless (RX2 review B3): its audit passed; it validates against
    `judge_v1.schema.json`; it holds every item of its bundle once and nothing else; every sentence of
    every item is judged once; every key cause of the item's moment is judged once."""

    import jsonschema

    key = json.loads((keys / judging_id / "bundle_key.json").read_text(encoding="utf-8"))["key"]
    schema = json.loads((PROMPTS / "judge_v1.schema.json").read_text(encoding="utf-8"))
    out = {}
    parts = sorted(parts_root.glob("part*"))
    if {info["part"] for info in key.values()} != {int(p.name[4:]) for p in parts}:
        raise ValueError("the parts on disk are not the key's parts")
    for part_dir in parts:
        part = int(part_dir.name[4:])
        audit_file = keys / judging_id / f"audit-part{part:02d}.json"
        if (
            not audit_file.exists()
            or not json.loads(audit_file.read_text(encoding="utf-8"))["passed"]
        ):
            raise ValueError(f"part {part}: no passed audit ({audit_file.name})")
        doc = json.loads((part_dir / "judging.json").read_text(encoding="utf-8"))
        jsonschema.validate(doc, schema)
        bundle_items = {i["key"]: i for i in
                        json.loads((part_dir / "bundle.json").read_text(encoding="utf-8"))["items"]}  # fmt: skip
        judged = [i["key"] for i in doc["items"]]
        if len(judged) != len(set(judged)):
            raise ValueError(f"part {part}: an item judged twice")
        if set(judged) != set(bundle_items):
            raise ValueError(f"part {part}: {len(set(bundle_items) - set(judged))} items not judged, "
                             f"{len(set(judged) - set(bundle_items))} not in the bundle")  # fmt: skip
        for item in doc["items"]:
            want = {s["n"] for s in bundle_items[item["key"]]["sentences"]}
            got = [s["n"] for s in item["sentences"]]
            if sorted(got) != sorted(want):
                raise ValueError(
                    f"part {part}: item {item['key']}'s sentences are not judged one each"
                )
            info = key[item["key"]]
            ref = json.loads((part_dir / "references" / f"{info['game']}-{info['ply']}.json")
                             .read_text(encoding="utf-8"))  # fmt: skip
            causes = sorted(c["cause"] for c in item.get("causes") or [])
            if causes != list(range(1, len(ref.get("key_causes") or []) + 1)):
                raise ValueError(
                    f"part {part}: item {item['key']}'s key causes are not judged one each"
                )
        out[part] = doc
    return out


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
