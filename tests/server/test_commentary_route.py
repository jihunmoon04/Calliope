"""AG-D §8 and §11 test 7: accepted commentary through the HTTP server — the commentary route
(current, stale, out of range, judged), the combined document built on request, and the stored
`result.json` served as it was."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import jsonschema
import pytest
from helpers import UNRATED, slot
from synthetic import engine
from test_web import call

from calliope.agent import Session
from calliope.results import schema, schema_errors
from calliope.server import CommentaryStore, game_key, parse_game
from calliope.server.jobs import Jobs
from calliope.server.web import IMMUTABLE, serve

VIEWER = Path(__file__).resolve().parents[2] / "viewer"


@pytest.fixture
def served(tmp_path):
    table = Jobs(tmp_path, slot()[0])
    table.recover()
    job, _ = table.submit(UNRATED, "1-3")
    table.run_next()
    server = serve(table, VIEWER, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield table, job["id"], server.server_address[1]
    server.shutdown()
    server.server_close()


def _accept(tmp_path, ply: int | None = None, judged: str | None = None) -> str:
    """An accepted commentary written by an MCP session on the same data directory."""

    s = Session(tmp_path, engine)
    try:
        s.open_game(pgn=UNRATED)
        if judged is None:
            record = s.ply("g1", ply)
            move = record["uci"]
        else:
            record = s.judge_move("g1", {"ply": 3, "at": "before"}, judged)
            move = judged
        j = record["analysis"]["judgements"][0]
        p = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": move,
             "grade": j["grade"], "label": j["label"], "best_move": j["best"]["move"]["uci"]}  # fmt: skip
        subject = {"ply": ply} if judged is None else {"position": {"ply": 3, "at": "before"},
                                                       "move": judged}  # fmt: skip
        answer = s.submit_commentary(
            "g1", agent={"name": "t"}, propositions=[p],
            sentences=[{"text": "이 수의 판정이다.", "class": "sourced", "cites": ["p1"]}],
            **subject,
        )  # fmt: skip
        assert answer["accepted"], answer
        return answer["id"]
    finally:
        s.close()


def test_the_commentary_route_and_the_combined_document(served, tmp_path) -> None:
    _, jid, port = served
    _, _, before = call(port, "GET", f"/api/games/{jid}/result")
    stored = (tmp_path / "games" / jid / "result.json").read_bytes()
    current = _accept(tmp_path, ply=2)
    beyond = _accept(tmp_path, ply=5)  # the job analysed plies 1-3
    judged = _accept(tmp_path, judged="Nc3")
    code, headers, body = call(port, "GET", f"/api/games/{jid}/commentary")
    listing = json.loads(body)
    assert code == 200 and headers["Cache-Control"] == "no-store"
    assert [(c["id"], c["stale"]) for c in listing["plies"]["2"]] == [(current, False)]
    assert [(c["id"], c["stale"]) for c in listing["plies"]["5"]] == [(beyond, None)]
    assert [(c["id"], c["stale"]) for c in listing["judged"]] == [(judged, None)]
    code, headers, body = call(port, "GET", f"/api/games/{jid}/result?with=commentary")
    combined = json.loads(body)
    assert code == 200 and headers["Cache-Control"] == "no-store"
    plies = {p["ply"]: p for p in combined["plies"]}
    assert plies[2]["ai_commentary"]["id"] == current and "ai_commentary" not in plies[1]
    assert plies[2]["ai_commentary"]["level"] == "SOURCE_VERIFIED"
    assert not schema_errors(combined)
    jsonschema.validate(combined, schema(), cls=jsonschema.Draft202012Validator)
    code, headers, after = call(port, "GET", f"/api/games/{jid}/result")
    assert after == before == stored and headers["Cache-Control"] == IMMUTABLE
    assert (tmp_path / "games" / jid / "result.json").read_bytes() == stored


def test_a_commentary_on_another_analysis_is_stale(served, tmp_path) -> None:
    _, jid, port = served
    _accept(tmp_path, ply=2)
    store = CommentaryStore(tmp_path / "commentary")
    key = game_key(parse_game(UNRATED).game)
    [path] = list((tmp_path / "commentary" / key).rglob("*.json"))
    record = json.loads(path.read_bytes())
    path.write_text(json.dumps(record | {"bundle": {"tree": "0" * 64, "graph": "0" * 64}}))
    assert store.for_game(key)[0]["bundle"]["tree"] == "0" * 64
    listing = json.loads(call(port, "GET", f"/api/games/{jid}/commentary")[2])
    assert listing["plies"]["2"][0]["stale"] is True
    combined = json.loads(call(port, "GET", f"/api/games/{jid}/result?with=commentary")[2])
    assert all("ai_commentary" not in p for p in combined["plies"])  # only current ones


def test_unknown_games_and_no_commentary(served) -> None:
    _, jid, port = served
    assert call(port, "GET", "/api/games/" + "0" * 64 + "/commentary")[0] == 404
    listing = json.loads(call(port, "GET", f"/api/games/{jid}/commentary")[2])
    assert listing == {"format": "ai_commentary_list_v1", "plies": {}, "judged": []}
