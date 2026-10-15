"""DF-D §7 tests 3, 4, 8: units, the optional `analysis` against the claim graph, its size."""

from __future__ import annotations

import dataclasses
import json
import re

import chess
import jsonschema
import pytest
from corpus_case import analyse, cases
from result_input import engine_run, game_input, ply_input

from calliope.reasoning import CausalCheck, JudgementRef, ObservationRef
from calliope.results import dumps, game_result, schema, schema_errors
from calliope.results.analysis import (
    FINDING_TYPES,
    ProjectionError,
    _observation_indexes,
    _Projection,
)
from calliope.results.document import UNITS

CASES = {c["name"]: c for c in cases()}
LEAK = re.compile(r'"(?:n|r|s)_[0-9a-f]{8,}"|\b[wb]\.[KQRBNP]\.[a-h][1-8]\b')


def _doc(case: dict, analysis: bool = True) -> tuple:
    a = analyse(case)
    sans = [*case.get("before", "").split(), case["played"]]
    doc = game_result(
        game_input(case["fen"], sans), engine_run(a), [ply_input(a)], analysis=analysis
    )
    return a, doc


# -- 3. units --------------------------------------------------------------------------------------


def test_every_number_has_a_unit() -> None:
    _a, doc = _doc(CASES["fork_blunder"], analysis=False)
    assert doc["units"] == UNITS
    evaluation = doc["plies"][0]["evaluation"]
    assert set(evaluation) == {
        "played",
        "best",
        "best_move",
        "loss",
        "expected",
        "grade_basis",
        "search",
    }
    assert isinstance(evaluation["expected"]["played"], int) and evaluation["search"]["depth"] == 12
    assert "analysis" not in doc["plies"][0]  # only on request


# -- 4. the analysis against the graph -------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_analysis_is_the_graph(name: str) -> None:
    a, doc = _doc(CASES[name])
    assert not schema_errors(doc)
    jsonschema.validate(doc, schema(), cls=jsonschema.Draft202012Validator)
    text = dumps(doc).decode()
    assert not LEAK.findall(text), LEAK.findall(text)[:3]  # AR-D G3
    out = doc["plies"][0]["analysis"]
    # claims: every one, in the graph's order, status, reason, scope and effective scopes
    assert [c["id"] for c in out["claims"]] == [c.id for c in a.claims]
    for c, record in zip(a.claims, out["claims"], strict=True):
        v = c.verdict
        assert record["status"] == v.status.value and record.get("reason") == v.reason
        assert record.get("refuted_by") == v.refuted_by
        assert (record["scope"] is None) == (v.scope is None)
        if v.scope is not None:
            assert (record["scope"]["basis"], record["scope"]["quantifier"]) == (
                v.scope.basis.value, v.scope.quantifier.value)  # fmt: skip
            assert len(record["scope"]["population"]["moves"]) == len(v.scope.population.moves)
        assert [(s["basis"], s["quantifier"], s["policies"]) for s in record["effective_scopes"]] == [
            (s.basis.value, s.quantifier.value, list(s.policies)) for s in c.effective_scope]  # fmt: skip
        assert len(record["evidence"]) == len(v.evidence)
        assert [x.get("kind") for x in record["evidence"]] == [_kind(x) for x in v.evidence]
        checks = [f for f in v.findings if isinstance(f, CausalCheck)]
        assert [(x["kind"], x["passed"]) for x in record["checks"]] == [
            (f.kind.lower(), f.passed) for f in checks]  # fmt: skip
        assert len(record["findings"]) == len(v.findings) - len(checks)
    # relations decode back to the graph's, observation and judgement targets included
    view = a.tree.view(a.rev)
    decoded = sorted(
        (c["id"], r["kind"], _key(r["target"])) for c in out["claims"] for r in c["relations"]
    )
    assert decoded == sorted(
        (r.source, r.kind.value, _graph_key(view, r.target)) for r in a.relations
    )
    # judgements and observations
    zero = a.round_zero
    assert len(out["judgements"]) == len(zero.judgements)
    assert [j["move"]["uci"] for j in out["judgements"]] == [
        a.tree.view(a.rev).node(j.subject.child).incoming_move for j in zero.judgements]  # fmt: skip
    assert [(o["kind"], o["index"]) for o in out["observations"]] == list(
        zip([o.kind for o in zero.observations], _observation_indexes(zero.observations), strict=True))  # fmt: skip
    # every position replays from the root to its FEN
    for position in _positions(out):
        board = chess.Board(out["root"]["fen"])
        for uci in position["from_root"]:
            board.push_uci(uci)
        assert board.fen() == position["fen"]


def _kind(evidence) -> str:
    return {"FactRef": "fact", "SearchRef": "search_line", "LineSegment": "line"}[
        type(evidence).__name__
    ]


def _key(target: dict) -> tuple:
    if target["type"] == "claim":
        return ("claim", target["id"])
    if target["type"] == "observation":
        return ("observation", target["kind"], target["round"], target["index"])
    return ("judgement", target["move"]["uci"])


def _graph_key(view, target) -> tuple:
    if isinstance(target, str):
        return ("claim", target)
    if isinstance(target, ObservationRef):
        return ("observation", target.kind, target.round, target.index)
    assert isinstance(target, JudgementRef)
    return ("judgement", view.node(target.subject.child).incoming_move)


def _positions(value):
    if isinstance(value, dict):
        if value.get("kind") == "position":
            yield value
        for x in value.values():
            yield from _positions(x)
    elif isinstance(value, list):
        for x in value:
            yield from _positions(x)


def test_a_score_check_refusal_names_its_rule() -> None:
    from test_explanation_accuracy import ONE, ONE_LP, gain

    a = gain(ONE, "Nc3", ONE_LP, cp=50)  # the gain at ply 3, the score below 80 per point
    claim = next(c for c in a.claims if c.hypothesis.template == "material_gain_v3")
    assert claim.verdict.refuted_by == "material_gain.score_check"
    doc = game_result(game_input(ONE, ["Nc3"]), engine_run(a), [ply_input(a)], analysis=True)
    record = next(c for c in doc["plies"][0]["analysis"]["claims"] if c["id"] == claim.id)
    assert record["status"] == "refuted" and record["refuted_by"] == "material_gain.score_check"


def test_an_inconclusive_judgement_validates() -> None:
    _a, doc = _doc(CASES["inconclusive_exact"])
    judgement = doc["plies"][0]["analysis"]["judgements"][0]
    assert judgement["status"] == "inconclusive" and judgement["reason"]
    assert not schema_errors(doc)


def test_a_previous_move_s_judgement_is_listed() -> None:
    a, doc = _doc(CASES["missed_gain"])  # MISS reads the opponent's previous move
    assert len(a.round_zero.judgements) == 2
    assert len(doc["plies"][0]["analysis"]["judgements"]) == 2


def test_an_unknown_type_is_refused() -> None:
    a = analyse(CASES["forced"])

    @dataclasses.dataclass(frozen=True)
    class Unknown:
        x: int

    with pytest.raises(ProjectionError):
        _Projection(a).value(Unknown(1))


def test_the_schema_states_every_finding_type_s_fields() -> None:
    findings = schema()["$defs"]["Findings"]
    assert set(findings) == {k.__name__ for k in FINDING_TYPES}
    for k in FINDING_TYPES:
        required = set(findings[k.__name__]["required"])
        assert required == {"type", *(f.name for f in dataclasses.fields(k))}, k.__name__


# -- 8. size ---------------------------------------------------------------------------------------


def test_the_analysis_size_is_recorded() -> None:
    sizes = []
    for case in CASES.values():
        _a, plain = _doc(case, analysis=False)
        _a, full = _doc(case, analysis=True)
        sizes.append((len(dumps(full)), len(dumps(plain))))
    factor = max(f / p for f, p in sizes)
    assert factor < 20, factor  # DF1 §4 records the measured figures (a real game: 15.7)
    json.dumps(sizes)


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_reference_decodes_to_its_target(name: str) -> None:
    """DF1 review note: evidence and population moves map back to the graph's own references —
    fact targets by path or key, searches by index and rank, moves by UCI."""

    from calliope.facts import NodeId, PositionKey
    from calliope.reasoning import FactRef, LineSegment, MoveRef, SearchMoveRef, SearchRef

    a = analyse(CASES[name])
    p = _Projection(a)
    view = p.view
    records = [p.claim(c) for c in a.claims]  # p.searches is the index → search id table

    def moves_to(node) -> list[str]:
        return [view.node(n).incoming_move for n in view.path(node)[1:]]

    def same(ref, out) -> None:
        if isinstance(ref, FactRef):
            assert (out["kind"], out["family"], out["path"]) == ("fact", ref.family, list(ref.path))
            if isinstance(ref.target, PositionKey):
                assert out["target"] == {"kind": "position_key", "epd": ref.target.value}
            else:
                assert isinstance(ref.target, NodeId) and out["target"]["from_root"] == moves_to(
                    ref.target
                )
        elif isinstance(ref, SearchRef):
            assert p.searches[out["search"]] == ref.search_id and out["rank"] == ref.rank
        elif isinstance(ref, SearchMoveRef):
            assert p.searches[out["search"]] == ref.search_id
            assert (out["rank"], out["ply"]) == (ref.rank, ref.ply)
        elif isinstance(ref, MoveRef):
            assert out["uci"] == view.node(ref.node).incoming_move
        elif isinstance(ref, LineSegment):
            assert (out["first"], out["last"]) == (ref.first, ref.last)
        else:
            raise TypeError(f"unexpected reference {type(ref).__name__}")

    for c, record in zip(a.claims, records, strict=True):
        for ref, out in zip(c.verdict.evidence, record["evidence"], strict=True):
            same(ref, out)
        if c.verdict.scope is not None:
            moves = record["scope"]["population"]["moves"]
            for ref, out in zip(c.verdict.scope.population.moves, moves, strict=True):
                same(ref, out)
            for ref, out in zip(c.verdict.scope.searches, record["scope"]["searches"], strict=True):
                same(ref, out)
