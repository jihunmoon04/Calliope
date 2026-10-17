"""Results: the game result document `calliope_result_v1` (AR-D).

`game_result(game, engine, plies)` projects the per-ply analyses and renderings of one game into
one JSON-ready document; `dumps` serializes it. The caller normalizes the game (PGN, SAN → UCI,
FENs) and passes the engine run; this package checks every analysis against them and refuses a
mismatch with `ResultError` (AR-D §5). `schema_errors` checks a stored document against the
shipped schema without a runtime dependency (AS1 re-review B3). It imports only the public names
of `calliope.reasoning` and `calliope.facts`, never the legacy MVP
(`tests/test_package_boundaries.py`).
"""

from calliope.results.document import (
    SCHEMA,
    Bundle,
    EngineRun,
    GameInput,
    GameMove,
    PlyInput,
    ResultError,
    dumps,
    game_result,
    schema,
    view_schema,
)
from calliope.results.validate import schema_errors

__all__ = [
    "SCHEMA",
    "Bundle",
    "EngineRun",
    "GameInput",
    "GameMove",
    "PlyInput",
    "ResultError",
    "dumps",
    "game_result",
    "schema",
    "schema_errors",
    "view_schema",
]
