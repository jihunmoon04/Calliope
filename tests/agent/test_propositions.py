"""AG-D §11 tests 4 and 5: every proposition kind and every use of a claim, one accepting and one
refusing case each, on the synthetic engine; handles of another kind, game or session refuse."""

from __future__ import annotations

import pytest
from agent_helpers import GAME, session

from calliope.agent.propositions import Refused, Verifier

FORK = "r3k3/2N5/8/8/8/8/8/4K3 b - - 0 1"  # the knight on c7 attacks the rook and the king
EXPOSED = "1. e4 e5 2. Nf3 d6 3. Ng5 h6 *"  # the knight on g5: a pawn attacks it, nothing defends


@pytest.fixture
def s(tmp_path):
    s = session(tmp_path)
    s.open_game(pgn=GAME)  # g1
    s.open_game(fen=FORK, moves=["Kd8"])  # g2
    s.open_game(pgn=EXPOSED)  # g3
    yield s
    s.close()


def verify(s, game_id: str, proposition: dict) -> dict:
    record, _ = Verifier(s, s.game(game_id)).verify({"id": "p", **proposition})
    return record


def refused(s, game_id: str, proposition: dict, field: str | None = None) -> Refused:
    with pytest.raises(Refused) as error:
        verify(s, game_id, proposition)
    if field is not None:
        assert error.value.field == field, error.value.problem
    return error.value


# -- judgements, claims, searches ------------------------------------------------------------------


def test_judgement(s) -> None:
    j = s.ply("g1", 3)["analysis"]["judgements"][0]
    good = {"kind": "judgement", "judgement": j["ref"], "move": "exd5", "grade": j["grade"],
            "label": j["label"], "best_move": j["best"]["move"]["san"]}  # fmt: skip
    assert verify(s, "g1", good)["move"] == "e4d5"
    refused(s, "g1", good | {"grade": "blunder"}, "grade")
    refused(s, "g1", good | {"best_move": "Nc3"}, "best_move")
    claim = s.ply("g1", 3)["analysis"]["claims"][0]["ref"]
    assert "not a judgement" in refused(s, "g1", good | {"judgement": claim}, "judgement").problem


def test_handles_of_another_game_or_session_refuse(s, tmp_path) -> None:
    j = s.ply("g1", 3)["analysis"]["judgements"][0]
    good = {"kind": "judgement", "judgement": j["ref"], "move": "exd5", "grade": j["grade"],
            "label": j["label"], "best_move": j["best"]["move"]["san"]}  # fmt: skip
    assert "another game" in refused(s, "g3", good, "judgement").problem
    other = session(tmp_path / "other")
    other.open_game(pgn=GAME)
    with pytest.raises(Refused, match="not served in this session"):
        Verifier(other, other.game("g1")).verify({"id": "p", **good})


def _claim(s, game_id: str, claim: dict, others=()) -> str:
    """Serve a claim record as `ply` would, for the rules of the uses."""

    s.analyses["test"] = ({"claims": [claim, *others]}, None)
    source = {"kind": "analysis", "analysis": "test", "path": ["e2e4"]}
    return s.handles.serve("c", s.game(game_id).key, source, {"claim": claim["id"]}, claim)


SCOPE_LINE = {"basis": "engine", "quantifier": "specific_line", "plies": 4}
SCOPE_ALT = {"basis": "engine", "quantifier": "exists_alternative", "plies": None}


def _record(**fields) -> dict:
    base = {"id": "c", "template": "fork_v2", "role": "mechanism", "status": "supported",
            "checks": [], "relations": [], "effective_scopes": [SCOPE_LINE]}  # fmt: skip
    return base | fields


@pytest.mark.parametrize(
    ("use", "accepted", "refused_record"),
    [
        ("result",
         _record(template="material_gain_v3", role="consequence",
                 checks=[{"kind": "attributed", "passed": True, "evidence": []}]),
         _record(template="material_gain_v3", role="consequence",
                 checks=[{"kind": "attributed", "passed": False, "evidence": []}])),
        ("result", _record(template="mate_delivered_v1", role="consequence"),
         _record(template="material_loss_v2", role="consequence")),  # ATTRIBUTED absent
        ("line_fact", _record(), _record(status="refuted")),
        ("mechanism",
         _record(relations=[{"kind": "explains", "target": {"type": "claim", "id": "t"}}]),
         _record(relations=[{"kind": "explains", "target": {"type": "claim", "id": "u"}}])),
        ("mechanism",
         _record(relations=[{"kind": "causes", "target": {"type": "judgement", "move": {}}}]),
         _record(relations=[{"kind": "associated_with", "target": {"type": "claim", "id": "t"}}])),
        ("associated",
         _record(relations=[{"kind": "associated_with", "target": {"type": "claim", "id": "t"}}]),
         _record(relations=[{"kind": "associated_with", "target": {"type": "claim", "id": "t"}},
                            {"kind": "explains", "target": {"type": "claim", "id": "t"}}])),
        ("comparison", _record(role="comparison"), _record(role="mechanism")),
        ("uncertain", _record(status="inconclusive"), _record(status="supported")),
        ("not_the_case", _record(status="refuted"), _record(status="inconclusive")),
    ],
)  # fmt: skip
def test_the_uses_of_a_claim(s, use, accepted, refused_record) -> None:
    targets = [{"id": "t", "status": "supported"}, {"id": "u", "status": "refuted"}]
    for record, ok in ((accepted, True), (refused_record, False)):
        ref = _claim(s, "g1", record, targets)
        p = {"kind": "claim", "claim": ref, "use": use, "scopes": record["effective_scopes"]}
        if ok:
            assert verify(s, "g1", p)["use"] == use
        else:
            refused(s, "g1", p, "use")


def test_the_scopes_of_a_claim_are_its_effective_scopes_as_a_set(s) -> None:
    """Review R1: a claim over a premise holds both scopes (`sacrifice_sound_v1` is
    `specific_line` over `sacrifice_offer_v1`'s `exists_alternative`)."""

    record = _record(template="sacrifice_sound_v1", effective_scopes=[SCOPE_LINE, SCOPE_ALT])
    ref = _claim(s, "g1", record)
    p = {"kind": "claim", "claim": ref, "use": "line_fact"}
    assert verify(s, "g1", p | {"scopes": [SCOPE_ALT, SCOPE_LINE]})["scopes"]
    refused(s, "g1", p | {"scopes": [SCOPE_LINE]}, "scopes")  # one missing
    refused(s, "g1", p | {"scopes": [SCOPE_LINE, SCOPE_ALT | {"plies": 2}]}, "scopes")
    real = next(c for c in s.ply("g1", 3)["analysis"]["claims"] if c["status"] == "supported")
    p = {"kind": "claim", "claim": real["ref"], "use": "line_fact",
         "scopes": real["effective_scopes"]}  # fmt: skip
    assert verify(s, "g1", p)["template"] == real["template"]


def test_engine_score_and_engine_line(s) -> None:
    best = s.ply("g1", 3)["analysis"]["judgements"][0]["best"]
    p = {"kind": "engine_score", "line": best["ref"], "move": best["move"]["san"],
         "score": best["score"], "depth": 12}  # fmt: skip
    assert verify(s, "g1", p)["score"] == best["score"]
    refused(s, "g1", p | {"score": {"cp": best["score"].get("cp", 0) + 1}}, "score")
    refused(s, "g1", p | {"depth": 11}, "depth")
    pv = [m["uci"] for m in best["pv"]]
    assert verify(s, "g1", {"kind": "engine_line", "line": best["ref"], "moves": pv[:2]})
    refused(s, "g1", {"kind": "engine_line", "line": best["ref"], "moves": pv[1:3]}, "moves")
    searched = s.explore("g1", {"ply": 2, "at": "after"}, [], search=True)["search"]["lines"][0]
    assert verify(s, "g1", {"kind": "engine_score", "line": searched["ref"],
                            "move": searched["move"]["uci"], "score": searched["score"]})  # fmt: skip


def test_material_and_explored_lines(s) -> None:
    x = s.explore("g1", {"ply": 4, "at": "after"}, ["Nc3", "Nxd5", "Nxd5", "Qxd5"])
    p = {"kind": "material", "line": x["ref"], "from": 0, "to": 3, "side": "white", "balance": 2}
    record = verify(s, "g1", p)
    assert record["balance"] == 2 and record["by_agent"]
    assert verify(s, "g1", p | {"from": 2, "to": 4, "balance": 0})  # 3.Nxd5, then 4...Qxd5
    refused(s, "g1", p | {"balance": 1}, "balance")
    refused(s, "g1", p | {"to": 9}, "to")
    line = {"kind": "explored_line", "line": x["ref"], "moves": ["Nc3", "Nxd5", "Nxd5", "Qxd5"]}
    assert verify(s, "g1", line)["by"] == "agent"
    refused(s, "g1", line | {"moves": ["Nc3"]}, "moves")
    as_engine = {"kind": "engine_line", "line": x["ref"], "moves": ["Nc3"]}
    assert "not a search_line" in refused(s, "g1", as_engine, "line").problem


# -- positions ------------------------------------------------------------------------------------


def test_attack_defence_pin_check_and_legal_moves(s) -> None:
    at = {"ply": 2, "at": "after"}  # 1.e4 d5
    assert verify(s, "g1", {"kind": "attack", "position": at, "attacker": "e4", "target": "d5"})
    refused(s, "g1", {"kind": "attack", "position": at, "attacker": "e4", "target": "f5"},
            "target")  # fmt: skip
    assert verify(s, "g1", {"kind": "defence", "position": at, "defender": "d8", "defended": "d5"})
    refused(s, "g1", {"kind": "defence", "position": at, "defender": "c8", "defended": "d5"},
            "defender")  # fmt: skip
    pin_at = {"from_root": ["e4", "e5", "d4", "Bb4+", "c3"]}  # the pawn on c3 blocks the check
    assert verify(s, "g1", {"kind": "pin", "position": pin_at, "pinned": "c3", "pinner": "b4"})
    refused(s, "g1", {"kind": "pin", "position": pin_at, "pinned": "c3", "pinner": "a5"}, "pinner")
    assert verify(s, "g1", {"kind": "check", "position": pin_at, "checkers": []})
    check_at = {"from_root": ["e4", "e5", "d4", "Bb4+"]}
    assert verify(s, "g1", {"kind": "check", "position": check_at, "checkers": ["b4"]})
    refused(s, "g1", {"kind": "check", "position": check_at, "checkers": []}, "checkers")
    record = verify(s, "g1", {"kind": "legal_moves", "position": {"from_root": []}, "count": 20})
    assert record["count"] == 20
    refused(s, "g1", {"kind": "legal_moves", "position": {"from_root": []}, "count": 19}, "count")
    king = {"kind": "legal_moves", "position": check_at,
            "moves": ["c3", "Nc3", "Nd2", "Bd2", "Qd2", "Ke2"]}  # the six answers  # fmt: skip
    assert verify(s, "g1", king)["moves"]
    refused(s, "g1", king | {"moves": ["c3"]}, "moves")


def test_exposed(s) -> None:
    at = {"ply": 6, "at": "after"}  # 3...h6: the knight on g5
    p = {"kind": "exposed", "position": at, "piece": "g5", "exposed": "exposed", "gain": 3}
    assert verify(s, "g3", p)["exposed"] == "exposed"
    assert verify(s, "g3", p | {"piece": "e4", "exposed": "not_exposed", "gain": 0})
    refused(s, "g3", p | {"exposed": "not_exposed"}, "exposed")
    refused(s, "g3", p | {"gain": 1}, "gain")
    refused(s, "g3", p | {"exposed": "maybe"}, "exposed")


def test_pattern_is_a_configuration(s) -> None:
    at = {"from_root": []}
    p = {"kind": "pattern", "position": at, "pattern": "multi_target_attacks",
         "participants": {"actor": "c7", "targets": ["e8", "a8"]}}  # fmt: skip
    record = verify(s, "g2", p)
    assert record["configuration_only"] and record["participants"]["actor"] == "c7"
    refused(s, "g2", p | {"participants": {"actor": "c7", "targets": ["e8"]}}, "participants")
    refused(s, "g2", p | {"pattern": "forks"}, "pattern")


def test_after_reply_compares_one_reply_after_two_moves(s) -> None:
    a = {"from_root": ["e4", "d5", "exd5", "Nf6"]}
    b = {"from_root": ["e4", "d5", "Nc3", "Nf6"]}
    p = {"kind": "after_reply", "reply": "Nf6", "after_a": a, "after_b": b,
         "proposition_a": {"kind": "attack", "position": a, "attacker": "f6", "target": "d5"},
         "proposition_b": {"kind": "attack", "position": b, "attacker": "f6", "target": "e4"}}  # fmt: skip
    assert verify(s, "g1", p)["reply"] == "g8f6"
    failing = p | {"proposition_b": p["proposition_b"] | {"target": "d5"}}  # d5 is black's own
    assert refused(s, "g1", failing).field == "proposition_b.target"
    other_p = p | {"after_b": {"from_root": ["d4", "d5", "Nc3", "Nf6"]},
                   "proposition_b": p["proposition_b"] | {"position": {"from_root": [
                       "d4", "d5", "Nc3", "Nf6"]}}}  # fmt: skip
    refused(s, "g1", other_p, "after_b")
    kinds = p | {"proposition_b": {"kind": "check", "position": b, "checkers": []}}
    refused(s, "g1", kinds, "proposition_b")


def test_definition(s) -> None:
    assert verify(s, "g1", {"kind": "definition", "definition": "REFUTED"})
    assert verify(s, "g1", {"kind": "definition", "definition": "proposition.claim"})
    refused(s, "g1", {"kind": "definition", "definition": "threat_v1"}, "definition")
    refused(s, "g1", {"kind": "rumour"}, "kind")
