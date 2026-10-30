"""`board` of a digest (AG8-D §2, §5; MS-D §6; BL-D; ST-D `board_v4`): what the move changed, by
whose side, and the same reply — a view of the reasoning layer's piece relations at the move; on a
weak move ordered by what is at stake, with the played line's material when the claim cannot
decide; the scene the opponent's last move set, since when an attack has stood, and the pawn
structure and files the move changed (ST-D).

The relations are `piece_relations.move_relations` on the facts tree's records at the positions
before and after the subject's move; every item carries propositions the server's own verifier
accepts as given, a `b` handle, and the canonical form of each proposition is kept so a submission's
propositions can be matched to the items they come from (AG8-D §6.2). A relation claim whose
relation is an item's is that item's `leads_to`; one whose relation held is a `held` item. A mover's
exposed piece names the piece that attacks it first in the exchange (BL-D §3).
"""

from __future__ import annotations

import logging

import chess

from calliope.facts import Defined, ExchangeFacts, PieceId
from calliope.reasoning import (
    MOVE,
    RELATION_FAMILIES,
    Exposed,
    claim_relation,
    exposed,
    limited,
    move_relations,
)

from . import remarks as r
from .budget import BudgetError, EngineBusy
from .digest import PV_PLIES, numbered_line, score_text

FORMAT = "board_v4"
FAMILIES = ("pieces", "patterns", "exchange", "status")  # the records of the position before
WEAK_GRADES = ("inaccuracy", "mistake", "blunder")
HELD_GAIN = 3  # BL-D §2: a held piece from the facts on any grade from this gain (any if weak)
FIRST_GAIN = 3  # BL-D §5 (3): a mover's exposed piece the opponent can take before a threat counts
SCENE_ITEMS = 3  # ST-D §2.1 (owner O3)
SCENE_KINDS = ("attack", "exposed", "check", "double_attack", "absolute_pin")
SINCE_PLIES = 16  # ST-D §3.1: how far back since-when walks
PAWN_FLAGS = ("passed", "isolated", "doubled", "backward")  # ST-D §4.1, `pawns_v1`'s flags
log = logging.getLogger(__name__)


def canonical(record: dict) -> dict:
    """A verified proposition's record without what the submission adds (§6.2)."""

    return {
        k: v
        for k, v in record.items()
        if k not in ("id", "sources", "by_agent", "by_handle", "use_by")
    }  # MS-c review B3


class Board:
    """One subject's `board`: `build()` gives the field and the items' canonical propositions."""

    def __init__(self, session, game_id: str, game, path: tuple[str, ...], uci: str,
                 record: dict, digest: dict, by_ply: bool) -> None:  # fmt: skip
        self.session, self.game_id, self.game = session, game_id, game
        self.path, self.uci, self.record, self.digest = path, uci, record, digest
        self.mover = digest["side"]
        self.move = digest["move"]
        self.by_ply = by_ply
        self.extra_moves: dict[int, list[tuple[str, str]]] = {}  # id(item) → moves it names
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
        self.facts, self.parent, self.child = facts, parent, child
        self.nodes = nodes  # the subject's path from the root (ST-D §3)
        weak = self.digest.get("grade") in WEAK_GRADES
        relations = limited(tuple(rel for rel in move_relations(facts, parent, child)
                                  if _gated(rel, weak)), self.mover)  # fmt: skip
        groups: dict[str, list[tuple[dict, object]]] = {"threat": [], "weakness": [],
                                                        "held": [], "lost_defence": []}  # fmt: skip
        refused = 0
        for relation in relations:
            item = self._of_relation(relation)
            if item is None:  # an exposed piece with no attacker read: a fault (BL-D §3)
                refused += 1
                continue
            groups[item["kind"]].append((item, relation))
        unmatched = self._link(analysis, facts, parent, child, groups) if analysis else []
        if weak:  # BL-D §5 (1): the costs by what is at stake (stable: today's kind order on ties)
            ordered = sorted((x for kind in ("lost_defence", "held", "weakness") for x in groups[kind]),
                             key=lambda x: -_stake(x[1]))  # fmt: skip
            ordered += groups["threat"]
        else:
            ordered = [x for kind in ("threat", "weakness", "held", "lost_defence")
                       for x in groups[kind]]  # fmt: skip
        kept, served = [], []
        for item, relation in ordered:
            verified, fault = self._verify(item["propositions"])
            if verified is None:
                refused += fault
                continue
            kept.append((item, relation))
            served.append({"part": item["part"], "canonical": verified})
        changes = [item for item, _relation in kept]
        for item in self._structure():  # ST-D §4.1–4.2: after the move's relation items
            verified, fault = self._verify(item["propositions"])
            if verified is None:
                refused += fault
                continue
            changes.append(item)
            served.append({"part": item["part"], "canonical": verified})
        scene = []  # ST-D §2: its own list, built after `_link` (re-review N-c)
        for item in self._scene(kept):
            verified, fault = self._verify(item["propositions"])
            if verified is None:
                refused += fault
                continue
            scene.append(item)
            served.append({"part": item["part"], "canonical": verified})
        # the `b` handles through the session's own path, its room made first (review B1); bound
        # to the subject and the analysis whose claims the items carry (review N2)
        self.source = {"kind": "board", "subject": [*self.path, self.uci],
                       "bundle": self.record.get("bundle")}  # fmt: skip
        self.session._serve(self.game, [("b", self.source, {"propositions": entry["canonical"]},
                                         item, item)
                                        for item, entry in zip([*changes, *scene], served,
                                                               strict=True)])  # fmt: skip
        if weak:
            self._opponent_first(kept)
        for item in [*changes, *scene]:  # MS-D §8.3: citing the item by handle allows what it shows
            self._tokens(item)
        board = {"v": FORMAT, "mover": self.mover, "changes": changes}
        if scene:
            board["scene"] = scene
        same, same_served = self._same_reply()
        if same is not None:
            board["same_reply"] = same
            if same_served is not None:
                served.append(same_served)
        played, played_served = self._played_material() if weak else (None, None)
        if played is not None:
            board["played_material"] = played
            served.append(played_served)
        elif played_served is not None:
            refused += 1  # its propositions refused: a fault (AG8-D §2.1)
        if refused:
            board["refused"] = refused
        self.unmatched = unmatched
        return board, served

    def _tokens(self, item: dict) -> None:
        tokens = self.session.board_tokens.setdefault(self.game.key, {})
        tokens[item["ref"]] = r.board_tokens(item["proves"], self.uci, self.digest["fen_before"])
        for uci, fen in self.extra_moves.get(id(item), ()):  # ST-D §2.5, §3.4: the moves it names
            tokens[item["ref"]].add_move(uci, fen)

    def _opponent_first(self, kept: list[tuple[dict, object]]) -> None:
        """BL-D §5 (3): while the opponent, to move and not in check, can take a mover's piece of
        gain ≥ 3 first, each threat that is no check points at that item (the largest gain, the
        first in the order on a tie) and says so; the suffix states only the pointer."""

        if self.facts.fact("status", self.child).in_check:
            return
        first = [(item, dict(rel.data)["gain"]) for item, rel in kept
                 if item["owner"] == self.mover and rel.kind == "exposed"
                 and dict(rel.data).get("gain", 0) >= FIRST_GAIN]  # fmt: skip
        if not first:
            return
        target = max(first, key=lambda x: x[1])[0]
        for item, rel in kept:
            if item["kind"] == "threat" and rel.kind != "check":
                item["opponent_first"] = target["ref"]
                item["proves"] = r.with_opponent_first(item["proves"])

    def _item(self, kind: str, owner: str, proves: str, propositions: list[dict]) -> dict:
        good = self.mover if kind == "threat" else r.other(owner if kind == "held" else self.mover)
        return {"kind": kind, "part": "reason", "owner": owner, "good_for": good,
                "proves": proves, "propositions": propositions}  # fmt: skip

    def _of_relation(self, relation) -> dict | None:
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
            item = self._item("lost_defence", mover, proves, [
                {"kind": "defence", "position": self.before, "defender": sq["defender"],
                 "defended": sq["defended"]},
                {"kind": "attack", "position": after, "attacker": sq["attacker"],
                 "target": sq["defended"]},
            ])  # fmt: skip
            since = self._since(relation.role("attacker").id, relation.role("defended").id)
            hitter, defended = names[sq["attacker"]], names[sq["defended"]]
            if since is None:  # ST-D §3.2: new with the move
                self._append(item, r.since_lost_defence(hitter, defended, self.move, None))
            else:
                self._append(item, r.since_lost_defence(hitter, defended, self.move, since["when"],
                                                        since["where"]),
                             since, at_p=True)  # fmt: skip
            return item
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
        elif kind == "exposed" and relation.side == mover:  # BL-D §3: with its attacker
            return self._held(relation) if relation.time == "held" else self._weakness(relation)
        elif kind == "exposed":
            proposition = {"kind": "exposed", "position": after, "piece": sq["piece"],
                           "exposed": "exposed", "gain": dict(relation.data)["gain"]}  # fmt: skip
        else:  # absolute_pin
            proposition = {"kind": "pin", "position": after, "pinned": sq["pinned"],
                           "pinner": sq["slider"]}  # fmt: skip
        side = "threat" if relation.side == enemy else "weakness"
        owner = enemy if side == "threat" else mover
        proves = r.change_proves(side, mover, self.move, proposition, names)
        item = self._item(side, owner, proves, [proposition])
        if kind == "exposed":  # ST-D §3.2 (review B4): an opponent piece the mover can now take
            attacker = self._attacker(self.child, sq["piece"])
            since = None if attacker is None else self._since(str(attacker[2]),
                                                              relation.role("piece").id)  # fmt: skip
            if since is not None:  # no attacker named (re-review N-a) or a new attack: nothing
                after_attack = {"kind": "attack", "position": after, "attacker": attacker[0],
                                "target": sq["piece"]}  # fmt: skip
                self._append(item, r.since_exposed(attacker[1], self.move, since["when"], True,
                                                   since["where"], since["moved"]),
                             since, at_p=True, also=[after_attack])  # fmt: skip
        return item

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
                hit = next(
                    (x for x in groups["held"] if x[1].identity() == relation.identity()), None
                )  # BL-D §2: the facts' held item of the same piece
                if hit is None:
                    item = self._held(relation)
                    if item is None:
                        unmatched.append(claim.id)
                        continue
                    groups["held"].append((item, relation))
                elif "leads_to" in hit[0]:  # a second claim on one held piece: listed (review N2)
                    unmatched.append(claim.id)
                    continue
                else:
                    item = hit[0]
                item["leads_to"] = leads
                self._append(item, r.link_remark(leads))
                continue
            hit = next(((item, rel) for kind in ("threat", "weakness", "lost_defence")
                        for item, rel in groups[kind]
                        if rel.identity() == relation.identity()), None)  # fmt: skip
            if hit is None:
                unmatched.append(claim.id)
                continue
            hit[0]["leads_to"] = leads
            self._append(hit[0], r.link_remark(leads))
        return unmatched

    def _attacker(self, node, square: str) -> tuple[str, str, object] | None:
        """(square, name, identity) of the piece that starts the exchange on `square` at `node`
        (`exchange.first_capture`), or None when the record names none."""

        exchange = self.facts.fact("exchange", node)
        if not isinstance(exchange, ExchangeFacts):
            return None
        entry = next((e for e in exchange.pieces if e.square == square), None)
        if entry is None or not entry.first_capture:
            return None
        at = entry.first_capture[:2]
        found = self.facts.fact("pieces", node).at(at)
        if found is None:
            return None
        name = r.piece(found.color.value, found.piece_type.value, at)
        return at, name, self.facts.node(node).piece_at(at)

    def _weakness(self, relation) -> dict | None:
        """BL-D §3: a mover's piece exposed after the move and not before, and its attacker."""

        piece = relation.role("piece")
        gain = dict(relation.data)["gain"]
        exposed = {"kind": "exposed", "position": self.after, "piece": piece.square,
                   "exposed": "exposed", "gain": gain}  # fmt: skip
        name = r.piece(piece.color, piece.type, piece.square)
        attacker = self._attacker(self.child, piece.square)
        if attacker is None:  # not expected (a gain above 0 names its first capture): a fault
            return None
        in_check = bool(self.facts.fact("status", self.parent).in_check)
        proves = r.weakness_proves(self.mover, self.move, name, gain, attacker[1], in_check)
        item = self._item("weakness", self.mover, proves, [
            exposed,
            {"kind": "attack", "position": self.after, "attacker": attacker[0],
             "target": piece.square},
        ])  # fmt: skip
        since = self._since(str(attacker[2]), piece.id)  # ST-D §3.2: new adds nothing here
        if since is not None:
            self._append(item, r.since_exposed(attacker[1], self.move, since["when"], False,
                                               since["where"], since["moved"]),
                         since, at_p=True)  # fmt: skip
        return item

    def _held(self, relation) -> dict | None:
        """A `held` item (MS-D §6 item 3, BL-D §3): the piece exposed before the move and after
        it, and the piece that attacks it first in the exchange at each."""

        (piece,) = [p for _n, p in relation.roles]
        before = self.facts.node(self.parent).square_of(PieceId(piece.id))
        exchange = self.facts.fact("exchange", self.parent)
        if before is None or not isinstance(exchange, ExchangeFacts):
            return None
        entry = next((e for e in exchange.pieces if e.square == before), None)
        if entry is None or not isinstance(entry.gain, Defined):
            return None
        gain_after = dict(relation.data).get("gain")
        if gain_after is None:
            return None
        first, then = self._attacker(self.parent, before), self._attacker(self.child, piece.square)
        if first is None or then is None:
            return None
        was = self.facts.fact("pieces", self.parent).at(before)
        kinds = (was.piece_type.value if was is not None else piece.type, piece.type)
        proves = r.held_proves(piece.color, self.move, kinds, before, piece.square, gain_after,
                               (first[1], then[1]), first[2] == then[2])  # fmt: skip
        item = self._item("held", piece.color, proves, [
            {"kind": "exposed", "position": self.before, "piece": before, "exposed": "exposed",
             "gain": entry.gain.value},
            {"kind": "attack", "position": self.before, "attacker": first[0], "target": before},
            {"kind": "exposed", "position": self.after, "piece": piece.square,
             "exposed": "exposed", "gain": gain_after},
            {"kind": "attack", "position": self.after, "attacker": then[0],
             "target": piece.square},
        ])  # fmt: skip
        if first[2] == then[2]:  # ST-D §3.2: one piece attacks it before and after
            since = self._since(str(first[2]), piece.id)
            if since is not None:  # the attack at `p` is the item's already
                self._append(item, r.since_held(first[1], since["when"], since["then"]), since)
        return item

    # -- ST-D: appended parts, since when, the scene, pawn structure and files -------------------

    def _append(self, item: dict, part: str, since: dict | None = None, at_p: bool = False,
                also: list[dict] = ()) -> bool:  # fmt: skip
        """ST-D §7: `part` appended to the item's `proves` whole or not at all, room kept for a
        threat's `opponent_first` suffix; with it, and only with it, the propositions and the move
        token it brings (re-review N-b): `also`, the attack at the position before the move
        (`at_p`) and at the run's first position."""

        reserve = len(r.OPPONENT_FIRST) if item["kind"] == "threat" else 0
        text = r.appended(item["proves"], part, reserve)
        if text is None:
            return False
        item["proves"] = text
        item["propositions"] += list(also)
        if since is not None:
            if at_p:
                item["propositions"].append(since["at_p"])
            if since["first"] is not None:
                item["propositions"].append(since["first"])
            if since["move"] is not None:
                self.extra_moves.setdefault(id(item), []).append(since["move"])
        return True

    def _pos(self, index: int) -> dict:
        """The position after `index` plies of the subject's path, as the board's positions are
        written (ST-D §3.3; the root as ply 1 before: re-review C1)."""

        if self.by_ply:
            return {"ply": index, "at": "after"} if index else {"ply": 1, "at": "before"}
        return {"from_root": list(self.path[:index])}

    def _attacks(self, index: int, attacker: str, target: str) -> tuple[str, str, int] | None:
        """(attacker's square, target's square, attacker's type) when the piece `attacker` attacks
        the piece `target` after `index` plies — python-chess's attack sets, as `pieces_v1`'s
        footprint — else None."""

        node = self.facts.node(self.nodes[index])
        a, t = node.square_of(PieceId(attacker)), node.square_of(PieceId(target))
        if a is None or t is None:
            return None
        board = chess.Board(node.fen)
        held = board.piece_at(chess.parse_square(a))
        if held is None or chess.parse_square(t) not in board.attacks(chess.parse_square(a)):
            return None
        return a, t, held.piece_type

    def _kinds(self, index: int, squares) -> list[tuple[str, str]]:
        """(color, type) of the pieces on `squares` after `index` plies of the subject's path."""

        board = chess.Board(self.facts.node(self.nodes[index]).fen)
        held = [board.piece_at(chess.parse_square(sq)) for sq in squares]
        return [(chess.COLOR_NAMES[q.color], chess.piece_name(q.piece_type)) for q in held]

    def _since(self, attacker: str, target: str) -> dict | None:
        """ST-D §3.1: None when the attack does not hold before the move (new); else its outcome —
        since k, at least since k (the walk's bound), from the start — with `when` (its words),
        `at_p` (the attack before the move), `first` (the attack at the run's first position, when
        that is not `p`) and `move` (the move of ply k with its FEN before, for since and long).
        WS-D §2: `then`, where the two pieces stood at `k` when not as at `p`; `where`, that and
        where they stood at `p` when not as after the move; `moved`, the target's (color, kind,
        square after) when the move moved it."""

        p = len(self.path)
        at_p = self._attacks(p, attacker, target)
        if at_p is None:
            return None
        k = p
        while k > 0 and p - k < SINCE_PLIES:
            earlier = self._attacks(k - 1, attacker, target)
            if earlier is None or earlier[2] != at_p[2]:  # a promotion ends the walk (review N9)
                break
            k -= 1
        if k == 0:
            outcome = "start"
        elif (
            p - k >= SINCE_PLIES
            and (prior := self._attacks(k - 1, attacker, target)) is not None
            and prior[2] == at_p[2]
        ):
            outcome = "long"
        else:
            outcome = "since"
        move = label = None
        if outcome != "start":
            fen, uci = self.facts.node(self.nodes[k - 1]).fen, self.path[k - 1]
            move, label = (uci, fen), r.numbered(fen, [uci], 0)
        first, then = None, []
        kinds_p = self._kinds(p, at_p[:2])  # WS-D §2.1: each piece by its type there (review B2)
        if k != p:
            a, t, _type = self._attacks(k, attacker, target)
            first = {"kind": "attack", "position": self._pos(k), "attacker": a, "target": t}
            then = [(*kind, sq) for kind, sq, now in zip(self._kinds(k, (a, t)), (a, t), at_p[:2])
                    if sq != now]  # fmt: skip
        child = self.facts.node(self.child)
        after = [child.square_of(PieceId(x)) for x in (attacker, target)]
        before = [(*kind, sq) for kind, sq, now in zip(kinds_p, at_p[:2], after)
                  if now is not None and sq != now]  # fmt: skip
        moved = (*kinds_p[1], after[1]) if after[1] not in (None, at_p[1]) else None
        return {"outcome": outcome, "when": r.since_words(outcome, label), "move": move,
                "at_p": {"kind": "attack", "position": self.before, "attacker": at_p[0],
                         "target": at_p[1]},
                "first": first,
                "then": r.since_where(outcome, label, then, []),
                "where": r.since_where(outcome, label, then, before),
                "moved": moved}  # fmt: skip

    def _scene(self, kept: list) -> list[dict]:
        """ST-D §2: what the opponent's previous move began against the mover's pieces, and its
        fate after the move by the attacker that made it."""

        p = len(self.path)
        if p == 0:
            return []
        view = self.game.facts.view()
        prev_parent, prev_child = self.nodes[p - 1], self.nodes[p]
        self.session._records(self.game, view, prev_parent, FAMILIES)
        self.session._records(self.game, view, prev_child, RELATION_FAMILIES)
        facts = self.game.facts.view()
        enemy = r.other(self.mover)
        held = {rel.roles[0][1].id for item, rel in kept if item["kind"] == "held"}
        rels = [
            rel
            for rel in move_relations(facts, prev_parent, prev_child)
            if rel.time == "began" and rel.side == self.mover and rel.kind in SCENE_KINDS
        ]
        exposed = {rel.role("piece").id for rel in rels if rel.kind == "exposed"}
        rels = [rel for rel in rels
                if not (rel.kind == "attack" and rel.role("target").id in exposed)
                and not (rel.kind == "attack" and rel.role("target").id in held)
                and not (rel.kind == "exposed" and rel.role("piece").id in held)]  # fmt: skip
        rels = sorted(limited(tuple(rels), enemy), key=_scene_order)[:SCENE_ITEMS]
        prev_fen, prev_uci = self.facts.node(prev_parent).fen, self.path[p - 1]
        prev = r.numbered(prev_fen, [prev_uci], 0)
        child = self.facts.node(self.child)
        after = chess.Board(child.fen)
        # WS-D §3 (review B1): after a check the count reads legal captures only, not the danger
        checked = bool(self.facts.fact("status", self.child).in_check)
        items = []
        for rel in rels:
            name = {n: r.piece(q.color, q.type, q.square) for n, q in rel.roles}
            data, props, pairs = {}, [], []  # pairs: (attacker id, its name, target Piece)
            if rel.kind == "check":
                data["checkers"] = [q.square for _n, q in rel.roles]
                props.append({"kind": "check", "position": self.before,
                              "checkers": data["checkers"]})  # fmt: skip
            elif rel.kind == "attack":
                a, t = rel.role("attacker"), rel.role("target")
                props.append({"kind": "attack", "position": self.before, "attacker": a.square,
                              "target": t.square})  # fmt: skip
                pairs.append((a.id, name["attacker"], t))
            elif rel.kind == "double_attack":
                actor = rel.role("actor")
                targets = [q for n, q in rel.roles if n == "target"]
                name["targets"] = [r.piece(q.color, q.type, q.square) for q in targets]
                props.append({"kind": "pattern", "position": self.before,
                              "pattern": "multi_target_attacks",
                              "participants": {"actor": actor.square,
                                               "targets": [q.square for q in targets]}})  # fmt: skip
                pairs += [(actor.id, name["actor"], q) for q in targets]
            elif rel.kind == "exposed":
                piece = rel.role("piece")
                attacker = self._attacker(prev_child, piece.square)
                if attacker is None:
                    continue
                data["gain"] = dict(rel.data)["gain"]
                name["attacker"] = attacker[1]
                props += [{"kind": "exposed", "position": self.before, "piece": piece.square,
                           "exposed": "exposed", "gain": data["gain"]},
                          {"kind": "attack", "position": self.before, "attacker": attacker[0],
                           "target": piece.square}]  # fmt: skip
                pairs.append((str(attacker[2]), attacker[1], piece))
            else:  # absolute_pin
                name["pinner"] = name["slider"]
                props.append({"kind": "pin", "position": self.before,
                              "pinned": rel.role("pinned").square,
                              "pinner": rel.role("slider").square})  # fmt: skip
            proves = r.scene_proves(rel.kind, prev, self.mover, name, data)
            item = {"kind": "scene", "relation": rel.kind, "part": "reason", "owner": self.mover,
                    "good_for": enemy, "proves": proves, "propositions": props}  # fmt: skip
            fates, after_props = [], []
            for attacker_id, attacker_name, target in pairs:
                a_sq = child.square_of(PieceId(attacker_id))
                t_sq = child.square_of(PieceId(target.id))
                target_name = r.piece(target.color, target.type, target.square)
                if a_sq is None:
                    fates = [(target_name, attacker_name, "taken", None, None)]
                    after_props = []
                    break
                if t_sq is None:
                    continue
                moved = t_sq if t_sq != target.square else None
                if chess.parse_square(t_sq) in after.attacks(chess.parse_square(a_sq)):
                    count = None if checked else self._count(target.id, t_sq)
                    fates.append((target_name, attacker_name, "kept", moved,
                                  None if count is None else count[1]))  # fmt: skip
                    after_props.append({"kind": "attack", "position": self.after,
                                        "attacker": a_sq, "target": t_sq})  # fmt: skip
                    if count is not None:  # WS-D §3: the count on its square after the move
                        after_props.append({"kind": "exposed", "position": self.after,
                                            "piece": t_sq, "exposed": count[0],
                                            "gain": count[1]})  # fmt: skip
                else:
                    fates.append((target_name, attacker_name, "ended", moved, None))
            if fates:
                self._append(item, r.scene_fate(self.move, fates, self.mover), also=after_props)
            self.extra_moves.setdefault(id(item), []).append((prev_uci, prev_fen))
            items.append(item)
        return items

    def _count(self, piece: str, square: str) -> tuple[str, int] | None:
        """WS-D §3 (review N5): `exposed_v1` of the piece after the move, as the verifier reads it,
        with the gain of the same `exchange` entry; None when undecided or without a defined gain."""

        state = exposed(self.facts, PieceId(piece), self.child)
        exchange = self.facts.fact("exchange", self.child)
        if state not in (Exposed.EXPOSED, Exposed.NOT_EXPOSED) or not isinstance(
            exchange, ExchangeFacts
        ):
            return None
        entry = next((e for e in exchange.pieces if e.square == square), None)
        if entry is None or not isinstance(entry.gain, Defined):
            return None
        return state.value, entry.gain.value

    def _structure(self) -> list[dict]:
        """ST-D §4.1–4.2: the pawns that became passed, isolated, doubled or backward with the move,
        and the files whose pawn state changed."""

        def raw(path):
            _view, nodes = self.session._node(self.game, path)
            return self.session._raw_records(self.game, nodes[-1], ("pawns",))[1]["pawns"]

        before, after = raw(self.path), raw((*self.path, self.uci))
        board = chess.Board(self.digest["fen_before"])
        move = chess.Move.from_uci(self.uci)
        moved = board.piece_type_at(move.from_square) == chess.PAWN and move.promotion is None
        to, frm = chess.square_name(move.to_square), chess.square_name(move.from_square)
        groups: dict[tuple[str, str], list[tuple[str, str, bool]]] = {}
        for pawn in after.pawns:
            was = frm if moved and pawn.square == to else pawn.square
            old = before.at(was)
            for flag in PAWN_FLAGS:
                if getattr(pawn, flag) and not (old is not None and getattr(old, flag)):
                    groups.setdefault((str(pawn.color.value), flag), []).append(
                        (pawn.square, was, old is not None)
                    )
        items = []
        for (color, flag), pawns in groups.items():
            props, said = [], []
            for square, was, had in pawns:
                props.append({"kind": "pawn", "position": self.after, "square": square,
                              "flag": flag, "value": True})  # fmt: skip
                if had:
                    props.append({"kind": "pawn", "position": self.before, "square": was,
                                  "flag": flag, "value": False})  # fmt: skip
                said.append(square if was == square else f"{square}(수 전 {was})")
            good = color if flag == "passed" else r.other(color)
            items.append({"kind": "structure", "part": "reason", "owner": color, "good_for": good,
                          "proves": r.structure_proves(color, good, self.move, said, flag),
                          "propositions": props})  # fmt: skip
        for b, a in zip(before.files, after.files, strict=True):
            if b.state == a.state:
                continue
            items.append({"kind": "file", "part": "reason", "owner": self.mover, "good_for": None,
                          "proves": r.file_proves(self.move, a.file, b.state.value, a.state.value),
                          "propositions": [
                              {"kind": "file", "position": self.before, "file": b.file,
                               "state": b.state.value},
                              {"kind": "file", "position": self.after, "file": a.file,
                               "state": a.state.value}]})  # fmt: skip
        return items

    # -- the played line's material (BL-D §4) ----------------------------------------------------

    def _played_material(self) -> tuple[dict | None, dict | None]:
        """On a weak move whose `material_loss_v2` is INCONCLUSIVE (not `MATE_LINE`): the mover's
        balance at two plies of the played line's window when it ends behind and not on a capture,
        and the best line ends better at its last ply that is no capture (undecided without one).
        (item, served) or (None, None); (None, {}) when its propositions are refused."""

        analysis = self.record["analysis"]
        subject = analysis["judgements"][0]
        played, best = subject.get("played"), subject.get("best")
        if played is None or best is None or best.get("rank") == played.get("rank"):
            return None, None
        loss = next((c for c in analysis["claims"] if c["template"] == "material_loss_v2"), None)
        if loss is None or loss["status"] != "inconclusive" or loss.get("reason") == "MATE_LINE":
            return None, None
        fen = self.digest["fen_before"]
        pv = [m["uci"] for m in played.get("pv") or []][:PV_PLIES]
        best_pv = [m["uci"] for m in best.get("pv") or []][:PV_PLIES]
        balances, quiet = _balances(fen, pv, self.mover)
        points = played_points(balances, quiet, *_balances(fen, best_pv, self.mover))
        if points is None:
            return None, None
        k, n, e = *points, balances[-1]
        line = played["ref"]
        at_n = r.numbered(fen, pv, n - 1)
        last = {"kind": "material", "line": line, "from": 0, "to": n, "side": self.mover,
                "balance": e}  # fmt: skip
        if k == n:
            propositions = [last]
            proves = r.played_material_proves(self.mover, None, 0, at_n, n, -e)
        else:
            propositions = [{"kind": "material", "line": line, "from": 0, "to": k,
                             "side": self.mover, "balance": balances[k - 1]}, last]  # fmt: skip
            proves = r.played_material_proves(self.mover, r.numbered(fen, pv, k - 1),
                                              -balances[k - 1], at_n, n, -e)  # fmt: skip
        verified, _fault = self._verify(propositions)
        if verified is None:
            return None, {}
        item = {"kind": "played_material", "part": "consequence", "owner": self.mover,
                "good_for": r.other(self.mover), "proves": proves, "propositions": propositions}  # fmt: skip
        self.session._serve(self.game, [("b", self.source, {"propositions": verified}, item, item)])
        self._tokens(item)
        return item, {"part": "consequence", "canonical": verified}

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
        fen = self.digest["fen_before"]  # PW-D §2: each move numbered from its own position
        after = chess.Board(fen)
        after.push_san(best_san)
        at_reply = after.fen()
        for san in same:
            after.push_san(san)
        proves = r.same_reply_proves(self.move, numbered_line(at_reply, same),
                                     numbered_line(fen, [best_san]),
                                     numbered_line(after.fen(), [top["move"]["san"]]),
                                     score_text(top["score"]), score_text(played["score"]))  # fmt: skip
        item = {"kind": "same_reply", "part": "reason", "proves": proves,
                "propositions": propositions}  # fmt: skip
        return item, {"part": "reason", "canonical": verified}


def _gated(relation, weak: bool) -> bool:
    """BL-D §2: a held relation (the mover's) gives an item at gain ≥ `HELD_GAIN`, any on a weak
    move; every other relation passes."""

    if relation.kind != "exposed" or relation.time != "held":
        return True
    return weak or dict(relation.data)["gain"] >= HELD_GAIN


def _scene_order(relation) -> tuple:
    """ST-D §2.1 (review N3): a check first, then by stake, the largest target's value, square."""

    pieces = [p for name, p in relation.roles
              if name in ("target", "piece", "pinned")]  # fmt: skip
    value = max((r.VALUE[p.type] for p in pieces), default=0)
    square = min((p.square for p in pieces), default="")
    return relation.kind != "check", -_stake(relation), -value, square


def _stake(relation) -> int:
    """BL-D §5 (1): what an item other than a threat puts at stake — an exposed piece its gain, a
    pin the pinned piece's value, a lost defence the defended piece's value (points_v1)."""

    if relation.kind == "exposed":
        return dict(relation.data)["gain"]
    for role in ("pinned", "defended"):
        piece = relation.role(role)
        if piece is not None:
            return r.VALUE[piece.type]
    return 0


def played_points(balances: list[int], quiet: list[bool], best_balances: list[int],
                  best_quiet: list[bool]) -> tuple[int, int] | None:  # fmt: skip
    """BL-D §4 over the two windows (balances after each ply, the mover's; whether each ply was
    no capture nor promotion): `(k, n)` when the played line ends behind (`e ≤ −1`) and not on a
    capture, and the best line's balance at its last quiet ply is above `e`; None otherwise —
    also when the best window has no quiet ply (owner's review O1: undecided)."""

    n = len(balances)
    if n < 2 or balances[-1] > -1 or not quiet[-1]:
        return None
    points = [j for j, q in enumerate(best_quiet) if q]
    if not points or best_balances[points[-1]] <= balances[-1]:
        return None
    e = balances[-1]
    return next(j for j in range(1, n + 1) if all(b <= e for b in balances[j - 1 :])), n


def _balances(fen: str, pv: list[str], mover: str) -> tuple[list[int], list[bool]]:
    """After each ply of `pv`: the mover's points minus the other side's against the start
    (points_v1, as `material_flow` counts them), and whether the ply was neither a capture nor a
    promotion."""

    board = chess.Board(fen)
    side = chess.WHITE if mover == "white" else chess.BLACK

    def points() -> int:
        return sum((1 if p.color == side else -1) * r.VALUE[chess.piece_name(p.piece_type)]
                   for p in board.piece_map().values() if p.piece_type != chess.KING)  # fmt: skip

    start, balances, quiet = points(), [], []
    for uci in pv:
        move = chess.Move.from_uci(uci)
        quiet.append(not board.is_capture(move) and move.promotion is None)
        board.push(move)
        balances.append(points() - start)
    return balances, quiet
