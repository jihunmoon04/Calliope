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
COMMENTARY_JOB = re.compile(r"^/api/games/([0-9a-f]{64})/commentary/job$")
COMMENTARY_CANCEL = re.compile(r"^/api/games/([0-9a-f]{64})/commentary/cancel$")
IMMUTABLE = "private, max-age=31536000, immutable"

log = logging.getLogger(__name__)


class CommentaryUnavailable(Exception):
    """AI commentary generation is not configured or cannot run (HTTP 503)."""


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, jobs: Jobs, viewer: Path, commentary_jobs=None) -> None:
        self.jobs = jobs
        self.viewer = viewer
        self.commentary_jobs = commentary_jobs
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
                    records, played, _ = self._commentary(match[1])
                except InputError:  # as the commentary route (AG2 re-review B2)
                    return self._error(HTTPStatus.CONFLICT, "the job's game cannot be read")
                combined = with_commentary(json.loads(body), records, played)
                return self._json(HTTPStatus.OK, combined)
            return self._send(HTTPStatus.OK, body, "application/json", IMMUTABLE)
        if match := COMMENTARY_JOB.match(path):
            if jobs.status(match[1]) is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            cjobs = self.server.commentary_jobs
            if cjobs is None:
                return self._json(
                    HTTPStatus.OK,
                    {
                        "state": "idle",
                        "available": False,
                        "model": None,
                        "reason": "AI 해설 생성기가 활성화되지 않았습니다.",
                    },
                )
            return self._json(HTTPStatus.OK, cjobs.status(match[1]))
        if match := COMMENTARY.match(path):
            if jobs.status(match[1]) is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            try:
                records, played, start_fen = self._commentary(match[1])
            except InputError:  # a damaged job keeps no game to key its commentary by
                return self._error(HTTPStatus.CONFLICT, "the job's game cannot be read")
            body = jobs.result(match[1])
            document = json.loads(body) if body is not None else None
            return self._json(HTTPStatus.OK, listing(records, played, document, start_fen))
        return self._error(HTTPStatus.NOT_FOUND, "not found")

    def _commentary(self, jid: str) -> tuple[list[dict], list[str], str]:
        """The game's accepted commentaries (newest first), its played moves and its start."""

        jobs = self.server.jobs
        parsed = parse_game(jobs.pgn(jid))
        store = CommentaryStore(jobs.data / "commentary")
        return store.for_game(game_key(parsed.game)), list(parsed.uci), parsed.game.start_fen

    def _drain_unread_body(self) -> None:
        """Drain bounded unread request bytes before closing so Windows does not send TCP RST."""

        headers = getattr(self, "headers", None)
        if headers is None or getattr(self, "_body_consumed", False):
            return
        try:
            length = int(headers.get("Content-Length", "0"))
        except ValueError:
            return
        if length <= 0:
            return
        remaining = min(length, 512 * 1024)
        self.connection.settimeout(0.05)
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def finish(self) -> None:
        if getattr(self, "close_connection", False):
            try:
                self.wfile.flush()
            except OSError:
                pass
            self._drain_unread_body()
        super().finish()

    def _read_json_object(self, *, allow_empty: bool = False) -> dict | None:
        kind = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if kind != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send application/json")
            return None
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._error(HTTPStatus.LENGTH_REQUIRED, "Content-Length is required")
            return None
        if length < 0:
            self._error(HTTPStatus.BAD_REQUEST, "Content-Length must not be negative")
            return None
        if length > MAX_BODY:
            self.close_connection = True
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "at most 256 KiB")
            return None
        if length == 0 and allow_empty:
            self._body_consumed = True
            return {}
        try:
            raw = self.rfile.read(length)
            self._body_consumed = True
            body = json.loads(raw)
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "the body is not JSON")
            return None
        if not isinstance(body, dict):
            self._error(HTTPStatus.BAD_REQUEST, "the body must be a JSON object")
            return None
        return body

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/games":
            body = self._read_json_object()
            if body is None:
                return
            if not isinstance(body.get("pgn"), str):
                return self._error(HTTPStatus.BAD_REQUEST, "pgn must be a string")
            plies = body.get("plies")
            if plies is not None and not isinstance(plies, str):
                return self._error(HTTPStatus.BAD_REQUEST, "plies must be a string")
            detail = body.get("detail", False)  # DF-D §4.3: each ply's `analysis`
            if not isinstance(detail, bool):
                return self._error(HTTPStatus.BAD_REQUEST, "detail must be a boolean")
            try:  # RV-1 P3-2: a lone surrogate cannot be stored or hashed
                body["pgn"].encode("utf-8")
                (plies or "").encode("utf-8")
            except (UnicodeEncodeError, AttributeError):
                return self._error(HTTPStatus.BAD_REQUEST, "pgn and plies must be valid Unicode text")
            try:
                status, done = self.server.jobs.submit(body["pgn"], plies or None, detail)
            except InputError as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            except QueueFull as error:
                return self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(error))
            return self._json(HTTPStatus.OK if done else HTTPStatus.ACCEPTED, status)
        if match := COMMENTARY.match(path):
            body = self._read_json_object(allow_empty=True)
            if body is None:
                return
            jid = match[1]
            status = self.server.jobs.status(jid)
            if status is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            if status["state"] != "done" or self.server.jobs.result(jid) is None:
                return self._error(
                    HTTPStatus.CONFLICT, "분석이 완료된 대국만 AI 해설을 생성할 수 있습니다."
                )
            if not self.server.jobs.matches_current(jid):
                return self._error(
                    HTTPStatus.CONFLICT,
                    "이 대국의 분석은 현재 엔진 또는 빌드 기준과 다릅니다. 대국을 다시 분석한 뒤 AI 해설을 생성하세요.",
                )
            try:
                parse_game(self.server.jobs.pgn(jid))
            except InputError:
                return self._error(HTTPStatus.CONFLICT, "the job's game cannot be read")
            cjobs = self.server.commentary_jobs
            if cjobs is None:
                return self._error(
                    HTTPStatus.SERVICE_UNAVAILABLE, "AI 해설 생성기가 활성화되지 않았습니다."
                )
            plies_info = status.get("plies") or {}
            first = plies_info.get("first")
            last = plies_info.get("last")
            ply_range = (first, last) if isinstance(first, int) and isinstance(last, int) and first > 0 else None
            try:
                cstatus, active = cjobs.start(jid, self.server.jobs.pgn(jid), ply_range)
            except (CommentaryUnavailable, QueueFull) as error:
                return self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(error))
            return self._json(HTTPStatus.OK if active else HTTPStatus.ACCEPTED, cstatus)
        if match := COMMENTARY_CANCEL.match(path):
            body = self._read_json_object(allow_empty=True)
            if body is None:
                return
            jid = match[1]
            if self.server.jobs.status(jid) is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such game")
            cjobs = self.server.commentary_jobs
            if cjobs is None:
                return self._error(
                    HTTPStatus.SERVICE_UNAVAILABLE, "AI 해설 생성기가 활성화되지 않았습니다."
                )
            return self._json(HTTPStatus.OK, cjobs.cancel(jid))
        return self._error(HTTPStatus.NOT_FOUND, "not found")

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


def serve(
    jobs: Jobs, viewer: Path, host: str = "127.0.0.1", port: int = 8765, commentary_jobs=None
) -> Server:
    return Server((host, port), jobs, viewer, commentary_jobs=commentary_jobs)
