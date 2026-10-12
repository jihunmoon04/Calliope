"""`claim_graph_v1`: storage, load and replay of an analysis (R0-D §14 as amended by R4-D).

An analysis bundle is two documents: the fact tree (`fact_tree_v1`) at the analysis's final
revision and the claim graph (`claim_graph_v1`). Load replays the unchanged reasoner against the
loaded tree through a `ReplayTree` (a revision cursor) and a `ReplayFactEngine` (requests checked
against the tree's log, never executed); the re-derived document must equal the stored bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from calliope.facts import (
    BudgetExceededError,
    CrossSearchError,
    EngineError,
    EngineOutputError,
    EngineUnsupportedError,
    EnsureRequest,
    FactEngine,
    FactEngineError,
    FactTree,
    decode,
    encode,
    save_tree,
    type_table,
)
from calliope.reasoning.errors import StoredGraphError
from calliope.reasoning.grading import SHIPPED, GradingBuild, resolve
from calliope.reasoning.render import RenderedExplanation, plan_analysis, render
from calliope.reasoning.runner import Analysis, Reasoner, RequestOutcome

GRAPH_FORMAT = "claim_graph_v1"
# the fact-engine refusals a round can record (`REFUSED(<type>)`), re-raised by name on replay
REFUSALS = {
    kind.__name__: kind
    for kind in (FactEngineError, BudgetExceededError, CrossSearchError, EngineError,
                 EngineOutputError, EngineUnsupportedError)
}  # fmt: skip
FIELDS = (
    "format", "build", "types", "request", "grading", "tree", "limits_reached", "rounds",
    "judgements", "observations", "claims", "relations", "labels", "plan", "rendered", "digest",
)  # fmt: skip


def _registry() -> dict[str, type]:
    from calliope.reasoning.encoding import reasoning_registry

    return reasoning_registry()


def _dumps(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _document(analysis: Analysis, rendered: RenderedExplanation) -> bytes:
    """The canonical bytes of `claim_graph_v1` (R4-D §2.2), fields in `FIELDS` order."""

    if analysis.build is None:
        raise StoredGraphError("the analysis records no reasoner build (R4-D §2.1)")
    registry = _registry()

    def enc(value: Any) -> Any:
        return encode(value, registry)

    zero = analysis.round_zero
    view = analysis.tree.view(analysis.rev)
    doc: dict[str, Any] = {
        "format": GRAPH_FORMAT,
        "build": enc(analysis.build),
        "types": type_table(registry),
        "request": enc(zero.request),
        "grading": enc(zero.grading),
        "tree": {"digest": view.digest(), "rev": analysis.rev, "reproducible": view.reproducible()},
        "limits_reached": enc(analysis.limits_reached),
        "rounds": [
            {
                "index": r.index,
                "rev": r.rev,
                "admitted": enc(r.admitted),
                "proposals": [],
                "requests": enc(r.requests),
            }
            for r in analysis.rounds
        ],
        "judgements": enc(zero.judgements),
        "observations": enc(zero.observations),
        "claims": enc(analysis.claims),
        "relations": enc(analysis.relations),
        "labels": enc(analysis.labels),
        "plan": enc(plan_analysis(analysis)),
        "rendered": enc(rendered),
    }
    doc["digest"] = hashlib.sha256(_dumps(doc)).hexdigest()
    return _dumps(doc)


def save(analysis: Analysis, rendered: RenderedExplanation) -> tuple[bytes, bytes]:
    """`(fact_tree_v1, claim_graph_v1)` bytes of an analysis and its rendering (R4-D §2.3)."""

    again = render(plan_analysis(analysis), analysis)
    if again != rendered:
        raise StoredGraphError("the rendering is not this analysis's plan_analysis rendering")
    return save_tree(analysis.tree, analysis.rev), _document(analysis, rendered)


# -- replay (R4-D §3.2) ---------------------------------------------------------------------------


class ReplayTree:
    """The loaded tree behind a revision cursor: `rev` and `view()` are the replay position, and
    no later revision is visible (R4-D review B1). The reasoner reads its tree only this way."""

    def __init__(self, tree: FactTree) -> None:
        self._tree = tree
        self.cursor = 0

    @property
    def rev(self) -> int:
        return self.cursor

    def view(self, rev: int | None = None):
        at = self.cursor if rev is None else rev
        if not 1 <= at <= self.cursor:
            raise StoredGraphError(f"replay: revision {at} is beyond the cursor {self.cursor}")
        return self._tree.view(at)


class ReplayFactEngine:
    """A stand-in for `FactEngine`: requests are normalized and checked against the loaded tree's
    log, never executed. No engine, no clock (R4-D §3.2)."""

    def __init__(self, fact_engine: FactEngine, tree: FactTree, refusals: list) -> None:
        self._engine = fact_engine
        self._tree = tree
        self._final = tree.view()
        self.replay = ReplayTree(tree)
        self._refusals = list(refusals)

    @property
    def families(self):
        return self._engine.families

    def open(self, request) -> ReplayTree:
        if self._engine.normalize_open(request) != self._final.request(1):
            raise StoredGraphError("replay: the open differs from the logged one")
        self.replay.cursor = 1
        return self.replay

    def extend(self, tree, request) -> int:
        return self._next(request)

    def ensure(self, tree, request) -> int:
        return self._next(request)

    def _next(self, request) -> int:
        view = self.replay.view()
        normal = self._engine.normalize(view, request)
        following = self.replay.cursor + 1
        if following <= self._final.rev and self._final.request(following) == normal:
            self.replay.cursor = following
            return following
        if isinstance(request, EnsureRequest) and all(
            view.fact_entry(family, node) is not None
            for node in request.nodes
            for family in request.families
        ):
            return self.replay.cursor  # NO_OP
        if self._refusals and self._refusals[0].request == request:
            outcome = self._refusals.pop(0)
            name = outcome.outcome[len("REFUSED(") : -1]
            kind = REFUSALS.get(name)
            if kind is None:
                raise StoredGraphError(f"replay: unknown refusal type {name!r}")
            raise kind(f"recorded refusal ({name}), replayed")
        raise StoredGraphError("replay: a request matches no recorded outcome")

    def finish(self) -> None:
        if self.replay.cursor != self._final.rev:
            raise StoredGraphError(
                f"replay ended at revision {self.replay.cursor}, not {self._final.rev}"
            )
        if self._refusals:
            raise StoredGraphError("replay left recorded refusals unused")


# -- load (R4-D §3.1) -----------------------------------------------------------------------------


def load(
    fact_engine: FactEngine,
    tree_bytes: bytes,
    graph_bytes: bytes,
    *,
    templates=None,
    grading_build: GradingBuild = SHIPPED,
) -> tuple[Analysis, RenderedExplanation]:
    """A stored analysis, replayed and verified; any difference raises `StoredGraphError`."""

    try:
        doc = json.loads(graph_bytes)
    except (ValueError, UnicodeDecodeError) as error:
        raise StoredGraphError(f"not a claim graph: {error}") from None
    if not isinstance(doc, dict) or doc.get("format") != GRAPH_FORMAT:
        raise StoredGraphError("not a claim_graph_v1 document")
    if list(doc) != list(FIELDS):
        raise StoredGraphError("the document's fields differ from claim_graph_v1")
    registry = _registry()
    if doc["types"] != type_table(registry):
        raise StoredGraphError("the type table differs from this build")
    try:
        stored_build = decode(doc["build"], registry)
        request = decode(doc["request"], registry)
        grading = decode(doc["grading"], registry)
        rounds = [decode(r["requests"], registry) for r in doc["rounds"]]
    except (FactEngineError, KeyError, TypeError, ValueError) as error:  # refused, not a crash
        raise StoredGraphError(f"malformed claim graph: {error}") from None
    if stored_build != Reasoner(fact_engine, templates, grading_build).build():
        raise StoredGraphError("the build differs from this reasoner's build (re-analyse instead)")

    tree = fact_engine.load(tree_bytes)
    view = tree.view()
    if (view.digest(), tree.rev) != (doc["tree"]["digest"], doc["tree"]["rev"]):
        raise StoredGraphError("the fact tree is not the one this graph names")
    if resolve(request.grading, grading_build) != grading:
        raise StoredGraphError("the grading resolves differently under this build")

    refusals = [o for outcomes in rounds for o in outcomes
                if isinstance(o, RequestOutcome) and o.outcome.startswith("REFUSED(")]  # fmt: skip
    replayer = ReplayFactEngine(fact_engine, tree, refusals)
    analysis = Reasoner(replayer, templates, grading_build).analyse(request)
    replayer.finish()
    zero = replace(analysis.round_zero, tree=tree)  # no replay object escapes (review note)
    analysis = replace(analysis, round_zero=zero)
    rendered = render(plan_analysis(analysis), analysis)

    again = _document(analysis, rendered)
    if again != graph_bytes:
        fresh = json.loads(again)
        field = next((f for f in FIELDS if fresh.get(f) != doc.get(f)), "digest")
        raise StoredGraphError(f"the re-derived claim graph differs at {field!r}")
    return analysis, rendered


__all__ = ["GRAPH_FORMAT", "ReplayFactEngine", "ReplayTree", "load", "save"]
