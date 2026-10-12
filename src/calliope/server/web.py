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

from calliope.server.jobs import Jobs, QueueFull
from calliope.server.pipeline import InputError

MAX_BODY = 256 * 1024
GAME = re.compile(r"^/api/games/([0-9a-f]{64})$")
RESULT = re.compile(r"^/api/games/([0-9a-f]{64})/result$")
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
        path = self.path.split("?", 1)[0]
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
            return self._send(HTTPStatus.OK, body, "application/json", IMMUTABLE)
        return self._error(HTTPStatus.NOT_FOUND, "not found")

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
        try:
            status, done = self.server.jobs.submit(body["pgn"], plies or None)
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
