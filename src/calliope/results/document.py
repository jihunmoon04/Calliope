"""`calliope_result_v1`: the builder, its inputs and its cross-checks (AR-D §2–§5)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from itertools import pairwise
from typing import Any

from calliope.facts import Color, Cp, Mate, NodeId, TreeView
from calliope.reasoning import (
    Analysis,
    Grade,
    Judgement,
    JudgementStatus,
    Label,
    LabelKind,
    RenderedExplanation,
    ScopeRef,
    TraceRef,
    VerdictStatus,
    build_digest,
    explain,
    plan_analysis,
    trace,
)

SCHEMA = "calliope_result_v1"
HEADERS = ("white", "black", "white_rating", "black_rating", "time_control", "site", "date",
           "result")  # fmt: skip
RATINGS = ("white_rating", "black_rating")
LABEL_KINDS = ("brilliant", "great", "miss")  # provenance.label_rules (AR-D §2)
PIECES = {"k": "king", "q": "queen", "r": "rook", "b": "bishop", "n": "knight", "p": "pawn"}
CONNECTIVE = "CONNECTIVE"  # the renderer's connective source (R3-D §7)
SHA256 = re.compile(r"[0-9a-f]{64}")


# DF-D §3.1: every number of the document has a unit (the registry's `unit.*` entries)
UNITS = {
    "score": {"cp": "cp_white", "mate": "mate_white"},
    "loss": "expected_2000",
    "expected": "expected_2000",
    "material": "points_v1",
    "wdl": "permille_white",
}


class ResultError(Exception):
    """The inputs do not describe one consistent game result (AR-D §5)."""


@dataclass(frozen=True, slots=True)
class GameMove:
    san: str
    uci: str
    fen_before: str  # the fact engine's form: `board.fen()`, en passant only when legal
    fen_after: str


@dataclass(frozen=True, slots=True)
class GameInput:
    """The whole game, normalized by the caller (AR-D §5, G8). `headers` holds any of `HEADERS`;
    the ratings are integers, the others strings."""

    start_fen: str
    moves: tuple[GameMove, ...]
    headers: Mapping[str, str | int | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EngineRun:
    """The engine port's `identity` and the request's `EngineProfile` (AR-D §5)."""

    identity: Any  # EngineIdentity
    profile: Any  # EngineProfile


@dataclass(frozen=True, slots=True)
class Bundle:
    tree: str  # sha256 of the `fact_tree_v1` bytes
    graph: str  # sha256 of the `claim_graph_v1` bytes
    stored: bool  # both documents were written and re-loaded (AR-D §3)


@dataclass(frozen=True, slots=True)
class PlyInput:
    ply: int  # 1-based, into `GameInput.moves`
    analysis: Analysis
    rendered: RenderedExplanation
    bundle: Bundle | None = None


@cache
def schema() -> dict:
    """The JSON Schema of `calliope_result_v1` (2020-12), shipped with the package."""

    data = resources.files("calliope.results").joinpath(f"schema/{SCHEMA}.json").read_bytes()
    return json.loads(data)


def view_schema() -> dict:
    """The JSON Schema of the MCP App's board document `calliope_view_v1` (AG6-D §6.1); its
    `result` refers to `calliope_result_v1` by `$id`."""

    data = resources.files("calliope.results").joinpath("schema/calliope_view_v1.json").read_bytes()
    return json.loads(data)


def dumps(document: dict) -> bytes:
    """Compact UTF-8 JSON, keys in the document's order (AR-D §5)."""

    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# -- the document ---------------------------------------------------------------------------------


def game_result(
    game: GameInput, engine: EngineRun, plies: Iterable[PlyInput], *, analysis: bool = False
) -> dict:
    """`calliope_result_v1` of a game and its analysed plies; pure (AR-D §5). With `analysis`, each
    ply also carries every claim, observation and judgement of its analysis (DF-D §4.3)."""

    plies = tuple(plies)
    if not plies:
        raise ResultError("no analysed ply")
    _check_game(game)
    numbers = [p.ply for p in plies]
    if any(not isinstance(n, int) or isinstance(n, bool) for n in numbers):
        raise ResultError("a ply number is not an integer")
    if any(b <= a for a, b in pairwise(numbers)):
        raise ResultError(f"the plies are not strictly increasing: {numbers}")
    if numbers[0] < 1 or numbers[-1] > len(game.moves):
        raise ResultError(f"a ply is outside the game's {len(game.moves)} moves")

    first = plies[0].analysis
    build, zero = first.build, first.round_zero
    if build is None:
        raise ResultError("the analysis records no reasoner build")
    root = first.tree.view(first.rev).request(1).root
    records = []
    for p in plies:
        _check_common(p, build, zero, root, game, engine)
        records.append(_ply(game, p, with_analysis=analysis))

    rendered = plies[0].rendered
    phrasebooks = dict(build.phrasebooks)
    if rendered.phrasebook not in phrasebooks:
        raise ResultError(f"the build has no phrasebook {rendered.phrasebook!r}")
    return {
        "schema": SCHEMA,
        "provenance": {
            "reasoning_build_version": build.reasoning_build_version,
            "build_digest": build_digest(build),
            "phrasebook": {
                "name": rendered.phrasebook,
                "digest": phrasebooks[rendered.phrasebook],
            },
            "engine": _engine(engine),
            "label_rules": _label_rules(build.label_rules),
        },
        "game": {
            "start_fen": game.start_fen,
            "moves": [{"san": m.san, "uci": m.uci} for m in game.moves],
            "headers": _headers(game.headers),
        },
        "grading": _grading(zero.request.grading, zero.grading),
        "units": UNITS,
        "plies": records,
        "summary": {
            side: _counts(r for r in records if r["side"] == side) for side in ("white", "black")
        },
    }


def _engine(engine: EngineRun) -> dict:
    profile = engine.profile
    return {
        "name": engine.identity.name,
        "binary_sha256": engine.identity.binary_sha256,
        "profile": {
            "name": profile.name,
            "depth": profile.depth,
            "time_cap_ms": profile.time_cap_ms,
            "multipv": profile.multipv,
            "threads": profile.threads,
            "hash_mb": profile.hash_mb,
        },
    }


def _label_rules(rules: tuple[str, ...]) -> dict:
    out = {}
    for kind in LABEL_KINDS:  # the build's last (current) rule of each kind
        found = [r for r in rules if r.startswith(f"{kind}_")]
        if not found:
            raise ResultError(f"the build has no {kind} rule")
        out[kind] = found[-1]
    return out


def _headers(headers: Mapping[str, str | int | None]) -> dict:
    out = {}
    for key in HEADERS:
        value = headers.get(key)
        if value is None:
            continue
        rating = key in RATINGS
        if rating != (isinstance(value, int) and not isinstance(value, bool)) or (
            not rating and not isinstance(value, str)
        ):
            raise ResultError(f"the header {key} is not a{'n integer' if rating else ' string'}")
        out[key] = value
    return out


def _grading(spec, grading) -> dict:
    curve = grading.curve
    if curve is None:
        return {"policy": grading.policy, "curve": None, "fallback": False}
    out: dict[str, Any] = {"model": curve.model, "source": curve.source.value}
    for key in ("scale", "table", "time_class", "band", "rating"):
        value = getattr(curve, key)
        if value is not None:
            out[key] = value
    out["pool"] = spec.rating_pool if curve.source.value == "table" else None
    out["clamped"] = curve.conversion_clamped or curve.band_clamped
    return {"policy": grading.policy, "curve": out, "fallback": curve.source.value == "default"}


def _counts(records: Iterable[dict]) -> dict:
    grades = {g.value: 0 for g in Grade}
    labels = {k.value: 0 for k in LabelKind}
    inconclusive = 0
    for r in records:
        if r["grade"] is not None:
            grades[r["grade"]] += 1
        if r["label"] is not None:
            labels[r["label"]["kind"]] += 1
        inconclusive += r["status"] == "inconclusive"
    return {"grades": grades, "labels": labels, "inconclusive": inconclusive}


# -- cross-checks (AR-D §5) -----------------------------------------------------------------------


def _check_game(game: GameInput) -> None:
    before = game.start_fen
    for i, move in enumerate(game.moves, 1):
        if move.fen_before != before:
            raise ResultError(f"the FEN chain breaks before ply {i}")
        before = move.fen_after


def _check_common(p: PlyInput, build, zero, root, game: GameInput, engine: EngineRun) -> None:
    a = p.analysis
    here = a.round_zero
    view = a.tree.view(a.rev)
    if a.build != build:
        raise ResultError(f"ply {p.ply}: the analysis has another reasoner build")
    if here.request.target != p.ply:
        raise ResultError(f"ply {p.ply}: the analysis is of ply {here.request.target}")
    if view.request(1).root != root:
        raise ResultError(f"ply {p.ply}: the analysis has another root")
    if view.node(view.root).fen != game.start_fen:
        raise ResultError(f"ply {p.ply}: the game starts elsewhere than the analysis's root")
    if (here.request.grading, here.grading) != (zero.request.grading, zero.grading):
        raise ResultError(f"ply {p.ply}: the analysis has another grading")
    if here.request.profile != engine.profile:
        raise ResultError(f"ply {p.ply}: the analysis ran another engine profile")
    for node in view.nodes():
        for bound in view.searches(node.node_id):
            if view.search(bound.search_id).identity != engine.identity:
                raise ResultError(f"ply {p.ply}: a search ran another engine")
    path = _path(view, here.subject.child)
    if path != [m.uci for m in game.moves[: p.ply]]:
        raise ResultError(f"ply {p.ply}: the analysis's moves are not the game's")
    move = game.moves[p.ply - 1]
    if (move.fen_before, move.fen_after) != (
        view.node(here.subject.parent).fen,
        view.node(here.subject.child).fen,
    ):
        raise ResultError(f"ply {p.ply}: the game's FENs are not the analysis's")
    if explain(a) != p.rendered:  # R4's `save` check: the whole rendering
        raise ResultError(f"ply {p.ply}: the rendering is not this analysis's")


def _path(view: TreeView, node_id: NodeId) -> list[str]:
    out = []
    node = view.node(node_id)
    while node.parent is not None:
        out.append(node.incoming_move)
        node = view.node(node.parent)
    return out[::-1]


# -- one ply (AR-D §3, §4) ------------------------------------------------------------------------


def _ply(game: GameInput, p: PlyInput, *, with_analysis: bool = False) -> dict:
    a = p.analysis
    view = a.tree.view(a.rev)
    zero = a.round_zero
    j: Judgement = zero.judgements[0]
    if j.subject != zero.subject:
        raise ResultError(f"ply {p.ply}: the first judgement is not the target's")
    move = game.moves[p.ply - 1]
    side, fullmove = move.fen_before.split()[1], int(move.fen_before.split()[5])

    traced = trace(plan_analysis(a), a)
    if [(s.text, s.source) for s in traced] != [(s.text, s.source) for s in p.rendered.segments]:
        raise ResultError(f"ply {p.ply}: trace differs from the rendering")
    claims = {c.id: c for c in a.claims}
    segments, named = [], []
    for s in traced:
        record = _segment(view, s.text, s.source, s.refs, claims)
        named += [record["claim"]] if "claim" in record else record.get("claims", [])
        segments.append(record)
    text = "".join(s["text"] for s in segments)
    if text != p.rendered.text:
        raise ResultError(f"ply {p.ply}: the segments do not rebuild the text")

    label = next((x for x in a.labels if x.subject == zero.subject), None)
    record: dict[str, Any] = {
        "ply": p.ply,
        "move_number": fullmove,
        "side": "white" if side == "w" else "black",
        "san": move.san,
        "uci": move.uci,
        "fen_before": move.fen_before,
        "fen_after": move.fen_after,
        "status": j.status.value,
    }
    if j.status is not JudgementStatus.DECIDED:
        record["reason"] = j.reason or ""
    record["grade"] = j.grade.value if j.grade is not None else None
    record["label"] = _label(label)
    record["evaluation"] = _evaluation(view, j)
    record["text"] = text
    record["segments"] = segments
    record["claims"] = _claims(a, zero.subject, named)
    if p.bundle is not None:
        record["bundle"] = _bundle(p.ply, p.bundle)
    if with_analysis:
        from calliope.results.analysis import analysis

        record["analysis"] = analysis(a)
    return record


def _bundle(ply: int, bundle: Bundle) -> dict:
    """The bundle's digests as the schema states them (AR1 review B1): refused, never copied."""

    for name in ("tree", "graph"):
        value = getattr(bundle, name)
        if not (isinstance(value, str) and SHA256.fullmatch(value)):
            raise ResultError(f"ply {ply}: the bundle's {name} digest is not a sha256 hex digest")
    if not isinstance(bundle.stored, bool):
        raise ResultError(f"ply {ply}: the bundle's stored flag is not a boolean")
    return {"tree": bundle.tree, "graph": bundle.graph, "stored": bundle.stored}


def _label(label: Label | None) -> dict | None:
    if label is None:
        return None
    return {"kind": label.kind.value, "rule": label.rule, "provisional": label.provisional}


def _score(score) -> dict:
    if isinstance(score, Cp):
        return {"cp": score.value}  # already White's view
    if isinstance(score, Mate):
        return {"mate": score.moves if score.winner is Color.WHITE else -score.moves}
    raise ResultError(f"unknown score {score!r}")


def _evaluation(view: TreeView, j: Judgement) -> dict:
    if j.status is not JudgementStatus.DECIDED or j.played is None or j.best is None:
        return {"grade_basis": None}
    out: dict[str, Any] = {"played": _score(j.played.score), "best": _score(j.best.score)}
    out["expected"] = {"played": j.played.expected, "best": j.best.expected}  # DF-D §3.1
    out["best_move"] = {"san": _san(view, j.subject.parent, j.best.move), "uci": j.best.move}
    if j.loss is not None:
        out["loss"] = j.loss
    p, b = j.played.score, j.best.score
    if j.played.rank == 1:  # `observer.grade`'s order: rank 1, the mate table, the bands
        basis = "best_move"
    elif isinstance(p, Mate) and isinstance(b, Mate) and p.winner is b.winner:
        basis = "mate_distance"
    else:
        basis = "expected_points"
    out["grade_basis"] = basis
    if j.search is not None:  # DF-D §3.2: the search S the grade read
        search = view.search(j.search.search_id)
        out["search"] = {"kind": search.kind.value, "multipv": search.multipv,
                         "depth": search.profile.depth, "profile": search.profile.name}  # fmt: skip
    return out


def _claims(a: Analysis, subject, named: list[str]) -> list[dict]:
    wanted = set(named)
    out = []
    for c in a.claims:
        own = c.hypothesis.subject == subject and c.supported
        if not (own or c.id in wanted):
            continue
        if c.verdict.status is VerdictStatus.REFUTED:
            raise ResultError(f"a segment names the refuted claim {c.id}")
        entry = {"id": c.id, "template": c.hypothesis.template,
                 "role": c.hypothesis.role.value, "status": c.verdict.status.value}  # fmt: skip
        if c.verdict.reason is not None:
            entry["reason"] = c.verdict.reason
        entry["rendered"] = c.id in wanted
        out.append(entry)
    missing = wanted - {e["id"] for e in out}
    if missing:
        raise ResultError(f"a segment names an unknown claim: {sorted(missing)}")
    return out


# -- segments and refs (AR-D §4) ------------------------------------------------------------------


def _segment(view: TreeView, text: str, source, refs: tuple[TraceRef, ...], claims) -> dict:
    out: dict[str, Any] = {"text": text}
    if isinstance(source, Judgement):
        out["source"] = "judgement"
    elif isinstance(source, Label):
        out["source"] = "label"
    elif isinstance(source, ScopeRef):
        out["source"], out["claim"] = "scope", source.claim
    elif isinstance(source, tuple) and all(isinstance(x, ScopeRef) for x in source):
        out["source"], out["claims"] = "scope", [x.claim for x in source]
    elif source == CONNECTIVE:
        out["source"] = "connective"
    elif isinstance(source, str) and source in claims:
        out["source"], out["claim"] = "claim", source
    else:
        raise ResultError(f"unknown segment source {source!r}")
    out["refs"] = [_ref(view, r) for r in refs]
    return out


def _ref(view: TreeView, r: TraceRef) -> dict:
    if r.kind == "move":
        node = view.node(r.node)
        return {"kind": "move", "uci": node.incoming_move, "san": view.fact("move", r.node).san,
                "fen": view.node(node.parent).fen}  # fmt: skip
    if r.kind == "search_move":
        return {"kind": "move", "uci": r.uci, "san": _san(view, r.node, r.uci),
                "fen": view.node(r.node).fen}  # fmt: skip
    if r.kind == "piece":
        fen = view.node(r.node).fen
        letter = _fen_piece(fen, r.square)
        if letter is None:
            raise ResultError(f"no piece on {r.square} at {r.node}")
        return {"kind": "piece", "square": r.square, "piece": PIECES[letter.lower()],
                "color": "white" if letter.isupper() else "black", "fen": fen}  # fmt: skip
    if r.kind == "square":  # EV-D §3.4: a square shown on the board of `node`
        return {"kind": "square", "square": r.square, "fen": view.node(r.node).fen}
    if r.kind == "line":
        if r.nodes:
            moves = [{"uci": view.node(n).incoming_move, "san": view.fact("move", n).san}
                     for n in r.nodes]  # fmt: skip
        else:  # a zero-ply segment: the first move it rendered from the search
            moves = [{"uci": r.uci, "san": _san(view, r.node, r.uci)}]
        return {"kind": "line", "fen": view.node(r.node).fen, "moves": moves,
                "truncated": r.truncated}  # fmt: skip
    raise ResultError(f"unknown reference kind {r.kind!r}")


def _san(view: TreeView, at: NodeId, uci: str) -> str:
    status = view.fact("status", at)
    move = next((m for m in getattr(status, "legal_moves", ()) if m.uci == uci), None)
    if move is None:
        raise ResultError(f"{uci} is not a legal move at {at}")
    return move.san


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
