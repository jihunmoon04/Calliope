"""The sets' builds and the fixed moments' references (RX2-D §3, §4.1).

Both read a set's sealed base cache on a copy, in process, so the base stays as it was sealed.
`annotate` writes the build into `base.json` after a probe shows that every fixed moment is a cache hit.
`reference` writes one JSON file a fixed moment: what the agent's `ply` shows (the digest), the full
record, the board and the PGN up to the move, and every served handle's `identity` and `line_key`.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import chess.pgn

from .manifest import MANIFEST, RX_DATA, pgn_text
from .run import REPO

REFERENCES = REPO / "tools" / "rx" / "references_v1"


@contextmanager
def probe_session(set_name: str, engine: str, recorder=None):
    """A session on a copy of the set's base cache, started on `engine`."""

    from calliope.agent import Limits, Session
    from calliope.facts.search import StockfishEngine

    tmp = Path(tempfile.mkdtemp(prefix="rx-probe-"))
    try:
        shutil.copytree(RX_DATA / "base" / set_name / "data", tmp / "data")
        for path in (tmp / "data").rglob("*"):
            path.chmod(0o644 if path.is_file() else 0o755)
        session = Session(tmp / "data", lambda: StockfishEngine.start(engine), Limits(),
                          recorder=recorder)  # fmt: skip
        try:
            yield session
        finally:
            session.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_of(session) -> dict:
    from calliope.agent.record import build_id

    port, _, digest = session._engine_build()
    parts = {"engine": list(port.identity.fingerprint()), "profile": list(session.profile.fingerprint()),
             "reasoning": digest}  # fmt: skip
    return parts | {"build_id": build_id(parts)}


def annotate(set_name: str, engine: str) -> dict:
    """RX2-D §3: the build into `base.json`, after every fixed moment reads from the cache."""

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base_json = RX_DATA / "base" / set_name / "base.json"
    doc = json.loads(base_json.read_text(encoding="utf-8"))
    with probe_session(set_name, engine) as session:
        build = build_of(session)
        for entry in manifest["sets"][set_name]:
            gid = session.open_game(pgn=pgn_text(set_name, entry, RX_DATA / "sets"))["game"]
            parsed = session.game(gid).parsed
            missed = [p for p in entry["moments"] if not session._cached(parsed, p)]
            if missed:
                raise RuntimeError(f"{set_name} {entry['name']}: plies {missed} are not in the base "
                                   "for this build; another engine or build")  # fmt: skip
    doc["build"] = build
    base_json.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return build


def _board_texts(pgn: str, ply: int) -> dict:
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    moves = list(game.mainline_moves())
    sans = []
    for move in moves[: ply - 1]:
        sans.append(board.san(move))
        board.push(move)
    before = board.fen()
    played = moves[ply - 1]
    san = board.san(played)
    board.push(played)
    numbered = []
    for i, s in enumerate(sans, start=1):
        numbered.append(f"{(i + 1) // 2}." + s if i % 2 else s)
    return {"fen_before": before, "fen_after": board.fen(), "move": san, "uci": played.uci(),
            "moves_before": " ".join(numbered)}  # fmt: skip


def references(set_name: str, engine: str, out_dir: Path = REFERENCES) -> list[Path]:
    from calliope.agent.record import HANDLE, Recorder

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sealed = json.loads((RX_DATA / "base" / set_name / "base.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="rx-ref-"))
    written = []
    try:
        recorder = Recorder(tmp, "REF")
        with probe_session(set_name, engine, recorder) as session:
            build = build_of(session)
            if build["build_id"] != (sealed.get("build") or {}).get("build_id"):
                raise RuntimeError("the probe's build is not the base's: annotate first")
            for entry in manifest["sets"][set_name]:
                pgn = pgn_text(set_name, entry, RX_DATA / "sets")
                gid = session.open_game(pgn=pgn)["game"]
                for ply in entry["moments"]:
                    digest = session.ply(gid, ply)
                    full = session.ply(gid, ply, view="full")
                    served = {}  # every handle the probe served so far, by ref
                    for raw in recorder.path.read_text(encoding="utf-8").splitlines():
                        line = json.loads(raw)
                        if line.get("type") == "handle":
                            served[line["ref"]] = {"kind": line["kind"], "identity": line["identity"],
                                                   "line_key": line.get("line_key")}  # fmt: skip
                    text = json.dumps([digest, full], ensure_ascii=False, default=str)
                    handles = {ref: served[ref] for ref in sorted(set(HANDLE.findall(text)))
                               if ref in served}  # fmt: skip
                    doc = {"version": "references_v1", "set": set_name, "game": entry["name"],
                           "ply": ply, "build_id": build["build_id"],
                           **_board_texts(pgn, ply), "digest": digest, "full": full,
                           "handles": handles, "key_causes": [], "status": "none"}  # fmt: skip
                    path = out_dir / set_name / f"{entry['name']}-{ply}.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n",
                                    encoding="utf-8")  # fmt: skip
                    written.append(path)
        recorder.end()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return written
