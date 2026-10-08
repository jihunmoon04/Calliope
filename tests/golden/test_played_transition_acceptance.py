"""I1 acceptance: PLAYED_TRANSITION against the frozen I1-D corpus (D01-D20).

Two independent oracles are used and neither is derived from the implementation:

* the committed JSON (`docs/legacy/corpus/played-transition-i1d-v1.json`): participants, critical core
  keys, ledger dispositions, exact digest sentences, status provenance and, for D06/D13, the
  complete census and ranking;
* a python-chess-only census below that re-derives, for every positive case, every changed
  shared fact, event and material key, then the frozen I1-D rank/cap/duplicate rules.
"""

import json
from pathlib import Path

import chess
import pytest
from test_scenario_design_observations import build

from calliope.domain.analysis.scenario import (
    Bucket,
    CaptureKey,
    CountKey,
    FileKey,
    PinKey,
    PlayedMoveTarget,
    PresentationExclusion,
    RayKey,
    ScenarioKind,
    ScenarioRequest,
    StepKey,
    SubjectKey,
    TemplateId,
    TransitionKey,
)
from calliope.domain.chess import ChessMove
from calliope.services.position.scenario import ScenarioLineAnalyzer
from calliope.services.position.scenario_observation import (
    PlayedObservationSelector,
    compact_observations,
)
from calliope.services.position.scenario_renderer import ScenarioSummaryRenderer

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.loads(
    (ROOT / "docs" / "legacy" / "corpus" / "played-transition-i1d-v1.json").read_text(encoding="utf-8")
)
POSITIVE = [c for c in CORPUS["cases"] if c["kind"] == "PLAYED_TRANSITION"]
BY_ID = {c["id"]: c for c in CORPUS["cases"]}


def summarize(fen, uci, line_san=None):
    rules, lines = build()
    request = ScenarioRequest(
        ScenarioKind.PLAYED_TRANSITION,
        PlayedMoveTarget(ChessMove(uci)),
        rules.position_from_fen(fen),
        (ChessMove(uci, line_san),),
        1,
    )
    return ScenarioLineAnalyzer(lines).analyze(request)


def fmt(bucket, key):
    """The corpus' shorthand for one typed (Bucket, CandidateKey)."""
    if type(key) is CaptureKey:
        return f"EVENTS/CAPTURE:ply{key.ply}:capture"
    if type(key) is TransitionKey:
        return f"EVENTS/{key.family.value}:ply{key.ply}:base-{key.subject.base_square}"
    if type(key) is CountKey:
        return f"AGGREGATES/{key.family.value}:{key.color.value}:{key.piece_type.value}"
    inner = key.property if type(key) is StepKey else key
    if type(inner) is SubjectKey:
        selector = f"base-{inner.subject.base_square}"
    elif type(inner) is RayKey:
        df, dr = inner.direction
        selector = f"base-{inner.subject.base_square}:dir-{df},{dr}"
    elif type(inner) is FileKey:
        selector = f"file-{inner.file}"
    elif type(inner) is PinKey:
        selector = (
            f"pinner-{inner.pinner.base_square}:pinned-{inner.pinned.base_square}"
            f":king-{inner.king.base_square}"
        )
    else:
        raise AssertionError(f"unexpected PLAYED key {key!r}")
    return f"{bucket.value.upper()}/{inner.family.value}:{selector}"


# ---- independent python-chess census --------------------------------------------------------

SLIDERS = {
    chess.BISHOP: ((-1, -1), (-1, 1), (1, -1), (1, 1)),
    chess.ROOK: ((-1, 0), (0, -1), (0, 1), (1, 0)),
}
SLIDERS[chess.QUEEN] = tuple(sorted(SLIDERS[chess.BISHOP] + SLIDERS[chess.ROOK]))
NAMES = {chess.WHITE: "white", chess.BLACK: "black"}
FAMILY_ORDER = (
    "PIECE_STATE",
    "PAWN_FLAGS",
    "PAWN_SUPPORTERS",
    "FILE_STATE",
    "ATTACK_FOOTPRINT",
    "ATTACK_PARTITION",
    "RAY_STATE",
    "PIN_PRESENT",
)
TIERS = {
    "CAPTURE": 0,
    "PROMOTION": 1,
    "CASTLING_ROOK": 2,
    "PIN_PRESENT": 3,
    "FILE_STATE": 4,
    "MATERIAL_COUNTS": 5,
    "PAWN_FLAGS": 6,
    "PAWN_SUPPORTERS": 7,
    "MOVE": 8,
    "ATTACK_FOOTPRINT": 9,
    "ATTACK_PARTITION": 10,
    "RAY_STATE": 11,
    "PIECE_STATE": 12,
}
NA = "NOT_APPLICABLE"


class Frame:
    def __init__(self, board, bases):
        self.board, self.bases = board, bases  # bases: current square -> initial square
        self.where = {b: sq for sq, b in bases.items()}

    def piece(self, base):
        square = self.where.get(base)
        return (square, self.board.piece_at(square)) if square is not None else (None, None)

    def piece_state(self, base):
        square, piece = self.piece(base)
        return "CAPTURED" if piece is None else (piece.color, piece.piece_type, square)

    def pawn_flags(self, base):
        square, piece = self.piece(base)
        if piece is None or piece.piece_type != chess.PAWN:
            return NA
        file, rank = chess.square_file(square), chess.square_rank(square)
        friendly = self.board.pieces(chess.PAWN, piece.color)
        enemy = self.board.pieces(chess.PAWN, not piece.color)
        ahead = 1 if piece.color == chess.WHITE else -1
        return (
            not any(abs(chess.square_file(p) - file) == 1 for p in friendly),
            sum(chess.square_file(p) == file for p in friendly) >= 2,
            not any(
                abs(chess.square_file(p) - file) <= 1 and (chess.square_rank(p) - rank) * ahead > 0
                for p in enemy
            ),
        )

    def supporters(self, base):
        square, piece = self.piece(base)
        if piece is None or piece.piece_type != chess.PAWN:
            return NA
        ahead = 1 if piece.color == chess.WHITE else -1
        found = (
            self.bases[p]
            for p in self.board.pieces(chess.PAWN, piece.color)
            if abs(chess.square_file(p) - chess.square_file(square)) == 1
            and chess.square_rank(square) - chess.square_rank(p) == ahead
        )
        return tuple(sorted(found))

    def footprint(self, base):
        square, piece = self.piece(base)
        return NA if piece is None else tuple(sorted(self.board.attacks(square)))

    def partition(self, base):
        square, piece = self.piece(base)
        if piece is None:
            return NA
        parts = {"empty": [], "friendly": [], "enemy": []}
        for target in sorted(self.board.attacks(square)):
            other = self.board.piece_at(target)
            kind = (
                "empty" if other is None else "friendly" if other.color == piece.color else "enemy"
            )
            parts[kind].append(target)
        return tuple(tuple(parts[k]) for k in ("empty", "friendly", "enemy"))

    def ray(self, base, direction):
        square, piece = self.piece(base)
        if piece is None or direction not in SLIDERS.get(piece.piece_type, ()):
            return NA
        df, dr = direction
        file, rank = chess.square_file(square), chess.square_rank(square)
        visible, occupants, blocked = [], [], False
        while 0 <= file + df < 8 and 0 <= rank + dr < 8:
            file, rank = file + df, rank + dr
            target = chess.square(file, rank)
            other = self.board.piece_at(target)
            if not blocked:
                visible.append(target)
            if other is not None:
                occupants.append((target, self.bases[target], other.color, other.piece_type))
                blocked = True
        return (square, piece.piece_type, tuple(visible), tuple(occupants))

    def file_counts(self, file):
        return tuple(
            sum(
                self.board.piece_at(chess.square(file, r)) == chess.Piece(chess.PAWN, color)
                for r in range(8)
            )
            for color in (chess.WHITE, chess.BLACK)
        )

    def pins(self):
        triples = set()
        for square, piece in self.board.piece_map().items():
            if piece.piece_type == chess.KING or not self.board.is_pinned(piece.color, square):
                continue
            king = self.board.king(piece.color)
            df = (chess.square_file(square) > chess.square_file(king)) - (
                chess.square_file(square) < chess.square_file(king)
            )
            dr = (chess.square_rank(square) > chess.square_rank(king)) - (
                chess.square_rank(square) < chess.square_rank(king)
            )
            file, rank = chess.square_file(square) + df, chess.square_rank(square) + dr
            while self.board.piece_at(chess.square(file, rank)) is None:
                file, rank = file + df, rank + dr
            pinner = chess.square(file, rank)
            triples.add((self.bases[pinner], self.bases[square], self.bases[king]))
        return triples


def frames(fen, uci):
    before = chess.Board(fen)
    move = chess.Move.from_uci(uci)
    assert move in before.legal_moves
    bases0 = {square: square for square in before.piece_map()}
    bases1 = dict(bases0)
    victim = rook = None
    if before.is_capture(move):
        victim_square = (
            chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
            if before.is_en_passant(move)
            else move.to_square
        )
        victim = bases1.pop(victim_square)
    if before.is_castling(move):
        kingside = chess.square_file(move.to_square) == 6
        rank = chess.square_rank(move.from_square)
        source, target = (
            chess.square(7 if kingside else 0, rank),
            chess.square(5 if kingside else 3, rank),
        )
        rook = bases1[source]
        bases1[target] = bases1.pop(source)
    bases1[move.to_square] = bases1.pop(move.from_square)
    after = before.copy()
    after.push(move)
    return before, move, Frame(before, bases0), Frame(after, bases1), victim, rook


def independent_census(fen, uci):
    """(core keys, eligible keys in frozen rank order, {key: exclusion}) from python-chess only."""
    board, move, f0, f1, victim, rook = frames(fen, uci)
    participants = {move.from_square, victim, rook} - {None}
    keys, rank, exclusion = [], {}, {}

    def changed(family, selector, before, after, subject=None, order=()):
        if before == after:
            return
        step, endpoint = f"STEPS/{family}:{selector}", f"ENDPOINTS/{family}:{selector}"
        keys.extend((step, endpoint))
        direct = 0 if subject is None or subject in participants else 1
        rank[step] = (TIERS[family], direct, FAMILY_ORDER.index(family), *order)
        exclusion[endpoint] = PresentationExclusion.SEMANTIC_DUPLICATE
        if any(v in (NA, "CAPTURED") for v in (before, after)):
            exclusion[step] = PresentationExclusion.CONTEXT_ONLY

    for base in sorted(f0.bases.values()):
        name = f"base-{chess.square_name(base)}"
        changed("PIECE_STATE", name, f0.piece_state(base), f1.piece_state(base), base, (base,))
        pawn = any(
            p is not None and p.piece_type == chess.PAWN
            for _, p in (f0.piece(base), f1.piece(base))
        )
        if pawn:
            changed("PAWN_FLAGS", name, f0.pawn_flags(base), f1.pawn_flags(base), base, (base,))
            changed(
                "PAWN_SUPPORTERS", name, f0.supporters(base), f1.supporters(base), base, (base,)
            )
        changed("ATTACK_FOOTPRINT", name, f0.footprint(base), f1.footprint(base), base, (base,))
        changed("ATTACK_PARTITION", name, f0.partition(base), f1.partition(base), base, (base,))
        directions = set()
        for frame in (f0, f1):
            piece = frame.piece(base)[1]
            directions.update(SLIDERS.get(piece.piece_type, ()) if piece else ())
        for df, dr in sorted(directions):
            changed(
                "RAY_STATE",
                f"{name}:dir-{df},{dr}",
                f0.ray(base, (df, dr)),
                f1.ray(base, (df, dr)),
                base,
                (base, df, dr),
            )
    for file in range(8):
        changed(
            "FILE_STATE",
            f"file-{'abcdefgh'[file]}",
            f0.file_counts(file),
            f1.file_counts(file),
            order=(file,),
        )
    pins0, pins1 = f0.pins(), f1.pins()
    for triple in sorted(pins0 | pins1):
        selector = "pinner-{}:pinned-{}:king-{}".format(*map(chess.square_name, triple))
        changed("PIN_PRESENT", selector, triple in pins0, triple in pins1, order=triple)

    def event(kind, selector, base_order):
        key = f"EVENTS/{kind}:ply1:{selector}"
        keys.append(key)
        rank[key] = (TIERS[kind], 0, 1, *base_order)

    source = chess.square_name(move.from_square)
    if board.is_capture(move):
        event("CAPTURE", "capture", (0,))
    if move.promotion:
        event("PROMOTION", f"base-{source}", (move.from_square,))
    elif not board.is_capture(move):
        event("MOVE", f"base-{source}", (move.from_square,))
    if rook is not None:
        event("CASTLING_ROOK", f"base-{chess.square_name(rook)}", (rook,))
    for color in (chess.WHITE, chess.BLACK):
        for kind in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            if len(f0.board.pieces(kind, color)) != len(f1.board.pieces(kind, color)):
                key = f"AGGREGATES/MATERIAL_COUNTS:{NAMES[color]}:{chess.piece_name(kind)}"
                keys.append(key)
                rank[key] = (TIERS["MATERIAL_COUNTS"], 0, 2, color == chess.BLACK, kind)
    eligible = sorted((k for k in rank if k not in exclusion), key=lambda k: rank[k])
    for key in eligible[2:]:
        exclusion[key] = PresentationExclusion.CAP_EXCEEDED
    return set(keys), eligible, exclusion


# ---- acceptance ------------------------------------------------------------------------------


def ledger_of(summary):
    selection = PlayedObservationSelector().select(summary)
    return selection, {fmt(c.bucket, c.key): c for c in selection.candidates}


@pytest.mark.parametrize("case", POSITIVE, ids=lambda c: c["id"])
def test_frozen_corpus_expectations(case):
    summary = summarize(case["fen"], case["uci"])
    assert summary.definition_version == "scenario_summary_v2"
    assert summary.detail.definition_version == "played_transition_rules_v1"
    assert summary.focus_timeline == ()
    # The corpus lists participants as a set (its checker compares sets); the detail contract
    # fixes canonical base-square order.
    bases = [p.base.base_square for p in summary.detail.participants]
    assert set(bases) == set(case["participants"]) and len(bases) == len(case["participants"])
    assert bases == sorted(bases, key=chess.parse_square)
    assert [len(p.history_refs) for p in summary.detail.participants] == [2] * len(
        case["participants"]
    )
    rows = summary.selection_accounting
    assert len(rows) == case["accounting"]["rows"] == 21
    assert not any(r.bucket is Bucket.SNAPSHOTS for r in rows)
    assert not any(r.family.value == "FOCUS_LOSSES" for r in rows)
    included = {fmt(r.bucket, k) for r in rows for k in r.included_keys}
    excluded = {fmt(r.bucket, k) for r in rows for k in r.excluded_keys}
    assert set(case["core_included_contains"]) <= included
    assert excluded == set(case["core_excluded_exact"]) == set()
    assert all(r.candidate_keys == r.included_keys for r in rows)

    _, ledger = ledger_of(summary)
    assert len(ledger) == len(included)
    for check in case["ledger_checks"]:
        row = ledger[check["key"]]
        assert row.decision.value == check["decision"], check
        assert (row.exclusion.value if row.exclusion else None) == check["reason"], check
        if "duplicate_of" in check:
            assert fmt(Bucket.STEPS, row.duplicate_of) == check["duplicate_of"]

    observations = compact_observations(summary)
    assert [
        {
            "key": fmt(o.bucket, o.key),
            "template_id": o.sentence.template_id.value,
            "text": o.sentence.text,
        }
        for o in observations
    ] == case["digest"]
    report = ScenarioSummaryRenderer().render(summary)
    assert report.digest == tuple(o.sentence for o in observations)
    status = case["status"]
    assert [(s.template_id.value, s.text) for s in report.detail] == [
        (status["template_id"], status["text"])
    ]
    first = summary.events[0]
    assert fmt(Bucket.EVENTS, first.key) == status["source_event_key"]
    assert report.detail[0].source_refs == first.source_refs


@pytest.mark.parametrize("case", POSITIVE, ids=lambda c: c["id"])
def test_independent_complete_census_rank_and_cap(case):
    summary = summarize(case["fen"], case["uci"])
    keys, eligible, exclusion = independent_census(case["fen"], case["uci"])
    included = {fmt(r.bucket, k) for r in summary.selection_accounting for k in r.included_keys}
    assert included == keys
    selection, ledger = ledger_of(summary)
    assert [fmt(b, k) for b, k in selection.selected_keys] == eligible[:2]
    for key, row in ledger.items():
        assert row.exclusion == exclusion.get(key), key


@pytest.mark.parametrize("case_id", CORPUS["contract"]["exhaustive_oracle_cases"])
def test_exhaustive_d06_d13_census_and_ranking(case_id):
    case = BY_ID[case_id]
    oracle = case["exhaustive_one_ply_oracle"]
    summary = summarize(case["fen"], case["uci"])
    included = {fmt(r.bucket, k) for r in summary.selection_accounting for k in r.included_keys}
    assert included == set(oracle["full_core_included_keys"])
    selection, ledger = ledger_of(summary)
    eligible = sorted(
        (
            c
            for c in selection.candidates
            if c.exclusion in (None, PresentationExclusion.CAP_EXCEEDED)
        ),
        key=lambda c: c.rank,
    )
    assert [fmt(c.bucket, c.key) for c in eligible] == oracle["ranked_eligible_keys"]
    decisions = {d["key"]: d for d in oracle["full_presentation_decisions"]}
    assert set(decisions) == set(ledger)
    for key, expected in decisions.items():
        row = ledger[key]
        assert row.decision.value == expected["decision"], key
        assert (row.exclusion.value if row.exclusion else None) == expected["reason"], key
        assert row.rank[0] == expected["rank_tier"], key
        if "duplicate_of" in expected:
            assert fmt(Bucket.STEPS, row.duplicate_of) == expected["duplicate_of"]


def keys_of(summary):
    return {fmt(r.bucket, k) for r in summary.selection_accounting for k in r.included_keys}


def test_d04_en_passant_victim_square_and_files():
    case = BY_ID["D04"]
    summary = summarize(case["fen"], case["uci"])
    capture = summary.events[0].payload
    assert (capture.captured_square, capture.landing_square, capture.is_en_passant) == (
        case["en_passant"]["captured_square"],
        case["en_passant"]["landing_square"],
        True,
    )
    assert {"STEPS/FILE_STATE:file-d", "STEPS/FILE_STATE:file-e"} <= keys_of(summary)


@pytest.mark.parametrize("case_id", ["D05-K", "D05-Q"])
def test_d05_castling_king_and_rook_are_distinct_events(case_id):
    case = BY_ID[case_id]
    summary = summarize(case["fen"], case["uci"])
    families = [e.key.family.value for e in summary.events]
    assert families == ["MOVE", "CASTLING_ROOK"]
    assert {e.key.subject.base_square for e in summary.events} == set(case["participants"])


@pytest.mark.parametrize("case_id", ["D06-q", "D06-r", "D06-b", "D06-n", "D07"])
def test_promotion_keeps_the_physical_pawn(case_id):
    case = BY_ID[case_id]
    summary = summarize(case["fen"], case["uci"])
    promotion = next(e for e in summary.events if e.key.family.value == "PROMOTION")
    assert promotion.key.subject.piece_type.value == "pawn"
    assert promotion.payload.after.piece_type.value == case["promoted_type"]
    assert summary.detail.mover == promotion.key.subject


@pytest.mark.parametrize("case_id", ["D08", "D10", "D19", "D20"])
def test_remote_subjects_are_core_included(case_id):
    case = BY_ID[case_id]
    summary = summarize(case["fen"], case["uci"])
    touched = set()
    for row in summary.selection_accounting:
        if row.bucket is not Bucket.STEPS:
            continue
        for key in row.included_keys:
            inner = key.property
            if type(inner) is PinKey:
                touched.update(b.base_square for b in (inner.pinner, inner.pinned, inner.king))
            elif hasattr(inner, "subject"):
                touched.add(inner.subject.base_square)
    assert set(case["remote_affected_subjects"]) <= touched
    participants = {p.base.base_square for p in summary.detail.participants}
    assert set(case["remote_affected_subjects"]) - participants  # genuinely remote


def test_d19_discovered_ray_and_pin():
    case = BY_ID["D19"]
    keys = keys_of(summarize(case["fen"], case["uci"]))
    assert "STEPS/PIN_PRESENT:pinner-e1:pinned-e7:king-e8" in keys
    assert any(k.startswith("STEPS/RAY_STATE:base-e1:") for k in keys)


def test_d20_remote_pawn_flags():
    case = BY_ID["D20"]
    expected = case["remotely_changed_pawn_flags"]
    summary = summarize(case["fen"], case["uci"])
    change = next(
        c
        for c in summary.selected_changes
        if c.key.family.value == "PAWN_FLAGS" and c.key.subject.base_square == expected["base"]
    )
    for fact, flags in ((change.before, expected["before"]), (change.after, expected["after"])):
        assert (fact.value.isolated, fact.value.doubled, fact.value.passed) == (
            flags["isolated"],
            flags["doubled"],
            flags["passed"],
        )


def test_d11_no_focus_and_no_cross_turn_legal_action():
    case = BY_ID["D11"]
    summary = summarize(case["fen"], case["uci"])
    families = {r.family.value for r in summary.selection_accounting}
    assert not families & {"FOCUS_OCCUPANT", "FOCUS_ATTACKERS", "FOCUS_LEGAL_CAPTURES_NOW"}
    assert summary.focus_timeline == ()


def test_d12_every_endpoint_is_a_semantic_duplicate():
    case = BY_ID["D12"]
    _, ledger = ledger_of(summarize(case["fen"], case["uci"]))
    endpoints = [c for c in ledger.values() if c.bucket is Bucket.ENDPOINTS]
    assert endpoints
    for row in endpoints:
        assert row.exclusion is PresentationExclusion.SEMANTIC_DUPLICATE
        assert row.duplicate_of == StepKey(1, row.key)


def test_d14_san_display_is_not_identity():
    case = BY_ID["D14-SAN"]
    base = BY_ID[case["expect_same_as"]]
    with_san = summarize(case["fen"], case["uci"], case["line_san_display"])
    plain = summarize(base["fen"], base["uci"])
    renderer = ScenarioSummaryRenderer()
    assert renderer.render(with_san) == renderer.render(plain)
    assert with_san.selection_accounting == plain.selection_accounting
    assert with_san.events == plain.events


def test_status_and_change_templates_are_closed():
    seen = set()
    for case in POSITIVE:
        report = ScenarioSummaryRenderer().render(summarize(case["fen"], case["uci"]))
        seen.update(s.template_id for s in (*report.digest, *report.detail))
        for sentence in (*report.digest, *report.detail):
            assert sentence.source_refs
            for word in (" because ", " improves", " better", " safe", " forces", " winning"):
                assert word not in sentence.text
    assert TemplateId.PLAYED_STATUS in seen and TemplateId.PLAYED_CHANGE in seen
