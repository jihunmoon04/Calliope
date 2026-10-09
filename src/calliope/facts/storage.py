"""Canonical encoding, digest chain, saved trees and the persisted store (design F5-D).

A saved tree holds the inputs of its construction — a normalized header, the normalized request
log with one replay record per request, the search tape and the digest chain — never its
records. Loading replays the requests in an isolated internal engine through the ordinary
`open` / `extend` / `ensure`, and accepts the tree only if every revision's digest matches.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import chess

from calliope.facts import keys, request, tree, values
from calliope.facts.errors import EngineError, EngineOutputError, StoredTreeError
from calliope.facts.families.base import FactFamily
from calliope.facts.search import inputs, port, profile, records
from calliope.facts.search.records import EngineSearch, normalize
from calliope.facts.search.store import EngineResultStore

FACTS_BUILD_VERSION = "1"  # bump for any behaviour change that keeps every family version
ENCODING = "fact_encoding_v1"
TREE_FORMAT = "fact_tree_v1"
STORE_FORMAT = "engine_store_v1"
EXPORT_FORMAT = "fact_export_v1"
KEY_TYPES = (keys.NodeId, keys.PieceId, keys.PositionKey, keys.RootId)  # closed list (§2)


@dataclass(frozen=True, slots=True)
class Attachment:
    """An engine-line attachment (anchor, search) as a record for the digest (F5-D §2)."""

    anchor: keys.NodeId
    search_id: str
    rev: int


@dataclass(frozen=True, slots=True)
class FamilyEntry:
    name: str
    version: str
    scope: tree.Scope
    fact_class: values.FactClass
    requires: tuple[str, ...]
    component_classes: tuple[tuple[str, values.FactClass], ...]


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    facts_build_version: str
    python_chess: str
    families: tuple[FamilyEntry, ...]
    encoding: str
    types: str  # digest of the type registry


@dataclass(frozen=True, slots=True)
class SessionHeader:
    root_id: keys.RootId
    start_fen: str  # as parsed, with a pseudo-legal en passant square kept
    pre_root_moves: tuple[str, ...]
    eager: tuple[str, ...]
    budget: request.SessionBudget
    engine: profile.EngineProfile | None
    identity: profile.EngineIdentity | None
    root_expansion: request.ExpansionSpec
    defaults: request.Defaults


# -- the closed type registry -----------------------------------------------------------------

_CORE_TYPES: tuple[type, ...] = (
    *KEY_TYPES,
    keys.Color,
    keys.PieceType,
    values.FactClass,
    values.NotObserved,
    values.HistoryUnknown,
    values.NotApplicable,
    values.NotComputed,
    values.Unavailable,
    values.AtLeast,
    values.Defined,
    values.AbsentReason,
    values.Absent,
    tree.Scope,
    tree.TerminalKind,
    tree.DrawRule,
    tree.Terminal,
    tree.FrameNode,
    tree.Edge,
    tree.RoleEntry,
    tree.LineEnd,
    tree.LineId,
    tree.EngineLineId,
    tree.LineRecord,
    tree.FactEntry,
    tree.NodeSearch,
    tree.BasisEntry,
    tree.ReplayRecord,
    request.RoleKind,
    request.LineRole,
    request.RootSpec,
    request.InputLine,
    request.SessionBudget,
    request.ExpansionSpec,
    request.Defaults,
    request.OpenRequest,
    request.ExtendRequest,
    request.EnsureRequest,
    inputs.EngineInput,
    profile.EngineProfile,
    profile.EngineOption,
    profile.EngineIdentity,
    port.Bound,
    port.StoppedBy,
    records.SearchKind,
    records.Cp,
    records.Mate,
    records.Wdl,
    records.EngineLineFact,
    records.EngineSearch,
    Attachment,
    FamilyEntry,
    BuildIdentity,
    SessionHeader,
)


def type_registry(families: Iterable[FactFamily]) -> dict[str, type]:
    registry: dict[str, type] = {}
    for kind in (*_CORE_TYPES, *(t for f in families for t in f.record_types)):
        existing = registry.setdefault(kind.__name__, kind)
        if existing is not kind:
            raise TypeError(f"two record types are named {kind.__name__}")
    return registry


def type_table(registry: dict[str, type]) -> list[list[Any]]:
    """Names with their fields (dataclasses) or members (enums), sorted by name."""

    table: list[list[Any]] = []
    for name in sorted(registry):
        kind = registry[name]
        if isinstance(kind, type) and issubclass(kind, enum.Enum):
            table.append([name, "enum", [member.value for member in kind]])
        else:
            table.append([name, "record", [f.name for f in dataclasses.fields(kind)]])
    return table


def types_digest(registry: dict[str, type]) -> str:
    return hashlib.sha256(_dumps(type_table(registry))).hexdigest()


def build_identity(families: Sequence[FactFamily]) -> BuildIdentity:
    return BuildIdentity(
        facts_build_version=FACTS_BUILD_VERSION,
        python_chess=chess.__version__,
        families=tuple(
            FamilyEntry(
                f.name,
                f.version,
                f.scope,
                f.fact_class,
                tuple(f.requires),
                tuple(sorted(getattr(f, "component_classes", {}).items())),
            )
            for f in families
        ),
        encoding=ENCODING,
        types=types_digest(type_registry(families)),
    )


# -- encoding (§2) --------------------------------------------------------------------------------


def encode(value: Any, registry: dict[str, type]) -> Any:
    if value is None or isinstance(value, bool | str) and not isinstance(value, enum.Enum):
        return value
    if isinstance(value, int) and not isinstance(value, enum.Enum):
        return value
    if isinstance(value, enum.Enum):
        _registered(type(value), registry)
        return {"e": type(value).__name__, "v": value.value}
    if isinstance(value, KEY_TYPES):
        return {"k": type(value).__name__, "v": value.value}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        _registered(type(value), registry)
        return {
            "t": type(value).__name__,
            "f": [encode(getattr(value, f.name), registry) for f in dataclasses.fields(value)],
        }
    if isinstance(value, tuple | list):
        return [encode(item, registry) for item in value]
    raise TypeError(f"{type(value).__name__} is not encodable (F5-D §2)")


def _registered(kind: type, registry: dict[str, type]) -> None:
    if registry.get(kind.__name__) is not kind:
        raise TypeError(f"{kind.__name__} is not in the type registry")


def _dumps(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def canonical(value: Any, registry: dict[str, type]) -> bytes:
    return _dumps(encode(value, registry))


class _Decoder:
    """Decodes by position when the saved table equals the current one, else by field name."""

    def __init__(self, registry: dict[str, type], saved_table: list[list[Any]] | None) -> None:
        self.registry = registry
        self.saved = {row[0]: row for row in saved_table or []}
        self.by_name = saved_table is not None

    def __call__(self, value: Any) -> Any:
        if isinstance(value, list):
            return tuple(self(item) for item in value)
        if not isinstance(value, dict):
            return value
        if "e" in value:
            kind = self._kind(value["e"])
            return kind(value["v"])
        if "k" in value:
            return self._kind(value["k"])(value["v"])
        if "t" in value:
            kind = self._kind(value["t"])
            fields = [f.name for f in dataclasses.fields(kind)]
            raw = [self(item) for item in value["f"]]
            if self.by_name and value["t"] in self.saved:
                saved_fields = self.saved[value["t"]][2]
                if saved_fields != fields:
                    return self._by_name(kind, saved_fields, raw)
            if len(raw) != len(fields):
                raise StoredTreeError(f"{value['t']} has {len(raw)} fields, expected {len(fields)}")
            return kind(*raw)
        raise StoredTreeError(f"malformed encoded value {value!r}")

    def _kind(self, name: str) -> type:
        kind = self.registry.get(name)
        if kind is None:
            raise StoredTreeError(f"unknown type {name!r}")
        return kind

    @staticmethod
    def _by_name(kind: type, saved_fields: list[str], raw: list[Any]) -> Any:
        given = dict(zip(saved_fields, raw, strict=True))
        current = {f.name: f for f in dataclasses.fields(kind)}
        extra = set(given) - set(current)
        if extra:
            raise StoredTreeError(f"{kind.__name__} lost fields {sorted(extra)}")
        kwargs = {}
        for name, spec in current.items():
            if name in given:
                kwargs[name] = given[name]
            elif (
                spec.default is dataclasses.MISSING and spec.default_factory is dataclasses.MISSING
            ):
                raise StoredTreeError(f"{kind.__name__} gained {name!r} without a default")
        return kind(**kwargs)


# -- the digest chain (§3) ----------------------------------------------------------------------


def _role_key(role: tree.RoleEntry) -> tuple:
    if role.kind is request.RoleKind.ENGINE:
        assert role.anchor is not None and role.search_id is not None
        engine = (role.anchor.value, role.search_id, role.rank, role.index)
        return (role.target.value, role.on_edge, len(request.RoleKind), engine)
    expansion = role.expansion
    exp = (
        (0,)
        if expansion is None
        else (
            1,
            expansion.survey,
            expansion.comparison,
            expansion.attach_lines,
        )
    )
    order = list(request.RoleKind).index(role.kind)
    return (
        role.target.value,
        role.on_edge,
        order,
        (role.by, role.label, role.index, role.rev, exp),
    )


def _line_key(line: tree.LineRecord) -> tuple:
    line_id = line.line_id
    if isinstance(line_id, tree.EngineLineId):
        return (1, line_id.anchor.value, line_id.search_id, line_id.rank)
    order = list(request.RoleKind).index(line_id.kind)
    return (0, order, line_id.by, line_id.label, line_id.segment)


def revision_sections(fact_tree: tree.FactTree, rev: int) -> list[Any]:
    """The ten sections of revision `rev` in canonical order (F5-D §2–§3)."""

    pending, delta = fact_tree._revisions[rev]
    family_index = {name: i for i, name in enumerate(fact_tree._families)}
    attachments = [Attachment(anchor, sid, rev) for anchor, sid in pending.attached]
    decisions = (
        tuple(sorted(delta.skipped)),
        tuple(sorted(delta.deadline_cuts)),
    )
    return [
        sorted(pending.nodes, key=lambda n: n.node_id.value),
        sorted(pending.edges, key=lambda e: e.child.value),
        sorted(pending.roles, key=_role_key),
        sorted(pending.lines, key=_line_key),
        sorted(pending.facts, key=lambda f: (family_index[f.family], str(f.target))),
        [pending.searches[sid] for sid in sorted(pending.searches)],
        sorted(
            pending.node_searches, key=lambda b: (b.node.value, b.rev, b.kind.value, b.search_id)
        ),
        sorted(pending.basis, key=lambda b: (b.node.value, b.rev)),
        sorted(attachments, key=lambda a: (a.anchor.value, a.search_id)),
        decisions,
    ]


def tree_registry(fact_tree: tree.FactTree) -> dict[str, type]:
    return type_registry(fact_tree._session.families)


def session_header(fact_tree: tree.FactTree) -> SessionHeader:
    session = fact_tree._session
    opening = fact_tree._log[0][0]
    return SessionHeader(
        root_id=fact_tree.root_id,
        start_fen=session.start_board.fen(en_passant="fen"),
        pre_root_moves=session.pre_root_moves,
        eager=tuple(f.name for f in session.eager),
        budget=session.budget,
        engine=session.engine,
        identity=session.identity,
        root_expansion=opening.root_expansion,
        defaults=session.defaults,
    )


def digest_bytes(fact_tree: tree.FactTree, rev: int) -> bytes:
    """digest(rev) as raw bytes; cached per revision (lazy, F5-D §3)."""

    cache = fact_tree._digests
    if rev in cache:
        return cache[rev]
    registry = tree_registry(fact_tree)
    if rev == 0:
        value = hashlib.sha256(canonical(session_header(fact_tree), registry)).digest()
    else:
        previous = digest_bytes(fact_tree, rev - 1)
        body = canonical(revision_sections(fact_tree, rev), registry)
        value = hashlib.sha256(previous + body).digest()
    cache[rev] = value
    return value


def digest(fact_tree: tree.FactTree, rev: int | None = None) -> str:
    return digest_bytes(fact_tree, fact_tree.rev if rev is None else rev).hex()


def reproducible(fact_tree: tree.FactTree, rev: int | None = None) -> bool:
    """F5-D §3: regular searches, no deadline or budget decisions, searches within budget."""

    rev = fact_tree.rev if rev is None else rev
    searches = 0
    for r in range(1, rev + 1):
        pending, delta = fact_tree._revisions[r]
        if delta.deadline_cuts or any(
            reason in ("BUDGET", "DEADLINE") for _, _, reason in delta.skipped
        ):
            return False
        if any(not s.regular for s in pending.searches.values()):
            return False
        searches += len(pending.searches)
    limit = fact_tree._session.budget.max_searches
    return limit is None or searches <= limit


# -- save, load, rebuild, export (§5–§7) ----------------------------------------------------------


def save(fact_tree: tree.FactTree, rev: int | None = None) -> bytes:
    rev = fact_tree.rev if rev is None else rev
    families = fact_tree._session.families
    registry = type_registry(families)
    log = fact_tree._log[:rev]
    tape = sorted(
        (s for r in range(1, rev + 1) for s in fact_tree._revisions[r][0].searches.values()),
        key=lambda s: s.search_id,
    )
    document = {
        "format": TREE_FORMAT,
        "build": encode(build_identity(families), registry),
        "types": type_table(registry),
        "header": encode(session_header(fact_tree), registry),
        "requests": [encode(req, registry) for req, _ in log],
        "replay": [encode(record, registry) for _, record in log],
        "tape": [encode(search, registry) for search in tape],
        "digests": [digest(fact_tree, r) for r in range(1, rev + 1)],
    }
    return _dumps(document)


def _parse(data: bytes, expected_format: str) -> dict:
    try:
        document = json.loads(data)
    except (ValueError, UnicodeDecodeError) as error:
        raise StoredTreeError(f"not a saved document: {error}") from None
    if not isinstance(document, dict) or document.get("format") != expected_format:
        raise StoredTreeError(f"format is not {expected_format}")
    return document


class ReplayEngine:
    """The port of a replay: its identity is the stored one, and it never searches (F5-D §6.1)."""

    def __init__(self, identity: profile.EngineIdentity) -> None:
        self.identity = identity

    def search(self, request_: port.SearchRequest) -> port.RawSearch:
        raise StoredTreeError("search missing from the tape")

    def close(self) -> None:
        pass


def raw_of(search: EngineSearch) -> port.RawSearch:
    """Invert normalization: the raw engine output a record was made from (F5-D §6.1 step 3)."""

    board = inputs.window_end(search.input)
    white = board.turn == chess.WHITE
    lines = []
    for line in search.lines:
        if isinstance(line.score, records.Cp):
            score = ("cp", line.score.value if white else -line.score.value)
        else:
            mover = keys.Color.of(board.turn)
            score = ("mate", line.score.moves if line.score.winner is mover else -line.score.moves)
        bound = line.bound
        if not white and bound is not port.Bound.EXACT:
            bound = port.Bound.UPPER if bound is port.Bound.LOWER else port.Bound.LOWER
        wdl = None
        if isinstance(line.wdl, records.Wdl):
            w = line.wdl
            wdl = (
                (w.white_win, w.draw, w.black_win) if white else (w.black_win, w.draw, w.white_win)
            )
        lines.append(
            port.RawLine(
                line.rank,
                line.depth,
                line.seldepth,
                score,
                bound,
                wdl,
                line.nodes,
                line.tbhits,
                line.pv,
            )
        )
    return port.RawSearch(tuple(lines), search.stopped_by, 0)


def ingest_search(search: EngineSearch) -> None:
    """Re-normalize a stored search and require the same record (F5-D §6.1 step 3, §8)."""

    if not isinstance(search, EngineSearch):
        raise StoredTreeError("a tape entry is not an engine search")
    request_ = port.SearchRequest(search.input, search.profile, search.root_moves, search.multipv)
    try:
        again = normalize(raw_of(search), request_, search.kind, search.identity)
    except (EngineOutputError, EngineError, ValueError, KeyError) as error:
        raise StoredTreeError(f"tape search {search.search_id} fails ingestion: {error}") from None
    if again != search:
        raise StoredTreeError(f"tape search {search.search_id} does not re-normalize to itself")


def _question(search: EngineSearch) -> str:
    request_ = port.SearchRequest(search.input, search.profile, search.root_moves, search.multipv)
    return records.request_key(request_, search.kind, search.identity)


def load(fact_engine, data: bytes, *, rev: int | None = None, rebuild: bool = False):
    """F5-D §6 (load) and §7 (rebuild). Refusals raise `StoredTreeError` and write nothing."""

    from calliope.facts.engine import FactEngine

    document = _parse(data, TREE_FORMAT)
    families = tuple(fact_engine._registry.values())
    registry = type_registry(families)
    current = build_identity(families)
    if not rebuild and document.get("types") != type_table(registry):
        raise StoredTreeError("type registry differs from this build")
    decode = _Decoder(registry, document.get("types") if rebuild else None)
    try:
        build = decode(document["build"])
        header = decode(document["header"])
        requests = [decode(r) for r in document["requests"]]
        replay = [decode(r) for r in document["replay"]]
        tape = [decode(s) for s in document["tape"]]
        digests = list(document["digests"])
    except (KeyError, TypeError, ValueError) as error:
        raise StoredTreeError(f"malformed saved tree: {error}") from None
    if not rebuild and build != current:
        raise StoredTreeError("build identity differs from this build (rebuild instead)")
    if not requests or len(requests) != len(replay) or len(requests) != len(digests):
        raise StoredTreeError("request log, replay records and digests disagree in length")
    if not isinstance(requests[0], request.OpenRequest):
        raise StoredTreeError("the first request is not an open")
    target = len(requests) if rev is None else rev
    if not 1 <= target <= len(requests):
        raise StoredTreeError(f"revision {target} is not saved")
    _check_engine_calls(replay, tape, header)
    _check_header(header, requests[0])

    # tape ingestion by re-normalization
    valid: list[EngineSearch] = []
    questions: set[str] = set()
    for search in tape:
        try:
            ingest_search(search)
        except StoredTreeError:
            if rebuild:
                continue  # changed by a normalization fix: dropped, searched again if needed
            raise
        if (
            header.identity is None
            or search.identity != header.identity
            or search.profile != header.engine
        ):
            raise StoredTreeError(
                f"tape search {search.search_id} is from another engine or profile"
            )
        if not search.regular:
            question = _question(search)
            if question in questions:
                raise StoredTreeError("two irregular searches answer one question")
            questions.add(question)
        valid.append(search)

    # isolated replay in an internal engine (§6.1 step 4)
    private = EngineResultStore()
    for search in valid:
        if search.regular:
            private.put(search)
    if rebuild and fact_engine._port is not None:
        if header.identity is not None and fact_engine._port.identity != header.identity:
            raise StoredTreeError("a rebuild needs the stored engine identity")
        engine_port = fact_engine._port
    else:
        engine_port = None if header.identity is None else ReplayEngine(header.identity)
    internal = FactEngine(families, engine=engine_port, store=private)
    internal._irregular_seed = {_question(s): s for s in valid if not s.regular}
    internal._strict = not rebuild
    rebuilt = None
    try:
        for index in range(target):
            req, record = requests[index], replay[index]
            internal._next_record = record
            if index == 0:
                rebuilt = internal.open(req)
            elif isinstance(req, request.ExtendRequest):
                internal.extend(rebuilt, req)
            elif isinstance(req, request.EnsureRequest):
                internal.ensure(rebuilt, req)
            else:
                raise StoredTreeError(f"request {index + 1} is not extend or ensure")
            if rebuilt.rev != index + 1:
                raise StoredTreeError(f"request {index + 1} did not commit a revision")
            if not rebuild and digest(rebuilt, index + 1) != digests[index]:
                raise StoredTreeError(f"digest of revision {index + 1} differs")
    except StoredTreeError:
        raise
    except Exception as error:  # noqa: BLE001 — any construction failure refuses the load
        raise StoredTreeError(f"replay failed: {type(error).__name__}: {error}") from None
    finally:
        internal._next_record = None
    assert rebuilt is not None

    in_tree = {
        sid: search
        for r in range(1, rebuilt.rev + 1)
        for sid, search in rebuilt._revisions[r][0].searches.items()
    }
    if not rebuild:  # the precise bound: no more new engine calls than new searches (§6.1)
        previous = 0
        for r in range(1, rebuilt.rev + 1):
            calls = replay[r - 1].engine_calls
            if calls - previous > len(rebuilt._revisions[r][0].searches):
                raise StoredTreeError(f"recorded engine calls of revision {r} are out of bounds")
            previous = calls
    if not rebuild:
        tape_ids = {s.search_id for s in valid}
        if target == len(requests) and set(in_tree) != tape_ids:
            raise StoredTreeError("the tape and the tree's searches differ")
        if not set(in_tree) <= tape_ids:
            raise StoredTreeError("a search of the tree is missing from the tape")
    _rebind(fact_engine, rebuilt, in_tree, replay[target - 1], header, rebuild)
    return rebuilt


def _check_engine_calls(replay, tape, header) -> None:
    """F5-D §6.1 step 2: bounds on the recorded engine calls (not digested)."""

    limit = header.budget.max_searches
    previous = 0
    for record in replay:
        if not isinstance(record, tree.ReplayRecord):
            raise StoredTreeError("a replay record is malformed")
        if record.engine_calls < previous or record.engine_calls > previous + len(tape):
            raise StoredTreeError("recorded engine calls are out of bounds")
        if limit is not None and record.engine_calls > limit:
            raise StoredTreeError("recorded engine calls exceed max_searches")
        previous = record.engine_calls


def _check_header(header: SessionHeader, opening: request.OpenRequest) -> None:
    if not isinstance(header, SessionHeader):
        raise StoredTreeError("the header is malformed")
    if (
        opening.root.fen != header.start_fen
        or tuple(opening.root.moves) != header.pre_root_moves
        or tuple(opening.families or ()) != header.eager
        or opening.budget != header.budget
        or opening.engine != header.engine
        or opening.root_expansion != header.root_expansion
        or opening.defaults != header.defaults
    ):
        raise StoredTreeError("the first request disagrees with the header")


def _rebind(fact_engine, fact_tree, in_tree, record, header, rebuild) -> None:
    """F5-D §6.1 step 7: only after every check passed."""

    searcher = fact_tree._session.searcher
    if searcher is None:
        return
    if fact_engine._port is not None:
        if fact_engine._port.identity != header.identity:
            raise StoredTreeError("the loading engine's port is another engine")
        searcher.port = fact_engine._port
    store = fact_engine._store
    regular = [s for s in in_tree.values() if s.regular]
    for search in regular:
        held = store.get(search.search_id)
        if held is not None and held != search:
            raise StoredTreeError(f"the loading store holds other content for {search.search_id}")
    for search in regular:
        store.put(search)
    searcher.store = store
    if not rebuild:
        searcher.engine_calls = searcher._committed_calls = record.engine_calls


def export(fact_tree: tree.FactTree, rev: int | None = None) -> bytes:
    """The records in canonical encoding, with the build identity and type table (F5-D §5.2)."""

    rev = fact_tree.rev if rev is None else rev
    families = fact_tree._session.families
    registry = type_registry(families)
    return _dumps(
        {
            "format": EXPORT_FORMAT,
            "build": encode(build_identity(families), registry),
            "types": type_table(registry),
            "header": encode(session_header(fact_tree), registry),
            "revisions": [
                encode(revision_sections(fact_tree, r), registry) for r in range(1, rev + 1)
            ],
            "digests": [digest(fact_tree, r) for r in range(1, rev + 1)],
        }
    )


# -- the persisted store (§8) ---------------------------------------------------------------------


def _store_build(families: Sequence[FactFamily]) -> dict:
    registry = type_registry(families)
    return {
        "facts_build_version": FACTS_BUILD_VERSION,
        "python_chess": chess.__version__,
        "encoding": ENCODING,
        "types": types_digest(registry),
    }


def save_store(store: EngineResultStore, families: Sequence[FactFamily]) -> bytes:
    registry = type_registry(families)
    with store._lock:
        searches = [store._searches[sid] for sid in sorted(store._searches)]
    body = [encode(search, registry) for search in searches]
    return _dumps(
        {
            "format": STORE_FORMAT,
            "build": _store_build(families),
            "body": body,
            "sha256": hashlib.sha256(_dumps(body)).hexdigest(),
        }
    )


def load_store(data: bytes, families: Sequence[FactFamily]) -> EngineResultStore:
    document = _parse(data, STORE_FORMAT)
    if document.get("build") != _store_build(families):
        raise StoredTreeError("the store was written by another build")
    body = document.get("body")
    if not isinstance(body, list) or hashlib.sha256(_dumps(body)).hexdigest() != document.get(
        "sha256"
    ):
        raise StoredTreeError("the store body digest does not match")
    decode = _Decoder(type_registry(families), None)
    store = EngineResultStore()
    try:
        searches = [decode(entry) for entry in body]
    except (KeyError, TypeError, ValueError) as error:
        raise StoredTreeError(f"malformed store entry: {error}") from None
    for search in searches:
        ingest_search(search)
        if not search.regular:
            raise StoredTreeError(f"store entry {search.search_id} is irregular")
    for search in searches:
        store.put(search)
    return store
