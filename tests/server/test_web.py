"""The HTTP API (AS-D §6; test 8) and the end-to-end run under Stockfish (test 12)."""

from __future__ import annotations

import http.client
import json
import os
import threading
from pathlib import Path

import pytest
from helpers import RATED, UNRATED, slot
from test_jobs import DOC, stub

from calliope.server.jobs import Jobs, wait_until
from calliope.server.web import IMMUTABLE, serve

VIEWER = Path(__file__).resolve().parents[2] / "viewer"


@pytest.fixture
def api(tmp_path):
    table = Jobs(tmp_path, slot()[0], analyse=stub, queue_limit=3)
    table.recover()
    server = serve(table, VIEWER, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield table, server.server_address[1]
    server.shutdown()
    server.server_close()


def call(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, dict(response.getheaders()), data


def post(port, value, kind="application/json"):
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    return call(port, "POST", "/api/games", body, {"Content-Type": kind})


def test_the_routes(api) -> None:
    table, port = api
    status, headers, page = call(port, "GET", "/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert page == (VIEWER / "index.html").read_bytes()
    assert call(port, "GET", "/index.html?game=x")[0] == 200
    code, headers, body = post(port, {"pgn": RATED})
    job = json.loads(body)
    assert code == 202 and job["state"] == "queued" and headers["Cache-Control"] == "no-store"
    code, _, body = call(port, "GET", f"/api/games/{job['id']}")
    assert code == 200 and json.loads(body)["queue_position"] == 1
    code, _, body = call(port, "GET", f"/api/games/{job['id']}/result")
    assert code == 409 and json.loads(body)["state"] == "queued"  # not done: its status
    table.run_next()
    code, headers, body = call(port, "GET", f"/api/games/{job['id']}/result")
    assert code == 200 and json.loads(body) == DOC and headers["Cache-Control"] == IMMUTABLE
    code, _, body = post(port, {"pgn": RATED})
    assert code == 200 and json.loads(body)["state"] == "done"  # already done
    code, _, body = call(port, "GET", "/api/games")
    assert code == 200 and [g["id"] for g in json.loads(body)["games"]] == [job["id"]]
    assert set(json.loads(body)["games"][0]) == {"id", "state", "created", "game", "plies"}


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/games/" + "0" * 64, "GET"),  # unknown
        ("/api/games/" + "G" * 64, "GET"),  # not lower-case hex
        ("/api/games/abc", "GET"),
        ("/api/games/" + "0" * 64 + "/result", "GET"),
        ("/viewer/local/g.json", "GET"),  # no other file
        ("/../README.md", "GET"),
        ("/api/other", "POST"),
    ],
)
def test_nothing_else_is_served(api, path, method) -> None:
    _, port = api
    assert call(port, method, path, b"{}", {"Content-Type": "application/json"})[0] == 404


def test_no_options_and_no_cors(api) -> None:
    _, port = api
    status, headers, _ = call(port, "OPTIONS", "/api/games")
    assert status == 501 and not any(k.lower().startswith("access-control") for k in headers)


@pytest.mark.parametrize(
    ("body", "kind", "code", "message"),
    [
        ({"pgn": RATED}, "text/plain", 415, "application/json"),
        ({"pgn": RATED}, "application/x-www-form-urlencoded", 415, "application/json"),
        (b"{", "application/json", 400, "not JSON"),
        ({"plies": "1"}, "application/json", 400, "pgn must be a string"),
        ({"pgn": 3}, "application/json", 400, "pgn must be a string"),
        ({"pgn": RATED, "plies": 4}, "application/json", 400, "plies must be a string"),
        ({"pgn": ""}, "application/json", 400, "no game"),
        ({"pgn": '[Event "x"]\n\n*'}, "application/json", 400, "no moves"),
        ({"pgn": "1. e4 e5 2. Ke3 *"}, "application/json", 400, "cannot be read"),
        ({"pgn": '[Variant "Atomic"]\n\n1. e4 *'}, "application/json", 400, "standard chess"),
        ({"pgn": UNRATED, "plies": "30-40"}, "application/json", 400, "outside the game"),
        ({"pgn": UNRATED, "plies": "a-b"}, "application/json", 400, "ply range"),
    ],
)
def test_input_checks(api, body, kind, code, message) -> None:
    _, port = api
    status, _, answer = post(port, body, kind)
    assert status == code and message in json.loads(answer)["error"]


def test_too_many_plies_and_too_large(api) -> None:
    _, port = api
    shuffle = " ".join(
        f"{n}. {'Nf3 Nf6' if n % 2 else 'Ng1 Ng8'}" for n in range(1, 302)
    )  # 602 plies
    status, _, answer = post(port, {"pgn": shuffle + " *"})
    assert status == 400 and "at most 600" in json.loads(answer)["error"]
    status, _, answer = post(port, {"pgn": "x" * (256 * 1024 + 1)})
    assert status == 413


def test_a_full_queue_is_503(api) -> None:
    _, port = api
    games = [UNRATED.replace("1. e4", f'[White "p{i}"]\n\n1. e4') for i in range(4)]
    codes = [post(port, {"pgn": g})[0] for g in games]
    assert codes == [202, 202, 202, 503]


STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH")


@pytest.mark.skipif(not STOCKFISH, reason="needs CALLIOPE_STOCKFISH_PATH")
def test_12_a_real_game_end_to_end(tmp_path) -> None:
    """A short game through HTTP, analysed by Stockfish 19, reaches `done` and validates."""

    import jsonschema

    from calliope.facts.search import StockfishEngine
    from calliope.results import schema
    from calliope.server import EngineSlot

    engine_slot = EngineSlot(lambda: StockfishEngine.start(STOCKFISH))
    table = Jobs(tmp_path, engine_slot)
    table.recover()
    table.start()
    server = serve(table, VIEWER, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        code, _, body = post(port, {"pgn": RATED, "plies": "1-4"})
        job = json.loads(body)
        assert code == 202
        assert wait_until(lambda: table.status(job["id"])["state"] in ("done", "failed"), 300)
        code, _, body = call(port, "GET", f"/api/games/{job['id']}/result")
        assert code == 200, body
        document = json.loads(body)
        jsonschema.validate(document, schema(), cls=jsonschema.Draft202012Validator)
        assert [p["ply"] for p in document["plies"]] == [1, 2, 3, 4]
        assert all(p["bundle"]["stored"] for p in document["plies"])
    finally:
        server.shutdown()
        server.server_close()
        table.stop(timeout=5)
        engine_slot.close()
