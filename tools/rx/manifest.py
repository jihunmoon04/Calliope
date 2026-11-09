"""The sets' manifest and base caches (RX0-D §2, §3.1; RX1-D §4.6, §5).

Train is the four trial games, their PGNs the repository's fixtures, their moments the trials'.
Validation and Test are the owner's chess.com games (RX framing §8.1), their PGNs outside the
repository. Validation's moments come from `rx_moments` over every analysed ply; Test gets digests
only, and no PGN of it is read beyond its digest.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path

import chess.pgn

from .run import REPO, tree_digests

RX_DATA = Path.home() / ".local" / "share" / "calliope" / "rx"
MANIFEST = REPO / "tools" / "rx" / "sets_v1.json"

TRAIN = [  # RX0-D §2, §3.1: the fixtures and the trials' fixed moments (ST-D §0)
    {"name": "hung", "path": "tests/agent/fixtures/hung_queen.pgn", "owner": "black",
     "moments": [14, 25, 68]},
    {"name": "rapid", "path": "tests/reasoning/fixtures/chesscom_rapid_813_801.pgn",
     "owner": "white", "moments": [40, 52, 54]},
    {"name": "fresh", "path": "tests/agent/fixtures/weak_engines_1.pgn", "owner": None,
     "moments": [56, 62, 76]},
    {"name": "fourth", "path": "tests/agent/fixtures/weak_engines_2.pgn", "owner": None,
     "moments": [37, 38, 56]},
]  # fmt: skip
VALIDATION = [("184800218248", "white"), ("185264271324", "white"), ("185371835722", "black"),
              ("185922072242", "black")]  # fmt: skip
TEST = [("186203030416", "black"), ("186437361608", "white"), ("186491823816", "black"),
        ("186492056006", "white")]  # fmt: skip


# AF-D §7.4 with AF implementation A7: Test 2's four games (chess.com numbers and the owner's side),
# chosen by the owner by metadata only (2026-11-09), opened only after the freeze. Two as White, two
# as Black; two won, two lost. Reserves, in order: 185790829982 (white), 185920835778 (black),
# 185573762490 (white).
TEST2: tuple[tuple[str, str], ...] = (
    ("186148834544", "white"),  # 2026-10-29, won by resignation, 77 plies
    ("186141458686", "black"),  # 2026-10-29, won by resignation, 61 plies
    ("186508597164", "white"),  # 2026-11-04, lost by resignation, 52 plies
    ("186014364656", "black"),  # 2026-10-27, lost to mate, 65 plies
)
TEST_SETS = ("test", "test2")  # each opened on its own, after its own freeze (AF-D §7.4)


def opened(manifest: dict, set_name: str) -> dict | None:
    """A test set's opening record (`opened[set]`; Test 1's earlier `test_opened` reads as
    `opened["test"]`)."""

    record = (manifest.get("opened") or {}).get(set_name)
    if record is None and set_name == "test":
        record = manifest.get("test_opened")
    return record


def uci_digest(pgn: str) -> str:
    game = chess.pgn.read_game(io.StringIO(pgn))
    return hashlib.sha256(" ".join(m.uci() for m in game.mainline_moves()).encode()).hexdigest()


def pgn_text(set_name: str, entry: dict, pgn_dir: Path) -> str:
    if set_name == "train":
        return (REPO / entry["path"]).read_text(encoding="utf-8")
    return (pgn_dir / f"{entry['number']}.pgn").read_text(encoding="utf-8")


def build_base(set_name: str, games: list[tuple[str, str]], base: Path, engine: str,
               on_game=None) -> dict[str, str]:  # fmt: skip
    """Analyse every ply of the games into `base/data`; their game ids by name."""

    from calliope.agent import Limits, Session
    from calliope.facts.search import StockfishEngine

    limits = replace(Limits(), max_job_plies_per_window=10_000, max_queued_jobs=8)
    session = Session(base / "data", lambda: StockfishEngine.start(engine), limits)
    ids = {}
    try:
        for name, pgn in games:
            game_id = session.open_game(pgn=pgn)["game"]
            ids[name] = game_id
            key = session.analyze_start(game_id)
            while True:
                session.analyze_wait(key, 120)
                job = session.analyze_answer(game_id)["job"]
                if on_game:
                    on_game(name, job)
                if job["state"] in ("done", "failed", "cancelled"):
                    break
            if job["state"] != "done" or job.get("failed_plies"):
                raise RuntimeError(f"{set_name} {name}: the analysis ended {job}")
        # LT review F1: Test's moments are chosen as Validation's, once Test is opened
        moments = {name: session.rx_moments(ids[name]) for name, _ in games} \
            if set_name in ("validation", *TEST_SETS) else {}  # fmt: skip
    finally:
        session.close()
    return {"ids": ids, "moments": moments}


def seal(base: Path, set_name: str) -> dict:
    """RX1-D §4.6: the base cache's digests, and its files read-only."""

    files = tree_digests(base / "data")
    doc = {"set": set_name, "files": files}
    (base / "base.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    for path in (base / "data").rglob("*"):
        if path.is_file():
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return doc


def build(sets: list[str], pgn_dir: Path, engine: str, out=sys.stdout) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {
        "version": "sets_v1", "sets": {}}  # fmt: skip
    for set_name in sets:
        base = RX_DATA / "base" / set_name
        if (base / "base.json").exists():
            raise RuntimeError(f"{base} is sealed; remove it to rebuild")
        entries: list[dict]
        if set_name == "train":
            entries = [dict(e) for e in TRAIN]
        elif set_name == "validation":
            entries = [{"name": n, "number": n, "owner": side} for n, side in VALIDATION]
        elif set_name == "test2":
            if not TEST2:
                raise RuntimeError("Test 2's games are not chosen yet (AF-D §7.4)")
            entries = [{"name": n, "number": n, "owner": side} for n, side in TEST2]
        else:
            entries = [{"name": n, "number": n, "owner": side} for n, side in TEST]
        for entry in entries:
            entry["uci_sha256"] = uci_digest(pgn_text(set_name, entry, pgn_dir))
        if set_name not in TEST_SETS:  # a test set: digests only, analysed when opened (RX0-D §2)
            games = [(e["name"], pgn_text(set_name, e, pgn_dir)) for e in entries]
            done = build_base(set_name, games, base, engine,
                              lambda n, j, s=set_name: print(f"{s} {n}: {j['state']} {j['done']}/"
                                                 f"{j['total']}", file=out, flush=True))  # fmt: skip
            for entry in entries:
                entry["game_id"] = done["ids"][entry["name"]]
                if set_name == "validation":
                    chosen = done["moments"][entry["name"]]
                    entry["moments"] = [m["ply"] for m in chosen["moments"]]
                    entry["moment_slots"] = chosen["moments"]
            seal(base, set_name)
        manifest["sets"][set_name] = entries
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")  # fmt: skip
    return manifest


def open_test(pgn_dir: Path, engine: str, freeze: Path, out=sys.stdout,
              set_name: str = "test") -> dict:  # fmt: skip
    """RX0-D §2 step 2 (LT-D §6.4; AF-D §7.4 for any test set): after the freeze, analyse every
    ply of the set's games, choose their moments as Validation's were, and seal the base. `freeze`
    is the freeze record (the candidate's versions and bounds, RX0-D §2 step 1); its digest is kept
    in the manifest as `opened[set]`. Refused while no freeze record exists, once the set is open,
    for a `freeze_v2` record made for another set, or for a record that opened another set."""

    if set_name not in TEST_SETS:
        raise RuntimeError(f"{set_name} is not a test set ({', '.join(TEST_SETS)})")
    if not freeze.is_file():
        raise RuntimeError(f"no freeze record at {freeze}: Test opens after the freeze (RX0-D §2)")
    from .freeze import problems, read, servers_problems

    doc, digest = read(freeze)
    wrong = problems(doc)  # LT implementation review N1: a record, not any file
    if wrong:
        raise RuntimeError(f"the freeze record {freeze} is not one: {'; '.join(wrong)}")
    if doc.get("version") == "freeze_v2" and doc.get("for") != set_name:
        raise RuntimeError(f"the freeze record is for {doc.get('for')}, not {set_name}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["sets"].get(set_name)
    if not entries:
        raise RuntimeError(f"{set_name} has no games in the manifest")
    if any("moments" in e for e in entries) or opened(manifest, set_name):
        raise RuntimeError(f"{set_name} is open already: a later candidate needs new Test games")
    for other in TEST_SETS:
        if other != set_name and (opened(manifest, other) or {}).get("freeze_sha256") == digest:
            raise RuntimeError(f"this freeze record opened {other}: one record opens one set")
    wrong = servers_problems(doc)  # AF-D §6: each worktree server like the base's checkout
    if wrong:
        raise RuntimeError("a variant's server is not ready: " + "; ".join(wrong))
    base = RX_DATA / "base" / set_name
    if (base / "base.json").exists():
        raise RuntimeError(f"{base} is sealed; remove it to rebuild")
    games = [(e["name"], verify(set_name, e, pgn_dir)) for e in entries]
    done = build_base(set_name, games, base, engine,
                      lambda n, j: print(f"{set_name} {n}: {j['state']} {j['done']}/{j['total']}",
                                         file=out, flush=True))  # fmt: skip
    for entry in entries:
        chosen = done["moments"][entry["name"]]
        if not chosen.get("moments"):  # rx_moments refuses fewer than three ranked plies
            raise RuntimeError(f"{set_name} {entry['name']}: no moments could be chosen ({chosen})")
    for entry in entries:
        entry["game_id"] = done["ids"][entry["name"]]
        chosen = done["moments"][entry["name"]]
        entry["moments"] = [m["ply"] for m in chosen["moments"]]
        entry["moment_slots"] = chosen["moments"]
    seal(base, set_name)
    record = {"freeze": str(freeze.resolve()), "freeze_sha256": digest}
    if set_name == "test":
        manifest["test_opened"] = record  # as LT wrote it
    else:
        manifest.setdefault("opened", {})[set_name] = record
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")  # fmt: skip
    return manifest


def verify(set_name: str, entry: dict, pgn_dir: Path) -> str:
    """The game's PGN, checked against the manifest's digest (RX0-D §2); a mismatch stops."""

    pgn = pgn_text(set_name, entry, pgn_dir)
    if uci_digest(pgn) != entry["uci_sha256"]:
        raise RuntimeError(f"{set_name} {entry['name']}: the PGN does not match the manifest")
    return pgn


def engine_path() -> str:
    path = os.environ.get("CALLIOPE_STOCKFISH_PATH")
    if not path:
        raise RuntimeError("set CALLIOPE_STOCKFISH_PATH")
    return path
