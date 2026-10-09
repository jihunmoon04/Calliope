"""F2-D §10.7: the auditor catches field-level mutations of every F2 family.

Each mutation corrupts one field of a family's records (often a legacy defect re-introduced);
the audited mini-corpus must then fail. The unmutated corpus must pass.
"""

import random
from dataclasses import replace

import chess
import pytest
from facts_auditor import audit_line, root_cursor
from test_auditor_fuzz import _game

from calliope.facts import PLAYED, ExtendRequest, FactEngine, InputLine, OpenRequest, RootSpec
from calliope.facts.families import (
    DeltaFamily,
    KingFamily,
    LinesFamily,
    PawnsFamily,
    PiecesFamily,
    SameSideDeltaFamily,
    SquaresFamily,
)
from calliope.facts.families.king import FlightKind
from calliope.facts.families.pawns import ByColor, FileState
from calliope.facts.values import CAPTURED, NOT_OBSERVED, PROMOTED, Absent, NotObserved

ENGINE = FactEngine()
FIXTURES = (
    ("1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1", ("a7b8q", "e8d7", "b8b7", "d7d6")),
    ("4k3/3p4/8/4P3/8/8/8/4K3 b - - 0 1", ("d5", "exd6", "Kf7", "d7")),
    ("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1", ("O-O", "O-O-O", "d4", "d5")),
    ("4k3/4n3/8/8/8/8/4B3/K3R3 w - - 0 1", ("e2f3", "e8d8", "f3b7")),
    ("3r3k/8/8/3P4/8/8/3R4/3RK3 w - - 0 1", ("Kf2", "Kg8", "Rd3")),
    ("4k3/8/8/3p4/3P1P2/4P3/8/4K3 w - - 0 1", ("Kd2", "Kd7", "f5")),
)


def _audit_corpus() -> int:
    audited = 0
    rng = random.Random(20261009)
    lines = [(None, tuple(m.uci() for m in _game(rng))) for _ in range(2)]
    for fen, moves in (*FIXTURES, *lines):
        tree = ENGINE.open(OpenRequest(root=RootSpec(fen=fen)))
        ENGINE.extend(tree, ExtendRequest((InputLine("l", moves),), PLAYED))
        start = chess.Board() if fen is None else chess.Board(fen)
        nodes = tree.view().input_line("l").nodes
        audited += audit_line(tree, nodes, root_cursor(start, start))
    return audited


def _each(record, field, change):
    """Replace `field` (a tuple of records) by `change` applied to each element."""

    return replace(record, **{field: tuple(change(x) for x in getattr(record, field))})


def _unpin(relations):
    return tuple(replace(r, absolutely_pinned=False) for r in relations)


# -- the mutations: (family, record -> mutated record) --------------------------------------------

MUTATIONS = {
    # pieces
    "pieces: pinned attackers lose their flag (E1)": (
        PiecesFamily,
        lambda r: _each(r, "pieces", lambda p: replace(p, attackers=_unpin(p.attackers))),
    ),
    "pieces: pinned flag stored as an int": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: replace(
                p,
                defenders=tuple(
                    replace(d, absolutely_pinned=int(d.absolutely_pinned)) for d in p.defenders
                ),
            ),
        ),
    ),
    "pieces: the king is dropped from defenders (E2)": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: replace(
                p, defenders=tuple(d for d in p.defenders if d.piece_type.value != "king")
            ),
        ),
    ),
    "pieces: lowest attacker types emptied": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: replace(p, lowest_attacker_types=replace(p.lowest_attacker_types, value=())),
        ),
    ),
    "pieces: false instead of NOT_OBSERVED (E7)": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: (
                replace(p, legally_capturable_now=False)
                if isinstance(p.legally_capturable_now, NotObserved)
                else p
            ),
        ),
    ),
    "pieces: attacked_without_defender follows capturability (E6)": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: (
                replace(p, attacked_without_defender=False)
                if p.legally_capturable_now is False
                else p
            ),
        ),
    ),
    "pieces: friendly and enemy targets swapped": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: replace(
                p, attacks=replace(p.attacks, friendly=p.attacks.enemy, enemy=p.attacks.friendly)
            ),
        ),
    ),
    "pieces: pin direction reversed": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: (
                p
                if p.absolutely_pinned is None
                else replace(
                    p,
                    absolutely_pinned=replace(
                        p.absolutely_pinned,
                        direction=(
                            -p.absolutely_pinned.direction[0],
                            -p.absolutely_pinned.direction[1],
                        ),
                    ),
                )
            ),
        ),
    ),
    "pieces: legal destinations of the other side reported empty": (
        PiecesFamily,
        lambda r: _each(
            r,
            "pieces",
            lambda p: (
                replace(p, legal_destinations=())
                if isinstance(p.legal_destinations, NotObserved)
                else p
            ),
        ),
    ),
    # squares
    "squares: white count off by one": (
        SquaresFamily,
        lambda r: _each(
            r,
            "squares",
            lambda s: replace(s, white_count=s.white_count + 1) if s.white_count else s,
        ),
    ),
    "squares: pinned flag dropped": (
        SquaresFamily,
        lambda r: _each(
            r,
            "squares",
            lambda s: replace(
                s,
                white_attackers=_unpin(s.white_attackers),
                black_attackers=_unpin(s.black_attackers),
            ),
        ),
    ),
    # lines
    "lines: x-rays dropped": (
        LinesFamily,
        lambda r: _each(r, "rays", lambda x: replace(x, xray=None)),
    ),
    "lines: batteries counted twice (F2D-C3)": (
        LinesFamily,
        lambda r: replace(
            r,
            batteries=r.batteries
            + tuple(
                replace(b, pieces=(b.pieces[1], b.pieces[0]), line=(-b.line[0], -b.line[1]))
                for b in r.batteries
            ),
        ),
    ),
    "lines: x-ray squares presented as visible": (
        LinesFamily,
        lambda r: _each(
            r,
            "rays",
            lambda x: x if x.xray is None else replace(x, visible=x.visible + x.xray.squares),
        ),
    ),
    "lines: unblocked reported as edge-empty": (
        LinesFamily,
        lambda r: _each(r, "rays", lambda x: replace(x, edge_empty=x.edge_empty or x.unblocked)),
    ),
    # pawns
    "pawns: own_pawn_ahead never set (S1)": (
        PawnsFamily,
        lambda r: _each(r, "pawns", lambda p: replace(p, own_pawn_ahead=False)),
    ),
    "pawns: backward never set": (
        PawnsFamily,
        lambda r: _each(r, "pawns", lambda p: replace(p, backward=False)),
    ),
    "pawns: semi-open colours swapped": (
        PawnsFamily,
        lambda r: _each(
            r,
            "files",
            lambda f: replace(
                f,
                state={
                    FileState.SEMI_OPEN_WHITE: FileState.SEMI_OPEN_BLACK,
                    FileState.SEMI_OPEN_BLACK: FileState.SEMI_OPEN_WHITE,
                }.get(f.state, f.state),
            ),
        ),
    ),
    "pawns: cones of the two colours swapped": (
        PawnsFamily,
        lambda r: replace(
            r,
            outside_enemy_pawn_cones=ByColor(
                r.outside_enemy_pawn_cones.black, r.outside_enemy_pawn_cones.white
            ),
        ),
    ),
    "pawns: chain heads reported as bases": (
        PawnsFamily,
        lambda r: _each(r, "chains", lambda c: replace(c, heads=c.bases)),
    ),
    "pawns: supporters dropped": (
        PawnsFamily,
        lambda r: _each(r, "pawns", lambda p: replace(p, supporters=())),
    ),
    # king
    "king: geometric flight squares dropped": (
        KingFamily,
        lambda r: ByColor(
            *(
                k
                if k.flight_squares.kind is FlightKind.LEGAL
                else replace(k, flight_squares=replace(k.flight_squares, squares=()))
                for k in (r.white, r.black)
            )
        ),
    ),
    "king: the king square left out of the zone": (
        KingFamily,
        lambda r: ByColor(
            *(
                replace(k, zone=tuple(z for z in k.zone if z.square != k.square))
                for k in (r.white, r.black)
            )
        ),
    ),
    "king: shield emptied": (
        KingFamily,
        lambda r: ByColor(*(replace(k, shield=()) for k in (r.white, r.black))),
    ),
    # delta
    "delta: piece flag changes dropped": (DeltaFamily, lambda r: replace(r, piece_flags=())),
    "delta: began pins dropped": (
        DeltaFamily,
        lambda r: replace(r, pins=replace(r.pins, began=())),
    ),
    "delta: promotion reported as capture": (
        DeltaFamily,
        lambda r: _each(
            r, "pawn_flags", lambda c: replace(c, after=CAPTURED) if c.after == PROMOTED else c
        ),
    ),
    "delta: ended square control dropped": (
        DeltaFamily,
        lambda r: replace(r, square_control=replace(r.square_control, ended=())),
    ),
    "delta: pawn support changes dropped": (
        DeltaFamily,
        lambda r: replace(r, pawn_supports=replace(r.pawn_supports, began=(), ended=())),
    ),
    # same_side_delta
    "same_side_delta: captured pieces silently dropped (F2D-C9)": (
        SameSideDeltaFamily,
        lambda r: replace(r, pieces=tuple(m for m in r.pieces if not isinstance(m.after, Absent))),
    ),
    "same_side_delta: legal move counts reversed": (
        SameSideDeltaFamily,
        lambda r: replace(r, legal_move_count=r.legal_move_count[::-1]),
    ),
    "same_side_delta: capturable pieces captured in between dropped": (
        SameSideDeltaFamily,
        lambda r: replace(
            r, capturable_now=tuple(c for c in r.capturable_now if not isinstance(c.after, Absent))
        ),
    ),
    "same_side_delta: flight squares gained and lost swapped": (
        SameSideDeltaFamily,
        lambda r: replace(
            r,
            flight_squares=replace(
                r.flight_squares, gained=r.flight_squares.lost, lost=r.flight_squares.gained
            ),
        ),
    ),
}


def test_unmutated_corpus_passes() -> None:
    assert _audit_corpus() > 100
    assert NOT_OBSERVED == NotObserved()


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_auditor_catches_mutation(name: str, monkeypatch) -> None:
    family, mutate = MUTATIONS[name]
    original = family.compute
    monkeypatch.setattr(family, "compute", lambda self, ctx: mutate(original(self, ctx)))
    with pytest.raises(AssertionError):
        _audit_corpus()
