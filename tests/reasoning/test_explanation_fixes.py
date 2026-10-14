"""EF-D: trades, the attribution of a line's material, `exposed_v1` in check, check answers
(EF-D §2–§5, §9; EF1 A1). Positions of the 2026-10-14 game (`g1014`) are taken from its result
document; their lines are the stored engine lines."""

from __future__ import annotations

from types import SimpleNamespace

from story import claim, finding, line, run

from calliope.facts import (
    Capture,
    Color,
    Defined,
    ExchangeFacts,
    NodeId,
    NotApplicable,
    PieceExchange,
    PieceId,
    PieceType,
    StatusFacts,
)
from calliope.facts.families.status import LegalMove  # a test fixture only
from calliope.reasoning import explain
from calliope.reasoning.findings import (
    CheckAnswerFinding,
    CheckAnswerKind,
    ConcessionFinding,
    MaterialFinding,
)
from calliope.reasoning.lines import (
    Attribution,
    _classify,
    attribution,
    reduced_balances,
    trade_pairs,
)
from calliope.reasoning.needs import LineNeed
from calliope.reasoning.verification import ATTRIBUTED, CausalCheck, VerdictStatus

S = VerdictStatus.SUPPORTED
WIN, EVEN, LOST = (700, 250, 50), (200, 600, 200), (50, 250, 700)


def _attributed(c) -> bool | None:
    check = next(
        (f for f in c.verdict.findings if isinstance(f, CausalCheck) and f.kind == ATTRIBUTED),
        None,
    )
    return None if check is None else check.passed


# -- trade_pairs_v1 (EF-D §2, test 1) ---------------------------------------------------------------


def _fake(captures, balances):
    """A line from (victim, square, mover piece, destination, promotes) per ply."""

    plies, moves = [], []
    for victim, square, piece, to, promotes in captures:
        capture = Capture(PieceId(victim), PieceType.PAWN, square, False) if victim else None
        plies.append(SimpleNamespace(capture=capture, promotion=object() if promotes else None))
        moves.append(SimpleNamespace(piece=PieceId(piece), to_square=to))
    return SimpleNamespace(
        flow=SimpleNamespace(plies=tuple(plies)), moves=tuple(moves), balances=balances,
        counted=True,
    )  # fmt: skip


def test_an_equal_recapture_of_the_capturer_is_a_trade() -> None:
    # 12.Qxe4 Qxe4+ 13.Nxe4: the pawn, then the queens; b′ keeps the pawn from ply 1
    line_ = _fake(
        [("b.P.e7", "e4", "w.Q.d1", "e4", False), ("w.Q.d1", "e4", "b.Q.d8", "e4", False),
         ("b.Q.d8", "e4", "w.N.b1", "e4", False), (None, "", "b.P.d7", "d5", False)],
        (0, 1, -8, 1, 1),
    )  # fmt: skip
    assert trade_pairs(line_) == ((2, 3),)
    assert reduced_balances(line_) == (0, 1, 1, 1, 1)


def test_a_bishop_for_a_knight_is_a_trade_a_rook_for_a_knight_is_not() -> None:
    bxn = _fake(
        [(None, "", "w.P.a2", "a3", False), ("w.N.b1", "c3", "b.B.f8", "c3", False),
         ("b.B.f8", "c3", "w.P.b2", "c3", False)],
        (0, 0, -3, 0),
    )  # fmt: skip
    assert trade_pairs(bxn) == ((2, 3),)
    rxn = _fake(
        [(None, "", "w.K.e1", "d1", False), ("w.N.g1", "e3", "b.R.h8", "e3", False),
         ("b.R.h8", "e3", "w.P.f2", "e3", False)],
        (0, 0, -3, 2),
    )  # fmt: skip
    assert trade_pairs(rxn) == ()
    assert reduced_balances(rxn) == (0, 0, -3, 2)


def test_trades_do_not_overlap_and_never_promote() -> None:
    # P×P, P×P, P×P on d5: plies 1–2 pair, ply 3 cannot also close one
    chain = _fake(
        [("b.P.d7", "d5", "w.P.c2", "d5", False), ("w.P.c2", "d5", "b.P.c7", "d5", False),
         ("b.P.c7", "d5", "w.P.e2", "d5", False)],
        (0, 1, 0, 1),
    )  # fmt: skip
    assert trade_pairs(chain) == ((1, 2),)
    promoting = _fake(
        [("b.N.b8", "b8", "w.P.a2", "b8", True), ("w.P.a2", "b8", "b.R.a8", "b8", False)],
        (0, 11, 2),
    )  # fmt: skip
    assert trade_pairs(promoting) == ()


def test_the_queen_trade_names_the_pawn_of_the_move() -> None:
    fen = "rn2k2r/p2pq1pp/b1p5/1p6/3Np3/2P5/P2NQPPP/R1B1KB1R w KQkq - 2 12"
    lines = [
        line(fen, "Qe3 O-O Be2 c5 N4b3", WIN, cp=969),
        line(fen, "Qxe4 Qxe4+ Nxe4 d5 Ng3 O-O Be2 Re8 Be3", WIN, cp=898),
    ]
    gain = claim(run(fen, "Qxe4", lines, multipv=2), "material_gain_v3")
    event = finding(gain, MaterialFinding).event
    assert gain.verdict.status is S and event.ply == 1  # was 3, the recapture 13.Nxe4
    assert event.victim.square == "e4" and finding(gain, MaterialFinding).amount.points == 1
    assert _attributed(gain) is True


# -- concession_v1 on g1014 (EF-D §3, test 2) ------------------------------------------------------


def test_17_ne3_the_exchange_sacrifice_is_a_concession() -> None:
    fen = "rn2r3/p2p1k1p/b7/1pp2N2/8/2P5/P2N1PPP/R1B1KB1R w KQ - 3 17"
    lines = [
        line(fen, "Ne3 Re6 Kd1 Rxe3 fxe3 Kg6 Bd3+ Kg7", WIN, cp=933),
        line(fen, "Kd1 Kg6 Ne3 b4 cxb4 Bxf1 Rxf1", WIN, cp=895),
    ]
    analysis = run(fen, "Ne3", lines, multipv=2)
    gain = claim(analysis, "material_gain_v3")
    assert gain.verdict.status is S and _attributed(gain) is False  # the line's fact stays
    c = finding(gain, ConcessionFinding)
    assert (c.origin_first, c.origin_last, c.piece.square) == (4, 4, "e3")  # 18...Rxe3
    text = explain(analysis).text
    assert "wins the rook" not in text
    assert "It blocks the check from the rook on e8." in text  # EF-D §5


def test_11_nd2_the_pawn_black_left_is_a_concession() -> None:
    fen = "rnb1k2r/p2pq1pp/2p5/1p6/3Np3/2P5/P3QPPP/RNB1KB1R w KQkq - 0 11"
    lines = [
        line(fen, "Ba3 c5 Nb3 O-O Bxc5 Qf7", WIN, cp=1104),
        line(fen, "Nd2 O-O Qe3 d5 N2b3 Nd7 Nxc6 Qf6 Nbd4 Qd6", WIN, cp=819),
    ]
    analysis = run(fen, "Nd2", lines, multipv=2)
    gain = claim(analysis, "material_gain_v3")
    assert gain.verdict.status is S and _attributed(gain) is False
    c = finding(gain, ConcessionFinding)
    # 13...Nd7: the knight on b8 still defended c6 after 12...d5 (EF1 corrects EF-D §0.2)
    assert (c.origin_first, c.origin_last, c.piece.square) == (6, 6, "c6")
    assert "wins the pawn on c6" not in explain(analysis).text


def test_6_bb4_the_knight_exposed_before_is_attributed() -> None:
    fen = "rnbqkb1r/pp1p2pp/2p5/5p2/4n3/3P1N2/PPP1QPPP/RNB1KB1R b KQkq - 0 6"
    lines = [
        line(fen, "d5 dxe4 fxe4 Nd4 Be7 Nc3", EVEN, cp=-410),
        line(fen, "Bb4+ c3 Be7 dxe4 O-O e5 d6 exd6 Bxd6 Qd1 Re8+", LOST, cp=-667),
    ]
    loss = claim(run(fen, "Bb4+", lines, multipv=2), "material_loss_v2")
    assert loss.verdict.status is S and _attributed(loss) is True


def test_9_dxe4_a_capture_by_the_move_is_attributed() -> None:
    fen = "rnb1k2r/pp1pq1pp/2p5/5p2/4n3/2PP1N2/P3QPPP/RNB1KB1R w KQkq - 1 9"
    lines = [
        line(fen, "dxe4 fxe4 Ba3 c5 Nfd2 O-O Nb3 Qf7", WIN, cp=700),
        line(fen, "Nbd2 Nxd2 Bxd2 O-O", EVEN, cp=200),
    ]
    gain = claim(run(fen, "dxe4", lines, multipv=2), "material_gain_v3")
    assert gain.verdict.status is S and _attributed(gain) is True


def test_a_check_fork_that_cannot_be_answered_is_attributed_one_that_can_is_not() -> None:
    # EF1 A1: at the check, the forked piece's `safe_moves` decide; a knight forked by a knight
    # takes it back (Nxf3), a bishop cannot
    played, lp = "a3", "a3 Bc5 b5 Be7 b6 Nf3+ Ke2 Nxd4+ Kd3 Nf5"
    for fen, kept in (("4kb2/8/8/6n1/1P1B4/8/P7/4K3 w - - 0 1", True),
                      ("4kb2/8/8/6n1/1P1N4/8/P7/4K3 w - - 0 1", False)):  # fmt: skip
        quiet = "Bb2 Ne6 Kd2 Kd7" if kept else "Nb3 Ne6 Kd2 Kd7"
        lines = [line(fen, quiet, EVEN), line(fen, lp, LOST, cp=-500)]
        loss = claim(run(fen, played, lines, multipv=2), "material_loss_v2")
        assert loss.verdict.status is S and _attributed(loss) is kept
        if not kept:
            c = finding(loss, ConcessionFinding)
            assert (c.origin_first, c.origin_last) == (7, 7)  # 4.Ke2, while 4.Nxf3 kept it


# -- the forced test and undecided origins, on a fake view (EF-D §3.2–§3.3, test 2) --------------


class _View:
    """Just what `_classify` and `attribution` read: nodes, children, status, exchange."""

    def __init__(self) -> None:
        self.nodes, self.facts, self.children = {}, {}, {}

    def node(self, n):
        return self.nodes[n]

    def fact(self, family, n):
        return self.facts.get((family, n))

    def child(self, n, uci):
        return self.children.get((n, uci))

    def fact_entry(self, family, n):
        return SimpleNamespace(target=n, rev=1) if (family, n) in self.facts else None


def _status(moves=(), mating=(), in_check=False) -> StatusFacts:
    legal = tuple(LegalMove(u, u) for u in moves)
    return StatusFacts(
        Color.BLACK, in_check, (), False, False, False, len(legal), legal, (), (), mating, ()
    )


def _position(view, n, mover, square="d4"):
    view.nodes[n] = SimpleNamespace(mover=mover, square_of=lambda _piece, s=square: s)


def _setup(moves, children):
    """N_0 … N_4; Black (the loser) plays ply 4 `d7d6` from N_3, its other moves as given."""

    view = _View()
    nodes = tuple(NodeId(f"n{i}") for i in range(5))
    for i, n in enumerate(nodes):
        _position(view, n, Color.WHITE if i % 2 else Color.BLACK)
    view.facts[("status", nodes[3])] = _status(moves)
    for uci, mating in children.items():
        child = NodeId(f"c_{uci}")
        view.children[(nodes[3], uci)] = child
        _position(view, child, Color.BLACK)
        view.facts[("status", child)] = _status(mating=mating)
    quiet = SimpleNamespace(capture=None, promotion=None)
    line_ = SimpleNamespace(
        nodes=nodes, moves=tuple(SimpleNamespace(uci=u) for u in ("a", "b", "c", "d7d6")),
        flow=SimpleNamespace(plies=(quiet,) * 5), balances=(0, 0, 0, 0, 0, 3),
    )  # fmt: skip
    return view, line_


def test_the_only_legal_move_is_forced() -> None:
    view, line_ = _setup(("d7d6",), {})
    assert _classify(view, line_, 4, Color.BLACK, PieceId("b.N.b8"), 5)[0] is Attribution.ATTRIBUTED


def test_every_other_move_allowing_mate_in_one_is_forced() -> None:
    mating = (LegalMove("h1h8", "Rh8#"),)
    view, line_ = _setup(("d7d6", "a7a6", "h7h6"), {"a7a6": mating, "h7h6": mating})
    assert _classify(view, line_, 4, Color.BLACK, PieceId("b.N.b8"), 5)[0] is Attribution.ATTRIBUTED
    view, line_ = _setup(("d7d6", "a7a6", "h7h6"), {"a7a6": mating, "h7h6": ()})
    found, wanted, _ = _classify(view, line_, 4, Color.BLACK, PieceId("b.N.b8"), 5)
    assert found is Attribution.CONCESSION and not wanted


def test_a_missing_child_is_a_line_need_without_search() -> None:
    view, line_ = _setup(("d7d6", "a7a6"), {})
    found, wanted, _ = _classify(view, line_, 4, Color.BLACK, PieceId("b.N.b8"), 5)
    assert found is None and wanted == (LineNeed(NodeId("n3"), ("a7a6",), _none()),)


def test_the_reply_and_the_winner_s_plies_are_attributed() -> None:
    view, line_ = _setup(("d7d6", "a7a6"), {})
    piece = PieceId("b.N.b8")
    assert _classify(view, line_, 2, Color.BLACK, piece, 5)[0] is Attribution.ATTRIBUTED  # o ≤ 2
    assert _classify(view, line_, 3, Color.BLACK, piece, 5)[0] is Attribution.ATTRIBUTED  # White's


def test_an_exposing_capture_worth_the_piece_is_an_exchange() -> None:
    # EF1 A3: Black's ply 4 recaptures a rook (5) and so leaves a pawn (1): not a concession;
    # taking a knight (3) with the rook (5) that is then lost is one (17.Ne3's ...Rxe3)
    view, line_ = _setup(("d7d6", "a7a6"), {"a7a6": ()})
    took = SimpleNamespace(capture=object(), promotion=None)
    quiet = SimpleNamespace(capture=None, promotion=None)
    line_.flow = SimpleNamespace(plies=(quiet, quiet, quiet, took, quiet))
    line_.balances = (0, 0, 5, 5, 0, 1)  # the mover's: −5 at ply 4, +1 at the event (ply 5)
    view.facts[("move", line_.nodes[4])] = object()
    piece = PieceId("b.P.a4")
    assert _classify(view, line_, 4, Color.BLACK, piece, 5)[0] is Attribution.ATTRIBUTED
    line_.balances = (0, 0, 0, 0, -3, 2)  # takes 3, loses 5 at the event
    assert _classify(view, line_, 4, Color.BLACK, piece, 5)[0] is Attribution.CONCESSION


def _none():
    from calliope.facts import NONE

    return NONE


def _exchange(gain, safe=()):
    entry = PieceExchange("d4", Color.BLACK, PieceType.KNIGHT, gain, None, False, safe)
    return ExchangeFacts((entry,))


def test_undecided_origins_read_both_ways_and_disagree() -> None:
    # Black captures at ply 4, so White is the loser. N_2 is in check without a safe-moves record:
    # o⁺ = 2 (the reply, attributed), o⁻ = 3 (White's own move, a concession: its other move
    # allows no mate), so the attribution stays open
    view, nodes = _View(), tuple(NodeId(f"m{i}") for i in range(5))
    movers = (None, Color.WHITE, Color.BLACK, Color.WHITE, Color.BLACK)
    for n, mover in zip(nodes, movers, strict=True):
        _position(view, n, mover)
    exposed, check = Defined("see_v1", 3), NotApplicable("IN_CHECK")
    for i, gain in enumerate((Defined("see_v1", 0), Defined("see_v1", 0), check, exposed)):
        view.facts[("exchange", nodes[i])] = _exchange(gain, safe=None if gain is check else ())
    view.facts[("status", nodes[2])] = _status(("y", "x"), in_check=True)
    view.children = {(nodes[2], "x"): NodeId("free")}
    _position(view, NodeId("free"), Color.WHITE)
    view.facts[("status", NodeId("free"))] = _status()
    victim = SimpleNamespace(piece=PieceId("b.N.d4"))
    event = SimpleNamespace(ply=4, victim=victim, node=nodes[4])
    quiet = SimpleNamespace(capture=None, promotion=None)
    line_ = SimpleNamespace(
        nodes=nodes, moves=tuple(SimpleNamespace(uci=u) for u in "axyz"),
        flow=SimpleNamespace(plies=(quiet,) * 4), balances=(0, 0, 0, 0, 3),
    )  # fmt: skip
    result = attribution(view, line_, event)
    assert result.state is Attribution.UNDECIDED and result.origins == (2, 3)


# -- check_answer_v1 (EF-D §5, test 4) -------------------------------------------------------------


def _answer(fen: str, move: str, rest: str = "") -> CheckAnswerFinding:
    lines = [line(fen, f"{move} {rest}".strip(), EVEN)]
    return finding(claim(run(fen, move, lines, multipv=1), "check_answer_v1"), CheckAnswerFinding)


def test_a_block_a_capture_and_a_king_move() -> None:
    block = _answer("rn2r3/p2p1k1p/b7/1pp2N2/8/2P5/P2N1PPP/R1B1KB1R w KQ - 3 17", "Ne3")
    assert (block.kind, [c.square for c in block.checkers]) == (CheckAnswerKind.BLOCK, ["e8"])
    capture = _answer("rnbqk2r/pp1p2pp/2p5/5p2/4n3/2bP1N2/PP2QPPP/RNB1KB1R w KQkq - 0 8", "bxc3")
    assert capture.kind is CheckAnswerKind.CAPTURE
    king = _answer("rnbqk2r/pp1p2pp/2p5/5p2/4n3/2bP1N2/PP2QPPP/RNB1KB1R w KQkq - 0 8", "Kd1")
    assert king.kind is CheckAnswerKind.KING


def test_a_checking_pawn_taken_en_passant_is_a_capture() -> None:
    found = _answer("4k3/8/8/3pP3/4K3/8/8/8 w - d6 0 2", "exd6")
    assert found.kind is CheckAnswerKind.CAPTURE and [c.square for c in found.checkers] == ["d5"]


def test_a_double_check_is_answered_by_the_king() -> None:
    found = _answer("4r1k1/8/8/8/1b6/8/8/4K3 w - - 0 1", "Kf2")
    assert found.kind is CheckAnswerKind.KING and len(found.checkers) == 2
    assert found.legal_moves >= 1


def test_no_check_no_claim_and_forced_keeps_its_own_sentence() -> None:
    fen = "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"
    analysis = run(fen, "a3", [line(fen, "a3 Kd7", EVEN)], multipv=1)
    assert not [c for c in analysis.claims if c.hypothesis.template == "check_answer_v1"]
    # the only legal move out of check: FORCED, and its sentence alone (EF-D §5)
    fen = "7k/8/8/8/8/8/1q6/K7 w - - 0 1"
    analysis = run(fen, "Kxb2", [line(fen, "Kxb2 Kg7", EVEN)], multipv=1)
    assert claim(analysis, "check_answer_v1").verdict.status is S
    assert explain(analysis).text.endswith("It is the only legal move.")
