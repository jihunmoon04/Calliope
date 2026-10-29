"""`python -m tools.explain_game GAME.pgn`: every ply of a game, analysed and explained (R4-D §5).

The PGN intake, the grading from the headers and the requests are the server's pipeline
(`calliope.server.pipeline`, AS-D S3); this tool keeps its options and its output.

For each ply it builds an `AnalysisRequest` (the game's moves, that ply as the target, the default
profile), runs the reasoner and `explain`. The grading spec comes from the headers: the players'
ratings, the time control, and the pool (chess.com when the `Site` header says so, else Lichess).
`--bundles DIR` writes each ply's `fact_tree_v1` / `claim_graph_v1` pair and re-loads it;
`--json OUT` writes the game's `calliope_result_v1` document (AR-D §6), with each ply's bundle
digests. A grading that falls back to the default curve is reported in one warning line.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from calliope.facts import EngineProfile, EngineResultStore, FactEngine, PositionRecords
from calliope.reasoning.storage import load, save
from calliope.results import Bundle, PlyInput, dumps
from calliope.server.pipeline import (
    MAX_POSITION_RECORDS,
    MAX_STORE_SEARCHES,
    EngineSlot,
    Prefetch,
    analyse_ply,
    document,
    fingerprint,
    game_input,
    grading_for,
    parse_game,
)
from calliope.server.pipeline import plies_range as _plies

__all__ = ["explain_game", "fallback_warning", "game_input", "grading_for", "line", "main"]


def explain_game(
    engine, pgn_text: str, *, plies: str | None = None, bundles: Path | None = None,
    digests: bool = False, detail: bool = False, ahead: EngineSlot | None = None,
) -> tuple[list[dict], dict | None]:  # fmt: skip
    """One record per ply (its move, grade, labels, supported claims and text) and the game's
    `calliope_result_v1` document. The bundle's digests are in both when `digests` or `bundles`
    is set (R4 review B1: `--json` alone needs them too); `stored` only with `bundles`. With no
    ply to analyse there are no records and no document (AR1 review B2).

    `engine` is an engine port or an `EngineSlot`. Each ply goes through the server's per-ply
    path, `analyse_ply` (AS-D §15): an engine failure restarts the slot's engine once, and a
    second one stops the tool with `JobFailed`. With `ahead`, a second engine's slot, every ply's
    played positions are surveyed ahead of its analysis (PF-D §4.2); without it, none are."""

    slot = engine if isinstance(engine, EngineSlot) else EngineSlot(lambda: engine)
    bound = fingerprint(slot.port)  # every ply runs on this engine
    parsed = parse_game(pgn_text)  # the shared pipeline (AS-D S3); ValueError when unreadable
    profile = EngineProfile()  # one profile: every request's, and the document's (AR-D §5)
    # the run's searches and POSITION records, shared by its plies (PF-D §2, §3)
    store, memo = EngineResultStore(MAX_STORE_SEARCHES), PositionRecords(MAX_POSITION_RECORDS)
    selected = list(_plies(plies, len(parsed.sans)))
    run = None
    if ahead is not None:  # no ply cache: every ply of the range is listed (§4.2)
        run = Prefetch(ahead).start(FactEngine(engine=slot.port, store=store), parsed, selected,
                                    profile)  # fmt: skip
    try:
        records, inputs = _explain(slot, parsed, selected, profile, bound, store, memo, run,
                                   bundles, digests)  # fmt: skip
    finally:
        if run is not None:
            try:
                run.stop()
            except KeyboardInterrupt:  # a second interrupt: still never close it mid-search
                run.thread.join()
                raise
    if not inputs:
        return records, None
    # the port's identity (equal to `bound`), the requests' profile
    return records, document(parsed, slot.port.identity, profile, inputs, detail=detail)


def _explain(slot, parsed, selected, profile, bound, store, memo, run, bundles, digests):
    sans = parsed.sans
    records, inputs = [], []
    for ply in selected:
        if run is not None:
            run.reach(ply)
        analysis, rendered = analyse_ply(slot, parsed, ply, profile, bound, store=store, memo=memo)
        judgement = analysis.round_zero.judgements[0]
        label = analysis.labels[0] if analysis.labels else None
        record = {
            "ply": ply,
            "move": sans[ply - 1],
            "grade": judgement.grade.value if judgement.grade is not None else None,
            "labels": [[lb.kind.value, lb.rule, lb.provisional] for lb in analysis.labels],
            "supported": sorted({c.hypothesis.template for c in analysis.claims if c.supported}),
            "text": rendered.text,
            "provisional": label.rule if label is not None and label.provisional else None,
        }
        bundle = None
        if digests or bundles is not None:
            tree_bytes, graph_bytes = save(analysis, rendered)
            record["bundle"] = {"tree": hashlib.sha256(tree_bytes).hexdigest(),
                                "graph": hashlib.sha256(graph_bytes).hexdigest()}  # fmt: skip
            bundle = Bundle(record["bundle"]["tree"], record["bundle"]["graph"],
                            stored=bundles is not None)  # fmt: skip
        if bundles is not None:
            bundles.mkdir(parents=True, exist_ok=True)
            (bundles / f"{ply}.tree").write_bytes(tree_bytes)
            (bundles / f"{ply}.graph").write_bytes(graph_bytes)
            loaded, again = load(FactEngine(), tree_bytes, graph_bytes)  # re-loaded and checked
            if save(loaded, again) != (tree_bytes, graph_bytes):
                raise RuntimeError(f"ply {ply}: the bundle did not round-trip")
        records.append(record)
        inputs.append(PlyInput(ply, analysis, rendered, bundle))
    return records, inputs


def fallback_warning(result: dict | None) -> str | None:
    """One line when the grading fell back to the default curve (AR-D §6; R4 record §4)."""

    if result is None:
        return None
    grading = result["grading"]
    if not grading["fallback"]:
        return None
    scale = grading["curve"]["scale"]
    return (f"warning: graded with the default curve (logistic10, scale {scale}): "
            "the PGN gives no ratings and time class to choose one")  # fmt: skip


def line(record: dict) -> str:
    """One output line; a provisional label's rule is marked here, not in the text (R3-D H9)."""

    mark = f"[{record['provisional']}, provisional] " if record["provisional"] else ""
    return f"{mark}{record['text']}"


def main(argv: list[str] | None = None) -> int:
    from calliope.facts.search import StockfishEngine

    parser = argparse.ArgumentParser(prog="python -m tools.explain_game")
    parser.add_argument("pgn", type=Path)
    parser.add_argument("--plies", help="a ply or a range, e.g. 17 or 1-40")
    parser.add_argument("--bundles", type=Path, help="write and re-load each ply's bundle here")
    parser.add_argument("--json", type=Path, help="write the calliope_result_v1 document here")
    parser.add_argument("--analysis", action="store_true",
                        help="with --json: each ply's every claim, scope and finding (DF-D §4.3)")  # fmt: skip
    parser.add_argument("--with-commentary", type=Path, metavar="DATA",
                        help="with --json: each ply's newest current AI commentary from DATA's "
                             "store as `ai_commentary` (AG-D §8)")  # fmt: skip
    parser.add_argument("--prefetch-engines", type=int, choices=(0, 1), default=1,
                        help="engines that survey the played positions ahead (PF-D §4.3)")  # fmt: skip
    args = parser.parse_args(argv)
    path = os.environ["CALLIOPE_STOCKFISH_PATH"]
    slot = EngineSlot(lambda: StockfishEngine.start(path))  # restartable (AS-D §5.2)
    ahead = EngineSlot(lambda: StockfishEngine.start(path)) if args.prefetch_engines else None
    try:
        records, result = explain_game(
            slot, args.pgn.read_text(), plies=args.plies, bundles=args.bundles,
            digests=args.json is not None, detail=args.analysis, ahead=ahead,
        )  # fmt: skip
    finally:  # the prefetch has stopped: its engine first, then the main one (§4.2)
        if ahead is not None:
            ahead.close()
        slot.close()
    for record in records:
        print(line(record))
    warning = fallback_warning(result)
    if warning:
        print(warning, file=sys.stderr)
    if args.json:
        if result is None:  # a document needs one analysed ply (AR1 review B2)
            print("error: --json: the game or the --plies range has no ply to analyse",
                  file=sys.stderr)  # fmt: skip
            return 2
        if args.with_commentary is not None:
            from calliope.server import CommentaryStore, game_key, parse_game, with_commentary

            parsed = parse_game(args.pgn.read_text())
            store = CommentaryStore(args.with_commentary.expanduser() / "commentary")
            result = with_commentary(result, store.for_game(game_key(parsed.game)),
                                     list(parsed.uci))  # fmt: skip
        args.json.write_bytes(dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
