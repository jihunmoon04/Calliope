# R1-D — legacy capture seams, request transcript and tape replay (design draft)

Status: **DRAFT / AWAITING INDEPENDENT R1-D REVIEW** (design only; no implementation authorized).
Date: 2026-10-08. Stacked on PR #35 A0 (`design/analysis-trace-a0` @ `7fa3fbe`; A0 rev. 3 reviewed
READY_WITH_CORRECTIONS in review 5458061255, which authorized R1-D design work). Base source:
`main @ 4940554`.

Scope: the E/S/C observer seams, the request-local capture scope, `engine_transcript_v1`, tape
serialization and the verifying tape replay port, plus the evidence that legacy results, errors and
engine call sequences are unchanged. It closes A0 review items **C3** (0.3 scope wiring) and **C4**
(tape proof). No trace, no new evidence rule, no public API or schema change.

## 1. Verified source facts this design depends on

| Fact | Source |
| --- | --- |
| One `StockfishAdapter` instance is passed as `AnalyzeMoveService.engine`, `AnalyzeMoveService.sessions` and `CounterfactualAnalyzer.engine` | `composition.py` |
| One `CounterfactualAnalyzer` instance is shared by `BadMoveExplainer` and `GoodMoveExplainer` (`counterfactual` attribute); batches are issued at `bad_move.py:476/515` and `good_move.py:456/531` | `composition.py`, explainers |
| `request_session()` is a context manager owned per thread; nesting on the same thread raises `EngineConfigurationError`; `analyze()` outside a session serializes on the session lock | `adapters/stockfish/adapter.py` |
| `CounterfactualAnalyzer.execute` preflights all probes (no engine), then per probe either builds a terminal `ProbeResult` without an engine call or calls `engine.analyze(analysis_position, settings, root_moves)` and validates it | `services/counterfactual/analyzer.py` |
| `ObservedMoveService.execute` runs shape preflight and full supplied-line legality **before** `self.legacy.execute(request.base)` | `application/observe_move.py` |
| The facade calls `_move_analysis.execute` for 0.2 and `_observed_move_analysis.execute` for 0.3 | `engine.py` |

## 2. Components

```text
EngineObserver(inner: StockfishAdapter)          E + S seam, one object
   .analyze(position, settings, root_moves)      delegates; records EngineCall
   .request_session()                            delegates; records SessionEvent
   .close()                                      delegates (no record)
CounterfactualObserver(inner: CounterfactualAnalyzer)   C seam
   .execute(request)                             delegates; records BatchCall window
CapturingMoveUseCase(inner: AnalyzeMoveService)  opens/closes the request scope
   .execute(request) -> MoveAnalysisResult       identical to inner (scope opened, transcript dropped
                                                 unless a sink is configured)
   .execute_captured(request) -> CapturedRun      internal: result or error + sealed transcript
RequestCapture                                   mutable, scope-private event buffer
EngineTranscript (engine_transcript_v1)          immutable sealed record
TapeReplayEngine / TapeReplayCounterfactual      verifying replay ports (section 6)
```

### 2.1 Composition (identity contract)

`composition.py` changes only by wrapping:

- `observer = EngineObserver(stockfish)`; `AnalyzeMoveService(engine=observer, sessions=observer,
  ...)`; `CounterfactualAnalyzer(engine=observer, ...)` wrapped once as
  `p7 = CounterfactualObserver(analyzer)` and passed to **both** explainers.
- The facade close hook stays `stockfish.close`.
- Identity invariants after the change: `service.engine is service.sessions is observer`;
  `observer.inner is stockfish`; `bad.counterfactual is good.counterfactual is p7`;
  `p7.inner.engine is observer`. `CounterfactualObserver` exposes the inner analyzer's `chess`,
  `engine`, `tactical_rules` and `position_rules` as read-only delegated attributes.
- Required legacy test change (reviewed, not silent): `tests/unit/test_composition.py` assertions
  `service.engine is stockfish`, `service.sessions is stockfish`, `...counterfactual.engine is
  stockfish` become the observer forms above plus `observer.inner is stockfish`. No behavioural test
  changes.
- Test monkeypatches on `StockfishAdapter.analyze` / `request_session` (G0 integration recorder)
  keep working because the observer calls the adapter's methods.

## 3. Seam semantics

All seams follow one template:

```python
def analyze(self, position, settings, root_moves=None):
    capture = _ACTIVE.get()                      # None outside a scope: pure delegation
    token = _safe(capture, "begin_engine_call", position, settings, root_moves)
    try:
        result = self.inner.analyze(position, settings, root_moves)
    except BaseException as error:
        _safe(capture, "end_engine_call", token, error=error)
        raise                                    # the identical exception object
    _safe(capture, "end_engine_call", token, result=result)
    return result                                # the identical result object
```

- `_safe` never raises: any exception inside recording marks the capture `CAPTURE_FAILED` with the
  failure type, disables further recording for that scope and lets legacy continue (**fail-open
  recorder**).
- Seams never call the engine, the rules port or sessions on their own; they never copy, normalize,
  retry, reorder or suppress. The returned object and the raised exception are the inner ones.
- `request_session()` returns a context manager that enters the inner one first. If the inner enter
  raises (closed engine, nested session), it records `ENTER_FAILED` and re-raises. On exit it records
  `EXIT` or `EXIT_WITH_ERROR(type)` and then delegates `__exit__` with the same exception triple,
  returning the inner return value unchanged (the inner manager does not suppress).
- `CounterfactualObserver.execute` records `BATCH_BEGIN(request)` before delegating and
  `BATCH_END(result)` or `BATCH_ERROR(type)` after; engine calls between them carry this batch's
  sequence number (`batch_seq`) because the capture holds the open batch window.
- Outside an open scope every seam is pure delegation (one `ContextVar.get()` of overhead).

## 4. Request scope (closes C3)

- `_ACTIVE: ContextVar[RequestCapture | None]`, default `None`.
- `CapturingMoveUseCase.execute_captured(request)`:
  1. if `_ACTIVE.get()` is not `None`, the new scope is **not** opened (no nesting); the call
     delegates and returns a run marked `CAPTURE_FAILED(NESTED_SCOPE)`;
  2. otherwise create `RequestCapture(anchor=request)`, `token = _ACTIVE.set(capture)`;
  3. call `inner.execute(request)`; keep the result or the raised exception object;
  4. in `finally`: `_ACTIVE.reset(token)`, then **seal** the capture into an immutable
     `EngineTranscript` (status `COMPLETE`, `FAILED`, `INCOMPLETE` or `CAPTURE_FAILED`);
  5. return `CapturedRun(result | error, transcript)`; the caller re-raises the identical error
     object when the legacy call failed.
- `CapturingMoveUseCase.execute(request)` is what the facade and `ObservedMoveService` call: it runs
  `execute_captured`, hands the transcript to an optional sink (none in R1 production wiring) and
  returns the identical result or re-raises the identical exception.
- **0.2 wiring:** `CalliopeEngine._move_analysis = CapturingMoveUseCase(move_service)`.
- **0.3 wiring:** `ObservedMoveService(legacy=CapturingMoveUseCase(move_service), ...)` — the same
  wrapper instance. The 0.3 preflight and legality checks run before `self.legacy.execute`, i.e.
  before the scope opens; a preflight failure produces no scope and no events. The 0.3 atomic
  failure policy and DTO are unchanged; the transcript is not added to the 0.3 result.
- Thread/request isolation: each thread has its own context; two concurrent requests get distinct
  captures even though the Stockfish session serializes them. Capture extraction happens only after
  `reset`, so no later event can reach a sealed transcript.
- Boundary: the recorder is fail-open (legacy is never affected); the future new path is fail-closed
  on a transcript whose status is not `COMPLETE` (it refuses and reports, never guesses).

## 5. `engine_transcript_v1`

```text
EngineTranscript(
  version="engine_transcript_v1", status, status_reason,
  anchor: (entry_point, base_fen, base_position_id or None, move_uci),
  engine_identity or None,
  events: tuple[Event, ...]               # one global seq per scope
  legacy_outcome: RESULT(public 0.2 projection) | ERROR(type, message)
)
Event = SessionEvent(seq, kind: ENTER | ENTER_FAILED | EXIT | EXIT_WITH_ERROR, error_type)
      | EngineCall(seq, batch_seq | None, position: PositionSnapshot, settings, root_moves,
                   result: EngineAnalysis | None, error_type | None)
      | BatchCall(seq, request: CounterfactualBatchRequest, result: CounterfactualBatchResult | None,
                  error_type | None, engine_call_seqs: tuple[int, ...])
```

- `status`: `COMPLETE` (legacy returned, every batch returned); `FAILED` (legacy raised; events up to
  the failure kept); `INCOMPLETE` (a batch raised: its partial `ProbeResult`s were never returned and
  are therefore absent, only the error and the engine calls inside the window exist);
  `CAPTURE_FAILED` (recording failed; content unreliable and not usable as evidence).
- **Live versus serialized errors:** the live exception object exists only in `CapturedRun` (the
  delegation invariant is identity). Transcripts and tapes store `error_type` (qualified class name)
  and the message; they never claim to carry the object.
- Events are recorded with the live domain objects (frozen dataclasses). Serialization (section 6)
  is a separate, versioned encoding.

## 6. Tape serialization and replay (closes C4)

### 6.1 Tape

`tape_v1` = canonical JSON of one `EngineTranscript`: every domain object encoded field by field
(positions by FEN and id, moves by UCI and SAN, scores, WDL, depth/seldepth/nodes, settings, probes,
terminal outcomes), plus engine identity and the legacy outcome projection (`dataclasses.asdict` of
the 0.2 result, canonical `json.dumps`). Decoding validates every field and recomputes position ids
from FEN; unknown versions or fields are refused.

### 6.2 Replay ports

`TapeReplayEngine` replaces the adapter (it implements `analyze` and `request_session`) and
`TapeReplayCounterfactual` wraps the real `CounterfactualAnalyzer` during replay. Replay runs the
**unchanged legacy code** (`AnalyzeMoveService`, P8/P9, the real `CounterfactualAnalyzer`) with only
the engine replaced. Each operation is checked against the next unconsumed tape event:

| Check | Rule |
| --- | --- |
| Session | enter/exit order and kinds equal the tape; nesting rules as the adapter |
| Engine call | position id, **exact** `EngineSettings` equality, `root_moves` UCI tuple in order, enclosing batch seq all equal the recorded call; returns the decoded recorded `EngineAnalysis`; a recorded error is re-raised as a new instance of the recorded class with the recorded message |
| Batch | the request (probes with kind, base id, intervention and execution UCI; settings) equals the recorded request; engine calls inside the window are exactly the recorded `engine_call_seqs`; the returned result equals the recorded result field by field, including terminal-only `ProbeResult`s that made no engine call |
| End | no unconsumed event remains; legacy outcome projection (or error type and message) equals the recorded one |

Any mismatch raises `TapeMismatchError` naming the event seq; counts or order alone never pass.
`INCOMPLETE` / `FAILED` tapes replay up to the recorded failure and must reproduce the same error
type and message at the same seq.

## 7. Required evidence for R1 (implementation acceptance)

1. **Unchanged legacy:** with seams installed, the pre-change capture method used for I3 D18
   (11 G0 fixtures × 2 modes, real Stockfish) gives byte-identical 0.2 DTOs and identical
   engine/session sequences; the same through `analyze_move_with_observations` (nested result and
   0.3 sections unchanged against a pre-change capture).
2. **Transparency:** returned objects and raised exceptions are identical (`is`) to the inner ones
   for engine, session and batch seams, with and without an open scope; seams outside a scope record
   nothing.
3. **Failure injection** (fakes): engine error at call k inside and outside a batch; batch error
   after a terminal probe; session enter failure; exception inside the session body; judge and
   explanation errors; recorder internal failure (fail-open, legacy result unchanged,
   `CAPTURE_FAILED`).
4. **Isolation:** two threads issuing requests concurrently produce two transcripts with disjoint
   events; nested scope attempt marked and harmless; preflight failure in 0.3 produces no scope.
5. **Tape round trip:** record live → serialize → decode → replay reproduces legacy outcome and
   consumes every event; mutations of the tape (settings, root move order, position id, batch probe,
   terminal result, removed or extra event) each raise `TapeMismatchError`.
6. **Coverage of P7 shapes:** recorded and replayed batches cover BEST_RESPONSE, ALTERNATIVE_MOVE,
   REFUTATION (including terminal-only) and IGNORE_THREAT.
7. **Cost:** overhead per request with scope open and closed, reported separately for G0 normal and
   I3 worst requests.

## 8. Out of scope

Trace construction, line assembly, EngineEvidence role derivation (`legacy_role_rules_v1`), public
exposure of transcripts, new probes and any change to legacy logic. Those belong to T1-D/T1, I-D and
later packets.

## 9. Review questions / STOP

1. Is the single `EngineObserver` for E and S (preserving "one engine object") preferable to two
   wrappers, and is the composition-test identity change acceptable as stated?
2. Is the fail-open recorder / fail-closed consumer boundary sufficient?
3. Do the replay checks of section 6.2 prove identical call sequences and batch linkage, including
   terminal-only probes and partial batches?
4. Is wrapping the legacy use case (0.2 facade and `ObservedMoveService.legacy`) the right scope
   point for both entry points?

**STOP** if any seam changes a returned value, an exception, an engine call, a session operation or
the 0.3 preflight order, or if a transcript claims completeness it cannot prove.
