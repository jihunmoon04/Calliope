"""The HTTP API (AS-D §6): fixed routes, JSON answers, the viewer page at the root.

Every path is relative to the server root, so the page and the API work under any prefix a
proxy adds (`/proxy/<port>/`, a domain root). The app has no authentication: it binds loopback,
and the proxy in front authenticates (AS-D S8).
"""

from __future__ import annotations

import json
import logging
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from calliope.server.commentary import CommentaryStore, game_key, listing, with_commentary
from calliope.server.jobs import Jobs, QueueFull
from calliope.server.pipeline import InputError, parse_game

MAX_BODY = 256 * 1024
GAME = re.compile(r"^/api/games/([0-9a-f]{64})$")
RESULT = re.compile(r"^/api/games/([0-9a-f]{64})/result$")
COMMENTARY = re.compile(r"^/api/games/([0-9a-f]{64})/commentary$")  # AG-D §8
IMMUTABLE = "private, max-age=31536000, immutable"

log = logging.getLogger(__name__)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, jobs: Jobs, viewer: Path) -> None:
        self.jobs = jobs
        self.viewer = viewer
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "calliope"
    sys_version = ""

    # -- routes -----------------------------------------------------------------------------

    def do_GET(self) -> None:
        path, _, query = self.path.partition("?")
        jobs = self.server.jobs
        if path in ("/", "/index.html"):
            page = self._viewer()
            if page is None:
                return self._error(HTTPStatus.NOT_FOUND, "the viewer page is missing")
            return self._send(HTTPStatus.OK, page, "text/html; charset=utf-8", "no-store")
        if path == "/api/games":
            return self._json(HTTPStatus.OK, {"games": jobs.summaries()})
        if match := GAME.match(path):
            status = jobs.status(match[1])
            if status is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            return self._json(HTTPStatus.OK, status)
        if match := RESULT.match(path):
            status = jobs.status(match[1])
            if status is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            body = jobs.result(match[1])
            if body is None:
                return self._json(HTTPStatus.CONFLICT, status)
            if parse_qs(query).get("with") == ["commentary"]:  # built fresh, never stored (§8)
                try:
                    records, played = self._commentary(match[1])
                except InputError:  # as the commentary route (AG2 re-review B2)
                    return self._error(HTTPStatus.CONFLICT, "the job's game cannot be read")
                combined = with_commentary(json.loads(body), records, played)
                return self._json(HTTPStatus.OK, combined)
            return self._send(HTTPStatus.OK, body, "application/json", IMMUTABLE)
        if match := COMMENTARY.match(path):
            if jobs.status(match[1]) is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            try:
                records, played = self._commentary(match[1])
            except InputError:  # a damaged job keeps no game to key its commentary by
                return self._error(HTTPStatus.CONFLICT, "the job's game cannot be read")
            body = jobs.result(match[1])
            document = json.loads(body) if body is not None else None
            return self._json(HTTPStatus.OK, listing(records, played, document))
        return self._error(HTTPStatus.NOT_FOUND, "not found")

    def _commentary(self, jid: str) -> tuple[list[dict], list[str]]:
        """The game's accepted commentaries (newest first) and its played moves."""

        jobs = self.server.jobs
        parsed = parse_game(jobs.pgn(jid))
        store = CommentaryStore(jobs.data / "commentary")
        return store.for_game(game_key(parsed.game)), list(parsed.uci)

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/games":
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        kind = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if kind != "application/json":
            return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send application/json")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._error(HTTPStatus.LENGTH_REQUIRED, "Content-Length is required")
        if length < 0:
            return self._error(HTTPStatus.BAD_REQUEST, "Content-Length must not be negative")
        if length > MAX_BODY:
            self.close_connection = True
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "at most 256 KiB")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, "the body is not JSON")
        if not isinstance(body, dict) or not isinstance(body.get("pgn"), str):
            return self._error(HTTPStatus.BAD_REQUEST, "pgn must be a string")
        plies = body.get("plies")
        if plies is not None and not isinstance(plies, str):
            return self._error(HTTPStatus.BAD_REQUEST, "plies must be a string")
        detail = body.get("detail", False)  # DF-D §4.3: each ply's `analysis`
        if not isinstance(detail, bool):
            return self._error(HTTPStatus.BAD_REQUEST, "detail must be a boolean")
        try:
            status, done = self.server.jobs.submit(body["pgn"], plies or None, detail)
        except InputError as error:
            return self._error(HTTPStatus.BAD_REQUEST, str(error))
        except QueueFull as error:
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(error))
        self._json(HTTPStatus.OK if done else HTTPStatus.ACCEPTED, status)

    # -- answers ----------------------------------------------------------------------------

    def _viewer(self) -> bytes | None:
        try:
            return (self.server.viewer / "index.html").read_bytes()
        except OSError:
            return None

    def _json(self, code: HTTPStatus, value) -> None:
        data = json.dumps(value, ensure_ascii=False).encode()
        self._send(code, data, "application/json; charset=utf-8", "no-store")

    def _error(self, code: HTTPStatus, message: str) -> None:
        self._json(code, {"error": message})

    def _send(self, code: HTTPStatus, data: bytes, kind: str, cache: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        """One line per request: method, path, code; never a body (AS-D §6.3)."""

        log.info("%s %s", self.address_string(), format % args)


def serve(jobs: Jobs, viewer: Path, host: str = "127.0.0.1", port: int = 8765) -> Server:
    return Server((host, port), jobs, viewer)
