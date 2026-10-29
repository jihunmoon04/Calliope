"""The local analysis server (AS-D): the game pipeline, the ply cache, jobs and the HTTP API.

A redesign package: it never imports the legacy MVP, and nothing in facts, reasoning or results
imports it (`tests/test_package_boundaries.py`).
"""

from calliope.server.cache import MAX_LOADED, MAX_LOADED_MB, PlyCache, StoreFailed, canonical
from calliope.server.commentary import (
    CommentaryStore,
    board_form,
    board_size,
    game_key,
    listing,
    stale,
    subject_digest,
    with_commentary,
)
from calliope.server.files import temporary_name
from calliope.server.pipeline import (
    HEADERS,
    MAX_POSITION_RECORDS,
    MAX_STORE_SEARCHES,
    EngineSlot,
    InputError,
    JobFailed,
    ParsedGame,
    PlyProgress,
    Prefetch,
    analyse_game,
    analyse_ply,
    game_input,
    grading_for,
    normalized_ply,
    parse_game,
    plies_range,
    ply_request,
)

__all__ = [
    "HEADERS",
    "MAX_LOADED",
    "MAX_LOADED_MB",
    "MAX_POSITION_RECORDS",
    "MAX_STORE_SEARCHES",
    "CommentaryStore",
    "EngineSlot",
    "InputError",
    "JobFailed",
    "ParsedGame",
    "PlyCache",
    "PlyProgress",
    "Prefetch",
    "StoreFailed",
    "analyse_game",
    "analyse_ply",
    "board_form",
    "board_size",
    "canonical",
    "game_input",
    "game_key",
    "grading_for",
    "listing",
    "normalized_ply",
    "parse_game",
    "plies_range",
    "ply_request",
    "stale",
    "subject_digest",
    "temporary_name",
    "with_commentary",
]
