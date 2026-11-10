"""TO-D §2: the brief views of `explore` and `facts`.

The handle an answer serves keeps the full record; the brief view is what the model reads. `pieces`
keeps the pieces in play (§2.1, review B3), each with the fields that say why, and names every piece
it left out; `exchange` keeps the exposed pieces (§2.2). Other families pass through. The functions
read the projected records (`projection.project`) and never change them.
"""

from __future__ import annotations

from calliope.facts import POINTS_V1_BY_TYPE, PieceType

KING_WORTH = 100  # above any piece: a king attacked is a check, never a lesser attacker's gain
LETTERS = {"pawn": "p", "knight": "n", "bishop": "b", "rook": "r", "queen": "q", "king": "k"}
VIEWS = ("brief", "full")
FLAGS = ("attacked_without_defender", "attackers_exceed_defenders")
OMITTED_NOTE = (
    "omitted: pieces nothing attacks, not pinned, attacking no enemy piece, defending no kept "
    "piece, not in check and not on the last move's square. Pieces are named by letter (upper "
    "case White, lower case Black) and square. detail(ref) gives every record."
)
ENTRY_NOTE = (
    "each kept piece: attackers, defenders and attacks (enemy pieces it attacks) by name, "
    '"pinned" after an attacker or defender that is absolutely pinned; absolutely_pinned names '
    "the piece pinning it; the flags shown are the true ones"
)


def _squares(items) -> list[str]:
    out = []
    for item in items or []:
        if isinstance(item, dict) and isinstance(item.get("square"), str):
            out.append(item["square"])
        elif isinstance(item, str):
            out.append(item)
    return out


def _gain(entry: dict) -> int:
    gain = entry.get("gain")
    value = gain.get("value") if isinstance(gain, dict) else gain
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def exposed_squares(exchange: dict | None) -> set[str]:
    """The squares `exchange` (see_v1) finds a non-zero gain on for the side that starts."""

    if not isinstance(exchange, dict):
        return set()
    return {
        e["square"] for e in exchange.get("pieces") or [] if isinstance(e, dict) and _gain(e) > 0
    }


def _worth(kind) -> int:
    """A piece type's points_v1 value from the fact engine's table (DF-D D4), by its name; a king
    is worth more than any piece."""

    try:
        return POINTS_V1_BY_TYPE.get(PieceType(str(getattr(kind, "value", kind))), KING_WORTH)
    except ValueError:
        return KING_WORTH


def _pinner(entry: dict) -> str | None:
    """The square of the piece that pins this one absolutely, or None (TO review N1).

    A piece's `absolutely_pinned` is the fact engine's `Pin | None` (`pieces.PieceFacts`): its
    projection is `{"pinner": square, "direction": …}` or None. An attacker's or defender's
    `absolutely_pinned` is a bool (`geometry.Relation`) and is read by `_named`, not here."""

    pin = entry.get("absolutely_pinned")
    if isinstance(pin, dict) and isinstance(pin.get("pinner"), str):
        return pin["pinner"]
    return None


def _lesser_attacker(entry: dict) -> bool:
    if not entry.get("attacker_count"):
        return False
    lowest = entry.get("lowest_attacker_types")
    types = lowest.get("value") if isinstance(lowest, dict) else lowest
    if not isinstance(types, list) or not types:
        return False
    worth = _worth(entry.get("piece_type"))
    return min(_worth(t) for t in types) < worth


def _attacked_enemies(entry: dict) -> list[str]:
    attacks = entry.get("attacks")
    return _squares(attacks.get("enemy")) if isinstance(attacks, dict) else []


def kept_squares(pieces: list[dict], exposed: set[str], checked: dict | None,
                 last_square: str | None) -> set[str]:  # fmt: skip
    """§2.1's rules 1–8 and the implementation's 9–10 (A1): the squares of the pieces in play."""

    by_square = {e["square"]: e for e in pieces if isinstance(e, dict) and "square" in e}
    kept = set(exposed) & set(by_square)  # 1: exposed
    for square in exposed:  # 2: every attacker and defender of an exposed piece's square
        entry = by_square.get(square)
        if entry:
            kept |= set(_squares(entry.get("attackers"))) | set(_squares(entry.get("defenders")))
    for square, entry in by_square.items():
        if _lesser_attacker(entry):  # 3
            kept.add(square)
        if entry.get("attacker_count") and (entry.get("attacked_without_defender") is True
                                            or entry.get("attackers_exceed_defenders") is True):  # fmt: skip
            kept.add(square)  # 4
        if _pinner(entry) is not None:  # 5
            kept.add(square)
    first = set(kept)
    for square, entry in by_square.items():  # 6: attacking a kept piece, or two or more pieces
        enemies = _attacked_enemies(entry)
        if len(enemies) >= 2 or set(enemies) & first:
            kept.add(square)
    if isinstance(checked, dict) and checked.get("in_check"):  # 7: the king in check, its checkers
        mover = checked.get("side_to_move")
        kept |= {s for s, e in by_square.items()
                 if e.get("piece_type") == "king" and e.get("color") == mover}  # fmt: skip
        kept |= set(_squares(checked.get("checkers")))
    if last_square:  # 8
        kept.add(last_square)
    # TO implementation A1 (the replay of TO-D §6.1): rules 1–8 lost 10 of 88 key-cause squares
    # (a sacrifice's target defended three times, a pawn the queen takes later in a line) and 65 of
    # 303 squares the agents cited. 9: every piece attacked, pinned or attacking an enemy piece;
    # 10: the defenders of every kept piece. Replayed: 88 of 88 and 302 of 303, `pieces` at a median
    # of 2,824 characters against 1,670 (the full record 10,187).
    for square, entry in by_square.items():
        if entry.get("attacker_count") or _pinner(entry) is not None or _attacked_enemies(entry):
            kept.add(square)  # 9
    for square in list(kept):  # 10
        kept |= set(_squares((by_square.get(square) or {}).get("defenders")))
    return kept & set(by_square)


def _name(entry: dict, color: str | None = None) -> str:
    letter = LETTERS.get(entry.get("piece_type"), "?")
    white = (color or entry.get("color")) == "white"
    return (letter.upper() if white else letter) + str(entry.get("square"))


def _named(items, color: str, by_square: dict) -> list[str]:
    """Attackers or defenders by name (`Nf5`), `pinned` added when absolutely pinned (A2)."""

    out = []
    for item in items or []:
        if not isinstance(item, dict) or "square" not in item:
            continue
        kind = item.get("piece_type") or (by_square.get(item["square"]) or {}).get("piece_type")
        name = _name({"piece_type": kind, "square": item["square"]}, color)
        out.append(name + " pinned" if item.get("absolutely_pinned") is True else name)
    return out


def _brief_entry(entry: dict, by_square: dict) -> dict:
    """A kept piece (A2): its name, origin, attackers, defenders and the enemy pieces it attacks by
    name, the flags that are true; counts and lowest attacker types follow from the lists."""

    color = entry.get("color")
    enemy = "black" if color == "white" else "white"
    out = {"piece": _name(entry)}
    identity = entry.get("identity")
    if isinstance(identity, dict) and identity.get("origin") not in (None, entry.get("square")):
        out["origin"] = identity["origin"]
    attackers = _named(entry.get("attackers"), enemy, by_square)
    if attackers:
        out["attackers"] = attackers
    defenders = _named(entry.get("defenders"), color, by_square)
    if defenders:
        out["defenders"] = defenders
    targets = [_name(by_square[s]) for s in _attacked_enemies(entry) if s in by_square]
    if targets:
        out["attacks"] = targets
    for flag in FLAGS:
        if entry.get(flag) is True:
            out[flag] = True
    pinner = _pinner(entry)
    if pinner is not None:  # TO review N1: the pin and its pinner, by name
        pinning = by_square.get(pinner)
        out["absolutely_pinned"] = {"pinner": _name(pinning) if pinning else pinner}
    capturable = entry.get("legally_capturable_now")
    if capturable is not None and not (isinstance(capturable, dict) and "sentinel" in capturable):
        out["legally_capturable_now"] = capturable
    return out


def brief_pieces(record, exchange: dict | None, status: dict | None, last_square: str | None):
    """The `pieces` record in its brief view; anything that is not a pieces list passes through."""

    if not isinstance(record, dict) or not isinstance(record.get("pieces"), list):
        return record
    pieces = record["pieces"]
    by_square = {e["square"]: e for e in pieces if isinstance(e, dict) and "square" in e}
    kept = kept_squares(pieces, exposed_squares(exchange), status, last_square)
    shown = [_brief_entry(e, by_square) for e in pieces if e.get("square") in kept]
    omitted = [_name(e) for e in pieces if e.get("square") not in kept]
    out = {k: v for k, v in record.items() if k != "pieces"}
    out |= {"pieces": shown, "shown": len(shown), "of": len(pieces), "omitted": omitted,
            "entries": ENTRY_NOTE}  # fmt: skip
    if omitted:
        out["note"] = OMITTED_NOTE
    return out


def brief_status(record):
    """The `status` record in its brief view (A3): the legal moves counted, not listed."""

    if not isinstance(record, dict) or not isinstance(record.get("legal_moves"), list):
        return record
    out = {k: v for k, v in record.items() if k != "legal_moves"}
    return out | {"legal_moves": f"{len(record['legal_moves'])} (detail(ref) lists them)"}


def brief_exchange(record):
    """The `exchange` record in its brief view: the exposed pieces, the others counted."""

    if not isinstance(record, dict) or not isinstance(record.get("pieces"), list):
        return record
    exposed = [e for e in record["pieces"] if isinstance(e, dict) and _gain(e) > 0]
    out = {k: v for k, v in record.items() if k != "pieces"}
    return out | {"pieces": exposed, "not_exposed": len(record["pieces"]) - len(exposed)}


def brief_families(records: dict, exchange: dict | None, status: dict | None,
                   last_square: str | None) -> dict:  # fmt: skip
    """Each family's brief view: `pieces` and `exchange` filtered, the others as they are."""

    out = {}
    for name, record in records.items():
        if name == "pieces":
            out[name] = brief_pieces(record, exchange, status, last_square)
        elif name == "exchange":
            out[name] = brief_exchange(record)
        elif name == "status":
            out[name] = brief_status(record)
        else:
            out[name] = record
    return out
