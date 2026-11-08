"""LT-D: the line ledger (§2), scores for the mover and the ranking (§3), and the square entries of
`squares` (§4).

Pure functions over the records the session already projects: `explore`'s plies (each a projected
`move` fact and the material balance), a search line's score, and the `pieces` and `exchange`
families. They compute what the agent used to work out by hand — who took what from whom, who is
ahead at a line's end, which move is better for the side that played it, what attacks and defends a
square — and never change the records they read.
"""

from __future__ import annotations

from itertools import pairwise

import chess

from .brief import LETTERS, _name, _pinner, _squares, _worth
from .digest import numbered, score_text

FAVOUR_BAND = 30  # LT-D §2, §7 Q3: within ±0.30 a score favours neither side
CLOSE_BAND = 30  # LT-D §3: two centipawn scores within ±0.30 are marked `close`
TERMINAL_DRAWS = (
    "stalemate",
    "insufficient_material",
    "seventyfive_moves",
    "fivefold_repetition",
)
LEDGER_NOTE = (
    "net: points_v1 from the line's start, per side (+ = ahead); captured: what each side took; "
    "end: pieces that moved or left the board; side: who moved, source: agent (your moves) or "
    "engine (appended by continue)"
)


def other(side: str) -> str:
    return "black" if side == "white" else "white"


def terminal_status(board: chess.Board) -> str | None:
    """The board's ending (LT-D re-review R1): checkmate or one of the draws `is_game_over`
    (claim_draw=False) knows; None while the game goes on."""

    outcome = board.outcome(claim_draw=False)
    if outcome is None:
        return None
    return outcome.termination.name.lower()


def terminal_score(board: chess.Board) -> dict | None:
    """A finished position's value: `{"terminal": "checkmate", "winner": side}` or
    `{"terminal": "<draw>"}`; None while the game goes on."""

    status = terminal_status(board)
    if status is None:
        return None
    if status == "checkmate":
        return {"terminal": "checkmate", "winner": "black" if board.turn else "white"}
    return {"terminal": status}


# -- scores (LT-D §2, §3) ---------------------------------------------------------------------


def for_side(score: dict | None, side: str) -> dict | None:
    """A White's-view score (`{"cp": n}` or `{"mate": n}`) in `side`'s view: + is good for it."""

    if not score:
        return None
    if "terminal" in score:
        return dict(score)
    sign = 1 if side == "white" else -1
    if score.get("mate") is not None:
        return {"mate": sign * score["mate"]}
    if score.get("cp") is not None:
        return {"cp": sign * score["cp"]}
    return None


def favours(score: dict | None) -> str | None:
    """The side a White's-view score is good for: `neither` within the band, a mate for the side
    that mates, a terminal position for its winner (a draw: neither)."""

    if not score:
        return None
    if "terminal" in score:
        return score.get("winner") or "neither"
    if score.get("mate") is not None:
        return "white" if score["mate"] > 0 else "black"
    cp = score.get("cp")
    if cp is None:
        return None
    if abs(cp) <= FAVOUR_BAND:
        return "neither"
    return "white" if cp > 0 else "black"


def mover_text(score: dict | None) -> str | None:
    """A mover's-view score as text: `+1.20`, `mate in 3 for the mover`, `mate in 2 against the
    mover`, `checkmate`, a draw's name."""

    if not score:
        return None
    if "terminal" in score:
        return score["terminal"]
    if score.get("mate") is not None:
        n = score["mate"]
        return f"mate in {n} for the mover" if n > 0 else f"mate in {-n} against the mover"
    return score_text({"cp": score.get("cp")})


def rank_key(score: dict | None, mover: str) -> tuple[int, int] | None:
    """LT-D §3's order, higher first: a checkmate by the move; a mate for the mover (shorter
    first); centipawns and drawn endings (0.00); a mate against the mover (longer first). `score`
    is in the mover's view (`for_side`), or a terminal value."""

    if not score:
        return None
    if "terminal" in score:
        if score["terminal"] == "checkmate":
            return (4, 0) if score.get("winner") == mover else (0, 0)
        return (2, 0)
    if score.get("mate") is not None:
        n = score["mate"]
        return (3, -n) if n > 0 else (1, -n)
    if score.get("cp") is not None:
        return (2, score["cp"])
    return None


def centipawns(score: dict | None) -> int | None:
    """A mover's-view score as centipawns when it is one (a drawn ending counts 0)."""

    if not score:
        return None
    if "terminal" in score:
        return 0 if score["terminal"] != "checkmate" else None
    if score.get("mate") is not None:
        return None
    return score.get("cp")


def vs_played(score: dict | None, played: dict | None) -> str | None:
    """LT-D §3: the difference for the mover against the move played; a text when a mate or a
    checkmate is involved; None when either has no score."""

    if not score or not played:
        return None
    a, b = centipawns(score), centipawns(played)
    if a is not None and b is not None:
        return score_text({"cp": a - b})
    return f"{mover_text(score)} against {mover_text(played)}"


def ranking(entries: list[dict], mover: str) -> tuple[list[dict], list[dict]]:
    """Order the scored entries (each with `for_mover`) for `mover`, stable on the given order
    (played, best, candidates); an entry without a score goes to `unranked` (LT-D §3)."""

    scored = [e for e in entries if rank_key(e.get("for_mover"), mover) is not None]
    unranked = [e for e in entries if rank_key(e.get("for_mover"), mover) is None]
    ordered = sorted(scored, key=lambda e: rank_key(e["for_mover"], mover), reverse=True)
    played = next((e for e in entries if e.get("role") == "played"), None)
    played_score = (played or {}).get("for_mover")
    for i, entry in enumerate(ordered):
        entry["rank"] = i + 1
        if played_score is not None:
            entry["vs_played"] = vs_played(entry["for_mover"], played_score)
    for a, b in pairwise(ordered):
        ca, cb = centipawns(a["for_mover"]), centipawns(b["for_mover"])
        if ca is not None and cb is not None and abs(ca - cb) <= CLOSE_BAND:
            b["close"] = True
    return ordered, unranked


# -- the line ledger (LT-D §2) ----------------------------------------------------------------


def _event_kind(event: dict) -> str | None:
    if "en_passant" in event:
        return "capture"
    if "to" in event:
        return "promotion"
    if "from_square" in event:
        return "castling"
    return None


def _piece_name(kind: str | None, color: str | None, square: str | None) -> str:
    letter = LETTERS.get(kind or "", "?")
    return (letter.upper() if color == "white" else letter) + str(square)


def _says(move: dict) -> str:
    side = move.get("mover")
    who = "White's" if side == "white" else "Black's"
    kind = move.get("piece_type")
    if move.get("castling"):
        text = f"{who} king castles {move['castling']}"
    else:
        text = f"{who} {kind} {move.get('from_square')}→{move.get('to_square')}"
    for event in move.get("events") or []:
        if not isinstance(event, dict):
            continue
        if _event_kind(event) == "capture":
            owner = "Black's" if side == "white" else "White's"
            points = _worth(event.get("piece_type"))
            ep = ", en passant" if event.get("en_passant") else ""
            text += (
                f" takes {owner} {event.get('piece_type')} on {event.get('square')} ({points}{ep})"
            )
        elif _event_kind(event) == "promotion":
            text += f", promotes to {event.get('to')}"
    if move.get("gives_mate"):
        text += ", checkmate"
    elif move.get("gives_check"):
        text += ", check"
    return text


def ledger(plies: list[dict], start_fen: str, sources: list[str] | None = None) -> dict:
    """§2: the ledger of `explore`'s plies, from `start_fen`. `sources[i]` is the i-th ply's
    `agent` or `engine` (default `agent`)."""

    fields = start_fen.split()
    white_first = fields[1] == "w"
    number = int(fields[5]) if len(fields) > 5 and fields[5].isdigit() else 1
    rows, captured = [], {"by_white": [], "by_black": []}
    final: dict[tuple, tuple] = {}  # identity → (type now, colour, square)
    start: dict[tuple, str] = {}
    gone: list[str] = []
    side_white = white_first
    for i, ply in enumerate(plies):
        move = ply.get("move") or {}
        side = move.get("mover") or ("white" if side_white else "black")
        san = numbered(number, side, move.get("san") or "?")
        row = {"ply": ply.get("ply", i + 1), "san": san, "says": _says(move), "side": side,
               "source": (sources[i] if sources and i < len(sources) else "agent"),
               "check": bool(move.get("gives_check"))}  # fmt: skip
        if move.get("gives_mate"):
            row["mate"] = True
        piece = move.get("piece") or {}
        key = (piece.get("color"), piece.get("origin"))
        start.setdefault(key, move.get("from_square"))
        final[key] = (piece.get("type_now") or move.get("piece_type"), piece.get("color"),
                      piece.get("square") or move.get("to_square"))  # fmt: skip
        for event in move.get("events") or []:
            if not isinstance(event, dict):
                continue
            kind = _event_kind(event)
            if kind == "capture":
                victim = event.get("piece") or {}
                owner = victim.get("color") or other(side)
                points = _worth(event.get("piece_type"))
                row["captured"] = {"piece": event.get("piece_type"), "owner": owner,
                                   "square": event.get("square"), "points": points}  # fmt: skip
                if event.get("en_passant"):
                    row["captured"]["en_passant"] = True
                label = f"{event.get('piece_type')} {event.get('square')} ({points})"
                captured["by_white" if side == "white" else "by_black"].append(label)
                vkey = (owner, victim.get("origin"))
                final.pop(vkey, None)
                gone.append(_piece_name(event.get("piece_type"), owner, event.get("square")))
            elif kind == "promotion":
                row["promotion"] = event.get("to")
            elif kind == "castling":
                rook = event.get("piece") or {}
                rkey = (rook.get("color"), rook.get("origin"))
                start.setdefault(rkey, event.get("from_square"))
                final[rkey] = ("rook", rook.get("color"), event.get("to_square"))
        rows.append(row)
        if side == "black":
            number += 1
        side_white = side == "black"
    balance = plies[-1].get("material_balance_white", 0) if plies else 0
    balance = balance if isinstance(balance, int) and not isinstance(balance, bool) else 0
    first = rows[0]["side"] if rows else ("white" if white_first else "black")
    moved = [_piece_name(kind, color, square) for key, (kind, color, square) in final.items()
             if square is not None and square != start.get(key)]  # fmt: skip
    return {
        "plies": rows,
        "captured": captured,
        "net": {
            "white": balance,
            "black": -balance,
            "first_mover": first,
            "for_first_mover": balance if first == "white" else -balance,
        },
        "end": {"moved_pieces": moved, "gone": gone},
        "note": LEDGER_NOTE,
    }


def outcome(full: dict) -> dict:
    """A ledger without its per-ply list (`compare_lines`' lines, LT-D §3)."""

    return {k: v for k, v in full.items() if k in ("captured", "net", "end")}


def end_score(score: dict | None, side_to_move: str, score_ref: str | None = None,
              at: int | None = None) -> dict | None:  # fmt: skip
    """A line's end score (§2): White's view, the side to move's view, the side it favours."""

    if not score:
        return None
    if "terminal" in score:
        return {**score, "favours": favours(score), "score_ref": None}
    mover = mover_text(for_side(score, side_to_move))
    out = {
        "white_view": score_text(score),
        "for_side_to_move": mover,
        "favours": favours(score),
        "score_ref": score_ref,
    }
    if at is not None:
        out["end_score_at"] = at
    return out


# -- squares (LT-D §4) ------------------------------------------------------------------------


def _identity_key(entry: dict | None) -> tuple | None:
    if not isinstance(entry, dict):
        return None
    identity = entry.get("identity")
    if isinstance(identity, dict):
        return (identity.get("color"), identity.get("origin"))
    return (entry.get("color"), entry.get("square"))


def _relation(item: dict, by_square: dict, color: str, target: str | None, attacker: bool) -> dict:
    square = item.get("square")
    entry = by_square.get(square) or {}
    kind = item.get("piece_type") or entry.get("piece_type")
    out = {"piece": _name({"piece_type": kind, "square": square}, color)}
    pinner = _pinner(entry)
    if item.get("absolutely_pinned") is True or pinner is not None:
        pinning = by_square.get(pinner) if pinner else None
        out["absolutely_pinned"] = {"pinner": _name(pinning) if pinning else pinner}
    if attacker and target is not None:
        out["can_move_there"] = target in _squares(entry.get("legal_destinations"))
    return out


def square_entry(square: str, pieces: list[dict], exchange: dict | None) -> dict:
    """One square of `squares` (§4, re-review R2): an occupied square's attackers and defenders
    from its piece's record; an empty square's attackers by reverse lookup of every piece's
    `attacks.empty`. Pinned pieces are included and marked; attackers say whether they can move
    there legally."""

    by_square = {e["square"]: e for e in pieces if isinstance(e, dict) and "square" in e}
    entry = by_square.get(square)
    if entry is not None:
        color = entry.get("color")
        out = {"square": square, "piece": _name(entry),
               "attackers": [_relation(i, by_square, other(color), square, True)
                             for i in entry.get("attackers") or [] if isinstance(i, dict)],
               "defenders": [_relation(i, by_square, color, square, False)
                             for i in entry.get("defenders") or [] if isinstance(i, dict)]}  # fmt: skip
        pinner = _pinner(entry)
        if pinner is not None:
            pinning = by_square.get(pinner)
            out["absolutely_pinned"] = {"pinner": _name(pinning) if pinning else pinner}
        if isinstance(exchange, dict):
            for item in exchange.get("pieces") or []:
                if isinstance(item, dict) and item.get("square") == square:
                    out["exchange"] = {k: v for k, v in item.items() if k != "square"}
        return out
    attackers: dict[str, list] = {"white": [], "black": []}
    for e in pieces:
        attacks = e.get("attacks") if isinstance(e, dict) else None
        if isinstance(attacks, dict) and square in _squares(attacks.get("empty")):
            item = {"square": e["square"], "piece_type": e.get("piece_type")}
            attackers[e.get("color", "white")].append(
                _relation(item, by_square, e.get("color"), square, True)
            )
    return {"square": square, "piece": None, "attackers": attackers}


def changed_by_move(square: str, before: list[dict], after: list[dict]) -> dict:
    """§4: what the move removed, added and left among the square's attackers and defenders, by
    piece identity (a piece that moved keeps its identity and is named where it stands now)."""

    b_sq = {e["square"]: e for e in before if isinstance(e, dict) and "square" in e}
    a_sq = {e["square"]: e for e in after if isinstance(e, dict) and "square" in e}
    b_entry, a_entry = b_sq.get(square), a_sq.get(square)
    if (b_entry is None) != (a_entry is None) or (
        b_entry is not None and a_entry is not None and b_entry.get("color") != a_entry.get("color")
    ):
        return {"occupant_changed": True}
    if a_entry is None:
        return {"empty": True}
    out = {}
    for role in ("attackers", "defenders"):
        b_items = [i for i in b_entry.get(role) or [] if isinstance(i, dict)]
        a_items = [i for i in a_entry.get(role) or [] if isinstance(i, dict)]
        b_keys = {_identity_key(b_sq.get(i["square"])) or i["square"]: i for i in b_items}
        a_keys = {_identity_key(a_sq.get(i["square"])) or i["square"]: i for i in a_items}
        color = a_entry.get("color") if role == "defenders" else other(a_entry.get("color"))

        def named(item, records, color=color):
            kind = item.get("piece_type") or (records.get(item["square"]) or {}).get("piece_type")
            return _name({"piece_type": kind, "square": item["square"]}, color)

        out[role] = {
            "lost": [named(i, b_sq) for k, i in b_keys.items() if k not in a_keys],
            "gained": [named(i, a_sq) for k, i in a_keys.items() if k not in b_keys],
            "kept": [named(i, a_sq) for k, i in a_keys.items() if k in b_keys],
        }
    return out
