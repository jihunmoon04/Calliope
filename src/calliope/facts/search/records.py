"""Search records, normalization, regularity and `SearchId` (F4-D §5)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import chess

from calliope.facts.board import MoveRejectedError, canonical_move
from calliope.facts.errors import EngineOutputError
from calliope.facts.keys import Color, digest
from calliope.facts.search.inputs import EngineInput, window_end
from calliope.facts.search.port import Bound, RawLine, RawSearch, SearchRequest, StoppedBy
from calliope.facts.search.profile import (
    EngineIdentity,
    EngineProfile,
    PinnedOptions,
    search_options,
    start_options,
)
from calliope.facts.values import UNAVAILABLE, Unavailable


class SearchKind(StrEnum):
    SURVEY = "survey"
    COMPARISON = "comparison"
    ANALYSIS = "analysis"  # an ANALYSIS request's restricted probe; never a basis


class ReuseSource(StrEnum):
    STORE = "store"
    SESSION = "session"


@dataclass(frozen=True, slots=True)
class Cp:
    """Centipawns from White's view."""

    value: int


@dataclass(frozen=True, slots=True)
class Mate:
    winner: Color
    moves: int  # >= 1, as the engine reports


Score = Cp | Mate


@dataclass(frozen=True, slots=True)
class Wdl:
    """Permille from White's view."""

    white_win: int
    draw: int
    black_win: int


@dataclass(frozen=True, slots=True)
class EngineLineFact:
    rank: int
    move: str
    score: Score
    bound: Bound
    wdl: Wdl | Unavailable
    depth: int
    seldepth: int
    nodes: int
    tbhits: int
    pv: tuple[str, ...]  # complete, canonical UCI


@dataclass(frozen=True, slots=True)
class EngineSearch:
    search_id: str
    input: EngineInput
    kind: SearchKind
    root_moves: tuple[str, ...] | None
    multipv: int
    profile: EngineProfile
    identity: EngineIdentity
    pinned_options: PinnedOptions  # start-time group, then the per-search group
    stopped_by: StoppedBy
    regular: bool
    lines: tuple[EngineLineFact, ...]  # rank order


@dataclass(frozen=True, slots=True)
class SearchRuntime:
    """Metadata, not a fact: outside comparisons and the digest (F4-D §5.1)."""

    rev: int
    search_id: str
    elapsed_ms: int
    reused: ReuseSource | None


def pinned(identity: EngineIdentity, profile: EngineProfile, multipv: int) -> PinnedOptions:
    return start_options(identity) + search_options(identity, profile, multipv)


def request_key(request: SearchRequest, kind: SearchKind, identity: EngineIdentity) -> str:
    """The `SearchId` of a regular answer to `request` (length-prefixed preimage, F4-D §5.4)."""

    return "s_" + digest(*_preimage(request, kind, identity))


def _preimage(request: SearchRequest, kind: SearchKind, identity: EngineIdentity) -> list[str]:
    roots = request.root_moves
    options = pinned(identity, request.profile, request.multipv)
    profile = request.profile.fingerprint()
    ident = identity.fingerprint()
    return [
        "search",
        request.input.fen,
        str(len(request.input.moves)),
        *request.input.moves,
        kind.value,
        str(-1 if roots is None else len(roots)),
        *(roots or ()),
        str(request.multipv),
        str(len(profile)),
        *profile,
        str(len(ident)),
        *ident,
        str(len(options)),
        *(f"{name}={value}" for name, value in options),
    ]


def normalize(
    raw: RawSearch, request: SearchRequest, kind: SearchKind, identity: EngineIdentity
) -> EngineSearch:
    """Every rule of F4-D §5.2–§5.4; any violation refuses with `EngineOutputError`."""

    board = window_end(request.input)
    legal = {m.uci() for m in board.legal_moves}
    restriction = legal if request.root_moves is None else set(request.root_moves)
    if not restriction:
        raise EngineOutputError("a position without legal moves is never searched")
    k = min(request.multipv, len(restriction))
    ranks = [line.multipv for line in raw.lines]
    expected = list(range(1, len(ranks) + 1))
    if ranks != expected or not ranks:
        raise EngineOutputError(f"engine ranks {ranks} are not 1..j in order")
    if raw.stopped_by is StoppedBy.DEPTH and len(ranks) != k:
        raise EngineOutputError(f"a depth-stopped search must give {k} ranks, got {len(ranks)}")
    if len(ranks) > k:
        raise EngineOutputError(f"{len(ranks)} ranks exceed k={k}")
    wdl_set = identity.offers("UCI_ShowWDL")
    lines: list[EngineLineFact] = []
    for raw_line in raw.lines:
        pv = _pv(board, raw_line)
        if pv[0] not in restriction:
            raise EngineOutputError(
                f"rank {raw_line.multipv} move {pv[0]} is outside the restriction"
            )
        lines.append(
            EngineLineFact(
                rank=raw_line.multipv,
                move=pv[0],
                score=_score(raw_line, board.turn),
                bound=raw_line.bound,
                wdl=_wdl(raw_line, board.turn, wdl_set),
                depth=raw_line.depth,
                seldepth=raw_line.seldepth,
                nodes=raw_line.nodes,
                tbhits=raw_line.tbhits,
                pv=pv,
            )
        )
    moves = [line.move for line in lines]
    if len(set(moves)) != len(moves):
        raise EngineOutputError(f"duplicate first moves across ranks: {moves}")
    regular = raw.stopped_by is StoppedBy.DEPTH and all(
        line.depth == request.profile.depth and line.bound is Bound.EXACT for line in lines
    )
    preimage = _preimage(request, kind, identity)
    if not regular:
        preimage += ["lines", digest(*(_line_text(line) for line in lines))]
    return EngineSearch(
        search_id="s_" + digest(*preimage),
        input=request.input,
        kind=kind,
        root_moves=request.root_moves,
        multipv=request.multipv,
        profile=request.profile,
        identity=identity,
        pinned_options=pinned(identity, request.profile, request.multipv),
        stopped_by=raw.stopped_by,
        regular=regular,
        lines=tuple(lines),
    )


def _pv(board: chess.Board, raw_line: RawLine) -> tuple[str, ...]:
    if not raw_line.pv:
        raise EngineOutputError(f"rank {raw_line.multipv} has an empty PV")
    walker = board.copy(stack=False)
    out: list[str] = []
    for token in raw_line.pv:
        try:
            structural = chess.Move.from_uci(token)  # structural UCI only: no SAN fallback
        except ValueError:
            raise EngineOutputError(f"PV token {token!r} is not UCI") from None
        if not structural:
            raise EngineOutputError("PV contains a null move")
        try:
            move = canonical_move(walker, token)
        except MoveRejectedError:
            raise EngineOutputError(f"PV move {token!r} is illegal at ply {len(out) + 1}") from None
        out.append(move.uci())
        walker.push(move)
    return tuple(out)


def _score(raw_line: RawLine, turn: chess.Color) -> Score:
    kind, value = raw_line.score
    mover = Color.of(turn)
    if kind == "cp":
        return Cp(value if turn == chess.WHITE else -value)
    if kind != "mate":
        raise EngineOutputError(f"unknown score kind {kind!r}")
    if value == 0:
        raise EngineOutputError("mate 0: a mated position is never searched")
    return Mate(mover if value > 0 else mover.opposite, abs(value))


def _wdl(raw_line: RawLine, turn: chess.Color, wdl_set: bool) -> Wdl | Unavailable:
    if not wdl_set:
        return UNAVAILABLE
    if raw_line.wdl is None:
        raise EngineOutputError(f"rank {raw_line.multipv} has no wdl although UCI_ShowWDL is set")
    win, draw, loss = raw_line.wdl
    if min(win, draw, loss) < 0:
        raise EngineOutputError("negative wdl")
    return Wdl(win, draw, loss) if turn == chess.WHITE else Wdl(loss, draw, win)


def _line_text(line: EngineLineFact) -> str:
    score = (
        f"cp:{line.score.value}"
        if isinstance(line.score, Cp)
        else f"mate:{line.score.winner.value}:{line.score.moves}"
    )
    wdl = (
        "unavailable"
        if isinstance(line.wdl, Unavailable)
        else f"{line.wdl.white_win}/{line.wdl.draw}/{line.wdl.black_win}"
    )
    return "|".join(
        (
            str(line.rank),
            line.move,
            score,
            line.bound.value,
            wdl,
            str(line.depth),
            str(line.seldepth),
            str(line.nodes),
            str(line.tbhits),
            " ".join(line.pv),
        )
    )
