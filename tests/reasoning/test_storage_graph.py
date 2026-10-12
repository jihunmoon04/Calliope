"""`claim_graph_v1`: save, load and replay (R4-D §7 test obligations)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import ClassVar

import pytest
from scripted import scripted
from story import WDL, after, claim, line, run
from test_render import brilliant, forced, fork, great, miss_mate, open_exchange
from test_runner import Probe

from calliope.facts import BudgetExceededError, EngineProfile, FactEngine, FactTree, RootSpec
from calliope.facts.engine_work import EngineWork
from calliope.reasoning import AnalysisRequest, Reasoner, ReasoningBudget
from calliope.reasoning.catalogue import CATALOGUE_V1
from calliope.reasoning.encoding import encoded
from calliope.reasoning.errors import StoredGraphError
from calliope.reasoning.needs import FamilyNeed
from calliope.reasoning.planner import plan_digest
from calliope.reasoning.render import explain, plan_analysis, render
from calliope.reasoning.storage import ReplayFactEngine, load, save
from calliope.reasoning.verification import Verdict, VerdictStatus

WIN, EVEN, DRAW = (1000, 0, 0), (300, 600, 100), (0, 1000, 0)
SCENARIOS = {f.__name__: f for f in (fork, brilliant, miss_mate, great, forced, open_exchange)}
ENCODED = ("request", "grading", "rounds", "judgements", "observations", "claims", "relations",
           "labels", "limits_reached", "build")  # fmt: skip


def round_trip(analysis, **kw):
    rendered = explain(analysis)
    tree_bytes, graph_bytes = save(analysis, rendered)
    loaded, again = load(FactEngine(), tree_bytes, graph_bytes, **kw)
    return (tree_bytes, graph_bytes), (loaded, again)


def _fields(analysis) -> dict:
    zero = analysis.round_zero
    values = {"request": zero.request, "grading": zero.grading, "rounds": analysis.rounds,
              "judgements": zero.judgements, "observations": zero.observations,
              "claims": analysis.claims, "relations": analysis.relations,
              "labels": analysis.labels, "limits_reached": analysis.limits_reached,
              "build": analysis.build}  # fmt: skip
    return {k: encoded(v) for k, v in values.items()}


def _tamper(graph_bytes: bytes, edit) -> bytes:
    doc = json.loads(graph_bytes)
    edit(doc)
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=True).encode("ascii")


# -- obligation 1: round trip; 6a, 6b ---------------------------------------------------------------


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_round_trip(name: str) -> None:
    analysis = SCENARIOS[name]()
    (tree_bytes, graph_bytes), (loaded, rendered) = round_trip(analysis)
    assert save(loaded, rendered) == (tree_bytes, graph_bytes)  # save(load(x)) == x, bytes
    assert _fields(loaded) == _fields(analysis)  # field by field, encoded
    view, original = loaded.tree.view(loaded.rev), analysis.tree.view(analysis.rev)
    assert (view.digest(), loaded.rev) == (original.digest(), analysis.rev)  # trees by digest
    assert isinstance(loaded.round_zero.tree, FactTree)  # 6b: no ReplayTree escapes
    assert rendered == explain(analysis)
    # 6a: one plan path
    p = plan_analysis(analysis)
    assert render(p, analysis) == explain(analysis)
    assert plan_digest(p) == explain(analysis).plan_digest


def test_a_non_reproducible_tree_round_trips(monkeypatch) -> None:
    """A round-0 deadline cut makes the tree load-dependent; replay reads no clock."""

    attach, passed, cut = EngineWork._attach_line, EngineWork._deadline_passed, {"now": False}

    def attach_line(self, anchor, search, rank, pv):
        cut["now"] = rank == 2
        try:
            return attach(self, anchor, search, rank, pv)
        finally:
            cut["now"] = False

    monkeypatch.setattr(EngineWork, "_attach_line", attach_line)
    monkeypatch.setattr(EngineWork, "_deadline_passed", lambda self: cut["now"] or passed(self))
    analysis = fork()
    assert not analysis.tree.view(analysis.rev).reproducible()
    monkeypatch.setattr(EngineWork, "_deadline_passed", passed)  # the load meets a calm clock
    (tree_bytes, graph_bytes), (loaded, rendered) = round_trip(analysis)
    assert save(loaded, rendered) == (tree_bytes, graph_bytes)


# -- obligations 2, 3, 9: tampering, build and grading refused --------------------------------------


def test_tampering_is_refused() -> None:
    analysis = great()  # it has a label, so dropping the labels changes the document
    rendered = explain(analysis)
    tree_bytes, graph_bytes = save(analysis, rendered)
    edits = {
        "rendered": lambda d: d["rendered"]["f"][3][0]["f"].__setitem__(0, "1.a3 is fine."),
        "labels": lambda d: d.__setitem__("labels", []),
        "claims": lambda d: d.__setitem__("claims", d["claims"][:-1]),
        "digest": lambda d: d.__setitem__("digest", "0" * 64),
    }
    for field, edit in edits.items():
        tampered = _tamper(graph_bytes, edit)
        assert tampered != graph_bytes, field
        with pytest.raises(StoredGraphError, match=field):
            load(FactEngine(), tree_bytes, tampered)
    with pytest.raises(StoredGraphError):
        load(FactEngine(), tree_bytes, graph_bytes[:-1])  # not JSON any more


def test_a_build_mismatch_is_refused(monkeypatch) -> None:
    analysis = fork()
    tree_bytes, graph_bytes = save(analysis, explain(analysis))
    from calliope.reasoning import build

    with monkeypatch.context() as m:  # another phrasebook file
        m.setattr(build, "_phrasebooks", lambda: (("phrases_en_v1", "0" * 64),))
        with pytest.raises(StoredGraphError, match="build"):
            load(FactEngine(), tree_bytes, graph_bytes)
    with monkeypatch.context() as m:  # another miss_p2 threshold
        from calliope.reasoning import labels

        m.setattr(labels, "MISS_LOSS", 161)
        with pytest.raises(StoredGraphError, match="build"):
            load(FactEngine(), tree_bytes, graph_bytes)

    class Renamed(type(CATALOGUE_V1[0])):
        version = "v2"  # another template version

    templates = (Renamed(), *CATALOGUE_V1[1:])
    with pytest.raises(StoredGraphError, match="build"):
        load(FactEngine(), tree_bytes, graph_bytes, templates=templates)


def test_a_grading_mismatch_is_refused() -> None:
    analysis = great()
    tree_bytes, graph_bytes = save(analysis, explain(analysis))

    def edit(doc):
        doc["grading"]["f"][0] = "quality_v2"

    with pytest.raises(StoredGraphError):
        load(FactEngine(), tree_bytes, _tamper(graph_bytes, edit))


# -- obligation 4: the replay cursor ----------------------------------------------------------------


class RevProbe(Probe):
    """Records the revision and node count it is proposed on."""

    name = "rev_probe"
    seen: ClassVar[list] = []

    def propose(self, ctx):
        RevProbe.seen.append((ctx.view.rev, len(ctx.view.nodes())))
        return super().propose(ctx)


def test_replay_sees_each_round_at_its_own_revision() -> None:
    templates = (*CATALOGUE_V1, RevProbe())
    x = after(BACK, "Qe8+ Rxe8")
    RevProbe.seen = []
    analysis = run(BACK, "Qe8+", BACK_LINES, multipv=2, templates=templates,
                   table={x: [line(x, "Rxe8#", WIN, mate=1)]})  # fmt: skip
    original = list(RevProbe.seen)
    assert len({rev for rev, _ in original}) >= 2  # several rounds
    RevProbe.seen = []
    round_trip(analysis, templates=templates)
    assert RevProbe.seen == original  # round 0 never sees the final revision


# -- obligation 6: configuration ----------------------------------------------------------------------


def test_a_custom_configuration_is_saved_and_required() -> None:
    templates = (*CATALOGUE_V1, RevProbe())
    analysis = run(QUIET, "a3", QUIET_LINES, multipv=2, templates=templates)
    assert ("rev_probe", "t1") in analysis.build.templates
    tree_bytes, graph_bytes = save(analysis, explain(analysis))
    with pytest.raises(StoredGraphError, match="build"):
        load(FactEngine(), tree_bytes, graph_bytes)  # the default catalogue
    load(FactEngine(), tree_bytes, graph_bytes, templates=templates)


# -- obligations 7, 8: replay mismatch and each outcome kind --------------------------------------


def test_replay_mismatches_are_refused() -> None:
    analysis = brilliant()
    tree_bytes, graph_bytes = save(analysis, explain(analysis))

    def no_op(doc):  # a recorded revision turned into NO_OP: the re-derived rounds differ
        doc["rounds"][0]["requests"][0]["f"][1] = "NO_OP"

    with pytest.raises(StoredGraphError, match="rounds"):
        load(FactEngine(), tree_bytes, _tamper(graph_bytes, no_op))
    tree = FactEngine().load(tree_bytes)
    replay = ReplayFactEngine(FactEngine(), tree, [])
    with pytest.raises(StoredGraphError, match="cursor|ended"):
        replay.finish()  # under-run: the cursor never reached the final revision


class NoOpProbe(Probe):
    """Asks for a default family that is already there: an `ensure` with nothing to do."""

    name = "noop_probe"

    def verify(self, h, view, grading):
        return Verdict(h.id, VerdictStatus.NEEDS_EVIDENCE,
                       needs=(FamilyNeed(h.subject.parent, "status"),))  # fmt: skip


def test_a_no_op_outcome_replays() -> None:
    templates = (NoOpProbe(),)  # alone, so no other need joins its ensure
    analysis = run(QUIET, "a3", QUIET_LINES, multipv=2, templates=templates)
    outcomes = [o.outcome for r in analysis.rounds for o in r.requests]
    assert "NO_OP" in outcomes
    (tree_bytes, graph_bytes), (loaded, rendered) = round_trip(analysis, templates=templates)
    assert save(loaded, rendered) == (tree_bytes, graph_bytes)


class Refusing(FactEngine):
    """Refuses the first `exchange` ensure, as an engine failure would."""

    refused = False

    def ensure(self, tree, request):
        if "exchange" in request.families and not Refusing.refused:
            Refusing.refused = True
            raise BudgetExceededError("refused for the test")
        return super().ensure(tree, request)


def test_a_refused_outcome_replays() -> None:
    fen = "4k3/8/8/3p4/4N3/8/8/4K3 w - - 0 1"
    lines = [line(fen, "Nc3 Kd7", WIN), line(fen, "Kd2 dxe4", DRAW)]
    Refusing.refused = False
    fact_engine = Refusing(engine=scripted({fen: lines}))
    request = AnalysisRequest(RootSpec(fen=fen), ("Nc3",), 1, replace(EngineProfile(), multipv=2),
                              ReasoningBudget(), grading=WDL)  # fmt: skip
    analysis = Reasoner(fact_engine).analyse(request)
    outcomes = [o.outcome for r in analysis.rounds for o in r.requests]
    assert "REFUSED(BudgetExceededError)" in outcomes
    rescue = claim(analysis, "rescue_v1").verdict
    assert rescue.reason == "NOT_COMPUTED(BudgetExceededError)"
    (tree_bytes, graph_bytes), (loaded, rendered) = round_trip(analysis)
    assert claim(loaded, "rescue_v1").verdict == rescue
    assert save(loaded, rendered) == (tree_bytes, graph_bytes)


BACK = "r5k1/5ppp/8/8/8/8/4QPPP/4R1K1 w - - 0 1"
BACK_LINES = [line(BACK, "Qe8+ Rxe8 Rxe8#", WIN, mate=2), line(BACK, "h3 h6 Qe3 Kh7", EVEN, cp=50)]
QUIET = "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"
QUIET_LINES = [line(QUIET, "a3 Kd7", WIN), line(QUIET, "Kd2 Kd7", DRAW)]


def test_a_malformed_document_is_refused_not_a_crash() -> None:
    """R4 review B2: every corruption below raises StoredGraphError, never KeyError/TypeError."""

    analysis = great()
    tree_bytes, graph_bytes = save(analysis, explain(analysis))
    doc = json.loads(graph_bytes)
    edits = {
        "tree null": lambda d: d.__setitem__("tree", None),
        "tree digest missing": lambda d: d["tree"].pop("digest"),
        "rounds not a list": lambda d: d.__setitem__("rounds", {}),
        "a round without requests": lambda d: d["rounds"][0].pop("requests"),
        "request is a grading": lambda d: d.__setitem__("request", doc["grading"]),
        "grading is a request": lambda d: d.__setitem__("grading", doc["request"]),
        "an outcome that is no string": lambda d: d["rounds"][0]["requests"][0]["f"].__setitem__(
            1, 7
        ),
        "digest is a number": lambda d: d.__setitem__("digest", 0),
        # re-review: nested values load consumes
        "a round's requests null": lambda d: d["rounds"][0].__setitem__("requests", None),
        "the request's grading null": lambda d: d["request"]["f"].__setitem__(6, None),
        "the request's target out of range": lambda d: d["request"]["f"].__setitem__(2, 99),
    }
    for name, edit in edits.items():
        tampered = _tamper(graph_bytes, edit)
        with pytest.raises(StoredGraphError):
            load(FactEngine(), tree_bytes, tampered)
        assert tampered != graph_bytes, name
