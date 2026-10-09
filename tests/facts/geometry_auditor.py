"""Test-only auditor of the F2 families (F2-D §10.1): independent geometry, compared exactly.

Nothing here calls `attacks_mask`, `attackers_mask`, `pin_mask` or any `calliope.facts` helper.
Geometry is walked square by square on a plain `{square: (colour, type)}` map; pawn structure
follows the F2-D §5 wording with file / rank arithmetic. python-chess is used only to read the
placement and, as the legal oracle, `Board.legal_moves`.

Every engine record is turned into plain tuples (`plain_*`) and compared with the auditor's own
expectation, so a field-level mutation of any family shows up as a difference.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from calliope.facts.values import Absent, AbsentReason, NotApplicable, NotObserved

TYPE = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
TYPE_ORDER = ["pawn", "knight", "bishop", "rook", "queen", "king"]
RANK_V1 = {"pawn": 0, "knight": 1, "bishop": 1, "rook": 2, "queen": 3, "king": 4}
KNIGHT_STEPS = [(1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)]
KING_STEPS = [(df, dr) for df in (-1, 0, 1) for dr in (-1, 0, 1) if (df, dr) != (0, 0)]
ROOK_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
SLIDES = {"rook": ROOK_DIRS, "bishop": BISHOP_DIRS, "queen": ROOK_DIRS + BISHOP_DIRS}
COLORS = ("white", "black")


def name(f: int, r: int) -> str:
    return "abcdefgh"[f] + str(r + 1)


def fr(square: str) -> tuple[int, int]:
    return "abcdefgh".index(square[0]), int(square[1]) - 1


def idx(square: str) -> int:
    f, r = fr(square)
    return r * 8 + f


def on_board(f: int, r: int) -> bool:
    return 0 <= f < 8 and 0 <= r < 8


def forward(color: str) -> int:
    return 1 if color == "white" else -1


def other(color: str) -> str:
    return "black" if color == "white" else "white"


@dataclass
class Position:
    """A naive position: square name -> (colour, type), plus the side to move."""

    pieces: dict[str, tuple[str, str]]
    turn: str

    @classmethod
    def of(cls, board: chess.Board) -> Position:
        return cls(
            {
                chess.square_name(sq): ("white" if p.color else "black", TYPE[p.piece_type])
                for sq, p in board.piece_map().items()
            },
            "white" if board.turn else "black",
        )

    def walk(self, square: str, d: tuple[int, int]) -> list[str]:
        f, r = fr(square)
        out = []
        f, r = f + d[0], r + d[1]
        while on_board(f, r):
            out.append(name(f, r))
            f, r = f + d[0], r + d[1]
        return out

    def attacks(self, square: str) -> set[str]:
        color, kind = self.pieces[square]
        f, r = fr(square)
        if kind == "pawn":
            steps = [(-1, forward(color)), (1, forward(color))]
        elif kind == "knight":
            steps = KNIGHT_STEPS
        elif kind == "king":
            steps = KING_STEPS
        else:
            out = set()
            for d in SLIDES[kind]:
                for target in self.walk(square, d):
                    out.add(target)
                    if target in self.pieces:
                        break
            return out
        return {name(f + df, r + dr) for df, dr in steps if on_board(f + df, r + dr)}

    def king(self, color: str) -> str:
        return next(sq for sq, (c, k) in self.pieces.items() if c == color and k == "king")

    def pins(self) -> dict[str, tuple[str, tuple[int, int]]]:
        """pinned square -> (pinner square, direction from the king toward the pinner)."""

        out = {}
        for color in COLORS:
            king = self.king(color)
            for d in ROOK_DIRS + BISHOP_DIRS:
                occupants = [sq for sq in self.walk(king, d) if sq in self.pieces]
                if len(occupants) < 2 or self.pieces[occupants[0]][0] != color:
                    continue
                pinner_color, pinner_kind = self.pieces[occupants[1]]
                if pinner_color != color and d in SLIDES.get(pinner_kind, []):
                    out[occupants[0]] = (occupants[1], d)
        return out


def same(actual, expected) -> bool:
    """`==` that also tells `True` from `1`: a bool must stay a bool (review F2-N3)."""

    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (tuple, list)) and isinstance(expected, (tuple, list)):
        return (
            type(actual) is type(expected)
            and len(actual) == len(expected)
            and all(same(a, e) for a, e in zip(actual, expected, strict=True))
        )
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            same(actual[k], expected[k]) for k in actual
        )
    return actual == expected


def by_square(squares) -> list[str]:
    return sorted(squares, key=idx)


# -- POSITION families -----------------------------------------------------------------------


def expected_pieces(pos: Position, board: chess.Board) -> list[tuple]:
    pins = pos.pins()
    attack_sets = {sq: pos.attacks(sq) for sq in pos.pieces}
    legal = list(board.legal_moves)
    victims = set()
    for move in legal:
        if board.is_capture(move):
            f, r = chess.square_file(move.to_square), chess.square_rank(move.to_square)
            if board.is_en_passant(move):
                r = chess.square_rank(move.from_square)
            victims.add(name(f, r))
    out = []
    for sq in by_square(pos.pieces):
        color, kind = pos.pieces[sq]
        attacks = attack_sets[sq]

        def rel(color_of, sq=sq):
            return tuple(
                (s, pos.pieces[s][1], s in pins)
                for s in by_square(attack_sets)
                if s != sq and pos.pieces[s][0] == color_of and sq in attack_sets[s]
            )

        attackers, defenders = rel(other(color)), rel(color)
        if attackers:
            low = min(RANK_V1[a[1]] for a in attackers)
            lowest = tuple(
                t for t in TYPE_ORDER if any(a[1] == t and RANK_V1[t] == low for a in attackers)
            )
        else:
            lowest = ()
        if color == pos.turn:
            moves = sorted(m.uci() for m in legal if chess.square_name(m.from_square) == sq)
            destinations = tuple(by_square({m[2:4] for m in moves}))
            legal_moves = tuple(moves)
            capturable = "NOT_OBSERVED"
        else:
            destinations = legal_moves = "NOT_OBSERVED"
            capturable = sq in victims
        out.append(
            (
                sq,
                color,
                kind,
                (
                    tuple(by_square(t for t in attacks if t not in pos.pieces)),
                    tuple(
                        by_square(
                            t for t in attacks if t in pos.pieces and pos.pieces[t][0] == color
                        )
                    ),
                    tuple(
                        by_square(
                            t for t in attacks if t in pos.pieces and pos.pieces[t][0] != color
                        )
                    ),
                ),
                attackers,
                defenders,
                len(attackers),
                len(defenders),
                ("piece_order_v1", lowest),
                len(attackers) >= 1 and len(defenders) == 0,
                len(attackers) > len(defenders),
                pins.get(sq),
                destinations,
                legal_moves,
                capturable,
            )
        )
    return out


def plain_pieces(record) -> list[tuple]:
    def obs(value):
        return "NOT_OBSERVED" if isinstance(value, NotObserved) else value

    def rels(items):
        return tuple((r.square, r.piece_type.value, r.absolutely_pinned) for r in items)

    return [
        (
            p.square,
            p.color.value,
            p.piece_type.value,
            (p.attacks.empty, p.attacks.friendly, p.attacks.enemy),
            rels(p.attackers),
            rels(p.defenders),
            p.attacker_count,
            p.defender_count,
            (
                p.lowest_attacker_types.definition,
                tuple(t.value for t in p.lowest_attacker_types.value),
            ),
            p.attacked_without_defender,
            p.attackers_exceed_defenders,
            None
            if p.absolutely_pinned is None
            else (p.absolutely_pinned.pinner, p.absolutely_pinned.direction),
            obs(p.legal_destinations),
            obs(p.legal_moves),
            obs(p.legally_capturable_now),
        )
        for p in record.pieces
    ]


def expected_squares(pos: Position) -> list[tuple]:
    pins = pos.pins()
    attack_sets = {sq: pos.attacks(sq) for sq in pos.pieces}
    out = []
    for i in range(64):
        sq = name(i % 8, i // 8)
        per_color = []
        for color in COLORS:
            per_color.append(
                tuple(
                    (s, pos.pieces[s][1], s in pins)
                    for s in by_square(attack_sets)
                    if pos.pieces[s][0] == color and sq in attack_sets[s]
                )
            )
        out.append(
            (
                sq,
                pos.pieces.get(sq),
                per_color[0],
                per_color[1],
                len(per_color[0]),
                len(per_color[1]),
            )
        )
    return out


def plain_squares(record) -> list[tuple]:
    def rels(items):
        return tuple((r.square, r.piece_type.value, r.absolutely_pinned) for r in items)

    return [
        (
            s.square,
            None if s.occupant is None else (s.occupant.color.value, s.occupant.piece_type.value),
            rels(s.white_attackers),
            rels(s.black_attackers),
            s.white_count,
            s.black_count,
        )
        for s in record.squares
    ]


def expected_lines(pos: Position) -> tuple[list[tuple], list[tuple]]:
    rays, batteries = [], set()
    for sq in by_square(pos.pieces):
        color, kind = pos.pieces[sq]
        if kind not in SLIDES:
            continue
        for d in sorted(SLIDES[kind]):
            path = pos.walk(sq, d)
            occ = [s for s in path if s in pos.pieces]
            occupants = tuple((s, *pos.pieces[s]) for s in occ)
            visible = path if not occ else path[: path.index(occ[0]) + 1]
            xray = None
            if len(occ) >= 2:
                xray = (
                    tuple(path[path.index(occ[0]) + 1 : path.index(occ[1]) + 1]),
                    occupants[0],
                    occupants[1],
                )
            rays.append(
                (
                    sq,
                    d,
                    tuple(path),
                    occupants,
                    not path,
                    bool(path) and not occ,
                    occupants[0] if occupants else None,
                    tuple(visible),
                    xray,
                )
            )
            if occ:
                partner_color, partner_kind = pos.pieces[occ[0]]
                if partner_color == color and d in SLIDES.get(partner_kind, []):
                    low, high = sorted((sq, occ[0]), key=idx)
                    line = d if low == sq else (-d[0], -d[1])
                    batteries.add(((low, high), line))
    return rays, sorted(batteries, key=lambda b: (idx(b[0][0]), idx(b[0][1])))


def plain_lines(record) -> tuple[list[tuple], list[tuple]]:
    def occ(o):
        return (o.square, o.color.value, o.piece_type.value)

    rays = [
        (
            r.source,
            r.direction,
            r.squares,
            tuple(occ(o) for o in r.occupants),
            r.edge_empty,
            r.unblocked,
            None if r.first_blocker is None else occ(r.first_blocker),
            r.visible,
            None if r.xray is None else (r.xray.squares, occ(r.xray.first), occ(r.xray.second)),
        )
        for r in record.rays
    ]
    return rays, [(b.pieces, b.line) for b in record.batteries]


def expected_pawns(pos: Position) -> dict:
    pawns = {sq: c for sq, (c, k) in pos.pieces.items() if k == "pawn"}
    out = []
    support: dict[str, list[str]] = {}
    for sq in by_square(pawns):
        color = pawns[sq]
        f, r = fr(sq)
        fw = forward(color)
        own = [fr(s) for s, c in pawns.items() if c == color and s != sq]
        enemy = [fr(s) for s, c in pawns.items() if c != color]
        isolated = not any(abs(of - f) == 1 for of, _ in own)
        supporters = [name(of, orr) for of, orr in own if abs(of - f) == 1 and orr == r - fw]
        phalanx = [name(of, orr) for of, orr in own if abs(of - f) == 1 and orr == r]
        stop = (f, r + fw)
        stop_attacked = on_board(*stop) and any(
            abs(ef - stop[0]) == 1 and er == stop[1] + fw for ef, er in enemy
        )
        backward = (
            not isolated
            and not any(abs(of - f) == 1 and (orr - r) * fw <= 0 for of, orr in own)
            and stop_attacked
        )
        support[sq] = supporters
        out.append(
            (
                sq,
                color,
                isolated,
                any(of == f for of, _ in own),
                not any(abs(ef - f) <= 1 and (er - r) * fw > 0 for ef, er in enemy),
                any(of == f and (orr - r) * fw > 0 for of, orr in own),
                backward,
                tuple(by_square(supporters)),
                tuple(by_square(phalanx)),
            )
        )
    # chains: connected components of the supporter graph
    parent = {sq: sq for sq in pawns}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for sq, sups in support.items():
        for s in sups:
            parent[find(s)] = find(sq)
    groups: dict[str, list[str]] = {}
    for sq in pawns:
        groups.setdefault(find(sq), []).append(sq)
    supporting = {s for sups in support.values() for s in sups}
    chains = sorted(
        (
            (
                pawns[members[0]],
                tuple(by_square(members)),
                tuple(by_square(m for m in members if not support[m])),
                tuple(by_square(m for m in members if m not in supporting)),
            )
            for members in groups.values()
            if len(members) >= 2
        ),
        key=lambda c: idx(c[1][0]),
    )
    islands = {}
    for color in COLORS:
        files = sorted({fr(s)[0] for s, c in pawns.items() if c == color})
        runs: list[list[int]] = []
        for f in files:
            if runs and runs[-1][-1] == f - 1:
                runs[-1].append(f)
            else:
                runs.append([f])
        islands[color] = tuple(tuple("abcdefgh"[f] for f in run) for run in runs)
    files = []
    for f in range(8):
        w = sum(1 for s, c in pawns.items() if c == "white" and fr(s)[0] == f)
        b = sum(1 for s, c in pawns.items() if c == "black" and fr(s)[0] == f)
        state = (
            "open"
            if w == b == 0
            else "semi_open_white"
            if w == 0
            else "semi_open_black"
            if b == 0
            else "closed"
        )
        files.append(("abcdefgh"[f], w, b, state))
    cones = {}
    for color in COLORS:
        covered = set()
        for s, c in pawns.items():
            if c == color:
                continue
            ef, er = fr(s)
            fw = forward(c)
            rr = er + fw
            while 0 <= rr < 8:
                for ff in (ef - 1, ef + 1):
                    if on_board(ff, rr):
                        covered.add(name(ff, rr))
                rr += fw
        cones[color] = tuple(
            name(i % 8, i // 8) for i in range(64) if name(i % 8, i // 8) not in covered
        )
    return {"pawns": out, "chains": chains, "islands": islands, "files": files, "cones": cones}


def plain_pawns(record) -> dict:
    return {
        "pawns": [
            (
                p.square,
                p.color.value,
                p.isolated,
                p.doubled,
                p.passed,
                p.own_pawn_ahead,
                p.backward,
                p.supporters,
                p.phalanx,
            )
            for p in record.pawns
        ],
        "chains": [(c.color.value, c.squares, c.bases, c.heads) for c in record.chains],
        "islands": {"white": record.islands.white, "black": record.islands.black},
        "files": [(f.file, f.white_pawns, f.black_pawns, f.state.value) for f in record.files],
        "cones": {
            "white": record.outside_enemy_pawn_cones.white,
            "black": record.outside_enemy_pawn_cones.black,
        },
    }


def expected_king(pos: Position, board: chess.Board, pawn_facts: dict) -> dict:
    pins = pos.pins()
    attack_sets = {sq: pos.attacks(sq) for sq in pos.pieces}

    def enemy_attackers(color, sq):
        return tuple(
            (s, pos.pieces[s][1], s in pins)
            for s in by_square(attack_sets)
            if pos.pieces[s][0] != color and sq in attack_sets[s]
        )

    out = {}
    for color in COLORS:
        king = pos.king(color)
        f, r = fr(king)
        neighbours = [name(f + df, r + dr) for df, dr in KING_STEPS if on_board(f + df, r + dr)]
        zone = tuple((sq, enemy_attackers(color, sq)) for sq in by_square([king, *neighbours]))
        fw = forward(color)
        shield = tuple(
            by_square(
                s
                for s, (c, k) in pos.pieces.items()
                if c == color
                and k == "pawn"
                and abs(fr(s)[0] - f) <= 1
                and (fr(s)[1] - r) * fw in (1, 2)
            )
        )
        files_near = tuple(pawn_facts["files"][ff] for ff in (f - 1, f, f + 1) if 0 <= ff < 8)
        if color == pos.turn:
            flight = (
                "legal",
                tuple(
                    by_square(
                        {
                            chess.square_name(m.to_square)
                            for m in board.legal_moves
                            if chess.square_name(m.from_square) == king and not board.is_castling(m)
                        }
                    )
                ),
            )
        else:
            flight = (
                "geometric",
                tuple(
                    by_square(
                        sq
                        for sq in neighbours
                        if (sq not in pos.pieces or pos.pieces[sq][0] != color)
                        and not enemy_attackers(color, sq)
                    )
                ),
            )
        out[color] = (color, king, zone, shield, files_near, flight)
    return out


def plain_king(record) -> dict:
    def one(k):
        return (
            k.color.value,
            k.square,
            tuple(
                (
                    z.square,
                    tuple((a.square, a.piece_type.value, a.absolutely_pinned) for a in z.attackers),
                )
                for z in k.zone
            ),
            k.shield,
            tuple((f.file, f.white_pawns, f.black_pawns, f.state.value) for f in k.files_near),
            (k.flight_squares.kind.value, k.flight_squares.squares),
        )

    return {"white": one(record.white), "black": one(record.black)}


def audit_position(view, node_id, board: chess.Board) -> Position:
    """Compare the five POSITION families of one node with the auditor's own computation."""

    pos = Position.of(board)
    assert same(plain_pieces(view.fact("pieces", node_id)), expected_pieces(pos, board))
    assert same(plain_squares(view.fact("squares", node_id)), expected_squares(pos))
    assert same(plain_lines(view.fact("lines", node_id)), expected_lines(pos))
    pawns = expected_pawns(pos)
    assert same(plain_pawns(view.fact("pawns", node_id)), pawns)
    assert same(plain_king(view.fact("king", node_id)), expected_king(pos, board, pawns))
    return pos


# -- deltas -----------------------------------------------------------------------------------


def naive_relations(pos: Position, board: chess.Board, ids: dict[str, str]) -> dict:
    """The side-independent relation sets of F2-D §7.1, keyed by the tracker's ids."""

    pins = pos.pins()
    attack_sets = {sq: pos.attacks(sq) for sq in pos.pieces}
    pieces = expected_pieces(pos, board)
    pawns = expected_pawns(pos)
    kings = expected_king(pos, board, pawns)
    rel: dict = {
        "square_control": {(ids[s], t) for s, ts in attack_sets.items() for t in ts},
        "piece_attacks": set(),
        "piece_defences": set(),
        "pins": set(),
        "piece_flags": {},
    }
    for s, ts in attack_sets.items():
        for t in ts:
            if t in pos.pieces:
                key = "piece_attacks" if pos.pieces[t][0] != pos.pieces[s][0] else "piece_defences"
                rel[key].add((ids[s], ids[t]))
    for p in pieces:
        rel["piece_flags"][ids[p[0]]] = (p[9], p[10])
    for pinned, (pinner, _d) in pins.items():
        rel["pins"].add((ids[pinner], ids[pinned], ids[pos.king(pos.pieces[pinned][0])]))
    rays, batteries = expected_lines(pos)
    rel["xrays"] = {(ids[r[0]], ids[r[8][1][0]], ids[r[8][2][0]]) for r in rays if r[8] is not None}
    rel["batteries"] = {tuple(sorted((ids[a], ids[b]))) for (a, b), _ in batteries}
    rel["pawn_flags"] = {ids[p[0]]: p[2:7] for p in pawns["pawns"]}
    rel["pawn_supports"] = {(ids[s], ids[p[0]]) for p in pawns["pawns"] for s in p[7]}
    rel["files"] = pawns["files"]
    rel["islands"] = pawns["islands"]
    rel["zone_attacks"] = {
        (ids[k[1]], sq, ids[a[0]])
        for k in kings.values()
        for sq, attackers in k[2]
        for a in attackers
    }
    rel["shield"] = {(ids[k[1]], ids[p]) for k in kings.values() for p in k[3]}
    return rel


SQUARE_FIELDS = {"square_control": (1,), "zone_attacks": (1,)}


def _sort_key(component):
    positions = SQUARE_FIELDS.get(component, ())
    return lambda t: tuple(idx(v) if i in positions else v for i, v in enumerate(t))


def plain_delta(record) -> dict:
    def pid(p):
        return p.value

    def raw(component, item):
        if component == "square_control":
            return (pid(item.piece), item.square)
        if component == "zone_attacks":
            return (pid(item.king), item.square, pid(item.attacker))
        if component == "pins":
            return (pid(item.pinner), pid(item.pinned), pid(item.king))
        if component == "xrays":
            return (pid(item.slider), pid(item.first), pid(item.second))
        if component == "batteries":
            return tuple(pid(p) for p in item.pieces)
        return (pid(item.source), pid(item.target))

    out = {}
    for component in (
        "square_control",
        "piece_attacks",
        "piece_defences",
        "pins",
        "xrays",
        "batteries",
        "pawn_supports",
        "zone_attacks",
        "shield",
    ):
        change = getattr(record, component)
        out[component] = (
            [raw(component, i) for i in change.began],
            [raw(component, i) for i in change.ended],
        )

    def after(value, fields):
        if isinstance(value, Absent):
            return value.reason.value
        return tuple(getattr(value, f) for f in fields)

    piece_fields = ("attacked_without_defender", "attackers_exceed_defenders")
    pawn_fields = ("isolated", "doubled", "passed", "own_pawn_ahead", "backward")
    out["piece_flags"] = [
        (c.piece.value, after(c.before, piece_fields), after(c.after, piece_fields))
        for c in record.piece_flags
    ]
    out["pawn_flags"] = [
        (c.piece.value, after(c.before, pawn_fields), after(c.after, pawn_fields))
        for c in record.pawn_flags
    ]
    out["files"] = [
        (
            c.file,
            (c.before.file, c.before.white_pawns, c.before.black_pawns, c.before.state.value),
            (c.after.file, c.after.white_pawns, c.after.black_pawns, c.after.state.value),
        )
        for c in record.files
    ]
    out["islands"] = [(c.color.value, c.before, c.after) for c in record.islands]
    return out


def expected_delta(before: dict, after: dict) -> dict:
    out = {}
    for component in (
        "square_control",
        "piece_attacks",
        "piece_defences",
        "pins",
        "xrays",
        "batteries",
        "pawn_supports",
        "zone_attacks",
        "shield",
    ):
        key = _sort_key(component)
        out[component] = (
            sorted(after[component] - before[component], key=key),
            sorted(before[component] - after[component], key=key),
        )
    out["piece_flags"] = [
        (pid, flags, after["piece_flags"].get(pid, "captured"))
        for pid, flags in sorted(before["piece_flags"].items())
        if after["piece_flags"].get(pid, "captured") != flags
    ]
    out["pawn_flags"] = []
    for pid, flags in sorted(before["pawn_flags"].items()):
        if pid in after["pawn_flags"]:
            now = after["pawn_flags"][pid]
        else:
            now = "promoted" if pid in after["piece_flags"] else "captured"
        if now != flags:
            out["pawn_flags"].append((pid, flags, now))
    out["files"] = [
        (b[0], b, a) for b, a in zip(before["files"], after["files"], strict=True) if b != a
    ]
    out["islands"] = [
        (c, before["islands"][c], after["islands"][c])
        for c in COLORS
        if before["islands"][c] != after["islands"][c]
    ]
    return out


@dataclass
class State:
    """One audited node: the true board and the tracker's square -> id map."""

    board: chess.Board
    ids: dict[str, str]


def audit_delta(view, node_id, parent: State, child: State) -> None:
    before = naive_relations(Position.of(parent.board), parent.board, parent.ids)
    after = naive_relations(Position.of(child.board), child.board, child.ids)
    assert same(plain_delta(view.fact("delta", node_id)), expected_delta(before, after))


def _side(state: State) -> dict:
    board, ids = state.board, state.ids
    pos = Position.of(board)
    mover = pos.turn
    legal = list(board.legal_moves)
    types = {ids[s]: k for s, (c, k) in pos.pieces.items() if c == mover}
    destinations = {
        ids[s]: {
            chess.square_name(m.to_square) for m in legal if chess.square_name(m.from_square) == s
        }
        for s, (c, _k) in pos.pieces.items()
        if c == mover
    }
    captures = set()
    victims = set()
    for m in legal:
        if not board.is_capture(m):
            continue
        f, r = chess.square_file(m.to_square), chess.square_rank(m.to_square)
        if board.is_en_passant(m):
            r = chess.square_rank(m.from_square)
        captures.add((ids[chess.square_name(m.from_square)], ids[name(f, r)]))
        victims.add(name(f, r))
    capturable = {ids[s]: s in victims for s, (c, _k) in pos.pieces.items() if c != mover}
    king = pos.king(mover)
    flight = {
        chess.square_name(m.to_square)
        for m in legal
        if chess.square_name(m.from_square) == king and not board.is_castling(m)
    }
    return {
        "mover": mover,
        "types": types,
        "destinations": destinations,
        "captures": captures,
        "capturable": capturable,
        "flight": flight,
        "count": len(legal),
    }


def audit_same_side(view, node_id, grandparent: State, node: State) -> None:
    record = view.fact("same_side_delta", node_id)
    before, after = _side(grandparent), _side(node)
    assert before["mover"] == after["mover"]
    pieces = [
        (pid, kind, after["types"].get(pid, "captured"))
        for pid, kind in sorted(before["types"].items())
    ]
    destinations = []
    for pid in sorted(before["destinations"].keys() & after["destinations"].keys()):
        old, new = before["destinations"][pid], after["destinations"][pid]
        if old != new:
            destinations.append((pid, tuple(by_square(new - old)), tuple(by_square(old - new))))
    capturable = []
    for pid, was in sorted(before["capturable"].items()):
        now = after["capturable"].get(pid, "captured")
        if now != was:
            capturable.append((pid, was, now))
    expected = (
        pieces,
        destinations,
        (
            sorted(after["captures"] - before["captures"]),
            sorted(before["captures"] - after["captures"]),
        ),
        capturable,
        (
            tuple(by_square(after["flight"] - before["flight"])),
            tuple(by_square(before["flight"] - after["flight"])),
        ),
        (before["count"], after["count"]),
    )

    def absent(value):
        return value.reason.value if isinstance(value, Absent) else value

    actual = (
        [
            (
                m.piece.value,
                m.before.value,
                absent(m.after) if isinstance(m.after, Absent) else m.after.value,
            )
            for m in record.pieces
        ],
        [(d.piece.value, d.gained, d.lost) for d in record.legal_destinations],
        (
            [(p.source.value, p.target.value) for p in record.legal_captures.gained],
            [(p.source.value, p.target.value) for p in record.legal_captures.lost],
        ),
        [(c.piece.value, c.before, absent(c.after)) for c in record.capturable_now],
        (record.flight_squares.gained, record.flight_squares.lost),
        record.legal_move_count,
    )
    assert same(actual, expected)


def audit_no_grandparent(view, node_id) -> None:
    assert view.fact("same_side_delta", node_id) == NotApplicable(
        "no same-side ancestor in the tree"
    )


__all__ = [
    "AbsentReason",
    "State",
    "audit_delta",
    "audit_no_grandparent",
    "audit_position",
    "audit_same_side",
]


# -- F3: patterns and pattern_delta (F3-D §7.1) ------------------------------------------------


def _order(target: str, actor: str) -> str:
    t, a = RANK_V1[target], RANK_V1[actor]
    return "above" if t > a else "below" if t < a else "equal"


def expected_patterns(pos: Position) -> dict:
    """F3-D §2 from the auditor's own geometry (no `pieces` / `lines` records)."""

    pins = pos.pins()
    attack_sets = {sq: pos.attacks(sq) for sq in pos.pieces}

    def part(sq):
        return (sq, pos.pieces[sq][1], sq in pins)

    def attackers(sq, color):
        return [s for s in attack_sets if pos.pieces[s][0] == color and sq in attack_sets[s]]

    multi = []
    for sq in by_square(pos.pieces):
        color, kind = pos.pieces[sq]
        enemy = by_square(
            t for t in attack_sets[sq] if t in pos.pieces and pos.pieces[t][0] != color
        )
        if len(enemy) >= 2:
            multi.append(
                (part(sq), tuple((part(t), _order(pos.pieces[t][1], kind)) for t in enemy))
            )
    rel, skw, disc = [], [], []
    for sq in by_square(pos.pieces):
        color, kind = pos.pieces[sq]
        for d in sorted(SLIDES.get(kind, [])):
            occ = [s for s in pos.walk(sq, d) if s in pos.pieces]
            if len(occ) < 2:
                continue
            (ca, ka), (cb, kb) = pos.pieces[occ[0]], pos.pieces[occ[1]]
            if cb == color:
                continue
            row = (part(sq), d, part(occ[0]), part(occ[1]))
            if ca == color:
                disc.append(row)
            elif kb == "king":
                continue
            elif RANK_V1[kb] > RANK_V1[ka]:
                rel.append(row)
            elif RANK_V1[ka] > RANK_V1[kb]:
                skw.append(row)
    groups: dict[str, list[str]] = {}
    for sq in by_square(pos.pieces):
        color, kind = pos.pieces[sq]
        if kind == "king":
            continue
        defenders = [s for s in attackers(sq, color) if s != sq]
        if attackers(sq, other(color)) and len(defenders) == 1:
            groups.setdefault(defenders[0], []).append(sq)
    sole = [
        (part(d), tuple(part(x) for x in xs))
        for d, xs in sorted(groups.items(), key=lambda i: idx(i[0]))
        if len(xs) >= 2
    ]
    back = []
    for color in COLORS:
        king = pos.king(color)
        f, r = fr(king)
        if r != (0 if color == "white" else 7):
            continue
        second = 1 if color == "white" else 6
        blockers, covered, free = [], [], False
        for ff in (f - 1, f, f + 1):
            if not on_board(ff, second):
                continue
            s = name(ff, second)
            if s in pos.pieces and pos.pieces[s][0] == color:
                blockers.append(part(s))
            elif attackers(s, other(color)):
                covered.append(s)
            else:
                free = True
        if not free and blockers:
            back.append((part(king), tuple(blockers), tuple(covered)))
    return {
        "multi": multi,
        "rel": rel,
        "skw": skw,
        "disc": disc,
        "sole": sole,
        "back": back,
    }


def plain_patterns(record) -> dict:
    def part(r):
        return (r.square, r.piece_type.value, r.absolutely_pinned)

    def line(p):
        return (part(p.slider), p.line, part(p.front), part(p.back))

    return {
        "multi": [
            (part(m.actor), tuple((part(t.piece), t.order.value) for t in m.targets))
            for m in record.multi_target_attacks
        ],
        "rel": [line(p) for p in record.relative_pins],
        "skw": [line(p) for p in record.skewers],
        "disc": [line(p) for p in record.discovery_lines],
        "sole": [
            (part(s.defender), tuple(part(x) for x in s.defended)) for s in record.sole_defenders
        ],
        "back": [
            (part(b.king), tuple(part(x) for x in b.blockers), b.covered) for b in record.back_ranks
        ],
    }


def audit_patterns(view, node_id, board: chess.Board) -> dict:
    pos = Position.of(board)
    expected = expected_patterns(pos)
    assert same(plain_patterns(view.fact("patterns", node_id)), expected)
    return expected


def _pattern_ids(patterns: dict, ids: dict[str, str]) -> dict:
    def sorted_ids(squares):
        return tuple(sorted(ids[s] for s in squares))

    return {
        "multi": {ids[a[0]]: sorted_ids(t[0][0] for t in ts) for a, ts in patterns["multi"]},
        "sole": {ids[d[0]]: sorted_ids(x[0] for x in xs) for d, xs in patterns["sole"]},
        "rel": {(ids[p[0][0]], ids[p[2][0]], ids[p[3][0]]) for p in patterns["rel"]},
        "skw": {(ids[p[0][0]], ids[p[2][0]], ids[p[3][0]]) for p in patterns["skw"]},
        "disc": {(ids[p[0][0]], ids[p[2][0]], ids[p[3][0]]) for p in patterns["disc"]},
        "back": {ids[k[0]]: (sorted_ids(b[0] for b in bl), cov) for k, bl, cov in patterns["back"]},
    }


def expected_pattern_delta(parent: State, child: State, move_uci: str) -> dict:
    """F3-D §4 from the auditor's own pattern sets and python-chess move metadata."""

    before = _pattern_ids(expected_patterns(Position.of(parent.board)), parent.ids)
    after = _pattern_ids(expected_patterns(Position.of(child.board)), child.ids)
    alive = set(child.ids.values())
    out: dict = {}
    for key in ("multi", "sole"):
        changes = []
        for pid in sorted(before[key].keys() | after[key].keys()):
            old = before[key].get(pid, ())
            new = after[key].get(pid, ()) if pid in alive else "captured"
            if new != old:
                changes.append((pid, old, new))
        out[key] = changes
    for key in ("rel", "skw", "disc"):
        out[key] = (sorted(after[key] - before[key]), sorted(before[key] - after[key]))
    kings = sorted(
        parent.ids[s] for s, (c, k) in Position.of(parent.board).pieces.items() if k == "king"
    )
    out["back"] = [
        (k, before["back"].get(k), after["back"].get(k))
        for k in kings
        if before["back"].get(k) != after["back"].get(k)
    ]
    out["ended"] = _expected_defences_ended(parent, child, move_uci)
    return out


def _expected_defences_ended(parent: State, child: State, move_uci: str) -> list:
    board = parent.board
    move = chess.Move.from_uci(move_uci)
    mover = parent.ids[chess.square_name(move.from_square)]
    captured = None
    if board.is_en_passant(move):
        captured = parent.ids[
            name(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        ]
    elif board.piece_at(move.to_square) is not None:
        captured = parent.ids[chess.square_name(move.to_square)]
    moved = {mover}
    if board.is_castling(move):
        kingside = chess.square_file(move.to_square) == 6
        rank = chess.square_rank(move.from_square)
        moved.add(parent.ids[name(7 if kingside else 0, rank)])
    pos_b, pos_a = Position.of(parent.board), Position.of(child.board)
    rel_b = naive_relations(pos_b, parent.board, parent.ids)["piece_defences"]
    rel_a = naive_relations(pos_a, child.board, child.ids)["piece_defences"]
    square_of = {pid: sq for sq, pid in child.ids.items()}
    out = []
    for d, x in sorted(rel_b - rel_a):
        sq = square_of.get(x)
        if sq is None or pos_a.pieces[sq][1] == "king":
            continue
        color = pos_a.pieces[sq][0]
        if not any(pos_a.pieces[s][0] != color and sq in pos_a.attacks(s) for s in pos_a.pieces):
            continue
        if d == captured:
            reason = "defender_captured"
        elif d in moved:
            reason = "defender_moved"
        elif x in moved:
            reason = "defended_moved"
        else:
            reason = "line_blocked"
        out.append((d, x, reason))
    return out


def plain_pattern_delta(record) -> dict:
    def ids(items):
        return tuple(p.value for p in items)

    def changes(items):
        return [
            (
                c.piece.value,
                ids(c.before),
                c.after.reason.value if isinstance(c.after, Absent) else ids(c.after),
            )
            for c in items
        ]

    def triples(change):
        return (
            [(t.slider.value, t.front.value, t.back.value) for t in change.began],
            [(t.slider.value, t.front.value, t.back.value) for t in change.ended],
        )

    def back(value):
        return None if value is None else (ids(value.blockers), value.covered)

    return {
        "multi": changes(record.multi_target_attacks),
        "sole": changes(record.sole_defenders),
        "rel": triples(record.relative_pins),
        "skw": triples(record.skewers),
        "disc": triples(record.discovery_lines),
        "back": [(c.king.value, back(c.before), back(c.after)) for c in record.back_ranks],
        "ended": [
            (e.defender.value, e.defended.value, e.reason.value)
            for e in record.defences_ended_under_attack
        ],
    }


def audit_pattern_delta(view, node_id, parent: State, child: State, move_uci: str) -> None:
    expected = expected_pattern_delta(parent, child, move_uci)
    actual = plain_pattern_delta(view.fact("pattern_delta", node_id))
    for key in ("rel", "skw", "disc"):
        expected[key] = (
            [tuple(t) for t in expected[key][0]],
            [tuple(t) for t in expected[key][1]],
        )
    assert same(actual, expected)
