"""Jobs (AS-D §5): content-named, queued in memory, run one at a time, persisted on disk.

`<data>/games/<id>/` holds `job.json` (the PGN, the ply range, the environment, the creation
time), then `result.json` or `error.json`. Every file is written atomically. One lock covers
lookup, capacity, `job.json` and enqueueing, and every state change of the worker.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from calliope.facts import EngineProfile, EngineResultStore, PositionRecords
from calliope.results import dumps, schema_errors
from calliope.server.cache import MAX_LOADED, MAX_LOADED_MB, PlyCache, canonical
from calliope.server.files import atomic_write, read_or_none, remove_temporaries
from calliope.server.pipeline import (
    MAX_POSITION_RECORDS,
    MAX_STORE_SEARCHES,
    EngineSlot,
    InputError,
    JobFailed,
    ParsedGame,
    PlyProgress,
    analyse_game,
    build_of,
    parse_game,
    plies_range,
)

JOB_KEY_VERSION = "job_key_v1"
MAX_PLIES = 600
QUEUE_LIMIT = 20
ID_LENGTH = 64
DAMAGED = "the job file is damaged; post the game again"
ENVIRONMENT_CHANGED = (
    "the engine or the reasoning build changed since this game was posted; post it again"
)
GAME_FIELDS = (
    ("white", "white"),
    ("black", "black"),
    ("date", "date"),
    ("result", "result"),
    ("site", "site"),
)

log = logging.getLogger(__name__)


class QueueFull(Exception):
    """AS-D §5.2: at most `QUEUE_LIMIT` queued jobs (HTTP 503)."""


@dataclass
class Job:
    id: str
    created: str
    pgn: str = ""
    plies_text: str | None = None
    detail: bool = False  # DF-D §4.3: each ply carries its `analysis`
    environment: dict | None = None
    state: str = "queued"  # queued | running | done | failed
    error: str | None = None
    game: dict = field(default_factory=dict)
    first: int = 0
    last: int = 0
    done: int = 0
    cached: int = 0
    current: dict | None = None
    analysed_seconds: list[float] = field(default_factory=list)
    warnings: tuple[str, ...] = ()
    sans: tuple[str, ...] = ()


def environment(port, profile: EngineProfile) -> dict:
    """The parts of a job id that do not come from the PGN (AS-D §5.1, review B4)."""

    return {
        "engine": list(port.identity.fingerprint()),
        "profile": list(profile.fingerprint()),
        "build": build_of(port),
    }


def job_id(parsed: ParsedGame, plies: range, env: dict, detail: bool = False) -> str:
    game = parsed.game
    preimage = {
        "v": JOB_KEY_VERSION,
        "game": {
            "start_fen": game.start_fen,
            "moves": [m.uci for m in game.moves],
            "headers": dict(game.headers),
        },
        "plies": [plies.start, plies.stop - 1],
        "grading": asdict(parsed.spec),
        "profile": env["profile"],
        "engine": env["engine"],
        "build": env["build"],
    }
    if detail:  # only then, so a job without `analysis` keeps its id (DF-D §4.3)
        preimage["detail"] = True
    return hashlib.sha256(canonical(preimage)).hexdigest()


def checked(pgn: str, plies_text: str | None) -> tuple[ParsedGame, range]:
    """The game and its ply range, or `InputError` (AS-D §6.3)."""

    parsed = parse_game(pgn)
    count = len(parsed.sans)
    if count == 0:
        raise InputError("the game has no moves")
    if count > MAX_PLIES:
        raise InputError(f"the game has {count} plies; at most {MAX_PLIES} are analysed")
    plies = plies_range(plies_text, count)
    if not plies or plies.start < 1:
        raise InputError(f"the ply range {plies_text!r} is outside the game's {count} plies")
    return parsed, plies


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summary_game(parsed: ParsedGame) -> dict:
    headers = parsed.game.headers
    return {key: headers[src] for key, src in GAME_FIELDS if src in headers}


Analyse = Callable[..., dict]


class Jobs:
    """The job table and its single worker thread."""

    def __init__(
        self,
        data: Path,
        slot: EngineSlot,
        *,
        profile: EngineProfile | None = None,
        analyse: Analyse = analyse_game,
        queue_limit: int = QUEUE_LIMIT,
        check: Callable[[bytes, ParsedGame, range, dict], bool] | None = None,
        verify_writes: bool = False,
        max_loaded: int = MAX_LOADED,
        max_loaded_mb: int = MAX_LOADED_MB,
        max_store_searches: int = MAX_STORE_SEARCHES,
        max_position_records: int = MAX_POSITION_RECORDS,
    ) -> None:
        self.data = data
        self.games = data / "games"
        self.cache = PlyCache(
            data / "plies",
            verify_writes=verify_writes,
            max_loaded=max_loaded,
            max_loaded_mb=max_loaded_mb,
        )  # fmt: skip (CC-D §2.3, §3.2)
        self.slot = slot
        # the process's searches and POSITION records, for every job (PF-D §2, §3)
        self.store = EngineResultStore(max_store_searches)
        self.memo = PositionRecords(max_position_records)
        self.profile = profile if profile is not None else EngineProfile()
        self.analyse = analyse
        self.queue_limit = queue_limit
        self.check = check if check is not None else result_matches  # tests replace both
        self.lock = threading.Condition()
        self.jobs: dict[str, Job] = {}
        self.queue: list[str] = []
        self.environment = environment(slot.port, self.profile)  # starts the engine (AS-D §5.2)
        self._thread: threading.Thread | None = None
        self._stopping = False

    # -- start-up ---------------------------------------------------------------------------

    def recover(self) -> None:
        """AS-D §5.2 start-up: remove temporaries, load every job, resume the sound unfinished
        ones whose environment is the current one, isolate the damaged ones."""

        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data.chmod(0o700)
        self.games.mkdir(exist_ok=True)
        removed = remove_temporaries(self.data)
        if removed:
            log.info("removed %d left-over temporary files", removed)
        found = []
        for folder in sorted(p for p in self.games.iterdir() if p.is_dir()):
            if len(folder.name) != ID_LENGTH:
                continue
            found.append(self._load(folder))
        with self.lock:
            for job in sorted(found, key=lambda j: j.created):
                self.jobs[job.id] = job
                if job.state == "queued":
                    self.queue.append(job.id)
            self.lock.notify_all()

    def _load(self, folder: Path) -> Job:
        job = Job(folder.name, created="")
        raw = read_or_none(folder / "job.json")
        try:
            record = json.loads(raw) if raw is not None else None
            pgn, plies_text = record["pgn"], record["plies"]
            env, created = record["environment"], record["created"]
            detail = record.get("detail", False)
            if not (
                isinstance(detail, bool)
                and isinstance(pgn, str)
                and isinstance(created, str)
                and isinstance(env, dict)
                and (plies_text is None or isinstance(plies_text, str))
            ):
                raise TypeError("a field has the wrong type")
        except (TypeError, KeyError, ValueError) as error:
            log.warning("job %s: damaged job.json (%s)", folder.name, error)
            job.state, job.error = "failed", DAMAGED
            self._write_error(job, DAMAGED)
            return job
        job.pgn, job.plies_text, job.environment, job.created = pgn, plies_text, env, created
        job.detail = detail
        try:
            parsed, plies = checked(pgn, plies_text)
            named = job_id(parsed, plies, env, detail) == folder.name  # AS1 review B2
        except (InputError, KeyError, TypeError) as error:
            log.warning("job %s: damaged job.json (%s)", folder.name, error)
            job.state, job.error = "failed", DAMAGED
            self._write_error(job, DAMAGED)
            return job
        if not named:
            log.warning("job %s: job.json does not hash to its directory's name", folder.name)
            job.state, job.error = "failed", DAMAGED
            self._write_error(job, DAMAGED)
            return job
        job.game, job.first, job.last = _summary_game(parsed), plies.start, plies.stop - 1
        job.warnings = parsed.warnings
        result = read_or_none(folder / "result.json")
        if result is not None:
            if self._matches(result, parsed, plies, env, job.detail):
                job.state, job.done = "done", plies.stop - plies.start
                return job
            log.warning("job %s: result.json is not this job's result; resumed", folder.name)
        error_bytes = read_or_none(folder / "error.json")
        if error_bytes is not None:
            job.state = "failed"
            try:
                job.error = str(json.loads(error_bytes)["message"])
            except (ValueError, KeyError, TypeError):
                job.error = DAMAGED
            return job
        if env != self.environment:
            job.state, job.error = "failed", ENVIRONMENT_CHANGED
            self._write_error(job, ENVIRONMENT_CHANGED)
            return job
        job.state = "queued"
        return job

    def _matches(self, data: bytes, parsed, plies: range, env: dict, detail: bool) -> bool:
        """The result check with the job's `detail`; a replaced check (tests) without it."""

        if self.check is result_matches:
            return result_matches(data, parsed, plies, env, detail)
        return self.check(data, parsed, plies, env)

    # -- requests ---------------------------------------------------------------------------

    def submit(self, pgn: str, plies_text: str | None, detail: bool = False) -> tuple[dict, bool]:
        """Post a game: its status and whether it is already done. `InputError`, `QueueFull`.
        `detail` asks for each ply's `analysis` (DF-D §4.3); it is part of the job's id."""

        parsed, plies = checked(pgn, plies_text)  # parsed and named before the lock
        jid = job_id(parsed, plies, self.environment, detail)
        with self.lock:
            job = self.jobs.get(jid)
            if job is not None and job.state != "failed":
                return self._status(job), job.state == "done"
            if len(self.queue) >= self.queue_limit:
                raise QueueFull(f"{len(self.queue)} games are already queued")
            folder = self.games / jid
            if job is None:
                job = Job(
                    jid,
                    created=_now(),
                    pgn=pgn,
                    plies_text=plies_text,
                    detail=detail,
                    environment=self.environment,
                )
                job.game, job.first, job.last = _summary_game(parsed), plies.start, plies.stop - 1
                job.warnings = parsed.warnings
                record = {
                    "pgn": pgn,
                    "plies": plies_text,
                    "environment": self.environment,
                    "created": job.created,
                }
                if detail:
                    record["detail"] = True
                atomic_write(folder / "job.json", canonical(record))
            else:  # a failed job, posted again in the same environment: queued again
                (folder / "error.json").unlink(missing_ok=True)
                job.detail = detail  # the id names it (DF1 review B3)
                if job.error == DAMAGED or job.pgn != pgn:
                    record = {
                        "pgn": pgn,
                        "plies": plies_text,
                        "environment": self.environment,
                        "created": job.created or _now(),
                    }
                    if detail:
                        record["detail"] = True
                    atomic_write(folder / "job.json", canonical(record))
                    job.pgn, job.plies_text, job.environment = pgn, plies_text, self.environment
                    job.created = record["created"]
                    job.game, job.first, job.last = (
                        _summary_game(parsed),
                        plies.start,
                        plies.stop - 1,
                    )
                    job.warnings = parsed.warnings
                job.error, job.done, job.cached, job.current = None, 0, 0, None
                job.analysed_seconds = []
                job.state = "queued"
            self.jobs[jid] = job
            self.queue.append(jid)
            self.lock.notify_all()
            return self._status(job), False

    def status(self, jid: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(jid)
            return None if job is None else self._status(job)

    def summaries(self) -> list[dict]:
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)
            keys = ("id", "state", "created", "game", "plies")
            return [{k: v for k, v in self._status(j).items() if k in keys} for j in jobs]

    def pgn(self, jid: str) -> str:
        """The PGN a job was posted with (AG-D §8: its game key)."""

        with self.lock:
            return self.jobs[jid].pgn

    def result(self, jid: str) -> bytes | None:
        """The result bytes of a done job, else None."""

        with self.lock:
            job = self.jobs.get(jid)
            if job is None or job.state != "done":
                return None
        return read_or_none(self.games / jid / "result.json")

    def _status(self, job: Job) -> dict:
        total = job.last - job.first + 1 if job.last else 0
        status = {
            "id": job.id,
            "state": job.state,
            "created": job.created,
            "game": dict(job.game),
            "plies": {
                "first": job.first,
                "last": job.last,
                "total": total,
                "done": job.done,
                "cached": job.cached,
            },
            "warnings": list(job.warnings),
        }
        if job.state == "running" and job.current is not None:
            status["current"] = dict(job.current)
        if job.state == "queued" and job.id in self.queue:
            status["queue_position"] = self.queue.index(job.id) + 1
        if job.state == "running" and job.analysed_seconds:
            mean = sum(job.analysed_seconds) / len(job.analysed_seconds)
            status["eta_seconds"] = round(mean * (total - job.done))
        if job.state == "failed":
            status["error"] = job.error or "failed"
        return status

    # -- the worker -------------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._work, name="calliope-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        with self.lock:
            self._stopping = True
            self.lock.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)

    def run_next(self) -> bool:
        """Run the first queued job to its end (the worker's step; tests call it directly)."""

        with self.lock:
            if not self.queue:
                return False
            job = self.jobs[self.queue.pop(0)]
            job.state = "running"
            pgn, plies_text, detail = job.pgn, job.plies_text, job.detail
        try:
            parsed, plies = checked(pgn, plies_text)
            self._check_environment(job)  # AS1 review B1
            with self.lock:
                job.sans = parsed.sans
                job.current = {"ply": plies.start, "san": parsed.sans[plies.start - 1]}
            document = self.analyse(
                self.slot,
                parsed,
                plies,
                self.cache,
                profile=self.profile,
                engine=job.environment["engine"],  # the job's engine, never just the current one
                on_ply=lambda p: self._progress(job, p),
                store=self.store,
                memo=self.memo,
                **({"detail": True} if detail else {}),
            )
            data = dumps(document)
            if not self._matches(data, parsed, plies, job.environment, detail):  # one rule for both
                raise JobFailed("the result does not pass its own check (schema, job)")
            atomic_write(self.games / job.id / "result.json", data)
        except Exception as error:  # every failure ends the job, never the worker
            self.slot.close()  # the next job starts a fresh engine (AS1 review B1)
            message = (
                str(error)
                if isinstance(error, JobFailed | InputError)
                else (f"{type(error).__name__}: {error}")
            )
            if not isinstance(error, JobFailed | InputError):
                log.exception("job %s failed", job.id)
            with self.lock:
                job.state, job.error, job.current = "failed", message, None
                self._write_error(job, message)
            return True
        with self.lock:
            job.state, job.current = "done", None
            job.done = job.last - job.first + 1
        return True

    def _check_environment(self, job: Job) -> None:
        """The engine, profile and build now must be the job's (AS1 review B1). When a restart
        brought another engine, the server's environment follows it, so a new POST gets an id
        that names it, and every job of the old environment fails instead of running."""

        current = environment(self.slot.port, self.profile)
        with self.lock:
            if current != self.environment:
                log.warning("the engine or the build changed; new jobs use the new environment")
                self.environment = current
        if job.environment != current:
            raise JobFailed(ENVIRONMENT_CHANGED)

    def _progress(self, job: Job, progress: PlyProgress) -> None:
        with self.lock:
            job.done += 1
            if progress.cached:
                job.cached += 1
            else:
                job.analysed_seconds.append(progress.seconds)
            nxt = progress.ply + 1
            job.current = {"ply": nxt, "san": job.sans[nxt - 1]} if nxt <= job.last else None

    def _work(self) -> None:
        while True:
            with self.lock:
                while not self.queue and not self._stopping:
                    self.lock.wait()
                if self._stopping:
                    return
            self.run_next()

    def _write_error(self, job: Job, message: str) -> None:
        try:
            atomic_write(
                self.games / job.id / "error.json", canonical({"message": message, "at": _now()})
            )
        except OSError:
            log.warning("job %s: error.json could not be written", job.id)


def result_matches(
    data: bytes, parsed: ParsedGame, plies: range, env: dict, detail: bool = False
) -> bool:
    """`result.json` is a valid `calliope_result_v1` (the shipped schema, AS1 re-review B3) and
    this job's (AS1 review B3): the build, the engine and profile, the game, the plies, every
    bundle stored — and every ply carries an `analysis` exactly when the job asked for it
    (DF1 review B2)."""

    try:
        doc = json.loads(data)
        if schema_errors(doc):  # the whole shipped schema first (AS1 re-review B3)
            return False
        provenance, game = doc["provenance"], doc["game"]
        engine = provenance["engine"]
        profile = [f"{name}={value}" for name, value in engine["profile"].items()]
        return (
            doc["schema"] == "calliope_result_v1"
            and provenance["build_digest"] == env["build"]
            and f"name={engine['name']}" in env["engine"]
            and f"sha256={engine['binary_sha256']}" in env["engine"]
            and profile == env["profile"]
            and game["start_fen"] == parsed.game.start_fen
            and [m["uci"] for m in game["moves"]] == [m.uci for m in parsed.game.moves]
            and game["headers"] == dict(parsed.game.headers)
            and [p["ply"] for p in doc["plies"]] == list(plies)
            and all(p["bundle"]["stored"] is True for p in doc["plies"])
            and all(isinstance(p.get("analysis"), dict) is detail for p in doc["plies"])
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def wait_until(predicate: Callable[[], bool], timeout: float = 30.0) -> bool:
    """Poll `predicate` (tests and the gated end-to-end run)."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()
