"""`analyze_game`'s jobs (AG6-D §4): a game's plies analysed in the background of the server
process, one job at a time.

A job lives in the process; its results are the ply cache, so a process that restarts forgets its
jobs and a new job finds the finished plies there (§4.2). The worker reads the parsed game it was
given and writes only the ply cache, the job's state and the plies' summaries (§4.3): it never
takes the tool lock, and it takes the engine lock one ply at a time through the session's
`job_ply`. Its plies are charged to the job's own window and its searches to the job's own meter
(§4.4, §8), never to AG4-D's.

States (§4.2): `queued` → `running` ⇄ `waiting` (the hourly ply budget) → `done` (every ply analysed,
or the failed ones listed), `failed` (the engine failed twice on one ply), `cancelled`.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from calliope.reasoning import AnalysisFailed
from calliope.server import JobFailed, StoreFailed

from .budget import Meter, MeteredSlot, Window

ACTIVE = ("queued", "running", "waiting")
ENDED = ("done", "failed", "cancelled")
WAIT_LIMIT = 240  # seconds one `analyze_game` call waits at most (§4.1)


@dataclass
class Job:
    key: str  # the game key
    game: str  # the game id the job was asked with
    parsed: object  # ParsedGame
    plies: range
    slot: MeteredSlot
    state: str = "queued"
    done: int = 0  # plies finished: cached, analysed or failed
    cached: int = 0
    analysed: int = 0
    current: int | None = None
    finished: set[int] = field(default_factory=set)  # this job's plies, cached, analysed or failed
    failed_plies: list[dict] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)  # each analysed ply's
    resume_at: float | None = None  # while `waiting`
    error: str | None = None
    cancel: bool = False

    @property
    def total(self) -> int:
        return len(self.plies)


class GameJobs:
    """The job table and its single worker thread. `job_ply(job, ply)` is the session's: it answers
    `(cached, summary)` for one ply, under the engine lock when it analyses."""

    def __init__(
        self,
        limits,
        job_ply: Callable[[Job, int], tuple[bool, dict]],
        is_cached: Callable[[Job, int], bool],
        raw_slot,
        clock: Callable[[], float] = time.monotonic,  # the budget window's (tests inject one)
    ) -> None:
        self.limits = limits
        self.job_ply = job_ply
        self.is_cached = is_cached
        self.raw_slot = raw_slot
        self.clock = clock
        self.lock = threading.Condition()  # the job lock (§4.3): the table, every job's state
        self.jobs: dict[str, Job] = {}  # by game key: the latest job of each game
        self.queue: deque[str] = deque()
        self.window = Window(limits.max_job_plies_per_window, limits.job_window_seconds, clock)
        self.summaries: dict[str, dict[int, dict]] = {}  # by game key, by ply (§5 of AG6b)
        self._thread: threading.Thread | None = None
        self._stopping = False

    # -- the table ---------------------------------------------------------------------------

    def start(self, key: str, game: str, parsed, plies: range) -> Job:
        """The game's active job when it is the same range; else a new one, queued (§4.1)."""

        if len(plies) > self.limits.max_job_plies:
            raise JobRefused(f"a job analyses at most {self.limits.max_job_plies} plies, not "
                             f"{len(plies)}")  # fmt: skip
        with self.lock:
            job = self.jobs.get(key)
            if job is not None and job.state in ACTIVE:
                if job.plies == plies:
                    return job
                raise JobRefused(f"the game already has a job over plies {_text(job.plies)} "
                                 f"({job.state}); wait for it or cancel it")  # fmt: skip
            running = sum(1 for j in self.jobs.values() if j.state in ("running", "waiting"))
            if len(self.queue) >= self.limits.max_queued_jobs and running:
                raise JobRefused(f"{len(self.queue)} jobs are queued, the most there may be "
                                 f"({self.limits.max_queued_jobs}); try again when one ends")  # fmt: skip
            meter = Meter(Window(math.inf, self.limits.job_window_seconds, self.clock))
            job = Job(key, game, parsed, plies, MeteredSlot(self.raw_slot, meter))
            self.jobs[key] = job
            self.queue.append(key)
            self._ensure_worker()
            self.lock.notify_all()
            return job

    def cancel(self, key: str) -> Job | None:
        with self.lock:
            job = self.jobs.get(key)
            if job is None or job.state in ENDED:
                return job
            job.cancel = True
            if job.state == "queued":
                self.queue.remove(key)
                job.state = "cancelled"
            self.lock.notify_all()
            return job

    def wait(
        self, key: str, seconds: float, on_progress: Callable[[Job], None] | None = None
    ) -> Job:
        """Until the game's job ends or `seconds` pass (at most WAIT_LIMIT), through `waiting` too
        (review B8); `on_progress` is called whenever a ply is finished. No other lock is held."""

        deadline = time.monotonic() + min(
            max(seconds, 0), WAIT_LIMIT
        )  # real time, not the budget's
        with self.lock:
            job = self.jobs[key]
            seen = job.done
            while job.state in ACTIVE:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self.lock.wait(min(left, 1.0))
                if job.done != seen and on_progress is not None:
                    seen = job.done
                    self.lock.release()
                    try:
                        on_progress(job)
                    finally:
                        self.lock.acquire()
            return job

    def snapshot(self, key: str) -> dict | None:
        """The game's job as an answer shows it (§4.1)."""

        with self.lock:
            job = self.jobs.get(key)
            if job is None:
                return None
            out = {"state": job.state, "plies": _text(job.plies), "done": job.done,
                   "total": job.total, "cached": job.cached, "analysed": job.analysed,
                   "failed_plies": list(job.failed_plies)}  # fmt: skip
            if job.current is not None and job.state == "running":
                out["current"] = job.current
            if job.seconds:
                mean = sum(job.seconds) / len(job.seconds)
                out["seconds_per_ply"] = round(mean, 1)
                if job.state in ACTIVE:
                    out["seconds_left"] = round(mean * (job.total - job.done))
            if job.state == "waiting" and job.resume_at is not None:
                out["resume_after_seconds"] = max(math.ceil(job.resume_at - self.clock()), 1)
            if job.error is not None:
                out["error"] = job.error
            return out

    def pending(self, key: str) -> set[int]:
        """The plies an active job of the game has not finished yet."""

        with self.lock:
            job = self.jobs.get(key)
            if job is None or job.state not in ACTIVE:
                return set()
            return {p for p in job.plies if p not in job.finished}

    def failed(self, key: str) -> set[int]:
        with self.lock:
            job = self.jobs.get(key)
            return set() if job is None else {f["ply"] for f in job.failed_plies}

    def summary(self, key: str, ply: int) -> dict | None:
        with self.lock:
            return self.summaries.get(key, {}).get(ply)

    def keep_summary(self, key: str, ply: int, summary: dict) -> None:
        with self.lock:
            self.summaries.setdefault(key, {})[ply] = summary

    def stop(self, timeout: float | None = 5) -> None:
        with self.lock:
            self._stopping = True
            for job in self.jobs.values():
                if job.state in ACTIVE:
                    job.cancel = True
            self.lock.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)

    # -- the worker ----------------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._work, name="calliope-jobs", daemon=True)
            self._thread.start()

    def _work(self) -> None:
        while True:
            with self.lock:
                while not self.queue and not self._stopping:
                    self.lock.wait()
                if self._stopping:
                    for key in self.queue:
                        self.jobs[key].state = "cancelled"
                    self.queue.clear()
                    self.lock.notify_all()
                    return
                job = self.jobs[self.queue.popleft()]
                job.state = "running"
                self.lock.notify_all()
            try:
                self._run(job)
            except Exception as error:  # a defect: the job fails with it, the worker goes on
                logging.getLogger(__name__).exception("job of %s failed", job.game)
                self._end(job, "failed", f"{type(error).__name__}: {error}")

    def _run(self, job: Job) -> None:
        for ply in job.plies:
            if not self._admit(job, ply):
                return  # cancelled while it waited for budget
            with self.lock:
                job.current = ply
            started = time.monotonic()
            try:
                cached, summary = self.job_ply(job, ply)
            except JobFailed as error:
                if isinstance(error.__cause__, AnalysisFailed):
                    with self.lock:  # not the engine: the ply is listed and the job goes on
                        job.failed_plies.append({"ply": ply, "message": str(error)})
                        job.finished.add(ply)
                        job.done += 1
                        self.lock.notify_all()
                    continue
                self._end(job, "failed", str(error))  # the engine failed twice, or changed
                return
            except StoreFailed as error:
                self._end(job, "failed", f"ply {ply} could not be stored: {error}")
                return
            with self.lock:
                job.done += 1
                job.finished.add(ply)
                if cached:
                    job.cached += 1
                else:
                    job.analysed += 1
                    job.seconds.append(time.monotonic() - started)
                self.summaries.setdefault(job.key, {})[ply] = summary
                self.lock.notify_all()
        self._end(job, "done", None)

    def _admit(self, job: Job, ply: int) -> bool:
        """Before a ply: a cancel ends the job; an uncached ply needs room in the hourly window
        and waits for it (`waiting`, §4.2), charged as it is admitted; a cached ply is free."""

        while True:
            with self.lock:
                if job.cancel or self._stopping:
                    job.state, job.current = "cancelled", None
                    self.lock.notify_all()
                    return False
            if self.is_cached(job, ply):
                return True
            with self.lock:
                if self.window.left >= 1:
                    self.window.charge()
                    if job.state == "waiting":
                        job.state, job.resume_at = "running", None
                        self.lock.notify_all()
                    return True
                retry = self.window.retry_after(1) or 1
                job.state, job.resume_at = "waiting", self.clock() + retry
                self.lock.notify_all()
                self.lock.wait(min(retry, 5))  # a cancel or the stop wakes it sooner

    def _end(self, job: Job, state: str, error: str | None) -> None:
        with self.lock:
            job.state, job.error, job.current = state, error, None
            self.lock.notify_all()


class JobRefused(Exception):
    """A job `analyze_game` cannot start: too many plies, another range, the queue full."""


def _text(plies: range) -> str:
    return f"{plies.start}" if len(plies) == 1 else f"{plies.start}-{plies.stop - 1}"
