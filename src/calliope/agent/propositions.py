"""Propositions (AG-D §4): structured statements, each verified field by field against what the
session served.

A proposition names its source by a handle field (`judgement`, `claim`, `line`) or reads a
position, whose source is the game's facts tree (implicit). Every field must lie within its
sources: a handle of another kind, game or session refuses it, and so does any field that does
not equal what the source holds. A verified proposition also says what a sentence citing it may
write (`Allowed`, §5.3 S3).
"""

from __future__ import annotations

import json

import chess

from calliope.facts import Color, Defined, NotApplicable, material_flow
from calliope.reasoning import exposed as exposed_v1

from .budget import BudgetError
from .build import find_definitions
from .handles import HandleError
from .sentences import Allowed
from .session import AgentError

POSITION_KINDS = ("attack", "defence", "exposed", "pin", "check", "legal_moves", "pattern")
KINDS = (
    "judgement", "claim", "engine_score", "engine_line", "material", *POSITION_KINDS,
    "after_reply", "explored_line", "definition",
)  # fmt: skip
USES = ("result", "line_fact", "mechanism", "associated", "comparison", "uncertain",
        "not_the_case")  # fmt: skip
MATERIAL_TEMPLATES = ("material_gain_v3", "material_loss_v2")  # the templates with ATTRIBUTED
PATTERNS = {
    "multi_target_attacks": ("actor", "targets"),
    "relative_pins": ("slider", "line", "front", "back"),
    "skewers": ("slider", "line", "front", "back"),
    "discovery_lines": ("slider", "line", "front", "back"),
    "sole_defenders": ("defender", "defended"),
    "back_ranks": ("king", "blockers"),
}
EXPOSED = ("exposed", "not_exposed", "undecided")


class Refused(Exception):
    """A field that does not hold: the field, the problem and what the source holds."""

    def __init__(self, field: str, problem: str, expected=None) -> None:
        super().__init__(problem)
        self.field, self.problem, self.expected = field, problem, expected


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Verifier:
    """Verifies the propositions of one submission for one game of a session."""

    def __init__(self, session, game) -> None:
        self.session = session
        self.game = game
        self.sources: list[dict] = []  # the resolved sources of the proposition being verified
        self.by_agent = False

    # -- the entry ---------------------------------------------------------------------------

    def verify(self, proposition) -> tuple[dict, Allowed]:
        """(the verified record, what a sentence may write); `Refused` otherwise."""

        if not isinstance(proposition, dict):
            raise Refused("proposition", "a proposition is an object")
        kind = proposition.get("kind")
        if kind not in KINDS:
            problem = f"no proposition kind {kind!r}"
            bare = kind.removeprefix("proposition.") if isinstance(kind, str) else None
            if bare != kind and bare in KINDS:  # the id of the kind's definition (AG5-D §5.3)
                problem += f": write {bare!r} ({kind!r} is the id of its definition)"
            raise Refused("kind", problem, list(KINDS))
        self.sources, self.by_agent = [], False
        allowed = Allowed()
        values = getattr(self, f"_{kind}")(proposition, allowed)
        refs = proposition.get("refs", [])
        if not isinstance(refs, list):
            raise Refused("refs", "a list of handles")
        for ref in refs:  # after the fields' own sources: extra refs are only this game's handles
            self._entry(ref, "refs")
        record = {"id": proposition.get("id"), "kind": kind, **values,
                  "sources": self.sources, "by_agent": self.by_agent}  # fmt: skip
        return record, allowed

    # -- helpers -----------------------------------------------------------------------------

    def _entry(self, ref, field: str, kinds: tuple[str, ...] = ()):
        if not isinstance(ref, str):
            raise Refused(field, "a handle is a string such as c3.k7f2a9")
        try:
            entry = self.session.resolve(ref, self.game)
        except HandleError as error:
            raise Refused(field, str(error)) from error
        if kinds and entry.kind not in kinds:
            raise Refused(field, f"{ref} is a {entry.kind}, not a {' or '.join(kinds)}")
        self.sources.append({"ref": ref, "kind": entry.kind, "source": entry.source,
                             "address": entry.address})  # fmt: skip
        if entry.kind == "explored_line" and entry.address.get("by", "agent") == "agent":
            self.by_agent = True  # a line Calliope played for a comparison is not (AG8-D §5)
        return entry

    def _path(self, position, field: str) -> tuple[str, ...]:
        try:
            return self.session.path(self.game, position)
        except AgentError as error:
            raise Refused(field, str(error)) from error

    def _fen(self, path) -> str:
        return self.session._board(self.game, path).fen()

    def _node(self, path, families):
        try:
            view, nodes = self.session._node(self.game, path)
            view, records = self.session._raw_records(self.game, nodes[-1], families)
        except (AgentError, BudgetError) as error:
            raise Refused("position", str(error)) from error
        return view, nodes, records

    @staticmethod
    def _uci(board_fen: str, text, field: str) -> str:
        board = chess.Board(board_fen)
        try:
            move = chess.Move.from_uci(str(text))
            if move in board.legal_moves:
                return move.uci()
        except ValueError:
            pass
        try:
            return board.parse_san(str(text)).uci()
        except ValueError as error:
            raise Refused(field, f"{text!r} is not a legal move at {board_fen}") from error

    @staticmethod
    def _equal(field: str, given, held) -> None:
        if given != held:
            raise Refused(field, f"{given!r} is not what the source holds", held)

    @staticmethod
    def _square(value, field: str) -> str:
        if not isinstance(value, str) or len(value) != 2 or value not in chess.SQUARE_NAMES:
            raise Refused(field, f"{value!r} is not a square")
        return value

    @staticmethod
    def _int(value, field: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise Refused(field, f"{value!r} is not an integer")
        return value

    # -- kinds with handles --------------------------------------------------------------------

    def _judgement(self, p, allowed: Allowed) -> dict:
        """A field given is verified; one left out is the judgement's (AG6-D §5.1)."""

        entry = self._entry(p.get("judgement"), "judgement", ("judgement",))
        item = entry.item
        fen = item["move"]["fen"]
        move = self._uci(fen, p["move"], "move") if "move" in p else item["move"]["uci"]
        self._equal("move", move, item["move"]["uci"])
        if "grade" in p:
            self._equal("grade", p["grade"], item["grade"])
        if "label" in p:
            self._equal("label", p["label"], item.get("label"))
        best = item["best"]["move"]["uci"] if item.get("best") else None
        if "best_move" in p:
            best_given = self._uci(fen, p["best_move"], "best_move") if p["best_move"] else None
            self._equal("best_move", best_given, best)
        allowed.add_move(move, fen)
        if best is not None:
            allowed.add_move(best, fen)
        return {"judgement": p["judgement"], "move": move, "grade": item["grade"],
                "label": item.get("label"), "best_move": best,
                "judged": {"source": entry.source, "address": entry.address}}  # fmt: skip

    def _claim(self, p, allowed: Allowed) -> dict:
        """`scopes` given is verified; left out, they are the claim's (AG6-D §5.1). The use is
        always the agent's."""

        entry = self._entry(p.get("claim"), "claim", ("claim",))
        claim = entry.item
        use = p.get("use")
        if use not in USES:
            raise Refused("use", f"no use {use!r}", list(USES))
        problem = self._use(claim, use, entry.source)
        if problem:  # `expected`: the uses this claim takes (AG7-D §4), not its status
            takes = [u for u in USES if self._use(claim, u, entry.source) is None]
            raise Refused("use", problem, takes)
        if "scopes" in p:
            scopes = p["scopes"]
            if not isinstance(scopes, list):
                raise Refused("scopes", "the claim's effective scopes, as a list (or leave it out)")
            given = sorted(_canonical(s) for s in scopes)
            held = sorted(_canonical(s) for s in claim["effective_scopes"])
            if sorted(set(given)) != sorted(set(held)):
                raise Refused("scopes", "not the claim's effective scopes",
                              claim["effective_scopes"])  # fmt: skip
        _harvest(claim, allowed)
        return {"claim": p["claim"], "template": claim["template"], "status": claim["status"],
                "use": use, "scopes": claim["effective_scopes"]}  # fmt: skip

    def _use(self, claim: dict, use: str, source: dict) -> str | None:
        status = claim["status"]
        relations = {r["kind"] for r in claim["relations"]}
        if use == "uncertain":
            return None if status == "inconclusive" else "only an INCONCLUSIVE claim is uncertain"
        if use == "not_the_case":
            return None if status == "refuted" else "only a REFUTED claim is not the case"
        if status != "supported":
            return f"a {status} claim cannot be used as {use}"
        if use == "result":
            if claim["role"] != "consequence":
                return "only a consequence is a result"
            if claim["template"] in MATERIAL_TEMPLATES:
                checks = [c for c in claim["checks"] if c["kind"] == "attributed"]
                if not checks or not all(c["passed"] for c in checks):
                    return "its ATTRIBUTED check did not pass: the line's fact, not the move's gain"
            return None
        if use == "line_fact":
            return None
        if use == "mechanism":
            projected, _ = self.session.analysis(self.game, source)
            statuses = {c["id"]: c["status"] for c in projected["claims"]}
            for r in claim["relations"]:
                if r["kind"] not in ("explains", "causes"):
                    continue
                target = r["target"]
                if target["type"] != "claim" or statuses.get(target["id"]) == "supported":
                    return None
            return "no explains or causes relation to a supported target"
        if use == "associated":
            if "associated_with" in relations and not relations & {"explains", "causes"}:
                return None
            return "not an associated_with claim (or it explains or causes)"
        if use == "comparison":
            return None if claim["role"] == "comparison" else "not a comparison claim"
        return f"no use {use!r}"

    def _search_line(self, p, field: str = "line"):
        entry = self._entry(p.get(field), field, ("search_line",))
        address = entry.address
        if "path" in address:  # a search the session ran: its position's path
            base = tuple(address["path"])
        else:  # a judgement's line: the judgement's position on the analysed path
            base = self._position_of(entry.source["path"], address["fen"])
            if base is None:
                raise Refused(field, "the line's position is not on its analysis's path")
        return entry, base

    def _position_of(self, path, fen: str) -> tuple[str, ...] | None:
        """The prefix of an analysed path whose position has `fen`."""

        board = chess.Board(self.game.parsed.game.start_fen)
        for index in range(len(path) + 1):
            if board.fen() == fen:
                return tuple(path[:index])
            if index < len(path):
                board.push_uci(path[index])
        return None

    def _engine_score(self, p, allowed: Allowed) -> dict:
        entry, _ = self._search_line(p)
        item, fen = entry.item, entry.address["fen"]
        move = self._uci(fen, p.get("move"), "move")
        self._equal("move", move, item["move"]["uci"])
        self._equal("score", p.get("score"), item["score"])
        if "depth" in p:
            self._equal("depth", p["depth"], item.get("depth"))
        allowed.add_move(move, fen)
        score = item["score"]
        if "cp" in score:
            allowed.scores.add(score["cp"])
        else:
            allowed.mates.add(abs(score["mate"]))
        if item.get("depth") is not None:
            allowed.integers.add(item["depth"])
        return {"line": p["line"], "move": move, "score": score, "depth": item.get("depth")}

    def _engine_line(self, p, allowed: Allowed) -> dict:
        entry, _ = self._search_line(p)
        fen, pv = entry.address["fen"], [x["uci"] for x in entry.item.get("pv", [])]
        moves = self._line_moves(fen, p.get("moves"), "moves")
        if not moves or pv[: len(moves)] != moves:
            raise Refused("moves", "not a prefix of the line's PV", pv)
        allowed.add_line(fen, moves)
        return {"line": p["line"], "moves": moves}

    def _line_moves(self, fen: str, moves, field: str) -> list[str]:
        if not isinstance(moves, list):
            raise Refused(field, "a list of moves")
        board, out = chess.Board(fen), []
        for text in moves:
            uci = self._uci(board.fen(), text, field)
            out.append(uci)
            board.push_uci(uci)
        return out

    def _line(self, p, field: str = "line") -> tuple[tuple[str, ...], list[str]]:
        """(the line's start path, its moves) of an explored line or a search line's PV."""

        ref = p.get(field)
        entry = self._entry(ref, field, ("explored_line", "search_line"))
        if entry.kind == "explored_line":
            return tuple(entry.address["from"]), list(entry.address["moves"])
        self.sources.pop()
        entry, base = self._search_line(p, field)
        return base, [x["uci"] for x in entry.item.get("pv", [])]

    def _material(self, p, allowed: Allowed) -> dict:
        base, moves = self._line(p)
        start, end = self._int(p.get("from"), "from"), self._int(p.get("to"), "to")
        if not 0 <= start <= end <= len(moves):
            raise Refused("to", f"from and to are plies 0 to {len(moves)} of the line")
        side = p.get("side")
        if side not in ("white", "black"):
            raise Refused("side", "white or black")
        balance = self._int(p.get("balance"), "balance")
        view, nodes, _ = self._node((*base, *moves), ())
        segment = tuple(nodes[len(base) + start : len(base) + end + 1])
        try:
            held = material_flow(view, segment).balance(Color(side), end - start)
        except ValueError as error:
            raise Refused("balance", f"the material records are missing: {error}") from error
        self._equal("balance", balance, held)
        allowed.add_line(self._fen(base), moves[:end])
        allowed.integers |= {start, end, balance}
        return {"line": p["line"], "from": start, "to": end, "side": side, "balance": held,
                "base": list(base), "moves": moves}  # the line verified (AG-D AM7)  # fmt: skip

    def _explored_line(self, p, allowed: Allowed) -> dict:
        entry = self._entry(p.get("line"), "line", ("explored_line",))
        fen = self._fen(tuple(entry.address["from"]))
        moves = self._line_moves(fen, p.get("moves"), "moves")
        self._equal("moves", moves, list(entry.address["moves"]))
        allowed.add_line(fen, moves)
        return {"line": p["line"], "from": entry.address["from"], "moves": moves,
                "by": entry.address.get("by", "agent")}  # fmt: skip

    def _definition(self, p, allowed: Allowed) -> dict:
        if not isinstance(p.get("definition"), str):
            raise Refused("definition", "a registry id")
        found = find_definitions(ids=[p["definition"]])
        if not found["definitions"]:
            raise Refused("definition", f"no definition {p.get('definition')!r}")
        return {"definition": p["definition"]}

    # -- kinds that read a position (the facts tree, implicit) --------------------------------

    def _position(self, p, families, field: str = "position"):
        path = self._path(p.get(field), field)
        view, nodes, records = self._node(path, families)
        self.sources.append({"kind": "facts_tree", "source": {"kind": "facts_tree",
                             "rev": view.rev}, "address": {"position": list(path)}})  # fmt: skip
        return path, view, nodes[-1], records

    @staticmethod
    def _piece(records, square: str, field: str):
        entry = next((e for e in records["pieces"].pieces if e.square == square), None)
        if entry is None:
            raise Refused(field, f"no piece on {square}")
        return entry

    def _attack(self, p, allowed: Allowed) -> dict:
        path, _, _, records = self._position(p, ("pieces",))
        attacker = self._square(p.get("attacker"), "attacker")
        target = self._square(p.get("target"), "target")
        held = self._piece(records, attacker, "attacker").attacks.enemy
        if target not in held:
            raise Refused("target", f"{attacker} does not attack {target}", list(held))
        allowed.squares |= {attacker, target}
        return {"position": list(path), "attacker": attacker, "target": target}

    def _defence(self, p, allowed: Allowed) -> dict:
        path, _, _, records = self._position(p, ("pieces",))
        defender = self._square(p.get("defender"), "defender")
        defended = self._square(p.get("defended"), "defended")
        held = [r.square for r in self._piece(records, defended, "defended").defenders]
        if defender not in held:
            raise Refused("defender", f"{defender} does not defend {defended}", held)
        allowed.squares |= {defender, defended}
        return {"position": list(path), "defender": defender, "defended": defended}

    def _exposed(self, p, allowed: Allowed) -> dict:
        path, view, node, records = self._position(p, ("exchange",))
        square = self._square(p.get("piece"), "piece")
        piece = view.node(node).piece_at(square)
        if piece is None:
            raise Refused("piece", f"no piece on {square}")
        state = exposed_v1(view, piece, node)
        held = state.value if state is not None else None
        if p.get("exposed") not in EXPOSED:
            raise Refused("exposed", "exposed, not_exposed or undecided", held)
        self._equal("exposed", p["exposed"], held)
        entry = next((e for e in records["exchange"].pieces if e.square == square), None)
        if entry is None:
            raise Refused("gain", f"the exchange record has no entry for {square} (a king?)")
        gain = "IN_CHECK" if isinstance(entry.gain, NotApplicable) else (
            entry.gain.value if isinstance(entry.gain, Defined) else None)  # fmt: skip
        self._equal("gain", p.get("gain"), gain)
        allowed.squares.add(square)
        if isinstance(gain, int):
            allowed.integers.add(gain)
        return {"position": list(path), "piece": square, "exposed": held, "gain": gain}

    def _pin(self, p, allowed: Allowed) -> dict:
        path, _, _, records = self._position(p, ("pieces",))
        pinned = self._square(p.get("pinned"), "pinned")
        pinner = self._square(p.get("pinner"), "pinner")
        pin = self._piece(records, pinned, "pinned").absolutely_pinned
        self._equal("pinner", pinner, pin.pinner if pin is not None else None)
        allowed.squares |= {pinned, pinner}
        return {"position": list(path), "pinned": pinned, "pinner": pinner}

    def _check(self, p, allowed: Allowed) -> dict:
        path, _, _, records = self._position(p, ("status",))
        checkers = p.get("checkers")
        if not isinstance(checkers, list):
            raise Refused("checkers", "a list of squares (empty: not in check)")
        status = records["status"]
        held = sorted(status.checkers)
        self._equal("checkers", sorted(self._square(c, "checkers") for c in checkers), held)
        allowed.squares |= set(held)
        allowed.integers.add(len(held))
        return {"position": list(path), "in_check": status.in_check, "checkers": held}

    def _legal_moves(self, p, allowed: Allowed) -> dict:
        path, _, _, records = self._position(p, ("status",))
        status = records["status"]
        if "moves" not in p and "count" not in p:
            raise Refused("moves", "give the moves, the count or both")
        out = {"position": list(path)}
        fen = self._fen(path)
        if "moves" in p:
            given = sorted(self._line_moves_at(fen, p["moves"]))
            held = sorted(m.uci for m in status.legal_moves)
            self._equal("moves", given, held)
            out["moves"] = held  # verified, but not a licence to write any of them (AG2 notes)
        if "count" in p:
            self._equal("count", p["count"], status.legal_move_count)
            allowed.integers.add(status.legal_move_count)
            out["count"] = status.legal_move_count
        return out

    def _line_moves_at(self, fen: str, moves) -> list[str]:
        if not isinstance(moves, list):
            raise Refused("moves", "a list of moves")
        return [self._uci(fen, m, "moves") for m in moves]

    def _pattern(self, p, allowed: Allowed) -> dict:
        path, _, _, records = self._position(p, ("patterns",))
        name = p.get("pattern")
        if not isinstance(name, str) or name not in PATTERNS:  # a list is no key (re-review 3.)
            raise Refused("pattern", f"no pattern list {name!r}", list(PATTERNS))
        given = p.get("participants")
        if not isinstance(given, dict) or not given or set(given) - set(PATTERNS[name]):
            raise Refused("participants", f"some of {PATTERNS[name]}")
        for element in getattr(records["patterns"], name):
            held = {k: _participant(getattr(element, k)) for k in given}
            if all(_same(given[k], held[k]) for k in given):
                for value in held.values():
                    allowed.squares |= {v for v in _flat(value) if isinstance(v, str)}
                return {"position": list(path), "pattern": name, "participants": held,
                        "configuration_only": True}  # fmt: skip
        raise Refused("participants", f"no such configuration in {name}")

    def _after_reply(self, p, allowed: Allowed) -> dict:
        a = self._path(p.get("after_a"), "after_a")
        b = self._path(p.get("after_b"), "after_b")
        if len(a) != len(b) or len(a) < 2 or a[:-2] != b[:-2] or a[-1] != b[-1] or a[-2] == b[-2]:
            raise Refused("after_b", "after_a and after_b are P + a + r and P + b + r for one P")
        reply = self._uci(self._fen(a[:-1]), p.get("reply"), "reply")
        self._equal("reply", reply, a[-1])
        nested = []
        for side, path in (("proposition_a", a), ("proposition_b", b)):
            inner = p.get(side)
            if not isinstance(inner, dict) or inner.get("kind") not in POSITION_KINDS:
                raise Refused(side, f"a proposition of one of {POSITION_KINDS}")
            if self._path(inner.get("position"), f"{side}.position") != path:
                raise Refused(f"{side}.position", f"the position is {side[-1:]}'s, after the reply")
            nested.append(inner)
        if nested[0]["kind"] != nested[1]["kind"]:
            raise Refused("proposition_b", "both nested propositions are of one kind")
        records = []
        for side, inner in zip(("proposition_a", "proposition_b"), nested, strict=True):
            try:
                values = getattr(self, f"_{inner['kind']}")(inner, allowed)
            except Refused as error:
                raise Refused(f"{side}.{error.field}", error.problem, error.expected) from error
            records.append({"kind": inner["kind"], **values})
        self.by_agent = True  # the agent chose P, a, b and r: its comparison (S6, AG2 notes)
        allowed.add_move(reply, self._fen(a[:-1]))
        allowed.add_move(reply, self._fen(b[:-1]))
        allowed.add_move(a[-2], self._fen(a[:-2]))
        allowed.add_move(b[-2], self._fen(b[:-2]))
        return {"reply": reply, "after_a": list(a), "after_b": list(b),
                "proposition_a": records[0], "proposition_b": records[1]}  # fmt: skip


def _participant(value):
    if hasattr(value, "square"):  # a Relation
        return value.square
    if isinstance(value, tuple) and value and hasattr(value[0], "piece"):  # targets
        return [t.piece.square for t in value]
    if isinstance(value, tuple) and value and hasattr(value[0], "square"):
        return [r.square for r in value]
    if isinstance(value, tuple):
        return list(value)
    return value


def _same(given, held) -> bool:
    if isinstance(held, list) and isinstance(given, list):
        return sorted(map(str, given)) == sorted(map(str, held)) if held and isinstance(
            held[0], str) else list(given) == list(held)  # fmt: skip
    return given == held


def _flat(value):
    if isinstance(value, list):
        for x in value:
            yield from _flat(x)
    else:
        yield value


def _harvest(value, allowed: Allowed) -> None:
    """The moves, squares and points a claim's record names (S3)."""

    if isinstance(value, dict):
        kind = value.get("kind")
        if kind in ("move", "search_move") and value.get("uci") and value.get("fen"):
            allowed.add_move(value["uci"], value["fen"])
        elif kind == "line" and value.get("fen") and value.get("moves"):
            allowed.add_line(value["fen"], [m["uci"] for m in value["moves"]])
        if isinstance(value.get("square"), str) and value["square"] in chess.SQUARE_NAMES:
            allowed.squares.add(value["square"])
        if isinstance(value.get("points"), int):
            allowed.integers.add(value["points"])
        for v in value.values():
            _harvest(v, allowed)
    elif isinstance(value, list):
        for v in value:
            _harvest(v, allowed)
