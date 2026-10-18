"""MS-D §5 over scripted lines: a relation claim's relation is read from its finding and the records
its evidence names; its time from the positions before and after the move (review N3), never from
its template's name; its link from the claim graph."""

from __future__ import annotations

from story import S, claim, line, run

from calliope.facts import EnsureRequest, FactEngine
from calliope.reasoning.piece_relations import MOVE, claim_relation

EVEN, LOST = (300, 600, 100), (0, 100, 900)


def _with_exchange(analysis):
    """The analysis's tree with `exchange` on the move's two nodes (an on-request family)."""

    tree = analysis.tree
    subject = analysis.round_zero.subject
    FactEngine().ensure(tree, EnsureRequest((subject.parent, subject.child), ("exchange",)))
    return tree.view()


def test_a_piece_moved_into_attack_is_an_exposure_that_began() -> None:
    # the knight on d5 is safe; 1.Nb4 puts it where the a5 pawn takes it
    fen = "4k3/8/8/p2N4/8/8/8/4K3 w - - 0 1"
    lines = [
        line(fen, "Ne3 Kd7 Kd2 Kd6", EVEN),
        line(fen, "Nb4 axb4 Kd2 Kd7 Kc2 Kd6", LOST, cp=-300),
    ]
    analysis = run(fen, "Nb4", lines, multipv=2)
    exposed = claim(analysis, "newly_exposed_v1")
    assert exposed.verdict.status is S
    read = claim_relation(analysis, exposed, analysis.tree.view(), _with_exchange(analysis))
    assert read is not None
    assert read.relation.kind == "exposed" and read.relation.place == MOVE
    assert read.relation.time == "began" and read.relation.role("piece").square == "b4"
    assert read.link is not None and read.link.kind in ("explains", "associated_with")


def test_a_piece_en_prise_that_moves_to_another_attacked_square_held_its_exposure() -> None:
    # review N3: the knight on d5 is en prise to c6 and 1.Nb4 leaves it en prise to a5 —
    # `newly_exposed_v1` (it skips the check before for a moved piece) yet the relation held
    fen = "4k3/8/2p5/p2N4/8/8/8/4K3 w - - 0 1"
    lines = [
        line(fen, "Ne3 Kd7 Kd2 Kd6", EVEN),
        line(fen, "Nb4 axb4 Kd2 Kd7 Kc2 Kd6", LOST, cp=-300),
    ]
    analysis = run(fen, "Nb4", lines, multipv=2)
    exposed = claim(analysis, "newly_exposed_v1")
    assert exposed.verdict.status is S
    read = claim_relation(analysis, exposed, analysis.tree.view(), _with_exchange(analysis))
    assert read is not None and read.relation.time == "held"


def test_a_claim_of_another_kind_or_not_supported_has_no_relation() -> None:
    fen = "4k3/8/8/p2N4/8/8/8/4K3 w - - 0 1"
    lines = [
        line(fen, "Ne3 Kd7 Kd2 Kd6", EVEN),
        line(fen, "Nb4 axb4 Kd2 Kd7 Kc2 Kd6", LOST, cp=-300),
    ]
    analysis = run(fen, "Nb4", lines, multipv=2)
    loss = claim(analysis, "material_loss_v2")
    assert claim_relation(analysis, loss, analysis.tree.view()) is None


class _Without:
    """A view without one family's record at one node (a record the analysis did not ask for)."""

    def __init__(self, view, family, node) -> None:
        self.view, self.family, self.node_id = view, family, node

    def fact(self, family, node):
        return (
            object()
            if (family, node) == (self.family, self.node_id)
            else self.view.fact(family, node)
        )

    def node(self, node):
        return self.view.node(node)


def test_without_the_record_before_a_moved_piece_the_relation_is_not_read() -> None:
    # MS-D §5: a relation not read whole is left out (the claim stays unmatched), unless the facts
    # tree of the game supplies the record (`move_view`)
    fen = "4k3/8/8/p2N4/8/8/8/4K3 w - - 0 1"
    lines = [
        line(fen, "Ne3 Kd7 Kd2 Kd6", EVEN),
        line(fen, "Nb4 axb4 Kd2 Kd7 Kc2 Kd6", LOST, cp=-300),
    ]
    analysis = run(fen, "Nb4", lines, multipv=2)
    exposed = claim(analysis, "newly_exposed_v1")
    view = analysis.tree.view()
    hidden = _Without(view, "exchange", analysis.round_zero.subject.parent)
    assert claim_relation(analysis, exposed, hidden) is None
    read = claim_relation(analysis, exposed, hidden, view)
    assert read is not None and read.relation.time == "began"
