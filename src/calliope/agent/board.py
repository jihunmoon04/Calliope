"""`board` of a digest (AG8-D §2, §5; MS-D §6 `board_v2`): what the move changed, by whose side,
and the same reply — a view of the reasoning layer's piece relations at the move.

The relations are `piece_relations.move_relations` on the facts tree's records at the positions
before and after the subject's move; every item carries propositions the server's own verifier
accepts as given, a `b` handle, and the canonical form of each proposition is kept so a submission's
propositions can be matched to the items they come from (AG8-D §6.2). A relation claim whose
relation is an item's is that item's `leads_to`; one whose relation held is a `held` item.
"""

from __future__ import annotations

import logging

import chess

from calliope.facts import Defined, ExchangeFacts, PieceId
from calliope.reasoning import (
    MOVE,
    RELATION_FAMILIES,
    claim_relation,
    limited,
    move_relations,
)

from . import remarks as r
from .budget import BudgetError, EngineBusy
from .digest import score_text

FORMAT = "board_v2"
FAMILIES = ("pieces", "patterns", "exchange", "status")  # the records of the position before
WEAK_GRADES = ("inaccuracy", "mistake", "blunder")
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

    def build(self, analysis=None) -> tuple[dict, list[dict]]:
        """(`board`, the served items as `{"part", "canonical"}` in the field's order). The items
        are `piece_relations.move_relations` at the move, limited as AG8's (MS-D §6); a relation
        claim of `analysis` whose relation is an item's carries its link (`leads_to`), one whose
        relation held at the move is a `held` item."""

        view, nodes = self.session._node(self.game, (*self.path, self.uci))
        parent, child = nodes[-2], nodes[-1]
        self.session._records(self.game, view, parent, FAMILIES)
        self.session._records(self.game, view, child, RELATION_FAMILIES)
        facts = self.game.facts.view()
        relations = limited(move_relations(facts, parent, child), self.mover)
        groups: dict[str, list[tuple[dict, object]]] = {"threat": [], "weakness": [],
                                                        "held": [], "lost_defence": []}  # fmt: skip
        for relation in relations:
            item = self._of_relation(relation)
            groups[item["kind"]].append((item, relation))
        unmatched = self._link(analysis, facts, parent, child, groups) if analysis else []
        weak = self.digest.get("grade") in WEAK_GRADES
        order = (("lost_defence", "held", "weakness", "threat") if weak
                 else ("threat", "weakness", "held", "lost_defence"))  # fmt: skip
        refused = 0
        changes, served = [], []
        for kind in order:
            for item, _relation in groups[kind]:
                verified, fault = self._verify(item["propositions"])
                if verified is None:
                    refused += fault
                    continue
                item["ref"] = self.session.handles.serve(
                    "b", self.game.key, {"kind": "board", "subject": [*self.path, self.uci]},
                    {"propositions": verified}, item)  # fmt: skip
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
        self.unmatched = unmatched
        return board, served

    def _item(self, kind: str, owner: str, proves: str, propositions: list[dict]) -> dict:
        good = self.mover if kind == "threat" else r.other(owner if kind == "held" else self.mover)
        return {"kind": kind, "part": "reason", "owner": owner, "good_for": good,
                "proves": proves, "propositions": propositions}  # fmt: skip

    def _of_relation(self, relation) -> dict:
        """A relation at the move as AG8's item (AG8-D §2.1): its kind by side, its propositions
        at the positions before and after, its `proves`."""

        mover, enemy = self.mover, r.other(self.mover)
        sq = {name: p.square for name, p in relation.roles}
        names = {p.square: r.piece(p.color, p.type, p.square) for _n, p in relation.roles}
        after = self.after
        kind = relation.kind
        if kind == "defence":
            defenders, attackers = (
                dict(relation.data)["defenders"],
                dict(relation.data)["attackers"],
            )
            proves = r.lost_defence_proves(mover, self.move, names[sq["defended"]],
                                           names[sq["defender"]], names[sq["attacker"]],
                                           defenders, attackers)  # fmt: skip
            return self._item("lost_defence", mover, proves, [
                {"kind": "defence", "position": self.before, "defender": sq["defender"],
                 "defended": sq["defended"]},
                {"kind": "attack", "position": after, "attacker": sq["attacker"],
                 "target": sq["defended"]},
            ])  # fmt: skip
        if kind == "check":
            proposition = {"kind": "check", "position": after,
                           "checkers": [p.square for _n, p in relation.roles]}  # fmt: skip
        elif kind == "double_attack":
            proposition = {"kind": "pattern", "position": after, "pattern": "multi_target_attacks",
                           "participants": {"actor": sq["actor"], "targets": [
                               p.square for n, p in relation.roles if n == "target"]}}  # fmt: skip
        elif kind == "attack":
            proposition = {"kind": "attack", "position": after, "attacker": sq["attacker"],
                           "target": sq["target"]}  # fmt: skip
        elif kind == "exposed":
            proposition = {"kind": "exposed", "position": after, "piece": sq["piece"],
                           "exposed": "exposed", "gain": dict(relation.data)["gain"]}  # fmt: skip
        else:  # absolute_pin
            proposition = {"kind": "pin", "position": after, "pinned": sq["pinned"],
                           "pinner": sq["slider"]}  # fmt: skip
        side = "threat" if relation.side == enemy else "weakness"
        owner = enemy if side == "threat" else mover
        proves = r.change_proves(side, mover, self.move, proposition, names)
        return self._item(side, owner, proves, [proposition])

    def _link(self, analysis, facts, parent, child, groups) -> list[str]:
        """MS-D §6 items 2–4: a SUPPORTED relation claim whose relation at the move is an item's
        (kind, pieces, place, time) is that item's `leads_to`; one whose relation held is a `held`
        item; the others' claim ids are returned (listed in `claims` with their relation)."""

        ids = {c["id"]: c.get("ref") for c in self.record["analysis"]["claims"]}
        templates = {c["id"]: c["template"] for c in self.record["analysis"]["claims"]}
        unmatched = []
        self.relations = {}
        for claim in analysis.claims:
            read = claim_relation(analysis, claim, analysis.tree.view(analysis.rev), facts)
            if read is None:
                continue
            self.relations[claim.id] = read
            leads = {"claim": ids.get(claim.id), "template": claim.hypothesis.template}
            if read.link is not None:
                leads |= {"link": read.link.kind, "to": ids.get(read.link.to),
                          "to_template": templates.get(read.link.to)}  # fmt: skip
                if read.link.did is not None:
                    leads["did"] = read.link.did
            relation = read.relation
            if relation.place != MOVE:
                unmatched.append(claim.id)
                continue
            if relation.time == "held" and relation.kind == "exposed":
                item = self._held(relation, facts, parent)
                if item is None:
                    unmatched.append(claim.id)
                    continue
                item["leads_to"] = leads
                item["proves"] = r.capped(item["proves"] + r.link_remark(leads))
                groups["held"].append((item, relation))
                continue
            hit = next(((item, rel) for kind in ("threat", "weakness", "lost_defence")
                        for item, rel in groups[kind]
                        if rel.identity() == relation.identity()), None)  # fmt: skip
            if hit is None:
                unmatched.append(claim.id)
                continue
            hit[0]["leads_to"] = leads
            hit[0]["proves"] = r.capped(hit[0]["proves"] + r.link_remark(leads))
        return unmatched

    def _held(self, relation, facts, parent) -> dict | None:
        """A `held` item (MS-D §6 item 3): the piece exposed before the move and after it."""

        (piece,) = [p for _n, p in relation.roles]
        frame = facts.node(parent)
        before = frame.square_of(PieceId(piece.id))
        exchange = facts.fact("exchange", parent)
        if before is None or not isinstance(exchange, ExchangeFacts):
            return None
        entry = next((e for e in exchange.pieces if e.square == before), None)
        if entry is None or not isinstance(entry.gain, Defined):
            return None
        gain_after = dict(relation.data).get("gain")
        if gain_after is None:
            return None
        name = r.piece(piece.color, piece.type, piece.square)
        proves = r.held_proves(piece.color, self.move, name, gain_after)
        return self._item("held", piece.color, proves, [
            {"kind": "exposed", "position": self.before, "piece": before, "exposed": "exposed",
             "gain": entry.gain.value},
            {"kind": "exposed", "position": self.after, "piece": piece.square,
             "exposed": "exposed", "gain": gain_after},
        ])  # fmt: skip

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
