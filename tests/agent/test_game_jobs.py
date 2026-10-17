"""AG6-D §4.2 and re-review B8 for `GameJobs` alone: every row of the state table, the waits, the
queue and its limits — over a fake per-ply path and a fake clock for the hourly window."""

from __future__ import annotations

import threading
import time

import pytest

from calliope.agent import Limits
from calliope.agent.jobs import ENDED, GameJobs, JobRefused
from calliope.reasoning import AnalysisFailed
from calliope.server import JobFailed


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Plies:
    """A fake per-ply path: plies in `cached` are hits; `fail` maps a ply to the error it raises
    (once); `gate`, when set, holds every ply until it opens."""

    def __init__(self, cached=(), fail=None) -> None:
        self.cached = set(cached)
        self.fail = dict(fail or {})
        self.calls: list[int] = []
        self.gate: threading.Event | None = None
        self.hit_late: set[int] = set()  # cached by a tool after the worker's first look
        self.jobs: GameJobs | None = None

    def job_ply(self, job, ply):
        if self.gate is not None:
            assert self.gate.wait(5)
        self.calls.append(ply)
        if ply in self.fail:
            raise self.fail.pop(ply)
        hit = ply in self.cached or ply in self.hit_late
        if not hit:
            self.jobs.charge()  # as the session's path: only an analysis is charged (N1)
        self.cached.add(ply)  # analysed now: cached for any later job
        return hit, {"ply": ply}

    def is_cached(self, job, ply):
        return ply in self.cached


def _jobs(plies: Plies, clock=None, **limits) -> GameJobs:
    plies.jobs = GameJobs(Limits(**limits), plies.job_ply, plies.is_cached, raw_slot=None,
                          clock=clock or Clock())  # fmt: skip
    return plies.jobs


def _until(jobs: GameJobs, key: str, states, seconds: float = 5) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        snap = jobs.snapshot(key)
        if snap is not None and snap["state"] in states:
            return snap
        time.sleep(0.01)
    raise AssertionError(f"the job did not reach {states}: {jobs.snapshot(key)}")


def _engine_failure() -> JobFailed:
    return JobFailed("ply 3: the engine failed twice: the engine process exited")


def _analysis_failure(ply: int) -> JobFailed:
    try:
        raise AnalysisFailed("round 0 could not build the base tree")
    except AnalysisFailed as cause:
        error = JobFailed(f"ply {ply}: round 0 could not build the base tree")
        error.__cause__ = cause
        return error


def test_a_job_runs_its_plies_in_order_counting_the_cached(tmp_path) -> None:
    plies = Plies(cached={1, 3})
    jobs = _jobs(plies)
    try:
        jobs.start("k", "g-1", None, range(1, 6))
        snap = _until(jobs, "k", ENDED)
        assert snap["state"] == "done" and plies.calls == [1, 2, 3, 4, 5]
        assert (snap["done"], snap["total"], snap["cached"], snap["analysed"]) == (5, 5, 2, 3)
        assert snap["failed_plies"] == [] and "seconds_per_ply" in snap
        assert jobs.window.used == 3  # the uncached plies only, charged to the job's window
        assert [jobs.summary("k", p) for p in (1, 5)] == [{"ply": 1}, {"ply": 5}]
    finally:
        jobs.stop()


def test_the_same_range_is_the_same_job_and_another_is_refused() -> None:
    plies = Plies()
    plies.gate = threading.Event()
    jobs = _jobs(plies)
    try:
        first = jobs.start("k", "g-1", None, range(1, 4))
        assert jobs.start("k", "g-1", None, range(1, 4)) is first
        with pytest.raises(JobRefused, match="already has a job over plies 1-3"):
            jobs.start("k", "g-1", None, range(2, 4))
        with pytest.raises(JobRefused, match="at most 600 plies, not 601"):
            jobs.start("other", "g-2", None, range(1, 602))
        plies.gate.set()
        _until(jobs, "k", ENDED)
        again = jobs.start("k", "g-1", None, range(2, 4))  # a job that ended is replaced
        assert again is not first
        _until(jobs, "k", ENDED)
    finally:
        plies.gate.set()
        jobs.stop()


def test_the_queue_holds_its_limit() -> None:
    plies = Plies()
    plies.gate = threading.Event()
    jobs = _jobs(plies, max_queued_jobs=1)
    try:
        jobs.start("a", "g-a", None, range(1, 2))
        _until(jobs, "a", ("running",))
        jobs.start("b", "g-b", None, range(1, 2))  # queued behind a
        with pytest.raises(JobRefused, match="1 jobs are queued"):
            jobs.start("c", "g-c", None, range(1, 2))
        plies.gate.set()
        assert _until(jobs, "b", ENDED)["state"] == "done"
    finally:
        plies.gate.set()
        jobs.stop()


def test_a_ply_that_fails_without_the_engine_is_listed_and_the_job_goes_on() -> None:
    plies = Plies(fail={2: _analysis_failure(2)})
    jobs = _jobs(plies)
    try:
        jobs.start("k", "g-1", None, range(1, 4))
        snap = _until(jobs, "k", ENDED)
        assert snap["state"] == "done" and plies.calls == [1, 2, 3]
        assert [f["ply"] for f in snap["failed_plies"]] == [2] and jobs.failed("k") == {2}
        assert snap["done"] == 3 and snap["analysed"] == 2
    finally:
        jobs.stop()


def test_the_engine_failing_twice_fails_the_job_and_a_new_job_reuses_the_cache() -> None:
    plies = Plies(fail={3: _engine_failure()})
    jobs = _jobs(plies)
    try:
        jobs.start("k", "g-1", None, range(1, 6))
        snap = _until(jobs, "k", ENDED)
        assert snap["state"] == "failed" and "engine failed twice" in snap["error"]
        assert plies.calls == [1, 2, 3]
        jobs.start("k", "g-1", None, range(1, 6))  # after an end: a new job
        snap = _until(jobs, "k", ENDED)
        assert snap["state"] == "done" and snap["cached"] == 2 and snap["analysed"] == 3
    finally:
        jobs.stop()


def test_the_hourly_limit_waits_and_resumes_by_itself() -> None:
    clock = Clock()
    plies = Plies()
    jobs = _jobs(plies, clock, max_job_plies_per_window=2, job_window_seconds=600)
    try:
        jobs.start("k", "g-1", None, range(1, 5))
        snap = _until(jobs, "k", ("waiting",))
        assert snap["done"] == 2 and snap["resume_after_seconds"] == 600
        assert jobs.pending("k") == {3, 4}
        clock.now += 600  # the window's charges expire
        with jobs.lock:
            jobs.lock.notify_all()
        snap = _until(jobs, "k", ENDED)
        assert snap["state"] == "done" and plies.calls == [1, 2, 3, 4]
    finally:
        jobs.stop()


@pytest.mark.parametrize("where", ["queued", "running", "waiting"])
def test_cancel_from_each_active_state(where) -> None:
    clock = Clock()
    plies = Plies()
    limits = {"max_job_plies_per_window": 1} if where == "waiting" else {}
    jobs = _jobs(plies, clock, **limits)
    plies.gate = threading.Event()
    if where == "waiting":
        plies.gate.set()
    try:
        if where == "queued":
            jobs.start("first", "g-0", None, range(1, 2))
            _until(jobs, "first", ("running",))
        jobs.start("k", "g-1", None, range(1, 4))
        _until(jobs, "k", (where,))
        jobs.cancel("k")
        plies.gate.set()
        assert _until(jobs, "k", ENDED)["state"] == "cancelled"
        if where == "running":
            assert plies.calls == [1]  # the ply in progress finished; no other started
    finally:
        plies.gate.set()
        jobs.stop()


def test_a_wait_holds_through_waiting_and_reports_progress() -> None:
    """Re-review B8: a wait does not return early because the job waits for budget."""

    clock = Clock()
    plies = Plies()
    jobs = _jobs(plies, clock, max_job_plies_per_window=1)
    seen = []
    try:
        jobs.start("k", "g-1", None, range(1, 3))
        started = time.monotonic()
        job = jobs.wait("k", 0.6, on_progress=lambda done, total, message: seen.append(message))
        assert job.state == "waiting" and time.monotonic() - started >= 0.6
        every = [e[2] for e in job.events]
        assert every == ["running", "ply 1", "waiting 3600 s for the job budget"]
        assert seen == every[len(every) - len(seen) :]  # the wait's events: a suffix, none missed
        clock.now += 3600
        with jobs.lock:
            jobs.lock.notify_all()
        assert jobs.wait("k", 5).state == "done"
    finally:
        jobs.stop()


def test_stop_cancels_what_is_active() -> None:
    plies = Plies()
    plies.gate = threading.Event()
    jobs = _jobs(plies)
    jobs.start("a", "g-a", None, range(1, 3))
    jobs.start("b", "g-b", None, range(1, 3))
    _until(jobs, "a", ("running",))
    plies.gate.set()
    jobs.stop()
    assert {jobs.snapshot(k)["state"] for k in ("a", "b")} <= {"cancelled", "done"}
    assert jobs.snapshot("b")["state"] == "cancelled"


def test_every_ply_and_every_change_of_state_is_reported_in_order() -> None:
    """Review N2: plies that finish between two wake-ups are each reported, and so is waiting."""

    clock = Clock()
    plies = Plies()
    jobs = _jobs(plies, clock, max_job_plies_per_window=3)
    events = []
    try:
        jobs.start("k", "g-1", None, range(1, 7))
        _until(jobs, "k", ("waiting",))  # three plies, then the window is full
        clock.now += 3600
        with jobs.lock:
            jobs.lock.notify_all()
        jobs.wait("k", 0)  # no wait: the events stay for the next caller
        jobs2 = jobs.jobs["k"]
        assert [e[2] for e in jobs2.events][:5] == ["running", "ply 1", "ply 2", "ply 3",
                                                    "waiting 3600 s for the job budget"]  # fmt: skip
        _until(jobs, "k", ENDED)
        jobs.jobs["k"].events.clear()
    finally:
        jobs.stop()
    plies = Plies()
    jobs = _jobs(plies)
    try:
        jobs.start("k", "g-1", None, range(1, 9))
        jobs.wait("k", 5, on_progress=lambda done, total, message: events.append((done, message)))
        assert [d for d, m in events if m.startswith("ply")] == list(range(1, 9))
        assert events[-1] == (8, "done")
    finally:
        jobs.stop()


def test_a_ply_cached_meanwhile_is_not_charged() -> None:
    """Review N1: the worker saw ply 2 uncached; a tool analysed it before the worker's analysis."""

    plies = Plies()
    plies.hit_late = {2}
    jobs = _jobs(plies)
    try:
        jobs.start("k", "g-1", None, range(1, 4))
        snap = _until(jobs, "k", ENDED)
        assert snap["cached"] == 1 and snap["analysed"] == 2 and jobs.window.used == 2
    finally:
        jobs.stop()


def test_a_job_budget_of_none_fails_the_job_at_its_first_uncached_ply() -> None:
    """Review B4: with `max_job_plies_per_window` 0 an uncached ply can never be analysed."""

    plies = Plies(cached={1, 2})
    jobs = _jobs(plies, max_job_plies_per_window=0)
    try:
        jobs.start("k", "g-1", None, range(1, 5))
        snap = _until(jobs, "k", ENDED)
        assert snap["state"] == "failed" and "max_job_plies_per_window is 0" in snap["error"]
        assert snap["done"] == 2 and plies.calls == [1, 2]
        jobs.start("c", "g-c", None, range(1, 3))  # every ply cached: it runs
        assert _until(jobs, "c", ENDED)["state"] == "done"
    finally:
        jobs.stop()


def test_a_cancel_during_the_last_ply_ends_cancelled() -> None:
    """Review B1: the last ply finishing does not turn a cancel into a finish."""

    plies = Plies()
    plies.gate = threading.Event()
    jobs = _jobs(plies)
    try:
        jobs.start("k", "g-1", None, range(1, 2))
        _until(jobs, "k", ("running",))
        jobs.cancel("k")
        plies.gate.set()
        assert _until(jobs, "k", ENDED)["state"] == "cancelled"
    finally:
        plies.gate.set()
        jobs.stop()


def test_stop_waits_for_the_worker_and_says_whether_it_ended() -> None:
    plies = Plies()
    plies.gate = threading.Event()
    jobs = _jobs(plies)
    jobs.start("k", "g-1", None, range(1, 3))
    _until(jobs, "k", ("running",))
    assert jobs.stop(timeout=0.2) is False  # the ply in progress holds it
    plies.gate.set()
    assert jobs.stop(timeout=5) is True
