"""The label benchmark tool (LV-D §9) without an engine: the static prefilter and the summary."""

from __future__ import annotations

import chess

from tools.label_bench.__main__ import offered, summary


def test_the_prefilter_finds_a_piece_offer_and_ignores_a_quiet_move() -> None:
    board = chess.Board("r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQ1RK1 w - - 0 1")
    assert offered(board, board.parse_san("Bxf7+"))  # the bishop for a pawn: net 2
    assert not offered(board, board.parse_san("d3"))
    trade = chess.Board("4k3/5p2/4n3/8/2B5/8/8/4K3 w - - 0 1")
    assert not offered(trade, trade.parse_san("Bxe6"))  # takes 3, may be retaken for 3: net 0


def _row(game: int, ply: int, brilliant: bool, called: bool) -> dict:
    labels = [("brilliant", "brilliant_p1")] if called else []
    verdicts = {} if called else {"piece_sacrifice_v1": ("refuted", None)}
    return {
        "game": game,
        "ply": ply,
        "brilliant": brilliant,
        "labels": labels,
        "verdicts": verdicts,
    }


def test_the_summary_counts_found_false_and_halves() -> None:
    rows = [_row(0, 5, True, True), _row(0, 9, False, True), _row(1, 7, True, False)]
    out = summary(rows, [41, 21])
    assert out["all"] == {"games": 2, "found": 1, "false_calls": 1, "false_per_1000": 16.67}
    assert out["even"]["found"] == 1 and out["odd"]["found"] == 0
    assert out["missed_by"] == {"sacrifice: refuted": 1}
