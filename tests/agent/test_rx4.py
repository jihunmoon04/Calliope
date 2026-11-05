"""RX4-D (agent-rx4-design.md): the lesson arms and their bases (§3.2; review N2, re-review C1), the
lesson set's rendering (§2.4, re-review N5), screening runs keyed by candidate (§2.3, re-review N4), the
bundle's part size (§4) and the batch's interleaving (§3.2, review N1); RX4a part 1's review: a set's status
against the run (B1), parts by commentaries (B2), `request_fetched` paired by moment (N1), the versions a set
was written for (N2)."""

from __future__ import annotations

import contextlib
import json

import anyio
import pytest
from agent_helpers import GAME

from tools.rx import lessons as lesson_sets
from tools.rx import run as rx_run

SOURCE_MARK = "SRC-MARK-7f3a"
VERSION_MARK = "VER-MARK-91c2"


def _lesson(lesson_id: str, **extra) -> dict:
    return {"id": lesson_id,
            "condition": "수의 등급이 엔진 줄의 기물 수지로 설명되지 않을 때",
            "action": ["그 수부터 실제 진행을 explore로 둔다"],
            "success": "그 진행이 무엇으로 이어졌는지 말한다",
            "fallback": "보여 주지 못하면 결론 없이 사실만 말한다",
            "versions": {"tools": VERSION_MARK, "guide": "commentary_ko_v8"},
            "source": [f"{SOURCE_MARK}:31"]} | extra  # fmt: skip


BUILD = "b" * 64


def _set(tmp_path, lessons, status="APPROVED", name="lessons_t", guide="commentary_ko_v8", **extra):
    """A set file; each lesson's versions are the set's (re-review N3) unless `raw` is passed."""

    raw = extra.pop("raw", False)
    versions = {"tools": VERSION_MARK, "guide": guide, "build_id": BUILD}
    if not raw:
        lessons = [
            x | {"versions": {k: versions[k] for k in x.get("versions") or {}}} for x in lessons
        ]
    path = tmp_path / f"{name}.json"
    doc = {"id": name, "status": status, "lessons": lessons, "versions": versions}
    if status in lesson_sets.APPROVED:
        doc["approval"] = {"by": "owner", "date": "2026-11-06"}
    path.write_text(json.dumps(doc | extra, ensure_ascii=False), encoding="utf-8")
    return path


def _base(tmp_path, build_id=BUILD):
    base = tmp_path / "base"
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "base.json").write_text(json.dumps({"files": {}, "build": {"build_id": build_id}}))
    return base


REFUSED = json.dumps({"accepted": False, "violations": [{"code": "cite_missing", "sentence": 1}]})


def test_each_lesson_arm_inherits_its_base_and_only_its_base() -> None:
    """Re-review C1, review N2: the same refused answer gives B and D the same retry message, and
    A-min and D-min none (D-min is A-min with lessons, RX0-D §8); A has none either."""

    messages = {}
    for arm in rx_run.ARMS:
        retries: dict = {}
        out = rx_run.retry_feedback(
            arm, "submit_commentary", {"ply": 3}, REFUSED, False, retries, 3
        )
        messages[arm] = [rx_run.retry_message(s, p) for s, p, _ in out]
    assert messages["B"] == messages["D"] and len(messages["B"]) == 1
    assert "ply 3" in messages["B"][0] and "cite_missing" in messages["B"][0]
    assert messages["A"] == messages["A-min"] == messages["D-min"] == []
    # the bound on retries holds for D as for B
    retries = {}
    for _ in range(5):
        rx_run.retry_feedback("D", "submit_commentary", {"ply": 3}, REFUSED, False, retries, 3)
    assert retries == {"ply 3": 3}
    assert rx_run.retry_feedback("D", "ply", {"ply": 3}, REFUSED, False, {}, 3) == []
    assert rx_run.retry_feedback("D", "submit_commentary", {"ply": 3}, REFUSED, True, {}, 3) == []


def _spec(tmp_path, arm, lessons_path=None, candidate=None, set_name="train"):
    if not (tmp_path / "base" / "base.json").exists():
        _base(tmp_path)
    return rx_run.RunSpec(arm=arm, set_name=set_name, game="g", pgn=GAME, moments=[3],
                          base=tmp_path / "base", records=tmp_path / "runs", work=tmp_path / "w",
                          lessons_path=lessons_path, candidate_id=candidate)  # fmt: skip


def test_only_the_strategy_reaches_the_prompt(tmp_path) -> None:
    """Re-review N5: `source` and `versions` (marked) never reach the rendered text; the four
    strategy fields do; only D's and D-min's prompts carry lessons."""

    two = [_lesson("L01"), _lesson("L02", condition="체크 뒤에 기물이 걸려 있을 때")]
    path = _set(tmp_path, two)
    for arm in ("D", "D-min"):
        guide = rx_run.guide_of(arm)
        text, info = rx_run.lessons(_spec(tmp_path, arm, _set(tmp_path, two, guide=guide)))
        assert SOURCE_MARK not in text and VERSION_MARK not in text
        assert "L01" not in text and "lessons_t" not in text
        lesson = _lesson("L01")
        for field in ("condition", "success", "fallback"):
            assert lesson[field] in text
        assert lesson["action"][0] in text
        assert info["rendered_fields"] == ["condition", "action", "success", "fallback"]
        assert info["lesson_ids"] == ["L01", "L02"] and info["lesson_set"] == "lessons_t"
        assert info["lesson_set_digest"] == lesson_sets.digest(text)
    for arm in ("A", "B", "A-min"):
        text, info = rx_run.lessons(_spec(tmp_path, arm))
        assert text == "" and info["lesson_ids"] == [] and info["rendered_fields"] == []
        assert info["lesson_set_digest"] == lesson_sets.digest("")
    with pytest.raises(ValueError, match="carries no lessons"):
        rx_run.lessons(_spec(tmp_path, "B", path))
    with pytest.raises(ValueError, match="needs a lesson set"):
        rx_run.lessons(_spec(tmp_path, "D"))


def test_a_screening_run_carries_one_candidate_alone(tmp_path) -> None:
    """Re-review N4, §2.3 step 2: D with a candidate carries that lesson alone and records its id;
    B in the pair records the same candidate with the digest of no lessons."""

    path = _set(
        tmp_path, [_lesson("L01"), _lesson("L02", success="다른 확인")], status="CANDIDATES"
    )
    text, info = rx_run.lessons(_spec(tmp_path, "D", path, "L02"))
    assert info["lesson_ids"] == ["L02"] and info["candidate_id"] == "L02"
    assert "다른 확인" in text and _lesson("L01")["success"] not in text
    _, b = rx_run.lessons(_spec(tmp_path, "B", None, "L02"))
    assert b["candidate_id"] == "L02" and b["lesson_set_digest"] == lesson_sets.digest("")
    with pytest.raises(ValueError, match="no lesson"):
        rx_run.lessons(_spec(tmp_path, "D", path, "L09"))


def test_a_lesson_set_is_refused_for_what_it_must_not_hold(tmp_path) -> None:
    """§2.2: a square or a numbered move, a missing field, more than 8 lessons (a candidates file may
    hold 12), a lesson too long, a repeated id."""

    fixed = {"tools": VERSION_MARK, "guide": "commentary_ko_v8"}
    assert lesson_sets.problems({"lessons": [_lesson("L01")], "versions": fixed}) == []
    square = _lesson("L01", condition="a5의 비숍이 걸려 있을 때")
    assert lesson_sets.problems({"lessons": [square]})
    move = _lesson("L01", action=["29...Bxa5를 둔다"])
    assert lesson_sets.problems({"lessons": [move]})
    assert lesson_sets.problems({"lessons": [_lesson("L01", fallback="")]})
    many = [_lesson(f"L{i:02d}") for i in range(1, 10)]
    assert any("at most 8" in p for p in lesson_sets.problems({"lessons": many}))
    assert lesson_sets.problems({"status": "CANDIDATES", "lessons": many, "versions": fixed}) == []
    long = _lesson("L01", success="가" * 400)
    assert any("characters" in p for p in lesson_sets.problems({"lessons": [long]}))
    assert lesson_sets.problems({"lessons": [_lesson("L01"), _lesson("L01")]})
    # material_* and grade names are not squares
    assert (
        lesson_sets.problems(
            {
                "lessons": [_lesson("L01", condition="material_gain이 inconclusive일 때")],
                "versions": fixed,
            }
        )
        == []
    )


def test_a_bad_lesson_set_stops_before_any_record(tmp_path, monkeypatch) -> None:
    _base(tmp_path)
    path = _set(tmp_path, [_lesson("L01", condition="e4의 폰이 걸려 있을 때")])
    with pytest.raises(ValueError, match="square"):
        anyio.run(rx_run.run_once, _spec(tmp_path, "D", path), "RUN-BAD")
    assert not (tmp_path / "runs" / "RUN-BAD").exists()


def test_the_start_line_records_the_lessons(tmp_path, monkeypatch) -> None:
    """§2.4, N4: the `start` line of a D run names the set, the lessons, the candidate, the fields
    rendered and the digest; the run then ends as RX1's runs do."""

    import mcp.client.stdio

    _base(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    @contextlib.asynccontextmanager
    async def broken(*args, **kwargs):
        raise ValueError("no server in this test")
        yield  # pragma: no cover

    monkeypatch.setattr(mcp.client.stdio, "stdio_client", broken)
    path = _set(tmp_path, [_lesson("L01"), _lesson("L02")], status="CANDIDATES")
    assert (
        anyio.run(rx_run.run_once, _spec(tmp_path, "D", path, "L01"), "RUN-D")["reason"] == "error"
    )
    start = json.loads(
        (tmp_path / "runs" / "RUN-D" / "agent.jsonl").read_text("utf-8").splitlines()[0]
    )
    assert start["arm"] == "D" and start["candidate_id"] == "L01" and start["lesson_ids"] == ["L01"]
    assert start["lesson_set"] == "lessons_t" and len(start["lesson_set_digest"]) == 64
    assert start["rendered_fields"] == ["condition", "action", "success", "fallback"]
    assert start["lesson_set_status"] == "CANDIDATES"
    assert SOURCE_MARK not in json.dumps(start, ensure_ascii=False)


def _run_dir(tmp_path, arm, game, plies, candidate=None):
    run = tmp_path / "runs" / f"{arm}-{game}-{candidate}"
    run.mkdir(parents=True)
    start = {"seq": 1, "type": "start", "arm": arm, "set": "train", "game": game, "moments": plies,
             "candidate_id": candidate}  # fmt: skip
    (run / "agent.jsonl").write_text(json.dumps(start) + "\n")
    subs = [{"seq": i, "type": "submission", "call_id": i,
             "subjects": [{"game_ply": p, "outcome": "accepted",
                           "submitted": {"sentences": [{"text": f"{arm} {game} {p}"}]}}]}
            for i, p in enumerate(plies, start=1)]  # fmt: skip
    (run / "tools.jsonl").write_text("".join(json.dumps(x) + "\n" for x in subs))
    return run


def test_the_bundle_part_size_is_a_setting(tmp_path) -> None:
    """§4: 4 moments a part with three arms, 36 commentaries at three runs; the key keeps each
    run's candidate and digest, the judge's files keep neither."""

    from tools.rx import judge

    refs = tmp_path / "refs" / "train"
    refs.mkdir(parents=True)
    runs = []
    for arm in ("A", "B", "D"):
        for game in ("g1", "g2", "g3"):
            runs.append(_run_dir(tmp_path, arm, game, [3, 5, 7], "L01" if arm != "A" else None))
            for p in (3, 5, 7):
                (refs / f"{game}-{p}.json").write_text("{}")
    original = judge.REFERENCES
    judge.REFERENCES = tmp_path / "refs"
    try:
        out = judge.bundle(runs, "J4", seed=1, root=tmp_path / "judging", keys=tmp_path / "keys",
                           moments_per_part=4)  # fmt: skip
        with pytest.raises(ValueError):
            judge.bundle(runs, "J5", seed=1, root=tmp_path / "judging", keys=tmp_path / "keys",
                         moments_per_part=0)  # fmt: skip
    finally:
        judge.REFERENCES = original
    assert out["items"] == 27 and len(out["parts"]) == 3  # 9 moments: 4, 4, 1
    first = json.loads((tmp_path / "judging" / "J4" / "part01" / "bundle.json").read_text())[
        "items"
    ]
    assert len(first) == 4 * 3 and "L01" not in json.dumps(first)
    key = json.loads((tmp_path / "keys" / "J4" / "bundle_key.json").read_text())["key"]
    assert {v["candidate_id"] for v in key.values()} == {None, "L01"}


def test_the_batch_interleaves_and_passes_lessons_to_the_lesson_arms_only(tmp_path) -> None:
    """Review N1: B, D, B, D ... game by game and repeat by repeat; `--lessons` for D only; the
    candidate on both; a bound passed through."""

    from tools.rx import batch

    todo = batch.jobs(2, ("B", "D"), ("train",), None, "L03")
    assert [j["arm"] for j in todo[:4]] == ["B", "D", "B", "D"]
    assert [j["repeat"] for j in todo[:4]] == [1, 1, 2, 2]
    assert len({j["game"] for j in todo[:4]}) == 1 and all(j["candidate"] == "L03" for j in todo)
    lessons = tmp_path / "set.json"
    b = batch.command(todo[0], tmp_path / ".env", lessons, {"turns": 40, "tokens": None})
    d = batch.command(todo[1], tmp_path / ".env", lessons, {"turns": 40})
    assert "--lessons" not in b and "--lessons" in d
    assert b[b.index("--candidate") + 1] == "L03" == d[d.index("--candidate") + 1]
    assert b[b.index("--turns") + 1] == "40" and "--tokens" not in b
    with pytest.raises(ValueError):
        batch.command(todo[1], tmp_path / ".env", None, {})
    assert [j["arm"] for j in batch.jobs(1)[:2]] == ["A", "A-min"]  # RX2's default unchanged


def test_screening_runs_are_paired_by_candidate() -> None:
    """Re-review N4: runs labelled by their candidate are paired within it, never pooled; the paired
    difference is given for each moment."""

    from tools.rx.report import label, paired

    assert label({"arm": "D", "candidate": "L03"}) == "D:L03"
    assert label({"arm": "A"}) == "A"
    v = lambda d: {"wrong": 0, "sentences": 4, "decisive": d, "score": 3.0}
    cells = {("train", "g1", 31): {"D:L03": [v(1.0)], "B:L03": [v(0.0)], "D:L05": [v(0.0)],
                                   "B:L05": [v(0.0)]},
             ("train", "g1", 40): {"D:L05": [v(1.0)], "B:L05": [v(0.0)]}}  # fmt: skip
    l3 = paired(cells, "train", "D:L03", "B:L03", "decisive")
    l5 = paired(cells, "train", "D:L05", "B:L05", "decisive")
    assert l3["by_moment"] == {"g1-31": 1.0} and l3["moments"] == 1
    assert l5["by_moment"] == {"g1-31": 0.0, "g1-40": 1.0}
    assert paired(cells, "validation", "D:L03", "B:L03", "decisive")["moments"] == 0


# -- the review of PR #145 -------------------------------------------------------------------------


def test_a_set_serves_only_the_runs_its_status_allows(tmp_path) -> None:
    """B1: candidates serve screening only (Train, one candidate); a set the owner has not approved
    runs on Train only; Validation takes an approved set whole; a run carries at most eight lessons
    whatever the file holds."""

    twelve = [_lesson(f"L{i:02d}", success=f"확인 {i}") for i in range(1, 13)]
    candidates = _set(tmp_path, twelve, status="CANDIDATES", name="cands")
    for set_name, candidate, match in (("validation", None, "screening only"),
                                       ("train", None, "screening only"),
                                       ("validation", "L01", "Train only")):  # fmt: skip
        with pytest.raises(ValueError, match=match):
            rx_run.lessons(_spec(tmp_path, "D", candidates, candidate, set_name))
    assert rx_run.lessons(_spec(tmp_path, "D", candidates, "L01"))[1]["lesson_ids"] == ["L01"]
    checking = _set(tmp_path, twelve[:8], status="CHECKING", name="check")
    assert len(rx_run.lessons(_spec(tmp_path, "D", checking))[1]["lesson_ids"]) == 8
    with pytest.raises(ValueError, match="Train only"):
        rx_run.lessons(_spec(tmp_path, "D", checking, set_name="validation"))
    with pytest.raises(ValueError, match="no --candidate"):
        rx_run.lessons(_spec(tmp_path, "D", checking, "L01"))
    approved = _set(tmp_path, twelve[:8], status="APPROVED", name="approved")
    _, info = rx_run.lessons(_spec(tmp_path, "D", approved, set_name="validation"))
    assert info["lesson_set_status"] == "APPROVED" and len(info["lesson_ids"]) == 8
    unsigned = _set(tmp_path, twelve[:8], status="APPROVED", name="unsigned", approval={})
    with pytest.raises(ValueError, match="approval"):
        rx_run.lessons(_spec(tmp_path, "D", unsigned, set_name="validation"))
    with pytest.raises(ValueError):
        rx_run.lessons(_spec(tmp_path, "D", _set(tmp_path, twelve[:8], status="DRAFT", name="x")))
    with pytest.raises(ValueError, match="at most 8"):
        lesson_sets.select({"lessons": twelve}, None)
    with pytest.raises(ValueError, match="Train only"):
        rx_run.lessons(_spec(tmp_path, "B", None, "L01", "validation"))


def test_a_set_runs_only_on_the_versions_it_was_written_for(tmp_path) -> None:
    """N2: a set written for another guide or another build is refused, to be written and approved
    again."""

    approved = _set(tmp_path, [_lesson("L01")], status="APPROVED")
    rx_run.lessons(_spec(tmp_path, "D", approved))
    with pytest.raises(ValueError, match="guide"):
        rx_run.lessons(_spec(tmp_path, "D-min", approved))
    _base(tmp_path, build_id="c" * 64)
    with pytest.raises(ValueError, match="build"):
        rx_run.lessons(_spec(tmp_path, "D", approved))


def test_parts_hold_whole_candidates_within_both_limits(tmp_path) -> None:
    """B2: twelve candidates on the same three moments (B and D each, three runs: 6 a candidate a
    moment, 72 at a moment) are packed into parts of at most 36 commentaries and 4 moments; a
    candidate's B and D at a moment are never split; RX2's parts are unchanged."""

    from tools.rx.judge import pack

    items = [(f"train/g1-{p}", {"candidate_id": f"L{c:02d}", "arm": arm}, [])
             for p in (3, 5, 7) for c in range(1, 13) for arm in ("B", "D") for _ in range(3)]  # fmt: skip
    parts = pack(items, 4, 36)
    assert sum(len(x) for x in parts) == len(items) == 216
    assert all(len(x) <= 36 for x in parts) and all(len({i[0] for i in x}) <= 4 for x in parts)
    where = {}
    for n, part in enumerate(parts):
        for moment, info, _ in part:
            where.setdefault((moment, info["candidate_id"]), set()).add(n)
    assert all(len(x) == 1 for x in where.values())  # each candidate's moment in one part
    rx2 = [(f"train/g{g}-{p}", {"candidate_id": None, "arm": arm}, [])
           for g in (1, 2, 3, 4) for p in (3, 5, 7) for arm in ("A", "A-min") for _ in range(3)]  # fmt: skip
    assert [len(x) for x in pack(rx2, 6, 36)] == [36, 36]  # 12 moments: 6 and 6, as RX2 judged
    with pytest.raises(ValueError, match="more than"):
        pack(items, 4, 5)


def test_request_fetched_is_paired_by_moment() -> None:
    """N1: a moment-run's share of its decisive `on_request` causes fetched, None without one; paired
    by moment like M2b."""

    from tools.rx.report import fetched_value, paired

    cause = lambda fetched, route="on_request", role="decisive": {
        "role": role, "route": route, "request_fetched": fetched}  # fmt: skip
    assert fetched_value({"causes": [cause(True), cause(False)]}) == 0.5
    assert fetched_value({"causes": [cause(True, route="in_digest")]}) is None
    assert fetched_value({"causes": [cause(True, role="supporting")]}) is None
    assert fetched_value(None) is None
    v = lambda f: {"wrong": 0, "sentences": 1, "decisive": None, "score": 3.0, "fetched": f}
    cells = {("train", "g1", 31): {"D:L03": [v(1.0)], "B:L03": [v(0.0)]},
             ("train", "g1", 40): {"D:L03": [v(None)], "B:L03": [v(None)]}}  # fmt: skip
    out = paired(cells, "train", "D:L03", "B:L03", "fetched")
    assert out["by_moment"] == {"g1-31": 1.0} and out["moments"] == 1


# -- the re-review of PR #145 ----------------------------------------------------------------------


def test_an_action_must_use_a_calliope_tool_with_what_to_pass() -> None:
    """Re-review C1: an abstract instruction, an empty step, a tool that does not exist, a tool named
    with nothing to pass, are refused; a step using `explore` or `facts` with what to pass is kept."""

    bad = {
        "abstract": ["더 깊이 생각하고 정확하게 설명한다"],
        "empty": [""],
        "blank and abstract": ["  ", "정확하게 설명한다"],
        "no such tool": ["analyze_deep로 그 수를 깊게 본다"],
        "no such call": ["analyze_deep(ply)를 부르고 explore로 그 진행을 둔다"],
        "nothing to pass": ["explore"],
        "not a list": {"tool": "explore"},
    }
    for name, action in bad.items():
        assert lesson_sets.action_problems(action), name
    good = [["그 수부터 실제 진행을 explore로 둔다"],
            ["facts로 그 국면의 exchange 기록을 읽는다", "결과의 평가를 함께 적는다"],
            ["judge_move로 엔진의 대안 수를 판정한다"], ["explore(from: 그 수, moves: 실제 진행)"]]  # fmt: skip
    for action in good:
        assert lesson_sets.action_problems(action) == [], action
    refused = lesson_sets.problems({"lessons": [_lesson("L01", action=bad["abstract"])]})
    assert any("explore" in p for p in refused)


def test_a_lesson_s_versions_are_the_set_s(tmp_path) -> None:
    """Re-review N3: a lesson naming another tools version, or a version the set does not fix, is
    refused; the set fixes them when it is written and the owner approves them with it."""

    stale = _lesson("L01", versions={"tools": "old-tools", "guide": "commentary_ko_v8"})
    path = _set(tmp_path, [stale], raw=True)
    with pytest.raises(ValueError, match="versions.tools"):
        rx_run.lessons(_spec(tmp_path, "D", path))
    unfixed = _lesson("L01", versions={"digest": "d-1"})
    with pytest.raises(ValueError, match="not fixed by the set"):
        rx_run.lessons(_spec(tmp_path, "D", _set(tmp_path, [unfixed], raw=True)))
    rx_run.lessons(_spec(tmp_path, "D", _set(tmp_path, [_lesson("L01")])))


def test_a_set_not_promoted_runs_only_to_reproduce(tmp_path) -> None:
    """Re-review N4: a NOT_PROMOTED set is kept, not used; it runs only with `reproduce`, recorded in
    the `start` line; a PROMOTED set runs as an approved one."""

    from tools.rx import batch

    dropped = _set(tmp_path, [_lesson("L01")], status="NOT_PROMOTED", name="dropped")
    with pytest.raises(ValueError, match="--reproduce"):
        rx_run.lessons(_spec(tmp_path, "D", dropped, set_name="validation"))
    spec = _spec(tmp_path, "D", dropped, set_name="validation")
    spec.reproduce = True
    assert rx_run.lessons(spec)[1]["reproduce"] is True
    promoted = _set(tmp_path, [_lesson("L01")], status="PROMOTED", name="promoted")
    assert (
        rx_run.lessons(_spec(tmp_path, "D", promoted, set_name="validation"))[1]["reproduce"]
        is False
    )
    job = {"set": "validation", "game": "g", "arm": "D", "repeat": 1}
    assert "--reproduce" in batch.command(job, tmp_path / ".env", dropped, {}, True)
    assert "--reproduce" not in batch.command(job, tmp_path / ".env", dropped, {})
