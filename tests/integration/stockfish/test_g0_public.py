"""G0 real public golden gate: CalliopeEngine.analyze_move() over real python-chess + Stockfish.

The system under test is only the production composition root.  A transparent observational
wrapper around the production StockfishAdapter records what the public DTO deliberately does not
expose (returned EngineLine.depth, engine call shape, request sessions, game tokens); it delegates
to the same process and changes nothing.

Every request uses an explicit depth-bounded budget with threads=1/hash=16 judgement options and
the frozen P7 profile, starts a fresh request session, and qualifies as a reproducibility golden
only if every P7 line reached depth 12 (so no 2000 ms time-cap preemption).
"""

import os
import shutil
import threading
from dataclasses import dataclass, field, fields

import chess.engine
import pytest

from calliope import AnalysisBudget, AnalysisOptions, AnalyzeMoveRequest, OutputMode
from calliope.adapters.stockfish import StockfishAdapter
from calliope.application.explanation import COUNTERFACTUAL_SETTINGS, MoveExplanationPipeline
from calliope.composition import create_calliope_engine
from calliope.contracts import ClaimEntityKind, CommentaryView, MoveAnalysisResult
from calliope.errors import ExplanationGraphError, FeatureUnavailableError

STOCKFISH = os.environ.get("CALLIOPE_STOCKFISH_PATH") or shutil.which("stockfish")
pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish binary not available")

BUDGET = AnalysisBudget(depth=12, multipv=3)
NO_EXPLANATION = "No verified explanation is available."
EV, LOCAL = "engine_verified", "local"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
_MATERIAL = "allows an engine-verified line with material loss."

# name -> (fen, move, quality, [(claim id, predicate, confidence, scope)], selected, sentences)
FIXTURES = {
    # 1+3: hanging piece and material loss selected; the removed-defender claim stays public.
    "hanging_material": (
        "3rk3/8/8/8/3N4/2P5/8/4K3 w - - 0 1",
        "c3c4",
        "blunder",
        [
            ("cl_001", "leaves_piece_hanging", EV, LOCAL),
            ("cl_002", "removes_defender", EV, LOCAL),
            ("cl_003", "allows_material_loss", EV, LOCAL),
        ],
        ("cl_003", "cl_001"),
        (f"Move c3c4 {_MATERIAL}", "Move c3c4 leaves white knight from d4 hanging."),
    ),
    "fork": (
        "r3k3/pp4pp/8/8/1n6/3B4/PP4PP/R3K3 w - - 0 1",
        "d3c4",
        "blunder",
        [("cl_001", "allows_fork", EV, LOCAL), ("cl_002", "allows_material_loss", EV, LOCAL)],
        ("cl_002", "cl_001"),
        (f"Move d3c4 {_MATERIAL}", "Move d3c4 allows a fork."),
    ),
    "exact_mate": (
        "4r1k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1",
        "d1d7",
        "blunder",
        [("cl_001", "allows_checkmate", "exact", LOCAL)],
        ("cl_001",),
        ("Move d1d7 allows checkmate.",),
    ),
    "engine_mate": (
        "6k1/5ppp/8/8/8/8/r4PPP/1R4K1 w - - 0 1",
        "b1b7",
        "blunder",
        [("cl_001", "allows_checkmate", EV, LOCAL), ("cl_002", "allows_material_loss", EV, LOCAL)],
        ("cl_001", "cl_002"),
        ("Move b1b7 allows an engine-verified mating line.", f"Move b1b7 {_MATERIAL}"),
    ),
    "forces_response": (
        "k7/8/2K5/8/8/8/8/1R6 w - - 0 1",
        "c6c7",
        "best",
        [("cl_001", "forces_response", "exact", LOCAL)],
        ("cl_001",),
        ("Move c6c7 forces response a8a7.",),
    ),
    "preservation": (
        "R1K5/4r3/8/8/8/8/7q/7k w - - 0 1",
        "a8a1",
        "best",
        [("cl_001", "avoids_representative_mate_failure", EV, "representative_alternatives")],
        ("cl_001",),
        (
            (
                "Compared with the tested representative alternatives, move a8a1 avoids the mate"
                " failure seen after a8a6 and a8b8."
            ),
        ),
    ),
    "equivalent_silence": ("7k/8/6K1/8/8/8/8/5Q2 w - - 0 1", "f1f8", "best", [], (), ()),
    "tested_material_threat": (
        "4k3/p7/8/7n/8/8/8/R3K3 w - - 0 1",
        "a1a5",
        "excellent",
        [("cl_001", "threatens_material_if_ignored", EV, "tested_response")],
        ("cl_001",),
        ("Move a1a5 creates a material threat that tested response a7a6 does not meet.",),
    ),
    "tested_mate_threat": (
        "6k1/5ppp/8/8/8/8/3B4/3Q2K1 w - - 0 1",
        "d2e3",
        "excellent",
        [("cl_001", "threatens_mate_if_ignored", EV, "tested_response")],
        ("cl_001",),
        ("Move d2e3 creates a mate threat that tested response g8f8 does not meet.",),
    ),
    "quiet_best_silence": (START, "e2e4", "best", [], (), ()),
    "inaccuracy_silence": (START, "h2h3", "inaccuracy", [], (), ()),
}
SILENT = {"equivalent_silence", "quiet_best_silence", "inaccuracy_silence"}
FORBIDDEN = (
    " because ",
    " therefore",
    " so ",
    " causes ",
    "only",
    "unique",
    " all ",
    "every",
    "forced",
    "exhaustive",
    "unstoppable",
    "unavoidable",
    "intend",
    "wanted",
    " on ",
)


# ---- transparent observation of the production adapter ------------------------------------------


@dataclass
class Recorder:
    calls: list = field(default_factory=list)
    events: list = field(default_factory=list)
    newgames: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def clear(self):
        with self.lock:
            self.calls.clear()
            self.events.clear()
            self.newgames = 0


@pytest.fixture(scope="module")
def recorder():
    rec = Recorder()
    patch = pytest.MonkeyPatch()
    analyze, session = StockfishAdapter.analyze, StockfishAdapter.request_session
    newgame = chess.engine.UciProtocol._ucinewgame

    def observe_analyze(self, position, settings, root_moves=None):
        result = analyze(self, position, settings, root_moves)
        with rec.lock:
            token = self._session_game
            rec.calls.append(
                (
                    threading.current_thread().name,
                    id(token) if token is not None else None,
                    position.position_id,
                    settings,
                    root_moves,
                    tuple(line.depth for line in result.lines),
                )
            )
            rec.events.append((threading.current_thread().name, "engine", id(token)))
        return result

    def observe_session(self):
        inner = session(self)

        class Observed:
            def __enter__(self_):
                inner.__enter__()
                with rec.lock:
                    rec.events.append((threading.current_thread().name, "acquire", None))

            def __exit__(self_, *exc):
                with rec.lock:
                    rec.events.append((threading.current_thread().name, "release", None))
                return inner.__exit__(*exc)

        return Observed()

    def observe_newgame(self):
        with rec.lock:
            rec.newgames += 1
        return newgame(self)

    patch.setattr(StockfishAdapter, "analyze", observe_analyze)
    patch.setattr(StockfishAdapter, "request_session", observe_session)
    patch.setattr(chess.engine.UciProtocol, "_ucinewgame", observe_newgame)
    yield rec
    patch.undo()


@pytest.fixture(scope="module")
def engine(recorder):
    with create_calliope_engine(STOCKFISH) as composed:  # type: ignore[arg-type]
        yield composed


def ask(engine, name, mode=OutputMode.STRUCTURED, budget=BUDGET):
    fen, move = FIXTURES[name][:2]
    options = AnalysisOptions(budget=budget, output_mode=mode)
    return engine.analyze_move(AnalyzeMoveRequest(fen=fen, move_uci=move, options=options))


@dataclass
class Observation:
    structured: MoveAnalysisResult
    commentary: MoveAnalysisResult
    work: dict


@pytest.fixture(scope="module")
def observed(engine, recorder):
    results = {}
    for name in FIXTURES:
        work = {}
        pair = []
        for mode in (OutputMode.STRUCTURED, OutputMode.COMMENTARY):
            recorder.clear()
            pair.append(ask(engine, name, mode))
            work[mode] = (list(recorder.calls), list(recorder.events), recorder.newgames)
        results[name] = Observation(*pair, work)
    return results


def p7_calls(calls):
    return [c for c in calls if c[3] == COUNTERFACTUAL_SETTINGS]


# ---- the golden ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_public_golden(observed, name):
    _, _, quality, claims, selected, sentences = FIXTURES[name]
    result = observed[name].commentary
    assert result.schema_version == "0.2"
    assert result.position_fen == FIXTURES[name][0]
    assert result.judgement.move_uci == FIXTURES[name][1]
    assert result.judgement.quality == quality
    assert [(c.claim_id, c.predicate, c.confidence, c.scope) for c in result.claims] == claims
    assert result.selected_claim_ids == selected
    assert result.variations == ()
    ids = [c.claim_id for c in result.claims]
    assert all(ids.count(claim_id) == 1 for claim_id in selected)
    assert result.commentary.sentences == sentences
    assert result.commentary.used_claim_ids == selected
    assert result.commentary.text == (" ".join(sentences) if sentences else NO_EXPLANATION)
    for sentence in result.commentary.sentences:
        lowered = f" {sentence.lower()} "
        assert not any(word in lowered for word in FORBIDDEN), sentence
    assert all(c.confidence != "forced" for c in result.claims)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_structured_and_commentary_parity(observed, name):
    o = observed[name]
    for f in fields(MoveAnalysisResult):
        if f.name != "commentary":
            assert getattr(o.structured, f.name) == getattr(o.commentary, f.name), f.name
    assert o.structured.commentary is None
    assert type(o.commentary.commentary) is CommentaryView
    # Identical engine/P7 work shape; P12 adds no engine call.
    structured_calls, _, _ = o.work[OutputMode.STRUCTURED]
    commentary_calls, _, _ = o.work[OutputMode.COMMENTARY]
    shape = [c[2:] for c in structured_calls]
    assert shape == [c[2:] for c in commentary_calls]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_depth_and_session_profile(observed, name):
    for mode in OutputMode:
        calls, events, newgames = observed[name].work[mode]
        judgement, p7 = calls[:2], p7_calls(calls)
        assert [c[3].threads for c in judgement] == [1, 1]
        assert [c[3].hash_mb for c in judgement] == [16, 16]
        assert len(p7) == len(calls) - 2  # every later call is a frozen-profile P7 probe
        # INACCURACY has no strict family, so it runs no P7 probe at all.
        assert (len(p7) == 0) is (name == "inaccuracy_silence")
        # Reproducibility qualification: depth-bound completion, never time-cap preemption.
        assert all(depth == 12 for c in calls for depth in c[5]), [c[5] for c in calls]
        tokens = {c[1] for c in calls}
        assert len(tokens) == 1 and None not in tokens  # one request, one game token
        assert events[0][1] == "acquire" and events[-1][1] == "release"
        assert sum(1 for e in events if e[1] == "acquire") == 1
        assert newgames == 1  # exactly one new-game boundary, never mid-request


# ---- scope, frame and selection safety ----------------------------------------------------------


def test_all_claims_are_public_and_selection_is_a_strict_subset(observed):
    result = observed["hanging_material"].structured
    assert len(result.claims) == 3 > len(result.selected_claim_ids) == 2
    assert result.selected_claim_ids == ("cl_003", "cl_001")
    assert "removes_defender" in {c.predicate for c in result.claims}


def test_hanging_piece_keeps_its_base_frame(observed):
    result = observed["hanging_material"].structured
    hanging = result.claims[0]
    punishment, piece = hanging.objects
    assert punishment.kind is ClaimEntityKind.MOVE and punishment.move_uci == "d8d4"
    assert punishment.position_id != hanging.base_position_id
    assert piece.kind is ClaimEntityKind.PIECE
    assert (piece.color, piece.base_piece_type, piece.base_square) == ("white", "knight", "d4")
    assert piece.at_position_id == hanging.base_position_id
    assert (piece.current_piece_type, piece.current_square) == ("knight", "d4")


@pytest.mark.parametrize(
    "name,response", [("tested_material_threat", "a7a6"), ("tested_mate_threat", "g8f8")]
)
def test_tested_response_scope_is_public(observed, name, response):
    result = observed[name].commentary
    (claim,) = result.claims
    assert claim.scope == "tested_response"
    (move,) = [o for o in claim.objects if o.kind is ClaimEntityKind.MOVE]
    assert move.move_uci == response and move.position_id != claim.base_position_id
    (sentence,) = result.commentary.sentences
    assert sentence.endswith(f"tested response {response} does not meet.")
    assert "not played" not in sentence and "unless" not in sentence


def test_representative_scope_is_public(observed):
    result = observed["preservation"].commentary
    (claim,) = result.claims
    assert claim.scope == "representative_alternatives"
    alternatives = [o for o in claim.objects if o.kind is ClaimEntityKind.MOVE]
    assert [m.move_uci for m in alternatives] == ["a8a6", "a8b8"]
    assert all(m.position_id == claim.base_position_id for m in alternatives)
    assert result.commentary.sentences[0].startswith(
        "Compared with the tested representative alternatives, "
    )


@pytest.mark.parametrize("name", sorted(SILENT))
def test_silence_keeps_the_judgement(observed, name):
    o = observed[name]
    assert o.structured.claims == () and o.structured.selected_claim_ids == ()
    assert o.structured.commentary is None
    assert o.commentary.commentary == CommentaryView(NO_EXPLANATION, (), ())
    assert o.structured.judgement.quality == FIXTURES[name][2]


def test_multipv_one_is_valid_p9_silence(engine):
    result = ask(engine, "forces_response", budget=AnalysisBudget(depth=12, multipv=1))
    assert result.judgement.quality == "best"
    assert result.claims == () and result.selected_claim_ids == ()


def test_heuristic_request_fails_before_any_engine_work(engine, recorder):
    recorder.clear()
    fen, move = FIXTURES["fork"][:2]
    options = AnalysisOptions(budget=BUDGET, allow_heuristic_claims=True)
    with pytest.raises(FeatureUnavailableError):
        engine.analyze_move(AnalyzeMoveRequest(fen=fen, move_uci=move, options=options))
    assert recorder.calls == [] and recorder.events == [] and recorder.newgames == 0


# ---- reproducibility across processes -----------------------------------------------------------


def test_fresh_process_reproduces_byte_identical_results(observed, recorder):
    with create_calliope_engine(STOCKFISH) as second:  # type: ignore[arg-type]
        for name in ("hanging_material", "tested_mate_threat", "preservation"):
            recorder.clear()
            again = ask(second, name, OutputMode.COMMENTARY)
            assert all(d == 12 for c in recorder.calls for d in c[5])
            assert repr(again) == repr(observed[name].commentary)


# ---- concurrency gate ---------------------------------------------------------------------------


def _run_pair(engine, names, failing=None):
    errors = {}
    results = {}
    barrier = threading.Barrier(2)

    def run(label, name):
        barrier.wait()
        try:
            results[label] = ask(engine, name, OutputMode.COMMENTARY)
        except Exception as exc:  # noqa: BLE001 - the gate inspects every outcome
            errors[label] = exc

    threads = [
        threading.Thread(target=run, args=(label, name), name=label)
        for label, name in zip(("A", "B"), names, strict=True)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)
    assert not any(thread.is_alive() for thread in threads)
    return results, errors


def _assert_serial(events):
    order = [e[0] for e in events]
    first = order[0]
    second = "B" if first == "A" else "A"
    cut = order.index(second)
    assert set(order[:cut]) == {first} and set(order[cut:]) == {second}, order
    for label in ("A", "B"):
        mine = [e for e in events if e[0] == label]
        assert mine[0][1] == "acquire" and mine[-1][1] == "release"


def test_concurrent_public_requests_never_interleave(engine, recorder, observed):
    recorder.clear()
    results, errors = _run_pair(engine, ("hanging_material", "tested_mate_threat"))
    assert errors == {}
    _assert_serial(recorder.events)
    tokens = {label: {c[1] for c in recorder.calls if c[0] == label} for label in ("A", "B")}
    assert all(len(t) == 1 and None not in t for t in tokens.values())
    assert tokens["A"] != tokens["B"]
    assert recorder.newgames == 2
    # Serialization keeps each request's answer identical to its isolated golden.
    assert repr(results["A"]) == repr(observed["hanging_material"].commentary)
    assert repr(results["B"]) == repr(observed["tested_mate_threat"].commentary)


def test_failed_request_releases_the_session_for_the_other(engine, recorder, monkeypatch):
    original = MoveExplanationPipeline.explain

    def fail_in_a(self, *args):
        if threading.current_thread().name == "A":
            raise ExplanationGraphError("injected failure inside A's session")
        return original(self, *args)

    monkeypatch.setattr(MoveExplanationPipeline, "explain", fail_in_a)
    recorder.clear()
    results, errors = _run_pair(engine, ("exact_mate", "forces_response"))
    assert set(errors) == {"A"} and type(errors["A"]) is ExplanationGraphError
    assert results["B"].selected_claim_ids == ("cl_001",)
    _assert_serial(recorder.events)
    assert sum(1 for e in recorder.events if e[1] == "release") == 2
