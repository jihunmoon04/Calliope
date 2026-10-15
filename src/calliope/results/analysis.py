"""The optional per-ply `analysis` of `calliope_result_v1` (DF-D §4.3–§4.4).

Every claim, observation and judgement of an analysis, with its scope, effective scopes, evidence,
relations, causal checks and findings, projected by one recursive rule. No internal identifier
leaves (AR-D G3): nodes become `Position`s (the moves from the request's root), searches indexes
into `searches`, piece identities are dropped; positions by repetition identity become
`PositionKeyRef`s. A type the projection does not know is refused, never guessed.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

from calliope.facts import (
    Cp,
    EngineLineId,
    LineId,
    Mate,
    NodeId,
    NotApplicable,
    NotComputed,
    PositionKey,
    TreeView,
    Unavailable,
    Wdl,
)
from calliope.reasoning import (
    FINDING_KINDS,
    Analysis,
    CausalCheck,
    Claim,
    FactRef,
    Judgement,
    JudgementRef,
    LineScore,
    LineSegment,
    MaterialAmount,
    MissingLine,
    MoveRef,
    MoveSubject,
    Observation,
    ObservationRef,
    PieceRef,
    ProofScope,
    SearchMoveRef,
    SearchRef,
    SquareRef,
)

CHECK_KINDS = {
    "REALIZED": "realized",
    "COUNTERFACTUAL": "counterfactual",
    "ATTRIBUTED": "attributed",
}
PIECES = {"k": "king", "q": "queen", "r": "rook", "b": "bishop", "n": "knight", "p": "pawn"}


class ProjectionError(ValueError):
    """A value of a type the projection has no case for (DF-D §4.4)."""


class _Projection:
    def __init__(self, a: Analysis) -> None:
        self.a = a
        self.view: TreeView = a.tree.view(a.rev)
        self.root = self.view.root
        self.p = a.round_zero.subject.parent
        self.p_ply = len(self.view.path(self.p)) - 1
        self.searches: list[str] = []
        self.anchor: dict[str, NodeId] = {}
        for node in self.view.nodes():
            for binding in self.view.searches(node.node_id):
                self.anchor.setdefault(binding.search_id, node.node_id)

    # -- identities -------------------------------------------------------------------------

    def search(self, search_id: str | None) -> int | None:
        if search_id is None:
            return None
        if search_id not in self.searches:
            self.searches.append(search_id)
        return self.searches.index(search_id)

    def position(self, node: NodeId) -> dict:
        path = self.view.path(node)
        moves = [self.view.node(n).incoming_move for n in path[1:]]
        return {"kind": "position", "fen": self.view.node(node).fen, "from_root": moves,
                "ply": len(moves) - self.p_ply}  # fmt: skip

    def move(self, node: NodeId) -> dict:
        n = self.view.node(node)
        assert n.parent is not None
        return {"kind": "move", "uci": n.incoming_move, "san": self.view.fact("move", node).san,
                "fen": self.view.node(n.parent).fen}  # fmt: skip

    def san(self, node: NodeId | None, uci: str) -> str | None:
        if node is None:
            return None
        status = self.view.fact("status", node)
        found = next((m for m in getattr(status, "legal_moves", ()) if m.uci == uci), None)
        return found.san if found is not None else None

    # -- values (DF-D §4.4) -----------------------------------------------------------------

    def value(self, v: Any, board: NodeId | None = None) -> Any:
        if v is None or isinstance(v, bool | int | str):
            return v
        if isinstance(v, Enum):
            return v.value
        if isinstance(v, tuple | list):
            return [self.value(x, board) for x in v]
        if isinstance(v, NodeId):
            return self.position(v)
        if isinstance(v, PositionKey):
            return {"kind": "position_key", "epd": v.value}
        if isinstance(v, PieceRef):
            return self.piece(v)
        if isinstance(v, MoveRef):
            return self.move(v.node)
        if isinstance(v, SquareRef):
            return {"kind": "square", "square": v.square,
                    "fen": self.view.node(board or self.p).fen}  # fmt: skip
        if isinstance(v, LineSegment):
            return self.segment(v)
        if isinstance(v, SearchRef):
            return {"kind": "search_line", "search": self.search(v.search_id), "rank": v.rank}
        if isinstance(v, SearchMoveRef):
            return self.search_move(v)
        if isinstance(v, MaterialAmount):
            return {"points": v.points, "unit": "points_v1", "policy": v.policy}
        if isinstance(v, FactRef):
            return {"kind": "fact", "family": v.family, "target": self.value(v.target),
                    "path": list(v.path)}  # fmt: skip
        if isinstance(v, Cp):
            return {"cp": v.value}
        if isinstance(v, Mate):
            return {"mate": v.moves if v.winner.value == "white" else -v.moves}
        if isinstance(v, Wdl):
            return {"white_win": v.white_win, "draw": v.draw, "black_win": v.black_win}
        if isinstance(v, MissingLine):
            return {"kind": "missing_line", "search": self.search(v.search_id), "rank": v.rank,
                    "reason": v.reason}  # fmt: skip
        if isinstance(v, MoveSubject):
            return {"kind": "subject", "move": self.move(v.child)}
        if isinstance(v, EngineLineId | LineId):
            raise ProjectionError(f"a bare line id {v!r}: lines are projected as segments")
        if dataclasses.is_dataclass(v) and type(v) in FINDING_TYPES:
            return self.record(v)
        raise ProjectionError(f"no projection for {type(v).__name__}")

    def record(self, v: Any) -> dict:
        board = getattr(v, "board", None)
        out: dict[str, Any] = {"type": type(v).__name__}
        for f in dataclasses.fields(v):
            x = getattr(v, f.name)
            if isinstance(x, NotApplicable | NotComputed | Unavailable):
                out[f.name] = None
                reason = getattr(x, "reason", None)
                if reason is not None:
                    out[f"{f.name}_reason"] = reason
                continue
            if f.name == "keeping":  # OfferFinding: (SearchRef, Fate) pairs
                out[f.name] = [{"line": self.value(s), "fate": fate.value} for s, fate in x]
                continue
            out[f.name] = self.value(x, board)
        return out

    def piece(self, r: PieceRef) -> dict:
        fen = self.view.node(r.node).fen
        letter = _fen_piece(fen, r.square)
        if letter is None:
            raise ProjectionError(f"no piece on {r.square} at a referenced node")
        return {"kind": "piece", "square": r.square, "piece": PIECES[letter.lower()],
                "color": "white" if letter.isupper() else "black", "fen": fen}  # fmt: skip

    def segment(self, s: LineSegment) -> dict:
        try:
            record = self.view.line(s.line)
        except KeyError:
            record = None
        base: dict[str, Any] = {"kind": "line", "first": s.first, "last": s.last}
        if isinstance(s.line, EngineLineId):
            base |= {"search": self.search(s.line.search_id), "rank": s.line.rank}
        if record is None:
            return base | {"fen": None, "moves": []}
        lo, hi = s.first - record.first_index, s.last - record.first_index
        nodes = record.nodes[max(lo, 0) : hi + 1]
        moves = [{"uci": self.view.node(n).incoming_move, "san": self.view.fact("move", n).san}
                 for n in nodes[1:]]  # fmt: skip
        return base | {"fen": self.view.node(nodes[0]).fen, "moves": moves}

    def search_move(self, r: SearchMoveRef) -> dict:
        search = self.view.search(r.search_id)
        line = next(ln for ln in search.lines if ln.rank == r.rank)
        uci = line.pv[r.ply - 1]
        node: NodeId | None = self.anchor.get(r.search_id)
        for step in line.pv[: r.ply - 1]:
            node = self.view.child(node, step) if node is not None else None
        return {"kind": "search_move", "search": self.search(r.search_id), "rank": r.rank,
                "ply": r.ply, "uci": uci, "san": self.san(node, uci),
                "fen": self.view.node(node).fen if node is not None else None}  # fmt: skip

    # -- the parts (DF-D §4.3) --------------------------------------------------------------

    def scope(self, s: ProofScope | None) -> dict | None:
        if s is None:
            return None
        population = s.population
        return {
            "basis": s.basis.value,
            "quantifier": s.quantifier.value,
            "population": {
                "kind": population.kind.value,
                "search": self.search(population.search_id),
                "moves": [self.value(m) for m in population.moves],
            },
            "at": self.value(s.at),
            "witnesses": list(s.witnesses),
            "searches": [self.value(x) for x in s.searches],
            "depth": s.depth,
            "multipv": s.multipv,
            "plies": s.plies,
            "line_end": s.line_end.value if s.line_end is not None else None,
            "policies": list(s.policies),
        }

    def line_score(self, search_id: str | None, j: Judgement, ls: LineScore | None) -> dict | None:
        if ls is None:
            return None
        return {
            "search": self.search(search_id),
            "rank": ls.rank,
            "move": {"uci": ls.move, "san": self.san(j.subject.parent, ls.move)},
            "score": self.value(ls.score),
            "wdl": self.value(ls.wdl) if isinstance(ls.wdl, Wdl) else None,
            "expected": ls.expected,
        }

    def judgement(self, j: Judgement) -> dict:
        sid = j.search.search_id if j.search is not None else None
        out: dict[str, Any] = {"move": self.move(j.subject.child), "status": j.status.value}
        if j.reason is not None:
            out["reason"] = j.reason
        out |= {
            "search": self.search(sid),
            "played": self.line_score(sid, j, j.played),
            "best": self.line_score(sid, j, j.best),
            "alternatives": [self.line_score(sid, j, x) for x in j.alternatives],
            "loss": j.loss,
            "grade": j.grade.value if j.grade is not None else None,
            "policy": j.policy,
            "curve": dataclasses.asdict(j.curve) if j.curve is not None else None,
        }
        return out

    def observation(self, o: Observation, index: int) -> dict:
        return {"kind": o.kind, "version": o.version, "round": o.round, "index": index,
                "operands": [self.value(x) for x in o.operands],
                "evidence": [self.value(x) for x in o.evidence]}  # fmt: skip

    def target(self, t: Any) -> dict:
        if isinstance(t, str):
            return {"type": "claim", "id": t}
        if isinstance(t, ObservationRef):
            return {"type": "observation", "kind": t.kind, "version": t.version,
                    "round": t.round, "index": t.index}  # fmt: skip
        if isinstance(t, JudgementRef):
            return {"type": "judgement", "move": self.move(t.subject.child)}
        raise ProjectionError(f"no relation target {type(t).__name__}")

    def claim(self, c: Claim) -> dict:
        v = c.verdict
        out: dict[str, Any] = {"id": c.id, "template": c.hypothesis.template,
                               "role": c.hypothesis.role.value, "status": v.status.value}  # fmt: skip
        if v.reason is not None:
            out["reason"] = v.reason
        if v.refuted_by is not None:
            out["refuted_by"] = v.refuted_by
        out["scope"] = self.scope(v.scope)
        out["effective_scopes"] = [self.scope(s) for s in c.effective_scope]
        out["evidence"] = [self.value(x) for x in v.evidence]
        out["relations"] = [{"kind": r.kind.value, "target": self.target(r.target)}
                            for r in self.a.relations if r.source == c.id]  # fmt: skip
        out["checks"] = [{"kind": CHECK_KINDS[f.kind], "passed": f.passed,
                          "evidence": [self.value(x) for x in f.evidence]}
                         for f in v.findings if isinstance(f, CausalCheck)]  # fmt: skip
        out["findings"] = [self.value(f) for f in v.findings if not isinstance(f, CausalCheck)]
        return out


def _observation_indexes(observations: tuple[Observation, ...]) -> list[int]:
    """`ObservationRef.index`: the position within (round, kind), canonical order."""

    seen: dict[tuple, int] = {}
    out = []
    for o in observations:
        key = (o.kind, o.version, o.subject, o.round)
        out.append(seen.get(key, 0))
        seen[key] = seen.get(key, 0) + 1
    return out


def analysis(a: Analysis) -> dict:
    """The `analysis` record of one analysed ply (DF-D §4.3)."""

    p = _Projection(a)
    zero = a.round_zero
    judgements = [p.judgement(j) for j in zero.judgements]
    observations = [
        p.observation(o, i)
        for o, i in zip(zero.observations, _observation_indexes(zero.observations), strict=True)
    ]
    claims = [p.claim(c) for c in a.claims]
    searches = []
    for sid in p.searches:
        s = p.view.search(sid)
        anchor = p.anchor.get(sid)
        searches.append({
            "kind": s.kind.value,
            "position": p.position(anchor) if anchor is not None else None,
            "root_moves": list(s.root_moves) if s.root_moves is not None else None,
            "multipv": s.multipv,
            "depth": s.profile.depth,
            "profile": s.profile.name,
        })  # fmt: skip
    return {
        "root": {"fen": p.view.node(p.root).fen, "p_ply": p.p_ply},
        "searches": searches,
        "judgements": judgements,
        "observations": observations,
        "claims": claims,
    }


def _fen_piece(fen: str, square: str) -> str | None:
    file, rank = ord(square[0]) - ord("a"), int(square[1])
    col = 0
    for ch in fen.split()[0].split("/")[8 - rank]:
        if ch.isdigit():
            col += int(ch)
            continue
        if col == file:
            return ch
        col += 1
    return None


FINDING_TYPES = frozenset(k for k in (*FINDING_KINDS, CausalCheck) if dataclasses.is_dataclass(k))
