"""The guarded renderer and `phrases_en_v1` (R0-D §13, R3-D §2–§7).

`render(plan, analysis)` turns an `ExplanationPlan` into segments. Every segment has a source (a
claim, the judgement, the label, a scope, or a phrasebook connective). A slot's value comes only
from its source's own references, read through a handle that refuses anything else. The guard is
structural: it re-verifies nothing (R0-D §13.4).
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Self

from calliope.facts import POINTS_V1_BY_TYPE, Color, EngineLineId, NodeId, PieceType, TreeView
from calliope.reasoning.errors import GuardError
from calliope.reasoning.findings import (
    AlternativeFinding,
    CaptureHoldsFinding,
    CheckAnswerFinding,
    ChecksDrawFinding,
    ComparisonFinding,
    CompensationFinding,
    DefenceFinding,
    ForcingFinding,
    HangingFinding,
    MateFinding,
    MaterialFinding,
    MechanismFinding,
    MissedGainFinding,
    OfferFinding,
    PieceOfferFinding,
    PreventsFinding,
    ReplyFinding,
    ReplyKind,
    RescueFinding,
)
from calliope.reasoning.graph import ClaimRelation
from calliope.reasoning.hypotheses import RelationKind
from calliope.reasoning.labels import Label, LabelKind
from calliope.reasoning.observer import Judgement, JudgementStatus
from calliope.reasoning.planner import (
    DETAIL_AFTER,
    DETAILS,
    SACRIFICES,
    ExplanationPlan,
    plan,
    plan_digest,
)
from calliope.reasoning.refs import (
    LineSegment,
    MaterialAmount,
    MoveRef,
    PieceRef,
    ScopeRef,
    SearchMoveRef,
    SearchRef,
    SquareRef,
)
from calliope.reasoning.verification import Claim, ProofScope, VerdictStatus

PHRASES_EN_V1 = "phrases_en_v1"
CONNECTIVE = "CONNECTIVE"
MAX_LINE_PLIES = 6  # R3-D H5
IMMEDIATE_PLIES = (
    2  # R3-D §17: an event at the move or the reply is told plainly, later ones as the line's
)
PIECES = {"k": "king", "q": "queen", "r": "rook", "b": "bishop", "n": "knight", "p": "pawn"}
SLOT = re.compile(r"\{([a-z_]+)(?:\|([^/}]*)/([^}]*))?\}")
PAIR = ("piece_offer_v1", "capture_holds_v1")  # BRILLIANT's ground (R3-D H10)
MOVES = ("move", "search_move")  # the TraceRef kinds of a numbered move


@dataclass(frozen=True, slots=True)
class Segment:
    text: str
    source: object  # claim id | Judgement | Label | ScopeRef | CONNECTIVE


@dataclass(frozen=True, slots=True)
class RenderedExplanation:
    plan_digest: str
    language: str
    phrasebook: str
    segments: tuple[Segment, ...]
    label_rule: str | None = None  # R3-D H9
    label_provisional: bool = False

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)


@cache
def phrasebook() -> dict:
    data = resources.files("calliope.reasoning.render").joinpath("phrases/en.toml").read_bytes()
    return tomllib.loads(data.decode("utf-8"))


# -- the handle: a source and the references it may resolve (G1, G3) ----------------------------


def _refs(value: object, out: set) -> None:
    if isinstance(value, NodeId | str | EngineLineId):
        out.add(value)
    elif isinstance(value, LineSegment):
        out.add(value)
        out.add(value.line)
    elif isinstance(value, tuple | list):
        for v in value:
            _refs(v, out)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        out.add(value)
        for field in dataclasses.fields(value):
            _refs(getattr(value, field.name), out)


@dataclass(frozen=True, slots=True)
class TraceRef:
    """A reference a slot expressed (AR-D §4): what `trace` reports beside the text.

    `move`: the edge into `node`. `search_move`: `uci` played from `node`. `piece`: `square` at
    `node`. `square`: `square` shown on `node`'s board (EV-D §3.4). `line`: from `node`, the shown edges into `nodes` (at most six), `truncated` when
    more were left out; a zero-ply line shows only `uci`, played from `node`, and is truncated.
    """

    kind: str
    node: NodeId
    uci: str | None = None
    square: str | None = None
    nodes: tuple[NodeId, ...] = ()
    truncated: bool = False


class Expressed(str):
    """A formatter's text with the reference it expressed (`trace`); compares as its text."""

    ref: TraceRef

    def __new__(cls, text: str, ref: TraceRef) -> Self:
        out = super().__new__(cls, text)
        out.ref = ref
        return out


class Phrased(str):
    """A phrase with the references of its chosen variant's slots, in slot order (`trace`)."""

    refs: tuple[TraceRef, ...]

    def __new__(cls, text: str, refs: tuple[TraceRef, ...]) -> Self:
        out = super().__new__(cls, text)
        out.refs = refs
        return out


@dataclass(frozen=True, slots=True)
class TracedSegment:
    """A segment as `render` makes it, with the references its text expressed (AR-D §4)."""

    text: str
    source: object
    refs: tuple[TraceRef, ...]


class Handle:
    """What one source may read. Formatters receive the handle, never the view (R3-D §7)."""

    def __init__(self, source: object, view: TreeView, *contents: object) -> None:
        self.source = source
        self._view = view
        self._allowed: set = set()
        for content in contents:
            _refs(content, self._allowed)

    def check(self, ref: object) -> None:  # G3
        if ref not in self._allowed:
            raise GuardError(f"G3: {ref!r} is not among the references of {self.source!r}")

    def node(self, node: NodeId):  # G1
        if node not in self._allowed:
            raise GuardError(f"G1: node {node} is outside the references of {self.source!r}")
        return self._view.node(node)

    def fact(self, family: str, node: NodeId):
        self.node(node)
        return self._view.fact(family, node)

    def line(self, line_id):
        if line_id not in self._allowed:
            raise GuardError(f"G1: line {line_id} is outside the references of {self.source!r}")
        return self._view.line(line_id)

    def search_at(self, search_id: str) -> tuple:
        """The search record and the node it is bound at (R0-D §13.2)."""

        if search_id not in self._allowed:
            raise GuardError(f"G1: search {search_id} is outside the references of {self.source!r}")
        for node in self._view.nodes():
            if any(b.search_id == search_id for b in self._view.searches(node.node_id)):
                return self._view.search(search_id), node
        raise GuardError(f"G1: search {search_id} is bound at no node")

    def edge_nodes(self, node: NodeId) -> None:
        """A move into `node` also reads its parent (the move number)."""

        parent = self.node(node).parent
        if parent is not None:
            self._allowed.add(parent)


# -- slot values (R3-D §3) -----------------------------------------------------------------------


def _numbered(side_white: bool, fullmove: int, san: str) -> str:
    return f"{fullmove}.{san}" if side_white else f"{fullmove}...{san}"


def _move_ref(h: Handle, ref: MoveRef) -> Expressed:
    h.check(ref.node)  # the edge into a referenced node (G3)
    h.edge_nodes(ref.node)
    parent = h.node(h.node(ref.node).parent)
    text = _numbered(parent.side_to_move.value == "white", parent.fullmove_number,
                     h.fact("move", ref.node).san)  # fmt: skip
    return Expressed(text, TraceRef("move", ref.node))


def _search_move(h: Handle, search_id: str, rank: int) -> Expressed:
    search, node = h.search_at(search_id)
    line = next((x for x in search.lines if x.rank == rank), None)
    if line is None:
        raise GuardError(f"G3: search {search_id} has no rank {rank}")
    return _uci(h, node.node_id, line.pv[0], node)


def _uci(h: Handle, at: NodeId, uci: str, node=None) -> Expressed:
    h._allowed.add(at)  # the search's or the scope's node: its `status` gives SAN (R0-D §13.2)
    node = node or h.node(at)
    status = h.fact("status", at)
    move = next((m for m in status.legal_moves if m.uci == uci), None)
    if move is None:
        raise GuardError(f"G3: {uci} is not legal at {at}")
    text = _numbered(node.side_to_move.value == "white", node.fullmove_number, move.san)
    return Expressed(text, TraceRef("search_move", at, uci=uci))


def fmt_move(h: Handle, ref: object) -> Expressed:
    if isinstance(ref, MoveRef):
        return _move_ref(h, ref)
    h.check(ref)
    if isinstance(ref, SearchMoveRef):
        if ref.ply != 1:
            raise GuardError(f"G3: only ply 1 of a search is rendered, not {ref}")
        return _search_move(h, ref.search_id, ref.rank)
    if isinstance(ref, SearchRef) and ref.rank is not None:
        return _search_move(h, ref.search_id, ref.rank)
    raise GuardError(f"G3: {ref!r} is not a move")


def fmt_witness(h: Handle, scope: ProofScope) -> Expressed:
    if not scope.witnesses or not isinstance(scope.at, NodeId):
        raise GuardError("G3: the scope has no witness")
    return _uci(h, scope.at, scope.witnesses[0])


def _fen_piece(fen: str, square: str) -> str | None:
    file, rank = ord(square[0]) - ord("a"), int(square[1])
    row = fen.split()[0].split("/")[8 - rank]
    col = 0
    for ch in row:
        if ch.isdigit():
            col += int(ch)
            continue
        if col == file:
            return ch.lower()
        col += 1
    return None


def _piece_letter(h: Handle, ref: PieceRef) -> str:
    kind = _fen_piece(h.node(ref.node).fen, ref.square)  # a promoted pawn reads as its new type
    if kind is None:
        raise GuardError(f"G3: no piece on {ref.square} at {ref.node}")
    return kind


def fmt_piece(h: Handle, ref: PieceRef) -> Expressed:
    h.check(ref)
    kind = _piece_letter(h, ref)
    return Expressed(
        f"the {PIECES[kind]} on {ref.square}", TraceRef("piece", ref.node, square=ref.square)
    )


def fmt_line(h: Handle, seg: LineSegment) -> Expressed:
    h.check(seg)
    record = h.line(seg.line)
    nodes = record.nodes[seg.first - record.first_index : seg.last - record.first_index + 1]
    for n in nodes:
        h._allowed.add(n)
    moves = nodes[1:]
    if not moves:  # a zero-ply segment: its first move from the search, then "..."
        if not isinstance(seg.line, EngineLineId):
            raise GuardError("G3: an empty input segment has no move")
        h._allowed.add(seg.line.search_id)
        first = _search_move(h, seg.line.search_id, seg.line.rank)
        return Expressed(first + " ...", TraceRef("line", first.ref.node, uci=first.ref.uci,
                                                  truncated=True))  # fmt: skip
    out = []
    for i, n in enumerate(moves[:MAX_LINE_PLIES]):
        parent = h.node(h.node(n).parent)
        san = h.fact("move", n).san
        white = parent.side_to_move.value == "white"
        out.append(_numbered(white, parent.fullmove_number, san) if i == 0 or white else san)
    shown = tuple(moves[:MAX_LINE_PLIES])  # exactly the plies the text shows (AR-D §4)
    truncated = len(moves) > MAX_LINE_PLIES
    return Expressed(" ".join(out) + (" ..." if truncated else ""),
                     TraceRef("line", nodes[0], nodes=shown, truncated=truncated))  # fmt: skip


def fmt_square(h: Handle, ref: SquareRef, board: NodeId) -> Expressed:
    """A square, shown on `board`'s position (EV-D §3.4, rev. 2 B4)."""

    h.check(ref)
    h.node(board)
    return Expressed(ref.square, TraceRef("square", board, square=ref.square))


def fmt_side(color: Color) -> str:
    return "White" if color is Color.WHITE else "Black"


def fmt_amount(h: Handle, value: object) -> str:
    points = value.points if isinstance(value, MaterialAmount) else value
    if not isinstance(points, int):
        raise GuardError(f"G3: {value!r} is not an amount")
    return f"{points} point" if points == 1 else f"{points} points"


# -- bindings (R3-D §4) ---------------------------------------------------------------------------


def _finding(claim: Claim, kind: type):
    return next((f for f in claim.verdict.findings if isinstance(f, kind)), None)


def _event_suffix(event) -> str:  # R3-D review B4; §17: `line.` when it happens later in the line
    if event.promotion is not None:
        kind = "capture_promotion" if event.victim is not None else "promotion"
    else:
        kind = "capture"
    return f"line.{kind}" if event.ply > IMMEDIATE_PLIES else kind


def bind(claim: Claim, h: Handle, form: str) -> tuple[str, dict[str, str | None]]:
    """The key (`<form>` or `<form>.<suffix>`) and the slot values of a claim (R3-D §4)."""

    t = claim.hypothesis.template
    ops = claim.hypothesis.operands
    v: dict[str, str | None] = {}
    suffix = None
    if t == "mate_delivered_v1":
        f = _finding(claim, MateFinding)
        v["move"] = fmt_move(h, f.mating_move) if f.mating_move is not None else None
    elif t in ("mate_found_v1", "mate_allowed_v1"):
        f = _finding(claim, MateFinding)
        v["count"], v["line"] = str(f.moves), fmt_line(h, ops[0])
    elif t == "mate_in_one_allowed_v1":
        v["reply"] = fmt_witness(h, claim.verdict.scope)
    elif t == "mate_missed_v1":
        f = _finding(claim, ComparisonFinding)
        v["best"], v["count"] = fmt_move(h, f.best_move), str(f.best.moves)
    elif t in ("material_loss_v2", "material_gain_v3"):
        f = _finding(claim, MaterialFinding)
        suffix = _event_suffix(f.event)
        v["victim"] = fmt_piece(h, f.event.victim) if f.event.victim is not None else None
        v["capture"] = _move_ref(h, MoveRef(f.event.node))
        v["amount"] = fmt_amount(h, f.amount)
    elif t == "forcing_v1":
        f = _finding(claim, ForcingFinding)
        v["count"] = str(f.replies)
        suffix = ("check_single" if f.replies == 1 else "check") if f.check else "single"
    elif t == "check_answer_v1":
        f = _finding(claim, CheckAnswerFinding)
        suffix = f.kind.value
        v["checker"] = fmt_piece(h, f.checkers[0]) if f.checkers else None
    elif t == "only_move_v1":
        v["second"] = fmt_move(h, _finding(claim, AlternativeFinding).line)
    elif t == "prevents_v1":
        f = _finding(claim, PreventsFinding)
        v["count"] = str(f.alternatives)
        v["amount"] = fmt_amount(h, f.smallest_loss) if f.smallest_loss is not None else None
        suffix = f.kind.value + (".one" if f.alternatives == 1 else "")  # R3-D §17: verb agreement
    elif t == "sacrifice_offer_v1":
        f = _finding(claim, OfferFinding)
        v["victim"] = fmt_piece(h, f.event.victim) if f.event.victim is not None else None
        v["amount"] = fmt_amount(h, f.amount)
    elif t == "sacrifice_compensated_v2":
        suffix = _finding(claim, CompensationFinding).kind.value
    elif t in ("fork_v2", "pin_v2", "skewer_v2", "discovery_v2"):
        f = _finding(claim, MechanismFinding)
        v["actor"], v["move"] = fmt_piece(h, f.actor), fmt_move(h, f.move)
        suffix = "walked" if f.walked_into and t != "discovery_v2" else None
    elif t == "removed_defender_v2":
        f = _finding(claim, DefenceFinding)
        v["defender"], v["defended"] = fmt_piece(h, f.defender), fmt_piece(h, f.defended)
    elif t in ("newly_exposed_v1", "left_en_prise_v2"):
        f = _finding(claim, HangingFinding)
        v["piece"] = fmt_piece(h, f.piece)
        suffix = f.kind.value if t == "newly_exposed_v1" else None
    elif t == "better_move_v1":
        f = _finding(claim, ComparisonFinding)
        v["best"], v["line"] = fmt_move(h, f.best_move), fmt_line(h, ops[0])
    elif t in ("missed_gain_v1", "better_alternative_v1"):
        v["best"] = fmt_move(h, _finding(claim, MissedGainFinding).best)
    elif t == "checks_draw_v1":
        f = _finding(claim, ChecksDrawFinding)
        v["side"], v["line"] = fmt_side(f.checker), fmt_line(h, f.line)
        own = f.line.first % 2 == 0  # the run starts at ply first + 1; the mover plays odd plies
        suffix = f"{'mover' if own else 'opponent'}.{f.kind.value}"
    elif t == "checks_draw_missed_v1":
        f = _finding(claim, ChecksDrawFinding)
        assert isinstance(f.line.line, EngineLineId)
        v["best"] = fmt_move(h, SearchRef(f.line.line.search_id, f.line.line.rank))
        v["line"], suffix = fmt_line(h, f.line), f.kind.value
    elif t == "best_stops_reply_v1":
        f = _finding(claim, ReplyFinding)
        v["best"], v["piece"] = fmt_move(h, f.best), fmt_piece(h, f.piece)
        suffix = f.kind.value
        if f.kind is ReplyKind.COVERS:  # the reply played after the best move, from B1
            v["reply"] = _uci(h, f.board, h.fact("move", f.reply.node).uci)
            suffix += (
                ".piece"
                if f.lost >= POINTS_V1_BY_TYPE.get(PieceType(PIECES[_piece_letter(h, f.piece)]), 0)
                else ".material"
            )
            v["amount"] = fmt_amount(h, f.lost)
        else:
            v["reply"] = fmt_move(h, f.reply)
        if f.square is not None:
            v["square"] = fmt_square(h, f.square, f.board)
            v["capture"] = _uci(h, f.counter, f.answer)
    elif t == "piece_offer_v1":
        f = _finding(claim, PieceOfferFinding)
        v["piece"], v["amount"] = fmt_piece(h, f.piece), fmt_amount(h, f.offer)
        v["capture"] = fmt_move(h, f.taken_by)
    elif t == "capture_holds_v1":
        v["reply"] = fmt_move(h, _finding(claim, CaptureHoldsFinding).reply)
    elif t == "rescue_v1":
        v["piece"] = fmt_piece(h, _finding(claim, RescueFinding).piece)
    elif t != "sacrifice_sound_v1":
        raise GuardError(f"G5: no binding for {t}")
    return (f"{form}.{suffix}" if suffix else form), v


# -- phrases and variants (R3-D §5, §6) -----------------------------------------------------------


def _slots(variant: str) -> set[str]:
    return {m.group(1) for m in SLOT.finditer(variant)}


def _numbered_first(variant: str, values: dict) -> bool:
    """A sentence may open with a slot whose value is a numbered move ("33.Qc2"): a digit has no
    case to fix (R3-D §6), and no lead precedes it (EV-D §4, S6b)."""

    first = SLOT.match(variant)
    value = values.get(first.group(1)) if first is not None else None
    return isinstance(value, Expressed) and value.ref.kind in MOVES and value[:1].isdigit()


def phrase(
    table: str, key: str, values: dict, source_id: str, *, sentence: bool = False
) -> Phrased:
    """The variant at `int(h[:8], 16) mod n` among the usable ones, filled (R3-D §6; G5)."""

    variants = phrasebook().get(table, {}).get(key)
    if variants is None:
        raise GuardError(f"G5: no phrase {table}.{key}")
    usable = [x for x in variants if all(values.get(s) is not None for s in _slots(x))]
    if not usable:
        raise GuardError(f"G5: no usable variant of {table}.{key}")
    chosen = usable[int(source_id[:8], 16) % len(usable)]
    if sentence and chosen.startswith("{") and not _numbered_first(chosen, values):
        raise GuardError(f"G5: the sentence form {table}.{key} begins with a slot")

    def fill(m: re.Match) -> str:
        value = values[m.group(1)]
        if m.group(2) is not None:  # {count|singular/plural}
            return f"{value} {m.group(2) if value == '1' else m.group(3)}"
        return value

    text = SLOT.sub(fill, chosen)
    if text.endswith(" ...."):  # a truncated line ends the sentence: no closing "." (R3-D §16)
        text = text[:-1]
    names = list(dict.fromkeys(m.group(1) for m in SLOT.finditer(chosen)))  # slot order
    return Phrased(text, tuple(values[s].ref for s in names if isinstance(values[s], Expressed)))


def _sha(value: object) -> str:
    from calliope.reasoning.encoding import canonical_bytes

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _english_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _lower(text: Phrased) -> Phrased:
    return Phrased(text[:1].lower() + text[1:], text.refs)


def _reason(reason: str | None) -> str:
    key = "NOT_COMPUTED" if reason and reason.startswith("NOT_COMPUTED(") else (reason or "")
    return phrase("reason", key, {}, _sha(key))


# -- the renderer ---------------------------------------------------------------------------------


class _Renderer:
    def __init__(self, plan_: ExplanationPlan, analysis) -> None:
        self.plan = plan_
        self.view = analysis.tree.view(analysis.rev)
        self.claims = {c.id: c for c in analysis.claims}
        self.relations: tuple[ClaimRelation, ...] = analysis.relations
        self.judgement: Judgement = analysis.round_zero.judgements[0]
        self.labels: tuple[Label, ...] = analysis.labels
        self.segments: list[Segment] = []
        self.refs: list[tuple[TraceRef, ...]] = []  # per segment, for `trace`

    def handle(self, claim: Claim) -> Handle:
        h = claim.hypothesis
        return Handle(claim.id, self.view, h.operands, claim.verdict.evidence,
                      claim.verdict.findings, claim.verdict.scope)  # fmt: skip

    def claim_text(self, claim_id: str, form: str, *, sentence: bool) -> Phrased:
        claim = self.claims[claim_id]
        key, values = bind(claim, self.handle(claim), form)
        return phrase(claim.hypothesis.template, key, values, claim.id, sentence=sentence)

    def emit(self, parts: list[tuple[str, object]]) -> None:
        if self.segments:
            self.append(" ", CONNECTIVE)
        for i, (text, source) in enumerate(parts):
            if i:
                self.append(" ", CONNECTIVE)
            self.append(text, source)

    def append(self, text: str, source: object) -> None:
        self.segments.append(Segment(str(text), source))
        self.refs.append(text.refs if isinstance(text, Phrased) else ())

    def sentence(self, claim_id: str, lead: str | None = None, lead_form: str = "lead") -> None:
        if lead is None:
            self.emit([(self.claim_text(claim_id, "sentence", sentence=True), claim_id)])
            return
        first = self.claim_text(lead, lead_form, sentence=False)
        rest = _lower(self.claim_text(claim_id, "sentence", sentence=True))
        self.emit([(first, lead), (rest, claim_id)])

    def premise(self, claim_id: str, template: str) -> str | None:
        """The SUPPORTED premise of `template` behind `claim_id`: its derived lead (review B6)."""

        for use in self.claims[claim_id].hypothesis.premises:
            found = self.claims.get(use.claim)
            if found is not None and found.hypothesis.template == template and found.supported:
                return found.id
        return None

    def run(self) -> RenderedExplanation:
        p, j = self.plan, self.judgement
        self.guard()
        jh = Handle(j, self.view, j.subject)
        move = _move_ref(jh, MoveRef(j.subject.child))
        sid = _sha(j)
        played = (move.ref,)  # judgement and label segments reference the played move (AR-D §4)
        if j.status is JudgementStatus.DECIDED:  # S1
            self.emit([(phrase("judgement", j.grade.value, {"move": move}, sid), j)])
        else:
            values = {"move": move, "reason": _reason(j.reason)}
            self.emit([(phrase("judgement", "inconclusive", values, sid), j)])
        label = p.label
        if label is not None and label.kind is not LabelKind.MISS:  # S2, S3
            text = phrase("label", label.kind.value, {}, _sha(label))
            self.emit([(Phrased(text, played), label)])
            if label.kind is LabelKind.BRILLIANT:
                holds = next(
                    g for g in label.grounds if self.claims[g].hypothesis.template == PAIR[1]
                )
                self.sentence(holds, self.premise(holds, PAIR[0]))
            elif label.kind is LabelKind.GREAT:
                self.sentence(p.purpose[0])
            # MISS is told after what the move did (R3-D §17): see below
        if p.consequence:  # S4
            means = p.mechanism[0] if p.mechanism else None
            self.sentence(p.consequence[0], means, "means")
        if p.purpose and not (label is not None and label.kind is LabelKind.GREAT):  # S5
            function = p.purpose[0]
            lead = None
            if self.claims[function].hypothesis.template in SACRIFICES:
                lead = self.premise(function, "sacrifice_offer_v1")
            self.sentence(function, lead)
        comparison = next((x for x in p.justification if isinstance(x, str)), None)
        if label is not None and label.kind is LabelKind.MISS:  # S6 for MISS (R3-D §17)
            lead = Phrased(phrase("label", "miss.lead", {}, _sha(label)), played)
            rest = _lower(self.claim_text(comparison, "sentence", sentence=True))
            self.emit([(lead, label), (rest, comparison)])
        elif comparison:  # S6
            self.sentence(comparison)
        if p.detail:  # S6b (EV-D §4): its sentence opens with the best move, a numbered move
            self.sentence(p.detail[0])
        self.qualification()  # S7
        return RenderedExplanation(
            plan_digest(p), "en", PHRASES_EN_V1, tuple(self.segments),
            label.rule if label is not None else None,
            label.provisional if label is not None else False,
        )  # fmt: skip

    def qualification(self) -> None:
        phrases: list[str] = []
        sources: list[ScopeRef] = []
        for item in self.plan.qualification:
            if not isinstance(item, ScopeRef):
                continue
            claim = self.claims[item.claim]
            for scope in claim.effective_scope or (claim.verdict.scope,):
                for text in self.scope_phrases(scope, claim):
                    if text not in phrases:
                        phrases.append(text)
                        sources.append(item)
        if phrases:
            text = phrase("scope", "sentence", {"scopes": _english_list(phrases)},
                          _sha(tuple(sources)))  # fmt: skip
            self.emit([(text, sources[0] if len(sources) == 1 else tuple(sources))])
        for item in self.plan.qualification:
            if isinstance(item, str):  # a pending claim (H7)
                claim = self.claims[item]
                name = phrase("claim", claim.hypothesis.template, {}, claim.id)
                values = {"claim": name, "reason": _reason(claim.verdict.reason)}
                self.emit([(phrase("scope", "pending", values, claim.id), item)])

    def scope_phrases(self, scope: ProofScope, claim: Claim) -> list[str]:
        if scope.basis.value == "exact":
            return []  # exact facts are not qualified (R3-D §5)
        h = Handle(ScopeRef(claim.id), self.view, scope)
        table = phrasebook()["scope"]
        q, pk = scope.quantifier.value, scope.population.kind.value
        key = f"{scope.basis.value}.{q}.{pk}"
        key = key if key in table else f"{scope.basis.value}.{q}"
        values = {"depth": str(scope.depth) if scope.depth is not None else None}
        if scope.population.search_id is not None:
            h.check(scope.population.search_id)
            values["count"] = str(len(self.view.search(scope.population.search_id).lines))
        out = [phrase("scope", key, values, _sha(scope))]
        for policy in scope.policies:
            if f"policy.{policy}" in table:
                out.append(phrase("scope", f"policy.{policy}", {}, _sha(scope)))
        return out

    # -- G4 ---------------------------------------------------------------------------------------

    def guard(self) -> None:
        p = self.plan
        if p.subject != self.judgement.subject or p.judgement.subject != self.judgement.subject:
            raise GuardError("G4: the plan's subject is not the analysis's target")
        if p.label is not None:  # the label must be the analysis's own (R3 review B2)
            if p.label not in self.labels:
                raise GuardError(f"G4: the label {p.label.kind.value} is not in the analysis")
            for ground in p.label.grounds:
                found = self.claims.get(ground)
                if found is None or found.verdict.status is not VerdictStatus.SUPPORTED:
                    raise GuardError(f"G4: the label's ground {ground} is not SUPPORTED")
        assertive = (*p.purpose, *p.mechanism, *p.consequence,
                     *(x for x in p.justification if isinstance(x, str)), *p.detail)  # fmt: skip
        for cid in assertive:
            claim = self.claims.get(cid)
            if claim is None or claim.verdict.status is not VerdictStatus.SUPPORTED:
                raise GuardError(f"G4: {cid} is not SUPPORTED")
            if (
                claim.hypothesis.template in PAIR
                or claim.hypothesis.template == "sacrifice_offer_v1"
            ):
                raise GuardError(f"G4: {claim.hypothesis.template} is stored in a role")
        if len(p.purpose) > 1 or len(p.mechanism) > 1 or len(p.consequence) > 1:
            raise GuardError("G4: a role holds more than one claim (a stored lead)")
        if len(p.detail) > 1:
            raise GuardError("G4: the plan holds more than one detail")
        if p.detail:  # EV-D §4: a detail follows a comparison it can explain
            if self.claims[p.detail[0]].hypothesis.template not in DETAILS:
                raise GuardError("G4: the detail is not a best_stops_reply_v1 claim")
            compared = next((x for x in p.justification if isinstance(x, str)), None)
            if compared is None or self.claims[compared].hypothesis.template not in DETAIL_AFTER:
                raise GuardError("G4: the detail follows no comparison it can explain")
        if p.mechanism:
            explains = any(
                r.source == p.mechanism[0] and r.target == p.consequence[0]
                and r.kind is RelationKind.EXPLAINS for r in self.relations
            ) if p.consequence else False  # fmt: skip
            if not explains:
                raise GuardError("G4: the mechanism has no EXPLAINS edge to the consequence")
        label = p.label
        if label is not None and label.kind is LabelKind.BRILLIANT:
            templates = sorted(self.claims[g].hypothesis.template for g in label.grounds)
            if templates != sorted(PAIR):
                raise GuardError("G4: BRILLIANT's ground is not the pair")
            holds = next(g for g in label.grounds if self.claims[g].hypothesis.template == PAIR[1])
            if self.premise(holds, PAIR[0]) not in label.grounds:
                raise GuardError("G4: capture_holds_v1 does not rest on the label's offer")


def render(plan_: ExplanationPlan, analysis) -> RenderedExplanation:
    """`phrases_en_v1` over a plan of `analysis` (R3-D §2–§7)."""

    return _Renderer(plan_, analysis).run()


def trace(plan_: ExplanationPlan, analysis) -> tuple[TracedSegment, ...]:
    """`render`'s segments with the references each one's text expressed (AR-D §4): one per
    slot of its chosen variant that names the board, in slot order. Same bindings, same variant
    choice: `render` with the references kept, not a second renderer."""

    renderer = _Renderer(plan_, analysis)
    rendered = renderer.run()
    return tuple(
        TracedSegment(s.text, s.source, refs)
        for s, refs in zip(rendered.segments, renderer.refs, strict=True)
    )


def plan_analysis(analysis) -> ExplanationPlan:
    """The one path from an analysis to its plan (R4-D §2.3, review B5): `plan` with `ply_of`
    read from the analysis's final view. `explain`, storage's save and load all use it."""

    view = analysis.tree.view(analysis.rev)

    def ply_of(claim: Claim) -> int:
        found = _finding(claim, MechanismFinding)
        return view.node(found.node).ply if found is not None else 0

    return plan(analysis.round_zero.judgements, analysis.claims, analysis.relations,
                analysis.labels, ply_of)  # fmt: skip


def explain(analysis) -> RenderedExplanation:
    """Plan (`selection_v1`, through `plan_analysis`) and render one analysis."""

    return render(plan_analysis(analysis), analysis)


def claim_sentence(analysis, claim_id: str) -> str | None:
    """One claim's sentence form on its own, bound and phrased as `render` would write it (AG6-D
    §3.2): for a claim the plan left out. None for a claim the analysis does not hold, or one
    whose template has no usable sentence form."""

    renderer = _Renderer(None, analysis)  # no plan: only `claim_text` is used
    if claim_id not in renderer.claims:
        return None
    try:
        return str(renderer.claim_text(claim_id, "sentence", sentence=True))
    except (GuardError, LookupError, AttributeError, TypeError, ValueError):
        return None  # no sentence form, or one its findings cannot fill


__all__ = [
    "CONNECTIVE",
    "PHRASES_EN_V1",
    "GuardError",
    "Handle",
    "RenderedExplanation",
    "Segment",
    "TraceRef",
    "TracedSegment",
    "claim_sentence",
    "explain",
    "phrase",
    "phrasebook",
    "plan_analysis",
    "render",
    "trace",
]
