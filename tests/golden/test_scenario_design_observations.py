"""Verify design examples against existing observations, not future summary acceptance.

Expected captures, counts and distinguishing facts are manually specified in JSON.
No new scenario service or renderer is implemented or simulated here.
"""

import json
from collections import Counter
from pathlib import Path

import chess
import pytest

from calliope.adapters.python_chess import PythonChessAdapter
from calliope.domain.chess import ChessMove
from calliope.services.position import BoardDeltaAnalyzer, PositionFactExtractor
from calliope.services.position.activity import ActivityAnalyzer, ActivityLineAnalyzer
from calliope.services.position.line import LineAnalyzer
from calliope.services.position.positional import PositionAnalyzer, TransitionAnalyzer

CORPUS = json.loads(
    Path(__file__).with_name("scenario_explanation_cases.json").read_text(encoding="utf-8")
)
CASES = CORPUS["cases"]


def build():
    rules = PythonChessAdapter()
    facts = PositionFactExtractor(rules)
    positions = PositionAnalyzer(facts)
    transitions = TransitionAnalyzer(rules, positions, BoardDeltaAnalyzer(rules, facts))
    return rules, ActivityLineAnalyzer(
        LineAnalyzer(transitions), ActivityAnalyzer(positions, rules)
    )


def type_key(piece):
    return f"{piece.color.value}:{piece.piece_type.value}"


def history_at(result, base_square):
    return next(h for h in result.structural.piece_histories if h.base.base_square == base_square)


def base_square_of(result, frame, piece):
    return next(
        h.base.base_square for h in result.structural.piece_histories if h.states[frame] == piece
    )


def observable_key_value(result, key, frame):
    """Resolve only the corpus's named observation oracles; no relevance selection."""
    family = key["family"]
    observed = result.activity_frames[frame]
    if family == "PIECE_STATE":
        return history_at(result, key["subject"]).states[frame]
    if family in ("FOCUS_OCCUPANT", "FOCUS_ATTACKERS", "FOCUS_LEGAL_CAPTURES_NOW"):
        access = next(s for s in observed.activity.squares if s.square == key["square"])
        if family == "FOCUS_OCCUPANT":
            return access.occupant
        if family == "FOCUS_ATTACKERS":
            return access.white_attackers, access.black_attackers
        return observed.activity.side_to_move, access.current_legal_captures
    if family == "PIN_PRESENT":
        return any(
            [base_square_of(result, frame, piece) for piece in (p.pinner, p.pinned, p.king)]
            == key["pin"]
            for p in observed.activity.absolute_pins
        )
    if family == "FILE_STATE":
        file = next(f for f in observed.structural.features.files if f.file == key["file"])
        return file.white_pawns, file.black_pawns
    current = history_at(result, key["subject"]).states[frame]
    if family == "PAWN_FLAGS":
        pawn = next((p for p in observed.structural.features.pawns if p.pawn == current), None)
        return (pawn.isolated, pawn.doubled, pawn.passed) if pawn else "NOT_APPLICABLE"
    if family == "ATTACK_FOOTPRINT":
        activity = next((p for p in observed.activity.pieces if p.piece == current), None)
        return activity.footprint if activity else "NOT_APPLICABLE"
    if family == "RAY_STATE":
        ray = next(
            (
                r
                for r in observed.activity.rays
                if r.source == current and r.direction == tuple(key["direction"])
            ),
            None,
        )
        return ray if ray else "NOT_APPLICABLE"
    raise AssertionError(f"Unsupported corpus oracle: {family}")


def event_for_key(result, key):
    step = result.structural.transitions[key["ply"] - 1]
    if key["family"] == "CAPTURE":
        assert step.board_delta.capture is not None
        return step.board_delta.capture
    before = history_at(result, key["subject"]).states[key["ply"] - 1]
    transition = next(
        t
        for t in step.board_delta.transitions
        if t.before == before and t.kind.name == key["family"]
    )
    # Suppressed capturer MOVE is not an event candidate, even though P5 retains it.
    capture = step.board_delta.capture
    assert not (key["family"] == "MOVE" and capture and capture.capturer_before == before)
    return transition


def verify_key_domain(result, key, *, absent=False):
    selectors = {
        "CAPTURE": set(),
        "MOVE": {"subject"},
        "PROMOTION": {"subject"},
        "CASTLING_ROOK": {"subject"},
        "PIECE_STATE": {"subject"},
        "FOCUS_OCCUPANT": {"square"},
        "FOCUS_ATTACKERS": {"square"},
        "FOCUS_LEGAL_CAPTURES_NOW": {"square"},
        "PAWN_FLAGS": {"subject"},
        "FILE_STATE": {"file"},
        "ATTACK_FOOTPRINT": {"subject"},
        "RAY_STATE": {"subject", "direction"},
        "PIN_PRESENT": {"pin"},
    }
    scope, family = key["scope"], key["family"]
    required = {"scope", "family"} | selectors[family]
    if scope in ("event", "step"):
        required |= {"ply"}
        assert type(key["ply"]) is int and 1 <= key["ply"] <= len(result.structural.transitions)
    elif scope == "snapshot":
        required |= {"frame"}
        assert family.startswith("FOCUS_")
        assert type(key["frame"]) is int and 0 <= key["frame"] < len(result.activity_frames)
    else:
        assert scope in ("endpoint", "history")
    assert set(key) - {"reasons"} == required
    assert "reasons" not in key or family == "CAPTURE"
    for subject in [key["subject"]] if "subject" in key else key.get("pin", []):
        history_at(result, subject)
    if scope == "event":
        assert not absent
        event_for_key(result, key)
    elif scope == "snapshot":
        assert not absent
        observable_key_value(result, key, key["frame"])
    elif scope == "history":
        assert not absent
        values = [observable_key_value(result, key, i) for i in range(len(result.activity_frames))]
        assert any(v != values[0] for v in values[1:])
    else:
        a, b = (
            (key["ply"] - 1, key["ply"])
            if scope == "step"
            else (0, len(result.activity_frames) - 1)
        )
        different = observable_key_value(result, key, a) != observable_key_value(result, key, b)
        assert different is not absent


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_structured_review_expectations_have_observation_evidence(case):
    """Freeze factual membership/counts and verify keys, not the future selector."""
    assert CORPUS["version"] == "scenario_explanation_corpus_v2"
    rules, lines = build()
    result = lines.analyze(
        rules.position_from_fen(case["fen"]), tuple(ChessMove(m) for m in case["moves"])
    )
    expected = case["summary_expectations"]
    participants, losses = set(), Counter()
    focus_captures = []
    for ply, step in enumerate(result.structural.transitions, 1):
        c = step.board_delta.capture
        if c and c.landing_square == case["focus"]:
            focus_captures.append(c)
            participants.add(base_square_of(result, ply - 1, c.capturer_before))
            participants.add(base_square_of(result, ply - 1, c.captured))
            losses[type_key(c.captured)] += 1
    order = lambda s: chess.parse_square(s)
    assert sorted(participants, key=order) == expected["participants"]
    assert dict(losses) == expected["focus_losses"]
    status = "FOCUS_CAPTURES_OBSERVED" if focus_captures else "NO_FOCUS_CAPTURE"
    assert status == expected["status"]
    seen = set()
    for group in ("included_fact_keys", "excluded_fact_keys", "absent_fact_keys"):
        for key in expected[group]:
            identity = json.dumps({k: v for k, v in key.items() if k != "reasons"}, sort_keys=True)
            assert identity not in seen
            seen.add(identity)
            verify_key_domain(result, key, absent=group == "absent_fact_keys")
            if "reasons" in key:
                c = event_for_key(result, key)
                reasons = ["LINE_CONTEXT"]
                if c.landing_square == case["focus"]:
                    reasons.append("FOCUS_CAPTURE")
                if c.captured_square == case["focus"] and c.landing_square != case["focus"]:
                    reasons.append("FOCUS_VICTIM_SQUARE")
                assert reasons == key["reasons"]
    for track in expected.get("temporary_tracks", []):
        values = [
            observable_key_value(result, track, i) for i in range(len(result.activity_frames))
        ]
        assert values == track["values"]
        assert values[0] == values[-1] and any(v != values[0] for v in values[1:-1])
    for digest in expected.get("required_digest_events", []):
        c = event_for_key(result, {"family": "CAPTURE", "ply": digest["ply"]})
        assert digest["template"] == "CAPTURE_EP" and c.is_en_passant
        assert (c.landing_square, c.captured_square) == (digest["landing"], digest["victim_square"])
    if "castling_context" in expected:
        context = expected["castling_context"]
        t = event_for_key(result, dict(context, family="CASTLING_ROOK"))
        assert (
            result.structural.transitions[context["ply"] - 1].board_delta.move.uci == context["uci"]
        )
        assert (t.before.square, t.after.square) == (context["from"], context["to"])


def observations(result):
    captures = []
    for ply, step in enumerate(result.structural.transitions, 1):
        capture = step.board_delta.capture
        if capture:
            captures.append(
                {
                    "ply": ply,
                    "landing": capture.landing_square,
                    "victim_square": capture.captured_square,
                    "victim": type_key(capture.captured),
                    "ep": capture.is_en_passant,
                }
            )
    material = {
        f"{c.color.value}:{c.piece_type.value}": c.count_delta
        for c in result.structural.material_changes
    }
    return captures, material


def read_check(result, check):
    if check["kind"] == "history":
        history = next(
            h
            for h in result.structural.piece_histories
            if h.base.base_square == check["base_square"]
        )
        return [f"{p.square}:{p.piece_type.value}" if p else None for p in history.states]
    frame = result.activity_frames[check["frame"]]
    kind = check["kind"]
    if kind in ("occupant", "attackers", "legal_captures"):
        access = next(s for s in frame.activity.squares if s.square == check["square"])
        if kind == "occupant":
            return type_key(access.occupant) if access.occupant else None
        if kind == "attackers":
            attackers = getattr(access, f"{check['color']}_attackers")
            return [p.square for p in attackers]
        return [c.move.uci for c in access.current_legal_captures]
    if kind == "pins":
        return [
            [p.pinner.square, p.pinned.square, p.king.square] for p in frame.activity.absolute_pins
        ]
    if kind == "pawn":
        pawn = next(p for p in frame.structural.features.pawns if p.pawn.square == check["square"])
        return {
            "isolated": pawn.isolated,
            "doubled": pawn.doubled,
            "passed": pawn.passed,
            "supporters": [p.square for p in pawn.pawn_supporters],
        }
    if kind == "file":
        file = next(f for f in frame.structural.features.files if f.file == check["file"])
        return [file.white_pawns, file.black_pawns]
    if kind == "ray":
        ray = next(
            r
            for r in frame.activity.rays
            if r.source.square == check["square"] and r.direction == tuple(check["direction"])
        )
        return list(ray.visible_squares)
    raise AssertionError(f"Unknown observation oracle: {kind}")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_design_case_factual_oracles(case):
    rules, lines = build()
    result = lines.analyze(
        rules.position_from_fen(case["fen"]), tuple(ChessMove(m) for m in case["moves"])
    )
    assert len(result.activity_frames) == len(case["moves"]) + 1
    assert observations(result) == (case["captures"], case["material"])
    for check in case["checks"]:
        assert read_check(result, check) == check["value"], (case["id"], check)

    # Replay is independently legal in python-chess; explicit JSON remains the fact oracle.
    board = chess.Board(case["fen"])
    assert board.is_valid()
    for i, uci in enumerate(case["moves"], 1):
        move = chess.Move.from_uci(uci)
        assert move in board.legal_moves
        board.push(move)
        observed = chess.Board(result.activity_frames[i].structural.position.fen)
        assert observed.piece_map() == board.piece_map()
        assert observed.turn == board.turn
    assert case["required"] and case["forbidden"] and case["alternative_needed"]


def mirror_square(square):
    return chess.square_name(chess.square_mirror(chess.parse_square(square)))


def mirror_move(uci):
    return mirror_square(uci[:2]) + mirror_square(uci[2:4]) + uci[4:]


def mirror_type_key(key):
    color, kind = key.split(":")
    return f"{'black' if color == 'white' else 'white'}:{kind}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_design_case_color_mirror_capture_and_material_oracles(case):
    rules, lines = build()
    initial = chess.Board(case["fen"]).mirror()
    result = lines.analyze(
        rules.position_from_fen(initial.fen()),
        tuple(ChessMove(mirror_move(m)) for m in case["moves"]),
    )
    expected_captures = [
        dict(
            c,
            landing=mirror_square(c["landing"]),
            victim_square=mirror_square(c["victim_square"]),
            victim=mirror_type_key(c["victim"]),
        )
        for c in case["captures"]
    ]
    expected_material = {mirror_type_key(k): v for k, v in case["material"].items()}
    assert observations(result) == (expected_captures, expected_material)
