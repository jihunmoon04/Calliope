"""`board` of a digest (AG8-D §2, §5): what the move changed, by whose side, and the same reply.

The records are the facts tree's at the positions before and after the subject's move; every item
carries propositions the server's own verifier accepts as given, and the canonical form of each is
kept so a submission's propositions can be matched to the items they come from (§6.2).
"""

from __future__ import annotations

import logging

import chess

from . import remarks as r
from .budget import BudgetError, EngineBusy
from .digest import score_text

FORMAT = "board_v1"
FAMILIES = ("pieces", "patterns", "exchange", "status")
LIMITS = {"double": 2, "attack": 3, "exposed": 3, "pin": 2, "lost_defence": 3}
WEAK_GRADES = ("inaccuracy", "mistake", "blunder")
LOST_REASONS = ("defender_moved", "line_blocked")  # pattern_delta's: the defended piece stayed
log = logging.getLogger(__name__)


def canonical(record: dict) -> dict:
    """A verified proposition's record without what the submission adds (§6.2)."""

    return {k: v for k, v in record.items() if k not in ("id", "sources", "by_agent")}


class Board:
    """One subject's `board`: `build()` gives the field and the items' canonical propositions."""

    def __init__(self, session, game_id: str, game, path: tuple[str, ...], uci: str,
                 record: dict, digest: dict, by_ply: bool) -> None:  # fmt: skip
        self.session, self.game_id, self.game = session, game_id, game
        self.path, self.uci, self.record, self.digest = path, uci, record, digest
        self.mover = digest["side"]
        self.move = digest["move"]
        n = len(path) + 1
        self.before = {"ply": n, "at": "before"} if by_ply else {"from_root": list(path)}
        self.after = {"ply": n, "at": "after"} if by_ply else {"from_root": [*path, uci]}

    # -- the records ---------------------------------------------------------------------------

    def _records(self, path, families=FAMILIES) -> dict:
        view, nodes = self.session._node(self.game, path)
        _, records = self.session._records(self.game, view, nodes[-1], families)
        return records

    def _verify(self, propositions: list[dict]) -> tuple[list[dict] | None, bool]:
        """(the canonical records, or None; whether a refusal is a fault). A piece whose
        exchange gain is positive but whose `exposed` state is another is no item, not a fault."""

        from .propositions import Refused, Verifier

        out = []
        for proposition in propositions:
            try:
                record, _ = Verifier(self.session, self.game).verify(proposition | {"id": "x"})
            except Refused as error:
                if proposition["kind"] == "exposed" and error.field == "exposed":
                    return None, False
                log.warning("board item refused at %s: %s %s", self.move, proposition["kind"],
                            error.problem)  # fmt: skip
                return None, True  # a fault: counted (§2.1)
            out.append(canonical(record))
        return out, False

    # -- the items -----------------------------------------------------------------------------

    def build(self) -> tuple[dict, list[dict]]:
        """(`board`, the served items as `{"part", "canonical"}` in the field's order)."""

        before = self._records(self.path)
        after = self._records((*self.path, self.uci), (*FAMILIES, "pattern_delta"))
        pb, pa = _by_square(before), _by_square(after)
        names = {s: r.piece(e["color"], e["piece_type"], s) for s, e in pa.items()}
        names_before = {s: r.piece(e["color"], e["piece_type"], s) for s, e in pb.items()}
        delta = after["pattern_delta"]
        threats, weaknesses = self._changes(before, after, pb, pa, names, delta)
        lost = self._lost(pb, pa, names, names_before, delta)
        refused = 0
        groups = {"threat": threats, "weakness": weaknesses, "lost_defence": lost}
        weak = self.digest.get("grade") in WEAK_GRADES
        order = ("lost_defence", "weakness", "threat") if weak else ("threat", "weakness",
                                                                        "lost_defence")  # fmt: skip
        changes, served = [], []
        for kind in order:
            for item in groups[kind]:
                verified, fault = self._verify(item["propositions"])
                if verified is None:
                    refused += fault
                    continue
                changes.append(item)
                served.append({"part": item["part"], "canonical": verified})
        board = {"v": FORMAT, "mover": self.mover, "changes": changes}
        same, same_served = self._same_reply()
        if same is not None:
            board["same_reply"] = same
            if same_served is not None:
                served.append(same_served)
        if refused:
            board["refused"] = refused
        return board, served

    def _item(self, kind: str, owner: str, proves: str, propositions: list[dict]) -> dict:
        good = self.mover if kind == "threat" else r.other(self.mover)
        return {"kind": kind, "part": "reason", "owner": owner, "good_for": good,
                "proves": proves, "propositions": propositions}  # fmt: skip

    def _changes(self, before, after, pb, pa, names, delta) -> tuple[list[dict], list[dict]]:
        mover, enemy = self.mover, r.other(self.mover)
        threats, weaknesses = [], []

        def add(kind, owner, proposition):
            group = threats if kind == "threat" else weaknesses
            proves = r.change_proves(kind, mover, self.move, proposition, names)
            group.append(self._item(kind, owner, proves, [proposition]))

        status = after["status"]
        if isinstance(status, dict) and status.get("in_check"):
            add("threat", enemy, {"kind": "check", "position": self.after,
                                  "checkers": list(status["checkers"])})  # fmt: skip
        actors = set()
        for actor, targets in _doubles(delta, mover)[: LIMITS["double"]]:
            actors.add(actor)
            add("threat", enemy, {"kind": "pattern", "position": self.after,
                                  "pattern": "multi_target_attacks",
                                  "participants": {"actor": actor, "targets": list(targets)}})  # fmt: skip
        gain_after, gain_before = _gains(after), _gains(before)
        ia, ib = _ids(pa), _ids(pb)  # a relation is new when its pieces had none before (review B1)
        had_attacks = {(ib[a], ib[t]) for a, t in _attacks(pb, mover)}
        exposed_before = {ib[s] for s, g in gain_before.items() if s in ib and (g or 0) > 0}
        had_pins = {(ib[p], ib[q]) for p, q in _pins(pb)}
        attacks = sorted(
            ((a, t) for a, t in _attacks(pa, mover) if (ia[a], ia[t]) not in had_attacks
             and pa[t]["piece_type"] != "king" and a not in actors
             and (pa[t]["piece_type"] != "pawn" or (gain_after.get(t) or 0) > 0)),
            key=lambda x: (-r.VALUE[pa[x[1]]["piece_type"]], x),
        )  # fmt: skip
        for a, t in attacks[: LIMITS["attack"]]:
            add("threat", enemy, {"kind": "attack", "position": self.after, "attacker": a,
                                  "target": t})  # fmt: skip
        exposed = sorted(
            (s for s, g in gain_after.items() if (g or 0) > 0 and s in pa
             and ia[s] not in exposed_before and pa[s]["piece_type"] != "king"),
            key=lambda s: (-r.VALUE[pa[s]["piece_type"]], s),
        )  # fmt: skip
        mine = [s for s in exposed if pa[s]["color"] == mover][: LIMITS["exposed"]]
        theirs = [s for s in exposed if pa[s]["color"] == enemy][: LIMITS["exposed"]]
        for square in theirs:
            add("threat", enemy, {"kind": "exposed", "position": self.after, "piece": square,
                                  "exposed": "exposed", "gain": gain_after[square]})  # fmt: skip
        for square in mine:
            add("weakness", mover, {"kind": "exposed", "position": self.after, "piece": square,
                                    "exposed": "exposed", "gain": gain_after[square]})  # fmt: skip
        pins = sorted(p for p in _pins(pa) if (ia[p[0]], ia[p[1]]) not in had_pins)
        for pinned, pinner in [p for p in pins if pa[p[0]]["color"] == enemy][: LIMITS["pin"]]:
            add("threat", enemy, {"kind": "pin", "position": self.after, "pinned": pinned,
                                  "pinner": pinner})  # fmt: skip
        for pinned, pinner in [p for p in pins if pa[p[0]]["color"] == mover][: LIMITS["pin"]]:
            add("weakness", mover, {"kind": "pin", "position": self.after, "pinned": pinned,
                                    "pinner": pinner})  # fmt: skip
        return threats, weaknesses

    def _lost(self, pb, pa, names, names_before, delta) -> list[dict]:
        """§2.1: a piece of the mover's that lost a defender it had and is attacked, read from
        `pattern_delta`'s `defences_ended_under_attack` (by piece identity): the defender moved or
        the move blocked its line; the defended piece stayed on its square."""

        found = []
        for ended in delta["defences_ended_under_attack"]:
            defended, defender = ended["defended"], ended["defender"]
            if defended["color"] != self.mover or ended["reason"] not in LOST_REASONS:
                continue
            square, gone = defended["square"], _square_of(pb, defender)
            entry = pa[square]
            attackers = sorted(entry["attackers"], key=lambda a: (r.VALUE[a["piece_type"]],
                                                                  a["square"]))  # fmt: skip
            if gone is not None and attackers and entry["piece_type"] != "king":
                found.append((square, gone, attackers[0]["square"], len(entry["defenders"]),
                              len(attackers)))  # fmt: skip
        found.sort(key=lambda x: (x[3] - x[4], -r.VALUE[pa[x[0]]["piece_type"]], x[0]))
        items = []
        for square, gone, attacker, defenders, count in found[: LIMITS["lost_defence"]]:
            proves = r.lost_defence_proves(self.mover, self.move, names[square],
                                           names_before.get(gone, gone), names.get(attacker, attacker),
                                           defenders, count)  # fmt: skip
            items.append(self._item("lost_defence", self.mover, proves, [
                {"kind": "defence", "position": self.before, "defender": gone, "defended": square},
                {"kind": "attack", "position": self.after, "attacker": attacker, "target": square},
            ]))  # fmt: skip
        return items

    # -- the same reply (§5) -------------------------------------------------------------------

    def _same_reply(self) -> tuple[dict | None, dict | None]:
        subject = self.record["analysis"]["judgements"][0]
        played, best = subject.get("played"), subject.get("best")
        if best is None or played is None or best.get("rank") == played.get("rank"):
            return None, None
        pv = played.get("pv") or []
        if len(pv) < 2:
            return None, None
        board = chess.Board(self.digest["fen_before"])
        best_san = board.san(chess.Move.from_uci(best["move"]["uci"]))
        board.push_uci(best["move"]["uci"])
        if board.is_game_over():
            return {"not_computed": "game_over"}, None
        reply = chess.Move.from_uci(pv[1]["uci"])
        if reply not in board.legal_moves:
            return {"not_computed": "reply_illegal"}, None
        same = [board.san(reply)]
        board.push(reply)
        if board.is_game_over():
            return {"not_computed": "game_over"}, None
        try:
            explored = self.session.compare(self.game_id, self.before, [best_san, *same])
        except EngineBusy:  # a job holds the engine: answered without it, computed on a later read
            return {"not_computed": "engine_busy"}, None
        except BudgetError as error:
            out = {"not_computed": "budget"}
            if error.retry_after_seconds is not None:
                out["retry_after_seconds"] = error.retry_after_seconds
            return out, None
        top = explored["search"]["lines"][0]
        if len(pv) >= 4 and top["move"]["uci"] == pv[2]["uci"]:
            board.push_uci(pv[2]["uci"])
            third = chess.Move.from_uci(pv[3]["uci"])
            if third in board.legal_moves:
                longer = [*same, top["move"]["san"], board.san(third)]
                board.push(third)
                if not board.is_game_over():
                    try:  # the mover's move is the engine's there too: one more search
                        explored = self.session.compare(self.game_id, self.before,
                                                        [best_san, *longer])  # fmt: skip
                        top, same = explored["search"]["lines"][0], longer
                    except (BudgetError, EngineBusy):
                        pass  # the first search's comparison stands
        propositions = [
            {"kind": "explored_line", "line": explored["ref"], "moves": [best_san, *same]},
            {"kind": "engine_score", "line": top["ref"], "move": top["move"]["san"],
             "score": top["score"]},
            {"kind": "engine_score", "line": played["ref"], "move": played["move"]["san"],
             "score": played["score"]},
        ]  # fmt: skip
        verified, _ = self._verify(propositions)
        if verified is None:
            return {"not_computed": "refused"}, None
        proves = r.same_reply_proves(self.move, same, best_san, top["move"]["san"],
                                     score_text(top["score"]), score_text(played["score"]))  # fmt: skip
        item = {"kind": "same_reply", "part": "reason", "proves": proves,
                "propositions": propositions}  # fmt: skip
        return item, {"part": "reason", "canonical": verified}


def _by_square(records: dict) -> dict:
    return {p["square"]: p for p in records["pieces"]["pieces"]}


def _doubles(delta: dict, side: str) -> list[tuple[str, tuple[str, ...]]]:
    """`pattern_delta`'s double attacks of `side` that were none before (by piece identity). One
    that was a double attack already and gained a target is no new one (review B4): its new target
    is an `attack` item."""

    out = []
    for change in delta["multi_target_attacks"]:
        piece, after = change["piece"], change["after"]
        if piece["color"] != side or not isinstance(after, list) or len(after) < 2:
            continue
        if len(change["before"]) < 2:
            out.append((piece["square"], tuple(sorted(t["square"] for t in after))))
    return sorted(out)


def _ids(pieces: dict) -> dict:
    """A position's pieces (by square) to their identities' keys."""

    return {s: _key(e["identity"]) for s, e in pieces.items()}


def _key(identity: dict) -> tuple[str, str, str]:
    return identity["color"], identity["piece"], identity["origin"]


def _square_of(pieces: dict, identity: dict) -> str | None:
    """The square of the piece `identity` names in a position's pieces (by square)."""

    return next((s for s, e in pieces.items() if _key(e["identity"]) == _key(identity)), None)


def _attacks(pieces: dict, side: str) -> set:
    return {(s, t) for s, p in pieces.items() if p["color"] == side for t in p["attacks"]["enemy"]}


def _gains(records: dict) -> dict:
    out = {}
    for entry in records["exchange"]["pieces"]:
        gain = entry.get("gain")
        out[entry["square"]] = gain.get("value") if isinstance(gain, dict) else None
    return out


def _pins(pieces: dict) -> set:
    return {(s, p["absolutely_pinned"]["pinner"]) for s, p in pieces.items()
            if isinstance(p.get("absolutely_pinned"), dict)}  # fmt: skip
