"""`board` of a digest (AG8-D §2, §5; MS-D §6; BL-D `board_v3`): what the move changed, by whose
side, and the same reply — a view of the reasoning layer's piece relations at the move; on a weak
move ordered by what is at stake, with the played line's material when the claim cannot decide.

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
    claim_relation,
    limited,
    move_relations,
)

from . import remarks as r
from .budget import BudgetError, EngineBusy
from .digest import PV_PLIES, numbered_line, score_text

FORMAT = "board_v3"
FAMILIES = ("pieces", "patterns", "exchange", "status")  # the records of the position before
WEAK_GRADES = ("inaccuracy", "mistake", "blunder")
HELD_GAIN = 3  # BL-D §2: a held piece from the facts on any grade from this gain (any if weak)
FIRST_GAIN = 3  # BL-D §5 (3): a mover's exposed piece the opponent can take before a threat counts
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
        # the `b` handles through the session's own path, its room made first (review B1); bound
        # to the subject and the analysis whose claims the items carry (review N2)
        self.source = {"kind": "board", "subject": [*self.path, self.uci],
                       "bundle": self.record.get("bundle")}  # fmt: skip
        self.session._serve(self.game, [("b", self.source, {"propositions": entry["canonical"]},
                                         item, item)
                                        for item, entry in zip(changes, served, strict=True)])  # fmt: skip
        if weak:
            self._opponent_first(kept)
        for item in changes:  # MS-D §8.3: citing the item by handle allows what it shows
            self._tokens(item)
        board = {"v": FORMAT, "mover": self.mover, "changes": changes}
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
                item["proves"] = r.capped(item["proves"] + r.link_remark(leads))
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
        return self._item("weakness", self.mover, proves, [
            exposed,
            {"kind": "attack", "position": self.after, "attacker": attacker[0],
             "target": piece.square},
        ])  # fmt: skip

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
        return self._item("held", piece.color, proves, [
            {"kind": "exposed", "position": self.before, "piece": before, "exposed": "exposed",
             "gain": entry.gain.value},
            {"kind": "attack", "position": self.before, "attacker": first[0], "target": before},
            {"kind": "exposed", "position": self.after, "piece": piece.square,
             "exposed": "exposed", "gain": gain_after},
            {"kind": "attack", "position": self.after, "attacker": then[0],
             "target": piece.square},
        ])  # fmt: skip

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
