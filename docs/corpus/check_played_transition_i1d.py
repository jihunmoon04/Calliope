"""Independent I1-D design corpus checker.

Pure JSON schema/ledger closure mode:
  python docs/corpus/check_played_transition_i1d.py --schema-only

FEN/UCI + independently computed board observations (requires project python-chess):
  python docs/corpus/check_played_transition_i1d.py --full

This is a *design oracle*, not an implementation-derived snapshot generator.
It never writes expected strings or calls Calliope production analyzers/Stockfish.
Full production candidate census, source provenance, EXCHANGE byte-compatibility,
P10/P11/P12 and exact integration output require subsequent I1 regression tests.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().with_name("played-transition-i1d-v1.json")
UCI = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")
CHANGE_SENTENCE = re.compile(
    r"In the supplied one-move line ([a-h][1-8][a-h][1-8][qrbn]?), "
    r"(.+) \[([A-Z_]+)\]: (.+) -> (.+)\.\Z"
)
CASES_REQUIRED = {f"D{i:02}" for i in range(1, 21)}
NEGATIVE_KINDS = {"NEGATIVE_PREFLIGHT", "NEGATIVE_CHESS_LEGALITY", "NEGATIVE_INTEGRITY"}
NON_POSITION_KINDS = {"LEGACY_BYTE_COMPAT", "PUBLIC_V02_COMPAT"}
CLOSED_TEMPLATES = {
    "CAPTURE_NORMAL", "CAPTURE_EP", "PROMOTION", "MOVE", "CASTLING_ROOK",
    "MATERIAL_COUNTS", "PLAYED_CHANGE",
}
BUCKET_ORDER = {"STEPS", "ENDPOINTS", "EVENTS", "AGGREGATES"}
EXCLUDE_REASONS = {"CONTEXT_ONLY", "SEMANTIC_DUPLICATE", "CAP_EXCEEDED"}
FORBIDDEN_CAUSAL = (" because ", " improves ", " superior ", " winning ", " forces ", " safer ")


def require(condition: bool, where: str) -> None:
    if not condition:
        raise AssertionError(where)


def prefix_id(identifier: str) -> str:
    return identifier.split("-")[0]


def is_key(value: object) -> bool:
    if not isinstance(value, str) or "/" not in value or ":" not in value:
        return False
    return value.split("/", 1)[0] in BUCKET_ORDER


def check_schema(doc: dict) -> int:
    require(doc["schema"] == "calliope.i1d.corpus.v1", "schema")
    c = doc["contract"]
    require(c["kind"] == "PLAYED_TRANSITION", "kind")
    require(c["cap"] == 2 and c["expected_row_count"] == 21, "cap/row count")
    require(c["snapshots"] == 0 and c["max_plies"] == 1, "no snapshots/one ply")
    cases = doc["cases"]
    ids = [case["id"] for case in cases]
    require(len(ids) == len(set(ids)), "duplicate case id")
    require(CASES_REQUIRED <= {prefix_id(case_id) for case_id in ids}, "missing D01-D20")

    positives = 0
    for case in cases:
        ident = case["id"]
        kind = case["kind"]
        require(kind in {"PLAYED_TRANSITION", *NEGATIVE_KINDS, *NON_POSITION_KINDS, "POSITIVE_PREFLIGHT"}, ident + ": kind")
        if kind != "PLAYED_TRANSITION":
            require("digest" not in case, ident + ": negative/compat has fake digest")
            if kind in NEGATIVE_KINDS:
                require(bool(case["expected_error"]), ident + ": error expected")
            continue

        positives += 1
        require(case["target_uci"] == case["uci"], ident + ": target/line UCI")
        require(UCI.fullmatch(case["uci"]) is not None, ident + ": noncanonical UCI")
        require(case["max_plies"] == 1, ident + ": max_plies")
        require(case["accounting"] == {"rows": 21, "snapshots": 0, "focus_losses": 0}, ident + ": matrix")
        participants = case["participants"]
        require(bool(participants) and len(set(participants)) == len(participants), ident + ": participant keys")
        require(all(re.fullmatch(r"[a-h][1-8]", p) for p in participants), ident + ": base squares")
        require(case["core_excluded_exact"] == [], ident + ": core exclusions")
        included = set(case["core_included_contains"] + case.get("core_included_contains_extra", []))
        require(all(is_key(k) for k in included), ident + ": core keys")
        require(len(included) == len(case["core_included_contains"] + case.get("core_included_contains_extra", [])), ident + ": duplicate core key")

        ledger = case["ledger_checks"]
        digest = case["digest"]
        require(1 <= len(digest) <= 2, ident + ": capped digest")
        actual_included = {e["key"] for e in ledger if e["decision"] == "INCLUDE"}
        expected_digest = {e["key"] for e in digest}
        require(actual_included == expected_digest, ident + ": selected keys not equal ledger INCLUDES")
        require(len(actual_included) == len(digest), ident + ": repeated digest")
        ledger_keys = [entry["key"] for entry in ledger]
        require(len(ledger_keys) == len(set(ledger_keys)), ident + ": repeated ledger origin")
        for entry in ledger:
            key, decision, reason = entry["key"], entry["decision"], entry["reason"]
            require(is_key(key), ident + ": invalid ledger key")
            require(key in included, ident + ": assertion refers to nonincluded core key " + key)
            require((decision == "INCLUDE" and reason is None) or (decision == "EXCLUDE" and reason in EXCLUDE_REASONS),
                    ident + ": invalid decision/reason")
            if reason == "SEMANTIC_DUPLICATE":
                anchor = entry["duplicate_of"]
                require(key.startswith("ENDPOINTS/") and anchor.startswith("STEPS/"), ident + ": duplicate direction")
                require(anchor in included, ident + ": duplicate anchor missing")
                require(key.removeprefix("ENDPOINTS/") == anchor.removeprefix("STEPS/"),
                        ident + ": duplicate property identity")
            if reason == "CAP_EXCEEDED":
                require(key not in expected_digest, ident + ": selected cap exclusion")
        for sentence in digest:
            key, template, value = sentence["key"], sentence["template_id"], sentence["text"]
            require(template in CLOSED_TEMPLATES, ident + ": unknown TemplateId")
            require(value and value.endswith("."), ident + ": incomplete sentence")
            require(not any(x in value.lower() for x in FORBIDDEN_CAUSAL), ident + ": causal claim")
            if template == "PLAYED_CHANGE":
                match = CHANGE_SENTENCE.fullmatch(value)
                require(match is not None, ident + ": PLAYED_CHANGE exact grammar")
                move, _, family, before, after = match.groups()
                require(move == case["uci"], ident + ": sentence UCI")
                require(key.startswith("STEPS/" + family + ":"), ident + ": template/fact family")
                require(before != after, ident + ": nonchanged fact")
            else:
                require(value.startswith("In the supplied line, "), ident + ": legacy event/count grammar")
                require(key.startswith("EVENTS/") or key.startswith("AGGREGATES/"), ident + ": template bucket")
        for entry in ledger:
            if entry["key"].startswith("ENDPOINTS/"):
                require(entry["decision"] == "EXCLUDE" and entry["reason"] == "SEMANTIC_DUPLICATE",
                        ident + ": all endpoint observations must duplicate one-ply steps")
        require(case["accounting"]["rows"] == 21, ident + ": rows changed")
    require(positives >= 15, "insufficient real positive corpus")
    return positives


def verify_python_chess(doc: dict) -> int:
    try:
        import chess
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Full mode requires installed python-chess; run in the Calliope dev environment "
            "or use --schema-only for dependency-free corpus closure."
        ) from exc

    tested = 0
    for case in doc["cases"]:
        kind = case["kind"]
        if kind not in ("PLAYED_TRANSITION", "POSITIVE_PREFLIGHT"):
            continue
        ident = case["id"]
        board = chess.Board(case["fen"])
        require(board.is_valid(), ident + ": illegal FEN")
        move = chess.Move.from_uci(case["uci"])
        require(move in board.legal_moves, ident + ": illegal UCI")
        tested += 1
        if kind == "POSITIVE_PREFLIGHT":
            continue

        # This oracle uses python-chess' independent board geometry, not the
        # Calliope activity/scenario analyzer or its expected-output generator.
        mover = board.piece_at(move.from_square)
        require(mover is not None, ident + ": no physical mover")
        parts = {chess.square_name(move.from_square)}
        victim_square = None
        if board.is_capture(move):
            if board.is_en_passant(move):
                victim_square = move.to_square + (-8 if board.turn == chess.WHITE else 8)
            else:
                victim_square = move.to_square
            require(board.piece_at(victim_square) is not None, ident + ": no captured piece")
            parts.add(chess.square_name(victim_square))
        if board.is_castling(move):
            if chess.square_file(move.to_square) == 6:  # kingside
                rook_square = chess.H1 if board.turn else chess.H8
            else:
                rook_square = chess.A1 if board.turn else chess.A8
            parts.add(chess.square_name(rook_square))
        require(parts == set(case["participants"]), ident + ": participant base mismatch")
        if "en_passant" in case:
            ep = case["en_passant"]
            require(board.is_en_passant(move), ident + ": not EP")
            require(chess.square_name(victim_square) == ep["captured_square"], ident + ": EP victim")
            require(chess.square_name(move.to_square) == ep["landing_square"], ident + ": EP landing")

        before = board.copy()
        board.push(move)
        require(board.is_valid(), ident + ": resulting board invalid")
        for change in case["digest"]:
            if change["template_id"] != "PLAYED_CHANGE":
                continue
            key, value = change["key"], change["text"]
            match = CHANGE_SENTENCE.fullmatch(value)
            assert match is not None
            _, _, family, left, right = match.groups()
            if family == "ATTACK_FOOTPRINT":
                base = key.split("base-")[1]
                source = chess.parse_square(base)
                target = move.to_square if source == move.from_square else source
                for observed_board, sq, asserted in ((before, source, left), (board, target, right)):
                    observed = tuple(
                        sorted((chess.square_name(s) for s in observed_board.attacks(sq)),
                               key=lambda a: chess.parse_square(a))
                    )
                    expected = "geometric squares=(" + ", ".join(observed) + ")"
                    require(expected == asserted, ident + ": geometry expected value mismatch")
            elif family == "PIN_PRESENT":
                pinned = re.search(r"pinned=([a-h][1-8])", value)
                assert pinned is not None
                sq = chess.parse_square(pinned.group(1))
                owner_before = before.piece_at(sq)
                owner_after = board.piece_at(sq)
                require(owner_before is not None and owner_after is not None, ident + ": pin victim missing")
                require(str(before.is_pinned(owner_before.color, sq)).lower() == left,
                        ident + ": before pin")
                require(str(board.is_pinned(owner_after.color, sq)).lower() == right,
                        ident + ": after pin")
            elif family == "FILE_STATE":
                file_letter = key.split("file-")[1]
                idx = ord(file_letter) - ord("a")
                def counts(snap):
                    return (
                        sum(bool(snap.piece_at(chess.square(idx, rank)) and
                                 snap.piece_at(chess.square(idx, rank)).piece_type == chess.PAWN and
                                 snap.piece_at(chess.square(idx, rank)).color == color)
                            for rank in range(8))
                        for color in (chess.WHITE, chess.BLACK)
                    )
                def state(w, b):
                    return ("open" if not w and not b
                            else "semi-open for white" if not w
                            else "semi-open for black" if not b
                            else "neither")
                for snapshot, target in ((before, left), (board, right)):
                    w, b = tuple(counts(snapshot))
                    expected = f"white_pawns={w}, black_pawns={b}, state={state(w,b)}"
                    require(expected == target, ident + ": file state differs")
            elif family == "PAWN_SUPPORTERS":
                base = key.split("base-")[1]
                pawn_sq = chess.parse_square(base)
                for snap, asserted in ((before, left), (board, right)):
                    pawn = snap.piece_at(pawn_sq)
                    if pawn is None or pawn.piece_type != chess.PAWN:
                        raise AssertionError(ident + ": stationary pawn supporter subject gone")
                    attacked_from = (
                        pawn_sq - 7, pawn_sq - 9
                    ) if pawn.color == chess.WHITE else (pawn_sq + 7, pawn_sq + 9)
                    bases = []
                    for square in attacked_from:
                        if not 0 <= square < 64 or abs(chess.square_file(square)-chess.square_file(pawn_sq)) != 1:
                            continue
                        piece = snap.piece_at(square)
                        if piece and piece.color == pawn.color and piece.piece_type == chess.PAWN:
                            # For the independent oracle, map the moving pawn back to
                            # its base square rather than its current square.
                            base_square = move.from_square if square == move.to_square else square
                            bases.append(chess.square_name(base_square))
                    expected = "geometric pawn supporters=(" + ", ".join(sorted(bases, key=chess.parse_square)) + ")"
                    require(expected == asserted, ident + ": pawn support mismatch")
        if case.get("remote_affected_subjects") and ident in ("D08", "D19"):
            require(before.attacks(chess.E1) != board.attacks(chess.E1), ident + ": remote rook footprint unchanged")
            require(not before.is_pinned(chess.BLACK, chess.E7) and board.is_pinned(chess.BLACK, chess.E7),
                    ident + ": remote pin not created")
        if "remotely_changed_pawn_flags" in case:
            item = case["remotely_changed_pawn_flags"]
            base = chess.parse_square(item["base"])
            color = chess.WHITE
            def flags(snap):
                pawns = [sq for sq, p in snap.piece_map().items()
                         if p.piece_type == chess.PAWN and p.color == color]
                sq_file, sq_rank = chess.square_file(base), chess.square_rank(base)
                isolated = not any(abs(chess.square_file(sq)-sq_file) == 1 for sq in pawns if sq != base)
                doubled = any(chess.square_file(sq) == sq_file for sq in pawns if sq != base)
                foes = [sq for sq,p in snap.piece_map().items()
                        if p.piece_type == chess.PAWN and p.color != color]
                passed = not any(abs(chess.square_file(sq)-sq_file) <= 1 and
                                 chess.square_rank(sq) > sq_rank for sq in foes)
                return {"isolated": isolated, "doubled": doubled, "passed": passed}
            require(flags(before) == item["before"], ident + ": initial passed flag")
            require(flags(board) == item["after"], ident + ": endpoint passed flag")
    return tested


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--schema-only", action="store_true")
    group.add_argument("--full", action="store_true")
    args = parser.parse_args()
    doc = json.loads(HERE.read_text(encoding="utf-8"))
    positives = check_schema(doc)
    print(f"SCHEMA PASS: {len(doc['cases'])} scenarios, {positives} positive exact-digest records")
    if args.full:
        verified = verify_python_chess(doc)
        print(f"CHESS PASS: {verified} board/FEN/UCI fixtures checked with python-chess")


if __name__ == "__main__":
    main()
