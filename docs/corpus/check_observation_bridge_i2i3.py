"""Independent design-corpus checker for I2-D EXCHANGE and I3-D opt-in.

Usage:
    python docs/corpus/check_observation_bridge_i2i3.py --schema-only
    python docs/corpus/check_observation_bridge_i2i3.py --full

Does not import Calliope scenario/selector implementation or overwrite goldens.
I1-D has a separate independent checker; I3 output DTO and full scenario/ledger
mutation tests are distinct future implementation acceptance gates.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CORPUS = HERE / "observation-bridge-i2i3-v1.json"
EXCHANGE = ROOT / "tests" / "golden" / "scenario_explanation_cases.json"
UCI = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")
CLOSED = {"CAPTURE_NORMAL", "CAPTURE_EP", "FOCUS_LOSSES", "MATERIAL_COUNTS"}
IDS = tuple(f"E{i:02}" for i in range(1, 8))


def require(condition: bool, explanation: str) -> None:
    if not condition:
        raise AssertionError(explanation)


def check_schema(doc: dict, legacy: dict) -> None:
    require(doc["version"] == "calliope.observation_bridge_joint_design_v1", "bad corpus version")
    require(legacy["version"] == "scenario_explanation_corpus_v2", "legacy corpus changed")
    limits = doc["constraints"]
    require(limits["max_public_exchange_lines"] == 2, "line count")
    require(limits["max_public_plies_per_line"] == 8, "line depth")
    require(limits["max_observation_sentences_per_section"] == 2, "sentence cap")
    require(limits["max_observation_sentences_per_request"] == 6, "total cap")
    require(limits["legacy_exchange_bytes_unchanged"] is True, "legacy not sealed")
    old = {c["id"]: c for c in legacy["cases"]}
    cases = doc["cases"]
    require(tuple(c["id"] for c in cases) == IDS, "E01-E07 exact order")
    for case in cases:
        ident = case["id"]
        source = old[ident]
        require(all(case[k] == source[k] for k in ("fen", "focus")), ident+": root changed")
        require(case["moves"] == source["moves"], ident+": moves changed")
        require(case["request_origin"] == "USER", ident+": misleading source origin")
        require(case["cap"] == 2 and len(case["selected"]) <= 2, ident+": cap violation")
        require(case["expected_focus_capture_count"] ==
                sum(c["landing"] == source["focus"] for c in source["captures"]),
                ident+": wrong count")
        expected_status = ("FOCUS_CAPTURES_OBSERVED" if case["expected_focus_capture_count"]
                           else "NO_FOCUS_CAPTURE")
        require(case["expected_status"] == expected_status, ident+": wrong status")
        keys = [s["key"] for s in case["selected"]]
        require(len(keys) == len(set(keys)), ident+": duplicate selected")
        require(all(s["template_id"] in CLOSED and s["text"].endswith(".")
                    for s in case["selected"]), ident+": template/text")
        require(all(s["key"].startswith(("EVENTS/", "AGGREGATES/"))
                    for s in case["selected"]), ident+": unsupported simple golden")
        excluded = case["candidate_cap_exclusions"]
        require(set(excluded).isdisjoint(keys), ident+": excluded key selected")
        require(len(excluded) == len(set(excluded)), ident+": duplicate exclusion")
        for move in case["moves"]:
            require(UCI.fullmatch(move) is not None, ident+": noncanonical UCI")
        if ident == "E01":
            require(case["selected"] == [] and case["moves"] == [], "E01 nonempty")


def test_full(doc: dict) -> int:
    try:
        import chess
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install python-chess in project environment, or use --schema-only") from exc
    seen = 0
    for case in doc["cases"]:
        ident = case["id"]
        b = chess.Board(case["fen"])
        require(b.is_valid(), ident+": FEN invalid")
        initial = b.copy()
        events = {}
        captured_on_focus = Counter()
        for ply, uci in enumerate(case["moves"], 1):
            m = chess.Move.from_uci(uci)
            require(m in b.legal_moves, ident+": illegal supplied UCI "+uci)
            before = b.copy()
            if b.is_capture(m):
                victim_square = (m.to_square + (-8 if b.turn else 8)
                                 if b.is_en_passant(m) else m.to_square)
                victim = b.piece_at(victim_square)
                mover = b.piece_at(m.from_square)
                require(victim is not None and mover is not None, ident+": missing real capture")
                landing = chess.square_name(m.to_square)
                if landing == case["focus"]:
                    captured_on_focus[(victim.color, victim.piece_type)] += 1
                mover_desc = ("white" if mover.color else "black") + " " + chess.piece_name(mover.piece_type)
                victim_desc = ("white" if victim.color else "black") + " " + chess.piece_name(victim.piece_type)
                if before.is_en_passant(m):
                    text = (f"In the supplied line, at ply {ply}, {mover_desc} on "
                            f"{chess.square_name(m.from_square)} captures en passant, "
                            f"landing on {landing} and removing {victim_desc} on "
                            f"{chess.square_name(victim_square)} from {chess.square_name(victim_square)}.")
                    template = "CAPTURE_EP"
                else:
                    text = (f"In the supplied line, at ply {ply}, {mover_desc} on "
                            f"{chess.square_name(m.from_square)} captures {victim_desc} on {landing}.")
                    template = "CAPTURE_NORMAL"
                events[f"EVENTS/CAPTURE:ply{ply}:capture"] = (template, text)
            b.push(m)
        require(b.is_valid(), ident+": invalid resulting board")
        require(sum(captured_on_focus.values()) == case["expected_focus_capture_count"],
                ident+": real focus capture count")
        status = "FOCUS_CAPTURES_OBSERVED" if captured_on_focus else "NO_FOCUS_CAPTURE"
        require(status == case["expected_status"], ident+": derived status")
        counts = {}
        for color_name, color in (("white",chess.WHITE),("black",chess.BLACK)):
            for kind_name, kind in (("pawn",chess.PAWN),("knight",chess.KNIGHT),
                                     ("bishop",chess.BISHOP),("rook",chess.ROOK),
                                     ("queen",chess.QUEEN)):
                n0 = len(initial.pieces(kind,color))
                n1 = len(b.pieces(kind,color))
                if n0 != n1:
                    counts[f"AGGREGATES/MATERIAL_COUNTS:{color_name}:{kind_name}"] = (
                        "MATERIAL_COUNTS",
                        f"In the supplied line, at the supplied endpoint, the "
                        f"{color_name} {kind_name} count changes by {n1-n0:+d} relative to the initial frame."
                    )
                count = captured_on_focus[(color,kind)]
                if count:
                    counts[f"AGGREGATES/FOCUS_LOSSES:{color_name}:{kind_name}"] = (
                        "FOCUS_LOSSES",
                        f"In the supplied line, captures landing on {case['focus']} remove "
                        f"{count} {color_name} {kind_name} piece(s)."
                    )
        actual = {**events, **counts}
        for item in case["selected"]:
            key = item["key"]
            require(key in actual, ident+": selected candidate not observed "+key)
            require(actual[key] == (item["template_id"],item["text"]),
                    ident+": exact independent text mismatch "+key)
        for key in case["candidate_cap_exclusions"]:
            require(key in actual, ident+": cap-excluded candidate missing "+key)
        # The frozen total rank controls selected choice independent of
        # production selection code. Top candidates in E01-E07 are all
        # captures/focus-loss/material facts; no new heuristic tie breaker.
        def priority(key):
            if key.startswith("EVENTS/CAPTURE"):
                ply=int(key.split(":")[1].removeprefix("ply"))
                focus_landing=False
                if ply <= len(case["moves"]):
                    rewind=chess.Board(case["fen"])
                    for j,mv in enumerate(case["moves"],1):
                        cm=chess.Move.from_uci(mv)
                        if j==ply:
                            focus_landing=chess.square_name(cm.to_square)==case["focus"]
                            break
                        rewind.push(cm)
                return (0 if focus_landing else 1,ply,key)
            if key.startswith("AGGREGATES/FOCUS_LOSSES"):
                return (3,0,key)
            return (4,0,key)
        all_early = sorted(actual, key=priority)
        # For these seven cases E06 includes promotion (tier 2) not represented
        # in 'actual' dict; two focus captures beat it so the assertion stays valid.
        require([x["key"] for x in case["selected"]] == all_early[:2],
                ident+": top-two ranking changed under independent event/count oracle")
        seen += 1
    return seen


def main() -> None:
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--schema-only",action="store_true")
    group.add_argument("--full",action="store_true")
    args=parser.parse_args()
    doc=json.loads(CORPUS.read_text(encoding="utf-8"))
    legacy=json.loads(EXCHANGE.read_text(encoding="utf-8"))
    check_schema(doc,legacy)
    print(f"SCHEMA PASS: {len(doc['cases'])} compact E01-E07 frozen examples")
    if args.full:
        n=test_full(doc)
        print(f"CHESS PASS: {n} legal EXCHANGE fixtures and exact event/count texts")


if __name__=="__main__":
    main()
