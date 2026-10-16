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
        game = s.open_game(pgn=UNRATED)["game"]
        if judged is None:
            record = s.ply(game, ply)
            move = record["uci"]
        else:
            record = s.judge_move(game, {"ply": 3, "at": "before"}, judged)
            move = judged
        j = record["analysis"]["judgements"][0]
        p = {"id": "p1", "kind": "judgement", "judgement": j["ref"], "move": move,
             "grade": j["grade"], "label": j["label"], "best_move": j["best"]["move"]["uci"]}  # fmt: skip
        subject = {"ply": ply} if judged is None else {"position": {"ply": 3, "at": "before"},
                                                       "move": judged}  # fmt: skip
        answer = s.submit_commentary(
            game, agent={"name": "t"}, propositions=[p],
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
    entry = listing["plies"]["2"][0]  # display_v1 (AG3-D D14): the judgement and the subject
    assert entry["display"]["subject"]["moves"][0]["uci"] == entry["subject"]["path"][-1]
    assert entry["propositions"][0]["display"]["moves"][0]["uci"] == entry["subject"]["path"][-1]
    assert listing["judged"][0]["display"]["subject"]["moves"][0]["san"] == "Nc3"
    code, headers, body = call(port, "GET", f"/api/games/{jid}/result?with=commentary")
    combined = json.loads(body)
    assert code == 200 and headers["Cache-Control"] == "no-store"
    plies = {p["ply"]: p for p in combined["plies"]}
    assert plies[2]["ai_commentary"]["id"] == current and "ai_commentary" not in plies[1]
    assert plies[2]["ai_commentary"]["level"] == "SOURCE_VERIFIED"
    assert plies[2]["ai_commentary"]["display"] == entry["display"]
    assert plies[2]["ai_commentary"]["propositions"] == entry["propositions"]
    assert "subject" not in plies[2]["ai_commentary"]  # the combined document's fields only
    for path in (tmp_path / "commentary").glob("*/*/*.json"):  # never stored
        assert "display" not in path.read_text()
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


def test_a_damaged_record_is_skipped_and_a_damaged_job_answers_409(served, tmp_path) -> None:
    table, jid, port = served
    current = _accept(tmp_path, ply=2)
    key = game_key(parse_game(UNRATED).game)
    folder = next((tmp_path / "commentary" / key).iterdir())
    (folder / "broken.json").write_text('{"format": "ai_commentary_v1", "id": "x"}')
    (folder / "garbage.json").write_text("{not json")
    listing = json.loads(call(port, "GET", f"/api/games/{jid}/commentary")[2])
    assert [c["id"] for c in listing["plies"]["2"]] == [current]
    table.pgn = lambda jid: ""  # a damaged job keeps no PGN
    assert call(port, "GET", f"/api/games/{jid}/commentary")[0] == 409
    assert call(port, "GET", f"/api/games/{jid}/result?with=commentary")[0] == 409  # B2
    assert call(port, "GET", f"/api/games/{jid}/result")[0] == 200  # the stored bytes still


def test_a_readable_but_incomplete_record_is_skipped(served, tmp_path) -> None:
    """Re-review B1: a newer record that lacks `sentences`, or whose level or propositions are
    not an `AiCommentary`, never reaches the combined document."""

    _, jid, port = served
    current = _accept(tmp_path, ply=2)
    key = game_key(parse_game(UNRATED).game)
    path = next((tmp_path / "commentary" / key).glob("*/*.json"))
    record = json.loads(path.read_bytes())
    for n, damage in enumerate(({"sentences": None}, {"level": "VERIFIED"}, {"propositions": []},
                                {"sentences": [{"text": "x", "class": "sourced"}]})):  # fmt: skip
        newer = {k: v for k, v in (record | damage).items() if v is not None}
        newer["id"] = f"{'9' * 19}{n}-ffffffff"  # newer than any id written by time
        (path.parent / f"{newer['id']}.json").write_text(json.dumps(newer))
    listing = json.loads(call(port, "GET", f"/api/games/{jid}/commentary")[2])
    assert [c["id"] for c in listing["plies"]["2"]] == [current]
    combined = json.loads(call(port, "GET", f"/api/games/{jid}/result?with=commentary")[2])
    assert combined["plies"][1]["ai_commentary"]["id"] == current
    assert schema_errors(combined) == []


def test_ids_order_by_time_within_a_second(tmp_path) -> None:
    store = CommentaryStore(tmp_path)
    record = {"game_key": "k", "subject": {"path": ["e2e4"]}, "bundle": {"tree": "t", "graph": "g"},
              "level": "SOURCE_VERIFIED", "propositions": [{"id": "p", "kind": "definition"}],
              "sentences": [{"text": "t", "class": "sourced", "cites": ["p"]}]}  # fmt: skip
    ids = [store.write(record) for _ in range(5)]
    assert [r["id"] for r in store.for_game("k")] == ids[::-1]
